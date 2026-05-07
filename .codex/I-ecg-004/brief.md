# Codex Brief Review — I-ecg-004 (ITER 2 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-ecg-004 — Contract version migration test
**Phase:** 1 / **Feature:** ECG
**LOC budget:** 100 net per breakdown. **CHARTER §1 hard cap: 200.**

## Mission

Per breakdown: v1 → v2 schema migration; backward-compat. Migration test on fixture v1 contracts.

## Substrate (HONEST at HEAD)

- `src/polaris_graph/evidence_contract/schema.py:62` `EvidenceContract.contract_version: Literal["1.0"]`. Currently ONE version exists; no v2 yet.
- This Issue ships the migration scaffolding so when v2 lands later, the migration path is already tested.

## Approach

**Part 1 — `src/polaris_graph/evidence_contract/migration.py`** (NEW, ~50 LOC):
- `MIGRATIONS: dict[tuple[str, str], Callable[[dict], dict]]` — registry of (from_version, to_version) → migration function.
- `migrate_contract(raw: dict, target_version: str = "1.0") -> dict` — looks up the source version's `contract_version`. SHORT-CIRCUITS when source == target (no traversal, no self-loop). Else chains migrations following the registry; raises `ContractMigrationError` if no path. Self-loop (X, X) entries in MIGRATIONS are NOT consulted during traversal.
- `class ContractMigrationError(Exception)`.
- `_identity_migration(d: dict) -> dict`: returns dict unchanged. Pre-registered for ("1.0", "1.0") so the trivial case works.
- Forward-compatibility shim: when v2 lands, register `("1.0", "2.0")` migration function alongside.

**Part 2 — `tests/polaris_graph/evidence_contract/fixtures/v1_contract_minimal.json`** (NEW, ~25 LOC): a hand-curated minimal valid v1 contract.

**Part 3 — `tests/polaris_graph/evidence_contract/fixtures/v1_contract_full.json`** (NEW, ~50 LOC): a richer v1 contract with 3 entities, 3 claims, multiple jurisdictions.

**Part 4 — `tests/polaris_graph/evidence_contract/test_migration.py`** (NEW, ~75 LOC):
- `test_v1_minimal_loads_via_pydantic`: load fixture JSON, parse via `EvidenceContract.model_validate`, assert valid.
- `test_v1_full_loads_via_pydantic`: same for full fixture.
- `test_migrate_v1_to_v1_is_identity`: `migrate_contract(v1_json, "1.0") == v1_json`.
- `test_migrate_unknown_version_raises`: `migrate_contract({"contract_version": "0.5", ...}, "1.0")` raises `ContractMigrationError`.
- `test_migrate_unknown_target_raises`: `migrate_contract(v1_json, "99.0")` raises.
- `test_v1_round_trip_through_migration`: load v1 fixture JSON, parse via `EvidenceContract.model_validate`, then `model_dump(mode="json")` and compare to fixture sub-fields (research_question, expected_entities[0].name, contract_version). Strict-equality round-trip is brittle because contract_id and created_at_utc default at parse time; assert specific business fields instead.

## Acceptance criteria (binding)

1. `src/polaris_graph/evidence_contract/migration.py` NEW.
2. `src/polaris_graph/evidence_contract/__init__.py` EDIT — re-export migration symbols.
3. 2 fixture JSON files (NEW).
4. `tests/polaris_graph/evidence_contract/test_migration.py` NEW with 6 tests.

## Planned diff shape

```
src/polaris_graph/evidence_contract/migration.py        NEW +50
src/polaris_graph/evidence_contract/__init__.py         EDIT +5
tests/polaris_graph/evidence_contract/fixtures/v1_contract_minimal.json  NEW +25
tests/polaris_graph/evidence_contract/fixtures/v1_contract_full.json     NEW +50
tests/polaris_graph/evidence_contract/test_migration.py NEW +75
```

LOC: +205 net. Over CHARTER §1 200-cap by 5. Brief author commits to inline-trimming during impl (one of the JSON fixtures may be fewer LOC if formatted compactly).

## Out of scope

- v2 schema definition itself → not needed until v2 ships.
- Frontend migration utility → I-ecg-004a follow-up if needed.
- Database migration for stored contracts → I-ecg-003b backend persistence comes first.

## Risks for Codex Red-Team

1. **Identity migration only at HEAD.** No real version transitions exist yet. The scaffolding is valuable because when v2 lands, the migration function slots into `MIGRATIONS` and ALL existing v1 fixtures must still load + migrate cleanly. Test asserts the registry mechanism works.
2. **Unknown version raises.** Defensive — production loaders should never see an unknown version, but if they do, fail loud per LAW II.
3. **JSON fixture validity.** Both fixtures must `model_validate` cleanly via existing Pydantic schema. Brief author commits to running fixtures through `EvidenceContract.model_validate_json()` before commit.
4. **§9.4 compliance.** No mocks. No magic numbers. No `try: pass`. No TODO/FIXME.
5. **CHARTER §1 LOC cap.** 205 net. At cap; trim if needed.
6. **No new package dep.**

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
