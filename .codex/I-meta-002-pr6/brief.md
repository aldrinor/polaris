# Codex brief-gate — I-meta-002 sub-PR-6: sweep wiring + Gate-A no-spend dry run (capstone)

> **THIS IS A BRIEF / DESIGN REVIEW, NOT A DIFF REVIEW.** Implementation files do not exist yet —
> written in BUILD after this APPROVE, reviewed at the DIFF-gate. "Files not present" is expected.

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings. Reserve P0/P1 for real execution/safety risks.
- If holding back a P1 for the next round — surface it now; iter 6 does not exist.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

## HARD CONSTRAINTS (operator-locked, NOT consultable)
- 4-role architecture LOCKED. **NO MONEY in this PR.** The sweep wiring is exercised ONLY via mock/
  injected transport in tests; the live 4-role sweep (real Mirror/Sentinel/Judge on rented GPUs) is
  Gate-B, AFTER the operator loads Vast credit — explicitly out of scope here.
- **The operator's standing rule: NO spend until the no-spend dry run is GREEN and BOTH Claude and
  Codex review every output/log line-by-line (§-1.1).** This PR delivers exactly that dry run, with
  no spend.
- Operator is blind — crisp verdict.
- Frozen: `claim_audit_scorer.py`. Canonical: `polaris_pipeline_canonical.md` (do not drift).
- The runtime lock `polaris_runtime_lock.yaml` status is `codex_approved_pending_operator_signature`;
  the architecture-coverage gate RAISES while pending ("smokes FROZEN"). See Question 1 — Claude
  proposes NOT auto-promoting the lock to `locked` in this PR (promotion un-freezes paid smokes =
  the operator's spend gate).

## Context
sub-PR-1..5 committed + Codex-APPROVED on branch bot/I-meta-002-4role-wiring: lock slug+serving_route
+ verify_lock --consistency (1); role contracts (2); D8 release policy (3); 3 role adapters (4);
4-role orchestration pipeline + snowball KG + 4-role pins (5). Grounding (read this session):
- Sweep seam: `scripts/run_honest_sweep_r3.py:2918-2956` runs `run_external_evaluation(enable_llm_judge=
  False)` then `judge_report()` tagged role="evaluator"; manifest finalized at :2981-3116 via
  `compute_evaluator_gate(...)` -> `manifest["release_allowed"]`. `VerifiedSentence.evaluator_agrees`
  is currently always None.
- sub-PR-5 `roles/role_pipeline.run_claim_pipeline(transport, *, claim_id, ...) -> ClaimPipelineResult`
  (D8ClaimRow w/ final_verdict, records, raw sub-results); `memory/verified_claim_graph.VerifiedClaimGraphStore`.
- sub-PR-3 `release_policy.apply_d8_release_policy(...)`.
- `pathB_run_gate.preflight(..., offline=False, enforce_architecture_coverage=True)`;
  `_assert_architecture_coverage()` RAISES while lock status==pending.

## Scope of sub-PR-6 (acceptance criteria) — PROPOSED
1. **Sweep wiring (no-spend, transport-injected)** — at the `run_honest_sweep_r3.py` evaluator seam,
   add a 4-role path that, FOR EACH kept verified claim, runs `run_claim_pipeline` over an INJECTED
   `RoleTransport`, collects D8ClaimRows, applies `apply_d8_release_policy`, sets manifest
   `release_allowed`/status from the D8 decision, populates `VerifiedSentence.evaluator_agrees` from
   the final_verdict, fixes the judge/mirror/sentinel role tags, and writes the snowball KG at run
   end. **Guarded behind an explicit mode/flag** so the DEFAULT/dry-run path does NOT make real role
   calls (the 4-role path activates only when a real transport is supplied = Gate-B). The legacy
   evaluator path remains available behind the flag so nothing breaks pre-Gate-B. Unit/integration
   tested with a MOCK transport (no network).
2. **Gate-A no-spend dry-run harness** (`scripts/dr_benchmark/gate_a_dry_run.py`): runs the no-spend
   checks and emits a machine-readable PASS/FAIL + artifacts for the dual §-1.1 review:
   (a) pytest tests/roles tests/architecture tests/dr_benchmark (serialized);
   (b) `verify_lock --consistency` exit 0;
   (c) `preflight(offline=True)` proving all 4 role pins resolve (see Question 2 for the frozen-lock
       coverage check);
   (d) per-role contract fixtures (Sentinel yes=UNGROUNDED lethal-polarity; Judge 5-enum; Mirror
       two-pass) exercised via the mock transport;
   the 3 cheap real probes (Serper/S2/DeepSeek) are GATED behind an explicit `--with-live-probes`
   flag, default OFF, so the dry run is pure-offline/no-spend unless the operator opts in (Question 3).
   The harness writes `outputs/gate_a/dry_run_report.json` + a human-readable summary.
3. **NO lock promotion** (Question 1): leave status `codex_approved_pending_operator_signature`; the
   dry run does not require `locked`. Document that flipping to `locked` (which un-freezes paid
   smokes) is the operator's spend-authorization step, performed AFTER the green dry run + dual review.
4. Hygiene: snake_case, explicit imports, named constants, no `except: pass`, no unittest.mock in
   `src/`, no real network in the default dry-run path, no `datetime.now()` in library code.

## Files I have ALSO checked / relevant
- `pathB_run_gate.py:_assert_architecture_coverage` — raises while lock pending; the dry run must
  verify 4-role coverage WITHOUT requiring `locked` and WITHOUT weakening the freeze (Question 2).
- `evaluator_gate.py:compute_evaluator_gate` — the legacy manifest gate; the 4-role path uses D8
  `apply_d8_release_policy`. Whether D8 REPLACES or runs ALONGSIDE the evaluator gate at the manifest
  seam is Question 4.
- sub-PR-2..5 modules — consumed as-is.

## Questions for Codex (load-bearing)
1. **LOCK PROMOTION:** Claude proposes NOT auto-flipping the lock to `locked` in this PR — promotion
   un-freezes paid smokes and is the operator's spend gate (the operator's hard no-spend-until-green-
   dry-run rule). The dry run runs with the lock still pending. Correct, or must this PR promote?
2. **FROZEN-LOCK COVERAGE CHECK:** how should the no-spend dry run prove all 4 role pins are present/
   resolvable while `_assert_architecture_coverage` RAISES on a pending lock? Options: (a) a dedicated
   `coverage_dry_run` mode that checks role-pin completeness + family segregation but treats pending
   status as a WARN (not raise) when offline=True and no live calls are made; (b) call
   `_role_pins()` + `validate_role_families()` directly and assert 4 roles without invoking the
   frozen-status raise. Which is safe (does not create a path that lets a real paid smoke run while
   pending)?
3. **CHEAP PROBES:** are the 3 cheap real probes (Serper/S2/DeepSeek, sub-dollar) acceptable inside a
   "no-spend" dry run, or should they stay behind the default-OFF `--with-live-probes` flag so the
   default dry run is truly zero-spend? (The operator's rule is strict; Claude defaults them OFF.)
4. **D8 vs evaluator_gate at the manifest seam:** in the 4-role path, does `apply_d8_release_policy`
   REPLACE `compute_evaluator_gate` for `manifest["release_allowed"]`, or run alongside (D8 as the
   binding gate, evaluator_gate advisory)? Which avoids a double-gate contradiction?
5. Anything that could let this PR cause real spend, or let a hallucination reach a released report,
   that the wiring must prevent.

Hand me APPROVE iff the no-spend boundary, the frozen-lock coverage approach, the lock-promotion
deferral, and the D8-at-the-seam decision are correct and clinically safe.
