# Codex Brief Review — I-f3-003 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f3-003 — Backend: sovereignty router (intercepts CLIENT-tagged docs from external API)
**Phase:** 1 / **Feature:** F3
**LOC budget:** 180 net per breakdown. **CHARTER §1 hard cap: 200.**

## Mission

Add `src/polaris_graph/sovereignty/router.py` — the policy enforcement point that gates outbound payloads against the I-f3-002 `EXTERNAL_LEAK_FORBIDDEN` set. Per Carney v6.2 §332: "All non-PUBLIC_SYNTHETIC classifications blocked from external API."

Per breakdown: "Acceptance: unit + integration; CLIENT cannot leak."

## Substrate (HONEST)

- I-f3-002 (just merged, PR #237): `DataClassification`, `EXTERNAL_LEAK_FORBIDDEN = {CAN_REAL, PRIVATE, CLIENT, UNKNOWN}`, `is_external_leak_forbidden()`, `parse_classification()`.
- The router enforces policy at the call-site of any external-egress code path. It is a policy library, NOT a network-layer interceptor (that's a heavier substrate concern out of scope for this Issue).
- The router function takes a "payload candidate" (e.g. a list of evidence chunks each with a classification) and either returns the filtered-safe subset OR raises a `SovereigntyViolationError` if any forbidden item is present, depending on enforcement mode.
- Future Issues (`I-f3-004` CI test) will assert the router is called at every external-egress site.

## Acceptance criteria (binding)

1. **`src/polaris_graph/sovereignty/router.py`** (NEW):
   ```python
   from dataclasses import dataclass
   from typing import Any, Iterable, Protocol

   from polaris_graph.sovereignty.classification import (
       DataClassification, EXTERNAL_LEAK_FORBIDDEN,
       is_external_leak_forbidden, parse_classification,
   )


   class ClassifiedItem(Protocol):
       """Minimal protocol: any object with a `classification` attr (str | DataClassification)."""
       classification: Any  # raw string or DataClassification; router parses


   @dataclass(frozen=True)
   class SovereigntyDecision:
       allowed: list  # items passed
       blocked: list  # items rejected
       reasons: list[str]  # human-readable reason per blocked item


   class SovereigntyViolationError(RuntimeError):
       """Raised in strict mode when any item is forbidden external-egress."""


   def filter_for_external_egress(
       items: Iterable, *, strict: bool = True,
   ) -> SovereigntyDecision:
       """Filter items against EXTERNAL_LEAK_FORBIDDEN.

       - strict=True (default): raises SovereigntyViolationError on first forbidden item.
       - strict=False: returns SovereigntyDecision with allowed/blocked split.

       Per Carney v6.2 §332 default-deny: only PUBLIC_SYNTHETIC items pass.
       """
       allowed: list = []
       blocked: list = []
       reasons: list[str] = []
       for item in items:
           raw = getattr(item, "classification", None)
           if raw is None and isinstance(item, dict):
               raw = item.get("classification")
           cls = parse_classification(raw)
           if is_external_leak_forbidden(cls):
               reason = f"classification={cls.value} forbidden external-egress"
               if strict:
                   raise SovereigntyViolationError(reason)
               blocked.append(item)
               reasons.append(reason)
           else:
               allowed.append(item)
       return SovereigntyDecision(allowed=allowed, blocked=blocked, reasons=reasons)


   def assert_safe_for_external(items: Iterable) -> None:
       """Convenience strict gate; raises SovereigntyViolationError on any forbidden item."""
       filter_for_external_egress(items, strict=True)
   ```
   - Handles dict-shaped items (e.g. `{"text": "...", "classification": "CLIENT"}`) AND attr-bearing objects (e.g. dataclass instances with `classification` field).
   - Default-deny on missing `classification` (parse_classification(None) → UNKNOWN → forbidden).
   - LOC: ~75.

2. **`tests/polaris_graph/sovereignty/test_router.py`** (NEW): 8 tests:
   - `test_strict_blocks_client_doc`: 1 PUBLIC_SYNTHETIC + 1 CLIENT → SovereigntyViolationError.
   - `test_strict_blocks_can_real`: CAN_REAL → raises.
   - `test_strict_blocks_private`: PRIVATE → raises.
   - `test_strict_blocks_unknown_default_deny`: UNKNOWN (or missing classification) → raises.
   - `test_strict_allows_only_public_synthetic`: 3 PUBLIC_SYNTHETIC → no raise; SovereigntyDecision.allowed has 3, blocked has 0.
   - `test_lax_returns_split`: strict=False; mixed CLIENT + PUBLIC_SYNTHETIC → SovereigntyDecision with allowed=[ps], blocked=[client], reasons populated.
   - `test_dict_items_classification_field`: dict items with `"classification": "PUBLIC_SYNTHETIC"` → allowed.
   - `test_assert_safe_for_external_passthrough`: PUBLIC_SYNTHETIC-only → no raise; CLIENT → raises.
   - LOC: ~85.

## Planned diff shape

```
src/polaris_graph/sovereignty/router.py            NEW +75
tests/polaris_graph/sovereignty/test_router.py     NEW +85
```

LOC: +160 net pre-Prettier. Under CHARTER §1 200-cap by 40.

## Out of scope (deferred per breakdown)

- **CI test** asserting the router is called at every external-egress site → **I-f3-004** next.
- **Network-layer interceptor** (e.g. wrapping httpx.Client.post) — out of scope; router is a policy library, callers invoke it.
- **Audit logging** of blocked items → follow-up if needed.

## Risks for Codex Red-Team

1. **Default-deny on missing classification.** `parse_classification(None) → UNKNOWN → forbidden`. Items lacking classification are TREATED AS UNKNOWN (defensive). Test 4 asserts.

2. **Strict mode is the default.** Caller must explicitly pass `strict=False` to get the split-not-raise behavior. Reduces footgun risk.

3. **`SovereigntyViolationError` inherits RuntimeError.** Catchable but distinguishable. Per LAW II — fail loudly.

4. **Dict + attr support.** `getattr(item, "classification", None)` for dataclass-style; `item.get("classification")` for dict-style. Both covered.

5. **`parse_classification` is the canonical normalizer.** Raw strings AND enum instances AND None all flow through it. Invalid raw strings raise ValueError (escapes the router; caller sees the bad input clearly).

6. **No Protocol enforcement at runtime.** `ClassifiedItem` Protocol is type-hint only. Runtime relies on duck-typing (getattr + dict.get).

7. **No new package.json / requirements.txt dep.**

8. **CHARTER §1 LOC cap.** 160 net.

9. **Test coverage:** all 4 forbidden classifications + the 1 allowed; both strict + lax modes; dict + attr access patterns.

10. **No I/O.** Pure-functional; no side effects beyond raising.

11. **`SovereigntyDecision` is a frozen dataclass.** Immutable post-construction; safe to share across boundaries.

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
