# Claude architect audit — I-rdy-010 (#506): async worker consumes uploaded document_ids

**Issue:** GH #506 — the v6 worker actor passes uploaded `document_ids` into the
research pipeline; F3 works end-to-end. Acceptance: uploaded-document evidence
appears in a live run's report; sovereignty routing for CLIENT docs holds.

**Commit:** `52275e44` on `bot/I-rdy-010-document-grounding` (off `polaris` @
`9185035e`). 6 files, +460/-1. Canonical-diff-sha256
`f21e24f14a8c67f8a7b0e529623147f6a2ec437fc644f8ae677f723dd2d70876`.

## The gap this closes (grounded)

Four breaks, all verified in the code:
1. `enqueue_research_run` (`queue/actors.py`) built its `q`-dict from only
   `template`+`question` — `document_ids` from the `RunRequest` were never read.
2. Uploads live in `api/upload.py:_UPLOAD_TABLE`, an in-memory dict in the API
   process — invisible to the separate Dramatiq worker.
3. `run_one_query` (pipeline-A) had zero upload/document_id handling.
4. No sovereignty gate on uploaded documents — a CLIENT doc reaching the
   external generator would be a leak.

## Acceptance check

- **"Uploaded-document evidence appears in a live run's report."** `POST /runs`
  resolves `document_ids` → content (`_resolve_uploaded_documents`); the actor
  passes the sovereignty-cleared uploads into `q["uploaded_documents"]`;
  `run_one_query` builds evidence dict rows (`build_upload_evidence_rows`) and
  prepends them onto `evidence_for_gen` — the exact mechanism the V30-P2
  contract rows use (`run_honest_sweep_r3.py:2089`). They flow into the
  generator AND into `ev_pool` (`:2550`) → `evidence_pool.json` (`:2611`) → the
  report bibliography + the line-by-line audit harness. The row shape matches
  `_contract_evidence_rows` (`:2044-2059`) exactly.
- **"Sovereignty routing for CLIENT docs holds."** The generator is an external
  LLM call. `partition_uploads_by_sovereignty` (delegating to the existing
  `sovereignty/router.filter_for_external_egress`) splits uploads: only
  `PUBLIC_SYNTHETIC` reaches `q`; `CLIENT`/`CAN_REAL`/`PRIVATE`/`UNKNOWN` are
  blocked at the actor stage and never forwarded. A belt-and-suspenders re-check
  in `build_upload_evidence_rows` *raises* `UploadSovereigntyError` if a
  forbidden doc somehow reaches row construction — fail loud, never a silent
  pass. Blocked/used counts ride the manifest + log (metadata-only — document
  text is never logged).

## Codex brief APPROVE rulings honored

`content_transport_ruling=option-a-embed` (resolve at `/runs`, embed in actor
message — no new persistence module, robust across the API/worker process
boundary). `scope_ruling=single-pr-cap-exemption`. `merger_ruling=direct-dict-rows`
(the unwired `evidence_pool_merger` emits `SourceSpan`, the wrong shape for
pipeline-A's dict rows — direct rows match `_contract_evidence_rows`).
`sovereignty_surface_ruling=manifest-and-log-ok`.

The five iter-1 P2 guardrails are all implemented: re-chunk `record.content`
(not the 3-chunk preview); resolve+validate BEFORE `insert_run`/`enqueue`;
unparsed pdf/docx → HTTP 400 (fail loud, no silent zero-evidence run);
blocked-doc observability is metadata-only counts; `MAX_GROUNDING_CHUNKS=40`
caps the embedded actor-message payload (uploads can be 50 MB).

## Fail-loud review (LAW II)

- Missing `document_id` → HTTP 400 at `/runs` (before any run row is created).
- Unparsed upload (no extractable text) → HTTP 400 — not a silent zero-evidence
  run.
- Forbidden classification reaching `build_upload_evidence_rows` →
  `UploadSovereigntyError` → propagates to `run_one_query`'s error handler →
  `error_*` manifest → actor `mark_failed`. No silent leak.
- A run with no uploads: `q.get("uploaded_documents")` is `[]`, the injection
  block is skipped — zero behavior change for existing runs.

## Tests

`tests/v6/test_document_grounding.py` — 14 tests, all pass locally (offline,
no network): `chunk_text` cap/empty; `get_upload_record`;
`_resolve_uploaded_documents` happy + missing-id-400 + unparsed-400;
`partition_uploads_by_sovereignty` allow/block split; `build_upload_evidence_rows`
row shape + empty-chunk skip + forbidden-classification rejection. Import smoke
clean on all 5 touched modules incl. `run_honest_sweep_r3.py`. `test_actors.py`
8/8 — actor not regressed. `test_api_health_and_runs.py` errors are the
pre-existing gpg-`OSError` in `create_app()` on this gpg-less dev host
(untouched file; identical to `test_api_bundle.py`).

A full live `run_one_query` proving uploaded evidence in a rendered `report.md`
needs network + the generator API + cost — CI/e2e territory, not the autonomous
loop (CLAUDE.md §8.4). The injected-row logic is unit-tested; the prepend is a
one-liner mirroring the proven V30-P2 pattern.

## Residual / follow-up

- Uploads are still not durable across an API-process restart between upload and
  run-create (pre-existing `_UPLOAD_TABLE` limitation — Codex brief-iter-1
  explicitly ruled a durable upload store a separate follow-up, not a #506
  blocker). Acceptable for a single demo session.
- pdf/docx parsing is still unimplemented in `upload.py`; #506 fails such
  uploads loud rather than grounding on them.

## Verdict

The diff implements the APPROVE'd brief end-to-end, all five P2 guardrails are
in, fail-loud holds at every stage, sovereignty is enforced at the actor with a
belt-and-suspenders re-check, and tests cover every resolution + sovereignty +
row-build path. Ready for Codex diff review.
