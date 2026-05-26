# Hack2hire scraper (reference implementation)

This is the working scraper that produced the original 564-page dataset
(455 ALGORITHM + 71 SD + 18 ML_SD + 20 SQL) under `prep/AGENTS.md`'s
contract. Treat it as a reference: each script demonstrates one stage
of the pipeline that any new source should also implement.

## Pipeline overview

```
                              ┌─────────────────────────┐
hack2hire.com ──RSC parse──▶  │ scrape_all_daemon.py    │
                              │  /tmp/h2h/notion_queue/ │  raw JSON per problem
                              └────────────┬────────────┘
                                           │
                              ┌────────────▼────────────┐
                              │ render_all.py           │
                              │  /tmp/h2h/notion_chunks/│  Notion page payloads (chunked)
                              └────────────┬────────────┘
                                           │
                              ┌────────────▼────────────┐
                              │ prep_full_push.py       │  icon/content sanitization
                              │  /tmp/h2h/full_push/    │
                              └────────────┬────────────┘
                                           │
                              ┌────────────▼────────────┐
                              │ algo_only_chunks.py     │  filter & re-batch by Type
                              │  /tmp/h2h/algo_push/    │
                              └────────────┬────────────┘
                                           │
                              ┌────────────▼────────────┐
                              │ migrate_to_mikoxyr.py   │  retarget at new data source
                              │  /tmp/h2h/mikoxyr_push/ │  → ready for upload_to_notion.py
                              └─────────────────────────┘
```

## Scripts

| Script | Stage | Inputs | Outputs |
|---|---|---|---|
| `scrape_all_daemon.py` | Scrape | hack2hire.com API + SSR HTML (with `ALGRO_TOKEN`) | Raw per-problem JSON to `/tmp/h2h/notion_queue/` |
| `render_all.py` | Render | Raw scraped JSON | Notion-payload chunks to `/tmp/h2h/notion_chunks/` |
| `prep_full_push.py` | Sanitize | Notion-payload chunks | Cleaned chunks to `/tmp/h2h/full_push/` |
| `algo_only_chunks.py` | Filter | Full-push chunks | ALGORITHM-only re-batched chunks |
| `migrate_to_mikoxyr.py` | Retarget | Any chunks | Same chunks with new `parent.data_source_id` |

## What to reuse for a new source

When building a scraper for a different site, lift these patterns:

1. **Persistent queue on disk** (`notion_queue/*.json`) — one file per problem,
   so a crash mid-run loses at most one item. Resumable by listing the dir.
2. **Render stage produces the contract format** — make the renderer the only
   place that knows about Notion's property and content schema. The scraper
   stays domain-specific.
3. **Re-batching is cheap** — keep raw + intermediate chunks on disk so you
   can re-render with new conventions without re-scraping.
4. **Sanitization is its own step** — icon swaps, RSC-ref stripping, HTML
   comment removal. The validator in `prep/scripts/validate_chunks.py` is
   the spec these sanitizers must satisfy.

## Caveats

- These scripts read/write absolute paths under `/tmp/h2h/` because that's
  where the working set lived during development. For a new run, either
  edit the paths or symlink your scrape root to `/tmp/h2h`.
- `scrape_all_daemon.py` expects an `ALGRO_TOKEN` env var (extracted from
  a logged-in browser session at hack2hire). Without it most endpoints
  return 401.
- The RSC payload parser (`_resolve_ref`) handles Next.js 14+ React Server
  Component payloads. If hack2hire's framework changes, that's the file
  to debug first.
