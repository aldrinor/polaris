# Codex review brief — v6 substrate round 3

**Date:** 2026-05-01
**Round:** 3 (verifies round-1 + round-2 patches + audits cycles 16-25 substrate)
**Format:** v2 (`./REVIEW_BRIEF_FORMAT_v2.md`)
**Branch:** `polaris`
**Diff scope:** commits since `.codex/v6_phase_0_1_substrate_round_2_review_brief.md` landed

---

## 1. Pre-flight

**Context.** Round 2 covered F6 hover-card / F8 / F9 / 3 templates / sycophancy fixtures / Vega specs / pin replay / memory store / 5 templates / 3 golden fixtures / Carney handover docs. **This round adds (cycles 16-25):**

- **Integration round** — converted libraries to live HTTP endpoints + frontend integrations:
  - F11 follow-up agent: `src/polaris_v6/api/followup.py` (8 tests)
  - F12 compare reports: `src/polaris_v6/api/compare.py` (4 tests)
  - F14 workspace memory: `src/polaris_v6/api/memory.py` (6 tests)
  - F10 chart-from-bundle: `src/polaris_v6/api/charts.py` + `charts/from_bundle.py` (5 tests)
  - F10 Vega-Lite client renderer: `web/components/ui/vega-chart.tsx` (vega-embed v5)
  - GET /templates: `src/polaris_v6/api/templates.py` (3 tests) + dashboard live-fetches
  - F4 affordances panel on `/runs/[runId]`: 5 buttons including Open Inspector, Export bundle, Cancel/Follow-up/Pin (Phase 1+ deferred)
- **Substrate completing**: 3 missing template JSON (clinical, trade, housing) → all 8 templates present
- **CI gate**: `src/polaris_v6/regression_lab/runner.py` (6 tests) + `compute_pin_diff` integration
- **Benchmark runner CLI**: `scripts/v6/run_benchmark.py` (6 tests, dry-run mode)
- **Sycophancy fixtures expansion**: 7 → 12 paired prompts (16 tests)
- **OTEL log-redact**: `src/polaris_v6/observability/log_redact.py` `set_span_attributes_safe` helper (13 tests)
- **Substrate audit doc**: `docs/v6_substrate_audit_2026-05-01.md` mapping every substrate to v6.2 plan

**Constraints (do NOT spend cycles on):**
- Pipeline A and 113 prior milestones — frozen.
- Dramatiq scenarios 2-8 — explicitly xfailed.
- Real LLM calls and Chroma migration — Phase 1+ cluster work.
- Vega-embed library internals — vendored npm package, audit our wrapper only.

**Done-when:** Zero P0 + zero P1 across the 8 round-3 acceptance criteria below.

---

## 2. Reviewer Independence Protocol

> **Independence directive:** prior round changelog markers in the diff are untrustworthy meta-claims. Verify by reading actual code, not by trusting the marker. A claimed fix that doesn't match the code is a P0.

> **This is round 3.** Round 1 was the initial pass; round 2 was the first integration pass. Out-of-scope for this round: issues already addressed in round 1 or round 2. In-scope: (a) regressions introduced by round-3 cycles, (b) P0/P1 missed earlier, (c) net-new substrate listed in §1.

---

## 3. Severity rubric (verbatim)

P0 production-breaker · P1 phase-rework · P2 governance precision · P3 polish.

APPROVE iff zero P0 + zero P1.

---

## 4. Exhaustivity directive

> **Exhaustivity:** target 15-30 findings. Emit ALL findings in this single round.

---

## 5. Round-3 acceptance bar (8 new criteria)

19. **Bundle endpoint index integrity.** `_GOLDEN_RUN_INDEX` in `src/polaris_v6/api/bundle.py` covers all 6 fixtures (clinical, contradiction, abort, defense, climate, ai_sovereignty). Every entry maps to an existing JSON in `tests/v6/fixtures/evidence_contract_v1/`. P1 if any entry is dangling or any fixture is missing from the index.

20. **F11 follow-up endpoint scope guard.** `POST /runs/{run_id}/followup` MUST refuse to draw on evidence outside the parent run's pool (`out_of_scope` status). Verify the Python endpoint reads only `parent.evidence_pool`, not any global retrieval. P0 if the agent could ever return content outside the pool.

