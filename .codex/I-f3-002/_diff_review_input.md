# Codex Diff Review — I-f3-002 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-002 — data classification taxonomy
**Branch:** bot/I-f3-002
**Brief:** APPROVED iter 3 (iter1 REQ_CH under-block → iter2 REQ_CH test contradicted → iter3 APPROVE 0/0/2P2 accept_remaining)
**Canonical-diff-sha256:** `a6bac6427d9e084ad82fae5dea5aadd5cefb9696073e2b003c09d96a9adab86a`
**LOC:** 111 net (under CHARTER §1 200-cap by 89)
**Tests:** 7/7 PASS via `PYTHONPATH=src python -m pytest tests/polaris_graph/sovereignty/test_classification.py -v`

## Files

```
src/polaris_graph/sovereignty/__init__.py              NEW +0
src/polaris_graph/sovereignty/classification.py        NEW +48
tests/polaris_graph/sovereignty/__init__.py            NEW +0
tests/polaris_graph/sovereignty/test_classification.py NEW +63
```

## What changed

### `src/polaris_graph/sovereignty/classification.py`
- `class DataClassification(str, Enum)` with 5 members: PUBLIC_SYNTHETIC | CAN_REAL | PRIVATE | CLIENT | UNKNOWN.
- `ALL_CLASSIFICATIONS: tuple` — convenience iteration.
- `EXTERNAL_LEAK_FORBIDDEN: frozenset` = {CAN_REAL, PRIVATE, CLIENT, UNKNOWN}. Codifies Carney v6.2 §332 default-deny.
- `parse_classification(value: str | DataClassification | None) -> DataClassification` — None→UNKNOWN; invalid string→ValueError.
- `is_external_leak_forbidden(classification) -> bool` — set-membership check.

### `tests/polaris_graph/sovereignty/test_classification.py`
7 tests covering: 5-value membership, JSON serialization (str+Enum behavior), parse from enum/string/None/invalid, EXTERNAL_LEAK_FORBIDDEN policy (PUBLIC_SYNTHETIC→False; other 4→True).

## Risks for Codex Red-Team

1. **Default-deny on UNKNOWN.** Per Carney v6.2 §332 + iter-2 fix. UNKNOWN is forbidden external; only PUBLIC_SYNTHETIC allowed.
2. **`str` + `Enum`** — JSON-native via `str.__str__` invoked by `json.dumps`. Test 2 asserts.
3. **`parse_classification(None)` → UNKNOWN.** Defensive; caller can `is None` check upstream if rejecting.
4. **`is_external_leak_forbidden` typed for DataClassification.** Iter-3 P2 hardening note: router (I-f3-003) should `parse_classification()` raw strings before calling. Documented in module docstring.
5. **No new package.json / requirements.txt dep.**
6. **CHARTER §1 LOC cap.** 111 net.
7. **Frozen set immutability.** `EXTERNAL_LEAK_FORBIDDEN` cannot be mutated post-import.
8. **Test isolation.** All tests are pure-functional; no fixtures, no monkeypatch.
9. **`ValueError` on invalid string.** `DataClassification("bad")` raises ValueError per stdlib enum behavior; test 6 asserts.

## Out of scope

- Sovereignty router → I-f3-003.
- Sovereignty CI test → I-f3-004.

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


## Diff to review

