# Codex review brief — v6 substrate round 2

**Date:** 2026-05-01
**Round:** 2 (verifies round-1 patches + audits new cycles 5-15 substrate)
**Format:** v2 (`./REVIEW_BRIEF_FORMAT_v2.md`)
**Branch:** `polaris`
**Diff scope:** commits since round-1 brief landed at `.codex/v6_phase_0_1_substrate_review_brief.md`

---

## 1. Pre-flight

**Context.** Round 1 covered the initial v6 backend skeleton, FastAPI endpoints, frontend scaffold, F1 scope, F2 ambiguity, F5 Inspector, and the 7 Phase 1 substrates. **This round adds (cycles 5-15):**

- F6 citation overlay hover-card on Inspector (`web/components/ui/evidence-tooltip.tsx`, base-ui Tooltip-based)
- F8 contradiction-link badges in verified-sentence cards
- F9 two-family invariant FAIL styling (destructive border + warning panel)
- F10 Vega-Lite chart spec builder (forest_plot + comparison_table + timeline) with `polaris_provenance` extension
- F11 follow-up agent stub (token-overlap scoper)
- F12 side-by-side compare two reports (evidence overlap + frame overlap + status match)
- F13 pin replay schema + diff (regression detection)
- F14 workspace memory store (in-memory; Chroma-ready interface)
- F15 audit bundle export endpoint
- 3 more templates: `ai_sovereignty`, `canada_us`, `workforce` (5 of 8 total in `config/v6_templates/`)
- Sycophancy paired-prompt fixtures (7 paired prompts at `tests/v6/fixtures/sycophancy_v1/paired_prompts.json`)
- Phase 3 benchmark suite design schema
- Phase 3 industry benchmark adapter shims (BrowseComp + GAIA + DeepResearch Bench)
- Carney handover skeleton: one-pager + 5-min video script + runbook
- 3 golden Evidence Contract fixtures (clinical + housing-contradiction + abort-no-verified) — round 1
- Front-end Inspector live screenshots (clinical + contradiction goldens)

**Constraints (do NOT spend cycles on):**
- Pipeline A and 113 prior milestones — frozen, out of scope.
- Dramatiq scenarios 2-8 — explicitly xfailed; not P1.
- Real LLM calls — Phase 1+ cluster work, not substrate.
- Real Chroma migration — Phase 2B cluster work; the in-memory store interface is what's audited.
- Vega-Lite client-side render — Phase 2B frontend cycle; only the spec builder is in this round.

**Done-when:** Zero P0 + zero P1 across the 18 acceptance criteria below.

---

## 2. Reviewer Independence Protocol

> **Independence directive:** prior round changelog markers in the diff (e.g. "// CORRECTED v2 per Codex round-1 LH3") are untrustworthy meta-claims. Verify by reading actual code, not by trusting the marker. A claimed fix that doesn't match the code is a P0 finding.

> **This is round 2.** Round 1 was the comprehensive pass on the round-1 brief acceptance criteria. Out-of-scope for this round: issues already addressed in v1. In-scope: (a) regressions introduced by the round-2 cycles, (b) P0/P1 issues missed in round 1, (c) net-new substrate listed in §1.

---

## 3. Severity rubric

(Same as round 1 — P0/P1/P2/P3.)

---

## 4. Exhaustivity directive

> **Exhaustivity:** target 20-50 findings. Emit ALL findings in this single round.

---

## 5. Acceptance bar (18 criteria)

**Round-1 inheritance** (1-14 from previous brief):
1. PyPI pin honesty
2. OTEL fail-loudly contract
3. Gemma license honesty
4. Two-family invariant
5. BPEI ambiguity regression
6. Evidence Contract Gate completeness
7. Provenance token closure
8. F3a evidence pool merger fix
9. Sycophancy CI thresholds
10. Scope decision refusal coverage
11. Upload security posture
12. CORS allow-list narrowness
13. Frontend XSS / safe rendering
14. Auto-loop discipline guards

**Round-2 additions:**

