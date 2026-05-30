# PR-11b build spec — robust offline e2e proving all 5 benchmark questions route to their native contracts — NO SPEND

PR-11 (commit d4a9b587) registered the 5 benchmark questions in SWEEP_QUERIES so q["slug"]/q["domain"]
route to their frozen PR-10 contracts. PR-11b ROBUSTLY proves, end-to-end and OFFLINE, that each of the
5 questions actually picks up ITS OWN native required-element contract through the 4-role seam — the
operator's "truly, robustly test e2e, confirm it is wired, functional and good to launch" gate.

## Locked constraints
- NO MONEY / NO NETWORK: extend the existing offline harness; drive the 4-role seam with an INJECTED
  FAKE RoleTransport (reuse the proven pattern in tests/dr_benchmark/test_offline_e2e.py +
  scripts/dr_benchmark/offline_e2e.py). Socket BLOCKED for the whole run (a stray real connection fails
  the test). No live generator, no verifier network, nothing deployed.
- Frozen, no drift: claim_audit_scorer.py, runtime lock (do NOT promote), the 5 PR-10 contracts.
- snake_case; explicit imports; no except:pass; no unittest.mock in src/scripts (stub in tests); fail-closed.

## Goal (per-question proof, all 5)
For EACH of the 5 wired benchmark questions (drb_75_metal_ions_cvd→clinical, drb_76_gut_microbiota_crc→
clinical, drb_78_parkinsons_dbs→clinical, drb_72_ai_labor→workforce, drb_90_adas_liability→policy), prove
OFFLINE:
1. **Routing**: the SWEEP_QUERIES entry's q["domain"] loads the template that holds q["slug"]'s contract
   (load_scope_template(q["domain"]) then native_gate_b_inputs.load_required_entities(template, q["slug"])
   resolves NON-EMPTY).
2. **Right denominator (the robustness core)**: the M3a builder, given THAT question, builds its 4-role
   inputs from THAT slug's required_entities — assert the resolved required_element_ids are EXACTLY that
   slug's contract entity ids (the right COUNT per slug: drb_75=6, drb_76=5, drb_78=5, drb_72=7,
   drb_90=6) and NOT another question's. (Cross-check: drb_75's denominator != drb_76's, etc. — prove no
   cross-contamination of contracts between questions.)
3. **Full chain offline**: drive the 4-role seam (run_four_role_seam / the four_role_input_builder path)
   with an INJECTED FAKE RoleTransport over that question's contract → manifest['four_role_evaluation']
   with final_verdicts + the M5 evaluator_agrees map + four_role_claim_audit.json; M4 pathB served==pinned
   over a FIXTURE served-metadata → PASS (and a wrong-model fixture → fail-closed); then the external
   scorer leg over SYNTHETIC fixtures (reconciled ledger + rubric) → score_run → aggregate_systems.
4. **No network**: socket blocked for the whole run; a real connection FAILS the test.

## Build
Extend scripts/dr_benchmark/offline_e2e.py + tests/dr_benchmark/test_offline_e2e.py (and
tests/fixtures/offline_e2e/ if needed) so the harness PARAMETERIZES over all 5 benchmark slugs (today
it runs the tirzepatide non-benchmark contract; ADD the 5 benchmark questions driven from their
SWEEP_QUERIES registration, looked up by slug/domain — do NOT hardcode the contract; resolve it through
the same load_scope_template(q["domain"]) path production uses, to prove the WIRING).
- A new test e.g. test_all_5_benchmark_questions_route_to_their_own_contract: parameterized over the 5
  slugs; for each, assert routing (1), right-denominator (2) incl. the cross-question distinctness, and
  the full chain (3) flows offline; plus the existing socket-block (4).
- Keep the existing tirzepatide e2e tests passing.
- The canned FAKE transport's role responses can be generic (the point is the CONTRACT/denominator
  wiring per question, not the verifier content); use a small fixture report/evidence per question OR
  reuse a shared canned report keyed so each question's claims map into its own contract entities.
  Document any simplification honestly.

## Verify
python -c "import scripts.dr_benchmark.offline_e2e" ;
python -m pytest tests/dr_benchmark/test_offline_e2e.py -v ;
python -m pytest tests/dr_benchmark tests/roles tests/architecture -q ;
python -m scripts.architecture.verify_lock --consistency ;
python -m scripts.dr_benchmark.gate_a_dry_run
Report: per-question routing + denominator (entity ids/count) + chain result, confirm socket-blocked
no-network + no spend, and that each question's denominator is distinct (no cross-contamination). Do NOT commit.
