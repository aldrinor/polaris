# Codex DIFF review — I-ui-010 (#730) Frontier Minimal design-system foundation

HARD ITERATION CAP: 5. iter 1. P0/P1 = real execution risk / fails Frontier-Minimal direction / AA failure. APPROVE iff zero P0/P1. Final line MERGE AUTHORIZED if mergeable. web/ only.

Canonical-diff-sha256: `eacb64ba938294b2c1ce4d02e12a43a7207b52798809a9128d6c2800dc9c6c48`. 3 files. Operator CONFIRMED the blue accent. Smoke: typecheck clean, lint 0 errors, build green; screenshot-verified the accent renders on the current home.

## Diff (.codex/I-ui-010/codex_diff.patch)
- web/app/globals.css — :root tokens: --primary/--ring → confident blue oklch(0.50 0.18 255) (replaces faint cyan that read grey); --accent oklch(0.96 0.02 255) / --accent-foreground oklch(0.40 0.12 255); near-mono zinc + hairline --border kept. Keep Geist fonts.
- web/components/app_shell.tsx — sovereign shell mark "⬡ Canadian AI · no external AI vendor" (honest wording; title shows the full logged-Canadian-egress detail; no air-gap overclaim). Preserves 1-header / Primary nav / 1-main.
- web/app/components/home_keyboard_shell.tsx — same sovereign mark in the home shell (parity).

## Review focus
1. AA: primary/primary-foreground (blue/white) ≥4.5:1? accent/accent-foreground AA? ring visible on zinc-50?
2. Sovereign mark wording honest (no overclaim) + accessible (title)?
3. home_g1_g8 structure preserved (1 header, Primary nav, 1 main, focus-visible, no banned strings, no console errors)? The mark adds a <span> in the header — not a 2nd header/nav/main.
4. Any NOVEL P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
