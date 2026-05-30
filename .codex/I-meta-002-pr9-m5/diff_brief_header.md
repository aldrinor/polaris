HARD ITERATION CAP: 5 per document. This is iter 1 of the M5 DIFF gate.
- Front-load ALL real findings; reserve P0/P1 for real execution/safety risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (emit this exact YAML block as your final output)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

# Codex DIFF-gate — I-meta-002 PR-9/M5: evaluator_agrees per-claim manifest map

You APPROVED the M5 design (.codex/I-meta-002-pr9-m5/codex_design_verdict.txt): benchmark/sweep-path
manifest map only; writeback in run_one_query right after run_four_role_evaluation; safe rule
evaluator_agrees = (kept) AND final_verdict=="VERIFIED"; never True on non-VERIFIED or dropped; do NOT
synthesize a VerifiedSentence on the sweep path. This diff implements that ruling. NO SPEND / NO NETWORK.

## HARD CONSTRAINTS
- §-1.1 clinical safety: a non-VERIFIED verdict (PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE/unknown/
  missing) must NEVER yield evaluator_agrees=True. Never True on a not-kept claim. Fail-safe default False.
- Frozen, no drift: claim_audit_scorer.py, runtime lock (NOT promoted), clinical_generator/strict_verify.py,
  verified_report.py (all OUT OF SCOPE per your ruling). M1/M2/M3/M4 committed code unchanged.
- D8 stays the single binding gate: M5 must NOT change release_allowed/status; evaluator_agrees is
  audit/inspector fidelity metadata only, strictly ADDITIVE to manifest['four_role_evaluation'].

## What to verify in the diff
1. `build_evaluator_agrees_map(final_verdicts, kept_claim_ids=None)` in sweep_integration.py delegates
   the verdict test to the EXISTING `evaluator_agrees_from_verdict` (== "VERIFIED"; single source of
   truth, not re-inlined); value = is_kept AND VERIFIED; is_kept = (kept_claim_ids is None or claim_id
   in kept_claim_ids); empty final_verdicts -> {}; keys are EXACTLY final_verdicts.keys() (kept_claim_ids
   only affects the boolean, never adds/removes keys — joinable to four_role_claim_audit.json).
2. run_one_query adds manifest['four_role_evaluation']['evaluator_agrees'] = build_evaluator_agrees_map(
   four_role_result.final_verdicts) — strictly ADDITIVE (existing keys release_allowed/held_reasons/
   coverage_fraction/final_verdicts/gaps/kg_path untouched); release_allowed/status logic unchanged.
   kept_claim_ids passed as None (sweep builds FourRoleClaim only from kept/is_verified sentences) —
   confirm this None-default cannot mark a NON-kept claim True (on this path all claims are kept; the
   safe rule still holds since value also requires VERIFIED).
3. Tests cover: True only for VERIFIED; False for PARTIAL/UNSUPPORTED/FABRICATED/UNREACHABLE/unknown/
   missing; empty -> {}; not-kept VERIFIED -> False; None treats all as kept; extra kept id not in
   final_verdicts adds no key.
4. No network/spend; no clinical_generator/frozen drift.

## SMOKE (build agent, this session)
- import scripts.run_honest_sweep_r3 — OK
- pytest tests/roles tests/dr_benchmark tests/architecture -q — 394 passed (test_sweep_integration 11->16).
- verify_lock --consistency — exit 0 (lock NOT promoted). gate_a_dry_run — OVERALL PASS, exit 0.
- tests/polaris_graph not re-run here (M5 touches only run_one_query manifest assembly + sweep_integration
  helper + its test; the 49 tests/polaris_graph failures are PRE-EXISTING per the M3b stash-comparison).

## DIFF (follows)
