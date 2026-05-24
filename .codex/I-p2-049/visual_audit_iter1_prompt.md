# Codex VISUAL audit — I-p2-049 (#845) Sign-in (last public page), A++/S bar — iter 1 of 5

You have VISION. Audit the rebuilt /sign-in at the A++/S bar (institutional auth screen).
Front-load all; don't pick bone from egg; APPROVE iff zero P0/P1.

## What changed (vs the B- baseline)
- The 3 present-tense sovereignty OVERCLAIMS are gone, narrowed to claims that can't be read as
  covering US-routed LLM inference: trust point → "Canadian-hosted evidence records,
  integrity-hashed."; left strip → "Canadian-hosted research workspace · auditable evidence";
  mobile lockup → "Canadian-hosted Workspace". (Footer on every page discloses the OpenRouter-US
  inference path.)
- Otherwise the institutional split-screen (left value panel + right sign-in card) is preserved.

## Attached
1. `signin_desktop.png` (split-screen)  2. `signin_mobile.png` (single column + lockup)

## Locked / do NOT flag
- Brand `#c8102e` locked. The "Continue" button appears washed ONLY because the demo capture
  has empty Username/Password → it's correctly DISABLED (disabled is WCAG-contrast-exempt); it
  renders full #c8102e once fields are filled. Not a bug.
- The maple-leaf braille mark is an operator signature element (#767) — judge placement only.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { signin_desktop: "", signin_mobile: "" }
novel_p0: [...]
continuing_p0: []
p1: [...]
p2: [...]
highest_leverage_change_to_S: "..."
convergence_call: continue | accept_remaining
```
APPROVE iff a confident A-tier institutional auth screen, overclaim-free, zero P0/P1.
