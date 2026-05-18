# Codex BRIEF review — GH #506 (I-rdy-010): async worker consumes uploaded document_ids

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. Stage

Review-stage **brief** — reviewing the *plan + recut rationale*. This is a
**recut** of an already-Codex-APPROVE'd implementation (see §1), so the code
already exists on the branch; you are confirming the recut is faithful and
the polaris-HEAD divergence was handled correctly. The diff itself gets a
separate Codex diff review next.

## 1. Why this is a recut (front-loaded so you VERIFY, not rediscover)

#506 was implemented in a prior session as PR #536
(`bot/I-rdy-010-document-grounding`). That PR earned **Codex brief APPROVE
iter-1 AND Codex diff APPROVE iter-1**; the diff review surfaced 3
non-blocking P2s, which were carved out to follow-up issue **#537**
(I-rdy-010-followup) — none block #506. PR #536 was never merged and is now
unmergeable as-is:

1. **41 commits stale** behind `polaris`. Its `lint+format+typecheck+build`
   CI fails on `app/generation/page.tsx` + `lib/auth.ts` prettier debt —
   files NOT in #506's diff; pre-existing repo-wide format:check debt on the
   *stale* tree (current `polaris` HEAD passes that check, proven by PR #600
   merging green).
2. **Verdict-only-rule violation.** PR #536's `.codex/I-rdy-010/` committed
   `codex_brief_verdict.txt` (14221 lines) + `codex_diff_audit.txt` (19851
   lines) + `_iter_1` duplicates — i.e. **~68k lines of RAW Codex
   transcripts**, not the ~7-line slim YAML verdict. Raw transcripts must
   never reach `polaris` (CLAUDE.md §8.3 verdict-only; the raw-transcript
   secret-exposure surface is #535).

Decision (Codex-advisor-confirmed): **recut** onto a clean `bot/I-rdy-010`
off current `polaris` HEAD, re-applying #536's APPROVE'd #506 source
implementation, with proper slim verdict artifacts. PR #536 is closed; this
PR replaces it.

### 1.1 Recut fidelity — how the 6 files were re-applied

`polaris`'s 41 commits touched exactly **one** of the 6 #506 files:
`scripts/run_honest_sweep_r3.py` (I-naming-003 #437, I-gen-561 #561,
I-modref-004 #530, I-gen-004 #496).

- **3 modified-clean files** (`src/polaris_v6/api/runs.py`,
  `src/polaris_v6/api/upload.py`, `src/polaris_v6/queue/actors.py`) — polaris
  did NOT touch them; `git checkout origin/bot/I-rdy-010-document-grounding
  -- <file>` re-applies #536's exact APPROVE'd content.
- **2 new files** (`src/polaris_v6/adapters/upload_evidence.py`,
  `tests/v6/test_document_grounding.py`) — new, no divergence possible.
- **`scripts/run_honest_sweep_r3.py`** — the +26-line #506 delta (2 hunks)
  was re-anchored manually onto current HEAD. Both hunk anchors
  (`f"{_p2_exc} — falling back to legacy generator"` → `multi = await
  generate_multi_section_report(`; and the `manifest = {...}` `"status":
  unified_status,` row) survived the 4 polaris commits unchanged; the
  re-apply is byte-equivalent to #536's hunk except for line numbers.

## 2. Issue + acceptance

#506 (I-rdy-010, Phase 3.7): "The v6 worker actor passes uploaded
`document_ids` into the research pipeline; F3 works end-to-end. Acceptance:
uploaded-document evidence appears in a live run's report; sovereignty
routing for CLIENT docs holds; Codex APPROVE." Depends on I-rdy-007 (#503,
CLOSED).

## 3. Grounded current state (`polaris` HEAD 30c0b488)

- `RunRequest` (`schemas/run_request.py`) already has
  `document_ids: list[str]` (default `[]`).
- The v6 worker actor `enqueue_research_run` (`queue/actors.py`) built its
  `q`-dict from `request_payload` but **dropped `document_ids`** — uploaded
  documents never reached `run_one_query`.
- `run_one_query` (`scripts/run_honest_sweep_r3.py`) had **zero**
  `uploaded_documents` references — pipeline-A never consumed uploads.
- The upload table (`api/upload.py` `_UPLOAD_TABLE`) is an in-process dict;
  the Dramatiq worker is a SEPARATE process and cannot read it.
- The sovereignty router (`polaris_graph/sovereignty/router.py`
  `filter_for_external_egress`, I-f3-003) classifies items by a
  `classification` key; only `PUBLIC_SYNTHETIC` is egress-safe.

## 4. The change (6 files, +460/-1)

1. **`api/upload.py`** (+41): `CHUNK_SIZE=280`, `MAX_GROUNDING_CHUNKS=40`;
   `chunk_text(text)` (fixed-size chunks, capped — bounds the embedded
   actor-message payload, since a `.md`/`.txt` upload can be up to
   `MAX_BYTES`); `get_upload_record(id)`.
2. **`api/runs.py`** (+58/-1): `_resolve_uploaded_documents(document_ids)`
   resolves each id → `{document_id, classification, filename, chunks}` in
   the API process; **fails loud HTTP 400** on a missing id or an upload
   with no extractable text (LAW II — no silent zero-evidence run).
   `create_run` resolves BEFORE `insert_run`/`enqueue` (a bad id orphans no
   queued run) and embeds the resolved content in the actor message.
3. **`queue/actors.py`** (+21): `enqueue_research_run`
   sovereignty-partitions `request_payload["uploaded_documents"]` via
   `partition_uploads_by_sovereignty`; only allowed (PUBLIC_SYNTHETIC) docs
   go into `q["uploaded_documents"]`; `q["uploaded_documents_blocked_count"]`
   records the blocked count (metadata only — never document text).
4. **`adapters/upload_evidence.py`** (NEW, 99): `partition_uploads_by_
   sovereignty` (delegates to the router — single enforcement point);
   `build_upload_evidence_rows` turns cleared uploads into pipeline-A
   evidence dict rows (`ev_upload_<id>_<n>`, `tier=T2`, `source_url=
   upload://<id>`), and raises `UploadSovereigntyError` belt-and-suspenders
   if any non-PUBLIC_SYNTHETIC doc reaches it.
5. **`run_honest_sweep_r3.py`** `run_one_query` (+26): prepends the upload
   evidence rows onto `evidence_for_gen` (mirroring the V30-P2 contract-row
   prepend) so uploads reach the generator + `evidence_pool.json` + the
   report bibliography; manifest gets `uploaded_documents_used` /
   `uploaded_documents_blocked`.
6. **`tests/v6/test_document_grounding.py`** (NEW, 216): 14 tests —
   `chunk_text`, `get_upload_record`, `_resolve_uploaded_documents`
   (missing/unparsed → 400), `partition_uploads_by_sovereignty`
   (PUBLIC_SYNTHETIC allowed, others blocked), `build_upload_evidence_rows`
   (rows + forbidden-classification raise). The sovereignty router runs for
   real (CLAUDE.md §9.4 — no mocking the policy under test).

## 5. Scope boundary — what #506 covers vs #537 (Codex: confirm)

#506 is the **v6 worker-actor path** (`POST /runs` → `enqueue_research_run`
→ `run_one_query`). The 3 P2s already carved to **#537** are explicitly OUT
of #506 scope:
- **#537 P2-1** — the `pipeline_a_ui_adapter.build_and_run_v4` /
  `live_server /api/research` path threads `q["uploaded_documents"]` in an
  OLDER per-chunk shape; it fails closed (no leak) but is not grounded with
  the v6 shape. OUT of #506.
