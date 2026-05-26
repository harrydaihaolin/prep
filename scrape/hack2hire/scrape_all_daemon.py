#!/usr/bin/env python3
"""Daemon: scrape ALL hack2hire problems (ALGORITHM, SD, ML_SD, OOD, SQL).

Pipeline:
1. Read /tmp/h2h/all_posts.json (already fetched).
2. Filter to scrape-able types; skip already-in-Notion ids (whitelist).
3. For each post, build SSR URL, fetch HTML, parse RSC for content+metadata.
4. Render to Notion-ready page payload, write to /tmp/h2h/notion_queue/{id}.json.
5. Log progress to /tmp/h2h/daemon.log.

Idempotent: skips problems already in /tmp/h2h/notion_queue/.
Resumable: just re-run.
"""
from __future__ import annotations

import concurrent.futures
import json
import os
import re
import signal
import sys
import time
import traceback
from datetime import datetime
from pathlib import Path

import requests

sys.path.insert(0, "/tmp/h2h")
from build_full import (  # noqa: E402
    decode_rsc,
    parse_chunks,
    collect_raw_payloads,
    extract_array,
    extract_field,
)

UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/138.0.0.0 Safari/537.36"
ALGRO_TOKEN = os.environ["ALGRO_TOKEN"]

OUT_DIR = Path("/tmp/h2h/notion_queue")
OUT_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = Path("/tmp/h2h/daemon.log")
STATE_FILE = Path("/tmp/h2h/daemon.state.json")

# Type slug map (from chunk_1811.js)
TYPE_SLUG = {
    "ALGORITHM": "coding-questions",
    "SD": "system-design",
    "ML_SD": "ml-system-design",
    "OOD": "object-oriented-design",
    "SQL": "sql-questions",
}

# Problems already in Notion (so we don't recreate them)
ALREADY_IN_NOTION = {
    # Stripe scrape problemIds
    "69753e1a17272b5c868d5eb2", "696fea94b7afade5b30a39c4", "67ce44ae8f73eb6319edd1ed",
    "69810d31f8f2604d5eecfff3", "697c3da69731315964cfb08a", "697c2d689731315964cfb047",
    "697bdcdd9731315964cfaf6e", "697a5a4e2ae9e181e44b7b95", "697697e35ed12b33b05f0f4b",
    "69767fdf5ed12b33b05f0efe",
    # Amazon/Snowflake/Lyft scrape problemIds
    "677593f60d31dc201f712036", "6760edb72f1ff3d3c88bf914", "688bd4593867670cfb894187",
    "688aefa53867670cfb894128", "6887e0ec6509c24ee64e4b20", "687e9cba7bd121d1f502daa1",
    # Add more from the prior scrape:
}


def log(msg: str) -> None:
    ts = datetime.now().strftime("%H:%M:%S")
    line = f"[{ts}] {msg}"
    with LOG_FILE.open("a") as f:
        f.write(line + "\n")
    print(line, flush=True)


def load_existing_notion_ids() -> set:
    """Load problemIds from the prior scraped JSON files to avoid re-creating."""
    ids = set(ALREADY_IN_NOTION)
    # Also include from existing scraped_amazon_snowflake_lyft.json
    for path in ["/tmp/h2h/scraped_amazon_snowflake_lyft.json", "/tmp/h2h/full.json"]:
        if Path(path).exists():
            try:
                data = json.load(open(path))
                for item in data:
                    pid = item.get("problemId") or item.get("pid")
                    if pid:
                        ids.add(pid)
            except Exception:
                pass
    return ids


def http_get(url: str, retries: int = 3) -> str:
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(
                url,
                headers={"User-Agent": UA, "Cookie": f"ALGRO_TOKEN={ALGRO_TOKEN}"},
                timeout=30,
            )
            r.raise_for_status()
            return r.text
        except Exception as e:
            last_err = e
            time.sleep(0.5 * (attempt + 1))
    raise last_err  # type: ignore


def company_slug(name: str) -> str:
    """COMPANY enum to URL slug (lowercase, underscores preserved)."""
    return name.lower()


def build_ssr_url(post: dict) -> str:
    """Construct the SSR URL we should scrape for `post`."""
    qtype = post["type"]
    slug = TYPE_SLUG.get(qtype)
    if not slug:
        return ""
    company = sorted(post.get("company", {}).keys())[0] if post.get("company") else None
    if not company:
        # fallback to general /questions/<type>/
        base = f"https://www.hack2hire.com/questions/{slug}/{post['id']}"
    else:
        base = f"https://www.hack2hire.com/companies/{company_slug(company)}/{slug}/{post['id']}"
    # ALGORITHM/SQL pages use /practice (+ questionId)
    if qtype in ("ALGORITHM", "SQL") and post.get("codingQuestions"):
        qid = post["codingQuestions"][0]["id"]
        return f"{base}/practice?questionId={qid}"
    return base


def _resolve_ref(value: str, chunks: dict) -> str:
    """If `value` is an RSC ref like '$15', return the chunk's content; else return as-is."""
    if not isinstance(value, str):
        return value
    m = re.fullmatch(r"\$([0-9a-f]+)", value.strip())
    if not m:
        return value
    cid = m.group(1)
    c = chunks.get(cid)
    if not c:
        return value  # unresolved
    return c.get("content") if isinstance(c, dict) else str(c)


