# M-D7 phase 2 v1 — cache warming substrate boundary

**Status:** v1 / 2026-04-28
**Module:** `src/polaris_graph/audit_ir/cache_warming.py`
**Tests:** `tests/polaris_graph/test_md7_phase2_cache_warming.py` (30 passing)
**Pairs with:** M-D7 phase 1 (`retrieval_cache.py`, commit 74b8962).
**Substrate:** stdlib + `retrieval_cache.RetrievalCacheStore` /
`make_cache_key` only — no HTTP client, no DB queries beyond
the M-D7 phase 1 API surface.

---

## Scope

M-D7 phase 1 ships per-workspace SQLite cache + DOI/PMID/URL
canonicalization + 4-method eviction API. Phase 2 v1 layers
**preemptive cache warming**: given a list of source URLs +
a pluggable Fetcher Protocol, populate the cache before the
user-facing request path needs the entries.

Phase 2 v1 ships:
  - `CacheFetcher` Protocol (pluggable seam for HTTP /
    Crossref / Semantic Scholar)
  - `FetchResult` dataclass (payload + content_type +
    fetch_status_code)
  - `WarmingStatus` enum (FETCHED | SKIPPED_CACHED | ERRORED)
  - `WarmingResult` per-URL outcome
  - `WarmingReport` aggregate with counts + timestamps
  - `warm_cache(store, workspace_id, source_urls, fetcher, *,
    skip_existing, on_fetcher_error)` pure substrate

Phase 2 v2 (deferred):
  - Concurrent warming (thread / asyncio Fetcher variants)
  - Auto-warming heuristics (recent hits across workspaces;
    static "always-fresh" lists)
  - M-D10 freshness monitor integration (auto-warm on
    eviction trigger so the next fetch is never cold)

---

## Phase 2 v1 boundaries

### 1. Pure substrate — no live HTTP, no concurrent execution

`cache_warming.py` imports only stdlib +
`retrieval_cache.RetrievalCacheStore` /
`retrieval_cache.make_cache_key`. The Fetcher Protocol is the
seam: caller code wires up the actual HTTP / Crossref /
Semantic Scholar client. `warm_cache` itself is single-
threaded; concurrency is v2 territory.

This boundary mirrors M-D11 phase 2 v2 (pin trends), M-D9
phase 2 (BEAT-BOTH scoring), and M-D7 phase 1 itself —
substrate primitives never touch runtime services.

### 2. Workspace-scoped — every operation requires workspace_id

`warm_cache` validates `workspace_id` as non-empty and strips
whitespace before passing through to the M-D7 phase 1 store.
Cross-workspace warming is impossible by API: a URL warmed
into ws1 is invisible to ws2's cache lookups (verified by
`test_warming_one_workspace_does_not_warm_another` and
`test_skip_existing_is_workspace_scoped`).

### 3. skip_existing default True; opt-out for force-refresh

The default is "warm what's missing, skip what's already
cached". Re-warming an already-warm cache is then cheap (one
DB lookup per URL, no fetcher invocation). For force-refresh
scenarios (e.g. an operator wants to invalidate stale cached
PDFs), `skip_existing=False` invokes the fetcher even on
cache hits.

