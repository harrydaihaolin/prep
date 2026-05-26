#!/usr/bin/env python3
"""Rewrite notion_chunks for the new mikoxyr workspace.

- Re-targets parent.data_source_id at the new DB.
- Keeps `date:Last Reported:*` expanded props (prep_full_push stripped them).
- Unwraps single-element `Stage` arrays into a plain string (DB is SELECT, not MULTI_SELECT).
- Sanitises page icons + in-content callout icons (problematic emoji -> safe fallbacks).
- Strips stray RSC refs and HTML paywall delimiters.
- Collapses runs of 3+ newlines.
"""
import json
import re
from pathlib import Path

SRC = Path("/tmp/h2h/notion_chunks")
DST = Path("/tmp/h2h/mikoxyr_push")
DST.mkdir(exist_ok=True)

NEW_DATA_SOURCE_ID = "2ea55f8d-1963-409f-b82b-1ee37432be40"

ICON_FIXES = {
    "\u21A9\uFE0F": "\U0001F519",
    "\u21CC": "\U0001F3AF",
    "\U0001F310": "\U0001F50C",
    "\U0001F5A7\uFE0F": "\U0001F50C",
    "\U0001F5A7": "\U0001F50C",
    "\u269B\uFE0F": "\U0001F9EC",
    "\U0001F30A": "\U0001F4CA",
}
DEFAULT_PAGE_ICON = "\U0001F4DD"


def sanitize_icon(icon):
    if not icon:
        return None
    if icon in ICON_FIXES:
        return ICON_FIXES[icon]
    stripped = icon.replace("\uFE0F", "").strip()
    if not stripped:
        return DEFAULT_PAGE_ICON
    return icon


def clean_content(md: str) -> str:
    md = re.sub(r"\*\*TL;DR\*\*\s*\n\s*\$\d+", "**TL;DR**\n\n_See Problem section below._", md)
    md = md.replace("<!-- ###PREMIUM_CONTENT_DELIMITER### -->", "")
    for bad, good in ICON_FIXES.items():
        md = md.replace(f'icon="{bad}"', f'icon="{good}"')
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def fix_props(props: dict) -> dict:
    out = {}
    for k, v in props.items():
        if k == "Stage" and isinstance(v, str) and v.startswith("["):
            try:
                arr = json.loads(v)
                v = arr[0] if arr else None
            except Exception:
                pass
        out[k] = v
    return out


def slim_page(p: dict) -> dict:
    return {
        "properties": fix_props(p["properties"]),
        "icon": sanitize_icon(p.get("icon")),
        "content": clean_content(p.get("content", "")),
    }


def main():
    total_pages = 0
    for ch in sorted(SRC.glob("chunk_*.json")):
        d = json.loads(ch.read_text())
        out = {
            "parent": {"data_source_id": NEW_DATA_SOURCE_ID},
            "pages": [slim_page(p) for p in d["pages"]],
        }
        target = DST / ch.name
        target.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        total_pages += len(out["pages"])
        print(f"{ch.name}: {len(out['pages']):>2} pages  {target.stat().st_size:>7} bytes")
    print(f"\nTotal: {total_pages} pages across {len(list(DST.glob('chunk_*.json')))} chunks -> {DST}")


if __name__ == "__main__":
    main()
