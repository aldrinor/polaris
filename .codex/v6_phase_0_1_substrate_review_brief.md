# Codex review brief — v6 Phase 0 + Phase 1 substrate batch

**Date:** 2026-05-01
**Round:** 1 (comprehensive pass)
**Format:** v2 (`./REVIEW_BRIEF_FORMAT_v2.md`)
**Branch:** `polaris`
**Diff scope:** commits `6bd1557..7893ae4` (19 commits, ~3,500 LOC + tests + screenshots)
**Cross-review target:** `outputs/audits/v6_phase_0_1_substrate/cross_review.md`

---

## 1. Pre-flight

**Context.** First v6 substrate batch since the v6.2 plan was Codex-GREEN'd. Ships:
- 6 task-deliverable docs (`docs/{blockers,agent_architecture,backend_modernization,gemma_4_verification,opentelemetry_genai}.md`, plus `carney_delivery_plan_FINAL.md` Errata)
- v6 backend skeleton: `src/polaris_v6/{api,bpei,sycophancy,scope,observability,queue,schemas,adapters}/` + `requirements-v6.txt` (18 PyPI-verified pins)
- v6 frontend: `web/` Next.js 16.2.4 + React 19.2.4 + shadcn 4.6 (MIT) + Tailwind v4 + TypeScript 5; 3 routes (`/`, `/dashboard`, `/runs/[runId]`, `/sign-in`)
- 8 FastAPI router endpoints: `/health`, `POST /runs`, `GET /runs/{id}`, `GET /stream/{id}`, `POST /ambiguity`, `POST /scope/check`, `GET /runs/{id}/bundle`, `POST /upload` + `GET /upload/{id}`, plus CORS middleware
- 12 v6 test modules — 61 tests passing, 1 skipped, 7 xfailed (Dramatiq scenarios 2-8 await Task 0.3 cluster)
- 3 Evidence Contract v1.0 golden fixtures
- 5 frontend screenshots, 2 captured against live backend with CORS

**Constraints (do NOT spend cycles on):**
- Pipeline A (`src/polaris_graph/*`) — frozen substrate, out of scope. Only `graph_v4.py:149` is touched indirectly via the v6 `evidence_pool_merger.py` which was written BECAUSE of that bug; you do not need to audit pipeline A.
- The 113 prior milestones (M-1..M-PROD-4) — locked, out of scope.
- Dramatiq acceptance scenarios 2-8 — explicitly xfailed pending Vast.ai cluster (Task 0.3), do not flag as P1.
- `gen_ai.prompt`/`gen_ai.completion` redaction CI — Phase 1 deliverable; presence of the `genai_attributes.py` placeholder in `backend_modernization.md` §4 is NOT a P1 yet.

**Done-when:** Zero P0 + zero P1 across the 14 acceptance criteria below.

---

## 2. Reviewer Independence Protocol

> **Independence directive:** prior round changelog markers in the diff (e.g. "// CORRECTED v2 per Codex round-1 LH3") are untrustworthy meta-claims. Verify by reading actual code, not by trusting the marker. A claimed fix that doesn't match the code is a P0 finding.

Specifically: the v6.2 plan errata section at the top of `docs/carney_delivery_plan_FINAL.md` claims two corrections (Gemma license, OTEL env var). Verify against `docs/gemma_4_verification.md` + `docs/opentelemetry_genai.md` + `requirements-v6.txt` + `src/polaris_v6/observability/otel_init.py` that the corrections are actually applied in code, not just narrated in markdown.

---

## 3. Severity rubric (verbatim from format v2)

- **P0** production-breaker: silent failure path, broken auth, data loss, missing rollback flag, security hole
- **P1** phase-rework: acceptance-bar criterion failed; the feature is not actually integrated
- **P2** governance precision: real bug, bounded blast radius
- **P3** polish: style, comment clarity, test coverage gap with no functional defect

**APPROVE rule:** zero P0 + zero P1 → APPROVE. P2/P3 → `deferred_polish` array.

---

## 4. Exhaustivity directive

> **Exhaustivity:** target 20-50 findings on the first scan. Do NOT truncate. Emit ALL findings in this single round. Subsequent rounds verify the v(N) patch only — re-raising previously addressed issues is a defect, but missing a P0 in this round is also a defect.

---

## 5. Acceptance bar (14 criteria — forced enumeration required)

