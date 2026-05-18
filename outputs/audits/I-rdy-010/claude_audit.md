# Claude architect audit — GH #506 (I-rdy-010)

**Issue:** GH #506 (I-rdy-010) — Phase 3.7: document grounding — the async
worker consumes uploaded `document_ids`. Acceptance: uploaded-document
evidence appears in a live run's report; sovereignty routing for CLIENT
docs holds; Codex APPROVE.
**Branch:** `bot/I-rdy-010` off `polaris` HEAD `30c0b488`.
**Commit 1:** `8179fc03` — 6 files, +460/-1.
**Brief:** `.codex/I-rdy-010/brief.md` — Codex brief review APPROVE iter 1
(0 P0/P1/P2, accept_remaining).

## 1. Recut provenance

This is a **recut** of PR #536 (`bot/I-rdy-010-document-grounding`). PR #536
earned Codex brief APPROVE iter-1 + diff APPROVE iter-1 (3 non-blocking P2s
→ #537) but became unmergeable: 41 commits stale, and its `.codex/` committed
~68k lines of raw Codex transcripts (verdict-only-rule violation, CLAUDE.md
§8.3 / the #535 secret-exposure surface). The recut re-applies #536's
APPROVE'd #506 implementation onto current `polaris` HEAD with proper slim
verdict artifacts; PR #536 is closed.

`polaris`'s 41 commits touched exactly one of the 6 files
(`scripts/run_honest_sweep_r3.py`). The 3 modified-clean files + 2 new files
were re-applied verbatim from #536; `run_honest_sweep_r3.py`'s +26 delta was
re-anchored manually (both hunk anchors survived the 4 polaris commits).

## 2. What shipped

The v6 worker path `POST /runs → enqueue_research_run → run_one_query` now
grounds a run on uploaded documents:

- `api/upload.py` (+41): `chunk_text` (CHUNK_SIZE=280, MAX_GROUNDING_CHUNKS=40)
  + `get_upload_record`.
- `api/runs.py` (+58/-1): `_resolve_uploaded_documents` resolves ids →
  content in the API process; fails loud HTTP 400 on missing/unparsed
  upload; `create_run` resolves before insert/enqueue and embeds resolved
  content in the actor message.
- `queue/actors.py` (+21): `enqueue_research_run` sovereignty-partitions the
  uploads; only PUBLIC_SYNTHETIC reaches `q["uploaded_documents"]`.
- `adapters/upload_evidence.py` (NEW, 99): `partition_uploads_by_
  sovereignty` (delegates to the router) + `build_upload_evidence_rows`
  (cleared uploads → pipeline-A evidence rows; raises `UploadSovereigntyError`
  belt-and-suspenders).
- `run_honest_sweep_r3.py` `run_one_query` (+26): prepends upload evidence
  rows onto `evidence_for_gen`; manifest carries
  `uploaded_documents_used/_blocked`.
- `tests/v6/test_document_grounding.py` (NEW, 216): 14 tests.

## 3. Per-finding verification (against the APPROVE'd brief)

- **VERIFIED — actor passes document_ids into the pipeline.** The gap was
  real: `enqueue_research_run` dropped `document_ids` and `run_one_query`
  had zero `uploaded_documents` references. The change resolves uploads at
  `POST /runs`, embeds them in the actor message, the actor
  sovereignty-filters them into `q["uploaded_documents"]`, and
  `run_one_query` prepends them onto `evidence_for_gen`.
- **VERIFIED — sovereignty routing for CLIENT docs holds.** Two gates:
  `enqueue_research_run` calls `partition_uploads_by_sovereignty` (only
  PUBLIC_SYNTHETIC into the q-dict; CLIENT/CAN_REAL/PRIVATE/UNKNOWN blocked,
  counts-only); `build_upload_evidence_rows` re-raises `UploadSovereigntyError`
  belt-and-suspenders on any forbidden doc. The sovereignty router
  (`filter_for_external_egress`) is the single enforcement point. The test
  `test_partition_allows_public_synthetic_blocks_others` + the real
  (un-mocked) router prove CLIENT cannot egress.
- **VERIFIED — fail-loud on bad uploads (LAW II).** `_resolve_uploaded_
  documents` raises HTTP 400 on a missing id and on an upload with no
  extractable text (an unparsed pdf/docx) — no silent zero-evidence run.
  Tests `test_resolve_missing_document_id_raises_400` /
  `test_resolve_unparsed_document_raises_400`.
- **VERIFIED — cross-process correctness.** The upload table is an
  in-process dict; `/runs` runs in the API process and resolves content
  there, embedding it in the Dramatiq actor message — the worker process
  never needs to read the API process's table.
- **VERIFIED — bounded payload.** `MAX_GROUNDING_CHUNKS=40` caps embedded
  chunks per document (a `.md`/`.txt` upload can be up to `MAX_BYTES`).
  Test `test_chunk_text_splits_and_caps_at_max`.
- **VERIFIED — scope boundary honest.** #506 is the worker-actor path; the
  3 P2s (graph_v4/live_server path, `document_ids` item-count cap,
  error-manifest counts) are carved to #537 and out of #506. The acceptance
  phrase "evidence appears in a live run's report" cannot be verified
  offline (needs a live LLM run); #506 scopes it as wiring + harness
  coverage, live-run verification = Phase 5 (#515/#516).

## 4. Smoke

`ast.parse` 6/6 clean. `PYTHONPATH='src;.' pytest
tests/v6/test_document_grounding.py` → 14/14. Adjacent v6 suites
(test_actors, test_api_health_and_runs, test_api_upload,
test_runs_db_integration, …) → 50/50 green.

## 5. Codex iteration trail

- PR #536 (prior, recut-from): brief APPROVE iter-1, diff APPROVE iter-1.
- Recut brief: Codex brief review APPROVE iter 1 — 0 P0/P1/P2,
  accept_remaining (the recut fidelity + polaris-HEAD divergence handling +
  scope boundary all confirmed).

## 6. Verdict

Faithful recut of #536's Codex-APPROVE'd #506 implementation onto current
`polaris` HEAD. The async worker now grounds runs on uploaded documents;
sovereignty blocks CLIENT/CAN_REAL/PRIVATE/UNKNOWN from external-generator
egress (double-gated + harness-proven with the real router); bad uploads
fail loud. Ready for Codex diff review.
