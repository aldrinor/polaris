HARD ITERATION CAP: 5 per document. This is iter 1 of the offline-E2E DIFF gate.
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

# Codex DIFF-gate — I-meta-002 PR-9 offline END-TO-END (no-spend capstone)

You APPROVED this e2e design (.codex/I-meta-002-pr9-e2e/codex_design_verdict_iter2.txt: zero P0/P1,
3 P2s). This diff implements it: ONE offline harness proving the whole toolchain runs end-to-end so
canary day adds ONLY real model calls. NO SPEND / NO NETWORK (socket blocked in the test).

## HARD CONSTRAINTS
- NO MONEY / NO NETWORK: zero real LLM calls (generator + 3 verifier roles faked/canned); the test
  BLOCKS sockets so any stray real connection FAILS. Confirm there is no hidden live call.
- NATIVE-ONLY: uses the EXISTING annotated clinical_tirzepatide_t2dm contract (NON-benchmark). The
  harness must NEVER read outputs/dr_benchmark gold rubric/competitor answers. Fixture rubric+ledger
  are SYNTHETIC, labeled, and isolated under tests/fixtures/offline_e2e/.
- Frozen, no drift: claim_audit_scorer.py, runtime lock (NOT promoted). Reuses committed M3a/M3b/M4/M5
  + the external scorer scripts.

## Your 3 design P2s — confirm each is honored in the diff
1. Fixture rubric/ledger clearly labeled synthetic/non-benchmark + isolated from outputs/dr_benchmark.
2. No-network assertion FAIL-CLOSED by blocking socket/connect paths (not merely "fake transport used").
3. BOTH a matching served-metadata fixture (pathB PASS) AND a wrong-model fixture (pathB fail-closed).

## What to verify
- The chain genuinely connects: 4-role seam (fake transport + M3a builder over tirzepatide) ->
  manifest four_role_evaluation with final_verdicts + M5 evaluator_agrees map + four_role_claim_audit.json
  -> M4 pathB served==pinned (PASS on match, fail-closed on wrong-model) -> synthetic fixture
  reconciled ledger + rubric -> score_run -> aggregate_systems.
- Non-vacuous assertions (not a pass that proves nothing): non-empty evaluator_agrees obeying the safe
  rule (FABRICATED canned verdict -> False; VERIFIED+kept -> True); audit json keys == final_verdicts;
  pathB raises on wrong-model; score_run emits a scored ledger; aggregate emits a systems summary;
  socket blocked throughout.
- No frozen/lock drift; lock NOT promoted; no read of outputs/dr_benchmark.

## SMOKE (Claude main-thread; build agent was session-limited mid-report, Claude re-verified)
- offline_e2e test: 7 passed (socket-block + 4-role + FABRICATED-marker + pathB pass/fail-closed +
  scorer + full-chain-under-socket-block).
- pytest tests/dr_benchmark tests/roles tests/architecture -q: 401 passed (was 394 + 7 new). Exit 0.
- verify_lock --consistency: exit 0 (lock NOT promoted). gate_a_dry_run: OVERALL PASS, exit 0.
- tests/polaris_graph not re-run here (e2e adds only scripts/dr_benchmark/offline_e2e.py + test +
  fixtures; the 49 tests/polaris_graph failures are PRE-EXISTING per the M3b stash-comparison).

## DIFF (follows)
