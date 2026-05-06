# Codex round 1 — M-D7 phase 2 v1 (commit 4bcf714)

## Tool hints
- `python -m pytest -q tests\polaris_graph\test_md7_phase2_cache_warming.py`
- DO NOT run rg or find — directly read these files only:
  - `src/polaris_graph/audit_ir/cache_warming.py` (~330 lines)
  - `tests/polaris_graph/test_md7_phase2_cache_warming.py` (~520 lines)
  - `docs/md7_phase2_threat_model.md` (~200 lines)
- DO NOT run Python verification scripts that print Unicode

## Scope
M-D7 phase 1 (commit 74b8962, LOCKED) shipped per-workspace
SQLite cache + DOI/PMID/URL canonicalization + 4-method
eviction API.

This v2 layers cache warming: given a list of source URLs +
a pluggable Fetcher Protocol, populate the cache before the
user-facing request path.

## Public API

```python
class CacheFetcher(Protocol):
    def fetch(self, source_url: str) -> FetchResult: ...

@dataclass(frozen=True)
class FetchResult:
    payload: bytes
    content_type: str
    fetch_status_code: int

class WarmingStatus(str, Enum):
    FETCHED = "fetched"
    SKIPPED_CACHED = "skipped_cached"
    ERRORED = "errored"

def warm_cache(
    store: RetrievalCacheStore,
    workspace_id: str,
    source_urls: Sequence[str],
    fetcher: CacheFetcher,
    *,
    skip_existing: bool = True,
    on_fetcher_error: Literal["raise", "record"] = "record",
) -> WarmingReport: ...

def report_to_exit_code(report: WarmingReport) -> int: ...
```

## Boundaries (7 documented in threat model)

1. Pure substrate — stdlib + retrieval_cache only
2. Workspace-scoped — every op needs workspace_id
3. skip_existing default True; force-refresh opt-in
4. on_fetcher_error: "record" continues, "raise" aborts
   with idempotent partial-progress preserved
5. Duplicate URLs collapse to first-occurrence
6. Empty/whitespace URLs skip silently
7. Non-2xx status codes ARE cached (caller raises if
   filtering desired)

## Tests (30/30 passing locally)

- Empty / no-op cases
- Cold cache → all FETCHED
- skip_existing semantics (default + force-refresh + mixed)
- on_fetcher_error semantics (record + raise + protocol error
  doesn't get swallowed)
- Duplicate URL dedup
- Workspace isolation (warming ws1 doesn't warm ws2)
- Contract validation (empty workspace_id, non-Sequence urls,
  non-string url, fetcher missing fetch method, invalid
  on_fetcher_error)
- FetchResult shape validation (FetcherProtocolError)
- Partial-progress preservation under raise mode
- WarmingReport count aggregation
- report_to_exit_code mapping (0 errored → 0; any errored → 1)

## What might Codex probe

- BEGIN IMMEDIATE / WAL interaction with M-D7 phase 1 store
- Race: two concurrent warm_cache calls on same workspace+URL
  (per phase 2 v1 boundary 1, single-threaded — no concurrency
  guarantee, but a doc-level note may be needed)
- on_fetcher_error="raise" swallowing FetcherProtocolError —
  v1 explicitly RE-RAISES protocol errors regardless of mode
  (verified by test_fetcher_protocol_error_propagates_under_record_mode)
- Sequence(str, bytes) edge case — v1 explicitly rejects str
  and bytes as inputs (test_non_sequence_urls_raises)
- store.put exception inside the loop — v1 lets RetrievalCacheError
  propagate (no catch), since malformed FetchResult means caller
  Fetcher needs fixing

## Verdict format

```
## Verdict
GREEN | PARTIAL | BLOCKED

## Boundary integration
- [x/ ] Pure substrate (no live HTTP)
- [x/ ] Workspace-scoped
- [x/ ] on_fetcher_error semantics correct
- [x/ ] Duplicate URL dedup correct

## New findings (if any)
[SEVERITY] file:line — description

## Final word
GREEN | PARTIAL until X
```
