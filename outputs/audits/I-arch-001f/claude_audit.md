# I-arch-001f Claude architect audit

**Issue:** GH#468 — e2e test with pinned AuditIR fixture + full POST→graph→bundle→compare chain
**Branch:** `bot/I-arch-001f-e2e-pinned-fixture`
**Codex brief verdict:** APPROVE iter 3 of 5
**Codex diff verdict:** APPROVE iter 2 of 5

## Surface

Single new test file `tests/v6/test_end_to_end_arch_001f.py` (~290 LOC, 1 test) pinning the I-arch-001a..001e architectural seam end-to-end:

1. POST `/runs` → 202 + uuid + `lifecycle_status="queued"`
2. Simulate pipeline-A side-effects (manifest patch, `run_store.set_pipeline_meta(**kwargs)`, `emit_event`/`emit_terminal_event`, `mark_completed`)
3. GET `/runs/{uuid}` → 200 + `lifecycle_status="completed"` + `pipeline_status="success"`
4. GET `/stream/{uuid}` (fakeredis-backed) → SSE: `scope_decision` + `run_complete` v6 events
5. GET `/stream/{uuid}` with `Last-Event-ID: <first_id>` → only `run_complete` (resume semantics)
6. GET `/runs/{uuid}/bundle.tar.gz` with signer override → 200 application/gzip
7. Extract tar; verify FK chain: `manifest.report_id == report.report_id`, `manifest.decision_id == report.decision_id == f"dec-{uuid}"`, `manifest.pool_id == report.pool_id`

## Codex iteration trail

| Doc | Iter | Outcome | Real findings |
|---|---|---|---|
| brief | 1 | REQUEST_CHANGES | P1-001 fixture run_id; P1-002 RUN_DB isolation; P1-003 Last-Event-ID resume; P1-004 keyword-only set_pipeline_meta |
| brief | 2 | REQUEST_CHANGES | P1-005 broker.flush_all (not flush_queue); P1-006 manifest.yaml + verified_report.json (not manifest.json) |
| brief | 3 | **APPROVE** | zero P0/P1 |
| diff | 1 | REQUEST_CHANGES | P1 cited_span_unreachable: synthetic fixture missing evidence_pool.json with long full_text |
| diff | 2 | **APPROVE** | zero P0/P1 |

## Iter-1 diff finding addressed

Codex diff iter-1 caught a real bug: `if bundle_resp.status_code == 200:` guard silently skipped all tar/manifest assertions, even though the bundle endpoint was returning 400 `cited_span_unreachable_after_snapshot`. The synthetic fixture's bibliography statements were 35 chars but sentences cited span 0-100; without `evidence_pool.json`, `Source.full_text` was None, so `_snapshot_text` used the 35-char snippet, so the 100-char span was unreachable.

Fix: add `evidence_pool.json` with `sources: [{evidence_id, full_text}]` where `full_text` is padded >100 chars. Asserts now hard-require `status_code == 200`, drop the conditional guard, assert `pool_id` unconditionally, drop unused `Path` import.

## Test evidence

```
$ python -m pytest tests/v6/test_end_to_end_arch_001f.py -x
1 passed in 1.60s
```

Test hermetic: no real Redis (fakeredis FakeServer), no real LLM, no network. Asserts the architectural seam end-to-end so any I-arch-001a..001e regression breaks one obvious assertion.

## Regressions this test catches (per acceptance criteria)

- `run_store.mark_completed` schema drift
- `bundle.py` Depends(get_sign_fn) callable identity (I-arch-001d P1-001)
- `stream.py` Last-Event-ID header parsing (I-arch-001e Header alias)
- `run_events.translate` 6-event mapping (I-arch-001e)
- `artifact_to_slice_chain` ScopeDecision / EvidencePool / VerifiedReport schemas (I-arch-001d)
- `snapshot_sources` cited-span resolution (I-arch-001d audit_bundle gate)

## Deferred (P2/P3)

- PyYAML direct pin in `requirements-v6.txt` (Codex iter-3 P2): deferred to a hygiene PR; bundle manifest serialization already imports yaml transitively, so this isn't a new runtime dependency.
- Docstring `iter 3 of 5` reference in test (Codex iter-2 diff P3 cosmetic): test was authored against brief iter 3 of 5 so the reference is intentionally accurate; leaving as-is.

## Verdict

READY TO MERGE. All Codex required artifacts present:
- `.codex/I-arch-001f/brief.md` + `brief_iter_2.md` + `brief_iter_3.md`
- `.codex/I-arch-001f/codex_brief_verdict.txt` (APPROVE)
- `.codex/I-arch-001f/codex_diff.patch`
- `.codex/I-arch-001f/codex_diff_audit_iter_2.txt` (APPROVE)
- `outputs/audits/I-arch-001f/claude_audit.md` (this file)
