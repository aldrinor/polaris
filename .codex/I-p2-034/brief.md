# Codex DESIGN+DIFF review — I-p2-034 (#790): responsive nav

HARD ITERATION CAP: 5. iter 1. Canonical-diff-sha256 `8cf574c468c1ce602d6d681c126812608b5de392155e3dc49005315cbb533bd5`. web/ only. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

P1: the global nav (9 links, single row) overflowed off-screen on mobile → links unreachable. Fix: shared PrimaryNav (web/components/primary_nav.tsx, "use client"): inline links md+ (hidden below); hamburger + full-width dropdown below md. a11y: aria-expanded/aria-controls, Escape-to-close, click-away backdrop, focus-visible /70, closes on nav. Both shells (app_shell server + home_keyboard_shell client) replaced their inline <nav> with <PrimaryNav/>; home header made relative for the absolute dropdown (app_shell header already sticky). NavLink gained optional onClick (close-on-nav).

## Claude visual audit (standalone): mobile hamburger opens a clean dropdown with all 9 routes (Home active → Memory); desktop inline nav intact. Verified 390/1366.

## Review focus
1. a11y: aria-expanded/controls correct; Escape + click-away + close-on-nav; focus-visible; the dropdown reachable + dismissible by keyboard?
2. Positioning: absolute dropdown relative to the (sticky/relative) header — correct in both shells, no clipping?
3. md breakpoint hides inline / shows hamburger cleanly (no double-render)? Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
