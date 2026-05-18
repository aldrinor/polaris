# Codex BRIEF review — I-rdy-008 / GH #504 slice 7a: v6 inspector evidence-span route

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. Stage

Pre-implementation **brief** review — reviewing the *plan*, NOT a diff. No code written yet.

## 0.1 This is slice 7a of #504 — the architecture is already decided

#504 (I-rdy-008, Phase 3.5 — "wire live runs into the rich UI"). Slices 1-6
merged (PR #590-#595). Slice-7 grounding hit a real blocker — the inspector
page's `getBundle()` route is golden-fixture-only, AuditIR carries no
evidence span text, so the page works only for 7 golden fixtures, not live
runs. That blocker was routed to a **Codex architecture consult**
(`.codex/I-rdy-008/slice7_arch_consult_verdict.txt`); its verdict split
slice 7 into **7a (backend evidence-span route) / 7b (frontend migration) /
7c (test+demo rebaseline)**. **This brief is slice 7a — a normal
implementation brief; the architecture is settled. Review the plan, not the
decomposition.**

Codex's verdict (for reference): "live runs DO persist verified span text in
`artifact_dir/evidence_pool.json` ... the displayed span is reconstructed as
`source_text[start:end]` for each token in `verification_details.json`. No
7a-pre generator persistence slice is needed for current HEAD; older
artifacts missing `evidence_pool.json` must fail loud, not fall back to
`bibliography.statement`."

## 1. Grounded state (against `polaris` HEAD `06fbf61a`)

- **`src/polaris_v6/api/inspector.py`** (slice 1) — `router = APIRouter(
  prefix="/api/inspector")`; one route `GET /runs/{run_id}` →
  `get_inspector_run`: `run_store.get_run(run_id)` (None→404), `lifecycle_status
  != "completed"`→409, `pipeline_status` startswith `abort_`/`error_`→422,
  absent/non-dir `artifact_dir`→404, `load_audit_ir(artifact_dir)` in
  `try/except (FileNotFoundError, NotADirectoryError, ValueError, TypeError)`
  →422, success→`to_json_dict(ir)`.
- **`evidence_pool.json`** — in the run `artifact_dir`. Confirmed shape
  (`outputs/carney_demo_rehearsal_smoke/clinical/clinical_tirzepatide_t2dm/`):
  a **bare JSON list** of 18 rows, each
  `{evidence_id, direct_quote, full_content_length, source, source_url,
  statement, tier}`. `direct_quote` is the full fetched source text (e.g.
  7226 chars); `tier` is the raw string (`T4`, …); no `source_text` key.
- **Precedent — `artifact_to_slice_chain.py:_full_text_for_evidence_id`**:
  `evidence_pool.json` is EITHER a bare list OR `{"sources": [...]}`; the
  per-row text field precedence is `full_text` → `direct_quote` → `snippet`.
  Slice 7a's resolver must mirror this (both container shapes, that field
  precedence).
- **AuditIR token shape** (`src/polaris_graph/audit_ir/loader.py`, slice-2/4
  grounding) — `ir.verified_report.sections[].sentences[]` is
  `ReportSentence{claim_id, section, text, tokens, is_verified,
  failure_reasons}`; each `tokens[]` entry is `EvidenceSpanToken{evidence_id,
  start, end}` — `start`/`end` are char offsets into the evidence body
  (`direct_quote`). Real tokens seen: `{ev_004, 4800, 5300}` against a
  `direct_quote` of 7226 chars — in-bounds.
- **`tests/v6/test_inspector_route.py`** exists (slice-1 tests: 404/409/422/
  200 + the `_write_minimal_artifact_dir` helper + a `client` fixture that
  seeds `POLARIS_V6_RUN_DB`).

## 2. The plan — `src/polaris_v6/api/inspector.py` + `tests/v6/` (backend only)

### 2.1 `src/polaris_v6/api/inspector.py`

**(a) Extract a shared resolver.** Factor the `get_inspector_run` resolution
(run_store lookup + the 404/409/422 + artifact_dir checks) into a module
helper `_resolve_completed_artifact_dir(run_id) -> Path` that raises the same
`HTTPException`s. `get_inspector_run` calls it then `load_audit_ir`. **Pure
refactor — identical behavior, identical status codes.** (§3.1)

**(b) New route `GET /api/inspector/runs/{run_id}/evidence`** →
`get_inspector_run_evidence(run_id) -> dict[str, Any]`:
1. `artifact_dir = _resolve_completed_artifact_dir(run_id)` (reuses (a)'s
   404/409/422).
2. Read `artifact_dir / "evidence_pool.json"`. **Absent → 422** (fail loud,
   per the Codex verdict — older artifacts predating evidence_pool.json
   persistence are not renderable; NO `bibliography.statement` fallback).
   Malformed JSON → 422.
3. Build `evidence_id -> body` from the pool — accept a bare list OR
   `{"sources": [...]}`; per-row body = `full_text or direct_quote or
   snippet`; also keep `tier` (raw string) and `source_url`.
4. `ir = load_audit_ir(artifact_dir)` (same `try/except`→422 as
   `get_inspector_run`).
5. Walk `ir.verified_report.sections[].sentences[]`; for each sentence
   collect `(sentence.claim_id, token)` for each `token` in `sentence.tokens`.
6. De-duplicate by the range key `(evidence_id, start, end)`. For each unique
   span:
   - `evidence_id` not in the pool → **422** (token cites missing evidence).
   - row body missing/empty → **422** (cannot reconstruct the span).
   - `start`/`end` out of `range(0, len(body)+1)` or `start > end` → **422**
     (out-of-range offsets — fail loud, do not clamp).
   - else `span_text = body[start:end]`.
   - `claim_ids` = sorted unique `claim_id`s of the sentences whose tokens
     hit this exact range.
