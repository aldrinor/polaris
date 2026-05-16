# Codex DIFF review — I-rdy-010 (#506): async worker consumes uploaded document_ids

**Type:** DIFF review (code correctness against the APPROVE'd brief). iter 1 of 5.

## §0. Iteration cap directive (CLAUDE.md §8.3.1, verbatim, binding)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §1. What to review

The diff for #506 against the brief APPROVE'd at brief-iter 1
(`.codex/I-rdy-010/codex_brief_verdict.txt`). Canonical diff:
`.codex/I-rdy-010/codex_diff.patch`, trailer
`# canonical-diff-sha256: f21e24f14a8c67f8a7b0e529623147f6a2ec437fc644f8ae677f723dd2d70876`
= sha256 of `git diff origin/polaris...HEAD -- ':(exclude).codex/I-rdy-010/'
':(exclude)outputs/audits/I-rdy-010/'`.

6 files, +460/-1 (commit `52275e44`).

## §2. Implementation map (verify against the brief + the 5 iter-1 P2s)

**`src/polaris_v6/adapters/upload_evidence.py` (new, ~100 LOC)**
- `partition_uploads_by_sovereignty(docs) -> (allowed, blocked)` — delegates to
  `sovereignty.router.filter_for_external_egress(strict=False)`. Only
  `PUBLIC_SYNTHETIC` is egress-safe.
- `build_upload_evidence_rows(docs) -> list[dict]` — one evidence dict row per
  non-empty chunk, shaped like the V30-P2 `_contract_evidence_rows`
  (`run_honest_sweep_r3.py:2044-2059`). Raises `UploadSovereigntyError` on any
  non-PUBLIC_SYNTHETIC doc (belt-and-suspenders — the actor filter is the gate).

**`src/polaris_v6/api/upload.py` (mod, +41)** — `get_upload_record` accessor;
`chunk_text(text, max_chunks=MAX_GROUNDING_CHUNKS=40)` — **P2-1** (re-chunk full
content, not `chunk_preview`) + **P2-5** (cap the embedded payload — uploads can
be 50 MB). The existing upload endpoint is unchanged.

**`src/polaris_v6/api/runs.py` (mod, +58)** — `_resolve_uploaded_documents`
resolves `document_ids` → `{document_id, classification, filename, chunks}`
**before `insert_run`/`enqueue`** (**P2-2** — no orphan queued run). Missing id
→ HTTP 400; an upload with no extractable text (unparsed pdf/docx) → HTTP 400
(**P2-3** — fail loud, not a silent zero-evidence run). `create_run` embeds the
resolved content into the actor message (`content_transport_ruling=option-a`).

**`src/polaris_v6/queue/actors.py` (mod, +21)** — after the `q`-dict is built,
`partition_uploads_by_sovereignty` splits `request_payload["uploaded_documents"]`;
`q["uploaded_documents"]` = allowed only; `q["uploaded_documents_blocked_count"]`
= len(blocked). Counts logged metadata-only (**P2-4** — no document text logged).

**`scripts/run_honest_sweep_r3.py` (mod, +26)** — between `evidence_for_gen`
(`:1938`) and the generator call (`:2108`): `build_upload_evidence_rows` on
`q["uploaded_documents"]`, prepend onto `evidence_for_gen` (mirroring the V30-P2
prepend `:2089-2091`). Upload rows flow into the generator AND `ev_pool`
(`:2550`) → `evidence_pool.json`. `summary` + the success manifest (`:2724`)
record `uploaded_documents_used` / `uploaded_documents_blocked`. A run with no
uploads skips the block entirely (zero behavior change).

**`tests/v6/test_document_grounding.py` (new, ~210 LOC)** — 14 tests (see §3).

## §3. Test evidence

`tests/v6/test_document_grounding.py` — **14/14 pass** locally (offline):
`chunk_text` empty/short/cap-at-40; `get_upload_record` missing/hit;
`_resolve_uploaded_documents` empty / missing-id→400 / unparsed→400 / happy;
`partition_uploads_by_sovereignty` allow-PUBLIC_SYNTHETIC-block-rest / empty;
`build_upload_evidence_rows` row-shape / empty-chunk-skip /
forbidden-classification→`UploadSovereigntyError`. The sovereignty router runs
for real (not mocked). Import smoke clean on all 5 touched modules incl.
`run_honest_sweep_r3.py`; `test_actors.py` 8/8 (actor not regressed).
`test_api_health_and_runs.py` errors are the pre-existing gpg-`OSError` in
`create_app()` on this gpg-less host (untouched file).

A full live `run_one_query` proving uploaded evidence in a rendered `report.md`
needs network + generator API + cost — CI/e2e, not the autonomous loop
(CLAUDE.md §8.4). The row-construction logic is unit-tested; the prepend is one
line mirroring the proven V30-P2 pattern.

## §4. Points to scrutinise

1. **Sovereignty completeness.** Is actor-stage `filter_for_external_egress` +
   the `build_upload_evidence_rows` belt-and-suspenders raise sufficient that no
   CLIENT/CAN_REAL/PRIVATE/UNKNOWN upload chunk can reach `evidence_for_gen`
   (and thus the external generator prompt)? Any path that bypasses the actor
   filter?
2. **Fail-loud.** Missing id and unparsed-doc both → HTTP 400 before the run row
   exists. The `UploadSovereigntyError` propagates to `run_one_query`'s error
   handler (`error_*` manifest → `mark_failed`). Correct?
3. **No-upload regression.** `q.get("uploaded_documents")` is `[]` for runs
   without uploads → injection block skipped, `summary` keys still set to 0.
   Confirm zero behavior change for existing runs.
4. **Chunk cap.** `MAX_GROUNDING_CHUNKS=40` × 280 chars ≈ 11 KB/doc bounds the
   actor message. Reasonable, or should it be configurable?
5. Any P0/P1 execution risk.

## §5. Adjacent-file scan — checked, clean

`src/polaris_v6/schemas/run_request.py` (`document_ids` API field — unchanged),
`src/polaris_v6/queue/run_store.py` (run record — untouched; counts ride the
manifest/summary, not `set_pipeline_meta`), `src/polaris_v6/api/app.py:98`
(upload router mounted), `src/polaris_graph/sovereignty/{router,classification}.py`
(egress policy — reused, unchanged), `src/polaris_v6/adapters/evidence_pool_merger.py`
(Phase-1 substrate — `SourceSpan` output ≠ pipeline-A dict rows; not used, per
`merger_ruling=direct-dict-rows`), `run_honest_sweep_r3.py:2089-2110` (V30-P2
prepend — the injection template), `:2550` `ev_pool`, `:2719` success manifest.

## §6. Output schema (CLAUDE.md §8.3.9 — bind to this)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
verdict_reasoning: <text>
```
Loose prose without the schema → resubmit.