| # | Criterion | What to verify |
|---|---|---|
| 1 | **PyPI pin honesty** | All 18 pins in `requirements-v6.txt` resolve on PyPI at the pinned version (e.g. `fastapi==0.136.1`, `redis==7.4.0`, `opentelemetry-api==1.41.1`). No phantom packages (advisor caught `opentelemetry-instrumentation-dramatiq` doesn't exist; verify it's NOT in the file). Dramatiq 2.1's `redis<8.0,>=4.0` constraint is satisfied. |
| 2 | **OTEL fail-loudly contract** | `src/polaris_v6/observability/otel_init.py` raises `RuntimeError` if `OTEL_SEMCONV_STABILITY_OPT_IN` does not contain the literal `gen_ai_latest_experimental`. Tests at `tests/v6/test_otel_init.py` verify env-missing / legacy-`gen_ai_dev`-rejected / correct-accepted / csv-list-accepted. The plan errata E-2 claim (`gen_ai_dev` legacy → `gen_ai_latest_experimental`) is reflected in CODE, not just docs. |
| 3 | **Gemma license honesty** | `docs/gemma_4_verification.md` Errata E-1 claim (Apache 2.0 + Gemma Use Policy) is sourced (verbatim URLs) and the `family_segregation_passed` invariant in `EvidenceContract` v1.0 cross-checks the DeepSeek vs Google lineage assumption. |
| 4 | **CLAUDE.md §9.1 invariant 1 (two-family)** | The `EvidenceContract.generator_model` and `verifier_model` fields cannot trivially be set to the same family. (Phase 0: invariant is documented; Phase 1: enforced at run construction. Do NOT P1 the absence of run-time enforcement; DO P1 if the schema accepts identical values without comment.) |
| 5 | **BPEI ambiguity regression** | `tests/v6/test_ambiguity_detector.py::test_bpei_pattern_detects_ambiguity` actually catches the failure pattern from `memory/bpei_phantom_completion_lessons.md`. Cluster separation between medical and financial BPEI snippets is real, not just `is_ambiguous=True` by accident. Trigram cosine threshold (0.5 default) tuned against both positive and negative cases. |
| 6 | **Evidence Contract Gate completeness** | All 10 tests in `tests/v6/test_evidence_contract_gate.py` pass. The 3 golden fixtures cover (a) success, (b) contradiction with `noted_both` resolution, (c) `abort_no_verified_sections` with empty `verified_sentences`. The malformed-rejection tests (negative cost / wrong contract_version / `span_end<=span_start`) actually fail validation. |
| 7 | **Provenance token → evidence_id closure** | `test_provenance_tokens_reference_pool` in the gate verifies every `[#ev:<id>:<a>-<b>]` token's `<id>` resolves to a member of `evidence_pool`. CLAUDE.md §9.1 invariant 2 (provenance tokens) is enforced at the schema level. |
| 8 | **F3a evidence pool merger fix** | `src/polaris_v6/adapters/evidence_pool_merger.py` is the substrate fix for `graph_v4.py:149` (which was caught ignoring `document_ids`). Verify (a) uploaded chunks reach the pool, (b) dedup normalizes whitespace + case, (c) upload-takes-priority over retrieval-side duplicates, (d) evidence_ids are stable across calls. Do NOT require this to be wired into a live run yet — that's Phase 1. |
| 9 | **Sycophancy CI thresholds** | `src/polaris_v6/sycophancy/scorer.py` drift_score = `1 - mean(pairwise Jaccard)`. Verify (a) factual-anchor token-set subset check is correct, (b) drift_score_max=0.4 catches a deliberately-sycophantic 4-framing fixture, (c) refusal_consistency catches "refused some, answered others". `test_sycophantic_model_fails_drift_threshold` is real, not a tautology. |
| 10 | **Scope decision refusal coverage** | `_REFUSAL_PATTERNS` in `src/polaris_v6/scope/decision.py` covers the 5 named refusal reasons (clinical_treatment_recommendation, individual_legal_advice, individual_financial_advice, personal_political_endorsement, out_of_template_scope). Tests verify treatment / legal / political reject. The classifier is intentionally a Phase-0 stub; do NOT P1 the absence of LLM augmentation. |
| 11 | **Upload security posture** | `src/polaris_v6/api/upload.py` enforces (a) extension whitelist `.pdf/.docx/.md/.txt`, (b) 25 MB cap, (c) reject empty files (422), (d) classification field with default `UNKNOWN`. The sha256 hash is computed and stored. P0 if any of: path traversal in filename, content sniffing bypass, missing classification → ingest. |
| 12 | **CORS allow-list narrowness** | `src/polaris_v6/api/app.py` CORS middleware has explicit origin list (not `["*"]`), bound by `POLARIS_V6_CORS_ORIGINS` env var, with `allow_credentials=False`. P0 if `["*"]` + `credentials=True` ever combine. |
| 13 | **Frontend XSS / safe rendering** | `web/app/runs/[runId]/page.tsx` renders SSE event data via `JSON.stringify(evt.data, null, 2)` inside `<pre>` — verify no innerHTML / dangerouslySetInnerHTML anywhere. `web/app/dashboard/page.tsx` scope rationale rendered as text content. `web/lib/api.ts` `downloadBundleAsJson` uses `Blob` + `URL.createObjectURL` correctly. |
| 14 | **Auto-loop discipline guards** | `memory/feedback_dont_stop_on_user_budget_block.md` is in place. `docs/todo_list.md` accurately reflects current state (3 done / 3 cluster-blocked / 3 user-$-blocked in Phase 0; 7 substrates landed in Phase 1). The triangle loop protocol is followed (this brief exists; its cross-review will live at `outputs/audits/v6_phase_0_1_substrate/cross_review.md`). |

