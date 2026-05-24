# Claude architect audit — I-p2-061 (#869): WCAG 2.2 AA fixes

## Goal
The cross-cutting WCAG 2.2 AA verification pass (#765). After every production page reached the
A bar under the dual Codex VISUAL gate, I ran a @axe-core/playwright sweep (wcag2a/2aa/21aa/22aa) —
the NUMERICAL accessibility check the visual gate structurally cannot do (contrast ratios,
accessible names, nested-interactive). It found 15 real violations on the LIVE pages.

## Findings → fixes (axe-measured 15 → 0 across 15 routes)
- **color-contrast (serious, systemic)**: opacity-reduced `text-muted-foreground/70` (~2.6:1) and
  `/80` (~3.1:1) at 11-12px fell below the AA 4.5:1 normal-text threshold. The bulk was the GLOBAL
  footer (one fix → contrast clean on every page); plus proof_showcase, pin_replay, bundle_header
  captions. Bumped to full `text-muted-foreground` (verified AA-passing).
- **ErrorState message (shared component)**: `text-muted-foreground` on the `bg-destructive/5` tint
  failed → `text-foreground/80`. Every error state across the product is now AA.
- **benchmark `<code>`**: muted text on `bg-muted` (grey-on-grey) → `text-foreground`.
- **select-name (critical, /contracts)**: added `aria-label` to the entity-type select.
- **label (critical, /upload + /inspector/offline)**: added `aria-label` to the file inputs.
- **nested-interactive (serious, /upload)**: moved the file input OUT of the `role=button` dropzone
  to a sibling (the dropzone still drives it via inputRef).

## Verification
@axe-core/playwright re-run = **0 violations** across: / · /sign-in · /intake · /contracts · /upload
· /pin_replay · /inspector/v1-canonical · /inspector/offline · /runs/v1-canonical/audit · /dashboard
· /benchmark · /memory · /compare · /source_review · /plan. (The existing accessibility.spec.ts
also covers dashboard/plan/inspector with the same tags.)

## Dual Codex gate
- Brief APPROVE. Visual `-i` APPROVE (darker footer/error text legible, no regression). Code diff
  APPROVE. Objective evidence = the axe 15→0 result.

## Constraints honored
Tokens only; no layout/logic/testids changed; the upload input move preserves the ref-driven click
+ handleFiles. Brand `#c8102e` untouched.

canonical-diff-sha256: ac3f72197c29e10a048866358e17b91de313fe0650cac7d9b2b680ad63ff1284
