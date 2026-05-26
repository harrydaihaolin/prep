#!/usr/bin/env python3
"""Render 1point3acres thread JSONs into Notion-payload chunks.

Reads `raw/thread_*.json` produced by `scrape.py`, classifies each thread
(company / type / stage / difficulty), strips Discuz HTML to clean
markdown, and emits `algo_push/chunk_NNN.json` matching `prep/AGENTS.md`.

Heuristics:
  - Company → extracted from title prefix `[Amazon]` / `【Google】` or keyword scan
  - Type → ALGORITHM unless title contains "system design" / "sd" / "设计"
  - Difficulty → not generally known on 1point3acres → omitted
  - Stage → OA / Onsite / Phone / Final extracted from title keywords
  - Tags → extracted from title keywords (sliding window, dp, graph, …)

The output passes `prep/scripts/validate_chunks.py` cleanly.
"""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
from pathlib import Path

RAW_DIR = Path(__file__).parent / "raw"
CHUNK_DIR = Path(__file__).parent / "algo_push"
CHUNK_DIR.mkdir(exist_ok=True)

# --- Classification vocab (canonical names from prep/AGENTS.md) -------------

KNOWN_COMPANIES = [
    "Affirm", "Airbnb", "Amazon", "Anthropic", "Atlassian", "Bloomberg",
    "CapitalOne", "Citadel", "Coinbase", "Confluent", "Databricks", "Datadog",
    "DoorDash", "Figma", "Google", "HRT", "HubSpot", "Instacart", "JaneStreet",
    "LinkedIn", "Lyft", "Meta", "Microsoft", "Netflix", "OpenAI", "Optiver",
    "Oracle", "Perplexity", "Pinterest", "Ramp", "Reddit", "Rippling",
    "Robinhood", "Roblox", "ScaleAI", "Snapchat", "Snowflake", "Square",
    "Squarepoint", "Stripe", "Tesla", "TikTok", "TwoSigma", "Uber", "Waymo",
    "Yelp", "xAI",
]
# Common alias / Chinese variants seen on 1point3acres
COMPANY_ALIASES = {
    "facebook": "Meta", "fb": "Meta", "meta": "Meta",
    "亚马逊": "Amazon", "amzn": "Amazon", "amazon": "Amazon",
    "google": "Google", "谷歌": "Google", "goog": "Google",
    "微软": "Microsoft", "ms": "Microsoft", "msft": "Microsoft", "microsoft": "Microsoft",
    "字节": "TikTok", "tiktok": "TikTok", "bytedance": "TikTok", "tk": "TikTok",
    "苹果": "Apple",  # not in vocab; will pass through as new company
    "甲骨文": "Oracle", "oracle": "Oracle",
    "网飞": "Netflix", "netflix": "Netflix",
    "stripe": "Stripe",
    "uber": "Uber", "优步": "Uber",
    "lyft": "Lyft",
    "airbnb": "Airbnb",
    "snap": "Snapchat", "snapchat": "Snapchat",
    "linkedin": "LinkedIn", "领英": "LinkedIn",
    "doordash": "DoorDash", "dd": "DoorDash",
    "instacart": "Instacart",
    "openai": "OpenAI",
    "anthropic": "Anthropic",
    "databricks": "Databricks",
    "snowflake": "Snowflake",
    "pinterest": "Pinterest",
    "robinhood": "Robinhood", "hood": "Robinhood",
    "coinbase": "Coinbase",
    "bloomberg": "Bloomberg", "bbg": "Bloomberg",
    "atlassian": "Atlassian",
    "yelp": "Yelp",
    "reddit": "Reddit",
    "figma": "Figma",
    "ramp": "Ramp",
    "datadog": "Datadog", "dd0": "Datadog",
    "confluent": "Confluent",
    "rippling": "Rippling",
    "tesla": "Tesla",
    "waymo": "Waymo",
    "scaleai": "ScaleAI", "scale ai": "ScaleAI",
    "hubspot": "HubSpot",
    "perplexity": "Perplexity",
    "xai": "xAI", "x.ai": "xAI", "grok": "xAI",
    "roblox": "Roblox",
}

