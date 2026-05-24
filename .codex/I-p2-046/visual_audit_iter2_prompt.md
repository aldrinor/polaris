# Codex VISUAL audit — I-p2-046 (#839) Contracts editor, A++/S bar — iter 2 of 5

You have VISION. iter 2. iter-1 P1: the sticky action bar overlaid editable fields. FIXED.
Re-grade as a confident A-tier config tool. APPROVE iff zero P0/P1.

## Fix since iter 1
- **P1 overlay** → the action bar is now STATIC (a crafted ring+shadow card at the form end),
  not sticky — it no longer overlays any editable field on desktop or mobile.
- **P2.1 mobile entity row** → the entity name input + type select now stack
  (flex-col sm:flex-row) so the input no longer truncates on 375w.

## Attached
1. `contracts_desktop_full.png` (no overlay — action bar at the end)
2. `contracts_mobile.png`  3. `contracts_desktop_sticky.png` (scrolled)

## Locked (do NOT flag)
- Brand `#c8102e` locked; field logic/testids unchanged; config tool (dense by nature).

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { desktop_full: "", mobile: "", desktop_scrolled: "" }
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
highest_leverage_change_to_S: "..."
convergence_call: continue | accept_remaining
```
APPROVE iff a confident A-tier config tool, no overlay, zero P0/P1.
