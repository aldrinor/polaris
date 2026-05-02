M-D7 phase 1 review (commit 9201fe7).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Phase D M-D7 (caching layer). M-D11 phase 1 + M-D9 phase 1
both LOCKED. Per advisor: extend M-21 substrate, per-workspace
scope (not global), explicit eviction API for M-D10 hookup.

This commit ships **bootstrap retrieval cache**: per-workspace
SQLite cache with DOI/PMID/URL canonicalization + 4-method
eviction API. Phase 2 (system-wide cache + empirical ≥80%
time-saved acceptance test + honest_pipeline wire-in) deferred.

## Files

`src/polaris_graph/audit_ir/retrieval_cache.py`:
  - CacheEntry frozen dataclass
  - make_cache_key(source_url): canonicalizes via
    DOI(`10.NNNN/...`) / PMID(`\d+`) / URL fallback
    (reuses M-16 `run_diff._normalize_url`)
    Discriminator prefix prevents kind collision.
  - RetrievalCacheStore (Path-based, matches M-21 per-call
    WAL pattern):
    - put / get / count
    - evict(workspace, cache_key)
    - evict_by_url(workspace, source_url) — M-D10 hookup
    - evict_older_than(workspace, max_age_seconds)
    - evict_all(workspace)
  - SQLite schema with 2 indexes (ws+fetched, ws+last_hit)

`tests/polaris_graph/test_md7_retrieval_cache.py`: 29 tests.

## Your job

GREEN / PARTIAL / DISAGREE.

1. **Scope**: per-workspace bootstrap is the right cut?
   Global system-wide cache deferred to phase 2 with auth
   isolation work.

2. **Cache key strategy**: DOI > PMID > canonical URL with
   discriminator prefix. Any cross-kind collision risks I
   missed? E.g. URL containing `10.NNNN/` could plausibly
   look like a DOI?

3. **Eviction API for M-D10 hookup**: evict_by_url(ws, url)
   takes raw URL, canonicalizes, calls evict(). M-D10's
   freshness-detection daemon can call this without
   knowing the key format. Sufficient for the integration?

4. **Payload integrity**: SHA-256 stored on every put;
   last_hit_at tracks LRU candidates. Anything else
   needed for the cache integrity layer?

5. **M-21 coexistence**: same DB file, separate table, no
   foreign keys / shared rows. Right cut, or should there
   be cross-references (e.g. memory entries pointing at
   cache entries)?

6. **Pin coupling**: cache state NOT in
   `ModelPin.retrieval_source_versions` — workspace-scoped
   vs run-scoped (see module docstring). Phase 2 may add
   `cache_revision` if replay needs bit-exact cache. Right
   call, or should cache state pin in v5?

7. **Concurrency**: per-call WAL connections matching
   M-21. Any race the put + last_hit_at UPDATE could hit
   under concurrent gets?

8. **Phase 2 readiness**: with phase 1 substrate stable, can
   honest_pipeline wire-in + empirical timing test layer
   cleanly?

## Output

`outputs/codex_findings/md7_phase1_review/findings.md`:

```markdown
# Codex review of M-D7 phase 1 (commit 9201fe7)

## Verdict
GREEN / PARTIAL / DISAGREE

## Findings
- [scope concern, if any]
- [cache key concern, if any]
- [eviction API concern, if any]
- [integrity concern, if any]
- [coexistence concern, if any]
- [pin coupling concern, if any]
- [concurrency concern, if any]
- [phase-2 readiness concern, if any]

## Final word
GREEN to lock M-D7 phase 1 / PARTIAL with edits.
```

Be terse. Under 60 lines.
