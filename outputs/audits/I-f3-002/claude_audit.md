# Claude Architect Audit — I-f3-002

**Branch:** bot/I-f3-002 / **Diff SHA256:** `a6bac6427d9e084ad82fae5dea5aadd5cefb9696073e2b003c09d96a9adab86a`
**LOC:** 111 net (under CHARTER §1 200-cap by 89)
**Tests:** 7/7 PASS

## Files

```
src/polaris_graph/sovereignty/__init__.py             NEW +0
src/polaris_graph/sovereignty/classification.py       NEW +48
tests/polaris_graph/sovereignty/__init__.py           NEW +0
tests/polaris_graph/sovereignty/test_classification.py NEW +63
```

## Architecture review

1. **`str` + `Enum` multiple inheritance** for JSON-native serialization.
2. **EXTERNAL_LEAK_FORBIDDEN = {CAN_REAL, PRIVATE, CLIENT, UNKNOWN}** codifies Carney v6.2 §332 default-deny. PUBLIC_SYNTHETIC is the only externally-allowed classification.
3. **`parse_classification`** accepts enum / string / None. None → UNKNOWN (defensive).
4. **Iter-3 P2 advisory hardening (deferred to I-f3-003 router):** `is_external_leak_forbidden` typed for DataClassification; raw-string callers must `parse_classification()` first. Documented in module docstring; router will enforce.

## LAW + invariant checks

- **LAW II:** Default-deny on UNKNOWN; invalid string raises ValueError. ✓
- **LAW V:** snake_case file naming; PascalCase class. ✓
- **LAW VI:** No magic strings — all 5 enum values are module constants. ✓
- **§9.4:** No `unittest.mock`. ✓
- **CHARTER §1 200-cap:** 111 net. ✓

## Verdict

APPROVE for Codex diff review.
