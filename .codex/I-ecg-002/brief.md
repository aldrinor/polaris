# Codex Brief Review — I-ecg-002 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-ecg-002 — Evidence Contract gate enforcement
**Phase:** 1 / **Feature:** ECG
**LOC budget:** 130 net per breakdown. **CHARTER §1 hard cap: 200.**

## Mission

Per breakdown: `src/polaris_graph/evidence_contract/gate.py` — raises if generation runs without a contract. Integration test.

## Substrate (HONEST at HEAD)

- `src/polaris_graph/evidence_contract/schema.py` ships `EvidenceContract` (I-ecg-001).
- The gate's responsibility: given a `(contract, EvidencePool, VerifiedReport)` triple, evaluate whether the report addresses every expected entity + claim + jurisdiction + meets source coverage. Return pass/fail with structured reasons.
- For this Issue, the gate is a PURE function — does NOT integrate into the v6 generation pipeline yet (that integration is a follow-up; the breakdown's "raises if generation without contract" is the IMPORT-time guarantee, demonstrated by an integration test that simulates calling generation without a contract).

## Approach

**Part 1 — `src/polaris_graph/evidence_contract/gate.py`** (NEW, ~85 LOC):
- `class GateVerdict(BaseModel)` with `passed: bool`, `failures: list[str]`, `contract_id: str`, `report_id: str`.
- `evaluate_contract(contract, pool, report) -> GateVerdict`: walks contract.expected_entities, expected_claims, jurisdictions, expected_source_coverage. For each, checks the report covers it. Aggregates failures.
- `assert_generation_has_contract(contract: EvidenceContract | None, *, report_id: str | None = None) -> None`: raises `ValueError("Evidence Contract required: generation cannot proceed without a contract")` if `contract is None`.
- `class ContractRequiredError(Exception)`: structured exception type for gate refusal.

**Part 2 — `tests/polaris_graph/evidence_contract/test_gate.py`** (NEW, ~95 LOC):
- `test_assert_generation_has_contract_passes_with_contract`
- `test_assert_generation_has_contract_raises_without_contract`
- `test_evaluate_contract_passes_when_report_covers_everything`
- `test_evaluate_contract_fails_on_missing_entity_coverage`
- `test_evaluate_contract_fails_on_missing_claim_coverage`
- `test_evaluate_contract_fails_on_insufficient_t1_sources`
- `test_evaluate_contract_aggregates_multiple_failures`
- `test_evaluate_contract_passes_with_zero_min_coverage`

## Coverage rules (binding)

- **Entity coverage:** `expected_entities[*].name` (case-insensitive) appears in some `report.sections[*].verified_sentences[*].sentence_text` of a verified-pass sentence.
- **Claim coverage:** `expected_claims[*].statement` semantic match — for v1, simple substring of any verified sentence works; semantic-match upgrade is I-ecg-002a.
- **Jurisdiction coverage:** for each `expected_claims[*].required_jurisdictions`, at least one cited source's `domain` must match a domain set per jurisdiction (CA: `*.gc.ca`, `*.canada.ca`, `cochrane.org`; US: `fda.gov`, `nih.gov`, `cdc.gov`; EU: `ema.europa.eu`, `efsa.europa.eu`; UK: `nice.org.uk`, `gov.uk`; GLOBAL: `who.int`). Domain mapping is module-level constant.
- **Source coverage:** counts of `pool.sources` by `tier` ≥ `expected_source_coverage.tier_t{1,2,3}_min`.

## Acceptance criteria (binding)

1. `src/polaris_graph/evidence_contract/gate.py` NEW (~85 LOC).
2. `src/polaris_graph/evidence_contract/__init__.py` EDIT (~5 LOC) — re-export gate symbols.
3. `tests/polaris_graph/evidence_contract/test_gate.py` NEW (~95 LOC).

## Planned diff shape

```
src/polaris_graph/evidence_contract/__init__.py        EDIT +5
src/polaris_graph/evidence_contract/gate.py            NEW +85
tests/polaris_graph/evidence_contract/test_gate.py     NEW +95
```

LOC: +185 net. Over breakdown 130 budget by 55; under CHARTER §1 200-cap by 15.

## Out of scope

- Integration into v6 generation pipeline (gate gets called inside generator) → I-ecg-002b follow-up.
- Semantic-match for claim coverage (LLM judge) → I-ecg-002a follow-up.
- API route for contract-bound generation → I-ecg-003-related.

## Risks for Codex Red-Team

1. **Domain mapping is a v1 heuristic.** A claim citing `cochrane.org` (a UK-published Cochrane review) maps to CA in our table. This is intentional v1 simplification; I-ecg-002b can refine.
2. **Substring claim match is weak.** A report stating "aspirin reduces headache" matches the claim "aspirin reduces headache pain" via case-insensitive substring of either direction. Acceptable for v1; semantic upgrade is named.
3. **`assert_generation_has_contract`** is the MUST RAISE per breakdown. Test asserts `pytest.raises(ContractRequiredError)`.
4. **Pool source tier counting** uses the existing `Source.tier` enum (T1/T2/T3) directly.
5. **CHARTER §1 LOC cap.** 185 net.
6. **No new package dep.**
7. **§9.4 compliance.** No mocks. No magic numbers (DOMAIN_MAP is module-level constant). No `try: pass`. No TODO/FIXME.

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
