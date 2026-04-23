M-51 code audit — V29 Strategy β cycle 1, item 1 of 3.

## Commit

`0143deb` PL: M-51 — anchor-matched primary hard-reservation post-process (V29-a)

## Plan reference

`outputs/audits/v28/fix_plan_v29.md` M-51 + your pass-1 plan review
at `outputs/codex_findings/v29_fix_plan_review_pass1/findings.md`
(CONDITIONAL-no-blockers with 7 specific revisions).

## What changed

`src/polaris_graph/retrieval/evidence_selector.py`:

1. **Main branch** (after tier-balanced + M-42 floor reservations
   complete, before final sort at line ~945):
   - New `_m51_canonical_identity(row)` helper — evidence_id when
     present, else `("key", url_lower, title_lower[:200],
     direct_quote[:200])` tuple.
   - For each unique anchor (deduped from
     `primary_trial_anchors`), scan `scored` for first row matching
     `_m42e_detect_primary_for_anchor` that isn't already in
     `selected_canon`. Insert at position 0 of `selected`.
   - Cap: `min(len(unique_anchors), max_rows)`.
   - Trim on overflow: identify non-M-51 rows, sort by
     (-tier_priority, +score, -idx) to pop lowest-priority first.
     Rebuild `selected` preserving original order minus evicted.
   - Telemetry note emitted only when insertions happen.

2. **Short-pool branch** (M-46 path):
   - Parallel helper `_m51_canonical_identity_sp` (same logic,
     scoped to the short-pool function).
   - For each unique anchor not already caught by M-42e floor,
     scan full `scored` pool (including non-T1) for
     anchor-matched primary. Add to `m51_extra_ids`.
   - `_priority_class` updated: class 0 now covers M-42e primaries
     AND M-51 extras.
   - Telemetry note emitted.

## Tests

`tests/polaris_graph/test_m51_selector_primary_custody.py` — 11 tests:
- Core acceptance (primary dropped by tier-balance → inserted)
- Multi-anchor multi-primary all inserted
- Anchor without primary in corpus → no-op (no telemetry)
- Primary already selected → no duplicate
- Cap = min(|unique_anchors|, max_rows)
- Duplicate anchor list dedupe
- Trim overflow (max_rows enforcement)
- Backward-compat: None anchors = empty anchors (byte-identical)
- Short-pool full-pool scan
- M-51 does not reinsert already-selected primary (canonical check)
- Missing evidence_id tuple-identity fallback

305/305 full M-series regression (M-32/35/41/42/43/44/45/46/47/48/50/51).

## What to audit

1. **Canonical identity per your revision #1**: helper correctly
   falls back to (url, title[:200], quote[:200]) when evidence_id
   missing?
2. **Cap per your revision #3**: `min(len(unique_anchors), max_rows)`
   applied correctly?
3. **Trim per your revision #2**: my eviction order is
   `(-tier_priority, +score, -idx)` — pops lowest-priority row
   first. Correct?
4. **Backward-compat per your revision #4**: primary_trial_anchors
   None/empty = no M-51 activity?
5. **Short-pool path**: M-51 fires for anchors M-42e missed (non-T1
   primaries, or relevance-driven misses). Correct?
6. **Trim protects reserved primaries**: when overflow, the trim
   should not evict any M-51-inserted row. Verified by my fixture
   `test_insertion_triggers_trim_to_max_rows`?

## Strategic context

You explicitly said V29 should be "first architectural slice of β,
not a narrow patch. If SURPASS-4 and SURPASS-CVOT are already in
live_corpus and still absent from the report after V29, the
architecture is failing at the exact custody boundary that must be
fixed before 7/7 is credible."

M-51 is that custody fix at the SELECTOR boundary. M-52 will add
the generator-side safety net pull. M-53 will give per-anchor
diagnostic telemetry for V30 planning. All three ship as V29.

Write verdict to `outputs/codex_findings/m51_code_audit/findings.md`.
On READY / CONDITIONAL-no-blockers: Claude proceeds to M-52.
