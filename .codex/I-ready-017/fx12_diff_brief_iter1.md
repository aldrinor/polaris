# FX-12 (#1130) diff-gate — ITER 1 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope
P3 audit-trail honesty — faithfulness-SAFE. LAST item of the I-ready-017 campaign. Diff:
`.codex/I-ready-017/fx12_codex_diff.patch` (vs FX-14 verified tip `abb6dd09`, 3 files, 72 insertions).

## Bug (audit-trail mislabel)
When the 4-role seam (D8) is binding, the legacy judge is intentionally SKIPPED and the call site passes
`judge_result=None`. `compute_evaluator_gate` then emitted `'judge_parse_failed'` + `judge_parse_ok=False`
→ the #1055 fail-closed (`advisory_unavailable`, release withheld). That code means the judge RAN and
CRASHED — the SAME sentinel as a genuine parse failure. A skip must carry a distinct status.

## Fix (additive — NOT a string swap)
- `evaluator_gate.py`: add `judge_skipped: bool = False`. New FIRST branch
  `if judge_result is None and judge_skipped:` → `reasons.append('judge_skipped_d8_binding')`, keep
  `judge_parse_ok=True`, NO `judge_parse_failed`, NO #1055 fail-closed. `None and NOT judge_skipped` →
  UNCHANGED (`judge_parse_failed` + parse_ok=False + fail-closed). A RAN-but-unparseable judge
  (`parse_ok=False`) is STILL `judge_parse_failed` even with the flag on (skip branch only when
  `judge_result is None`).
- `run_honest_sweep_r3.py` (~5207): `judge_skipped=_seam_will_run`.
- Byte-identical when `judge_skipped=False`.

## Evidence
- §-1.1: the held drb_72 `manifest.json` carries `four_role_evaluation` with the D8 decision
  (`release_allowed: False`, coverage 0.286) → the run was SEAM mode, the legacy judge was skipped
  (`run_drb72.log`: "[judge] skipped — 4-role seam (D8) is the binding gate"), and the legacy
  evaluator_gate is superseded by the seam → FX-12 is AUDIT-TRAIL-ONLY (cannot change a release
  outcome; it corrects the `reasons` label). Full audit: `outputs/audits/I-ready-017/fx12_s11_audit.md`.
- Offline smoke `test_fx12_judge_skipped_iready017.py` → 4 passed: skip → distinct code + no fail-closed;
  genuine failure (default) → `judge_parse_failed` + advisory_unavailable + withheld (UNCHANGED);
  `judge_skipped=False` == default (byte-identical); RAN-but-unparseable + flag-on → still
  `judge_parse_failed`.
- Regression: `test_m205_evaluator_gate` 12 + `test_fx10_completeness_state` 6 — all green (the genuine
  parse-failure + #1055 fail-closed path unregressed; `test_m205` asserts it at :174/:183).

## Faithfulness
Audit-trail observability only. No grounding / strict_verify / 4-role-decision change. The seam's D8
decision gates release in seam mode regardless; this only stops a SKIP from masquerading as a judge
CRASH. The genuine non-seam fail-closed path is preserved exactly.

## Question
Is the skip-vs-failure distinction correct (skip → distinct code + no fail-closed; genuine None and
parse_ok=False both still fail closed), the #1055 path preserved, and OFF byte-identical? Anything
blocking APPROVE?