- **#537 P2-2** — `RunRequest.document_ids` has no max-item count
  (`MAX_GROUNDING_CHUNKS` caps chunks per-doc, not doc count). OUT of #506.
- **#537 P2-3** — the generic error-manifest omits
  `uploaded_documents_used/blocked`. OUT of #506.

The acceptance phrase "uploaded-document evidence appears in a live run's
report" cannot be verified offline (needs a live LLM run). #506 scopes it as
the **wiring + `test_document_grounding.py` harness coverage**; the live-run
verification is Phase 5 (#515/#516) territory. Codex: confirm this boundary
is honest and #506 is not under-scoped.

## 6. Smoke

`ast.parse` 6/6 clean. `PYTHONPATH='src;.' pytest
tests/v6/test_document_grounding.py` → 14/14. Adjacent v6 suites
(`test_actors`, `test_api_health_and_runs`, `test_api_upload`,
`test_runs_db_integration`, …) → 50/50 green — no regression from the
`runs.py`/`actors.py`/`upload.py` wiring.

## 7. Files I have ALSO checked and they're clean

- `src/polaris_graph/sovereignty/router.py` — `filter_for_external_egress`
  signature (`items, *, strict`) + `SovereigntyDecision(allowed, blocked,
  reasons)` confirmed compatible with `upload_evidence.py`'s
  `strict=False` call; NOT modified.
- `src/polaris_v6/schemas/run_request.py` — `RunRequest.document_ids`
  already present; consumed as-is, NOT modified.
- `src/polaris_v6/queue/run_store.py` — `insert_run` / `mark_*`; the upload
  resolution happens before `insert_run`; NOT modified.
- `src/polaris_graph/pipeline_a_ui_adapter.py` — the OTHER (graph_v4)
  pipeline-A entry; its `_load_uploaded_documents` path is #537 P2-1, OUT of
  #506; NOT modified.
- `tests/v6/test_actors.py`, `test_api_upload.py`, `test_api_health_and_
  runs.py` — adjacent suites; run green (50/50); NOT modified.

## 8. Output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
