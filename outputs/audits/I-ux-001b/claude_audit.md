# Claude architect audit — I-ux-001b (GH#876, foundation)

**Branch:** `bot/I-ux-001b-foundation` (off `bot/I-ux-001a-prereq-0-signed-bundle`).
**Plan source:** §14.1 of `docs/stier_experience_plan.md` (Codex iter-4 APPROVE, plan PR #873).
**Codex review trajectory:** brief iter 1→4 (APPROVE iter 4; zero P0/P1/P2; two cosmetic P3 typos noted, since cleaned).

## What's in this PR (spec only — no code)

1. **`docs/web/design_tokens_v2.md`** — type scale (Geist, 8 sizes), two-judgment color (faithfulness vs evidence-strength in chromatically distant hue families per Codex iter-1 P1: `--unsupported` at hue 320° magenta-red, brand red at hue 22°), per-level certainty foregrounds for WCAG AA on all 4 levels (Codex iter-2 P1: `--certainty-moderate` lightness bumped 0.56→0.50 to pass AA on near-white fg), motion tokens (3 durations / 1 easing / `prefers-reduced-motion` honored), brand-LOCKED `#c8102e`, crisp maple-leaf SVG spec (replaces "dot-cloud"), trust-copy table (de-jargon).

2. **`docs/web/components_catalogue.md`** — 9 components × six microstates × concrete CSS contract. Shared interactive baseline (§0) covers ALL selectors (button, [role=button], a, summary, .btn, .link, .interactive) including a visible-spinner loading state via `visibility: hidden` on children (NOT `color: transparent`; iter-2 P1 spinner-invisibility fix) + reduced-motion fallback. Components: `<ClaimSentence>`, `<ProofPanel>` (desktop right-rail + mobile bottom-sheet), `<FaithfulnessChip>`, `<CertaintyBadge>`, `<SourceCard>`, `<SourceSpanPreview>` (handles verified/partial/**unsupported** spans per Stage 6, iter-3 P2 fix), `<SignaturePill>` (tri-valued from I-ux-001a), `<WhatThisDoesNotProve>`, `<IntendedUseBanner>`.

3. **`docs/web/proof_replay_storyboard.md`** — frame-level 6-beat hero choreography (Stage 0 resting → Stage 7 Home teaser → Stage 8 Playwright acceptance tests). Real verified-sentence text from the shipped bundle in both Stage 0 + Stage 7 illustrations (iter-1 P1: previous mock had fabricated text). Time-to-first-proof <400ms clarified as "Beat 2 visible at 250ms," NOT total reveal (iter-2 timing-math clarification). Honest failure-state choreography (missing/present_unverified signature, UNSUPPORTED claim, inadequacy refusal) per LAW II.

## Codex review trajectory (uncapped per operator override on plan; standard 5-cap on brief gate)

| iter | verdict | findings |
|---|---|---|
| 1 | REQUEST_CHANGES | 4 P1 (color collision, microstates deferred, timing math, fabricated claim) + 1 P2 + 1 P3 |
| 2 | REQUEST_CHANGES | 2 P1 (selector scope + invisible spinner, per-level fg gaps) + 2 P2 + 0 P3 |
| 3 | REQUEST_CHANGES | 2 P1 (loading on bare selectors, CertaintyBadge stale `--certainty-fg` + moderate contrast under AA) + 1 P2 + 1 P3 |
| 4 | **APPROVE** | zero P0/P1/P2; one cosmetic P3 noted (`--ring-offset` mention in microstate table, since cleaned) |

## Depends on
- #875 (Prereq 0 — real signed bundle) — branched off `bot/I-ux-001a-prereq-0-signed-bundle`. When #875 merges to polaris, this PR rebases cleanly.

## Unblocks
The next sub-issues for per-page rebuilds (the actual production CSS/Tailwind migration + per-page hero implementation). Closes #876.
