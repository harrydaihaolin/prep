# AGENTS.md — Coding Interview Question Scraper Contract

You are a coding agent helping a human scrape coding-interview problems from a website and emit them as **JSON chunk files** that another person will bulk-upload to a shared Notion database.

You are **not** pushing to Notion. You only produce files on disk. The receiver runs the upload script with their own credentials.

This file is the contract. If your output deviates, the upload script will reject the chunk or render garbage in Notion. Read it end-to-end before you write any code.

## Deliverable

A directory of JSON chunk files, each named `chunk_NNN.json` (zero-padded 3-digit), placed under:

```
<your-scrape-root>/algo_push/
  chunk_000.json
  chunk_001.json
  ...
```

Then zip the entire `algo_push/` folder and send it back.

## Chunk file schema

Every file is one JSON object with exactly two top-level keys:

```json
{
  "parent": { "data_source_id": "REPLACED_BY_RECEIVER" },
  "pages": [ /* 10–25 page objects */ ]
}
```

- `parent.data_source_id` is a placeholder. The receiver overrides it with their own Notion data source ID before upload. Leave the literal string `"REPLACED_BY_RECEIVER"` (or any UUID — it gets stripped).
- `pages` is an array of page objects (see below).
- Target **70–85 KB serialized size per chunk** and **max 25 pages per chunk**. The Notion API and the receiver's tooling choke on larger chunks.

## Page object schema

```json
{
  "properties": { /* see Properties table below */ },
  "icon": "🎯",
  "content": "<markdown string, see Content conventions below>"
}
```

### Properties table

| Property | Type | Required | Format | Allowed values |
|---|---|---|---|---|
| `Question` | string | ✅ | Problem title, plain text, no markdown | — |
| `Source URL` | string | ✅ | Canonical URL of the problem on the source site | — |
| `Status` | string | ✅ | Single SELECT | `Not Started` (always use this for new imports) |
| `Difficulty` | string | ✅ | Single SELECT | `Easy` \| `Medium` \| `Hard` |
| `Type` | string | ✅ | Single SELECT | `ALGORITHM` \| `SQL` \| `SD` \| `ML_SD` \| `OOD` |
| `Companies` | string | ✅ | **JSON-encoded array of strings** | e.g. `"[\"Google\", \"Amazon\"]"` — note the escaped quotes, this is a STRING, not a real array |
| `Stage` | string | ✅ | Single SELECT | `OA` \| `Screening` \| `Onsite` \| `Phone` \| `Final` |
| `Tags` | string | ✅ | **JSON-encoded array of strings** | e.g. `"[\"Hash Map\", \"Prefix Sum\"]"` — see tag vocabulary below |
| `Acceptance Rate` | number | ⛔ optional | JavaScript number, fractional (0.0–1.0) | omit if unknown; do not write `null` or `0` as a placeholder |
| `date:Last Reported:start` | string | ⛔ optional | ISO date `YYYY-MM-DD` | omit if unknown |
| `date:Last Reported:is_datetime` | number | with `start` | `0` (date only) or `1` (datetime) | always `0` for our use case |

#### Tag vocabulary (use these names verbatim when applicable; new tags will auto-create but increase clutter)

`Arrays`, `BFS`, `BST`, `Backtracking`, `Binary Search`, `Binary Tree`, `Bit Manipulation`, `Concurrency`, `DFS`, `Design`, `Divide & Conquer`, `Dynamic Programming`, `Graph`, `Greedy`, `Hash Map`, `Heap`, `Linked List`, `Math`, `Matrix`, `Memoization`, `Prefix Sum`, `Queue`, `Recursion`, `Segment Tree`, `Simulation`, `Sliding Window`, `Sorting`, `Stack`, `Strings`, `Trie`, `Two Pointers`, `Union Find`

#### Company vocabulary (extend freely with the actual scraped name)

Existing known options: `Affirm`, `Airbnb`, `Amazon`, `Anthropic`, `Atlassian`, `Bloomberg`, `CapitalOne`, `Citadel`, `Coinbase`, `Confluent`, `Databricks`, `Datadog`, `DoorDash`, `Figma`, `Google`, `HRT`, `HubSpot`, `Instacart`, `JaneStreet`, `LinkedIn`, `Lyft`, `Meta`, `Microsoft`, `Netflix`, `OpenAI`, `Optiver`, `Oracle`, `Perplexity`, `Pinterest`, `Ramp`, `Reddit`, `Rippling`, `Robinhood`, `Roblox`, `ScaleAI`, `Snapchat`, `Snowflake`, `Square`, `Squarepoint`, `Stripe`, `Tesla`, `TikTok`, `TwoSigma`, `Uber`, `Waymo`, `Yelp`, `xAI`. Use these spellings when the name matches; otherwise add the new company verbatim (PascalCase, no spaces, e.g. `JaneStreet`, not `Jane Street`).

### Icon rules

`icon` is a single emoji character placed at the top of the Notion page. Pick by topic:

| Type / topic | Icon |
|---|---|
| Algorithm — Hash Map / dict | 🗝️ |
| Algorithm — Sliding Window / Two Pointers | 🪟 |
| Algorithm — Greedy / Heap / Sorting | 🏆 |
| Algorithm — DP / Recursion / Memo | 🧩 |
| Algorithm — Graph / DFS / BFS | 🔊 |
| Algorithm — Tree / BST | 🌳 |
| Algorithm — Strings | 🔠 |
| Algorithm — Math / Bit | 🔢 |
| Algorithm — generic | 💡 |
| SQL | 🗄️ |
| System Design | 🏛️ |
| ML System Design | 🤖 |
| OOD | 🧱 |

