# Codex VISUAL audit — I-p2-053 (#853) Workspace memory, A++/S bar — iter 2 of 5

You have VISION. iter-1 was REQUEST_CHANGES (populated_desktop A- / populated_mobile B+ / empty A).
P1: mobile textarea clipped its placeholder. P2: mobile row meta squeezed; desktop list
over-separated from the form stack.

## Fixes applied (this iter)
- Textarea: rows 2→3 + min-h-20 + shorter placeholder ("…as primary sources.") → no clipping.
- Memory row restructured to a deliberate 3-line layout: row1 = kind chip (left) + Forget (right,
  never squeezed); row2 = content full-width; row3 = meta footer (mono id · relative date · reused
  N×). Same on desktop + mobile.
- Added a "SAVED MEMORY · N" section heading above the list to anchor it to the form stack
  (tighter vertical rhythm).
- prior_run_summary chip is neutral (brand red reserved for the Remember action).

## Attached
1. mem_populated_desktop  2. mem_populated_mobile  3. mem_empty_desktop

## Locked / do NOT flag
- Brand #c8102e (Remember button only). Fixture visual-audit-only. LIVE-populated verification
  DEFERRED. prior_run appears in both "Prior research" and the list — intentional.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { populated_desktop: "", populated_mobile: "", empty: "" }
novel_p0: [...]
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```
APPROVE iff zero P0/P1 (textarea fits, mobile rows uncramped).
