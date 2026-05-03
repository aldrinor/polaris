# Phase 2C End-of-Phase Walkthrough — Evaluator Briefing

**Task:** `2C.6` · **Substrate-prep:** `2c_6_prep_briefing_pack` · **Deadline:** 2026-07-19 (§G #7)
**Scope:** Phase 2C UI polish + integration — full-feature walkthrough

> **Phase-2C-PARTIAL bar (post halt-resolution path 3 — 2026-05-02).**
> Full-feature walkthrough is the canonical end-of-Phase-2C bar; that
> requires §G #3 Vast.ai cluster online + Phase 1/2A/2B substrate live
> for real query → run → report → bundle. Phase-2C-PARTIAL exercises
> the integration layers that exist on HEAD: dashboard → /scope/check
> + /ambiguity contract checks; Inspector renders the
> `_GOLDEN_RUN_INDEX` golden fixtures end-to-end with the F5/F7/F8/F9
> behavior already scoped in `2A.7_prep_briefing_pack`; charts +
> Executive summary + tooltips already scoped in `2B.7_prep_briefing_pack`;
> bundle export already exercised in `1.8_prep_briefing_pack` Block D.
> See "Phase 2C known gaps" below.

## What you'll be evaluating (Phase-2C-PARTIAL bar)

Testable on HEAD (golden-fixture end-to-end + cross-browser):

1. Dashboard form → POST `/scope/check` → inline scope panel renders;
   Type "tirzepatide" surfaces clinical template suggestion (per
   `1.8_prep_briefing_pack` Block A, repeated cross-browser here).
2. POST `/ambiguity` against "What is BPEI?" → modal renders within 1s
   (per `1.8_prep_briefing_pack` Block B, repeated cross-browser here).
3. Inspector page for `golden_clinical_001` renders all 6 tabs per
   `web/app/inspector/[runId]/page.tsx`: Executive summary, Verified
   sentences, Frame coverage, Contradictions, Evidence pool, Charts —
   without console errors (per `2A.7` + `2B.7` packs).
4. F15 Bundle export endpoint at `GET /runs/{run_id}/bundle` returns
   valid `EvidenceContract v1.0` JSON for every `_GOLDEN_RUN_INDEX`
   ID (per `1.8_prep_briefing_pack` Block D + `4_5_prep_drafts`
   bundle_export_sample).
5. Cross-browser parity: Chromium + Firefox + WebKit all render
   Inspector page identically + load bundle JSON.
6. WCAG-AA via axe-core: no new violations introduced beyond Phase-1
   baseline.
7. Performance: hover-tooltip <100ms (per `2B.7_prep_briefing_pack`
   F6 row); Inspector FCP <1.5s on golden fixtures.

Observational-only on HEAD (require cluster — see known gaps):
- Live audit run "shows reasoning visibly" (F4 — see `2A.7` known-gaps)
- Pin replay determinism (F13 — see `2B.7` known-gaps)
- Memory persistence with real-corpus content (F14 — see `2B.7`)
- "Real query → run → report" end-to-end (no live LLM)

## Test corpus
See `test_inputs.md` — single end-to-end golden flow on 3 templates × 3 browsers = 9 walkthroughs.

## Failure flags (Phase-2C-PARTIAL bar)
Any regression in the Phase-2C-PARTIAL items above vs the prior phase
walkthroughs (1.8, 2A.7, 2B.7) → halt.
Any cross-browser inconsistency in Inspector page rendering of golden
fixtures → P1.
Any axe-core violation introduced beyond Phase-1 baseline → P1.

## Phase 2C known gaps (in scope to observe, out of scope to ship in this walkthrough)

Per Plan v13 §F (no SILENT fallback):

- **Real query end-to-end (Type → scope → ambiguity → run → report)**:
  cluster-dependent (§G #3). The walkthrough exercises endpoint contracts
  + golden-fixture rendering only — NOT live LLM-driven generation.
- **F4 / F13 / F14 cluster-dependent items**: see prior phase walkthrough
  briefings for full disclosure (`2A.7_prep_briefing_pack` for F4 +
  templates; `2B.7_prep_briefing_pack` for F13 pin replay + F14 memory).
