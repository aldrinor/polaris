# Claude architect audit — I-perm-009 (#1203) behavioral replay/proof harness (Wave 0)

## What landed
Five test-only modules under `tests/polaris_graph/replay/` (478 LOC, zero production code):
`saved_run_loader.py`, `d8_replay_harness.py`, `cited_span_audit.py`, `test_drb76_baseline.py`,
`__init__.py`. An offline, deterministic replay of the D8 release decision + the §-1.1
zero-fabrication invariant over the committed saved run `outputs/audits/beatboth8/drb_76/`.

## Why it is the right Wave-0 foundation
The operator's hard lesson (2026-06-06/09): "gates green ≠ faithful," "audit content not status,"
"prove behavior before spend." Every prior fix→re-run→discover loop wasted a paid run. This harness
is the structural answer: it replays the REAL release policy (`apply_d8_release_policy`, imported, not
copied) over frozen real evidence and asserts the exact saved decision — so a fix is proven on real
data before any spend, and any regression is caught offline.

## Architecture decisions
1. **Reuse, don't re-implement.** The harness imports the production policy + the production
   required-entity/S0 derivation helpers (`load_required_entities`, `validate_entity_severity`).
   Zero logic drift: the BASELINE-LOCK reproduces the saved `held_reasons` bit-for-bit, which proves
   the reconstruction of INPUTS is faithful (if it weren't, the lock would fail loudly).
2. **Dual-assert against hard-code AND live manifest.** Each baseline assert compares the replay to
   both a written constant AND `saved_run.saved_*` (read live from manifest.json), so a stale constant
   cannot silently mask drift.
3. **§-1.1 invariant is content, not metadata.** `audit_cited_spans` checks every numeric in a claim
   appears verbatim in its cited span — a faithfulness check, never a banned keyword/count proxy.
   0 findings on drb_76 mechanically re-confirms `DRB76_FORENSIC.md`.
4. **Honest sim vs honest xfail.** The I-perm-002 fix logic is PROVEN as a clearly-labelled simulation
   (corpus-wide satisfaction clears the false `contraindications` hold, 0.40→0.60, other holds remain).
   The production flip is a strict-xfail ledger entry that I will RE-POINT at the production
   `build_native_gate_b_inputs` replay when I-perm-002 lands. No fake "already fixed" claims.

## Honest limitations (REPLAYABLE-OFFLINE vs RE-RUN-REQUIRED, per blueprint §5)
- The full production `build_native_gate_b_inputs` replay (reconstructing `multi` + `evidence_lookup`
  from `evidence_pool.json`) is NOT in this skeleton — it lands with I-perm-002 (#1196), which owns
  that builder. The Wave-0 harness proves the POLICY replay + the fix LOGIC, not the production binding.
- The `corpus_satisfaction` sim credits via `evidence_ids ∩ required_element_ids`. This is sound for
  drb_76 (the VERIFIED Safety claims genuinely state the contraindication), but the production
  I-perm-002 MUST add the R6 same-substance/risk-population guard before crediting a SAFETY category
  cross-document — the sim is a logic proof, not the safety-guarded production rule.
- Selection / four-role-coverage-rises / extraction asserts are NOT in this skeleton (RE-RUN-REQUIRED
  per blueprint; added under I-perm-003/004/007 with their own fixtures).

## Risk
Lowest-risk possible change class: additive test-only, cannot alter any pipeline behavior. The one
real review question (handed to Codex): does the numeric invariant have a false-negative path that
would let a real fabrication ship? That is the clinical-safety load-bearing check.

## Verdict
Foundationally sound and honest about scope. Smoke: `pytest tests/polaris_graph/replay/` → 6 passed,
1 xfailed. Submitted to Codex as the only gate.
