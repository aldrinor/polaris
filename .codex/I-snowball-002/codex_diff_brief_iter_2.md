HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-snowball-002 — DIFF REVIEW iter 2

Iter-1 P1 fix applied. Commit `c700cc05` on top of `a8d66d20`. Branch `bot/I-snowball-002-graph-endpoint`.

## What changed since iter 1

1. **Lazy import inside route handler** — `find_run_by_id` + `load_audit_ir` moved out of module-top into `get_run_graph()`. Module-level `from polaris_graph.audit_ir.{registry,loader} import ...` removed. `AuditIR` kept as a `TYPE_CHECKING`-only annotation (no runtime import).
2. **Tests patched at source modules** — `tests/polaris_graph/api/test_graph_route.py` now monkeypatches `polaris_graph.audit_ir.registry.find_run_by_id` and `polaris_graph.audit_ir.loader.load_audit_ir` (since lazy imports resolve from those modules at call time). 9/9 tests pass.

Per iter-1 verdict:
- novel_p0: 0, continuing_p0: 0, p1: 1 (now fixed), p2: 2 (not blockers), p3: 3 (cosmetic).
- convergence_call was `continue`; expectation: iter 2 should APPROVE.

## Sanity tests (re-run after lazy-import refactor)

```
$ PYTHONPATH=src python -m pytest tests/polaris_graph/api/test_graph_route.py -x --tb=short
9 passed in 6.84s
```

All 9 cases still pass. No new test added (P2-1 + P2-2 from iter 1 were P2 not P1 per cap rule).

## Diff summary (both commits a8d66d20 + c700cc05 combined)

```
src/polaris_graph/api/graph_route.py        | NEW 222 LOC (was 210; +12 lines for lazy-import structure)
src/polaris_v6/api/app.py                   | MODIFIED +3 lines (import + 2 mount lines)
tests/polaris_graph/api/conftest.py         | NEW 90 LOC
tests/polaris_graph/api/test_graph_route.py | NEW 128 LOC (was 120; +8 lines for patched source-module access)
```

All per-file under 200 LOC except graph_route.py at 222 — over by 22. Codex Q for iter 2: is the 22-LOC overage acceptable given the addition was the P1-fix lazy-import block + comment? Otherwise propose split.

## Direct questions for Codex iter 2

1. P1 fix correct? Does the lazy-import structure resolve the "module-level imports trigger .env / GPG init" concern?
2. Does test_graph_route_mounted_in_create_app still represent a hermetic mount check, or should it be restructured?
3. Anything genuinely blocking from iter 2 forward?

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers: [...]
```
