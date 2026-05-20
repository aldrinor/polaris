HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- "Don't pick bone from egg" — P1 only for real execution risks.
- If iter 5 returns REQUEST_CHANGES, Claude force-APPROVE's on non-P0/P1 residuals.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex brief review — I-cd-018 (#628) — document-grounding follow-up

## §A Scope (parent #537 — narrowed by reality)

Parent #537 listed 3 sub-tasks (P2-1, P2-2, P2-3) at I-rdy-010 time. State today (verified by grep 2026-05-20):

- **P2-1 (graph_v4 grounding shape mismatch) — MOOT.** `graph_v4.py` no longer exists anywhere in the tree (`ls src/polaris_graph/graph_v4.py` returns nothing). The `live_server /api/research` path now consumes uploads via `pipeline_a_ui_adapter.py:242` using the same `uploaded_documents` key + shape as the v6 actor. Nothing to fix.
- **P2-2 (RunRequest.document_ids has no max item count) — actionable.** Current `RunRequest.document_ids: list[str] = Field(default_factory=list, ...)` has no bound. Many `PUBLIC_SYNTHETIC` uploads can inflate the actor message + generator prompt.
- **P2-3 (error-manifest omits upload counts) — actionable.** Three error paths (pipeline_exception, manifest_missing, manifest_invalid) at `src/polaris_v6/queue/actors.py:197-220` call `run_store.mark_failed(...)` without surfacing `uploaded_documents_used` / `uploaded_documents_blocked` for observability. The success path at actors.py:140-150 already logs them.

### Implementation

1. `src/polaris_v6/schemas/run_request.py` — add `max_length=20` to `document_ids`. Rationale: 20 docs × 40 chunks-per-doc = 800 chunks ceiling, matching the existing `MAX_GROUNDING_CHUNKS=40` per-doc cap. Test: POST /runs with 21 ids → 422.
2. `src/polaris_v6/queue/run_store.py` — extend `mark_failed(run_id, error, ...)` signature with optional `uploaded_documents_used` + `uploaded_documents_blocked` keyword args that thread into the SQL `error_json` field. Backwards-compat: existing callers omit them; the SQL UPDATE remains safe.
3. `src/polaris_v6/queue/actors.py` — pass `uploaded_documents_used=len(allowed_uploads)` + `uploaded_documents_blocked=len(blocked_uploads)` at all three error sites (pipeline_exception, manifest_missing, manifest_invalid).
4. Tests: extend `tests/v6/test_actors.py` (or add new `tests/v6/test_actors_upload_error_path.py`) covering all three error paths surface the upload counts.

Estimated canonical diff: **~120-160 LOC** (within 200 halt).

## §B Acceptance criteria

| Criterion | Met by |
|---|---|
| `RunRequest.document_ids` enforces max-item count | run_request.py + 422 test |
| 422 returned when count exceeded; no actor enqueue happens | runs.py is unchanged — FastAPI's request validation runs BEFORE the handler |
| `mark_failed` accepts optional `uploaded_documents_used` + `uploaded_documents_blocked` | run_store.py signature change |
| All 3 actor error sites pass the upload counts | actors.py:204, 209, 216 |
| error_json column contains the counts (visible via GET /runs/{id}) | run_store.py + RunStatusResponse passthrough OR error_json contents |
| Tests cover all 3 error paths surfacing counts | tests/v6/ new or extended |

## §C Codex Red-Team checklist

1. `max_length=20` — is 20 the right ceiling? 20 docs × 40 chunks = 800 chunks; PUBLIC_SYNTHETIC corpus on Carney-demo profile is typically <10. Justifiable as breathing-room cap.
2. error_json shape — currently freeform JSON. Adding new keys breaks no existing reader IF readers do `.get()`; check `RunStatusResponse._row_to_response` parsing.
3. Backwards-compat — existing test_actors.py uses `mark_failed(run_id, error)` positional. Keyword args MUST be optional with defaults, NOT new positionals.
4. Logging at success path is already INFO-level; error-path counts are persisted to DB (not just logged) per the observability gap framing in #537.
5. The 22 of `document_ids` field in `RunRequest` IS the same as `RunRequest.document_ids` in `tests/v6/`'s existing fixtures? Confirm.
6. POST /runs handler at runs.py:85 calls `_resolve_uploaded_documents(payload.document_ids)` — if the new max_length=20 raises 422 BEFORE the handler runs, no actor enqueue happens. Existing concurrency-gate test stays valid.
7. The actor uses `len(allowed_uploads)` — that's the post-sovereignty-filter count. The Issue framing was "uploaded_documents_used" — confirm semantics match.
8. The block-count `len(blocked_uploads)` is the sovereignty-filtered-OUT count, NOT the user-requested-but-missing count. Semantically distinct; document in the field name.

## §D Files I have ALSO checked and they're clean

- `src/polaris_graph/graph_v4.py` — does not exist; P2-1 moot.
- `src/polaris_graph/pipeline_a_ui_adapter.py:242` — uses `uploaded_documents` key, same shape as v6 actor; no migration needed.
- `src/polaris_graph/state.py:568,684` — `uploaded_documents: list[dict]` field shape matches.
- `src/polaris_graph/graph.py:1375` — state assignment matches.
- `src/polaris_graph/agents/analyzer.py:1286`, `planner.py:165` — consumers read same key.
- `src/polaris_v6/adapters/upload_evidence.py:39,47,51,67` — shape is `{document_id, classification, filename, chunks}`.
- `src/polaris_v6/api/runs.py:40,85` — resolver reads `payload.document_ids`; will respect max_length validation at parse time.
- `src/polaris_v6/queue/actors.py:140-150,197,209,216` — three error sites identified.
- `src/polaris_v6/schemas/run_request.py` — no existing max_length on document_ids.
- `tests/v6/test_actors.py` — existing tests do not exercise the error paths with uploads; new tests needed.

## §E Smoke test (will run before pushing diff)

```bash
PYTHONPATH=src python -m pytest tests/v6/test_actors.py tests/v6/test_api_runs.py -v
cd web && npx tsc --noEmit  # confirm no client breaks (no client API surface change expected)
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