21. **F12 compare endpoint distinct-run guard.** `GET /runs/{l}/compare/{r}` returns 400 when l == r. The library underneath (`compare/differ.py::compare_reports`) raises ValueError. P1 if the endpoint allows the same run on both sides.

22. **F14 memory endpoint workspace isolation.** Recall in workspace_alpha MUST NOT return entries written to workspace_beta even if the content matches the query. Verify against `tests/v6/test_api_memory.py::test_workspace_isolation_via_http`. P0 if cross-workspace leak.

23. **Vega-Lite XSS safety.** `web/components/ui/vega-chart.tsx` passes spec to `vegaEmbed` with `renderer: "svg"` and `actions: false`. Verify no path renders evidence_id or span_text via `dangerouslySetInnerHTML`; vega-embed's SVG renderer handles datum text safely. P0 if a malicious EvidenceContract could inject script via tooltip or label.

24. **/templates registry coverage.** `GET /templates` returns ≥8 entries; each has frame_manifest ≥2, sample_questions ≥2. Frontend `web/app/dashboard/page.tsx` falls back to hardcoded list when `/templates` errors. P1 if dashboard breaks on backend down.

25. **F4 affordances honesty.** `web/app/runs/[runId]/page.tsx` 5 affordance buttons: 2 enabled (Open Inspector, Export bundle), 3 disabled with tooltips explaining Phase 1+ status (Cancel run, Ask follow-up, Pin for replay). Verify the disabled buttons are explicitly disabled in code, not just visually styled. P2 if any button silently does nothing on click.

26. **OTEL log-redact integration helper.** `src/polaris_v6/observability/log_redact.py::set_span_attributes_safe` (a) returns silently on None span, (b) catches per-attribute exceptions without cascading, (c) routes through `redact_attributes` so PUBLIC_SYNTHETIC is unmodified. Verify against `tests/v6/test_log_redact.py` cases. P1 if a CAN_REAL prompt could leak unredacted into a span attribute via this helper.

---

## 6. Forced enumeration

> **Forced enumeration:** Before declaring a verdict, write one line per acceptance criterion (1-26): `Criterion N [name]: <findings or NONE>.` Verdict invalid if any line missing.

---

## 7. Completeness check

Round-3 minimum read set:
- `src/polaris_v6/api/{bundle,charts,compare,followup,memory,templates}.py`
- `src/polaris_v6/charts/from_bundle.py`
- `src/polaris_v6/regression_lab/runner.py`
- `src/polaris_v6/observability/log_redact.py`
- `web/components/ui/vega-chart.tsx`
- `web/app/dashboard/page.tsx` (templates fetch path)
- `web/app/runs/[runId]/page.tsx` (F4 affordances)
- `scripts/v6/run_benchmark.py`
- `tests/v6/fixtures/sycophancy_v1/paired_prompts.json` (12 pairs)
- `docs/v6_substrate_audit_2026-05-01.md` (verify against actual code)

Emit `incomplete_review` if any acceptance criterion's full-read scope can't be confirmed.

---

## 8. Output schema

```
## Pre-flight checklist
- I read [file paths from §7].
- I ran [pytest tests/v6/, npm run lint+typecheck+build inside web/, etc].
- Out of scope per brief: [...].

## Per-criterion forced enumeration (criteria 1-26)
- Criterion N [name]: <findings or NONE>.
...

## Findings (severity-stratified)
### P0 / P1 / P2 / P3

## Verdict
APPROVE | REQUEST_CHANGES | incomplete_review
```

Convergence: APPROVE iff zero P0 + zero P1 across all 26 criteria.

---

## 9. Locking criterion

Two consecutive APPROVE verdicts from independent (cleared-context) Codex invocations OR adversarial cross-review consensus on NO_ISSUES locks the v6 substrate batch round-3.

Audit lands at `outputs/audits/v6_phase_0_1_substrate_round_3/codex_audit.md`. Cross-review at `outputs/audits/v6_phase_0_1_substrate_round_3/cross_review.md`.