---

## 6. Forced enumeration

> **Forced enumeration:** Before declaring a verdict, write one line per acceptance criterion: `Criterion N [name]: <findings or NONE>.` Verdict is invalid if any line is missing.

---

## 7. Completeness check

> **Completeness check:** list which files / parts you actually read (not just grep'd) this round. If you cannot confirm full scan of every acceptance criterion, emit `incomplete_review` instead of APPROVE / REQUEST_CHANGES.

Minimum read set (full read, not grep) for this round:
- `requirements-v6.txt`
- `src/polaris_v6/observability/otel_init.py`
- `src/polaris_v6/schemas/evidence_contract.py`
- `src/polaris_v6/bpei/ambiguity_detector.py`
- `src/polaris_v6/sycophancy/scorer.py`
- `src/polaris_v6/scope/decision.py`
- `src/polaris_v6/api/upload.py`
- `src/polaris_v6/api/app.py`
- `src/polaris_v6/adapters/evidence_pool_merger.py`
- `web/app/dashboard/page.tsx`
- `web/app/runs/[runId]/page.tsx`
- `web/lib/api.ts`
- `tests/v6/test_evidence_contract_gate.py` + the 3 fixtures in `tests/v6/fixtures/evidence_contract_v1/`
- `docs/blockers.md` + `docs/agent_architecture.md`
- `docs/carney_delivery_plan_FINAL.md` Errata section (lines 1-30)

---

## 8. Output schema

```
## Pre-flight checklist
- I read [file paths from §7].
- I ran [pytest tests/v6/, npm run lint+typecheck+build inside web/, etc].
- Out of scope per brief: pipeline A, prior 113 milestones, Dramatiq scenarios 2-8.

## Per-criterion forced enumeration
- Criterion 1 [PyPI pin honesty]: <findings or NONE>.
- Criterion 2 [OTEL fail-loudly contract]: <findings or NONE>.
- Criterion 3 [Gemma license honesty]: <findings or NONE>.
- Criterion 4 [Two-family invariant]: <findings or NONE>.
- Criterion 5 [BPEI ambiguity regression]: <findings or NONE>.
- Criterion 6 [Evidence Contract Gate completeness]: <findings or NONE>.
- Criterion 7 [Provenance token closure]: <findings or NONE>.
- Criterion 8 [F3a evidence pool merger fix]: <findings or NONE>.
- Criterion 9 [Sycophancy CI thresholds]: <findings or NONE>.
- Criterion 10 [Scope decision refusal coverage]: <findings or NONE>.
- Criterion 11 [Upload security posture]: <findings or NONE>.
- Criterion 12 [CORS allow-list narrowness]: <findings or NONE>.
- Criterion 13 [Frontend XSS / safe rendering]: <findings or NONE>.
- Criterion 14 [Auto-loop discipline guards]: <findings or NONE>.

## Findings (severity-stratified)
### P0 (production-breakers)
### P1 (phase-rework)
### P2 (governance precision)
### P3 / deferred_polish (non-blocking)

## Verdict
APPROVE | REQUEST_CHANGES | incomplete_review

Convergence: APPROVE iff zero P0 + zero P1.
```

---

## 9. Locking criterion

Two consecutive APPROVE verdicts from independent (cleared-context) Codex invocations OR adversarial cross-review consensus on NO_ISSUES locks the v6 Phase 0/1 substrate batch.

Audit lands at `outputs/audits/v6_phase_0_1_substrate/codex_audit.md`. Cross-review at `outputs/audits/v6_phase_0_1_substrate/cross_review.md`.
