# Phase 2C Walkthrough — Phase-2C-PARTIAL Comprehensive Golden Flow

> **Phase-2C-PARTIAL bar (post halt-resolution path 3 — 2026-05-02).**
> Live-LLM end-to-end ("type query → wait 5-10 min for cluster to
> generate report → export ZIP") is Phase-2C-END behavior, requires §G
> #3 cluster online. This Phase-2C-PARTIAL flow exercises HEAD-shipped
> substrate end-to-end against `_GOLDEN_RUN_INDEX` golden fixtures
> (`src/polaris_v6/api/bundle.py:24-34`) instead of cluster-driven runs.

3 templates × 3 browsers = **9 walkthrough sessions**. For each:

## Phase-2C-PARTIAL Golden flow (per session)

1. Open browser (Chromium / Firefox / WebKit). Fresh tab. Clear cookies.
2. Navigate to POLARIS dashboard.
3. Type the template's golden query (see below per template).
4. Verify: `POST /scope/check` returns within 200ms; in-scope template
   surfaced inline.
5. If query has BPEI ambiguity (template's BPEI input below): `POST
   /ambiguity` returns modal candidates within 1s; pick clarification.
6. **Phase-2C-PARTIAL substitution**: rather than submit-and-wait-for-
   cluster, navigate directly to the golden-fixture Inspector page for
   that template (see "Golden run IDs" table below). The dashboard
   submit-flow is observational-only on HEAD without cluster — exercise
   it but do NOT wait for a real run.
7. On the Inspector page: verify all **6 tabs** render per
   `web/app/inspector/[runId]/page.tsx`:
   - Executive summary
   - Verified sentences
   - Frame coverage
   - Contradictions
   - Evidence pool
   - Charts
8. Click 5 random `[#ev:...]` provenance tokens within Verified-sentences
   tab → `EvidenceTooltip` shows source-span detail within 1s for each
   (per `2A.7_prep_briefing_pack` F5 row — sentence-level click is NOT
   wired in HEAD; provenance-token-level interaction IS).
9. Click the **"Frame coverage"** tab → panel renders within the tab
   without further scroll (per `2A.7_prep_briefing_pack` F7 row).
10. **Contradictions tab**: if the golden run has any contradictions
    (e.g., `golden_housing_002` has 1+ contradiction), verify each
    badge shows resolution-enum value from
    `src/polaris_v6/schemas/evidence_contract.py:80` (`unresolved` /
    `claim_a_preferred` / `claim_b_preferred` / `noted_both`).
11. Hover 10 `[#ev:...]` provenance tokens within tooltip-host elements
    → tooltips render <100ms each (per `2B.7_prep_briefing_pack` F6).
12. **Charts tab**: Vega-Lite SVG renders within 2.5s. Click datums:
    - if datum identifier is in `evidenceById` → source pane opens
    - if datum identifier is `frame_id` (frame-coverage-derived) →
      expected no-op per `2B.7` Block B (Phase-2B+ work)
13. **Executive summary tab**: 4-KPI strip composes; layout stable
    (no shift after load).
14. Click "Export bundle" → `GET /runs/{run_id}/bundle` → single
    `EvidenceContract v1.0` JSON downloads within 5s. Verify the 15
    required top-level fields per `1.8_prep_briefing_pack` Block D.
15. **Pin / replay / memory** (out of scope on HEAD per `2B.7` known-gaps):
    if buttons render, click them and observe behavior; do NOT fail on
    cluster-dependent behavior absence.

## Golden run IDs (per template)

| Template | Golden run ID | Inspector URL | Expected ambiguity? |
|---|---|---|---|
| Clinical | `golden_clinical_001` | `/inspector/golden_clinical_001` | No |
| Climate | `golden_climate_005` | `/inspector/golden_climate_005` | YES — BPEI ambiguity (test `/ambiguity` endpoint with the golden query) |
| Trade / Defense | `golden_defense_004` | `/inspector/golden_defense_004` | No |

(Trade template currently uses the defense golden fixture; trade-specific
fixture authoring is Phase-2C+ work.)

## Golden queries (3 templates)

| Template | Query | Notes |
|---|---|---|
| Clinical | "What is the FDA-approved efficacy of tirzepatide for type 2 diabetes?" | exercises `POST /scope/check` + Inspector golden render |
| Climate | "What is the BPEI for net-zero pathways in Canadian electricity?" | exercises `POST /ambiguity` (BPEI ambiguity expected) |
| Defense (placeholder for Trade) | "Has CUSMA Chapter 31 dispute on softwood lumber concluded?" | exercises `POST /scope/check` + Inspector golden render |

## Browser matrix

For each template, run on:
- Chromium (latest stable)
- Firefox (latest stable)
- WebKit / Safari (latest stable)

## Cross-cutting observations

After all 9 sessions, append:

```
SESSIONS COMPLETED: <9 of 9>
P0 count across all sessions: <number>
P1 count: <number>
Cross-browser deltas: <list any feature behaving differently>
WCAG-AA violations introduced: <0 expected>
RECOMMENDATION: ship / ship-with-fixes / halt
```
