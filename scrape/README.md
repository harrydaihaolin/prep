# scrape/ — per-source scrapers

Each subdirectory is a standalone scraper for one source site. They all
emit JSON chunks that match the contract in [`../AGENTS.md`](../AGENTS.md)
and can be validated with [`../scripts/validate_chunks.py`](../scripts/validate_chunks.py).

| Source | Auth | Output | README |
|---|---|---|---|
| [hack2hire/](./hack2hire/) | `ALGRO_TOKEN` from logged-in browser session | 564 pages (ALGORITHM + SD + ML_SD + SQL) | [hack2hire/README.md](./hack2hire/README.md) |
| [1point3acres/](./1point3acres/) | Full `Cookie:` header from logged-in session | Discuz forum threads from 面经 board | [1point3acres/README.md](./1point3acres/README.md) |

## How a scraper is shaped

Every scraper in this folder follows the same three-stage pipeline:

```
scrape.py    →  raw/<id>.json      (one file per source post; resumable)
render.py    →  algo_push/chunk_NNN.json  (Notion contract format)
validate     →  pass/fail report   (../scripts/validate_chunks.py)
```

The first stage is source-specific (parsing the site's API or HTML). The
second stage is shared: it classifies type/company/stage/tags, strips
markup to clean markdown, and batches into ~80 KB chunks. The third
stage is a hard gate before zipping.

## Adding a new scraper

1. Create `scrape/<source>/` with `scrape.py`, `render.py`, `README.md`.
2. Read raw posts into `raw/`, one JSON file per item, so the run is
   resumable.
3. In `render.py`, reuse the classification helpers from
   `1point3acres/render.py` (`detect_companies`, `pick_icon`, etc.) as a
   starting point; tweak for the source's metadata shape.
4. Write to `algo_push/chunk_NNN.json` with `parent.data_source_id`
   set to the placeholder `"REPLACED_BY_RECEIVER"` — the upload script
   overrides it.
5. Ensure `python3 ../../scripts/validate_chunks.py algo_push/` is green
   before zipping.

That's the contract. Don't push to Notion from inside a scraper — that's
the receiver's job via `scripts/upload_to_notion.py`.
