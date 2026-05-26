# prep — coding interview question scraper kit

A drop-in spec + tooling so your scraping agent (Claude, Cursor, anything that reads `AGENTS.md`) emits JSON chunks that bulk-upload cleanly into our shared Notion database.

You don't push to Notion. You scrape a site, produce a folder of JSON files, and zip it back. I run the upload on my side.

## What's in here

| Path | Purpose |
|---|---|
| `AGENTS.md` | The contract. Your agent reads this. It defines the chunk schema, properties, content conventions, and hard rules. |
| `examples/example_chunk.json` | A real, working chunk with two pages. Mirror its shape exactly. |
| `scripts/validate_chunks.py` | Run this locally before zipping. Must print `OK: all <N> chunks valid` before you ship. |
| `scripts/upload_to_notion.py` | Receiver-side script (for my reference / your debugging). You don't run it. |
| `scrape/hack2hire/` | Reference scraper: hack2hire.com → 564 pages. Pipeline + scripts to mirror. |
| `scrape/1point3acres/` | Reference scraper: 1point3acres.com Discuz forum, cookie-auth pattern. |

## How to use this

1. Open this folder in your AI coding tool (Cursor / Claude Code / etc.) and let it auto-load `AGENTS.md`.
2. Tell the agent which site you want to scrape and what scope (e.g. all coding questions for Companies X, Y, Z).
3. The agent scrapes and writes its output under `algo_push/chunk_NNN.json`.
4. Run:
   ```bash
   python3 scripts/validate_chunks.py algo_push/
   ```
   If it complains, ask the agent to fix the scraper. Do not hand-patch the JSON — fix the upstream renderer instead, since real fixes come from the source data.
5. Once the validator is green:
   ```bash
   zip -r algo_push.zip algo_push/
   ```
   and send the zip back.

## Quality bar

The number-one complaint from the original run was **summarized TL;DRs that lost the actual problem statement**. Read the "TL;DR rules" section in `AGENTS.md` before shipping. The TL;DR is a trimmed copy of the **first paragraph of the real problem**, not a paraphrase. Tell your agent: *"verbatim, not summary."*

Beyond that:
- Full problem statement preserved (constraints, examples, everything).
- Hints and test cases from the source — never invented.
- No HTML comments, no unresolved framework refs (`$15`, `$L1f`), no banned emojis (see AGENTS.md).
- Single-emoji icons only.

## Troubleshooting

- **Validator says `chunk too large`** — your agent batched too many pages or pages with very long bodies. Re-batch with smaller targets.
- **Validator says `unresolved RSC ref`** — your scraper grabbed a rendered HTML fragment instead of resolving the framework references. Fix the parser.
- **Validator says `banned icon`** — your agent picked one of the icons we know Notion renders badly. Apply the substitution table in AGENTS.md.
- **`Companies` / `Tags` rejected** — these must be JSON-encoded STRINGS, not real arrays. Example: `"Companies": "[\"Google\", \"Amazon\"]"`.
