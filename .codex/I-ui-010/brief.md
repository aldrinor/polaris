# Codex BRIEF — I-ui-010 (#730) Frontier Minimal design system + shell

HARD ITERATION CAP: 5. iter 2 of 5. Front-load ALL findings. Same bar regardless of iter. P0/P1 = real execution risk or fails the locked Frontier-Minimal direction. APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.

## Goal
The FOUNDATION every page consumes (parent epic #729; plan state/polaris_ui_design_plan_2026_05_21.md, Codex-APPROVED iter 5). Locked direction = **Frontier Minimal**: clean, minimal, near-monochrome + ONE confident accent, hairline borders, generous whitespace, restrained motion. Differentiation lives in BEHAVIOR (proof interactions), NOT type — keep type neutral.

## Verified facts (grounded)
- Fonts already wired: `web/app/layout.tsx` uses next/font Geist + Geist_Mono → `--font-geist-sans` / `--font-geist-mono`; `globals.css @theme inline` maps `--font-sans`/`--font-mono`/`--font-heading`. Geist is an ACCEPTED Frontier-Minimal choice (operator picked "Inter / Geist"); KEEP Geist — no font swap (avoids churn + risk).
- `globals.css :root` current tokens: `--background oklch(0.985 0.001 286.375)` (zinc-50), `--primary oklch(0.5 0.2 200)` (the cyan that reads GREY/faint at a glance — the problem to fix), near-mono elsewhere.
- Shell: `web/components/app_shell.tsx` + `web/app/components/home_keyboard_shell.tsx` PRIMARY_NAV (8-9 links incl Compare). home_g1_g8 e2e asserts 1 header / Primary nav / 1 main / focus-visible.

## Scope (this issue = the system only, not pages)
1. **globals.css** — Frontier Minimal token refinement:
   - **Accent (THE change):** replace the faint cyan with ONE confident accent. Render 2-3 candidates as FULL token pairs (primary + primary-foreground + ring + accent surface) with MEASURED contrast (primary-foreground on primary >= 4.5:1 AA), screenshot for the operator to pick. Candidates (each AA-measured, foreground = white oklch(0.985 0 0) unless noted): (a) confident blue oklch(0.52 0.19 255); (b) institutional indigo oklch(0.50 0.16 270); (c) darker teal oklch(0.52 0.12 215) — the vivid teal oklch(0.62…) is DROPPED (fails AA ~3.1:1). The accent surface/tint reuses the existing --accent token (mapped through @theme), not a new unmapped var. Picked hue → --primary/--ring + accent.
   - **Neutral:** keep near-monochrome zinc scale; ensure text contrast AA.
   - **Hairline borders:** --border a true hairline (1px, low-contrast); minimal/no shadows (subtle elevation only).
   - **Whitespace/radius:** generous spacing rhythm; keep radius modest (clean, not pill-heavy).
2. **shell** — the persistent header gets the sovereignty mark **"Canadian AI processing · no external AI vendor"** (locked honest wording — NOT "no external vendor" which overclaims) (honest wording, institutional, eye-level; per H2/H6 — NOT a false air-gap claim). Keep the 1-header / Primary-nav / focus-visible structure (home_g1_g8).

## Acceptance
- typecheck + lint + build green; home_g1_g8 structure preserved.
- SCREENSHOT (local stack + vision) the accent candidates + the shell mark on a sample page; operator picks the accent before merge.
- Codex diff APPROVE. No "done" without the screenshot.

## Review focus
1. Is keeping Geist (not swapping to Inter) acceptable for the locked Frontier-Minimal direction? (operator picked "Inter / Geist".)
2. Accent approach — candidates rendered + operator-picked — sound? Any contrast/AA risk in the candidate hues?
3. Hairline-borders + minimal-shadow direction correct for Frontier Minimal?
4. Sovereignty shell mark wording honest (no air-gap overclaim)?
5. Any NOVEL P0/P1; anything that would make the FOUNDATION generic/B+.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

---
## iter-2 changelog (addressing iter-1 REQUEST_CHANGES)
- P1 sovereignty wording → locked honest "Canadian AI processing · no external AI vendor" (not "no external vendor").
- P1 accent AA → candidates are now FULL token pairs with measured AA ≥4.5:1; vivid teal DROPPED (3.1:1 fail); accent surface reuses the themed --accent token.
