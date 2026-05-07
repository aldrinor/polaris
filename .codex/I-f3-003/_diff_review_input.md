# Codex Diff Review — I-f3-003 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-003 — sovereignty router (CLIENT-doc cannot leak)
**Brief:** APPROVED iter 1 (0/0/2P2 accept_remaining; both P2 addressed in implementation)
**Canonical-diff-sha256:** `4cb60cb8eec9037f8d62e1bee018dcacc63afed164f4366ce7fcc4bc70e1d69c`
**LOC:** 155 net (under 200-cap)
**Tests:** 9/9 PASS

## Files

```
src/polaris_graph/sovereignty/router.py        NEW +73
tests/polaris_graph/sovereignty/test_router.py NEW +82
```

## What changed

- `filter_for_external_egress(items, *, strict=True)` — gates each item against `EXTERNAL_LEAK_FORBIDDEN`. Strict raises `SovereigntyViolationError`. Lax returns `SovereigntyDecision(allowed, blocked, reasons)`.
- `assert_safe_for_external(items)` — convenience strict gate.
- `_classification_of(item)` — handles dict + attr access patterns.
- 9 tests covering all 4 forbidden classifications, allowed (PUBLIC_SYNTHETIC), strict + lax modes, dict + dataclass items, default-deny on missing classification, enum + string classification values.

## Iter-1 brief P2 addressed

- **P2 #1 (mutability):** `SovereigntyDecision` fields are now `tuple` not `list`.
- **P2 #2 (integration vs unit):** Acknowledged as I-f3-004's scope.

## Risks for Codex Red-Team

1. **Default-strict.** `strict=True` is the default; callers must opt-in to lax. Reduces footgun.
2. **Default-deny on UNKNOWN/missing.** Defensive. Test 4 covers both branches.
3. **Tuple immutability.** `SovereigntyDecision` carries tuples; safe to share references but inner items are still shared (dataclass instances mutable via their own attrs). Audit doc notes this explicitly.
4. **Dict + attr access.** `getattr(item, "classification", None) or item.get("classification") if dict`. Test 7 asserts dict access.
5. **`parse_classification`** is the canonical normalizer; raw strings, enum instances, None all flow.
6. **`SovereigntyViolationError`** subclasses RuntimeError — catchable but distinguishable.
7. **No I/O; pure-functional.**
8. **No new dep.**
9. **CHARTER §1 LOC cap.** 155 net.

## Out of scope

