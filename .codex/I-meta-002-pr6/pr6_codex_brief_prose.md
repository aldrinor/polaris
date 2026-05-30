# Codex DIFF-gate — I-meta-002 sub-PR-6: sweep 4-role wiring + Gate-A no-spend dry run (capstone)

> **THIS IS A DIFF REVIEW.** The implementation now exists; review the diff at `## DIFF` below
> against the APPROVE'd brief Scope + the 6 Codex P2 directives. The brief was APPROVE'd (iter 1).

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (return EXACTLY this YAML, last `verdict:` line is the binding one)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## NO-SPEND / NO REAL NETWORK (binding context for this review)
- This PR makes **NO MONEY and NO real network calls in the default/dry-run path.** The 4-role
  sweep branch is exercised ONLY via an INJECTED `RoleTransport`; every test injects a mock
  transport. The live 4-role sweep (real Mirror/Sentinel/Judge on rented GPUs) is **Gate-B**,
  AFTER the operator loads credit — explicitly out of scope here.
- The runtime lock (`config/architecture/polaris_runtime_lock.yaml`) is **intentionally NOT
  promoted** to `locked` in this PR. Promotion is the **operator's spend gate** — it un-freezes
  paid smokes and is performed AFTER a green dry run + dual §-1.1 line-by-line review. The lock
  stays `codex_approved_pending_operator_signature`; the architecture-coverage gate still RAISES
  while pending.
- The frozen `claim_audit_scorer.py`, the runtime lock, and the canonical pipeline
  (`polaris_pipeline_canonical.md`) **must not drift.** This PR does not touch them; confirm the
  diff introduces no implicit drift.

## EMPHASIS — the safety/no-spend invariants this diff MUST hold (verify each against the DIFF)
1. **D8 is the SINGLE binding `manifest.release_allowed` gate.** In the 4-role branch the legacy
   `evaluator_gate` must be DEMOTED to advisory metadata only (`evaluator_gate_advisory`); D8
   (`apply_d8_release_policy`) owns BOTH `manifest['release_allowed']` AND `manifest['status']`,
   so the two cannot contradict (no double-gate). Verify there is no path where evaluator_gate
   and D8 both write the headline release decision.
2. **D8 inputs are FAIL-CLOSED.** No synthesized claim_ids (each claim carries its existing id;
   blank/duplicate id raises `ValueError`). No empty/vacuous D8 pass (empty claim set OR empty
   canonical required-element set raises before any pipeline call). Coverage/S0 denominators come
   from the CANONICAL required elements (`coverage_ledger.required_element_ids`), NOT from which
   claims happened to survive — a dropped claim lowers coverage, it cannot dodge the gate.
3. **NO default real `RoleTransport`.** The 4-role branch activates ONLY when an explicit
   transport is INJECTED **AND** `PG_FOUR_ROLE_MODE` is on. There must be NO default real
   transport construction anywhere in the sweep or the Gate-A harness. The default path is
   byte-unchanged (legacy evaluator gate). Confirm.
4. **Gate-A coverage check does NOT bypass `_assert_architecture_coverage`.** Per P2 option (b),
   `check_frozen_lock_coverage` calls `_role_pins()` + `validate_role_families()` DIRECTLY and
   asserts 4 roles + distinct families — it must NOT add a bypass mode to
   `_assert_architecture_coverage` that a live paid smoke could reuse while the lock is pending.
5. **Cheap probes default-OFF.** Serper/S2/DeepSeek probes are gated behind `--with-live-probes`,
   default OFF, ADVISORY only, NEVER part of the PASS criteria. Confirm they cannot flip
   `overall_pass`.
6. **A Sentinel UNGROUNDED can NEVER yield a released VERIFIED claim.** Even when the Judge says
   VERIFIED, a Sentinel-UNGROUNDED claim must be downgraded (composed final verdict ≠ VERIFIED),
   credit no coverage, and therefore cannot make `release_allowed` True. This is the lethal
   clinical-safety property. Verify it in the code path AND in the test
   (`test_sentinel_ungrounded_claim_cannot_release`).

---

## Scope of sub-PR-6 (APPROVE'd acceptance criteria)
1. **Sweep wiring (no-spend, transport-injected)** — at the `run_honest_sweep_r3.py` evaluator
   seam, add a 4-role path that, FOR EACH kept verified claim, runs `run_claim_pipeline` over an
   INJECTED `RoleTransport`, collects D8ClaimRows, applies `apply_d8_release_policy`, sets manifest
   `release_allowed`/status from the D8 decision, populates `VerifiedSentence.evaluator_agrees`
   from the final_verdict, fixes the judge/mirror/sentinel role tags, and writes the snowball KG at
   run end. **Guarded behind an explicit mode/flag** so the DEFAULT/dry-run path does NOT make real
   role calls (the 4-role path activates only when a real transport is supplied = Gate-B). The
   legacy evaluator path remains available behind the flag so nothing breaks pre-Gate-B.
   Unit/integration tested with a MOCK transport (no network).
