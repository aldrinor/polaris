M-42e pass-2 audit. Pass-1 verdict: BLOCKED with 1 blocker + 3
mediums. Narrow scope — only review pass-2 diff.

## Pass-1 findings you raised

**Blocker**: `_m42e_detect_primary_for_anchor` accepted post-hoc/
subgroup/secondary/exploratory/pooled titles on NEJM/JAMA/Lancet/
Nature/Diabetes Care hosts as primaries. Pass-1 test fixture
used springer.com which bypassed the primary-host check.

**Medium #1**: cap test bypassed the floor code (pool_size ==
max_rows early exit).

**Medium #2**: no selector telemetry when floor fires.

**Medium #3**: T1-review-displacement trade-off — code comment.

## Pass-2 changes

1. **Blocker fix**: `_M42E_NON_PRIMARY_TITLE_PATTERNS` frozenset of
   23 markers (post hoc, post-hoc, subgroup analysis, secondary
   analysis, exploratory analysis, pooled analysis, network
   meta-analysis, meta-analysis, systematic review, substudy,
   sub-study, pre-planned analysis, pre-specified analysis,
   pre-specified secondary, commentary, editorial, perspective,
   sub study). Detection now requires: (a) anchor in title, (b)
   NO non-primary marker in title, (c) URL on primary host/DOI.
   Order matters — non-primary check BEFORE primary-host check.

2. **Telemetry**: `EvidenceSelection.notes` gains entries:
   - `m42e_primary_floor reserved=N cap=6 anchors=[...]` when floor
     reserves slots
   - Absent when no anchors matched

3. **Comment (medium #3)**: accepted-trade-off note added in code
   explaining that T1 review slots can become zero when primaries
   saturate quota.

4. **New regression tests** (9 blocker + 1 cap + 2 telemetry = 12):
   - Post-hoc on NEJM host (rejected)
   - Post-hoc on NEJM DOI (rejected)
   - Subgroup on JAMA (rejected)
   - Secondary on Lancet (rejected)
   - Exploratory on Diabetes Care (rejected)
   - Pooled analysis (rejected)
   - Meta-analysis on NEJM (rejected)
   - Substudy on Lancet DOI (rejected)
   - Commentary on NEJM editorial DOI (rejected)
   - 8-primary pool with max_rows=12 → cap enforced via telemetry
   - Telemetry note present when floor fires
   - Telemetry note absent when no anchors match

## Files

```
src/polaris_graph/retrieval/evidence_selector.py
  - _M42E_NON_PRIMARY_TITLE_PATTERNS (new frozenset)
  - _m42e_detect_primary_for_anchor() adds step (3) guard
  - select_evidence_for_generation() appends m42e_primary_floor note
tests/polaris_graph/test_m42e_primary_trial_floor.py (+12 tests)
```

## What to verify

1. Is the non-primary pattern list exhaustive? Consider adding
   "pharmacokinetic analysis", "modeling analysis", or similar?
2. Does the order of checks prevent a false positive on a
   multi-marker title (e.g., "Primary analysis of the SURPASS-2
   trial" — does "primary analysis" trigger anything? The pattern
   list avoids generic "analysis" for this reason)?
3. Telemetry format: is the list-truncation to 10 anchors
   reasonable, or should we enforce a specific max length?
4. Does the cap test actually exercise the floor (pool_size >
   max_rows path)?

## Deliverable

Write `outputs/codex_findings/m42e_code_audit_pass2/findings.md`
with:
- Final verdict (READY | BLOCKED | CONDITIONAL)
- Blockers (zero if READY)
- Remaining mediums
- Confirmation that pass-1 blocker is closed

Keep under 500 words.
