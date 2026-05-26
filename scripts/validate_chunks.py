#!/usr/bin/env python3
"""Validate algo_push/ chunks against the AGENTS.md contract.

Usage:
    python3 scripts/validate_chunks.py path/to/algo_push/

Exits 0 if every chunk passes; otherwise prints every violation grouped by
file and exits 1. Safe to run repeatedly while iterating on the scraper.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path


REQUIRED_PROPS = {"Question", "Source URL", "Status", "Difficulty", "Type",
                  "Companies", "Stage", "Tags"}
ALLOWED_DIFFICULTY = {"Easy", "Medium", "Hard"}
ALLOWED_TYPE = {"ALGORITHM", "SQL", "SD", "ML_SD", "OOD"}
ALLOWED_STAGE = {"OA", "Screening", "Onsite", "Phone", "Final"}
ALLOWED_STATUS = {"Not Started", "In Progress", "Done"}

BANNED_ICONS = {"\U0001F310", "\U0001F5A7", "\U0001F30A",
                "\u21CC", "\u269B\uFE0F", "\u21A9\uFE0F"}
BANNED_ICON_NAMES = {
    "\U0001F310": "globe (🌐)",
    "\U0001F5A7": "network (🖧)",
    "\U0001F30A": "wave (🌊)",
    "\u21CC": "equilibrium arrow (⇌)",
    "\u269B\uFE0F": "atom (⚛️)",
    "\u21A9\uFE0F": "return arrow (↩️)",
}

# Page-level limits.  Empirically derived from data that pushed cleanly: the
# real ceiling appears around 9 KB per page in our shipped 455-page run.
MAX_CHUNK_BYTES = 90_000
MAX_PAGES_PER_CHUNK = 25
MIN_PAGES_PER_CHUNK = 1
MAX_CONTENT_BYTES = 9_000

# RSC refs look like `$L1f`, `$F2a3` — a `$` followed by 1-6 chars that
# include at least one letter. Pure numeric `$N` is almost always money or a
# LaTeX delimiter, so we don't flag it here (use NO_PREVIEW and missing-TL;DR
# checks to catch the cases that actually mattered in production).
# We also strip `$$...$$` (LaTeX math) before scanning.
LATEX_BLOCK = re.compile(r"\$\$.+?\$\$", re.DOTALL)
UNRESOLVED_REF = re.compile(r"(?:^|[^\w$])(\$[0-9A-Za-z]*[A-Za-z][0-9A-Za-z]*)(?=$|[^\w$])")
HTML_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
NO_PREVIEW = re.compile(r"_\(no preview\)_")


def validate_page(page: dict, page_idx: int) -> list[str]:
    errs: list[str] = []
    prefix = f"page[{page_idx}]"

    if not isinstance(page, dict):
        return [f"{prefix} is not a JSON object"]

    # Top-level keys
    extra = set(page.keys()) - {"properties", "icon", "content"}
    if extra:
        errs.append(f"{prefix} has unexpected keys: {sorted(extra)}")

    props = page.get("properties")
    if not isinstance(props, dict):
        errs.append(f"{prefix}.properties missing or not an object")
        return errs

    # Required props
    missing = REQUIRED_PROPS - set(props.keys())
    if missing:
        errs.append(f"{prefix} missing required properties: {sorted(missing)}")

    # Title sanity
    q = props.get("Question")
    if not (isinstance(q, str) and q.strip()):
        errs.append(f"{prefix}.Question must be a non-empty string")
    elif len(q) > 200:
        errs.append(f"{prefix}.Question too long ({len(q)} chars; max 200)")

    # URL sanity
    url = props.get("Source URL")
    if not (isinstance(url, str) and url.startswith(("http://", "https://"))):
        errs.append(f"{prefix}.Source URL missing or not http(s)")

    # Single-select enums
    for k, allowed in [("Status", ALLOWED_STATUS), ("Difficulty", ALLOWED_DIFFICULTY),
                       ("Type", ALLOWED_TYPE), ("Stage", ALLOWED_STAGE)]:
        v = props.get(k)
        if v is None:
            continue  # already flagged above if required
        if v not in allowed:
            errs.append(f"{prefix}.{k} = {v!r} not in {sorted(allowed)}")

    # JSON-array-string multi-selects
    for k in ("Companies", "Tags"):
        v = props.get(k)
        if v is None:
            continue
        if not isinstance(v, str):
            errs.append(f"{prefix}.{k} must be a STRING containing a JSON array, got {type(v).__name__}")
            continue
        try:
            parsed = json.loads(v)
        except json.JSONDecodeError:
            errs.append(f"{prefix}.{k} is not valid JSON: {v[:80]!r}")
            continue
        if not isinstance(parsed, list):
            errs.append(f"{prefix}.{k} JSON is not an array")
        elif k == "Companies" and not parsed:
            errs.append(f"{prefix}.Companies array is empty")

    # Acceptance Rate
    ar = props.get("Acceptance Rate")
    if ar is not None and not (isinstance(ar, (int, float)) and 0 <= ar <= 1):
        errs.append(f"{prefix}.Acceptance Rate = {ar!r} not a number in [0, 1]")

    # Date pair consistency
    if "date:Last Reported:start" in props:
        start = props["date:Last Reported:start"]
        if not (isinstance(start, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", start)):
            errs.append(f"{prefix}.date:Last Reported:start must be YYYY-MM-DD")
        if props.get("date:Last Reported:is_datetime") not in (0, 1):
            errs.append(f"{prefix}.date:Last Reported:is_datetime must be 0 or 1")

    # Icon
    icon = page.get("icon")
    if icon:
        if not isinstance(icon, str):
            errs.append(f"{prefix}.icon must be a string")
        elif icon in BANNED_ICONS or any(b in icon for b in BANNED_ICONS):
            for bad in BANNED_ICONS:
                if bad in icon:
                    errs.append(f"{prefix}.icon uses banned glyph: {BANNED_ICON_NAMES[bad]}")
                    break
        elif len(icon) > 4:
            errs.append(f"{prefix}.icon too long ({len(icon)} chars; single emoji only)")

    # Content
    content = page.get("content", "")
    if not isinstance(content, str) or not content.strip():
        errs.append(f"{prefix}.content missing or empty")
    else:
        cbytes = len(content.encode("utf-8"))
        if cbytes > MAX_CONTENT_BYTES:
            errs.append(f"{prefix}.content too large ({cbytes} bytes; max {MAX_CONTENT_BYTES})")
        if HTML_COMMENT.search(content):
            errs.append(f"{prefix}.content still contains HTML comments — strip them")
        if NO_PREVIEW.search(content):
            errs.append(f"{prefix}.content has placeholder '_(no preview)_' — scraper failed to extract this problem; re-scrape or drop it")
        # Strip LaTeX blocks before scanning for unresolved RSC refs
        scrub = LATEX_BLOCK.sub("", content)
        m = UNRESOLVED_REF.search(scrub)
        if m:
            errs.append(f"{prefix}.content contains unresolved RSC ref {m.group(1)!r}")
        for bad in BANNED_ICONS:
            if f'icon="{bad}"' in content:
                errs.append(f"{prefix}.content callout uses banned icon: {BANNED_ICON_NAMES[bad]}")
        if "**TL;DR**" not in content and "# TL;DR" not in content:
            errs.append(f"{prefix}.content missing TL;DR section")
        if "**Source:**" not in content and "**Source**" not in content:
            errs.append(f"{prefix}.content missing 'Source:' attribution link at bottom")

    return errs


def validate_chunk(path: Path) -> list[str]:
    errs: list[str] = []
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        return [f"{path.name}: invalid JSON — {e}"]

    if not isinstance(data, dict):
        return [f"{path.name}: top-level is not an object"]
    if "parent" not in data or "pages" not in data:
        errs.append(f"{path.name}: missing 'parent' or 'pages' at top level")

    parent = data.get("parent", {})
    if not isinstance(parent, dict) or "data_source_id" not in parent:
        errs.append(f"{path.name}: parent must be {{\"data_source_id\": ...}}")

    pages = data.get("pages", [])
    if not isinstance(pages, list):
        errs.append(f"{path.name}: pages must be an array")
        return errs

    n = len(pages)
    if n < MIN_PAGES_PER_CHUNK:
        errs.append(f"{path.name}: empty chunk ({n} pages)")
    if n > MAX_PAGES_PER_CHUNK:
        errs.append(f"{path.name}: too many pages ({n}; max {MAX_PAGES_PER_CHUNK})")

    fsize = path.stat().st_size
    if fsize > MAX_CHUNK_BYTES:
        errs.append(f"{path.name}: file too large ({fsize} bytes; max {MAX_CHUNK_BYTES} — rebatch into smaller chunks)")

    for i, page in enumerate(pages):
        errs.extend(f"{path.name}: {e}" for e in validate_page(page, i))

    return errs


def main() -> int:
    if len(sys.argv) != 2:
        print("Usage: validate_chunks.py <algo_push_dir_or_chunk.json>")
        return 2
    target = Path(sys.argv[1]).expanduser().resolve()

    if target.is_file():
        chunks = [target]
    elif target.is_dir():
        chunks = sorted(target.glob("chunk_*.json"))
        if not chunks:
            print(f"ERROR: no chunk_*.json files in {target}")
            return 2
    else:
        print(f"ERROR: {target} is not a file or directory")
        return 2

    all_errs: list[str] = []
    total_pages = 0
    seen_urls: dict[str, str] = {}

    for ch in chunks:
        errs = validate_chunk(ch)
        if errs:
            all_errs.extend(errs)
        # Track duplicate Source URLs across chunks
        try:
            data = json.loads(ch.read_text(encoding="utf-8"))
            for p in data.get("pages", []):
                url = (p.get("properties") or {}).get("Source URL")
                if url:
                    if url in seen_urls:
                        all_errs.append(
                            f"{ch.name}: duplicate Source URL {url!r} also in {seen_urls[url]}"
                        )
                    else:
                        seen_urls[url] = ch.name
                    total_pages += 1
        except Exception:
            pass

    if all_errs:
        print(f"FAILED with {len(all_errs)} issue(s) across {len(chunks)} chunks:\n")
        for e in all_errs:
            print(f"  - {e}")
        return 1

    print(f"OK: all {len(chunks)} chunks valid · {total_pages} unique pages.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
