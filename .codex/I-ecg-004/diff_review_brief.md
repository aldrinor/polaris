# Codex Diff Review — I-ecg-004 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-ecg-004 — Contract version migration test
**Brief:** APPROVED iter 2
**Canonical-diff-sha256:** `e3bba70a437b3d58ab17034b1be270a638f978dcc9902780cf35815bf898b339`
**LOC:** 195 net (5 under CHARTER §1 200-cap)
**Tests:** 8/8 PASS

## Files

```
src/polaris_graph/evidence_contract/migration.py        NEW +48
src/polaris_graph/evidence_contract/__init__.py         EDIT +8
tests/polaris_graph/evidence_contract/fixtures/v1_contract_minimal.json  NEW +20
tests/polaris_graph/evidence_contract/fixtures/v1_contract_full.json     NEW +34
tests/polaris_graph/evidence_contract/test_migration.py NEW +85
```

## What changed

**`migration.py`:** `MIGRATIONS: dict[tuple[str, str], Callable]` registry + `migrate_contract(raw, target_version)` walker + `ContractMigrationError`. Short-circuits source==target before traversal (prevents self-loop infinite loops); skips self-loop entries during traversal; tracks visited versions in `seen` set.

**`__init__.py`:** Re-exports migration symbols.

**Two v1 fixture JSON files:** minimal (1 entity, 1 claim, CA only) + full (3 entities, 3 claims, CA/US/EU multi-jurisdiction).

**`test_migration.py`:** 8 tests:
1. `test_v1_minimal_loads_via_pydantic`
2. `test_v1_full_loads_via_pydantic`
3. `test_migrate_v1_to_v1_is_identity`
4. `test_migrate_unknown_source_version_raises`
5. `test_migrate_missing_version_raises`
6. `test_migrate_unknown_target_version_raises`
7. `test_v1_round_trip_through_migration` — JSON-mode dump comparison (per Codex iter-1 P1)
8. `test_migrations_registry_supports_future_v2` — smoke registers a fake v2 migration, asserts walker chains correctly, then unregisters in finally block.

## Risks for Codex Red-Team

1. **Identity short-circuit + self-loop skip.** Per Codex iter-1 P2: source==target returns immediately; traversal `frm != to` filter ensures self-loops in MIGRATIONS aren't consulted.
2. **Round-trip via `model_dump_json` + `json.loads`.** Avoids enum/datetime native types; compares JSON-normalized output to fixture sub-fields (per Codex iter-1 P1 fix).
3. **`MIGRATIONS[("1.0", "2.0")]` smoke test** mutates module state then restores in `finally`; safe if test runner respects test isolation.
4. **§9.4 compliance.** No mocks. No magic numbers. No `try: pass`. No TODO/FIXME.
5. **CHARTER §1 LOC cap.** 195 net. Under 200.
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