2. **Gate-A no-spend dry-run harness** (`scripts/dr_benchmark/gate_a_dry_run.py`): runs the
   no-spend checks and emits a machine-readable PASS/FAIL + artifacts for the dual §-1.1 review:
   (a) pytest tests/roles tests/architecture tests/dr_benchmark (serialized);
   (b) `verify_lock --consistency` exit 0;
   (c) `preflight`/coverage proving all 4 role pins resolve via the frozen-lock coverage check;
   (d) per-role contract fixtures (Sentinel yes=UNGROUNDED lethal-polarity; Judge 5-enum; Mirror
       two-pass) exercised via the mock transport;
   the 3 cheap real probes (Serper/S2/DeepSeek) are GATED behind an explicit `--with-live-probes`
   flag, default OFF, so the dry run is pure-offline/no-spend unless the operator opts in. The
   harness writes `outputs/gate_a/dry_run_report.json` + a human-readable summary.
3. **NO lock promotion**: leave status `codex_approved_pending_operator_signature`; the dry run
   does not require `locked`. Document that flipping to `locked` (un-freezes paid smokes) is the
   operator's spend-authorization step, performed AFTER the green dry run + dual review.
4. Hygiene: snake_case, explicit imports, named constants, no `except: pass`, no unittest.mock in
   `src/`, no real network in the default dry-run path, no `datetime.now()` in library code.

## The 6 Codex P2 directives (from the brief APPROVE — the diff MUST satisfy all 6)
- **Q1 LOCK PROMOTION:** do NOT promote in this PR. Keep status
  `codex_approved_pending_operator_signature`; promotion to `locked` is the operator
  spend-authorization step after green dry run + dual line-by-line review.
- **Q2 FROZEN-LOCK COVERAGE:** choose option (b). For Gate-A, call the lock-sourced pin builder /
  role-pin completeness logic directly and assert generator, mirror, sentinel, judge plus family
  segregation. Do not add a bypass mode to `_assert_architecture_coverage` that could be reused by
  a live paid smoke while pending.
- **Q3 CHEAP PROBES:** keep Serper/S2/DeepSeek probes behind default-OFF `--with-live-probes`.
  They are not part of the no-spend dry-run PASS criteria.
- **Q4 D8 SEAM:** in the 4-role path, D8 is the single binding `manifest.release_allowed` gate.
  Legacy `evaluator_gate` may be emitted as advisory metadata only; do not let two independent
  gates write the headline release decision.
- **Implementation guardrail:** the D8 input set must be fail-closed: no synthesized claim IDs,
  no empty/vacuous D8 pass, and coverage/S0 denominators must come from canonical required
  elements rather than only the surviving kept claims.
- **Implementation guardrail:** no default real `RoleTransport` construction in Gate-A. Mock/
  injected transport only; live transport requires an explicit Gate-B mode after lock promotion.

## Smoke results (offline, no-spend, serialized per §8.4)
```
OVERALL: ALL THREE PASSED

[1] pytest tests/roles tests/architecture tests/dr_benchmark -q
    PASS — 293 passed, 0 failed, 0 errors, 0 skipped — 4.51s — rc 0

[2] python -m scripts.architecture.verify_lock --consistency
    PASS — rc 0 — families registered, family_policy holds, code defaults match lock,
    canonical_pin includes lock file

[3] python -m scripts.dr_benchmark.gate_a_dry_run  (default, no live probes)
    OVERALL PASS (no-spend, offline) — rc 0
      [PASS] pytest_suites: all 3 suites passed (serialized)
      [PASS] lock_consistency: Consistency OK
      [PASS] frozen_lock_coverage: 4 roles pinned + all-distinct families
             {generator: deepseek, mirror: cohere, sentinel: ibm-granite, judge: qwen}
      [PASS] role_contracts: Sentinel yes=UNGROUNDED, Judge off-enum raises,
             Mirror two-pass binding holds
    Harness note: Gate-A PASS does NOT authorize spend. Lock promotion to status: locked is the
    operator's separate spend gate. JSON report written to outputs/gate_a/dry_run_report.json.

No tracebacks. No errors. No bluffing.
```

## Files in this diff
- `scripts/dr_benchmark/gate_a_dry_run.py` (NEW, 374 lines) — Gate-A no-spend harness.
- `scripts/run_honest_sweep_r3.py` (MODIFIED) — the guarded 4-role evaluator seam in
  `run_one_query` (default OFF), status map additions, advisory demotion of `evaluator_gate`.
- `src/polaris_graph/roles/sweep_integration.py` (NEW, 269 lines) — thin seam:
  `run_four_role_evaluation` driving per-claim pipeline → single binding D8 → snowball KG.
- `tests/dr_benchmark/test_gate_a_dry_run.py` (NEW, 108 lines) — offline harness tests.
- `tests/roles/test_sweep_integration.py` (NEW, 220 lines) — mock-transport 4-role tests incl.
  the Sentinel-UNGROUNDED-cannot-release clinical-safety property.

## DIFF
