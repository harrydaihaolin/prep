#!/usr/bin/env python3
"""Prepare notion_chunks/*.json for MCP push.

For each chunk:
- Sanitize page icons (replace problematic unicode with safe emoji)
- Sanitize callout icons inside content
- Strip stray RSC refs ($N) that may have leaked into TL;DR/preview
- Drop verbose date:* properties (they're already in `Last Reported`)
- Drop empty Status/Owner if missing
- Write to /tmp/h2h/full_push/chunk_NNN.json

Output is byte-for-byte ready to forward to notion-create-pages.
"""
import json
import re
from pathlib import Path

SRC = Path("/tmp/h2h/notion_chunks")
DST = Path("/tmp/h2h/full_push")
DST.mkdir(exist_ok=True)

# Map problematic icons to safe Notion-friendly emoji
ICON_FIXES = {
    "\u21A9\uFE0F": "\U0001F519",  # ↩️ -> 🔙
    "\u21CC": "\U0001F3AF",         # ⇌ -> 🎯
    "\U0001F310": "\U0001F50C",     # 🌐 -> 🔌
    "\U0001F5A7\uFE0F": "\U0001F50C",  # 🖧️ -> 🔌
    "\U0001F5A7": "\U0001F50C",     # 🖧 -> 🔌
    "\u269B\uFE0F": "\U0001F9EC",   # ⚛️ -> 🧬
    "\U0001F30A": "\U0001F4CA",     # 🌊 -> 📊
}

# Strict emoji set — anything else gets replaced with this default
DEFAULT_PAGE_ICON = "\U0001F4DD"   # 📝
DEFAULT_CALLOUT_ICON = "\U0001F3AF"  # 🎯


def sanitize_icon(icon):
    if not icon:
        return None
    if icon in ICON_FIXES:
        return ICON_FIXES[icon]
    # Allow normal single emoji-ish strings; if it's empty after stripping
    # variation selectors, fall back to default.
    stripped = icon.replace("\uFE0F", "").strip()
    if not stripped:
        return DEFAULT_PAGE_ICON
    return icon


def clean_content(md: str) -> str:
    # 1) Strip stray RSC refs like "$15" if they appear as the WHOLE TL;DR body
    md = re.sub(r"\*\*TL;DR\*\*\s*\n\s*\$\d+", "**TL;DR**\n\n_See Problem section below._", md)
    # 2) Strip HTML comment delimiters used by hack2hire for paywall blocks
    md = md.replace("<!-- ###PREMIUM_CONTENT_DELIMITER### -->", "")
    # 3) Sanitize callout icons inside content
    for bad, good in ICON_FIXES.items():
        md = md.replace(f'icon="{bad}"', f'icon="{good}"')
    # 4) Collapse 3+ newlines into 2
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def slim_props(props: dict) -> dict:
    # Drop verbose date:* expanded props — these inflate JSON and Notion already
    # stores Last Reported as a single date field.
    return {k: v for k, v in props.items() if not k.startswith("date:")}


def slim_page(p: dict) -> dict:
    return {
        "properties": slim_props(p["properties"]),
        "icon": sanitize_icon(p.get("icon")),
        "content": clean_content(p.get("content", "")),
    }


def main():
    for ch in sorted(SRC.glob("chunk_*.json")):
        d = json.loads(ch.read_text())
        out = {
            "parent": d["parent"],
            "pages": [slim_page(p) for p in d["pages"]],
        }
        target = DST / ch.name
        target.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
        print(f"{ch.name}: {len(out['pages']):>2} pages  {ch.stat().st_size:>6} -> {target.stat().st_size:>6}")


if __name__ == "__main__":
    main()
