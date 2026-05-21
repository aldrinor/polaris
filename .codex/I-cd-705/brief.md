# Codex review — I-cd-705 GET /api/v6/runs list endpoint

HARD ITERATION CAP: 5. iter 1. Front-load ALL findings. "Don't pick bone from egg" — P0/P1 for real execution risks only. APPROVE iff zero P0 + zero P1. Per merge protocol (.codex/I-cd-567/DECISION.md) final line includes MERGE AUTHORIZED if mergeable. Touches only src/polaris_v6/** + tests/** (not operator-only exclusion list).

Canonical-diff-sha256: ``. 3 files.

## What this implements (PHASE 1 P1-3)
The backend lacked a runs LIST endpoint (only POST /runs, GET /runs/{id}, cancel). The home recent-runs strip + follow-up picker (#542) + compare picker (#543) need to list real completed runs.

- run_store.list_completed_runs(limit): completed + non-aborted, newest-first (finished_at DESC), capped. Excludes abort_* pipeline_status. release_allowed enforced downstream at fetch (#680). LIKE 'abort\_%' ESCAPE so the literal underscore matches.
- GET /runs (status=completed only → else 400; limit clamped [1,100]).
- 6 tests + 6 existing = 12 pass.

## Review focus
1. Route ordering: GET "" (list) vs GET "/{run_id}" — any FastAPI path-match ambiguity? (list registered before /{run_id}.)
2. The SQL abort exclusion: `pipeline_status IS NULL OR pipeline_status NOT LIKE 'abort\_%' ESCAPE '\'` — correct to keep NULL-status completed runs + exclude abort_*?
3. limit clamp [1,100] + status!=completed → 400. Sensible contract?
4. Any auth gap (endpoint relies on app-level auth like the sibling GET /runs/{id})?
5. Any NOVEL P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
remaining_blockers_for_execution: [...]
```
