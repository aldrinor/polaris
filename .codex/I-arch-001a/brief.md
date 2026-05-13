HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-arch-001a — run_store atomic schema + UUID/slug/artifact_dir mapping + pipeline-A manifest augmentation

GH#463. Day 1-3 of the I-carney-001 Posture C 24-day plan. Foundation issue: unblocks I-arch-001b/c/d/e/f.

## Acceptance criteria

1. **run_store schema migration** (additive, backward-compatible):
   - Add columns: `query_slug TEXT`, `manifest_run_id TEXT`, `artifact_dir TEXT`, `pipeline_status TEXT`, `cost_usd REAL`, `decision_id TEXT`
   - Keep existing: `run_id` (PK, UUID hex), `template`, `question`, `status` (now `lifecycle_status` per Codex iter-4 P2.1), `queued_at`, `started_at`, `finished_at`, `result_json`, `error_json`
   - Rename `status` → `lifecycle_status` via ALTER TABLE (idempotent migration)
   - Indexes on `query_slug`, `manifest_run_id`

2. **RunStatus Literal expansion** (`src/polaris_v6/schemas/run_status.py`):
   - `LifecycleStatus`: `Literal["queued", "in_progress", "completed", "cancelled", "failed"]`
   - `PipelineStatus`: `Literal[<full taxonomy>]` per Codex iter-5 P2.1 — include partial_thin_corpus, partial_incomplete_corpus, partial_outline_fallback, partial_qwen_advisory, partial_rule_check_warnings, abort_scope_rejected, abort_corpus_inadequate, abort_corpus_approval_denied, abort_no_verified_sections, abort_no_sources, abort_evaluator_critical, abort_quota_exceeded, error_unexpected, success
   - `RunStatusResponse` adds: `lifecycle_status`, `pipeline_status`, `query_slug`, `manifest_run_id`, `artifact_dir`, `cost_usd`, `decision_id`
   - Old `status` field stays for backcompat at response shape; populated from `lifecycle_status`

3. **run_store helpers**:
   - `mark_in_progress(run_id)` — UPDATE lifecycle_status='in_progress', started_at=now
   - `mark_completed(run_id, result, *, query_slug, manifest_run_id, artifact_dir, pipeline_status, cost_usd)` — atomic UPDATE all fields + lifecycle_status='completed'
   - `mark_failed(run_id, error)` — NEW per CLAUDE.md §8.3.1 force-APPROVE residual + Codex iter-2 P2.1. UPDATE lifecycle_status='failed', pipeline_status='error_unexpected', error_json=json.dumps({"error": error}), finished_at=now
   - `mark_aborted(run_id, pipeline_status, abort_reason)` — UPDATE lifecycle_status='completed' (still ran to completion, just aborted at a gate), pipeline_status=<one of abort_*>, finished_at=now
   - `set_pipeline_meta(run_id, query_slug, manifest_run_id, artifact_dir, decision_id)` — set after pipeline-A starts but before completion (idempotent)
   - `get_run(run_id)` — returns full RunStatusResponse with new fields populated

4. **Pipeline-A patches in `scripts/run_honest_sweep_r3.py`** (~40 LOC additive, NO existing-behavior change):
   - Read `POLARIS_V6_EXTERNAL_RUN_ID` env; if set, write that as `manifest.external_run_id`
   - Read `POLARIS_V6_DECISION_ID` env; if set, write to `manifest.scope.decision_id`; else mint new UUID and write
   - Augment manifest writes (at line ~1331, ~1453, success path):
     - `manifest.retrieval` block: `started_at`, `finished_at`, `latency_ms`, `cost_usd`, `queries_executed` (list), `pool_id` (UUID)
     - `manifest.adequacy` block: `decision`, `reason`, `score` (mapped from existing adequacy variables)
     - `manifest.models` block: `generator`, `evaluator` (already-known model IDs)
   - Bibliography augmentation (`bibliography.json` write): add `domain`, `title`, `publication_date`, `authors`, `fetched_at_utc`, `legal_cleared` (bool, default True for T1), `retracted` (bool, default False) to each entry
   - All additions guarded by `if os.environ.get("POLARIS_V6_MODE") == "1":` so non-v6 sweep invocations stay byte-identical to today

5. **actors.py wiring**:
   - Before invoking pipeline-A: `os.environ["POLARIS_V6_EXTERNAL_RUN_ID"] = run_id`; `os.environ["POLARIS_V6_DECISION_ID"] = str(uuid.uuid4())` (passed forward); `os.environ["POLARIS_V6_MODE"] = "1"`
   - After pipeline-A completes: read `manifest.json` from artifact_dir; extract `query_slug`/`manifest_run_id`/`pipeline_status`/`cost_usd`; `run_store.set_pipeline_meta(...)` + `run_store.mark_completed(...)` OR `mark_aborted(...)` depending on pipeline_status
   - Stub-mode path (`run_store.get_run(run_id) is None`) preserved for tests

