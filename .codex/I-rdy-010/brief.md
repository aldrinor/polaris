# Codex BRIEF review — I-rdy-010 (#506): document grounding — async worker consumes uploaded document_ids

**Type:** BRIEF review (acceptance-criteria + scope correctness). Phase 3.7 of the
Carney demo execution plan. iter 1 of 5.

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

## §1. Issue + acceptance

GH #506 (I-rdy-010, Phase 3.7): "The v6 worker actor passes uploaded
`document_ids` into the research pipeline; F3 works end-to-end. **Acceptance:
uploaded-document evidence appears in a live run's report; sovereignty routing
for CLIENT docs holds; Codex APPROVE.**" Depends on I-rdy-007 (#503 — the
live-run artifact contract doc; merged).

This brief carries a **scope decision** (§3) — the substrate has a real
architectural fork (how the worker process obtains uploaded content). Please
rule `scope_ruling` + `content_transport_ruling` in §7.

## §2. Grounded current state — the 4-part gap (all files read)

**Part 1 — the actor drops `document_ids` on the floor.**
`POST /runs` (`src/polaris_v6/api/runs.py:35`) calls
`enqueue_research_run.send(run_id, payload.model_dump())` — `payload` is a
`RunRequest` which **does** carry `document_ids` (`schemas/run_request.py:32`,
`default_factory=list`). But `enqueue_research_run` (`queue/actors.py:71`)
builds its `q` dict (`actors.py:105-114`) from only `template` + `question` —
**`document_ids` is never read**. So pipeline-A never sees uploads.
`run_request.py:34-38` even documents this: *"currently ignored at
graph_v4.py:149 — Errata to substrate_audit."*

**Part 2 — uploads live in an in-memory dict in the API process.**
`api/upload.py:50` `_UPLOAD_TABLE: dict[str, UploadResponse] = {}` is a plain
in-process dict. The Dramatiq worker that runs `enqueue_research_run` is a
**separate process** (production RedisBroker; or a StubBroker consumer) — it
**cannot read `_UPLOAD_TABLE`**. So even a `document_id` in `q` is unresolvable
worker-side. `upload.py` only chunks `.md`/`.txt` (`upload.py:80-91`; `.pdf`/
`.docx` parse is still Phase-1 TODO → `chunks=[]`); `UploadResponse` carries
`content` (full text) + `chunk_preview` (first 3 chunks).

**Part 3 — pipeline-A has no upload-evidence injection.**
`run_one_query` (`scripts/run_honest_sweep_r3.py:1112`) builds
`evidence_for_gen` at `:1938` (`= evidence_selection.selected_rows`), the V30-P2
path **prepends** contract rows onto it at `:2089-2091`, then the generator is
invoked with `evidence=evidence_for_gen` at `:2108-2110`, and `ev_pool` is built
from it at `:2550` (`{ev["evidence_id"]: ev for ev in evidence_for_gen}`) and
persisted as `evidence_pool.json` at `:2611`. **There is a clean, existing
injection pattern** (the `:2089` prepend) — uploaded-document evidence rows
prepended onto `evidence_for_gen` flow into BOTH the generator AND `ev_pool` →
the report's bibliography + the line-by-line audit. `run_one_query` has zero
`document_id`/`upload` handling today.

**Part 4 — sovereignty must gate uploads, and the substrate already exists.**
`generate_multi_section_report` is an **external LLM call** (OpenRouter V4 Pro).
`polaris_graph/sovereignty/classification.py` defines
`EXTERNAL_LEAK_FORBIDDEN = {CAN_REAL, PRIVATE, CLIENT, UNKNOWN}` (only
`PUBLIC_SYNTHETIC` is egress-safe). `polaris_graph/sovereignty/router.py`
provides `filter_for_external_egress(items, strict=)` /
`assert_safe_for_external(items)` — items expose `.classification` (attr or dict
key). **Nothing wires this to uploads today.** An uploaded `CLIENT` doc whose
chunks reach `evidence_for_gen` → the V4 Pro prompt **is a sovereignty leak**.
So `filter_for_external_egress` MUST gate uploaded docs before they become
generator evidence.

