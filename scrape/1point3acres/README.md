# 1point3acres.com scraper

Scrapes coding-interview thread reports (面经) from the Discuz forum at
`1point3acres.com/bbs/` and renders them into Notion chunks matching
`prep/AGENTS.md`.

## Authentication

1point3acres runs Discuz, which uses several cookies together (`_auth`,
`_saltkey`, `_lastvisit`, `_sid`). A single cookie isn't enough — you
need the full `Cookie:` header from a logged-in browser session.

### Get your cookie header

1. Sign in to https://www.1point3acres.com/bbs/ in a browser.
2. Open DevTools → **Network** tab → reload the page.
3. Click any request to `1point3acres.com`.
4. In **Request Headers**, find the `Cookie:` line.
5. Copy everything after `Cookie: ` (it's a single long line of
   `name=value; name=value; …`).

### Configure the scraper

Pick one of these:

```bash
# Option A: env var (recommended)
export ACRES_COOKIE="cookie1=val1; cookie2=val2; ..."

# Option B: file
echo 'cookie1=val1; cookie2=val2; ...' > ~/.1p3a-cookie
chmod 600 ~/.1p3a-cookie
```

Then confirm:

```bash
python3 scrape.py probe
# OK: authenticated as <your-username>
```

If it says "not authenticated", you probably copied a partial cookie set.
Re-copy the full header from DevTools.

## Workflow

```bash
# 1. List the first 5 pages of the 面经 board (fid=145 by convention).
#    Output: raw/board_145_threads.json with {tid, title, url} entries.
python3 scrape.py board --fid 145 --pages 5

# 2. Drain every thread referenced in any board_*.json into raw/thread_<tid>.json.
#    Resumable: skips already-cached threads.
python3 scrape.py drain --limit 50

# 3. Render the raw threads into Notion chunks under algo_push/.
python3 render.py

# 4. Validate (using the kit's shared validator).
python3 ../../scripts/validate_chunks.py algo_push/
# Must print: OK: all N chunks valid

# 5. Hand off.
zip -r 1p3a_algo_push.zip algo_push/
```

## Politeness & rate limits

The scraper sleeps a random 2-4.5 s between page fetches. Do **not**
parallelise — 1point3acres has aggressive anti-bot and will rate-limit
or temp-ban accounts that hit too fast.

If you see `AUTH FAIL: redirect to logging.php`, your session expired —
re-export the cookie. If you see HTTP 403 or 503, back off for an hour.

## Known forum IDs (`fid`)

| fid | Board (Chinese) | Notes |
|---|---|---|
| 145 | 面经 (Interview Experience) | Primary target — coding interview reports |
| 28 | 内推 (Referral) | Mostly job posts, not problems |
| 198 | 求职面试 / Interview Q&A | Has coding questions mixed with discussion |

`scrape.py probe` doesn't enumerate boards; pick fid from the forum URL
on the site (`forum-145-1.html` → fid=145).

## Caveats specific to 1point3acres

- **No difficulty field**. Forum posts don't tag difficulty. We omit it
  in the rendered properties (validator accepts that).
- **No reliable acceptance rate**. Also omitted.
- **Companies inferred from title prefix** (`[Amazon]`, `【Google】`) or
  body keyword scan. Some threads describe multiple companies; we cap
  at 5 hits per page.
- **Tag detection is keyword-based**, so it misses problems whose body
  doesn't mention algorithm names. Expect ~30-50% of pages to have an
  empty `Tags` array; that's fine, the property is required as a JSON
  array but empty arrays are allowed.
- **Body content is GBK-encoded**. The scraper decodes correctly; the
  renderer outputs UTF-8.
- **Hidden replies**: many 面经 threads have hidden content unlocked
  by replying or paying credits. We can only scrape what's visible
  to your account. Pages with paywalled solutions will still ship the
  problem statement, which is the part you actually want.

## Files

| Path | Purpose |
|---|---|
| `scrape.py` | HTTP fetcher (board listing + thread fetcher + drain mode) |
| `render.py` | HTML → markdown + Notion chunk emitter |
| `raw/` | Cached scrape results (1 file per board, 1 file per thread) |
| `algo_push/` | Output: Notion-ready chunks |