- CI test asserting router-called at every external-egress site → I-f3-004.
- Network-layer interceptor → out of scope.

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
diff --git a/src/polaris_graph/sovereignty/router.py b/src/polaris_graph/sovereignty/router.py
new file mode 100644
index 0000000..3208f64
--- /dev/null
+++ b/src/polaris_graph/sovereignty/router.py
@@ -0,0 +1,73 @@
+"""Sovereignty router: enforces EXTERNAL_LEAK_FORBIDDEN policy at call sites (I-f3-003).
+
+Per Carney v6.2 §332. The router is a policy library — callers invoke
+`assert_safe_for_external` (strict gate) or `filter_for_external_egress`
+(split mode) before any outbound payload leaves Canadian-sovereign infra.
+"""
+
+from __future__ import annotations
+
+from dataclasses import dataclass
+from typing import Any, Iterable
+
+from polaris_graph.sovereignty.classification import (
+    is_external_leak_forbidden,
+    parse_classification,
+)
+
+
+@dataclass(frozen=True)
+class SovereigntyDecision:
+    """Result of `filter_for_external_egress(strict=False)`.
+
+    Note: while the dataclass is frozen, the contained `tuple` fields
+    are themselves immutable.
+    """
+
+    allowed: tuple
+    blocked: tuple
+    reasons: tuple[str, ...]
+
+
+class SovereigntyViolationError(RuntimeError):
+    """Raised in strict mode when any item is forbidden external-egress."""
+
+
+def _classification_of(item: Any) -> str | None:
+    raw = getattr(item, "classification", None)
+    if raw is None and isinstance(item, dict):
+        raw = item.get("classification")
+    return raw
+
+
+def filter_for_external_egress(
+    items: Iterable, *, strict: bool = True,
+) -> SovereigntyDecision:
+    """Filter items against EXTERNAL_LEAK_FORBIDDEN per Carney v6.2 §332.
+
+    strict=True (default): raises SovereigntyViolationError on first forbidden item.
+    strict=False: returns SovereigntyDecision split.
+
+    Items lacking `classification` default to UNKNOWN (forbidden).
+    """
+    allowed: list = []
+    blocked: list = []
+    reasons: list[str] = []
+    for item in items:
+        cls = parse_classification(_classification_of(item))
+        if is_external_leak_forbidden(cls):
+            reason = f"classification={cls.value} forbidden external-egress"
+            if strict:
+                raise SovereigntyViolationError(reason)
+            blocked.append(item)
+            reasons.append(reason)
+        else:
+            allowed.append(item)
+    return SovereigntyDecision(
+        allowed=tuple(allowed), blocked=tuple(blocked), reasons=tuple(reasons),
+    )
+
+
+def assert_safe_for_external(items: Iterable) -> None:
+    """Strict gate; raises SovereigntyViolationError on any forbidden item."""
+    filter_for_external_egress(items, strict=True)
diff --git a/tests/polaris_graph/sovereignty/test_router.py b/tests/polaris_graph/sovereignty/test_router.py
new file mode 100644
index 0000000..9360a30
--- /dev/null
+++ b/tests/polaris_graph/sovereignty/test_router.py
@@ -0,0 +1,82 @@
+"""Unit tests for I-f3-003 — sovereignty router."""
+
+from __future__ import annotations
+
+from dataclasses import dataclass
+
+import pytest
+
+from polaris_graph.sovereignty.classification import DataClassification
+from polaris_graph.sovereignty.router import (
+    SovereigntyDecision,
+    SovereigntyViolationError,
+    assert_safe_for_external,
+    filter_for_external_egress,
+)
+
+
+@dataclass
+class Item:
+    text: str
+    classification: str
+
+
+def test_strict_blocks_client_doc():
+    items = [Item("ok", "PUBLIC_SYNTHETIC"), Item("leak", "CLIENT")]
+    with pytest.raises(SovereigntyViolationError, match="CLIENT"):
+        filter_for_external_egress(items, strict=True)
+
+
+def test_strict_blocks_can_real():
+    with pytest.raises(SovereigntyViolationError, match="CAN_REAL"):
+        filter_for_external_egress([Item("x", "CAN_REAL")], strict=True)
+
+
+def test_strict_blocks_private():
+    with pytest.raises(SovereigntyViolationError, match="PRIVATE"):
+        filter_for_external_egress([Item("x", "PRIVATE")], strict=True)
+
+
+def test_strict_blocks_unknown_default_deny():
+    # UNKNOWN-classified item:
+    with pytest.raises(SovereigntyViolationError, match="UNKNOWN"):
+        filter_for_external_egress([Item("x", "UNKNOWN")], strict=True)
+    # missing classification entirely:
+    with pytest.raises(SovereigntyViolationError, match="UNKNOWN"):
+        filter_for_external_egress([{"text": "no_class"}], strict=True)
+
+
+def test_strict_allows_only_public_synthetic():
+    items = [Item(f"ps{i}", "PUBLIC_SYNTHETIC") for i in range(3)]
+    decision = filter_for_external_egress(items, strict=True)
+    assert isinstance(decision, SovereigntyDecision)
+    assert len(decision.allowed) == 3
+    assert decision.blocked == ()
+
+
+def test_lax_returns_split():
+    items = [Item("ok", "PUBLIC_SYNTHETIC"), Item("leak", "CLIENT"), Item("ok2", "PUBLIC_SYNTHETIC")]
+    decision = filter_for_external_egress(items, strict=False)
+    assert len(decision.allowed) == 2
+    assert len(decision.blocked) == 1
+    assert decision.blocked[0].text == "leak"
+    assert decision.reasons[0].endswith("forbidden external-egress")
+
+
+def test_dict_items_classification_field():
+    items = [{"text": "ok", "classification": "PUBLIC_SYNTHETIC"}]
+    decision = filter_for_external_egress(items, strict=True)
+    assert len(decision.allowed) == 1
+
+
+def test_assert_safe_for_external_passthrough():
+    assert_safe_for_external([Item("ok", "PUBLIC_SYNTHETIC")])  # no raise
+    with pytest.raises(SovereigntyViolationError):
+        assert_safe_for_external([Item("leak", "CLIENT")])
+
+
+def test_enum_classification_value_works():
+    """Items can carry DataClassification enum directly, not just strings."""
+    items = [Item("ok", DataClassification.PUBLIC_SYNTHETIC)]
+    decision = filter_for_external_egress(items, strict=True)
+    assert len(decision.allowed) == 1

```
