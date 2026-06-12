# Codex DIFF gate — I-perm-021 (#1213): RequiredEntityLedger (narrow: inclusion + disclosure, WIRED LIVE)

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1/2. No drip-feeding.
- Reserve P0/P1 for real execution risks; cosmetic = P3/P2.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; no iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## ITER-1 P1 RESOLUTION — verify this fix is correct (the crux of iter 2)
Your iter-1 P1: `run_honest_sweep_r3.py` unioned `covered_element_ids` from EVERY audit row, but
`four_role_claim_audit.json` is the **pre-D8** audit map (written by `native_gate_b_inputs.py`).
D8 only credits coverage after `result.final_verdict == "VERIFIED"` (`sweep_integration.py`). So an
unfiltered union could mark an entity covered when the 4-role seam DOWNGRADED its covering claim —
suppressing a real Coverage-gaps disclosure (over-claiming completeness = the lethal direction).

**Fix applied (verify in the patch):**
1. NEW `required_entity_ledger.verified_covered_ids(audit_map, final_verdicts)` — returns the union
   of `covered_element_ids` ONLY for claim_ids where `final_verdicts.get(claim_id) == "VERIFIED"`.
   Empty/None `final_verdicts` (seam-timeout path) → empty set → every required entity disclosed as a
   gap (fail-safe OVER-disclose, never under-disclose).
2. Orchestrator now reads
   `_re_final_verdicts = (manifest.get("four_role_evaluation") or {}).get("final_verdicts") or {}`
   and calls `_verified_covered_ids(_re_audit, _re_final_verdicts)` instead of the raw union.
3. Two NEW tests: `test_verified_covered_ids_excludes_downgraded_claims` (a row with
   `covered_element_ids` but final verdict UNSUPPORTED/PARTIAL is NOT credited → entity stays
   GAP_DISCLOSED) and `test_verified_covered_ids_empty_verdicts_credits_nothing` (empty/None →
   set()).

**Verify:** (a) the filter key matches what the seam actually writes — confirm
`manifest["four_role_evaluation"]["final_verdicts"]` is the right source for the post-D8 VERIFIED set,
and the claim_id keys in `four_role_claim_audit.json` align 1:1 with the keys in `final_verdicts`.
(b) The fail-safe direction is correct (missing verdicts → MORE disclosure, never less). (c) No path
remains where a downgraded claim credits its entity.

## The diff (`.codex/I-perm-021/codex_diff.patch`, staged, +424). Read these EXACT files:
- NEW `src/polaris_graph/generator/required_entity_ledger.py` — pure ledger + disclosure +
  `verified_covered_ids` filter.
- NEW `tests/polaris_graph/generator/test_required_entity_ledger_iperm021.py` — 8 tests (6 + 2 new).
- EDIT `scripts/run_honest_sweep_r3.py` — the LIVE wiring block (after the V30 disclosure append,
  ~line 7609): reads `four_role_claim_audit.json` + `manifest["four_role_evaluation"]["final_verdicts"]`,
  builds the ledger via the VERIFIED-filtered covered set, writes `manifest["required_entity_coverage"]`,
  appends the "Coverage gaps" section to report.md. Fail-soft try/except.
- EDIT `scripts/dr_benchmark/run_gate_b.py` — slate `PG_REQUIRED_ENTITY_LEDGER=1` + force-on.

This implements the Codex design-gate APPROVE (`.codex/I-perm-021/codex_design_verdict.txt`):
report-level, PHASE B only (inclusion + disclosure; NO re-generation/recovery round — deferred
follow-up), explicit "Coverage gaps" body section + manifest evidence_gaps, native-template-only,
default-OFF byte-identical, url_pattern content-mismatch note.

## §-1.1 / faithfulness — red-team this (the crux)
1. **NO new coverage credit.** A required entity is VERIFIED in the ledger ONLY if its id is in the
   VERIFIED-filtered covered set (see P1 resolution). The ledger NEVER sets a verdict, NEVER
   re-implements coverage matching, NEVER adds a credit path. Confirm
   `manifest["required_entity_coverage"]` cannot change the D8 release decision (written AFTER the
   seam's release decision; not read by any gate).
2. **Gaps disclosed, NEVER filled.** A GAP_DISCLOSED slot becomes a deterministic templated
   "could not verify X" sentence (no LLM, no fabricated citation). Confirm no path fills a gap with
   an unsupported claim.
3. **No gate touched.** strict_verify / the 4-role evaluator / D8 / the report redaction
   reconciliation are unchanged. The Coverage gaps section is appended AFTER redaction + V30
   disclosure (reflects the final shipped body), ADDITIVE disclosure (not a body claim), not subject
   to the redaction pass.
4. **Default-OFF byte-identical.** `PG_REQUIRED_ENTITY_LEDGER` read at call time; OFF → whole block
   skipped → report.md + manifest byte-identical. Confirm.
5. **Fail-soft.** The block is wrapped try/except → a failure logs + continues, NEVER aborts the run.
   Confirm it cannot crash a paid run.
6. **Native-template-only (contamination lock).** Required entities come from
   `load_required_entities(_template, q["slug"])`; the block NEVER reads `outputs/dr_benchmark/`.
   Confirm.

## Wiring liveness (operator's explicit ask: "make sure all fixes are wired")
- The block runs in the per-question success path AFTER the 4-role seam writes
  `four_role_claim_audit.json` AND `manifest["four_role_evaluation"]["final_verdicts"]`. On a non-4-role
  path both are absent → graceful no-op (not an abort). Confirm.
- Slate force-on so an operator =0 cannot drop it. NOT preflight-required (fail-soft no-op when audit
  absent, never fail-closed).
- Verify `_template` and `q["slug"]` are in scope at the insertion point (the adjacent V30 block uses
  both).

## Honest scope
PHASE B only (inclusion + disclosure). The Phase-A gap-driven retrieval feed and the post-verify
gap-RECOVERY re-generation are deferred follow-ups per the Codex design ruling. Coverage LIFT mostly
comes from #1204 retrieval breadth; this ledger is the honest audit/disclosure surface. Build: 8
module tests pass; the orchestrator compiles.
