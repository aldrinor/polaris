# FX-12 §-1.1 audit — eval_gate judge_skipped_d8_binding reason (#1130)

**Standard:** §-1.1 over the eval_gate decision logic + the REAL held drb_72 `manifest.json` (which
confirms the seam-binding precondition). The fix is audit-trail-only; the binding release decision is
unchanged.

## The bug (audit-trail mislabel)
When the legacy judge is intentionally SKIPPED because the 4-role seam (D8) is the binding gate, the
call site passes `judge_result=None`. `compute_evaluator_gate` then emitted `'judge_parse_failed'` +
`judge_parse_ok=False` → the #1055 fail-closed (`advisory_unavailable`, release withheld). That code
means the judge RAN and CRASHED — the SAME sentinel as a genuine parse failure. An intentional skip
must carry a distinct status (audit-trail SOTA: never reuse a failure code for a skip).

## The fix (additive — NOT a string swap)
- `evaluator_gate.py`: add `judge_skipped: bool = False` to `compute_evaluator_gate`. New FIRST branch
  `if judge_result is None and judge_skipped:` → `reasons.append('judge_skipped_d8_binding')`, keep
  `judge_parse_ok=True`, NO `judge_parse_failed`, NO #1055 fail-closed. `judge_result is None and NOT
  judge_skipped` → unchanged (`judge_parse_failed` + parse_ok=False + fail-closed). A judge that RAN
  but failed to parse (`parse_ok=False`) is STILL `judge_parse_failed` even with the flag on (the skip
  branch only applies when `judge_result is None`).
- `run_honest_sweep_r3.py` call site (~5207): `judge_skipped=_seam_will_run`.
- Byte-identical when `judge_skipped=False`.

## §-1.1 — held drb_72 confirms the seam-binding precondition
The held `manifest.json` carries `four_role_evaluation` with the D8 decision (`release_allowed: False`,
`held_reasons: ['d8_unsupported_residual_below_coverage','d8_pending_rewrite']`, coverage 0.286) — i.e.
the run was SEAM mode, so the legacy judge was SKIPPED (`run_drb72.log`: "[judge] skipped — 4-role seam
(D8) is the binding gate"). The legacy `evaluator_gate` block is superseded by the seam in seam mode
(`superseded_by_four_role_seam`), so the release decision is the D8 one regardless — confirming FX-12 is
AUDIT-TRAIL-ONLY (it corrects the `reasons` label; it cannot change a release outcome). With FX-12, a
seam-mode eval_gate carries `judge_skipped_d8_binding` instead of the misleading `judge_parse_failed`.
The live seam-mode reasons surface at RERUN.

## Offline smoke (proves the behavior)
`pytest tests/polaris_graph/test_fx12_judge_skipped_iready017.py` → 4 passed:
- skip (`None, judge_skipped=True`) → `judge_skipped_d8_binding` in reasons, `judge_parse_failed` NOT,
  `judge_parse_ok=True`, gate_class != advisory_unavailable, release NOT withheld on judge grounds.
- genuine failure (`None`, default) → `judge_parse_failed` + advisory_unavailable + release withheld
  (UNCHANGED — the #1055 fail-closed preserved).
- explicit `judge_skipped=False` == default (byte-identical reasons/class/parse_ok/release).
- a RAN-but-unparseable judge (`parse_ok=False`) + `judge_skipped=True` → still `judge_parse_failed`
  (skip branch only when `judge_result is None`).
- Regression: `test_m205_evaluator_gate` 12 + `test_fx10_completeness_state` 6 — all green (the genuine
  parse-failure + completeness paths unregressed).

## Faithfulness
Audit-trail observability only. No grounding / strict_verify / 4-role-decision change. The seam's D8
decision gates release in seam mode regardless; this only stops a SKIP from masquerading as a judge
CRASH in `reasons`/`manifest`. The genuine non-seam parse-failure path (the #1055 fail-closed) is
preserved exactly. No-silent-anything-aligned: an intentional skip now reads as a skip.
