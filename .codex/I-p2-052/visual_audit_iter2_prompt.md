# Codex VISUAL audit — I-p2-052 (#851) Benchmark, A++/S bar — iter 2 of 5

You have VISION. iter-1 was REQUEST_CHANGES (grades: loaded_desktop A / loaded_mobile B /
empty A- / error A- / list A). One P1: mobile table clipped the 3rd peer (Gemini) column.

## Fix applied (this iter)
- loaded_mobile: REPLACED the clipped 4-column table (< sm) with per-dimension STACKED blocks —
  each dimension shows all three systems in a labelled 3-cell grid (POLARIS brand / ChatGPT DR /
  Gemini DR), green = leads reported peers, dash (—) = peer doesn't report it. The dense table is
  retained for sm+ desktop. Nothing else changed in the table semantics.
- loaded summary meta ("12 questions · 7 dimensions") now stacks under the id on mobile (iter-1 P2).
- Desktop/empty/error/list unchanged from iter-1.

## Attached
1. bench_loaded_desktop  2. bench_loaded_mobile  3. bench_empty_desktop
4. bench_error_desktop   5. bench_list_desktop

## Locked / do NOT flag
- Brand #c8102e. "BEAT-BOTH benchmark" H1 is e2e-required — keep. Fixture visual-audit-only.
  Empty state is the live-visible state. scripts/run_benchmark.py footer = deliberate
  reproducibility claim. The empty-state weight P2 (iter-1) uses the shared state-kit component —
  flag only if it now reads as a real defect.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { loaded_desktop: "", loaded_mobile: "", empty: "", error: "", list: "" }
novel_p0: [...]
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```
APPROVE iff zero P0/P1 (the mobile head-to-head is now fully readable).
