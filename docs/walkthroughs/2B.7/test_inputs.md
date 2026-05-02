# Phase 2B Walkthrough — 20-Input Corpus

## Block A — F6 Live citation overlay (4)
1. Hover percentage in body → tooltip with quote + tier within 100ms
2. Hover 100x same percentage → tooltip renders consistently <100ms each
3. Tooltip near viewport edge → repositions correctly
4. Mobile (375px viewport) → tap-to-show fallback works (no hover)

## Block B — F10a/b Vega-Lite charts (4)
5. Inspector Charts tab → forest_plot renders within 2.5s
6. Click datum on forest_plot → source span opens in side pane
7. Comparison_table → all rows clickable to source
8. Timeline chart → hover shows date + event detail with citation

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
20. Search "BPEI" in memory → returns prior runs that referenced BPEI ambiguity detector
