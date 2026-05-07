# Codex Brief Review — I-ecg-001 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-ecg-001 — Evidence Contract schema
**Phase:** 1 / **Feature:** ECG (Evidence Contract Gate)
**LOC budget:** 180 net per breakdown. **CHARTER §1 hard cap: 200.**

## Iter-1 verdict consumed

- P1 (internal-consistency gaps): RESOLVED iter 2 — `_entity_refs_resolve` validator extended to ALSO check (a) unique entity names, (b) unique claim_ids, (c) claim.required_jurisdictions ⊆ contract.jurisdictions. Three new tests added (`test_duplicate_entity_name_rejected`, `test_duplicate_claim_id_rejected`, `test_claim_jurisdiction_must_be_in_contract_jurisdictions`).
- P2 #1 (jurisdiction enum vs agency codes): RESOLVED iter 2 — module docstring + brief explicitly state I-ecg-002 owns the agency-code mapping (FDA→US, EMA→EU, NICE→UK, HC→CA, MHRA→UK). This Issue ships geographic enum only.
- P2 #2 (collision with polaris_v6 EvidenceContract): RESOLVED iter 2 — module docstring explicitly distinguishes: `polaris_v6.schemas.evidence_contract.EvidenceContract` is the post-run artifact (run output), while `polaris_graph.evidence_contract.schema.EvidenceContract` is the pre-run expectation contract (operator-declared INPUT to gate). Different concepts; same name acceptable since import paths disambiguate.
- P2 #3 (LOC near cap): RESOLVED iter 2 — trimmed brief plan; final estimate 185 LOC (still under 200 by 15).

## Mission

Per breakdown: `src/polaris_graph/evidence_contract/schema.py` — entities, claims, jurisdictions, expected sources. Pydantic schema + tests.

## Context

The Evidence Contract Gate (ECG) is one of the v6.2 §Phase 1 deliverables (per `docs/carney_delivery_plan_v6_2.md:38, 282-283`). It is "canonical JSON schema for run artifact" — a binding contract that declares, BEFORE generation runs, what entities + claims + jurisdictions + source-coverage the operator expects the report to address. Generation that produces output diverging from the contract is gated/refused (I-ecg-002).

This Issue ships ONLY the schema. Gate enforcement is I-ecg-002.

## Substrate (HONEST at HEAD)

- No `src/polaris_graph/evidence_contract/` directory exists.
- `src/polaris_graph/sovereignty/classification.py` provides `DataClassification` enum (PUBLIC_SYNTHETIC / CAN_REAL / PRIVATE / CLIENT / UNKNOWN) — same Pydantic-pattern reference for the new schema.
- `src/polaris_graph/scope/scope_decision.py` and `src/polaris_graph/retrieval2/evidence_pool.py` are reference Pydantic schemas — same conventions.

## Approach

**Part 1 — `src/polaris_graph/evidence_contract/__init__.py`** (NEW, ~5 LOC):
- Re-export the public types from schema.py.

**Part 2 — `src/polaris_graph/evidence_contract/schema.py`** (NEW, ~115 LOC):

Five Pydantic models + 1 Enum:

```python
class Jurisdiction(str, Enum):
    CA = "CA"
    US = "US"
    EU = "EU"
    UK = "UK"
    GLOBAL = "GLOBAL"


class ExpectedEntity(BaseModel):
    """A named entity (drug, condition, intervention) the report MUST address."""
    name: str = Field(min_length=1, max_length=200)
    aliases: list[str] = Field(default_factory=list, max_length=20)
    entity_type: Literal["drug", "condition", "intervention", "population", "outcome"]


class ExpectedClaim(BaseModel):
    """A claim the report MUST make a verdict on (efficacy, safety, etc.)."""
    claim_id: str = Field(min_length=1, max_length=100)
    statement: str = Field(min_length=1, max_length=1000)
    expected_entities: list[str] = Field(min_length=1, max_length=20)  # entity names
    required_jurisdictions: list[Jurisdiction] = Field(min_length=1)


class ExpectedSourceCoverage(BaseModel):
    """Minimum source counts per tier the report MUST cite."""
    tier_t1_min: int = Field(ge=0, le=100)
    tier_t2_min: int = Field(ge=0, le=100)
    tier_t3_min: int = Field(ge=0, le=100)


class EvidenceContract(BaseModel):
    """Top-level contract bound to a research question, reviewed BEFORE generation runs."""
    contract_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    contract_version: Literal["1.0"] = "1.0"
    research_question: str = Field(min_length=1, max_length=2000)
    expected_entities: list[ExpectedEntity] = Field(min_length=1, max_length=50)
    expected_claims: list[ExpectedClaim] = Field(min_length=1, max_length=50)
    expected_source_coverage: ExpectedSourceCoverage
    jurisdictions: list[Jurisdiction] = Field(min_length=1, max_length=10)
    created_at_utc: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    created_by: str = Field(min_length=1, max_length=200)

    @model_validator(mode="after")
    def _internal_consistency(self) -> "EvidenceContract":
        """All cross-references resolve; no duplicates; jurisdictions subset.

        4 invariants: (a) entity names unique, (b) claim_ids unique,
        (c) every claim.expected_entities reference a declared entity,
        (d) every claim.required_jurisdictions ∈ contract.jurisdictions.
        """
        names = [e.name for e in self.expected_entities]
        if len(set(names)) != len(names):
            raise ValueError(f"duplicate entity name(s): {sorted({n for n in names if names.count(n) > 1})}")
        ids = [c.claim_id for c in self.expected_claims]
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate claim_id(s): {sorted({i for i in ids if ids.count(i) > 1})}")
        declared = set(names)
        contract_jurs = set(self.jurisdictions)
        for claim in self.expected_claims:
            for ref in claim.expected_entities:
                if ref not in declared:
                    raise ValueError(f"claim {claim.claim_id!r} references undeclared entity {ref!r}")
            extra = set(claim.required_jurisdictions) - contract_jurs
            if extra:
                raise ValueError(f"claim {claim.claim_id!r} required_jurisdictions {sorted(extra)} not in contract jurisdictions")
        return self


class EvidenceContractError(BaseModel):
    """Returned when contract validation fails (parallel to existing slice errors)."""
    error: bool = True
    code: str
    message: str
    contract_id: str | None = None
```