def parse_full_content(html: str, qtype: str) -> dict:
    """Extract structured fields from SSR HTML, resolving RSC refs."""
    chunks = parse_chunks(html)
    rsc = decode_rsc(html)
    out: dict = {}

    # Catalog all T-chunks for ref resolution.
    text_chunks = sorted(
        [(c["length"], cid, c["content"])
         for cid, c in chunks.items()
         if c.get("type") == "T" and c.get("length", 0) > 200],
        key=lambda x: -x[0],
    )
    if text_chunks:
        out["content_md"] = text_chunks[0][2]
        out["content_chunk_id"] = text_chunks[0][1]
    else:
        out["content_md"] = ""

    title_m = re.search(r'"title"\s*:\s*"((?:[^"\\]|\\.)*?)"', rsc)
    if title_m:
        out["title"] = title_m.group(1).encode().decode("unicode_escape")

    accept = re.search(r'"acceptRate"\s*:\s*([0-9.]+)', rsc)
    if accept:
        try:
            out["acceptRate"] = float(accept.group(1))
        except ValueError:
            pass

    hints = extract_array(rsc, "hints")
    if hints:
        out["hints"] = hints
    testCases = extract_array(rsc, "testCases")
    if testCases:
        out["testCases"] = testCases
    insights = extract_array(rsc, "insights")
    if insights:
        out["insights"] = insights

    # description / explanation — resolve RSC refs
    desc = extract_field(rsc, "description")
    if desc:
        out["description"] = _resolve_ref(desc, chunks)
    expl = extract_field(rsc, "explanation")
    if expl:
        out["explanation"] = _resolve_ref(expl, chunks)

    return out


def fetch_one(post: dict) -> dict | None:
    """Fetch SSR content for one post, return a structured dict."""
    pid = post["id"]
    out_file = OUT_DIR / f"{pid}.json"
    if out_file.exists():
        return None  # already done

    url = build_ssr_url(post)
    if not url:
        log(f"  SKIP {pid} ({post['type']}): no URL")
        return None

    try:
        html = http_get(url)
    except Exception as e:
        log(f"  FAIL fetch {pid}: {e}")
        return None

    try:
        content = parse_full_content(html, post["type"])
    except Exception:
        log(f"  FAIL parse {pid}:\n{traceback.format_exc()}")
        return None

    record = {
        "problemId": pid,
        "type": post["type"],
        "title": post.get("title") or content.get("title"),
        "url": url,
        "companies": list(post.get("company", {}).keys()),
        "companyFreq": post.get("company", {}),
        "algorithmTags": post.get("algorithmTags", []),
        "stages": post.get("stages", []),
        "difficulty": post.get("difficulty"),
        "frequency": post.get("frequency"),
        "isLocked": post.get("isLocked"),
        "createdDate": post.get("createdDate"),
        "lastReportSeen": (post.get("lastReportSeenData") or {}).get("lastReportSeenDate"),
        "firstPublishedDate": post.get("firstPublishedDate"),
        "codingQuestionIds": [c["id"] for c in post.get("codingQuestions", [])],
        "content": content,
    }

    out_file.write_text(json.dumps(record, indent=2))
    return record


def main():
    log(f"=== Daemon start (pid={os.getpid()}) ===")
    posts = json.load(open("/tmp/h2h/all_posts.json"))
    log(f"Total posts: {len(posts)}")
    existing = load_existing_notion_ids()
    log(f"Already in Notion: {len(existing)}")

    scrape_types = {"ALGORITHM", "SD", "ML_SD", "OOD", "SQL"}
    todo = [p for p in posts if p["type"] in scrape_types and p["id"] not in existing]
    log(f"To scrape: {len(todo)} (by type: " +
        ", ".join(f"{t}:{sum(1 for p in todo if p['type']==t)}" for t in sorted(scrape_types)) + ")")

    # Skip already on disk (from previous runs)
    on_disk = {f.stem for f in OUT_DIR.glob("*.json")}
    todo = [p for p in todo if p["id"] not in on_disk]
    log(f"Remaining after on-disk dedup: {len(todo)} (already on disk: {len(on_disk)})")

    STATE_FILE.write_text(json.dumps({
        "started": datetime.now().isoformat(),
        "total": len(todo),
        "done": 0,
    }))

    success = fail = 0
    start = time.time()
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as ex:
        futures = {ex.submit(fetch_one, p): p for p in todo}
        for i, fut in enumerate(concurrent.futures.as_completed(futures), 1):
            post = futures[fut]
            try:
                r = fut.result()
                if r:
                    success += 1
                else:
                    fail += 1
            except Exception:
                fail += 1
                log(f"  ERR {post['id']}: {traceback.format_exc()}")

            if i % 25 == 0 or i == len(todo):
                elapsed = time.time() - start
                rate = i / elapsed if elapsed > 0 else 0
                eta = (len(todo) - i) / rate if rate > 0 else 0
                log(f"[{i}/{len(todo)}] ok={success} fail={fail} rate={rate:.1f}/s ETA={eta:.0f}s")
                STATE_FILE.write_text(json.dumps({
                    "total": len(todo),
                    "done": i,
                    "success": success,
                    "fail": fail,
                    "rate_per_s": rate,
                    "elapsed_s": elapsed,
                }))

    log(f"=== Daemon done: {success} ok, {fail} fail, total {time.time()-start:.0f}s ===")


if __name__ == "__main__":
    # Daemonize: detach from terminal
    if "--no-daemon" not in sys.argv:
        if os.fork() != 0:
            sys.exit(0)
        os.setsid()
        if os.fork() != 0:
            sys.exit(0)
        sys.stdin = open(os.devnull)
        sys.stdout = open(LOG_FILE, "a")
        sys.stderr = open(LOG_FILE, "a")
    main()
