# Codex round 1 — M-INT-2 v1

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_m_int_2_cache_warming_integration.py`
- Read `scripts/run_honest_sweep_r3.py` (imports + _warm_canonical_corpus + main_async pre-sweep block) and the test file.

## Scope
Wires `cache_warming.warm_cache(...)` + RetrievalCacheStore +
CacheFetcher into the sweep pre-loop stage.

## Acceptance bar
1. Imported (warm_cache, RetrievalCacheStore, CacheFetcher,
   WarmFetchResult)
2. Invoked (_warm_canonical_corpus called from main_async
   when canonical_urls present)
3. Run-log evidence (sweep_warm_summary printed + carries
   fetched/skipped/errored counts)
4. PG_USE_CACHE_WARMING=0 disables (returns None)

## v1 caveat to flag
The CacheFetcher impl is a STUB (returns empty payload). Real
HTTP wiring is Phase F. The substrate import + invocation +
SQLite write are demonstrated; the bytes payload is empty.

This is intentional for M-INT-2 v1 — the integration step is
the substrate-to-production wiring, not the fetcher backend.
v2 (in Phase F) replaces _StubHttpFetcher with a real httpx
client, but the call shape is already in place.

Tests: 6/6 passing.

## Verdict format
GREEN | PARTIAL | BLOCKED
