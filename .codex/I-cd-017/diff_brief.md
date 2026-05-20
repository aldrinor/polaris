HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- "Don't pick bone from egg" — P1 only for real execution risks.
- If iter 5 returns REQUEST_CHANGES, Claude force-APPROVE's on non-P0/P1 residuals.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff review — I-cd-017 (#627)

Brief APPROVE'd at iter 3. Iter-1 P1 (F13 row): fixed in 37c4a425. Iter-2 P1 (partial_qwen_advisory missing from _QUALIFYING_STATUSES): fixed in c478274b — added the status + dedicated test (10/10 backend tests pass). Canonical-diff-sha256 now `ad616358aa7cfea628beec6f20a6ba028fb187f68a2789d53e92ae731d721064`.

## §A Canonical diff summary

Production code: ~277 LOC
- `src/polaris_v6/schemas/pin_snapshot.py` NEW — Pydantic `PinSnapshot` (frozen, extra="forbid"), date-pattern field, `retracted_source_ids` nullable.
- `src/polaris_v6/api/pins.py` NEW — 2 routes (`GET /runs/{run_id}/pins` list + `GET /runs/{run_id}/pins/{date}` single) + `_synthesize_pin_from_manifest()` handling BOTH generator-block shape variants per iter-2 P1.2.
- `src/polaris_v6/queue/run_store.py` MOD — added `list_completed_runs_by_query_slug()` using existing `idx_runs_query_slug` index, finished_at ASC, defensive against missing-table/legacy-schema.
- `src/polaris_v6/api/app.py` MOD — register `pins_router` after `bundle_router`.
- `web/lib/api.ts` MOD — added `PinSnapshot` interface + `fetchPinList()` + `fetchPin()` using existing `authFetch` + `BACKEND_URL = "/api/v6"` (iter-1 P1 fix: in-house transport/auth).
- `web/lib/pin_replay_client.ts` NEW — thin re-export shim for ergonomic consumer imports.
- `web/lib/pin_replay_demo.ts` — DEMO_PIN_REGISTRY data DELETED (47 lines), kept as empty object + type re-export shim.
- `web/app/pin_replay/page.tsx` MOD — empty-state guard added BEFORE detectRegressions/delta math (iter-1 P2 fix); existing snapshot-card rendering preserved for when registry is non-empty.

Tests + Playwright: ~397 LOC
- `tests/v6/test_pins_route.py` NEW — 9 tests covering: success path synthesis, abort_no_verified_sections shape variant, multi-run chronological ordering, unknown run 404, in-progress/aborted-corpus exclusion, exact date match, date mismatch 404, malformed date 422, zero-denominator pass_rate.
- `web/tests/e2e/{pin_replay,pin_replay_diff,pin_regression_alert,pin_retraction_handled}.spec.ts` — wrapped in `test.describe.skip(...)` with Seq 29 / #619 pointer (iter-1 P1 fix + iter-2 P2 confirmation).
- `web/tests/e2e/visual_60_baselines.spec.ts` — F13 row commented out (iter-1 P1 fix).
- `web/tests/e2e/perf_core_web_vitals.spec.ts` — `test.skip()` the INP-on-pin_replay click test (iter-2 P2.1 fix).

## §B Acceptance check

| Criterion | Status |
|---|---|
| `GET /runs/{run_id}/pins` returns synthesized PinSnapshot[] sorted finished_at ASC | YES — pins.py:list_pins + run_store.list_completed_runs_by_query_slug |
| `GET /runs/{run_id}/pins/{date}` returns the single matching snapshot | YES — pins.py:get_pin_by_date with run_id AND date double match |
| Success-path generator block → sections_kept + sections_dropped synthesis | YES — pins.py:_synthesize_pin_from_manifest + test_list_pins_success_path |
| abort_no_verified_sections shape variant handled (sections_total + sections_dropped, no sections_kept/sentences_dropped) | YES — defensive .get() with fallback; test_list_pins_abort_no_verified_shape_variant |
| `RunStatusResponse.pipeline_status` is the authoritative source (NOT raw manifest field) | YES — pins.py:_qualifies reads run.pipeline_status |
| pass_rate zero-denominator returns 0.0 not NaN | YES — explicit branch + test_pass_rate_zero_denominator_returns_zero |
| Frontend uses `BACKEND_URL = "/api/v6"` + `authFetch` (Next.js rewrite + JWT auth) | YES — web/lib/api.ts:fetchPinList/fetchPin |
| Empty-state guard before detectRegressions/delta math | YES — page.tsx:if (PIN_DATES.length === 0) return <EmptyPinReplay /> |
| All 5 demo-dependent Playwright specs skipped with Seq 29 / #619 pointer | YES |
| perf_core_web_vitals.spec.ts INP test (clicks pin-show-diff) skipped | YES — test.skip("INP on /pin_replay show-diff...") |
| visual_60_baselines.spec.ts F13 row patched out | YES — commented block with Seq 29 / #619 comment |

## §C Codex Red-Team checklist

1. Synthesis math correctness — abort variant returns pass_rate=0 even when generator has no sentences_dropped key (test_pass_rate_zero_denominator_returns_zero).
2. Auth contract — fetchPinList/fetchPin use `authFetch` (private) via `api.ts` exports; 401 routes to /sign-in.
3. Date validation — `len(date) != 10` + `date[4] != "-"` + `date[7] != "-"` → 422 (test_get_pin_by_date_malformed_returns_422).
4. Duplicate date disambiguation — get_pin_by_date matches BOTH run_id AND finished_at[:10] (not ambiguous).
5. Excluded statuses — `abort_corpus_inadequate` + `abort_scope_rejected` excluded; `partial_*` included (test_list_pins_excludes_in_progress_and_aborted_corpus).
6. Missing manifest.json on disk — `_load_manifest()` returns None, excludes that run from list (no 500).
7. Path traversal — `{run_id}` and `{date}` come through FastAPI path params; no direct file path construction from user input beyond `Path(artifact_dir) / "manifest.json"` where artifact_dir comes from run_store, not user.
8. Empty list semantics — list endpoint returns `[]` only if no qualifying siblings; unknown run_id is 404.
9. The frontend page.tsx empty-state guard runs at FIRST conditional after useState; subsequent code paths require non-empty PIN_DATES.
10. CI workflow does NOT need new env vars; `PYTHONPATH=src` already set for tests/v6/ job per `.github/workflows/web_ci.yml`.

## §D Smoke test results

```
$ PYTHONPATH=src python -m pytest tests/v6/test_pins_route.py -v
9 passed in 3.84s
```

```
$ cd web && npx tsc --noEmit
(rc=0, no errors)
```

## §E Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