7. Return `{"run_id": run_id, "spans": [ {evidence_id, span_start, span_end,
   span_text, tier, source_url, claim_ids} … ]}` — `spans` ordered
   deterministically (by `evidence_id`, then `span_start`, then `span_end`).

### 2.2 `tests/v6/test_inspector_route.py` (extend)

New tests for the evidence route, reusing the existing `client` fixture +
`_write_minimal_artifact_dir` helper (extend the helper to also write an
`evidence_pool.json`): (1) 200 happy path — exact `direct_quote[start:end]`
slice; (2) **multi-span same `evidence_id`** — two tokens, same ev, different
ranges → two distinct `spans` entries; (3) **missing `evidence_pool.json`**
→ 422; (4) **out-of-range offset** → 422; (5) **token `evidence_id` absent
from the pool** → 422; (6) the 404/409/422 run-resolution cases still hold
(shared helper regression — exercise via the evidence route).

## 3. Scope-boundary calls for Codex — please rule explicitly

**3.1 — shared-resolver refactor of the slice-1 route.** Plan (a) extracts
`_resolve_completed_artifact_dir` from `get_inspector_run` so both routes
reuse the identical run-resolution. This edits the existing slice-1
function, but as a pure behavior-preserving refactor. Rule: accept the
refactor, or duplicate the ~30 resolution lines into the new route to leave
`get_inspector_run` byte-untouched?

**3.2 — `evidence_pool.json` body field + container.** Plan mirrors
`_full_text_for_evidence_id`: container is a bare list OR `{"sources": […]}`;
body precedence `full_text → direct_quote → snippet`. Rule: accept?

**3.3 — fail-loud taxonomy.** Plan returns **422** for: missing/malformed
`evidence_pool.json`; a token whose `evidence_id` is not in the pool; a row
with no body text; out-of-range/`start>end` offsets. No clamping, no
`statement` fallback, no zero-fill (audit-grade, per the Codex verdict +
LAW II). Rule: confirm 422 is the right code for all four (vs 404/500), and
confirm fail-loud over skip-the-span.

**3.4 — span de-dup + `claim_ids`.** Plan keys spans by `(evidence_id, start,
end)` and lists every citing `claim_id`. Two sentences citing the same range
→ one span, two `claim_ids`. Rule: accept?

**3.5 — synthesis sentences / zero-token sentences.** A sentence with no
`tokens` (e.g. a synthesis claim) contributes no spans — it is simply
skipped. A run whose verified_report has zero tokens overall yields
`{"spans": []}` with HTTP 200 (not an error — a real run can verify-then-
drop everything). Rule: confirm 200 + empty `spans` for the zero-token case.

**3.6 — scope.** Backend only: `src/polaris_v6/api/inspector.py` +
`tests/v6/test_inspector_route.py`. No `web/**` (that is slice 7b), no other
`src/`. Confirm.

## 4. Scope boundary

- **IN:** `src/polaris_v6/api/inspector.py` (shared resolver + the new
  `/runs/{run_id}/evidence` route); `tests/v6/test_inspector_route.py` (new
  evidence-route tests + `evidence_pool.json` in the fixture helper).
- **OUT:** `web/**` (slice 7b — `getInspectorEvidence()` client, `PoolTab`/
  `EvidencePane` migration, `getBundle()` removal, `ir &&` gate); the AuditIR
  loader / serializer (the route reads `evidence_pool.json` directly — no
  loader change); `src/polaris_v6/api/bundle.py` (golden-fixture route stays
  for legacy/F15); inspector e2e/demo fixture rebaseline (slice 7c).

## 5. Smoke test

Backend Python change. Offline: `python -c "import ast; ast.parse(open(
'src/polaris_v6/api/inspector.py').read())"`; `pytest tests/v6/test_inspector_route.py`
(PYTHONPATH includes `src` — the test imports `polaris_v6`). All new +
existing inspector-route tests green. Any pre-existing failure elsewhere in
`tests/v6/` → verify identical on clean `polaris` HEAD via `git stash`
before commit. No web/ smoke (no web/ change).

## 6. Files I have ALSO checked and they're clean

- `src/polaris_v6/api/inspector.py` — slice-1 route; the new route is added
  to the same `router`; the resolver refactor is behavior-preserving.
- `src/polaris_v6/api/artifact_to_slice_chain.py` — `_full_text_for_evidence_id`
  (the `evidence_pool.json` shape precedent the resolver mirrors); NOT
  modified.
- `src/polaris_graph/audit_ir/loader.py` — `EvidenceSpanToken` / `ReportSentence`
  shapes the walk relies on; NOT modified.
- `src/polaris_v6/api/app.py` — already mounts `inspector_router`; the new
  route rides the existing mount; NOT modified.
- `web/**` — untouched (slice 7b).

## 7. Acceptance criteria for THIS PR (slice 7a)

1. `GET /api/inspector/runs/{run_id}/evidence` returns `{run_id, spans[]}`
   with range-keyed `{evidence_id, span_start, span_end, span_text, tier,
   source_url, claim_ids}`; `span_text` is the exact `body[start:end]` slice.
2. Missing `evidence_pool.json` / missing evidence_id / OOB offsets / missing
   body → 422 fail-loud; zero-token run → 200 `{"spans": []}`.
3. The slice-1 `get_inspector_run` behavior is unchanged (shared resolver
   refactor is behavior-preserving).
4. `ast.parse` clean; `pytest tests/v6/test_inspector_route.py` all green.
5. Backend only — no `web/**`, no other `src/` change.

## 8. Required output schema (§8.3.9)

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
