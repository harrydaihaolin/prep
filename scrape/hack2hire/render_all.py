#!/usr/bin/env python3
"""Render scraped problems to Notion-ready page payloads.

Input:  /tmp/h2h/notion_queue/*.json (one per problem, written by daemon)
Output: /tmp/h2h/notion_pages_full.json (array of page objects)
        /tmp/h2h/notion_chunks/chunk_XX.json (batched into ~6 pages each)

Each page object is suitable for the notion-create-pages MCP tool.
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

QUEUE_DIR = Path("/tmp/h2h/notion_queue")
OUT_PAGES = Path("/tmp/h2h/notion_pages_full.json")
CHUNK_DIR = Path("/tmp/h2h/notion_chunks")
CHUNK_DIR.mkdir(exist_ok=True)

DATA_SOURCE_ID = "379f5460-672e-4d98-ad28-e84c785985cb"

# COMPANY (uppercase enum) -> Notion display name
COMPANY_MAP = {
    "AMAZON": "Amazon", "GOOGLE": "Google", "MICROSOFT": "Microsoft", "UBER": "Uber",
    "META": "Meta", "AIRBNB": "Airbnb", "PINTEREST": "Pinterest", "DOORDASH": "DoorDash",
    "OPENAI": "OpenAI", "SNOWFLAKE": "Snowflake", "COINBASE": "Coinbase", "LINKEDIN": "LinkedIn",
    "SNAPCHAT": "Snapchat", "ROBINHOOD": "Robinhood", "ATLASSIAN": "Atlassian",
    "DATABRICKS": "Databricks", "TIKTOK": "TikTok", "STRIPE": "Stripe", "ROBLOX": "Roblox",
    "ANTHROPIC": "Anthropic", "YELP": "Yelp", "DATADOG": "Datadog", "LYFT": "Lyft",
    "CONFLUENT": "Confluent", "CAPITAL_ONE": "CapitalOne", "ORACLE": "Oracle", "RAMP": "Ramp",
    "BLOOMBERG": "Bloomberg", "REDDIT": "Reddit", "HUBSPOT": "HubSpot", "INSTACART": "Instacart",
    "TESLA": "Tesla", "CITADEL": "Citadel", "RIPPLING": "Rippling", "WAYMO": "Waymo",
    "SQUARE": "Square", "NETFLIX": "Netflix", "AFFIRM": "Affirm", "PERPLEXITY": "Perplexity",
    "FIGMA": "Figma", "XAI": "xAI", "JANE_STREET": "JaneStreet", "SCALEAI": "ScaleAI",
    "TWOSIGMA": "TwoSigma", "SQUAREPOINT": "Squarepoint", "HRT": "HRT", "OPTIVER": "Optiver",
    "APPLE": "Apple", "STACKADAPT": "Stackadapt",
}

# Algorithm tag (API enum) -> Notion display name
TAG_MAP = {
    "ARRAY": "Arrays", "STRING": "Strings", "HASH_TABLE": "Hash Map",
    "GRAPH": "Graph", "BINARY_TREE": "Binary Tree", "LINKED_LIST": "Linked List",
    "DYNAMIC_PROGRAMMING": "Dynamic Programming", "GREEDY": "Greedy",
    "BREADTH_FIRST_SEARCH": "BFS", "DEPTH_FIRST_SEARCH": "DFS",
    "SORTING": "Sorting", "HEAP": "Heap", "TWO_POINTER": "Two Pointers",
    "SLIDING_WINDOW": "Sliding Window", "RECURSION": "Recursion",
    "BACKTRACKING": "Backtracking", "MATH": "Math", "STACK": "Stack",
    "QUEUE": "Queue", "TRIE": "Trie", "UNION_FIND": "Union Find",
    "BINARY_SEARCH": "Binary Search", "BIT_MANIPULATION": "Bit Manipulation",
    "DESIGN": "Design", "SIMULATION": "Simulation", "PREFIX_SUM": "Prefix Sum",
    "MEMOIZATION": "Memoization", "CONCURRENCY": "Concurrency",
    "DIVIDE_AND_CONQUER": "Divide & Conquer", "MATRIX": "Matrix",
    "BINARY_SEARCH_TREE": "BST", "SEGMENT_TREE": "Segment Tree",
}

# Stage (API enum) -> Notion display name
STAGE_MAP = {"OA": "OA", "SCREENING": "Screening", "ONSITE": "Onsite",
             "PHONE_SCREEN": "Phone Screen", "TAKE_HOME": "Take Home"}

DIFFICULTY_MAP = {1: "Easy", 2: "Medium", 3: "Hard", 4: "Hard"}

ICON_BY_TYPE = {"ALGORITHM": "\U0001f4a1", "SD": "\U0001f3db\ufe0f", "ML_SD": "\U0001f916",
                "SQL": "\U0001f5c4\ufe0f", "OOD": "\U0001f9f1"}


def fmt_arg(v: Any) -> str:
    """Format a test-case argument for display."""
    if isinstance(v, str):
        return repr(v)
    if isinstance(v, (list, tuple)):
        return json.dumps(v, ensure_ascii=False, indent=2)
    return json.dumps(v, ensure_ascii=False)


def render_algorithm_or_sql(rec: dict) -> str:
    """Render coding-style problem to markdown (preview + hints + testCases + solution)."""
    c = rec["content"]
    parts: list[str] = []

    # Prefer structured description, but skip unresolved RSC refs like "$15"
    desc = (c.get("description") or "").strip()
    if re.fullmatch(r"\$[0-9a-f]+", desc):
        desc = ""
    preview = desc or (c.get("content_md") or "").strip()
    if preview:
        snippet = re.split(r"\n#{1,3}\s", preview)[0].strip()
        if len(snippet) > 400:
            snippet = snippet[:400].rsplit(" ", 1)[0] + "..."
        parts.append("<callout icon=\"\U0001f3af\" color=\"blue_bg\">")
        parts.append("**TL;DR**")
        parts.append("")
        parts.append(snippet)
        parts.append("</callout>")
        parts.append("")

    # Full problem body
    parts.append("## \U0001f4cb Problem")
    parts.append("")
    parts.append(preview or "_(no preview)_")
    parts.append("")

    # Hints
    hints = c.get("hints") or []
    if hints:
        parts.append("## \U0001f4a1 Hints")
        parts.append("")
        for i, h in enumerate(hints, 1):
            content = h if isinstance(h, str) else (h.get("content") or h.get("text") or json.dumps(h))
            parts.append("<details>")
            parts.append(f"<summary>Hint {i}</summary>")
            parts.append("")
            parts.append(str(content))
            parts.append("")
            parts.append("</details>")
            parts.append("")

    # First 2 test cases (compact)
    tcs = c.get("testCases") or []
    if tcs:
        parts.append("## \U0001f9ea Test Cases")
        parts.append("")
        for i, tc in enumerate(tcs[:2], 1):
            steps = (tc.get("steps") or [])[:2] if isinstance(tc, dict) else []
            if not steps:
                continue
            for step in steps:
                name = step.get("functionName") or step.get("name") or "test"
                args = step.get("args") or step.get("arguments") or []
                expected = step.get("expected") or step.get("expectedOutput")
                parts.append("<details>")
                parts.append(f"<summary>Case {i} \u2014 {name}</summary>")
                parts.append("")
                parts.append("**Input**")
                parts.append("```")
                if args:
                    for j, a in enumerate(args, 1):
                        parts.append(f"arg{j} = {fmt_arg(a)}")
                parts.append("```")
                parts.append("")
                parts.append("**Expected**")
                parts.append("```")
                if expected is not None:
                    parts.append(json.dumps(expected, ensure_ascii=False))
                else:
                    parts.append("null")
                parts.append("```")
                parts.append("</details>")
                parts.append("")
        if len(tcs) > 2:
            parts.append(f"_\u2026{len(tcs) - 2} more cases on the source page._")
            parts.append("")

    # My notes
    parts.append("## \U0001f4dd My Notes")
    parts.append("")
    parts.append("_(Your approach, complexity analysis, mistakes\u2026)_")
    parts.append("")
    parts.append("```python")
    parts.append("# TBD")
    parts.append("```")
    parts.append("")

    # AI insights
    insights = c.get("insights") or {}
    if isinstance(insights, dict) and insights:
        parts.append("## \U0001f50d AI Insights")
        parts.append("")
        wt = insights.get("whatThisTests") or []
        if wt:
            parts.append("**What this tests**")
            for x in wt:
                parts.append(f"- {x}")
            parts.append("")
        cp = insights.get("commonPatterns") or []
        if cp:
            parts.append("**Common patterns** \u2014 " + " \u00b7 ".join(cp))
            parts.append("")
        fu = insights.get("likelyInterviewFollowUps") or []
        if fu:
            parts.append("**Likely follow-ups**")
            for x in fu:
                parts.append(f"- {x}")
            parts.append("")

    parts.append("---")
    parts.append("")
    parts.append(f"**Source:** [Hack2hire \u2014 {rec['title']}]({rec['url']})")
    return "\n".join(parts)


def render_design(rec: dict) -> str:
    """Render an SD/ML_SD problem: callout + raw markdown body."""
    c = rec["content"]
    parts: list[str] = []
    md = (c.get("content_md") or "").strip()

    # Take first paragraph (or heading-section) as TL;DR
    if md:
        first_para = ""
        for line in md.split("\n"):
            if line.strip() and not line.startswith("#"):
                first_para = line.strip()
                break
        if first_para:
            snippet = first_para[:400] + ("..." if len(first_para) > 400 else "")
            parts.append("<callout icon=\"\U0001f3af\" color=\"blue_bg\">")
            parts.append("**TL;DR**")
            parts.append("")
            parts.append(snippet)
            parts.append("</callout>")
            parts.append("")

    # Body
    if md:
        parts.append(md)
    else:
        parts.append("_(No public content available. Visit the source link to view the full problem.)_")

    parts.append("")
    parts.append("## \U0001f4dd My Notes")
    parts.append("")
    parts.append("_(Approach, key tradeoffs, follow-ups\u2026)_")
    parts.append("")
    parts.append("---")
    parts.append("")
    parts.append(f"**Source:** [Hack2hire \u2014 {rec['title']}]({rec['url']})")
    return "\n".join(parts)


def clean_markdown(md: str) -> str:
    """Strip site-specific artifacts."""
    md = md.replace("<!-- ###PREMIUM_CONTENT_DELIMITER### -->", "")
    md = re.sub(r"\n{3,}", "\n\n", md)
    return md.strip()


def truncate_markdown(md: str, max_chars: int = 8000) -> str:
    """Notion blocks max ~2K chars; total page size matters for MCP batch.
    Truncate at the nearest H2 boundary."""
    md = clean_markdown(md)
    if len(md) <= max_chars:
        return md
    cut = md.rfind("\n## ", 0, max_chars)
    if cut < 0:
        cut = max_chars
    return md[:cut] + "\n\n_\u2026Truncated. Full version on the source page._"


def build_properties(rec: dict) -> dict:
    qtype = rec["type"]
    diff = DIFFICULTY_MAP.get(rec.get("difficulty"), "Medium")
    tags = [TAG_MAP.get(t) for t in (rec.get("algorithmTags") or []) if TAG_MAP.get(t)]
    stages = [STAGE_MAP.get(s) for s in (rec.get("stages") or []) if STAGE_MAP.get(s)]
    companies = [COMPANY_MAP.get(c) for c in (rec.get("companies") or []) if COMPANY_MAP.get(c)]

    props: dict = {
        "Question": rec["title"],
        "Source URL": rec["url"],
        "Status": "Not Started",
        "Difficulty": diff,
        "Type": qtype,
        "Companies": json.dumps(sorted(set(companies))),
        "Stage": json.dumps(stages),
    }
    if tags:
        props["Tags"] = json.dumps(sorted(set(tags)))

    ar = rec["content"].get("acceptRate")
    if isinstance(ar, (int, float)) and 0 < ar <= 1:
        props["Acceptance Rate"] = round(ar, 4)

    lr = rec.get("lastReportSeen")
    if lr:
        date = lr[:10]
        props["date:Last Reported:start"] = date
        props["date:Last Reported:is_datetime"] = 0

    return props


def pick_icon(rec: dict) -> str:
    tags = rec.get("algorithmTags") or []
    # type-specific override for non-coding
    if rec["type"] in ("SD", "ML_SD"):
        return ICON_BY_TYPE[rec["type"]]
    if rec["type"] == "SQL":
        return ICON_BY_TYPE["SQL"]
    # ALGORITHM: tag-based
    tag_icons = {
        "ARRAY": "\U0001f522", "STRING": "\U0001f520", "HASH_TABLE": "\U0001f5dd\ufe0f",
        "GRAPH": "\U0001f578\ufe0f", "BINARY_TREE": "\U0001f333", "LINKED_LIST": "\U0001f517",
        "DYNAMIC_PROGRAMMING": "\U0001f9e9", "GREEDY": "\U0001f4b0",
        "BREADTH_FIRST_SEARCH": "\U0001f30a", "DEPTH_FIRST_SEARCH": "\U0001f50a",
        "HEAP": "\U0001f3c6", "SORTING": "\U0001f4ca", "TWO_POINTER": "\U0001f3af",
        "SLIDING_WINDOW": "\U0001fa9f", "BINARY_SEARCH": "\U0001f50d",
        "DESIGN": "\U0001f3d7\ufe0f", "TRIE": "\U0001f333", "UNION_FIND": "\U0001f517",
        "RECURSION": "\U0001f504", "BACKTRACKING": "\U0001f519",
        "SIMULATION": "\U0001f3ae", "QUEUE": "\U0001f4ec", "STACK": "\U0001f4da",
    }
    for t in tags:
        if t in tag_icons:
            return tag_icons[t]
    return "\U0001f4a1"


def build_page(rec: dict) -> dict:
    if rec["type"] in ("SD", "ML_SD"):
        body = render_design(rec)
    else:  # ALGORITHM, SQL, OOD
        body = render_algorithm_or_sql(rec)
    body = truncate_markdown(body)
    return {
        "properties": build_properties(rec),
        "icon": pick_icon(rec),
        "content": body,
    }


def main():
    files = sorted(QUEUE_DIR.glob("*.json"))
    print(f"Reading {len(files)} scraped files...")

    pages = []
    for f in files:
        rec = json.load(f.open())
        try:
            pages.append(build_page(rec))
        except Exception as e:
            print(f"  FAIL render {f.name}: {e}")

    OUT_PAGES.write_text(json.dumps(pages, indent=2))
    print(f"Wrote {len(pages)} pages to {OUT_PAGES}")

    # Dynamic chunking: aim for ~25K content bytes per batch (Notion MCP friendly)
    TARGET_BYTES = 25000
    chunk_idx = 0
    cur, cur_bytes = [], 0
    nchunks = 0
    for p in pages:
        size = len(p["content"]) + sum(len(str(v)) for v in p["properties"].values())
        if cur and (cur_bytes + size > TARGET_BYTES or len(cur) >= 6):
            (CHUNK_DIR / f"chunk_{chunk_idx:03d}.json").write_text(json.dumps({
                "parent": {"data_source_id": DATA_SOURCE_ID}, "pages": cur,
            }, ensure_ascii=False))
            chunk_idx += 1
            nchunks += 1
            cur, cur_bytes = [], 0
        cur.append(p)
        cur_bytes += size
    if cur:
        (CHUNK_DIR / f"chunk_{chunk_idx:03d}.json").write_text(json.dumps({
            "parent": {"data_source_id": DATA_SOURCE_ID}, "pages": cur,
        }, ensure_ascii=False))
        nchunks += 1
    print(f"Wrote {nchunks} chunks into {CHUNK_DIR}/ (target ~{TARGET_BYTES}B each)")


if __name__ == "__main__":
    main()
