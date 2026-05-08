# Codex Brief Review — I-f10-008 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix (port):** `npm run dev` invokes `next dev` with default port 3000 (per `web/package.json`); the 3738 port is the Playwright e2e config. Walkthrough now uses `http://localhost:3000/...` consistently with `npm run dev`.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you are reviewing

You are reviewing this PLAN, NOT the working tree. Brief review = plan-soundness; diff review = code-matches-plan.

## Pre-flight

- **Issue:** I-f10-008 — F10 walkthrough: tirzepatide vs semaglutide. Scope: "product-owner recording". Acceptance: "auto-table generated with citations". LOC estimate 0 (walkthrough).
- **What's needed:** a documentation walkthrough that exercises the F10 feature substrate end-to-end on a clinical research question (tirzepatide vs semaglutide) — visiting `/charts_test/comparison_table` to demonstrate the auto-table with citations + `/charts_test/click_through` to demonstrate the click-through-to-source-span behavior shipped in I-f10-006.
- **Honest framing per CLAUDE.md §9.4:** the live BPEI pipeline does NOT yet auto-generate Vega-Lite specs from real LLM-retrieved evidence (that wiring is post-Carney-handover). What IS wired and demoable today: the chart spec generators (Python `build_*` + TS mirrors), the `<VegaChart>` renderer, the click-through-to-source UX, and the polaris_provenance contract. The walkthrough exercises THIS substrate honestly, with demo data.

## Plan

### Documentation only (LOC 0 per issue spec)

1. New `docs/walkthroughs/I-f10-008-tirzepatide-vs-semaglutide.md` (~150 lines markdown):
   - **Purpose section:** state the walkthrough's scope — exercises F10 chart substrate end-to-end. Honestly frames "production wiring (live LLM → Vega-Lite spec from real evidence) is post-Carney; THIS walkthrough exercises the demo substrate that ships TODAY."
   - **Question:** "How does tirzepatide compare to semaglutide on cardiovascular outcomes?"
   - **Step 1: Comparison table.** Visit `http://localhost:3000/charts_test/comparison_table` (web dev server). Observe N=5 (entities × 2 metrics). Document: the bar chart renders, every data point carries `evidence_id` from `polaris_provenance`, color encoding by metric.
   - **Step 2: Click-through.** Visit `http://localhost:3000/charts_test/click_through`. Click any of the three forest-plot points (MACE/MI/Stroke). Observe: ChartSourceInspector pane opens with evidence_id + tier badge + URL link + excerpt blockquote.
   - **Step 3: ChartProvenance contract.** Show that every chart spec emitted by `polaris_v6.charts.spec_builder.build_*` validates against `ChartProvenance` (per I-f10-005). Include the relevant test file path.
   - **Step 4: Sandboxed analysis.** Document the I-f10-007 sovereignty layer briefly: sandbox blocks egress + 35 sovereignty tests pass. Reference I-f10-007b OS-isolation follow-up.
   - **What's NOT yet wired (honest gap section):**
     - Live LLM → tirzepatide-vs-semaglutide auto-table from real evidence retrieval (post-Carney).
     - Real evidence_id resolution from sovereign Canadian retrieval pipeline (post-Carney; demo registry used today).
     - I-f10-007b OS-level isolation for code_executor (deferred).
   - **Replay instructions:** explicit `cd web && npm run dev` + the 4 routes to visit + screenshots-as-text-description (since this is a markdown walkthrough, not a video).

2. NO code changes. Acceptance is "auto-table generated with citations" — the auto-table substrate ships in I-f10-003 + I-f10-006. This walkthrough validates it works end-to-end with documentation.

## Risks for Codex Red-Team

1. **Acceptance interpretation:** "auto-table generated with citations" — the live auto-generation (LLM → spec) is NOT in scope; what IS demoable is the substrate path (build_comparison_table → VegaChart → click → ChartSourceInspector with citations). The walkthrough honestly frames this distinction.
2. **Walkthrough is testable manually:** the routes + steps in the doc actually work today (verified via Playwright specs that ship I-f10-001..I-f10-007).
3. **§9.4 N/A documentation.**
4. **CHARTER §1 LOC cap:** ~150 lines markdown. The issue's LOC estimate is 0 because walkthroughs aren't counted as code changes; the markdown file is documentation-only artifact.

## Acceptance criteria

1. New `docs/walkthroughs/I-f10-008-tirzepatide-vs-semaglutide.md` exists with the 4-step walkthrough.
2. Walkthrough references concrete routes (`/charts_test/comparison_table`, `/charts_test/click_through`) that exist today.
3. Honestly frames the gap between demoable substrate (TODAY) and full production wiring (post-Carney).
4. Cites the I-f10-001..I-f10-007 PRs that ship the substrate.
5. CHARTER §1 LOC cap N/A (documentation-only).

**Forced enumeration:** before verdict, write one line per criterion 1-5.

**Completeness check:** list files actually read.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