**Note on the merger substrate:** `adapters/evidence_pool_merger.py`
(`merge_evidence_pool`, `UploadedChunk`) was built Phase-1 as the F3a fix but
has **no production consumer** — it merges retrieval + upload + memory spans
into `SourceSpan`s. Pipeline-A's `evidence_for_gen` is a list of **dict rows**
(not `SourceSpan`), so the merger's `SourceSpan` output is the wrong shape for
the `:2089` prepend pattern. The brief therefore builds upload **dict rows**
directly (matching `_contract_evidence_rows` at `:2044-2059`), not via the
merger. (Whether to retrofit the merger is a §6 question.)

## §3. The scope decision — Codex please rule

### §3.1 `content_transport_ruling` — how does the worker get upload content?

- **Option (a) — resolve-at-`/runs`, embed in the actor message (recommended).**
  `create_run` (`runs.py`) runs in the **API process**, where `_UPLOAD_TABLE`
  IS visible. It resolves `payload.document_ids` → `UploadResponse` records and
  embeds `{document_id, classification, chunks/content}` into the
  `enqueue_research_run.send(...)` payload. The worker receives the content
  directly — no cross-process store needed. Works whether the worker is
  in-process (StubBroker) or separate (RedisBroker). Uploaded docs are `.md`/
  `.txt`-only today (small) so message size is bounded. **Tradeoff:** uploads
  are still not durable across an API-process restart between upload and
  run-create — but that is the *pre-existing* `_UPLOAD_TABLE` limitation, not
  introduced here, and acceptable for a single demo session (upload → create
  run happen seconds apart). Fits one PR.
- **Option (b) — durable upload store.** Replace `_UPLOAD_TABLE` with a SQLite
  store (mirroring `queue/run_store.py`) the worker reads by `document_id`.
  Architecturally cleaner + durable, but a genuine new infra module (~120-150
  LOC) on top of the grounding work → forces a carve (§3.2).

**Recommendation: (a).** It satisfies #506's acceptance ("evidence appears in a
live run's report") with the smallest surface, needs no new persistence module,
and is robust to the worker-process topology. Durable upload persistence, if
wanted, is a clean carved follow-up (`I-rdy-010-followup` / I-f3-extension) —
not a #506 blocker.

### §3.2 `scope_ruling` — single PR vs carve

