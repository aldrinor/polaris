# Claude audit — I-cd-018 (#628)

## Scope verified against parent #537

Parent #537 listed three sub-tasks at I-rdy-010 time:

- **P2-1 (graph_v4 grounding shape)** — MOOT. `graph_v4.py` no longer exists; `pipeline_a_ui_adapter.py` already consumes uploads via the v6-shape `uploaded_documents` key. Nothing to fix.
- **P2-2 (RunRequest.document_ids cap)** — fixed. `max_length=20` on the field; 422 on 21+ items; 20 accepted.
- **P2-3 (error-manifest upload counts)** — fixed. `mark_failed` accepts optional `uploaded_documents_used` + `uploaded_documents_blocked` kwargs; actor passes them at all 3 error sites.

## Tests

- 5 new tests in `tests/v6/test_actors_upload_error_path.py` (all green).
- Existing `tests/v6/test_actors.py` + `tests/v6/test_api_health_and_runs.py` → 14 passing.

## Quality bar

- Codex brief APPROVE iter 1; diff APPROVE iter 1.
- No P0/P1.
- Two P2s from brief iter 1 (test path naming + actor stub caveat) were acknowledged and addressed in implementation (`test_actors_upload_error_path.py` pre-inserts run rows; smoke ran `tests/v6/test_api_health_and_runs.py`).

## Files I have checked clean

`.codex/I-cd-018/brief.md` §D lists all adjacent files verified clean. No outstanding follow-up against this Issue.
