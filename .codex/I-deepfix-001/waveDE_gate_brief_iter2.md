HARD ITERATION CAP: 5 per document. Iter 2 of 5. Verdict APPROVE iff zero NOVEL P0 AND zero P1.

# Codex re-gate — I-deepfix-001 Wave D/E slate, ITER 2 (after your 2 findings)

At iter 1 you returned REQUEST_CHANGES with a P0 (WS-8 depth recency before the cap = drop) + a P1 (WS-15 wall/cost defaults None = unbounded). Review the fixes in `.codex/I-deepfix-001/waveDE_diff_iter2.patch` (the current committed diff of the 5 files). Repo root C:/POLARIS, read-only.

## Confirm the two fixes
1. **WS-8 P0 (depth_synthesis.py):** the recency reorder is now CAP-GATED — `ordered_baskets = _order_baskets_by_recency(...) if cap <= 0 else list(baskets or [])`. When a POSITIVE cap is set, the ORIGINAL weight order is kept for inclusion (byte-identical which baskets survive the cap), so recency can NEVER turn an old-basket demotion into a DROP. Recency reorders only when cap<=0 (unbounded, the default), where every basket is synthesized. CONFIRM this closes the §-1.3 drop.
2. **WS-15 P1 (ttddr_loop.py):** wall_seconds now defaults to 1800.0 and cost_budget to 50.0 (finite), so a default invocation is bounded on max_rounds AND wall-clock AND cost. None still explicitly opts a single bound out. CONFIRM the default loop can never run unbounded, and WS-15 stays default-OFF (PG_TTDDR_ENABLED).

## Also re-confirm
frozen engine name-only diff EMPTY; no other §-1.3 drop/cap; WS-10 discloses-not-drops; WS-14 DRB-II wrapper does not re-implement the official scorer; WS-11 only a test.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
ws8_p0_drop_closed: true|false
ws15_bounded_and_default_off: true|false
frozen_engine_untouched: true|false
novel_p0: [...]
p1: [...]
convergence_call: continue|accept_remaining
```