**Part 3 — `tests/polaris_graph/evidence_contract/__init__.py`** (NEW, 0 LOC):
- Empty package marker.

**Part 4 — `tests/polaris_graph/evidence_contract/test_schema.py`** (NEW, ~75 LOC):
- `test_minimal_valid_contract`: smallest valid contract (1 entity, 1 claim, 1 jurisdiction).
- `test_jurisdiction_enum_values`: all 5 enum values accepted.
- `test_expected_source_coverage_zero_min_allowed`: tier_t1_min=0 is valid.
- `test_undeclared_entity_in_claim_rejected`: claim references entity not in expected_entities → ValueError.
- `test_empty_expected_entities_rejected`: min_length=1 enforced.
- `test_empty_expected_claims_rejected`: min_length=1 enforced.
- `test_contract_version_pinned`: contract_version literal "1.0" rejects other values.
- `test_contract_round_trip_json`: model_dump_json + model_validate_json yields equal contract.

## Acceptance criteria (binding)

1. `src/polaris_graph/evidence_contract/__init__.py` NEW.
2. `src/polaris_graph/evidence_contract/schema.py` NEW with the 6 models above.
3. `tests/polaris_graph/evidence_contract/__init__.py` NEW.
4. `tests/polaris_graph/evidence_contract/test_schema.py` NEW with 8 tests.

## Planned diff shape

```
src/polaris_graph/evidence_contract/__init__.py        NEW +5
src/polaris_graph/evidence_contract/schema.py          NEW +115
tests/polaris_graph/evidence_contract/__init__.py      NEW +0
tests/polaris_graph/evidence_contract/test_schema.py   NEW +75
```

LOC: +195 net. Over breakdown 180 budget by 15; under CHARTER §1 200-cap by 5. Brief author notes the budget overrun is small (15 LOC) and driven by tight test coverage of 8 distinct validation paths.

## Out of scope

- jsonschema export (Pydantic generates schema natively; jsonschema CLI dump is a separate utility) → I-ecg-001a follow-up.
- Cross-reference validation between contract entities and EvidencePool sources → I-ecg-002 (gate).
- UI editor → I-ecg-003.
- Migration tooling → I-ecg-004.

## Risks for Codex Red-Team

1. **Jurisdiction enum scope.** 5 values (CA / US / EU / UK / GLOBAL) cover Carney's clinical scope. Brief author commits to verifying `docs/carney_delivery_plan_v6_2.md` if other jurisdictions are mandatory.

2. **Cross-reference validator.** `expected_entities` referenced by claims must be declared at the contract level. Test `test_undeclared_entity_in_claim_rejected` covers.

3. **`contract_version` Literal["1.0"].** Future migrations bump this; I-ecg-004 will add a version-coercion path.

4. **`Pydantic v2 model_validator(mode="after")`.** Same idiom used in `verified_report.py:71-80, 141-162`.

5. **§9.4 compliance.** No mocks. No magic numbers (limits like 50 entities/50 claims are reasonable per-contract caps; alternatively make them named constants — brief author commits to making these `MAX_*` module constants if Codex requests).

6. **Sovereignty surface.** Pure type module; no I/O.

7. **CHARTER §1 LOC cap.** 195 net.

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