**Mitigation**: tests pin both modes explicitly. Force-
refresh is a deliberate caller choice — the substrate doesn't
auto-detect "stale vs fresh" (that's M-D10 freshness
monitor's job).

### 4. on_fetcher_error: "record" (default) vs "raise"

When the fetcher raises:
  - `"record"`: capture `str(exc)` in WarmingResult.error,
    continue with the next URL. Other URLs' warming progress
    is preserved.
  - `"raise"`: re-raise the fetcher's exception immediately.
    Already-warmed URLs in this call ARE preserved in the
    cache (idempotent partial progress per LAW II — no
    rollback that would force the operator to re-fetch
    already-warm entries).

`FetcherProtocolError` (the fetcher returned a non-FetchResult
shape) is NEVER caught by `on_fetcher_error="record"` — it's
a programmer error indicating the caller's Fetcher impl needs
fixing, not a transient fetch failure. Same with internal
`CacheWarmingError`.

**Mitigation**: tests pin both modes
(`test_on_error_record_continues_after_failure`,
`test_on_error_raise_propagates`,
`test_on_error_raise_preserves_partial_progress`,
`test_fetcher_protocol_error_propagates_under_record_mode`).

### 5. Duplicate URLs collapse to first-occurrence-wins

Two URLs that canonicalize to the same `cache_key` are
treated as duplicates. The first occurrence is processed;
subsequent occurrences are dropped from the report (NOT
counted in any aggregate, fetcher NOT called).

This is the right semantic because:
  - Bulk warming inputs often come from concatenated lists
    where dedup would otherwise be the caller's
    responsibility
  - Re-fetching the same URL twice in one warming run is
    wasted work — the second fetch would just refetch the
    same payload moments later

**Mitigation**: tests pin both exact-duplicate
(`test_duplicate_urls_deduplicate_in_report`) and
canonical-key-collision
(`test_duplicate_canonical_keys_deduplicate`) cases.

### 6. Empty / whitespace URLs skip silently, don't fail

A URL of `""` or `"   "` is dropped (not stored, not
fetched, not in the report). Bulk warming with a malformed
URL in position N should not abort — the rest of the list
proceeds. This trades strictness for usability; the operator
gets per-URL signal via the report's per-result status, but
empty URLs don't appear in the report at all.

**Mitigation**: `test_only_empty_or_whitespace_urls_returns_empty_report`
verifies no fetcher call + no cache entries.

### 7. Substrate trusts the Fetcher's status code semantics

A FetchResult with `fetch_status_code=404` IS stored in the
cache. The substrate does NOT auto-treat non-2xx as errored:
caching error pages (404, 410 GONE, 429 rate-limited) is
often what the operator wants for retry-suppression — re-
fetching a known-404 URL is wasted work.

If the operator wants to NOT cache non-2xx, their Fetcher
should raise on those status codes (which then routes
through `on_fetcher_error`).

**Mitigation**: `test_fetched_entries_preserve_content_type_and_status`
pins that status code is stored as-is. The Fetcher Protocol
docstring documents this contract explicitly.

---

## Phase 2 v1 NON-goals (defer to v2)

  - **No concurrent fetching**: single-threaded per call. v2
    may add `AsyncCacheFetcher` Protocol + `warm_cache_async`.
  - **No retry / backoff**: caller's Fetcher impl handles
    transient errors. The substrate just records what came
    out of the Fetcher.
  - **No fetch budget / rate limiting**: caller controls via
    Fetcher impl.
  - **No content validation**: substrate doesn't inspect
    `payload` beyond storing the bytes. Validation (PDF
    parses cleanly, JSON is well-formed, etc.) is caller
    territory.
  - **No auto-warming heuristics**: substrate accepts an
    explicit URL list. "What should we warm?" is V19+ live-
    audit territory.
  - **No M-D10 freshness integration**: auto-warm on
    eviction is v2.
  - **No warming-cost telemetry**: phase 2 v2 may add
    per-URL timing + payload-size aggregation.

---

## Codex review trail

Round-1 brief incoming. Tool hints (per M-D5 / M-D3 /
M-D9 phase 2 / M-D11 phase 2 v2 v1 lessons):
- Use `python -m pytest -q tests\polaris_graph\test_md7_phase2_cache_warming.py`
- Skip `outputs/codex_*` and `.codex_tmp/` in `rg`
- DO NOT run Python verification scripts that print Unicode —
  Windows sandbox uses cp1252 (cut off 5+ Codex reviews this
  session)
- 30 tests pin all 7 boundaries above

Targeted at 1-2 round convergence per the M-D7 phase 1 +
M-D11 phase 2 v1 patterns (substrate work with v1-shipped
threat-model docs and pure-derivation boundaries converges
fast).

---

## Lock note

v1 GREEN-lock target after Codex round 1-2. v2 (concurrency,
auto-warming, M-D10 integration) tracked separately.
