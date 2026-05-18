# Claude architect audit — I-rdy-008 (#504) slice 7a

**Issue:** GH #504 (I-rdy-008) — Phase 3.5: wire live runs into the rich UI.
**Slice 7a of #504** — the backend half of the slice-7 split decided by the
Codex architecture consult (`.codex/I-rdy-008/slice7_arch_consult_verdict.txt`):
7a backend evidence-span route → 7b frontend migration → 7c test rebaseline.
Slices 1-6 merged (PR #590-#595).
**Branch:** `bot/I-rdy-008-slice7a` off `polaris` HEAD `06fbf61a`.
**Commit 1:** `…` — `src/polaris_v6/api/inspector.py` +
`tests/v6/test_inspector_route.py`.
**Brief:** `.codex/I-rdy-008/brief.md` — Codex brief review iter 1 APPROVE
(0 P0/P1; 2 P2 baked into commit 1).

## 1. What shipped

A new v6 backend route `GET /api/inspector/runs/{run_id}/evidence` that
reconstructs the exact verified evidence spans a completed run cites — the
data the slice-7b frontend will use to migrate `PoolTab`/`EvidencePane` off
the golden-fixture-only `getBundle()`.

- **`_resolve_completed_artifact_dir(run_id)`** — extracted from
  `get_inspector_run` (the run_store lookup + 404/409/422 + artifact_dir
  checks), now shared by both routes. Behavior-preserving refactor.
- **`_load_evidence_pool` / `_evidence_body`** — read `evidence_pool.json`
  (bare list OR `{"sources": […]}`; id alias `evidence_id`/`source_id`; body
  precedence `full_text`/`direct_quote`/`snippet`) — mirrors
  `artifact_to_slice_chain._full_text_for_evidence_id`.
- **`get_inspector_run_evidence`** — walks `ir.verified_report.sections[]
  .sentences[].tokens[]`, de-duplicates by the range key `(evidence_id,
  start, end)`, returns `{run_id, spans:[{evidence_id, span_start, span_end,
  span_text, tier, source_url, claim_ids}]}` with `span_text = body[start:
  end]` — the exact cited span.

## 2. Per-finding verification (against the APPROVE'd brief)

- **VERIFIED — span text is the exact slice.** `span_text` is
  `_evidence_body(row)[start:end]`; `_evidence_body` returns the row's
  `full_text`/`direct_quote`/`snippet` (first non-empty). Confirmed against
  a real `evidence_pool.json` (`outputs/carney_demo_rehearsal_smoke/…`):
  rows carry `direct_quote` (full source text). Test
  `test_evidence_200_exact_span_slice` asserts `span_text == _BODY[5:25]`.
- **VERIFIED — fail-loud taxonomy (§3.3, brief).** 422 on: absent
  `evidence_pool.json`; malformed JSON; pool not a list; token `evidence_id`
  absent from the pool; row with no body text; offsets with `start<0` /
  `start>end` / `end>len(body)`. No clamping, no `bibliography.statement`
  fallback, no zero-fill — audit-grade per the Codex verdict + LAW II.
  Each is covered by a dedicated test.
- **VERIFIED — P2-1 (mirror the precedent).** `_load_evidence_pool` keys a
  row by `row.get("evidence_id") or row.get("source_id")`; `source_url` is
  `row.get("source_url") or row.get("url")`. Matches
  `_full_text_for_evidence_id`.
- **VERIFIED — P2-2 (test coverage).** Tests added for zero-token→200,
  malformed pool→422, missing body→422, the `{"sources": […]}` container +
  `full_text` precedence — beyond the brief's original 6.
- **VERIFIED — range-key de-dup + `claim_ids`.** Spans keyed by
  `(evidence_id, start, end)`; `claim_ids` is the sorted set of citing
  sentence `claim_id`s. `test_evidence_multi_span_same_evidence_id` proves
  two ranges of one `evidence_id` → two distinct spans.
- **VERIFIED — zero-token → 200 `{spans:[]}`** (§3.5) — a synthesis sentence
  with no tokens contributes nothing; a tokenless run is a valid 200, not an
  error. `test_evidence_zero_token_run_returns_200_empty`.
- **VERIFIED — shared-resolver refactor is behavior-preserving.** The
  slice-1 `get_inspector_run` 404/409/422 cases are byte-equivalent (same
  status codes, same detail strings); the 5 slice-1 tests still pass, plus
  `test_evidence_unknown_run_returns_404` exercises the shared resolver via
  the new route.
- **VERIFIED — scope.** Only `src/polaris_v6/api/inspector.py` +
  `tests/v6/test_inspector_route.py`. No `web/**` (slice 7b), no AuditIR
  loader/serializer change, no `bundle.py` change.

## 3. Smoke

`python -c "import ast; ast.parse(...)"` — both files clean.
`PYTHONPATH='src;.' pytest tests/v6/test_inspector_route.py` — **15 passed**
(5 slice-1 regression + 10 new evidence-route). No web/ smoke (no web/
change).

## 4. Codex iteration trail

- **Slice-7 architecture consult** — verdict: split into 7a/7b/7c; live runs
  persist span text in `evidence_pool.json`; reject the lossy fallback.
- **Brief iter 1 APPROVE** — 0 P0/P1; 2 P2 (precedent mirroring; test
  coverage) — both baked into commit 1.

## 5. Scope + residuals

Slice 7a = the backend evidence route. 7b (frontend: `getInspectorEvidence()`
client, `PoolTab`/`EvidencePane` migration, drop `getBundle()`, gate `ir &&`)
and 7c (test/demo fixture rebaseline) follow. #504 stays open.

## 6. Verdict

Faithful to the APPROVE'd brief and the Codex arch consult; the route serves
the exact verified spans from `evidence_pool.json` for any live completed
run; every failure mode fails loud (422), never degrades the clinical-audit
core; the shared-resolver refactor is behavior-preserving; 15/15 tests green.
Ready for Codex diff review.
