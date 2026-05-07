# Claude Architect Audit — I-f3-003 (sovereignty router)

**Branch:** bot/I-f3-003 / **Diff SHA256:** `4cb60cb8eec9037f8d62e1bee018dcacc63afed164f4366ce7fcc4bc70e1d69c`
**LOC:** 155 net (under CHARTER §1 200-cap by 45)
**Tests:** 9/9 PASS

## Files

```
src/polaris_graph/sovereignty/router.py        NEW +73
tests/polaris_graph/sovereignty/test_router.py NEW +82
```

## Iter-1 brief P2 advisories — addressed in implementation

- **P2 #1 (`SovereigntyDecision` mutability):** ADDRESSED. Fields are now `tuple` (truly immutable when contents are immutable; for callers passing dataclass items the references are still shareable — the dataclass docstring notes this explicitly).
- **P2 #2 (real external-egress integration test):** Acknowledged; per breakdown that's I-f3-004's scope. Not a blocker here.

## Architecture review

1. **Strict vs lax mode.** `strict=True` (default) raises `SovereigntyViolationError` on first forbidden item. `strict=False` returns split. Reduces footgun risk via default-strict.

2. **Default-deny on missing classification.** `parse_classification(None) → UNKNOWN → forbidden`. Test 4 covers both the explicit-UNKNOWN and missing-attribute branches.

3. **Dict + dataclass attr access.** `getattr(item, "classification", None)` AND `item.get("classification")` for dicts.

4. **`SovereigntyViolationError`** inherits RuntimeError.

5. **9 tests:** 4 forbidden classifications + 1 allowed (PUBLIC_SYNTHETIC) + dict access + lax split + assert_safe_for_external + enum-as-classification.

## LAW + invariant checks

- LAW II: Default-deny; fail-loud SovereigntyViolationError. ✓
- LAW V: snake_case file naming; PascalCase class. ✓
- §9.4: No `unittest.mock`. ✓
- CHARTER §1 200-cap: 155 net. ✓

## Verdict

APPROVE for Codex diff review.
