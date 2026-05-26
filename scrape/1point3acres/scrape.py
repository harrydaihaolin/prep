#!/usr/bin/env python3
"""Scrape coding-interview threads from 1point3acres.com (Discuz forum).

This is a starter scraper. It pages a forum board, harvests thread URLs that
look like coding-interview reports (面经), then fetches each thread and saves
its raw HTML + structured fields into a per-thread JSON file. A separate
renderer (`render.py`) turns those JSON files into Notion-payload chunks.

# Authentication

1point3acres runs Discuz, which uses multiple cookies (`<prefix>_<suffix>_auth`,
`_saltkey`, etc.). The simplest reliable way to authenticate is to copy your
ENTIRE `Cookie:` header from a logged-in browser session and pass it in:

  1. In Chrome/Firefox DevTools (logged in to 1point3acres):
       Network tab → reload page → click any request → Headers →
       copy the entire `Cookie:` value
  2. Save to `~/.1p3a-cookie` (single line, no quotes), or
     export ACRES_COOKIE='cookie1=val1; cookie2=val2; ...'

The scraper rejects responses that look like login redirects.

# Usage

  export ACRES_COOKIE="..."           # or: ~/.1p3a-cookie
  python3 scrape.py probe            # 1-shot auth check
  python3 scrape.py board --fid 145 --pages 5
  python3 scrape.py thread --tid 1234567

# Politeness

We sleep 1.5-3.5s between page fetches. 1point3acres has strict anti-bot
behaviour; if you get 403 or a redirect to a CAPTCHA page, slow down further
or back off entirely. This script is for your personal account; do not run
it from multiple machines concurrently.
"""
from __future__ import annotations

import argparse
import json
import os
import random
import re
import sys
import time
from pathlib import Path
from urllib.parse import urlencode

import requests

BASE = "https://www.1point3acres.com/bbs"
OUTPUT_DIR = Path(__file__).parent / "raw"
OUTPUT_DIR.mkdir(exist_ok=True)
COOKIE_FILE = Path.home() / ".1p3a-cookie"

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
ACCEPT_LANG = "en-US,en;q=0.9,zh-CN;q=0.8,zh;q=0.7"


def load_cookie_header() -> str:
    """Return the raw `Cookie:` header value to send with every request."""
    env = os.environ.get("ACRES_COOKIE", "").strip()
    if env:
        return env
    if COOKIE_FILE.exists():
        return COOKIE_FILE.read_text(encoding="utf-8").strip()
    print(
        "ERROR: no cookie provided.\n"
        "  Export ACRES_COOKIE='cookie1=val1; cookie2=val2; ...', or\n"
        f"  write the cookie header to {COOKIE_FILE}.\n"
        "Copy from DevTools → Network → any request → Headers → 'Cookie:' value.",
        file=sys.stderr,
    )
    sys.exit(2)


def make_session(cookie_header: str) -> requests.Session:
    s = requests.Session()
    s.headers.update({
        "User-Agent": UA,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": ACCEPT_LANG,
        "Cookie": cookie_header,
        "Referer": BASE + "/",
    })
    return s


def fetch(session: requests.Session, url: str, *, allow_login_redirect: bool = False) -> str | None:
    r = session.get(url, timeout=20, allow_redirects=False)
    if r.status_code in (301, 302, 303):
        loc = r.headers.get("Location", "")
        if not allow_login_redirect and ("logging" in loc or "login" in loc):
            print(f"  AUTH FAIL: redirect to {loc[:120]}", file=sys.stderr)
            return None
        return fetch(session, loc if loc.startswith("http") else f"{BASE}/{loc.lstrip('/')}")
    if r.status_code != 200:
        print(f"  HTTP {r.status_code} fetching {url}", file=sys.stderr)
        return None
    # Discuz pages are GBK-encoded
    body = r.content.decode("gbk", errors="ignore")
    # Detect "you need to login" pages that come back as 200
    if "您还未登录" in body or "您需要先登录" in body or "请先登录后才能继续" in body:
        if not allow_login_redirect:
            print(f"  AUTH FAIL: login wall on {url[:120]}", file=sys.stderr)
            return None
    return body


def probe(session: requests.Session) -> int:
    body = fetch(session, f"{BASE}/forum.php", allow_login_redirect=True)
    if not body:
        print("FAIL: could not fetch /forum.php")
        return 1
    # Look for username greeting `欢迎您, <name>` and logout link
    m_user = re.search(r"欢迎您[,，]\s*<a[^>]*>([^<]+)</a>", body)
    has_logout = "退出" in body or "action=logout" in body
    if has_logout and m_user:
        print(f"OK: authenticated as {m_user.group(1).strip()}")
        return 0
    if has_logout:
        print("OK: authenticated (logout link present)")
        return 0
    print("FAIL: not authenticated (no logout link, login form present).")
    print("  Re-export your cookies; you probably only have the _auth cookie")
    print("  and are missing _saltkey or _sid. Copy the FULL Cookie header.")
    return 1


THREAD_LINK = re.compile(r'<a[^>]+href="(?:forum\.php\?mod=viewthread&tid=|thread-)(\d+)[^"]*"[^>]*class="[^"]*xst[^"]*"[^>]*>([^<]+)</a>')


