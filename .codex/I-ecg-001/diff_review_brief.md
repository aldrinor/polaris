# Codex Diff Review — I-ecg-001 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-ecg-001 — Evidence Contract schema
**Brief:** APPROVED iter 2 (0/0/0P1, 2 P2 bookkeeping)
**Canonical-diff-sha256:** `c221bff21eba8158182b123ff277bb96ff58c181e771e415a7851fbb263a3322`
**LOC:** 246 net (46 over CHARTER §1 200-cap; LOC exemption requested below)
**Tests:** 11/11 PASS

## Files

```
src/polaris_graph/evidence_contract/__init__.py        NEW +24
src/polaris_graph/evidence_contract/schema.py          NEW +108
tests/polaris_graph/evidence_contract/__init__.py      NEW +0
tests/polaris_graph/evidence_contract/test_schema.py   NEW +114
```

## What changed

**`schema.py`:** 5 Pydantic models + 1 Enum + 1 Literal alias. `EvidenceContract._internal_consistency` model_validator covers all 4 invariants (unique entity names, unique claim_ids, claim entity refs resolve, claim jurisdictions ⊆ contract jurisdictions). Module docstring explicitly distinguishes from `polaris_v6.schemas.evidence_contract` per Codex iter-1 P2 #2.

**`__init__.py`:** Re-exports the 6 public types.

**`test_schema.py`:** 11 tests:
- `test_minimal_valid_contract` / `test_jurisdiction_enum_values` / `test_expected_source_coverage_zero_min_allowed` (3 happy)
- `test_undeclared_entity_in_claim_rejected` (cross-ref)
- `test_empty_expected_entities_rejected` / `test_empty_expected_claims_rejected` / `test_contract_version_pinned` (3 schema)
- `test_contract_round_trip_json` (serialization)
- `test_duplicate_entity_name_rejected` / `test_duplicate_claim_id_rejected` / `test_claim_jurisdiction_must_be_in_contract_jurisdictions` (3 NEW per iter-2 P1 resolution)

## LOC exemption requested

CHARTER §1 200-cap exceeded by 46. Test coverage of 11 distinct schema validation paths drives the overrun (114 LOC for 11 tests = ~10 LOC/test, tight). Codex iter-2 P1 added 3 mandatory new validation paths (duplicate-name, duplicate-id, jurisdiction-subset) that pushed test LOC from ~75 to 114. Exemption analogous to I-f15-003/I-f15-004 — binding cross-validation coverage is artifact-inseparable from the schema.

## Codex iter-2 P2 disposition

- P2 #1 (test count bookkeeping inconsistent): RESOLVED — 11 tests shipped (the binding count after iter-2 P1 added 3).
- P2 #2 (LOC accounting inconsistent): noted; final patch is 246 LOC. Exemption requested above.

## Risks for Codex Red-Team

1. **Module collision with `polaris_v6.schemas.evidence_contract`.** Resolved via module docstring; both modules have `class EvidenceContract` but represent different concepts (pre-run expectation vs post-run artifact).
2. **`_internal_consistency` runs ALL 4 invariants in order.** First failure raises; later invariants don't run. Tests cover each independently.
3. **Jurisdiction enum vs agency codes (FDA/EMA/etc.).** I-ecg-002 owns the agency→jurisdiction mapping (documented in module docstring).
4. **`Pydantic v2 model_validator(mode="after")`.** Same idiom used elsewhere (verified_report.py:71-80, 141-162).
5. **§9.4 compliance.** No mocks. No magic numbers (limits like max_length=50 are Pydantic Field constraints, idiomatic). No `try: pass`. No TODO/FIXME.
6. **No sovereignty surface.** Pure type module.
7. **CHARTER §1 LOC cap.** 246 net. Exemption requested.
8. **No new package dep.**

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
