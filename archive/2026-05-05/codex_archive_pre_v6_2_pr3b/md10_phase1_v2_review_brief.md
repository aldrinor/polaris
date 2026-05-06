M-D10 phase 1 v2 review (commit de6b987).

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Round 1 (commit 7bece98) verdict was PARTIAL with 3 findings:
  1. [HIGH] Alert state keyed by raw URL, not canonical identity
  2. [HIGH] Expression-of-concern conflated into `retracted`
  3. [LOW] Threat-model said unreachable should auto-promote

This v2 commit closes all 3.

## What changed in v2

`src/polaris_graph/audit_ir/freshness_monitor.py`:

1. Schema: added `cache_key TEXT NOT NULL` column. Index
   updated: `idx_freshness_ws_url_checked` ->
   `idx_freshness_ws_cachekey_checked`. CHECK constraint
   gained `expression_of_concern`.

2. FreshnessAlert dataclass: added `cache_key` field
   (canonical identity, computed via M-D7 `make_cache_key`).
   Raw `source_url` retained for operator visibility.

3. FreshnessStatus enum: added EXPRESSION_OF_CONCERN.
   `_EVICTING_STATUSES` now includes EoC (same eviction
   semantics as retracted; different operator routing).

4. record() accepts optional cache_key override or computes
   from source_url. Validates cache_key non-empty after
   strip.

5. latest_for_url() now canonicalizes input and queries by
   cache_key — equivalent URL forms merge into one history.

6. check_freshness coordinator computes cache_key once, uses
   it for both eviction and record. Canonicalize-fail is now
   a hard FreshnessMonitorError (was silently skip-eviction).

`docs/md10_phase1_threat_model.md`:
  - Eviction contract updated for EoC
  - Removed wrong "unreachable -> superseded" auto-promotion
  - Phase-2 contract clarified: persistent unreachable stays
    unreachable; daemon escalates to operator review queue,
    never changes taxonomy

## Your job

GREEN-LOCK or PARTIAL.

1. **Round 1 fix integration**:
   - [ ] alert dedup by canonical cache_key (not raw URL)
   - [ ] expression_of_concern split + SQL CHECK + eviction
   - [ ] threat-model doc corrected re: unreachable

2. **Stop criterion**: GREEN-lock if remaining findings are
   minor (additional protocol shape suggestions, doc nits,
   phase-2 hookup hints). PARTIAL only if you find:
     (a) Foundational substrate bug in v2
     (b) Canonical-key dedup is broken under some edge case
     (c) EoC eviction semantics still wrong
     (d) Pin coupling boundary doc still misleads

3. **Phase 2 readiness**: with v2 substrate stable
   (canonical-key dedup + 5-status taxonomy + clock
   injection + record-after-evict contract), can real
   Crossref/PubMed detectors layer on cleanly?

## Output

`outputs/codex_findings/md10_phase1_v2_review/findings.md`:

```markdown
# Codex round 2 — M-D10 phase 1 v2 (commit de6b987)

## Verdict
GREEN / PARTIAL / DISAGREE

## Round 1 fix integration
- [x/no] canonical cache_key dedup
- [x/no] expression_of_concern split
- [x/no] threat-model corrected

## New findings (if any)
- [...]

## Final word
GREEN to lock M-D10 phase 1 / PARTIAL with edits.
```

Be terse. Under 50 lines.
