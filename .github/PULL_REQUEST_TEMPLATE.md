## Summary

<!-- 1-3 bullets describing what changed and why. -->

## Validator output

<!-- Paste `python3 scripts/validate_chunks.py <dir>/` result, or N/A. -->

## Checklist

- [ ] `python -m compileall -q scripts scrape` is clean
- [ ] `python3 scripts/validate_chunks.py examples/` prints `OK: all <N> chunks valid`
- [ ] If scraper output changed, the fix is upstream in the renderer — not hand-patched JSON
- [ ] Touched files are listed in AGENTS.md ownership map (or call out the gap)