#### ❌ Never use these icons (Notion rendering bugs):

`🌐` (globe), `🖧` (network), `🌊` (wave), `⇌` (equilibrium arrow), `⚛️` (atom), `↩️` (return arrow).

If the topic suggests one of those, substitute: `🌐` → `🔌`, `🌊` → `📊`, `⇌` → `🎯`, `⚛️` → `🧬`, `↩️` → `🔙`.

## Content conventions (Notion-flavored markdown)

`content` is a single Notion-flavored markdown string. **Structure each page exactly like this** (omit sections that have no source data — never fabricate hints/tests):

```markdown
<callout icon="🎯" color="blue_bg">
**TL;DR**

<first paragraph of the actual problem, verbatim from source, trimmed to ~400 chars at a word boundary>
</callout>

## 📋 Problem

<full problem statement from source, verbatim — including constraints and examples>

## 💡 Hints

<details>
<summary>Hint 1</summary>

<verbatim hint text from source>

</details>

<details>
<summary>Hint 2</summary>

...

</details>

## 🧪 Test Cases

<details>
<summary>Case 1 — <function name or "test"></summary>

**Input**
```
<input verbatim from source>
```

**Expected**
```
<expected output verbatim>
```
</details>

_…N more cases on the source page._  (only if you truncated)

## 📝 My Notes

_(Approach, key tradeoffs, follow-ups…)_

```python
# TBD
```

## 🔍 AI Insights

**What this tests**
- <bullet>
- <bullet>

**Common patterns** — <pattern · pattern · pattern>

**Likely follow-ups**
- <q>
- <q>

---

**Source:** [<source site name> — <Problem title>](<source URL>)
```

### TL;DR rules — read this twice

The TL;DR is the **leading paragraph of the actual problem**, not a summary you wrote. Trim it to ~400 chars at a word boundary so it fits a callout, then ellipsis. Do **not** paraphrase, do **not** "summarize the key idea." A bad TL;DR was the #1 source of complaints in the original session.

If the problem opens with a story setup (e.g. "Consider a bank with…"), use that opening paragraph as the TL;DR. **The reader should be able to start solving from the TL;DR alone if they don't expand the page.**

### Hard MUST-NOTs

- ❌ Do **not** paraphrase, rewrite, or "improve" the problem statement. Copy it verbatim.
- ❌ Do **not** invent hints, test cases, or examples that aren't in the source.
- ❌ Do **not** include `<!-- ... -->` HTML comments in `content` — strip them.
- ❌ Do **not** include unresolved framework references like `$15`, `$L1f`, or `&lt;ref&gt;`. If you see them in the scrape, the structured parse failed — go back and fix the scraper, don't paper over with placeholders.
- ❌ Do **not** include base64-encoded inline images. Use the source URL only.
- ❌ Do **not** include AI-generated solution code. The `## 📝 My Notes` section stays a stub `# TBD` so the human writes their own.
- ❌ Do **not** embed SVG diagrams in `content` — they don't render in Notion via the API, and they bloat the chunk. If the problem has a diagram, link to it as a normal markdown image `![alt](url)` and trust the reader to click through.

### Soft preferences

- ✅ Preserve source-side LaTeX (`$$...$$`) verbatim — Notion's API renders it.
- ✅ Preserve source-side tables in GFM (pipe-table) form — Notion's API renders them.
- ✅ Keep code blocks with their original language tag (e.g. ` ```python `).
- ✅ The `🔍 AI Insights` section may be your own writing — 2-4 bullets per subsection, focused on patterns/follow-ups. Keep it short.

## Type-specific notes

- **`ALGORITHM`** — the bread and butter. Should always render cleanly.
- **`SQL`** — same template, but `## 📋 Problem` typically includes a schema block. Keep it.
- **`SD`** (System Design) — long-form, often has diagrams. Diagrams won't render. The receiver may strip these post-handoff; do your best but don't agonize. Cap `content` at ~6000 chars; if longer, end with `_…Truncated. Full version on the source page._` and the source link.
- **`ML_SD`** — like SD but with ML-specific structure (data, modeling, eval, serving). Same length cap.
- **`OOD`** (Object-Oriented Design) — UML-style diagrams often. Same cap as SD.

## Validation gate

Before zipping, run `python3 scripts/validate_chunks.py <your-scrape-root>/algo_push/` from this folder. It checks every chunk file for schema correctness, banned icons, unresolved refs, and content size. **Do not ship a zip until the validator prints `OK: all <N> chunks valid`.** If it complains, fix the underlying scraper or renderer — don't hand-patch the JSON.

## Reference materials

- `examples/example_chunk.json` — a real, working 2-page chunk. Mirror its shape exactly.
- `scripts/validate_chunks.py` — run this locally before zipping.
- `scripts/upload_to_notion.py` — for the receiver's reference; you don't run it.

## Workflow summary

1. Scrape from the assigned source site, parsing structured fields where possible.
2. Render each problem into the page object schema above.
3. Batch pages into 70–85 KB chunks under `<root>/algo_push/chunk_NNN.json`.
4. Run `validate_chunks.py` and fix anything it flags.
5. `zip -r algo_push.zip algo_push/` and send back.

If anything is ambiguous in the source data (e.g. unclear difficulty, no acceptance rate), **omit the property** rather than guess. Notion handles missing optional properties cleanly; bad guesses are harder to fix at upload time.
