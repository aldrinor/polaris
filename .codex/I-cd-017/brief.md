HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex brief review — I-cd-017 (#627) — pin-replay backend route

## §A Scope (Option B accepted per scope-consult)

You picked **Option B: synthesize-from-manifest adapter** in `.codex/I-cd-017/codex_scope_consult.md`. The data fields the frontend `PinSnapshot` needs (verdict, section_count_kept/dropped, verified_sentence_count, pass_rate) are ALL present in pipeline-A's existing `manifest.json` `generator` block — no new pin-write path is required.

**LOC budget concern:** the full B scope (route + frontend client + page.tsx rewire + Playwright migrations) estimates 270 LOC, over the 200-LOC halt. I propose the following lean split:

### This PR I-cd-017a — backend route + frontend client (no page rewire)
1. New `src/polaris_v6/schemas/pin_snapshot.py` — Pydantic `PinSnapshot` schema (frozen, `extra="forbid"`).
2. New `src/polaris_v6/api/pins.py` — `APIRouter(prefix="/runs", tags=["pins"])` with two routes:
   - `GET /runs/{run_id}/pins` → `list[PinSnapshot]` (all completed runs with same query_slug, chronologically by `finished_at`).
   - `GET /runs/{run_id}/pins/{date}` → `PinSnapshot` (one snapshot for the run matching that finished_at ISO date; 404 if absent).
3. `src/polaris_v6/queue/run_store.py` — add `list_completed_runs_by_query_slug(query_slug) -> list[RunStatusResponse]` ordered by finished_at ASC. Uses existing `idx_runs_query_slug` index.
4. `src/polaris_v6/api/app.py` — register `pins_router`.
5. **Iter-1 P1-client-transport fix:** Add `fetchPinList(runId)` + `fetchPin(runId, date)` as exported functions IN `web/lib/api.ts` (alongside existing `startRun`, `getRunStatus`, etc.), using the private `authFetch` wrapper + `BACKEND_URL = "/api/v6"` prefix. Plain `globalThis.fetch('/runs/...')` would NOT reach FastAPI (next.config.ts only rewrites `/api/v6/:path*`) and would 401 without the JWT header — confirmed by Codex iter 1. NEW `web/lib/pin_replay_client.ts` is a thin re-export module exposing the `PinSnapshot` type + the two functions from `api.ts` for ergonomic consumer imports.
6. `web/lib/pin_replay_demo.ts` — REMOVE `DEMO_PIN_REGISTRY` const; KEEP `PinSnapshot` type as a `type` re-export from `pin_replay_client.ts` (back-compat for existing component imports).
7. New `tests/v6/test_pins_route.py` — backend route smoke (200 success path with synthesized fields, 404 on unknown run_id, 404 on completed-but-different-date, multi-run query_slug series ordering).
8. **Minimal page guard:** `web/app/pin_replay/page.tsx` keeps importing `DEMO_PIN_REGISTRY`-via-deprecation-shim. Specifically: `pin_replay_demo.ts` keeps a tiny `DEMO_PIN_REGISTRY = {}` empty object + deprecation comment pointing to Seq 29 #619. The page adds an **empty-state guard at the top of the component** (iter-1 P2 fix): if `PIN_DATES.length === 0`, return an empty-state card with a "No pin data — pin generation lands in #619" message AND skip ALL the `detectRegressions` / delta math (which currently dereferences `DEMO_PIN_REGISTRY[selected_date_a]` and crashes on empty). Existing Playwright specs go to `test.describe.skip()`.
9. **Iter-1 P1-playwright-leftover fix:** `web/tests/e2e/visual_60_baselines.spec.ts` — patch out the F13 row from the `PAGES` array (lines ~78-83) with a comment `// F13 deferred to Seq 29 / I-A-12 / #619 — baseline re-captured after rebuild`. This avoids a runtime failure when the empty-state page is rendered.
10. **Iter-1 P2-duplicate-date fix:** route `GET /runs/{run_id}/pins/{date}` resolves as: "find the snapshot whose run_id == {run_id} path param AND finished_at[:10] == {date} path param". 404 if no match. Multiple runs on the same date are disambiguated by run_id; the route takes both. The list endpoint returns all completed runs sharing the query_slug (with their distinct run_ids embedded in each PinSnapshot).
11. Frontend page rebuild deferred to **Seq 29 / I-A-12 / #619** (already an Issue in the breakdown — "Rebuild /pin_replay").

Estimated canonical diff: **~180-220 LOC** (close to but typically under 200 halt).

### Why this split is honest, not scope-narrowing

- Seq 29 #619 already exists and IS the "rebuild /pin_replay" Issue. Doing FE work here would duplicate Seq 29.
- The `pin_replay_demo.ts` empty-registry + `describe.skip` Playwright migration mirrors the I-cd-013b legacy pattern that Codex APPROVE'd 2026-05-20.
- Acceptance of #627 phrased "A live completed run's pins are replayable through the product pin-replay surface (not demo data)." With this split, the BACKEND route is live; the FRONTEND surface (full UX) lands at Seq 29. Acceptance is met "in two PRs across two Issues" — analogous to how I-cd-016a + I-cd-016b together close #626.

If you reject this split, instruct me to ship the full B in one PR despite the halt-condition. The halt is enforced by Codex review verdict; if you APPROVE the brief, you implicitly grant the LOC exemption.

## §B Acceptance criteria

| Criterion | Met by |
|---|---|
| Backend route `GET /runs/{run_id}/pins` returns ordered `PinSnapshot[]` synthesized from manifest.json files of all completed runs sharing query_slug | `src/polaris_v6/api/pins.py:list_pins` |
| Backend route `GET /runs/{run_id}/pins/{date}` returns the snapshot matching BOTH `run_id` AND `finished_at[:10] == date`; 404 otherwise (duplicate dates across runs of same query disambiguated by run_id) | `src/polaris_v6/api/pins.py:get_pin_by_date` |
| `PinSnapshot` is a frozen Pydantic schema with `extra="forbid"` (matches BundleManifest v1.0 discipline post I-cd-012) | `pin_snapshot.py` |
| 404 for unknown run_id, 404 for date mismatch, 404 for in-progress/aborted runs (only `completed × pipeline_status in {success, partial_*, abort_no_verified_sections}` qualify) | route validation + tests |
| Synthesis source-of-truth for pipeline status: `RunStatusResponse.pipeline_status` from `run_store.get_run(run_id)` (NOT a direct manifest field — manifest top-level uses `status`, and `actors.py:219` translates it; iter-2 P1 fix). Tests use a real `manifest.json` shape with top-level `status`, not `pipeline_status`. |
| Synthesis maps manifest.json `generator` block fields with shape variants handled (iter-2 P1.2 fix): for `pipeline_status == "success"` → `generator.sections_kept` is canonical; for `pipeline_status == "abort_no_verified_sections"` → manifest writes `sections_total` + `sections_dropped` + `sentences_verified` (NO `sections_kept`, NO `sentences_dropped` — confirmed at `scripts/run_honest_sweep_r3.py:2468-2473`). Synthesis function reads defensively: `sections_kept = generator.get("sections_kept", generator.get("sections_total", 0) - generator.get("sections_dropped", 0))`; `sections_dropped = generator.get("sections_dropped", len(generator.get("outline_sections", [])) - sections_kept)`; `verified = generator.get("sentences_verified", 0)`; `dropped_sentences = generator.get("sentences_dropped", 0)`. `pass_rate = verified / (verified + dropped_sentences)` if denominator > 0 else `0.0`. ALL values clamped non-negative. | `pins.py:_synthesize_pin_from_manifest` + new test `test_synthesizes_abort_no_verified_sections` |
| `RunStatusResponse.pipeline_status` (NOT manifest field — see iter-2 P1.1 fix) not in the qualifying set → that run is excluded from the list; per-date 404 if requested | route logic + test |
| `retracted_source_ids` is `None` (not fabricated; honest "not captured today") | schema + synthesis |
| Frontend `web/lib/api.ts` adds `fetchPinList` / `fetchPin` exported functions using `authFetch` + `BACKEND_URL = "/api/v6"`; `web/lib/pin_replay_client.ts` thin-re-exports the two functions + `PinSnapshot` type | api.ts + client lib |
| Existing imports `import type { PinSnapshot } from "@/lib/pin_replay_demo"` continue to resolve via type re-export shim | demo-shim |
| `web/app/pin_replay/page.tsx` guards empty state BEFORE calling `detectRegressions` or referencing `DEMO_PIN_REGISTRY[selected_date]` — returns early with empty-state card | page guard |
| Playwright specs depending on demo dates: `test.describe.skip()` with comment pointing to Seq 29 #619 — INCLUDING `visual_60_baselines.spec.ts` F13 row (patched out of PAGES array) | spec patches |
| New backend tests cover: 200 success path with realistic manifest (top-level `status` key, full `generator` block); 200 abort_no_verified_sections path with the shape-variant generator block (`sections_total` + `sections_dropped` + `sentences_verified`, no `sections_kept`); 404 unknown run; 404 date mismatch; multi-run series ordering by `finished_at ASC`; non-completed run excluded; abort_corpus_inadequate excluded; schema strict validation; pass_rate denominator-zero → 0.0 | `tests/v6/test_pins_route.py` |

## §C Files I have ALSO checked and they're clean

- `src/polaris_graph/audit_ir/model_pin.py` — confirmed `ModelPin` is a DIFFERENT artifact (config-pinning for replay-from-pin); irrelevant for this Issue.
- `src/polaris_graph/audit_ir/pin_replay.py` — phase-2 replay execution; not on this route's hot path.
- `src/polaris_v6/queue/run_store.py:90-135` — schema has `query_slug` indexed column. No new migration needed; existing `_migrate_schema` is additive-idempotent.
- `src/polaris_v6/queue/actors.py:128,207-214` — `out_root_override` ensures pipeline-A writes `manifest.json` to `artifact_dir`. Confirmed manifest path is `{artifact_dir}/manifest.json`.
- `src/polaris_v6/queue/actors.py:219` — `pipeline_status = manifest.get("status") or "error_unexpected"` — confirmed the v6 actor translates manifest top-level `status` → `RunStatusResponse.pipeline_status`. The route reads `RunStatusResponse.pipeline_status` from `run_store`, NOT the raw manifest field (iter-2 P1.1 fix).
- `scripts/run_honest_sweep_r3.py:2460-2473` — `abort_no_verified_sections` writes `generator: {outline_sections, sections_total, sections_dropped, sentences_verified}` — NO `sections_kept`, NO `sentences_dropped` field. Synthesis function handles both shape variants defensively (iter-2 P1.2 fix).
- `src/polaris_v6/schemas/run_status.py:LifecycleStatus, PipelineStatus` — Literal types include the qualifying set; the route's filter list mirrors them.
- `outputs/honest_sweep_r3/clinical/clinical_tirzepatide_t2dm/manifest.json` (real example) — `generator.sections_kept=4`, `generator.outline_sections=5`, `generator.sentences_verified=14`, `generator.sentences_dropped=45`. Synthesis math: `pass_rate = 14/(14+45) = 0.237`; `section_count_dropped = 5-4 = 1`. Wired to PinSnapshot.
- `web/lib/pin_regression.ts:7` — `import type { PinSnapshot } from "@/lib/pin_replay_demo"` — will resolve via re-export shim, no change needed.
- `web/app/pin_replay/components/{diff_side_panel,pin_timeseries}.tsx` — both consume `PinSnapshot`; will resolve via re-export shim. They'll receive empty arrays via the empty-state page; no crash.
- `web/tests/e2e/{pin_replay,pin_replay_diff,pin_regression_alert,pin_retraction_handled}.spec.ts` — all assume demo dropdown; all go to `test.describe.skip()` with `// Re-enable at Seq 29 / I-A-12 / #619 rebuild of /pin_replay`.
- `web/tests/e2e/visual_60_baselines.spec.ts:78-83` — F13 row patched out of PAGES array with `// F13 deferred to Seq 29 / I-A-12 / #619` comment (iter-1 P1 fix).
- `web/tests/e2e/perf_core_web_vitals.spec.ts` — touches `/pin_replay` path; if it relies on demo content, also skipped with same comment.
- `web/lib/api.ts:authFetch` is module-private; the new `fetchPinList`/`fetchPin` exported functions live IN `api.ts` to use it; `pin_replay_client.ts` is a re-export shim only.
- `src/polaris_v6/api/app.py:92-106` — router registration is at line ~94 for runs_router; pins_router goes after bundle_router for grouping. No `prefix="/api"` (matches inspector + bundle pattern which are bare `/runs`).
- No new requirements: `httpx` (frontend fetch is browser-native `fetch`), Pydantic, FastAPI, pytest all already pinned.

## §D Codex Red-Team checklist

1. Synthesis math correctness — `pass_rate` denominator includes both verified + dropped (not just verified); clamp [0,1]; handle `sentences_verified == 0 AND sentences_dropped == 0` (e.g. abort_no_verified_sections with zero generator activity) → return `0.0` not NaN. Also handle the abort-shape variant where `sentences_dropped` key is absent (iter-2 P1.2): `sentences_dropped = generator.get("sentences_dropped", 0)`.
2. `query_slug` lookup safety — slug is normalized; user-supplied run_id resolves to slug via run_store; route does NOT accept raw query_slug as input (`{run_id}` only).
3. Date format strictness — `{date}` path param matches `\d{4}-\d{2}-\d{2}` ISO; non-matching → 422 (FastAPI's regex constraint pattern).
4. Multi-run series ordering — `finished_at ASC` (oldest first) so the timeseries renders left-to-right chronologically.
5. Manifest-read robustness — missing `manifest.json` (impossible for completed run but handle defensively) → exclude that run from the list, NOT 500.
6. Two-family segregation — N/A (no LLM calls in this route; pure read-from-disk).
7. Empty list — `GET /runs/{run_id}/pins` returns `[]` (HTTP 200) when run exists but its query_slug has no completed runs (impossible? since the run itself is completed) — actually means: any completed run with that query_slug always has ≥1 pin. Empty list happens only for unknown run_id, which is 404 instead.
8. `pin_date` derivation — `finished_at` is ISO timestamp; the pin_date is `finished_at[:10]` (the YYYY-MM-DD prefix). Multiple runs of same query on same date → 2 pins with same `pin_date` but different `run_id` — schema includes `run_id` to disambiguate.
9. Aborted runs — `abort_no_verified_sections` is INCLUDED (it produced data; verified count is 0 but the snapshot is informative). Other `abort_*` and `error_*` excluded. Confirmed by Carney-demo use case: showing "this query aborted on date X but produced N pins on date Y" is the regression visibility the demo needs.
10. `PinSnapshot.verdict` Literal needs to widen from `"success" | "abort_no_verified_sections"` to also cover the partial-* statuses — proposal: keep as `Literal["success", "abort_no_verified_sections"]` and synthesize `partial_*` → `"success"` (they did produce verified output). Document this collapsing in the synthesis function docstring.
11. The frontend shim — `pin_replay_demo.ts` keeps `export const DEMO_PIN_REGISTRY: Record<string, PinSnapshot> = {}` + `export type { PinSnapshot } from "@/lib/pin_replay_client"`. Existing imports from `pin_replay_demo` work; runtime registry is empty.
12. Authentication — `/runs/*` are currently authenticated via `require_auth` (I-carney-004) — confirm pins routes follow the same protection. If `runs_router` uses `Depends(require_auth)`, pins_router must too.

## §E Smoke test (will run before pushing diff)

```bash
cd /c/POLARIS
# (a) Unit-level synthesis math
python -c "
import sys; sys.path.insert(0, 'src')
from polaris_v6.schemas.pin_snapshot import PinSnapshot
print('schema imports OK')
"
# (b) Backend pytest (route + synthesis)
python -m pytest tests/v6/test_pins_route.py -v
# (c) Web TypeScript build (catches client lib type errors)
cd web && npx tsc --noEmit
# (d) Web Playwright dry-run (verify describe.skip in place)
npx playwright test pin_replay --reporter=line --list
```

## §F Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Return JSON-shaped verdict block above + 1-2 sentences explaining the convergence call.
