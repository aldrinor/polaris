# Codex DIFF review — GH #506 (I-rdy-010): async worker consumes uploaded document_ids

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #506 (I-rdy-010) — `git diff origin/polaris...HEAD`
excluding `.codex/I-rdy-010/` and `outputs/audits/I-rdy-010/` (canonical
diff in `.codex/I-rdy-010/codex_diff.patch`, sha256 trailer). Implements the
Codex-APPROVE'd brief `.codex/I-rdy-010/brief.md` (brief APPROVE iter 1; 0
P0/P1/P2). **6 files, +460/-1.**

## 2. Recut provenance (front-loaded so you VERIFY)

This is a **recut** of PR #536 (`bot/I-rdy-010-document-grounding`), which
earned Codex brief APPROVE iter-1 + **diff APPROVE iter-1** for this exact
#506 implementation (3 non-blocking P2s → carved to #537). PR #536 became
unmergeable (41 commits stale; its `.codex/` committed ~68k lines of raw
Codex transcripts — a verdict-only-rule violation). The recut re-applies
#536's APPROVE'd source onto current `polaris` HEAD `30c0b488`:

- 3 modified-clean files (`api/runs.py`, `api/upload.py`, `queue/actors.py`)
  + 2 new files (`adapters/upload_evidence.py`, `tests/v6/test_document_
  grounding.py`) — re-applied verbatim from #536 (polaris did not touch
  them).
- `scripts/run_honest_sweep_r3.py` — the +26-line delta re-anchored
  manually (polaris's I-naming-003 / I-gen-561 / I-modref-004 / I-gen-004
  commits touched the file but not the two #506 hunk regions).

So this is the same code Codex already diff-APPROVE'd on #536; your job is
to confirm the re-application onto current HEAD is faithful and introduced
no NEW P0/P1.

## 3. The change

`POST /runs → enqueue_research_run → run_one_query` now grounds a run on
uploaded documents:

- **`api/upload.py`** — `chunk_text` (CHUNK_SIZE=280, MAX_GROUNDING_CHUNKS=40
  cap) + `get_upload_record`.
- **`api/runs.py`** — `_resolve_uploaded_documents` resolves `document_ids`
  → `{document_id, classification, filename, chunks}` in the API process;
  fails loud HTTP 400 on a missing id or no-extractable-text upload;
  `create_run` resolves BEFORE `insert_run`/`enqueue` and embeds the
  resolved content in the actor message.
- **`queue/actors.py`** — `enqueue_research_run` sovereignty-partitions the
  uploads; only PUBLIC_SYNTHETIC into `q["uploaded_documents"]`; blocked
  count recorded (metadata only).
- **`adapters/upload_evidence.py`** (new) — `partition_uploads_by_
  sovereignty` (delegates to `filter_for_external_egress`);
  `build_upload_evidence_rows` → pipeline-A evidence rows; raises
  `UploadSovereigntyError` belt-and-suspenders on a forbidden doc.
- **`run_honest_sweep_r3.py`** `run_one_query` — prepends upload evidence
  rows onto `evidence_for_gen`; manifest gets `uploaded_documents_used/
  _blocked`.

## 4. Verify

1. **Sovereignty holds (the acceptance-critical check).** A CLIENT /
   CAN_REAL / PRIVATE / UNKNOWN upload must NOT reach the external
   generator: confirm `enqueue_research_run` only puts the
   `partition_uploads_by_sovereignty` *allowed* partition into
   `q["uploaded_documents"]`, and `build_upload_evidence_rows` re-raises on
   any non-PUBLIC_SYNTHETIC doc. The router is the single enforcement point;
   confirm there is no path that bypasses it.
2. **Fail-loud (LAW II).** `_resolve_uploaded_documents` raises HTTP 400 on
   a missing id and on a no-extractable-text upload — no silent
   zero-evidence run.
3. **Cross-process correctness.** The resolved content rides in the actor
   message because the Dramatiq worker cannot read the API process's
   in-process `_UPLOAD_TABLE`. Confirm `create_run` resolves in the API
   process and the actor reads `request_payload["uploaded_documents"]`.
4. **No fabricated data.** `build_upload_evidence_rows` reuses real upload
   chunk text verbatim as `statement`/`direct_quote`; `source_url=
   upload://<id>`. No invented evidence.
5. **Bounded payload.** `MAX_GROUNDING_CHUNKS=40` caps chunks per document.
6. **Recut fidelity.** The 6-file diff matches #536's APPROVE'd #506
   implementation; the `run_honest_sweep_r3.py` re-anchor did not drop or
   alter any of the +26 delta.
7. **Scope.** Only the 6 files. The 3 P2s carved to #537 (graph_v4/
   live_server path, `document_ids` item-count cap, error-manifest counts)
   are OUT of #506 — confirm none is a P0/P1 that must block.

## 5. Files I have ALSO checked and they're clean

- `src/polaris_graph/sovereignty/router.py` — `filter_for_external_egress`
  / `SovereigntyDecision`; consumed as-is, NOT modified.
- `src/polaris_v6/schemas/run_request.py` — `RunRequest.document_ids`
  already present; NOT modified.
- `src/polaris_v6/queue/run_store.py` — `insert_run`; NOT modified.
- `src/polaris_graph/pipeline_a_ui_adapter.py` — the graph_v4 path (#537
  P2-1, out of #506); NOT modified.

## 6. Smoke state

`ast.parse` 6/6 clean. `pytest tests/v6/test_document_grounding.py` 14/14.
Adjacent v6 suites (test_actors, test_api_health_and_runs, test_api_upload,
test_runs_db_integration, …) 50/50 green.

## 7. Required output schema (§8.3.9)

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
