HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- "Don't pick bone from egg" — P1 only for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff review — I-cd-018 (#628)

Brief APPROVE'd iter 1. Canonical-diff-sha256: `dfee9e5796fe70678d2ffe03c01dafda7955463a916b90fb6f5bfab3ccd84e5b`. 298-line patch.

## §A Canonical diff summary

- `src/polaris_v6/schemas/run_request.py` — `document_ids: max_length=20` added + description updated.
- `src/polaris_v6/queue/run_store.py:388` — `mark_failed` signature extended with optional kwargs `uploaded_documents_used` + `uploaded_documents_blocked`; both keys conditionally added to `error_json`.
- `src/polaris_v6/queue/actors.py:195+` — pre-compute `upload_counts: dict[str, int]` after `partition_uploads_by_sovereignty`; pass `**upload_counts` to all three error-path `mark_failed` calls (pipeline_exception, manifest_missing, manifest_invalid).
- `tests/v6/test_actors_upload_error_path.py` NEW — 5 tests: 3 error paths + 422 cap + 20-accept boundary.

## §B Acceptance check

| Criterion | Met by |
|---|---|
| `RunRequest.document_ids` rejects 21 items | run_request.py:max_length=20 + test_run_request_document_ids_cap_rejects_21 (422) |
| `RunRequest.document_ids` accepts 20 items | test_run_request_document_ids_accepts_20 |
| `mark_failed` signature backwards-compatible (kwargs-only additions) | run_store.py:388-407 |
| Three actor error sites pass upload counts | actors.py:208/214/220 (lines may shift; all three `mark_failed` calls now `**upload_counts`) |
| Counts surface in `error_json` SQL column | _read_error_json helper in test reads + asserts |
| Existing v6 test suite remains green | `pytest tests/v6/test_actors.py tests/v6/test_api_health_and_runs.py` → 14 passed |

## §C Red-team checklist

1. `mark_failed` callers in other modules — checked: only `enqueue_research_run` actor calls it across src/. Old positional signature preserved (`mark_failed(run_id, error)` still works); new kwargs default to None.
2. error_json is freeform JSON — `_row_to_response` parses error_json into a dict for the API; new keys (`uploaded_documents_used`, `uploaded_documents_blocked`) don't break any consumer since they're added optionally.
3. POST /runs at runs.py:81 — when payload validation fails (21 ids), FastAPI returns 422 BEFORE entering the handler body. `_resolve_uploaded_documents` (which returns 400 on missing id) never runs.
4. The `actors.py` per-iteration `upload_counts` dict captures the post-sovereignty-filter `allowed_uploads` size — same semantics as the success-path INFO log.
5. `mark_failed` writes `error_json = json.dumps(error_payload, sort_keys=True)` — sort_keys keeps test diff-stable.
6. 5/5 new tests pass via the v6 actor's `.fn()` direct-invoke path with pre-inserted run row (per Codex brief iter-1 P2 caveat acknowledged).
7. No frontend-visible change; web/ TypeScript untouched.

## §D Smoke test result

```
$ PYTHONPATH=src python -m pytest tests/v6/test_actors_upload_error_path.py tests/v6/test_actors.py tests/v6/test_api_health_and_runs.py -v
19 passed
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
