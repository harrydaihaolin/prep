#!/usr/bin/env python3
"""Receiver-side bulk-uploader: chunk_*.json → Notion DB.

You (the receiver, not the scraper) run this against an unzipped algo_push/
directory and a Notion database you control.

Prerequisites (one-time, in YOUR Notion):
  1. https://www.notion.so/profile/integrations → + New integration → Internal
  2. Copy the "Internal Integration Secret" (starts with `ntn_` or `secret_`)
  3. Open the target database → ⋯ menu → Connections → add the integration
  4. Note the database ID — it's the 32-char hex blob in the DB URL between
     the workspace slug and the `?v=...` query string.

Usage:
    export NOTION_TOKEN='ntn_...'
    python3 scripts/upload_to_notion.py \
        --chunks /path/to/algo_push/ \
        --database <32-char-database-id>

Idempotent: stores {Source URL → page_id} in upload.state.json so reruns skip
already-uploaded pages. Use --no-preflight to skip the initial DB scan (only
relevant on a fresh DB you know is empty — saves ~5s).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from pathlib import Path

import requests

NOTION_API = "https://api.notion.com/v1"
NOTION_VERSION = "2022-06-28"
STATE_FILE = Path("upload.state.json")


def http_headers(token: str) -> dict:
    return {
        "Authorization": f"Bearer {token}",
        "Notion-Version": NOTION_VERSION,
        "Content-Type": "application/json",
    }


def load_state() -> dict:
    if STATE_FILE.exists():
        return json.loads(STATE_FILE.read_text())
    return {"created": {}}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, indent=2))


def preflight_existing(database_id: str, headers: dict) -> dict[str, str]:
    seen: dict[str, str] = {}
    cursor = None
    while True:
        body = {"page_size": 100}
        if cursor:
            body["start_cursor"] = cursor
        for attempt in range(3):
            r = requests.post(f"{NOTION_API}/databases/{database_id}/query",
                              headers=headers, json=body, timeout=30)
            if r.status_code < 500:
                break
            time.sleep(2)
        if r.status_code >= 400:
            print(f"  preflight failed: {r.status_code} {r.text[:200]}")
            return seen
        data = r.json()
        for result in data.get("results", []):
            url_prop = (result.get("properties") or {}).get("Source URL", {})
            url = url_prop.get("url") if isinstance(url_prop, dict) else None
            if url:
                seen[url] = result["id"]
        if not data.get("has_more"):
            break
        cursor = data.get("next_cursor")
    return seen


def expand_properties(props: dict) -> dict:
    out: dict = {}
    date_starts: dict = {}
    date_ends: dict = {}

    for k, v in props.items():
        if k.startswith("date:"):
            _, name, kind = k.split(":")
            if kind == "start":
                date_starts[name] = v
            elif kind == "end":
                date_ends[name] = v
            continue
        if k == "Question":
            out["Question"] = {"title": [{"text": {"content": str(v)[:2000]}}]}
        elif k == "Source URL":
            out["Source URL"] = {"url": v}
        elif k in ("Status", "Difficulty", "Type", "Stage"):
            out[k] = {"select": {"name": str(v)}}
        elif k == "Acceptance Rate":
            out["Acceptance Rate"] = {"number": float(v)}
        elif k in ("Companies", "Tags"):
            try:
                items = json.loads(v) if isinstance(v, str) else list(v or [])
            except Exception:
                items = []
            out[k] = {"multi_select": [{"name": str(s)} for s in items]}

    for name, start in date_starts.items():
        end = date_ends.get(name)
        out[name] = {"date": {"start": start, **({"end": end} if end else {})}}
    return out


def text_runs(s: str) -> list:
    s = s.replace("\u00a0", " ")
    runs: list = []
    cur = ""

    def flush():
        nonlocal cur
        if cur:
            for j in range(0, len(cur), 2000):
                runs.append({"type": "text", "text": {"content": cur[j:j + 2000]}})
            cur = ""

    link_pat = re.compile(r"\[([^\]]+)\]\(([^)]+)\)")
    last = 0
    for m in link_pat.finditer(s):
        cur += s[last:m.start()]
        flush()
        runs.append({"type": "text",
                     "text": {"content": m.group(1)[:2000], "link": {"url": m.group(2)}}})
        last = m.end()
    cur += s[last:]
    flush()
    return runs


def md_to_blocks(md: str) -> list:
    blocks: list = []
    lines = md.split("\n")
    i = 0

    def para(text):
        return {"object": "block", "type": "paragraph",
                "paragraph": {"rich_text": text_runs(text)}}

    while i < len(lines):
        ln = lines[i]
        stripped = ln.strip()

        if not stripped:
            i += 1
            continue

        if stripped == "---":
            blocks.append({"object": "block", "type": "divider", "divider": {}})
            i += 1
            continue

        if stripped.startswith("## "):
            blocks.append({"object": "block", "type": "heading_2",
                           "heading_2": {"rich_text": text_runs(stripped[3:])}})
            i += 1
            continue
        if stripped.startswith("### "):
            blocks.append({"object": "block", "type": "heading_3",
                           "heading_3": {"rich_text": text_runs(stripped[4:])}})
            i += 1
            continue

        if stripped.startswith("```"):
            lang = stripped[3:].strip() or "plain text"
            lang_map = {"py": "python", "js": "javascript", "ts": "typescript",
                        "": "plain text", "plain": "plain text"}
            lang = lang_map.get(lang, lang)
            body_lines: list = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                body_lines.append(lines[i])
                i += 1
            i += 1
            body = "\n".join(body_lines)[:2000]
            blocks.append({"object": "block", "type": "code",
                           "code": {"rich_text": [{"type": "text", "text": {"content": body}}],
                                    "language": lang}})
            continue

        if stripped.startswith("<callout"):
            m = re.match(r'<callout(?:\s+icon="([^"]*)")?(?:\s+color="([^"]*)")?\s*>', stripped)
            icon = (m.group(1) if m and m.group(1) else "\U0001f3af")
            color = (m.group(2) if m and m.group(2) else "blue_background")
            if not color.endswith("_background"):
                color = color.replace("_bg", "_background")
            body_lines = []
            i += 1
            while i < len(lines) and "</callout>" not in lines[i]:
                body_lines.append(lines[i])
                i += 1
            i += 1
            body = "\n".join(body_lines).strip()
            blocks.append({"object": "block", "type": "callout",
                           "callout": {"rich_text": text_runs(body[:2000]),
                                       "icon": {"type": "emoji", "emoji": icon},
                                       "color": color}})
            continue

        if stripped.startswith("<details>"):
            i += 1
            summary = ""
            children_lines: list = []
            while i < len(lines) and "</details>" not in lines[i]:
                ll = lines[i].strip()
                if ll.startswith("<summary>"):
                    summary = re.sub(r"</?summary>", "", ll).strip()
                else:
                    children_lines.append(lines[i])
                i += 1
            i += 1
            children_md = "\n".join(children_lines).strip()
            children_blocks = md_to_blocks(children_md) if children_md else []
            blocks.append({"object": "block", "type": "toggle",
                           "toggle": {"rich_text": text_runs(summary),
                                      "children": children_blocks[:100]}})
            continue

        if stripped.startswith("- "):
            blocks.append({"object": "block", "type": "bulleted_list_item",
                           "bulleted_list_item": {"rich_text": text_runs(stripped[2:])}})
            i += 1
            continue
        if re.match(r"^\d+\.\s", stripped):
            text = re.sub(r"^\d+\.\s", "", stripped)
            blocks.append({"object": "block", "type": "numbered_list_item",
                           "numbered_list_item": {"rich_text": text_runs(text)}})
            i += 1
            continue
        if stripped.startswith("> "):
            blocks.append({"object": "block", "type": "quote",
                           "quote": {"rich_text": text_runs(stripped[2:])}})
            i += 1
            continue

        blocks.append(para(stripped))
        i += 1

    return blocks


def create_page(page: dict, database_id: str, headers: dict) -> str | None:
    body = {
        "parent": {"database_id": database_id},
        "properties": expand_properties(page["properties"]),
        "children": md_to_blocks(page.get("content", ""))[:100],
    }
    icon = page.get("icon")
    if icon and len(icon) <= 4:
        body["icon"] = {"type": "emoji", "emoji": icon}

    last = None
    for attempt in range(5):
        r = requests.post(f"{NOTION_API}/pages", headers=headers, json=body, timeout=30)
        if r.status_code < 400:
            return r.json()["id"]
        last = (r.status_code, r.text[:300])
        if r.status_code in (429, 502, 503, 504):
            time.sleep(1 + attempt * 2)
            continue
        break
    title = page["properties"].get("Question", "?")
    print(f"  FAIL {title!r}: {last[0]} {last[1]}")
    return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--chunks", required=True, help="Path to unzipped algo_push/ directory")
    ap.add_argument("--database", required=True, help="Notion database ID (32-char hex)")
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--no-preflight", action="store_true")
    args = ap.parse_args()

    token = os.environ.get("NOTION_TOKEN")
    if not token:
        print("ERROR: NOTION_TOKEN env var not set. See top of this file for setup.")
        return 1

    chunk_dir = Path(args.chunks)
    if not chunk_dir.is_dir():
        print(f"ERROR: {chunk_dir} is not a directory")
        return 1

    headers = http_headers(token)
    pages: list = []
    for ch in sorted(chunk_dir.glob("chunk_*.json")):
        d = json.loads(ch.read_text(encoding="utf-8"))
        pages.extend(d["pages"])
    print(f"Loaded {len(pages)} pages from {chunk_dir}")

    state = load_state()
    created = state.setdefault("created", {})

    if not args.no_preflight:
        print(f"Preflight: scanning DB {args.database[:8]}… for existing rows…")
        for url, pid in preflight_existing(args.database, headers).items():
            created.setdefault(url, pid)
        print(f"  Found {len(created)} existing pages (will skip)")
        save_state(state)

    todo = [p for p in pages if p["properties"]["Source URL"] not in created]
    if args.start:
        todo = todo[args.start:]
    if args.limit:
        todo = todo[: args.limit]
    print(f"To create: {len(todo)}  Already done: {len(created)}")

    ok = fail = 0
    t0 = time.time()
    for i, page in enumerate(todo, 1):
        url = page["properties"]["Source URL"]
        pid = create_page(page, args.database, headers)
        if pid:
            created[url] = pid
            ok += 1
        else:
            fail += 1
        if i % 10 == 0 or i == len(todo):
            save_state(state)
            rate = i / max(time.time() - t0, 0.001)
            eta = (len(todo) - i) / rate if rate > 0 else 0
            print(f"[{i:>3}/{len(todo)}] ok={ok} fail={fail} {rate:.1f}/s ETA={eta:.0f}s")
        time.sleep(0.35)

    save_state(state)
    print(f"\nDone in {time.time() - t0:.0f}s — {ok} ok, {fail} fail")
    return 0 if fail == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
