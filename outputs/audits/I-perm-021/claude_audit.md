# Claude architect audit — I-perm-021 (#1213): RequiredEntityLedger (inclusion + honest disclosure)

## Scope reviewed
- NEW `src/polaris_graph/generator/required_entity_ledger.py` (pure ledger + disclosure + the
  `verified_covered_ids` post-D8 filter).
- NEW `tests/polaris_graph/generator/test_required_entity_ledger_iperm021.py` (8 tests).
- EDIT `scripts/run_honest_sweep_r3.py` (live wiring block, ~L7609, fail-soft).
- EDIT `scripts/dr_benchmark/run_gate_b.py` (slate `PG_REQUIRED_ENTITY_LEDGER=1`).

## §-1.1 architectural verdict: SAFE
This module assigns NO verdicts and adds NO coverage credit. A required entity is VERIFIED only when
its id is in the VERIFIED-filtered covered set = ⋃ `covered_element_ids` over claims whose 4-role
FINAL verdict == "VERIFIED". The ledger never re-implements coverage matching, never touches
strict_verify / the 4-role evaluator / D8 / the release decision. A gap is a deterministic templated
"could not verify X" disclosure — it NEVER fills the gap with an unsupported claim. The direction of
error is fail-safe: missing verdicts → MORE disclosure, never less (no over-claiming of completeness,
the lethal direction).

## Codex P1 (iter-1) resolution — verified
Codex caught that `four_role_claim_audit.json.covered_element_ids` is the PRE-D8 builder audit map; an
unfiltered union could credit an entity whose covering claim the seam DOWNGRADED, suppressing a real
Coverage-gaps disclosure. Resolved by `verified_covered_ids(audit_map, final_verdicts)` filtering
through `manifest["four_role_evaluation"]["final_verdicts"][claim_id] == "VERIFIED"`; empty/None →
empty set. Two tests cover it. Codex diff-gate iter2 = APPROVE (0 P0/P1).

## Codex P2 (iter-2, non-blocking) — accepted
On a seam timeout/error the audit sidecar is commonly absent, so the whole block no-ops (rather than
disclosing every entity). Not a release risk: those paths are held/fail-closed (a held run ships no
report, so there is no completeness over-claim). Successful audit-present Gate-B runs use the correct
VERIFIED-only filter. Accepted as a documented edge, not a blocker.

## Default-OFF + fail-soft + contamination lock — verified
`PG_REQUIRED_ENTITY_LEDGER` read at CALL TIME (default OFF → byte-identical). Block wrapped try/except
(cannot abort a paid run). Required entities come only from the native scope template
(`load_required_entities(_template, q["slug"])`), never `outputs/dr_benchmark/`.

## Honest scope
PHASE B only (inclusion + disclosure). The Phase-A gap-driven retrieval feed and the post-verify
gap-RECOVERY re-generation are deferred follow-ups. Coverage LIFT mostly comes from #1204 retrieval
breadth; this ledger is the honest audit/disclosure surface.

## Build evidence
8 module tests pass; orchestrator compiles; behavioral glue smoke confirmed (verified entities
excluded from gaps, downgraded entities disclosed, url_pattern note present).

VERDICT: APPROVE (architect) — matches Codex diff-gate iter2 APPROVE.