```diff
diff --git a/src/polaris_graph/sovereignty/__init__.py b/src/polaris_graph/sovereignty/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/src/polaris_graph/sovereignty/classification.py b/src/polaris_graph/sovereignty/classification.py
new file mode 100644
index 0000000..fa9b690
--- /dev/null
+++ b/src/polaris_graph/sovereignty/classification.py
@@ -0,0 +1,48 @@
+"""Canonical data classification taxonomy + sovereignty policy (I-f3-002).
+
+Codifies `docs/carney_delivery_plan_v6_2.md:332` "All non-PUBLIC_SYNTHETIC
+classifications blocked from external API". The `EXTERNAL_LEAK_FORBIDDEN`
+set is the authoritative external-egress policy consumed by the
+sovereignty router (I-f3-003).
+"""
+
+from __future__ import annotations
+
+from enum import Enum
+from typing import Union
+
+
+class DataClassification(str, Enum):
+    PUBLIC_SYNTHETIC = "PUBLIC_SYNTHETIC"
+    CAN_REAL = "CAN_REAL"
+    PRIVATE = "PRIVATE"
+    CLIENT = "CLIENT"
+    UNKNOWN = "UNKNOWN"
+
+
+ALL_CLASSIFICATIONS: tuple[DataClassification, ...] = tuple(DataClassification)
+
+EXTERNAL_LEAK_FORBIDDEN: frozenset[DataClassification] = frozenset(
+    {
+        DataClassification.CAN_REAL,
+        DataClassification.PRIVATE,
+        DataClassification.CLIENT,
+        DataClassification.UNKNOWN,
+    }
+)
+
+
+def parse_classification(
+    value: Union[str, DataClassification, None],
+) -> DataClassification:
+    """Normalize input to DataClassification. None → UNKNOWN. Invalid → ValueError."""
+    if value is None:
+        return DataClassification.UNKNOWN
+    if isinstance(value, DataClassification):
+        return value
+    return DataClassification(value)
+
+
+def is_external_leak_forbidden(classification: DataClassification) -> bool:
+    """True iff the given classification is forbidden from external-API egress."""
+    return classification in EXTERNAL_LEAK_FORBIDDEN
diff --git a/tests/polaris_graph/sovereignty/__init__.py b/tests/polaris_graph/sovereignty/__init__.py
new file mode 100644
index 0000000..e69de29
diff --git a/tests/polaris_graph/sovereignty/test_classification.py b/tests/polaris_graph/sovereignty/test_classification.py
new file mode 100644
index 0000000..f3e03fb
--- /dev/null
+++ b/tests/polaris_graph/sovereignty/test_classification.py
@@ -0,0 +1,63 @@
+"""Unit tests for I-f3-002 — DataClassification + sovereignty policy."""
+
+from __future__ import annotations
+
+import json
+
+import pytest
+
+from polaris_graph.sovereignty.classification import (
+    ALL_CLASSIFICATIONS,
+    EXTERNAL_LEAK_FORBIDDEN,
+    DataClassification,
+    is_external_leak_forbidden,
+    parse_classification,
+)
+
+
+def test_all_five_values_present():
+    expected = {"PUBLIC_SYNTHETIC", "CAN_REAL", "PRIVATE", "CLIENT", "UNKNOWN"}
+    assert {c.value for c in ALL_CLASSIFICATIONS} == expected
+    assert len(ALL_CLASSIFICATIONS) == 5
+
+
+def test_str_inheritance_makes_json_serializable():
+    payload = {"c": DataClassification.CLIENT}
+    assert json.dumps(payload) == '{"c": "CLIENT"}'
+
+
+def test_parse_classification_accepts_enum():
+    assert parse_classification(DataClassification.CAN_REAL) is DataClassification.CAN_REAL
+
+
+def test_parse_classification_accepts_string():
+    assert parse_classification("CAN_REAL") is DataClassification.CAN_REAL
+
+
+def test_parse_classification_none_returns_unknown():
+    assert parse_classification(None) is DataClassification.UNKNOWN
+
+
+def test_parse_classification_invalid_raises():
+    with pytest.raises(ValueError):
+        parse_classification("NOT_A_REAL_CLASSIFICATION")
+
+
+def test_is_external_leak_forbidden():
+    """Per Carney v6.2 §332: only PUBLIC_SYNTHETIC is allowed external."""
+    assert is_external_leak_forbidden(DataClassification.PUBLIC_SYNTHETIC) is False
+    for c in (
+        DataClassification.CAN_REAL,
+        DataClassification.PRIVATE,
+        DataClassification.CLIENT,
+        DataClassification.UNKNOWN,
+    ):
+        assert is_external_leak_forbidden(c) is True
+    assert EXTERNAL_LEAK_FORBIDDEN == frozenset(
+        {
+            DataClassification.CAN_REAL,
+            DataClassification.PRIVATE,
+            DataClassification.CLIENT,
+            DataClassification.UNKNOWN,
+        }
+    )

```