def list_board(session: requests.Session, fid: int, pages: int) -> list[dict]:
    """List thread metadata across `pages` of a board (fid = forum id)."""
    threads: list[dict] = []
    for page in range(1, pages + 1):
        url = f"{BASE}/forum.php?mod=forumdisplay&fid={fid}&page={page}"
        body = fetch(session, url)
        if not body:
            break
        for m in THREAD_LINK.finditer(body):
            tid = int(m.group(1))
            title = re.sub(r"<[^>]+>", "", m.group(2)).strip()
            threads.append({"tid": tid, "title": title,
                            "url": f"{BASE}/forum.php?mod=viewthread&tid={tid}"})
        print(f"page {page}: {len(threads)} threads cumulative")
        time.sleep(random.uniform(1.5, 3.5))
    return threads


# Discuz post-body markup: <td class="t_f" id="postmessageN">…</td>
POST_BODY = re.compile(r'<td[^>]+class="t_f"[^>]*id="postmessage_\d+"[^>]*>(.*?)</td>', re.DOTALL)
TITLE = re.compile(r'<span id="thread_subject">([^<]+)</span>')
THREAD_TAGS = re.compile(r'<em>\[<a[^>]*>([^<]+)</a>\]</em>')


def parse_thread(html: str, tid: int) -> dict:
    """Extract title, OP body (HTML), tag prefix, and meta from a thread page."""
    title_m = TITLE.search(html)
    body_m = POST_BODY.search(html)
    tag_m = THREAD_TAGS.search(html)
    return {
        "tid": tid,
        "url": f"{BASE}/forum.php?mod=viewthread&tid={tid}",
        "title": (title_m.group(1).strip() if title_m else ""),
        "tag_prefix": (tag_m.group(1).strip() if tag_m else ""),
        "op_body_html": (body_m.group(1).strip() if body_m else ""),
    }


def fetch_thread(session: requests.Session, tid: int) -> dict | None:
    url = f"{BASE}/forum.php?mod=viewthread&tid={tid}"
    body = fetch(session, url)
    if not body:
        return None
    return parse_thread(body, tid)


def cmd_probe(args):
    sess = make_session(load_cookie_header())
    return probe(sess)


def cmd_board(args):
    sess = make_session(load_cookie_header())
    if probe(sess) != 0:
        return 1
    threads = list_board(sess, args.fid, args.pages)
    out = OUTPUT_DIR / f"board_{args.fid}_threads.json"
    out.write_text(json.dumps(threads, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {len(threads)} thread refs → {out}")
    return 0


def cmd_thread(args):
    sess = make_session(load_cookie_header())
    if probe(sess) != 0:
        return 1
    for tid in args.tids:
        out = OUTPUT_DIR / f"thread_{tid}.json"
        if out.exists() and not args.force:
            print(f"  skip {tid} (cached)")
            continue
        data = fetch_thread(sess, tid)
        if not data:
            print(f"  FAIL {tid}")
            continue
        out.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"  ok {tid} → {out.name}  ({len(data['op_body_html'])} body chars)")
        time.sleep(random.uniform(1.5, 3.5))
    return 0


def cmd_drain(args):
    """Read board_*.json files and fetch every uncached thread."""
    sess = make_session(load_cookie_header())
    if probe(sess) != 0:
        return 1
    tids: list[int] = []
    for f in OUTPUT_DIR.glob("board_*_threads.json"):
        for t in json.loads(f.read_text(encoding="utf-8")):
            tids.append(t["tid"])
    tids = sorted(set(tids))
    print(f"Total unique threads queued: {len(tids)}")
    todo = [t for t in tids if not (OUTPUT_DIR / f"thread_{t}.json").exists()]
    print(f"To fetch: {len(todo)}")
    if args.limit:
        todo = todo[: args.limit]
    for i, tid in enumerate(todo, 1):
        data = fetch_thread(sess, tid)
        if data:
            (OUTPUT_DIR / f"thread_{tid}.json").write_text(
                json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
            )
        print(f"[{i:>4}/{len(todo)}] tid={tid} {'ok' if data else 'FAIL'}")
        time.sleep(random.uniform(2.0, 4.5))
    return 0


def main():
    ap = argparse.ArgumentParser(description="1point3acres.com Discuz scraper")
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("probe", help="Confirm cookies authenticate").set_defaults(func=cmd_probe)

    p_board = sub.add_parser("board", help="List threads from a forum board")
    p_board.add_argument("--fid", type=int, required=True, help="Forum id (e.g. 145 = 面经)")
    p_board.add_argument("--pages", type=int, default=3)
    p_board.set_defaults(func=cmd_board)

    p_thread = sub.add_parser("thread", help="Fetch one or more threads by id")
    p_thread.add_argument("--tids", type=int, nargs="+", required=True)
    p_thread.add_argument("--force", action="store_true")
    p_thread.set_defaults(func=cmd_thread)

    p_drain = sub.add_parser("drain", help="Fetch every uncached thread referenced in board_*.json")
    p_drain.add_argument("--limit", type=int, default=0)
    p_drain.set_defaults(func=cmd_drain)

    args = ap.parse_args()
    sys.exit(args.func(args))


if __name__ == "__main__":
    main()