With option (a): the whole of #506 is **one coherent PR ~180-230 LOC** —
`runs.py` resolution + `actors.py` q-wiring + `run_one_query` injection +
sovereignty filter + tests. Recommend **single PR** (cap-exemption if it lands
50-30 LOC over 200, per the #504 precedent). With option (b): **carve** —
PR-1 durable upload store, PR-2 (#506 proper) the grounding. Recommendation
follows from §3.1: **(a) + single PR**.

### §3.3 Implementation plan (option a + single PR)

1. **`runs.py` — resolve uploads at create-run.** In `create_run`, for each id
   in `payload.document_ids`, look up `_UPLOAD_TABLE` (via a new
   `upload.get_upload_record(document_id)` accessor — no raw dict reach-in).
   Build a list of `{document_id, classification, filename, chunks}` (chunks =
   `record`'s chunk list; fall back to `[content]` when md/txt produced no
   chunks but has content). A missing id → `HTTP 400` (fail loud, not silent
   drop). Pass this list as `request_payload["uploaded_documents"]` into
   `enqueue_research_run.send(...)`. (`RunRequest.document_ids` stays the API
   contract; the resolved content is an internal actor-payload field.)
2. **`actors.py` — sovereignty-filter + put in `q`.** `enqueue_research_run`
   reads `request_payload.get("uploaded_documents", [])`. Apply
   `sovereignty.router.filter_for_external_egress(docs, strict=False)` →
   `allowed` (PUBLIC_SYNTHETIC) become `q["uploaded_documents"]`; `blocked`
   (CLIENT/CAN_REAL/PRIVATE/UNKNOWN) are recorded (count + reasons) into the
   run record / manifest and **logged**, never sent onward. `q["uploaded_documents"]`
   = list of `{document_id, classification, chunks}`.
3. **`run_one_query` — inject upload evidence rows.** Between `:1938` and the
   generator call `:2108`, when `q.get("uploaded_documents")`, build evidence
   dict rows (one per chunk) shaped like `_contract_evidence_rows`
   (`:2044-2059`): `evidence_id=f"ev_upload_<doc>_<chunk>"`,
   `statement`/`direct_quote` = chunk text, `source_url=f"upload://{document_id}"`,
   `tier="T2"`, `title=filename`. Prepend onto `evidence_for_gen` exactly as the
   V30-P2 path does at `:2089-2091`. They then flow into the generator AND
   `ev_pool` (`:2550`) → `evidence_pool.json` → report bibliography + audit.
4. **Sovereignty defense-in-depth.** The actor-stage filter (step 2) is the
   gate. `run_one_query` additionally asserts every injected upload row is
   `PUBLIC_SYNTHETIC` (belt-and-suspenders — a forbidden row reaching `:2089`
   is a bug, not a silent pass). The manifest records
   `uploaded_documents_used` + `uploaded_documents_blocked`.
5. **Tests** (`tests/v6/`): actor passes allowed uploads into `q`; actor blocks
   CLIENT/UNKNOWN (sovereignty); `run_one_query` injection unit test (upload
   rows appear in `evidence_for_gen`/`ev_pool`); a CLIENT doc never reaches the
   generator. Stub the broker + the generator boundary; do NOT mock sovereignty.

## §4. Deliverable files + LOC estimate (option a)

| File | New/Mod | ~LOC |
|---|---|---|
| `src/polaris_v6/api/upload.py` | mod (+`get_upload_record` accessor) | 12 |
| `src/polaris_v6/api/runs.py` | mod (resolve document_ids → content) | 35 |
| `src/polaris_v6/queue/actors.py` | mod (sovereignty filter + `q` wiring + manifest record) | 55 |
| `scripts/run_honest_sweep_r3.py` | mod (upload evidence-row injection at ~:1938) | 55 |
| `tests/v6/test_document_grounding.py` | new | 110 |

Estimate **~265 LOC**. Over the 200-LOC cap → **cap-exemption requested**
(precedent: #504 single-PR cap-exemption). The pipeline-A change is a contained
~55-LOC injection following the existing `:2089` pattern — not a deep rewrite.
If Codex prefers a carve, §3.2 option (b) is the split.

## §5. Adjacent-file scan — files I have ALSO checked and they're clean

`src/polaris_v6/schemas/run_request.py` (`document_ids` field — API contract,
unchanged), `src/polaris_v6/queue/run_store.py` (run record / manifest meta —
the blocked-doc record rides existing `set_pipeline_meta`/`mark_*`),
`src/polaris_v6/api/app.py:98` (upload router mounted),
`src/polaris_graph/sovereignty/router.py` + `classification.py` (egress policy —
reused, unchanged), `src/polaris_v6/adapters/evidence_pool_merger.py` (Phase-1
F3a substrate — unwired; `SourceSpan` output shape ≠ pipeline-A dict rows, see
§2 note), `scripts/run_honest_sweep_r3.py:2089-2110` (V30-P2 prepend pattern —
the injection template), `:2550` (`ev_pool` build), `:2611` (`evidence_pool.json`).
The generator (`generate_multi_section_report`) + `select_evidence_for_generation`
will be read at implement time for the exact row-dict contract.

## §6. Questions for Codex

1. **`content_transport_ruling`** — option (a) resolve-at-`/runs`+embed, or (b)
   durable upload store? (Recommendation: a.)
2. **`scope_ruling`** — single PR with cap-exemption (~265 LOC), or carve?
   (Recommendation: single PR, given option a.)
3. Should the unwired `evidence_pool_merger` be retrofitted to the pipeline-A
   dict-row shape (a larger refactor), or is building upload dict rows directly
   (matching `_contract_evidence_rows`) acceptable for #506? (Recommendation:
   direct dict rows; merger retrofit = separate hygiene issue.)
4. Sovereignty: is actor-stage `filter_for_external_egress` + the
   `run_one_query` belt-and-suspenders assert sufficient for "sovereignty
   routing for CLIENT docs holds", or must the block surface in the UI/report
   too (vs manifest + log)?
5. Any P0/P1 execution risk.

## §7. Output schema (CLAUDE.md §8.3.9 — bind to this)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
content_transport_ruling: <option-a-embed | option-b-durable-store + reasoning>
scope_ruling: <single-pr-cap-exemption | carve-2-pr + reasoning>
merger_ruling: <direct-dict-rows-ok | retrofit-merger>
sovereignty_surface_ruling: <manifest-and-log-ok | must-surface-in-ui>
convergence_call: continue | accept_remaining
verdict_reasoning: <text>
```
Loose prose without the schema → resubmit.