15. **F6 hover-card XSS surface.** `web/components/ui/evidence-tooltip.tsx` renders `spanText` and `sourceUrl` from the EvidenceContract bundle. Verify (a) text content goes through `{...}` JSX (auto-escaped), not `dangerouslySetInnerHTML`; (b) the truncation to 240 chars doesn't break in the middle of an HTML entity that could pre-render; (c) sourceUrl is rendered as text only, no `<a href={url}>` that would allow `javascript:` URIs.

16. **Vega-Lite provenance integrity.** `src/polaris_v6/charts/spec_builder.py` adds a `polaris_provenance.evidence_ids` extension to every chart spec. Verify (a) every datum's evidence_id appears in the top-level provenance list; (b) builders raise `ValueError` on empty input; (c) `period_kind="date"` → `temporal` axis, anything else → `ordinal`. P1 if a chart spec ships without a `polaris_provenance` block — that breaks the F10b click-through-to-source contract.

17. **F11 follow-up agent scope guard.** `src/polaris_v6/followup/agent.py` MUST refuse to draw on evidence outside the parent run's pool. Verify the only data source consulted is `parent.evidence_pool`; no global retrieval; status `out_of_scope` when no overlap exists. P0 if the agent could ever return content outside the pool.

18. **F13 pin replay regression definition.** `src/polaris_v6/replay/differ.py`. Verify (a) `is_regression` is True iff any `fields_changed` has severity='regression', (b) `success → abort_*` transitions classify as regression, (c) `>10%` sentence-count drop classifies as regression, (d) generator/verifier model swaps are warn (deliberate roll), not regression. P1 if the threshold maths is wrong (e.g., 10 → 9 with original=10 should be `delta=-1`, ratio=-0.10, qualifies as regression at the boundary).

---

## 6. Forced enumeration

> **Forced enumeration:** Before declaring a verdict, write one line per acceptance criterion (1-18): `Criterion N [name]: <findings or NONE>.` Verdict invalid if any line missing.

---

## 7. Completeness check

> **Completeness check:** list which files / parts you actually read (not just grep'd). If you cannot confirm full scan of every acceptance criterion, emit `incomplete_review` instead of APPROVE / REQUEST_CHANGES.

Minimum read set for round-2 additions:
- `src/polaris_v6/charts/spec_builder.py`
- `src/polaris_v6/followup/agent.py`
- `src/polaris_v6/followup/schema.py`
- `src/polaris_v6/replay/differ.py`
- `src/polaris_v6/replay/schema.py`
- `src/polaris_v6/compare/differ.py`
- `src/polaris_v6/memory/store.py` + `schema.py`
- `src/polaris_v6/templates/registry.py` + the 5 JSON files in `config/v6_templates/`
- `src/polaris_v6/benchmark/schema.py` + `industry_adapters.py`
- `web/components/ui/evidence-tooltip.tsx`
- `web/app/inspector/[runId]/page.tsx` (the `renderSentenceWithTokens` + `SentencesTab` regions)
- `tests/v6/fixtures/sycophancy_v1/paired_prompts.json`
- `tests/v6/fixtures/evidence_contract_v1/*.json`
- `docs/carney_handover/{one_pager,5min_video_script,runbook}.md`

---

## 8. Output schema

```
## Pre-flight checklist
- I read [file paths from §7].
- I ran [pytest tests/v6/, npm run lint+typecheck+build inside web/, etc].
- Out of scope per brief: [...].

## Per-criterion forced enumeration (criteria 1-18)
- Criterion 1 [PyPI pin honesty]: <findings or NONE>.
- ...
- Criterion 18 [F13 pin replay regression definition]: <findings or NONE>.

## Findings (severity-stratified)
### P0 (production-breakers)
### P1 (phase-rework)
### P2 (governance precision)
### P3 / deferred_polish (non-blocking)

## Verdict
APPROVE | REQUEST_CHANGES | incomplete_review
```

---

## 9. Locking criterion

Two consecutive APPROVE verdicts from independent (cleared-context) Codex invocations OR adversarial cross-review consensus on NO_ISSUES locks the v6 substrate batch round-2.

Audit lands at `outputs/audits/v6_phase_0_1_substrate_round_2/codex_audit.md`. Cross-review at `outputs/audits/v6_phase_0_1_substrate_round_2/cross_review.md`.