KNOWN_TAGS = {
    "arrays", "bfs", "bst", "backtracking", "binary search", "binary tree",
    "bit manipulation", "concurrency", "dfs", "design", "divide & conquer",
    "dynamic programming", "graph", "greedy", "hash map", "heap", "linked list",
    "math", "matrix", "memoization", "prefix sum", "queue", "recursion",
    "segment tree", "simulation", "sliding window", "sorting", "stack",
    "strings", "trie", "two pointers", "union find",
}
TAG_HINTS = {  # keyword → canonical tag
    "动态规划": "Dynamic Programming", "dp": "Dynamic Programming",
    "二分": "Binary Search", "binary search": "Binary Search",
    "滑动窗口": "Sliding Window", "sliding": "Sliding Window",
    "双指针": "Two Pointers",
    "图": "Graph", "graph": "Graph",
    "树": "Binary Tree", "tree": "Binary Tree",
    "递归": "Recursion", "recursion": "Recursion",
    "回溯": "Backtracking", "backtracking": "Backtracking",
    "贪心": "Greedy", "greedy": "Greedy",
    "堆": "Heap", "heap": "Heap",
    "栈": "Stack", "stack": "Stack",
    "队列": "Queue", "queue": "Queue",
    "字符串": "Strings", "string": "Strings",
    "矩阵": "Matrix", "matrix": "Matrix",
    "字典树": "Trie", "trie": "Trie",
    "并查集": "Union Find", "union find": "Union Find",
    "哈希": "Hash Map", "hash": "Hash Map",
    "前缀和": "Prefix Sum", "prefix sum": "Prefix Sum",
}

STAGE_HINTS = [
    ("oa", "OA"), ("online assessment", "OA"), ("笔试", "OA"),
    ("onsite", "Onsite"), ("on-site", "Onsite"), ("现场", "Onsite"),
    ("phone", "Phone"), ("phone screen", "Phone"), ("电面", "Phone"),
    ("final", "Final"), ("终面", "Final"),
    ("screen", "Screening"), ("筛选", "Screening"),
]

# --- HTML → markdown -------------------------------------------------------

DISCUZ_NOISE = [
    # ".attach_nopermission_notice" etc. = "you need to log in to view"
    re.compile(r'<div[^>]*class="[^"]*attach_nopermission_notice[^"]*"[^>]*>.*?</div>', re.DOTALL),
    re.compile(r'<div[^>]*id="attach_[^"]*"[^>]*>.*?</div>', re.DOTALL),
    re.compile(r'<script[^>]*>.*?</script>', re.DOTALL),
    re.compile(r'<style[^>]*>.*?</style>', re.DOTALL),
    re.compile(r'<!--.*?-->', re.DOTALL),
    # Discuz signature / "本帖最后由..."
    re.compile(r'<div[^>]*class="[^"]*tipi_click[^"]*"[^>]*>.*?</div>', re.DOTALL),
    re.compile(r'本帖最后由[^\n<]*?编辑\s*'),
    # "(?需登?录回?复)" / "已隐藏" inline notices
    re.compile(r'.\s*需\s*登录\s*[^<\n]*', re.IGNORECASE),
]

