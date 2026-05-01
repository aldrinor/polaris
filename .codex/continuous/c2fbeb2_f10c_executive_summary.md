# Per-commit Codex brief — `c2fbeb2`

**Commit:** `c2fbeb2 PL: v6.2 F10c executive-summary tab`
**Format:** v2 minimal (`./REVIEW_BRIEF_FORMAT_v2.md`)
**Files changed (1):** `web/app/inspector/[runId]/page.tsx` (+166/-2)

## What this commit does

Adds an "Executive summary" sub-tab as the new default landing tab on the Inspector. The tab composes:
- A 4-KPI strip (Verified / Dropped / Contradictions / Sources with T1/T2/T3 breakdown).
- All 3 Vega-Lite chart types stacked (forest_plot, comparison_table, timeline) fetched in parallel via `Promise.all(getChart(runId, t))`.
- Click-on-datum still routes to the right-pane Evidence inspector via `onPointClick`.

Live screenshot: `web/screenshots/inspector_executive_summary.png` (234 KB).

## Acceptance criteria (round-3 brief criteria 24 + new):

1. **Default tab.** Navigating to `/inspector/<id>` lands on Executive summary, not Verified sentences. Verify `useState<...>("summary")` initial value.
2. **Promise.all parallel fetch.** All 3 charts load concurrently, not sequentially. Verify `Promise.all([...chartTypes.map(getChart)])` not a `for` loop with `await`.
3. **Click-through preserved.** `onPointClick` on each VegaChart routes evidence_id to `setSelectedEvidence`. Same contract as Charts tab.
4. **Loading states.** Each chart card shows "Loading…" until its spec arrives; failed fetches don't break the others (per-chart `.catch(() => null)`).
5. **No new XSS surface.** KPI numbers and tier counts are integer / string interpolation only — no `dangerouslySetInnerHTML`.

## Codex focus

- P0: any path where a malicious bundle could inject script via tier counts or KPI display?
- P1: does setting initial tab to "summary" regress existing direct-link behaviour for anyone bookmarking `/inspector/<id>` and expecting Verified sentences first?
- P2: should the 4-KPI strip be a separate component for reuse on `/runs/[runId]`?

Cross-review lands at `outputs/audits/continuous/c2fbeb2/cross_review.md`.
