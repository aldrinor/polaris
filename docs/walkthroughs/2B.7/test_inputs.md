# Phase 2B Walkthrough — 20-Input Corpus

## Block A — F6 Live citation overlay (4)
1. Hover percentage in body → tooltip with quote + tier within 100ms
2. Hover 100x same percentage → tooltip renders consistently <100ms each
3. Tooltip near viewport edge → repositions correctly
4. Mobile (375px viewport) → tap-to-show fallback works (no hover)

## Block B — F10a/b Vega-Lite charts (4, **Phase-2B-PARTIAL bar**)

> Charts derived from `frame_coverage` (forest_plot + comparison_table rows
> emitted by `src/polaris_v6/charts/from_bundle.py` lines 49 + 108) use
> `frame_id` as their datum-identifier — those clicks intentionally do
> NOT resolve through `evidenceById` in HEAD. Only charts whose spec
> emits an evidence-id-keyed identifier resolve to a source pane. Block B
> evaluates render fidelity + click-resolution behavior matching this
> partition; do NOT fail clicks on frame-coverage-derived datums.

5. Inspector Charts tab → forest_plot renders within 2.5s
6. Click datum on forest_plot:
   - if datum identifier is in `evidenceById` → source pane opens within 1s
   - if datum identifier is a `frame_id` (frame-coverage-derived) →
     **expected no-op** under Phase-2B-PARTIAL; flag observationally if
     this surprises the evaluator, but do NOT fail
7. Comparison_table:
   - rows whose datum identifier is in `evidenceById` → click opens source
   - rows whose datum identifier is a `frame_id` → **expected no-op**
8. Timeline chart → hover shows date + event detail with citation (timeline
   datums use evidence-id-keyed identifiers per chart-spec convention)

## Block C — F10c Executive summary (3)
9. Inspector Executive summary tab → 4-KPI strip visible above-fold
10. Click any KPI number → click-to-evidence works
11. 3 charts compose correctly without layout shift

## Block D — F13 Pin replay (4)
12. Run a query, pin it → "pinned" badge appears
13. Wait 24h, replay pin → result deterministic (same evidence pool, same verify decisions)
14. Re-run pinned query with V4 model upgrade → diff view shows what changed
15. Replay failure (e.g., source URL dead) → graceful degradation visible (NOT silent)

## Block E — F14 Workspace memory (5)
16. Save a finding to memory → searchable in same session
17. New session → previous memory still searchable
18. Two workspaces → memories isolated (no cross-pollution)
19. Memory size limit reached → eviction policy visible (LRU? user-configurable?)
20. Search "BPEI" in memory → returns prior runs that referenced ambiguity detector