TAG_REWRITE = [
    (re.compile(r'<br\s*/?>'), "\n"),
    (re.compile(r'</p>'), "\n\n"),
    (re.compile(r'<p[^>]*>'), ""),
    (re.compile(r'</?(?:strong|b)>'), "**"),
    (re.compile(r'</?(?:em|i)>'), "*"),
    (re.compile(r'<h([1-6])[^>]*>'), lambda m: "\n" + "#" * int(m.group(1)) + " "),
    (re.compile(r'</h[1-6]>'), "\n\n"),
    (re.compile(r'<li[^>]*>'), "- "),
    (re.compile(r'</li>'), "\n"),
    (re.compile(r'</?ul[^>]*>'), "\n"),
    (re.compile(r'</?ol[^>]*>'), "\n"),
    (re.compile(r'<a [^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL),
     lambda m: f"[{re.sub('<[^>]+>', '', m.group(2))}]({m.group(1)})"),
    (re.compile(r'<img[^>]*src="([^"]+)"[^>]*/?>'),
     lambda m: f"![image]({m.group(1)})"),
    # blockquote / quote
    (re.compile(r'<blockquote[^>]*>'), "> "),
    (re.compile(r'</blockquote>'), "\n\n"),
    # code blocks (Discuz uses [code] BBCode rendered as <table class="code">)
    (re.compile(r'<pre[^>]*>'), "\n```\n"),
    (re.compile(r'</pre>'), "\n```\n"),
    (re.compile(r'<code[^>]*>'), "`"),
    (re.compile(r'</code>'), "`"),
]


def html_to_md(s: str) -> str:
    for pat in DISCUZ_NOISE:
        s = pat.sub("", s)
    for pat, repl in TAG_REWRITE:
        s = pat.sub(repl, s)
    # Strip residual tags
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    s = re.sub(r"\n{3,}", "\n\n", s)
    return s.strip()


# --- Classification ---------------------------------------------------------

def detect_companies(title: str, body: str) -> list[str]:
    text = f" {title} {body[:1500]} ".lower()
    hits: list[str] = []

    # bracketed prefix often holds the company: [Amazon], 【Google】, （Stripe）
    for m in re.finditer(r"[\[【（(]\s*([A-Za-z\u4e00-\u9fff. ]{2,30})\s*[\]】）)]", title):
        cand = m.group(1).strip().lower()
        canon = COMPANY_ALIASES.get(cand)
        if canon and canon not in hits:
            hits.append(canon)

    for alias, canon in COMPANY_ALIASES.items():
        # require word boundary for ASCII aliases to avoid false hits
        if re.search(r"[a-z]", alias):
            pat = re.compile(rf"\b{re.escape(alias)}\b")
            if pat.search(text) and canon not in hits:
                hits.append(canon)
        else:
            if alias in text and canon not in hits:
                hits.append(canon)
    return hits[:5]  # cap to avoid noise


def detect_type(title: str, body: str) -> str:
    text = f"{title}\n{body[:800]}".lower()
    if "system design" in text or "系统设计" in text or "sys design" in text:
        return "SD"
    if "ml" in text and ("design" in text or "system" in text):
        return "ML_SD"
    if "sql" in text or "leetcode sql" in text:
        return "SQL"
    if "ood" in text or "object-oriented design" in text:
        return "OOD"
    return "ALGORITHM"


def detect_stage(title: str) -> str:
    t = title.lower()
    for hint, stage in STAGE_HINTS:
        if hint in t:
            return stage
    return "Onsite"  # safe default for 面经 board


def detect_tags(title: str, body: str) -> list[str]:
    text = f"{title}\n{body[:2000]}".lower()
    hits: list[str] = []
    for hint, canon in TAG_HINTS.items():
        if hint in text and canon not in hits:
            hits.append(canon)
    return hits[:6]


# --- Icon picker (matches prep/AGENTS.md table) ----------------------------

def pick_icon(typ: str, tags: list[str]) -> str:
    if typ == "SD":
        return "🏛️"
    if typ == "ML_SD":
        return "🤖"
    if typ == "SQL":
        return "🗄️"
    if typ == "OOD":
        return "🧱"
    tagset = {t.lower() for t in tags}
    if {"hash map"} & tagset:
        return "🗝️"
    if {"sliding window", "two pointers"} & tagset:
        return "🪟"
    if {"greedy", "heap", "sorting"} & tagset:
        return "🏆"
    if {"dynamic programming", "recursion", "memoization"} & tagset:
        return "🧩"
    if {"graph", "dfs", "bfs"} & tagset:
        return "🔊"
    if {"binary tree", "bst"} & tagset:
        return "🌳"
    if "strings" in tagset:
        return "🔠"
    if {"math", "bit manipulation"} & tagset:
        return "🔢"
    return "💡"


# --- Rendering -------------------------------------------------------------

def trim_tldr(body_md: str, max_chars: int = 400) -> str:
    para = body_md.split("\n\n", 1)[0].strip()
    if len(para) <= max_chars:
        return para
    cut = para[:max_chars].rsplit(" ", 1)[0]
    return cut + "…"


def render_page(thread: dict) -> dict | None:
    title = thread.get("title", "").strip()
    body_html = thread.get("op_body_html", "")
    if not title or not body_html:
        return None
    body_md = html_to_md(body_html)
    if not body_md.strip():
        return None

    companies = detect_companies(title, body_md)
    typ = detect_type(title, body_md)
    stage = detect_stage(title)
    tags = detect_tags(title, body_md)

    tldr = trim_tldr(body_md)
    icon = pick_icon(typ, tags)

    content_parts = [
        f'<callout icon="🎯" color="blue_bg">',
        "**TL;DR**",
        "",
        tldr,
        "</callout>",
        "",
        "## 📋 Problem",
        "",
        body_md,
        "",
        "## 📝 My Notes",
        "",
        "_(Approach, key tradeoffs, follow-ups…)_",
        "",
        "```python",
        "# TBD",
        "```",
        "",
        "---",
        "",
        f'**Source:** [1point3acres — {title}]({thread["url"]})',
    ]
    content = "\n".join(content_parts)

    props = {
        "Question": title[:200],
        "Source URL": thread["url"],
        "Status": "Not Started",
        "Type": typ,
        "Companies": json.dumps(companies if companies else ["Unknown"], ensure_ascii=False),
        "Stage": stage,
        "Tags": json.dumps(tags, ensure_ascii=False),
    }
    # Difficulty: rarely declared on 1point3acres, omit by default (validator allows it)
    return {
        "properties": props,
        "icon": icon,
        "content": content,
    }


# --- Batching --------------------------------------------------------------

MAX_BYTES = 80_000
MAX_PAGES = 25


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    args = ap.parse_args()

    threads = []
    for f in sorted(RAW_DIR.glob("thread_*.json")):
        try:
            threads.append(json.loads(f.read_text(encoding="utf-8")))
        except Exception as e:
            print(f"  skip {f.name}: {e}")
    print(f"Loaded {len(threads)} threads")

    pages = []
    for t in threads:
        p = render_page(t)
        if p:
            pages.append(p)
    print(f"Rendered {len(pages)} pages (dropped {len(threads) - len(pages)} empty)")

    if args.limit:
        pages = pages[: args.limit]

    for old in CHUNK_DIR.glob("chunk_*.json"):
        old.unlink()

    buf, buf_bytes, idx = [], 0, 0
    for p in pages:
        psize = len(json.dumps(p, ensure_ascii=False))
        if buf and (buf_bytes + psize > MAX_BYTES or len(buf) >= MAX_PAGES):
            out = CHUNK_DIR / f"chunk_{idx:03d}.json"
            out.write_text(json.dumps(
                {"parent": {"data_source_id": "REPLACED_BY_RECEIVER"}, "pages": buf},
                ensure_ascii=False), encoding="utf-8")
            print(f"  {out.name}: {len(buf):>2} pages  {out.stat().st_size:>6} bytes")
            idx += 1
            buf, buf_bytes = [], 0
        buf.append(p)
        buf_bytes += psize
    if buf:
        out = CHUNK_DIR / f"chunk_{idx:03d}.json"
        out.write_text(json.dumps(
            {"parent": {"data_source_id": "REPLACED_BY_RECEIVER"}, "pages": buf},
            ensure_ascii=False), encoding="utf-8")
        print(f"  {out.name}: {len(buf):>2} pages  {out.stat().st_size:>6} bytes")
        idx += 1

    print(f"\nTotal: {idx} chunks, {len(pages)} pages → {CHUNK_DIR}")


if __name__ == "__main__":
    main()
