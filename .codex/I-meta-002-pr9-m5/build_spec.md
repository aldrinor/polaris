# M5 build spec — evaluator_agrees per-claim manifest map (I-meta-002 PR-9/M5) — NO SPEND, NO NETWORK

Codex DESIGN review ruled (.codex/I-meta-002-pr9-m5/codex_design_verdict.txt):
- **writeback_point**: in `scripts/run_honest_sweep_r3.py::run_one_query`, IMMEDIATELY after
  `run_four_role_evaluation` returns, at the existing `manifest['four_role_evaluation']` assembly.
  Write a per-claim manifest MAP from `final_verdicts`. **Do NOT mutate or synthesize a
  VerifiedSentence on the sweep path** (run_one_query's own comment warns that would be fake wiring).
- **scope_ruling**: BENCHMARK/sweep path ONLY. Clinical-generator VerifiedSentence writeback is OUT
  OF SCOPE until that path carries both 4-role final_verdicts AND a stable claim_id→VerifiedSentence
  binding. Do NOT touch clinical_generator/strict_verify.py or verified_report.py.
- **safe_rule**: `evaluator_agrees = (verifier_pass is True) AND evaluator_agrees_from_verdict(final_verdict)`,
  where `evaluator_agrees_from_verdict` is exactly `final_verdict == "VERIFIED"`. Missing / unknown /
  PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE => False. NEVER True before a final_verdict exists;
  NEVER True on verifier_pass=False. (§-1.1: a non-VERIFIED verdict must never read as agreed.)

## Locked constraints
- NO SPEND / NO NETWORK: M5 is a pure in-memory manifest enrichment + offline tests.
- Frozen, no drift: claim_audit_scorer.py, runtime lock (NOT promoted), clinical_generator/* (out of
  scope per ruling), M1/M2/M3/M4 committed code.
- snake_case, explicit imports, named constants, no except:pass, no unittest.mock in src/scripts,
  fail-safe (default False, never True without VERIFIED+verifier_pass).

## Scope (acceptance criteria)
1. In `run_one_query` (`scripts/run_honest_sweep_r3.py`), inside the guarded 4-role branch, AFTER
   `run_four_role_evaluation` returns and where `manifest['four_role_evaluation']` is assembled
   (~3196-3215), add a per-claim map:
   `manifest['four_role_evaluation']['evaluator_agrees'] = { claim_id: bool, ... }` built from
   `four_role_result.final_verdicts` using `evaluator_agrees_from_verdict` (import from
   `src.polaris_graph.roles.sweep_integration`), AND guarded so the value is True ONLY when the claim
   is a kept/verified claim (verifier_pass True). On the sweep path the FourRoleClaim set is built by
   the M3a builder from KEPT (is_verified) sentences only, so every claim_id in final_verdicts is a
   kept claim — but encode the rule explicitly/defensively (a claim that is somehow not kept => False),
   and document that invariant. Keys MUST be exactly the claim_ids used in final_verdicts (so the map
   is joinable to four_role_claim_audit.json from M3b).
   - Default/empty-safe: if final_verdicts is empty, the map is `{}` (not an error here — the branch's
     own fail-closed guards already handle empty claim sets upstream).
   - This is ADDITIVE to the existing manifest['four_role_evaluation'] dict; do not remove/rename
     existing keys (release_allowed / held_reasons / coverage_fraction / final_verdicts / gaps / kg_path).
2. Do NOT change release_allowed/status logic (D8 stays the single gate). evaluator_agrees is
   audit/inspector fidelity metadata only.
3. **Tests** (no network): a unit test that, given a final_verdicts dict
   {VERIFIED, PARTIAL, UNSUPPORTED, FABRICATED, UNREACHABLE, and an unknown string}, the produced
   evaluator_agrees map is True ONLY for the VERIFIED claim and False for all others; empty
   final_verdicts -> {} ; and (if reachable without a full live run) that the map lands under
   manifest['four_role_evaluation']['evaluator_agrees'] with claim_id keys matching final_verdicts.
   Prefer testing a small pure helper (extract the map-building into a tiny pure function in
   sweep_integration.py, e.g. `build_evaluator_agrees_map(final_verdicts, kept_claim_ids)`), so the
   §-1.1 safe-rule is unit-tested directly without a live run. The run_one_query call site then just
   invokes that helper.

## Verify
python -c "import scripts.run_honest_sweep_r3" ;
python -m pytest tests/roles tests/dr_benchmark tests/architecture -q ;
python -m scripts.architecture.verify_lock --consistency ;
python -m scripts.dr_benchmark.gate_a_dry_run
Report files changed + results + confirm no network/spend + the exact safe-rule you encoded. Do NOT commit.
