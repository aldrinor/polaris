# Phase 2C Walkthrough — Comprehensive Golden Flow

3 templates × 3 browsers = 9 walkthrough sessions. For each:

## Golden flow (per session)

1. Open browser (Chromium / Firefox / WebKit). Fresh tab. Clear cookies.
2. Navigate to POLARIS dashboard.
3. Type the template's golden query (see below per template).
4. Verify: scope detected within 200ms; in-scope template selected.
5. If query has BPEI ambiguity (template 1's query): modal appears; pick clarification.
6. Submit. Live audit run page loads. SSE stream visible. 5 affordances panel renders.
7. Wait for run to complete (5-10 min on dev cluster).
8. Click "Open Inspector".
9. Verify Inspector 5 tabs: Verified / Frames / Contradictions / Pool / Charts.
10. Click 5 random claim sentences → side pane within 1s for each.
11. Verify Frame coverage panel above-the-fold.
12. Verify at least 1 contradiction flagged (golden queries are picked to surface them).
13. Hover 10 citations → tooltips render <100ms each.
14. Charts tab — Vega-Lite SVG renders within 2.5s.
15. Executive summary tab — 4-KPI strip + 3 charts compose.
16. Click "Pin" → pinned badge.
17. Click "Export bundle" → ZIP downloads within 5s.
18. Unzip → verify report.md + evidence/ + trace.jsonl + provenance.json.
19. Open Memory panel → verify this run is searchable.
20. Re-run pin → verify reproducibility.

## Golden queries (3 templates)

| Template | Query | Expected ambiguity? |
|---|---|---|
| Clinical | "What is the FDA-approved efficacy of tirzepatide for type 2 diabetes?" | No |
| Climate | "What is the BPEI for net-zero pathways in Canadian electricity?" | YES — BPEI ambiguity |
| Trade | "Has CUSMA Chapter 31 dispute on softwood lumber concluded?" | No |

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
