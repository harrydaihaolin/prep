#!/usr/bin/env python3
"""Filter mikoxyr_push/ chunks to ALGORITHM-only and rebatch.

Drops SD, ML_SD, and SQL pages (they have diagrams/SVGs that don't render well
and get truncated). Outputs to /tmp/h2h/algo_push/ with chunks sized so each
fits in a single MCP call (target ~80 KB JSON, max ~25 pages each).
"""
import json
from pathlib import Path

SRC = Path("/tmp/h2h/mikoxyr_push")
DST = Path("/tmp/h2h/algo_push")
DST.mkdir(exist_ok=True)

NEW_DATA_SOURCE_ID = "2ea55f8d-1963-409f-b82b-1ee37432be40"

# Collect every ALGORITHM page across all chunks
algo_pages = []
for ch in sorted(SRC.glob("chunk_*.json")):
    d = json.loads(ch.read_text())
    for p in d["pages"]:
        if p["properties"].get("Type") == "ALGORITHM":
            algo_pages.append(p)

print(f"Collected {len(algo_pages)} ALGORITHM pages")

# Re-batch: target ~80 KB JSON per chunk
MAX_BYTES = 80_000
MAX_PAGES = 25

# Clear existing chunks
for old in DST.glob("chunk_*.json"):
    old.unlink()

buf = []
buf_bytes = 0
chunk_idx = 0

def flush():
    global buf, buf_bytes, chunk_idx
    if not buf:
        return
    out = {
        "parent": {"data_source_id": NEW_DATA_SOURCE_ID},
        "pages": buf,
    }
    target = DST / f"chunk_{chunk_idx:03d}.json"
    target.write_text(json.dumps(out, ensure_ascii=False), encoding="utf-8")
    print(f"  {target.name}: {len(buf):>2} pages  {target.stat().st_size:>6} bytes")
    chunk_idx += 1
    buf = []
    buf_bytes = 0

for p in algo_pages:
    psize = len(json.dumps(p, ensure_ascii=False))
    if buf and (buf_bytes + psize > MAX_BYTES or len(buf) >= MAX_PAGES):
        flush()
    buf.append(p)
    buf_bytes += psize

flush()
print(f"\nTotal: {chunk_idx} chunks for {len(algo_pages)} ALGORITHM pages -> {DST}")
