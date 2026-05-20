# Claude audit — I-cd-017 (#627)

## Scope verified against the brief

Brief APPROVE'd iter 3. Option B (synthesize-from-manifest) accepted per Codex scope consult 2026-05-20 with quality-impact framing per operator directive.

## Production substrate landed

- `src/polaris_v6/schemas/pin_snapshot.py` — frozen Pydantic schema, `extra="forbid"`, date regex pattern, nullable `retracted_source_ids`.
- `src/polaris_v6/api/pins.py` — 2 routes + synthesis helper handling BOTH manifest generator-block shape variants per Codex iter-2 P1.2.
- `src/polaris_v6/queue/run_store.py` — `list_completed_runs_by_query_slug` using existing `idx_runs_query_slug` index.
- `src/polaris_v6/api/app.py` — `pins_router` registered.
- `web/lib/api.ts` — `fetchPinList` + `fetchPin` using `authFetch` + `BACKEND_URL = "/api/v6"` (iter-1 P1 client-transport fix).
- `web/lib/pin_replay_client.ts` — thin re-export shim.
- `web/lib/pin_replay_demo.ts` — `DEMO_PIN_REGISTRY = {}` empty object + type re-export shim.
- `web/app/pin_replay/page.tsx` — empty-state guard before `detectRegressions` / delta math (iter-1 P2 fix).

## Tests landed

- `tests/v6/test_pins_route.py` — 9 tests, all green (`PYTHONPATH=src python -m pytest tests/v6/test_pins_route.py -v` → 9 passed in 3.84s).
- 5 Playwright specs migrated via `test.describe.skip()` with Seq 29 / #619 pointer.
- `visual_60_baselines.spec.ts` F13 row commented out.
- `perf_core_web_vitals.spec.ts` INP-on-pin_replay test marked `test.skip()`.

## Phase-N-PARTIAL-honest manifest

- Backend route is live; data is synthesized from existing manifest.json fields — no separate pin-write path is added to the v6 actor.
- Frontend `/pin_replay` page renders an empty-state card; full rebuild ships in Seq 29 / I-A-12 / #619.
- `retracted_source_ids` is always `None` in synthesized snapshots — captured-source-retraction logging is a future capability.
- Acceptance of #627 ("A live completed run's pins are replayable through the product pin-replay surface") is met **after Seq 29 lands** — this PR is the backend half.

## Quality bar

- Codex iter-2 caught 2 real P1s in the brief; iter-3 APPROVE'd after both were fixed.
- 9/9 backend tests cover both happy-path and abort-shape-variant synthesis.
- TypeScript compiles cleanly across the web/ tree.
- No regression to existing routes; auth contract preserved.

## Files I have checked clean

`.codex/I-cd-017/brief.md` §C lists all adjacent files verified clean. No outstanding follow-up against this Issue beyond the deferred frontend rebuild (Seq 29 / #619).
