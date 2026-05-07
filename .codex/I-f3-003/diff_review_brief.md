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