6. **Tests**:
   - `tests/polaris_v6/queue/test_run_store.py`: schema migration round-trip; insert_run + set_pipeline_meta + mark_completed → get_run returns all fields; mark_failed → status='failed'; mark_aborted with each abort_* status
   - `tests/polaris_v6/queue/test_actors.py`: stub-mode preserved; full-mode set_pipeline_meta wiring (mock pipeline-A invocation)
   - `tests/polaris_graph/test_manifest_augmentation.py`: with `POLARIS_V6_MODE=1` + envs set, manifest.json contains new blocks; without env, unchanged byte-identical (parameterized smoke against existing canonical sweep slug)

7. **LOC budget**: 200 LOC total diff (combined run_store + run_status + runs.py + actors.py + run_honest_sweep_r3.py + 3 test files). Pipeline-A patch ~40 LOC of the 200.

## Files I have ALSO checked and they're clean (per §-1.2 #2)

- `src/polaris_v6/queue/run_store.py:78,92,105,118` — current schema + helpers (insert_run, mark_in_progress, mark_completed, get_run); NO mark_failed yet (the module docstring explicitly says deferred)
- `src/polaris_v6/api/runs.py:27,37,45` — single insert + 2 get callers; safe to extend response shape
- `src/polaris_v6/queue/actors.py:54-56` — stub-mode body; will be the wiring site
- `src/polaris_v6/schemas/run_status.py` — current Literal has 9 values; need to expand to 15+ (lifecycle 5 + pipeline 13+)
- `scripts/run_honest_sweep_r3.py:1331,1453,1467,1493` — 4 manifest-write sites; all use `json.dumps(..., sort_keys=True, indent=2)` pattern; augmentation goes BEFORE the json.dumps call
- `scripts/run_honest_sweep_r3.py:165-183` — pipeline_status taxonomy reference; my brief enum should match exactly
- `src/polaris_graph/scope/scope_decision.py:151-153` — `decision_id` field exists with `default_factory=lambda: str(uuid.uuid4())` (per Codex iter-4); I will pass POLARIS_V6_DECISION_ID via env, pipeline-A writes to manifest.scope.decision_id BEFORE constructing ScopeDecision, then ScopeDecision uses the pre-minted value

## Smoke test plan (§-1.2 #3, before brief APPROVE)

I will run BEFORE writing the diff:
1. `pytest tests/polaris_v6/queue/test_run_store.py -x` (existing tests pass on current schema)
2. `python -c "from polaris_v6.queue.run_store import init_db; init_db('/tmp/test.db'); print('OK')"` (schema init works on fresh DB)
3. Brief manifest inspection: read `outputs/v30_phase2_carney_canonical_demo/manifest.json` to confirm current shape and identify which fields I'm ADDING vs ALREADY-PRESENT (don't double-write)

## Direct questions for iter 1

1. Schema migration approach: ALTER TABLE column-by-column (idempotent, runs on init_db each boot) — APPROVE'd? Or want a numbered migration table (`runs_schema_version`)?
2. `lifecycle_status` rename from `status`: do a 1-time ALTER (drop old `status`, add new `lifecycle_status`) — APPROVE'd, or keep both for transition period?
3. `POLARIS_V6_MODE=1` env guard on pipeline-A augmentation — APPROVE'd as the "no v6 behavior change for legacy CLI sweep" lock?
4. New `mark_aborted` helper handling `lifecycle_status='completed' + pipeline_status='abort_*'` — APPROVE'd? Or should abort_* map to `lifecycle_status='failed'`?
5. Bibliography augmentation: do I extend the existing `bibliography.json` shape OR write a sidecar `bibliography_extras.json` (Codex iter-2 brief proposed either)? Recommend extending for simplicity; only adds optional fields.
6. Test for byte-identical-when-POLARIS_V6_MODE-unset: parameterize against an existing canonical run + diff manifest.json — APPROVE'd test approach, or stricter (snapshot full run output)?
7. LOC budget 200 across 6 files — tight but doable? Or split into I-arch-001a-1 (run_store + run_status) + I-arch-001a-2 (pipeline-A patches)?

## Resource discipline (§8.4)

Pre-task: 1 node (44208, idle ~33s CPU). Will kill before next Codex run. No pipeline-A end-to-end runs during this Issue (smoke uses init_db + unit tests only).

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
