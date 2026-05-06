M-16 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-16 v1 verdict: PARTIAL with 4 HIGH:
1. `/runs/diff` registered AFTER `/runs/{slug}` → endpoint dead.
2. Tier keys hardcoded `tier1..tier4`; real V30 uses `T1..T7` +
   `UNKNOWN` → diff missed every real tier shift.
3. claim_id is run-local → false reorder deltas.
4. evidence_id is run-local sequential → false renumber deltas.

All 4 integrated in v2 (commit fbbef2b).

## What changed in v2

`inspector_router.py`:
- `/api/inspector/runs/diff` moved ABOVE `/api/inspector/runs/
  {slug}`. New test `test_run_diff_endpoint_route_order` hits
  the endpoint with two unknown slugs and verifies the response
  is reached (404 with "does_not_exist_a/b" detail), NOT routed
  to /runs/{slug}=diff.

`run_diff.py`:
- `_tier_pcts(ir)`: reads tier keys from
  `AuditIR.tier_mix.fractions` instead of hardcoding
  `tier1..tier4`. Whatever keys appear in the manifest
  (`T1..T7`, `UNKNOWN`) flow through untouched.
- `_diff_tier_mix(ir_a, ir_b)`: union of keys observed in
  either run. A tier present in only one side surfaces.
- `_claim_handle(section_title, text)`: stable content handle
  replaces run-local claim_id as the diff key. ClaimDelta
  still surfaces claim_id (for renderer use), but doesn't key
  on it.
- `_evidence_handle(entry)`: canonical-source handle. Order:
  DOI > PMID > normalized URL > normalized statement.
- `_normalize_url(url)`: lowercase host, strip scheme/www/
  fragment/trailing slash + tracking params (utm_*, fbclid,
  gclid, mc_*, ref, source).

Tests: 6 new regression tests:
- `test_claim_idx_renumber_does_not_surface`: same content,
  shifted idx → no delta.
- `test_evidence_id_renumber_does_not_surface`: same sources,
  different ev_xxx → no delta.
- `test_evidence_doi_collapses_url_variants`: same DOI in
  different URL strings → no delta.
- `test_evidence_normalized_url_collapses_tracking_params`:
  UTM params don't change source identity.
- `test_tier_shift_uses_real_v30_tier_keys`: T1..T4 keys.
- `test_tier_shift_with_extended_keys`: T5/T6/T7/UNKNOWN.
- `test_run_diff_endpoint_route_order`: HTTP-level reachability.

M-16 module 19 → 25 green.

## Your job

Final verdict on M-16. GREEN / PARTIAL / DISAGREE.

If GREEN, M-16 locks and Phase C proceeds to M-20 (50+ templates).

## Output

Write to `outputs/codex_findings/m16_v2_review/findings.md`:

```markdown
# Codex re-review of M-16 v2

## Verdict
GREEN / PARTIAL / DISAGREE

## v1 fix integration
- [x/no] /runs/diff route order fixed
- [x/no] Real V30 tier keys (T1..T7, UNKNOWN)
- [x/no] Stable claim handle (section + normalized text)
- [x/no] Stable evidence handle (DOI/PMID/normalized URL)

## Final word
GREEN to lock M-16 + proceed to M-20 / PARTIAL with edits.
```

Be terse. Under 100 lines.
