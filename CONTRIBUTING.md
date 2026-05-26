# Contributing

This is a tooling kit for scraping interview-question content into a
single Notion database. Most contributions land in one of three places:

1. **`AGENTS.md`** — the contract. Change only when the JSON schema, the
   property catalogue, or the icon/content conventions actually change.
   Bumping the contract forces every downstream scraper to re-emit.
2. **`scripts/validate_chunks.py`** — enforcement. Every change in
   `AGENTS.md` needs a matching check here, or the contract is
   advisory-only.
3. **`scrape/<source>/`** — a new source-specific scraper. Follow the
   shape of `scrape/hack2hire/` and `scrape/1point3acres/`.

## Branch / commit conventions

- Branches: `feat/<short-slug>`, `fix/<short-slug>`, `docs/<short-slug>`.
- Commits: imperative mood, one logical change per commit. Reference an
  issue or pillar when you can ("fix: render LaTeX dollar signs without
  tripping the validator").

## Local checks (before pushing)

```bash
# 1. Lint Python (we use ruff if installed, else nothing).
ruff check . 2>/dev/null || true

# 2. Run the validator on the bundled example.
python3 scripts/validate_chunks.py examples/

# 3. If you touched a scraper, run its render step and validate.
python3 scrape/<source>/render.py
python3 scripts/validate_chunks.py scrape/<source>/algo_push/
```

The validator is the gate. A change that makes the validator green on
new content but red on existing chunks needs an explanation in the PR.

## Adding a new scraper

See [`scrape/README.md`](./scrape/README.md). The TL;DR:

- Three files: `scrape.py`, `render.py`, `README.md`.
- Auth via env var, not hard-coded.
- Resumable: cache raw fetches under `scrape/<source>/raw/` (gitignored).
- Final output: `scrape/<source>/algo_push/chunk_NNN.json`, validator green.

## PR review flow

- Open a PR against `main`.
- For contract changes (`AGENTS.md` / `validate_chunks.py`): include a
  before/after example showing how an existing chunk needs to change.
- For new scrapers: include the validator output and a count of pages
  successfully rendered.
- Don't commit `raw/`, `algo_push/`, secrets, or zip files. The
  `.gitignore` covers the usual paths.

## Do-not-touch list

- `examples/example_chunk.json` — this is a frozen contract example. If
  you must update it, document why in the PR.
- The Notion `data_source_id` in chunks. The receiver replaces it on
  upload; scrapers always emit `"REPLACED_BY_RECEIVER"`.
