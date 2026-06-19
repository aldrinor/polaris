HARD ITERATION CAP: 3. This is iter 2 of 3. Front-load all findings; verdict APPROVE iff zero P0 and zero P1.
3-PRONG: reject your own suggestion if it (1) relaxes faithfulness, (2) grandfathers, (3) adds a cap/floor/throttle (a hang-guard timeout with a disclosed coverage row is NOT a neck-choke).

STATIC review (do NOT run pytest) of C:/POLARIS/.codex/iarch011_campaign/distill_iter2.patch — the iter-2 fix for B19.

ITER-1 P1 you raised (CORRECT, accepted): PG_DISTILL_MAP_CALL_WALL_S was applied PER retry attempt, so with MAX_RETRIES=2 a hung call could occupy the fan-out ~5493s before the coverage row.
ITER-2 FIX to verify: a new module-level async helper `_call_distill_map_with_wall(client, **kw)` wraps the call in an OUTER `asyncio.wait_for(wall)` so the TOTAL across internal retries is bounded at ~wall; BOTH distill_map sites now route through it; the inner per-attempt `timeout=wall` is kept defensively; a wall breach raises asyncio.TimeoutError caught by the caller -> loud map_failed coverage row. New test `test_distill_map_wall_bounds_call_end_to_end` drives a 30s _call and asserts it is cut at ~1s wall. The P2 duplicate comment block is removed (centralized in the helper).

VERIFY: (1) the total-bound now holds end-to-end; (2) asyncio.wait_for cancellation is safe here (no deadlock waiting on a non-cancellable to_thread — note the SSE worker thread may linger but the AWAIT is freed, which is acceptable and matches the sibling PG_CREDIBILITY_PASS_WALL_S contract); (3) no new silent-drop or faithfulness issue. Output schema; final line `verdict: APPROVE|REQUEST_CHANGES`.
