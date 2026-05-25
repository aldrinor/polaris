# I-ux-001c sub-PR 2 — Claude architect audit

## Scope

v6 marketing-auth home page rebuild. Replaces the previous one-CTA hero
(search bar + templates grid + ProofShowcase + RecentRunsStrip + three
pillar cards) with the brief-iter-4-APPROVE'd v6 marketing-auth hero:
brand-red eyebrow + H1 + subtitle + REAL verified-claim proof-as-CTA
card + ONE primary CTA → /intake.

## §-1.1 line-by-line audit standard

This sub-PR is a UI rebuild against the v6 design lock, NOT a clinical
content/evaluation change. The clinical-safety-critical line-by-line
standard applies to the CONTENT the UI renders (which is the canonical
signed-bundle fixture, unchanged) — this PR's review surface is:

1. **Honesty of the rendered metadata** (the matched-numbers stamp,
   the signature pill state, the source-tail copy)
2. **No silent fallback** when the bundle is missing or no real span
   resolves (LAW II)
3. **Two-judgment separation** (faithfulness greens never share a
   swatch with evidence-strength slate-blues; we use faithfulness
   greens here because Home is about verification, not certainty)

## Per-file audit

### `web/lib/home_brief_loader.ts` (NEW, ~165 LOC)

- Reads the canonical `v1-canonical-success` bundle via the existing
  server-side `loadBundle` (no new I/O path, no new fixture).
- Returns the **first** verified sentence whose primary provenance token
  resolves to a real `>40-char` span. Same selection logic as the prior
  `ProofShowcase` server component (I-p2-037 #794) — moved here as plain
  data so the v6 visual treatment is a pure renderer.
- Honest-fail: `bundle_loaded: false` when the bundle is absent OR when
  no verified sentence resolves to a real span. UI MUST render the
  "still loading" copy in that case (verified in `ProofAsCta`).
- `matched_numerics` is the actual count of numeric tokens in the
  sentence that appear in the cited span — NEVER `Math.max(2, matched)`
  or any synthesized number (sub-PR-1 Codex iter-1 P1-001 lesson
  carried forward).
- `signature_state` is the tri-state value from the loader
  (`gpg_verified` | `present_unverified` | `missing`) — UI must render
  the appropriate copy per state; only `gpg_verified` may render
  green "Signed bundle" (sub-PR-1 Codex iter-1 P1-005 carry-forward).

### `web/components/home/home_palette_shell.tsx` (NEW, ~85 LOC)

- Extracts ONLY the palette behavior from the deleted
  `HomeKeyboardShell`: `<CommandPalette>` mount + `Ctrl+K` /
  `Meta+K` toggle + `<Link data-testid="header-sign-in-link">` focus-
  restore target.
- Drops the marketing-header chrome (`PrimaryNav`, sovereign mark,
  brand link), templates grid, search bar — those are no longer the
  hero.
- `AppShellGate` marks `/` chromeless; this shell adds NO chrome —
  just the palette + a small top-right sign-in escape hatch.
- The 3 `command_palette*.spec.ts` files pass UNCHANGED (palette
  selectors + focus-restore target preserved). Verified by Codex
  iter-3 grounded repo check.

### `web/components/home/proof_as_cta.tsx` (NEW, ~165 LOC)

- Pure renderer over `HomeBrief` data.
- `bundle_loaded === false` branch renders honest "still loading"
  copy with link to `/inspector/v1-canonical-success` — NO numeric
  stamp, NO signature pill. LAW II compliance.
- `bundle_loaded === true` branch renders the v6 climax: numerics
  bolded green via `proof-numeric` spans, matched-numbers stamp with
  null-safe source tail (4 fallback templates for missing
  journal/year), tri-state signature pill, deep link to the full
  proof.
- `highlightNumerics()` uses the SAME regex as the loader's
  `extractNumerics()` — visual and count are guaranteed in sync.

### `web/app/page.tsx` (REBUILD)

- Async server component that calls `loadHomeBrief()` then renders the
  v6 hero. No client-side JS for the static parts (eyebrow, H1,
  subtitle, claim, CTA) — fastest first paint.
- Templates list preserved verbatim from the legacy page (the
  CommandPalette search corpus contract). Codex iter-2 P3 noted this
  duplication; sub-PR scope says preserve, defer DRY follow-up to a
  future cleanup PR.
- Honest sovereignty wording: "Canadian-hosted clinical research
  system, built toward sovereign Canadian deployment" — NEVER
  present-tense "Sovereign" overclaim. Mirrors I-p2-044 #835 fix and
  the iter-1 Codex P1-001 brief check.

### `web/app/globals.css` (EDIT, +20 LOC)

- Adds `--certainty-{level}-bg` slate-blue tints (very-light) paired
  with the existing `--certainty-{level}-fg` dark slate-blues.
- Registers Tailwind v4 utility-namespace tokens:
  `--color-certainty-{level}: var(--certainty-{level}-bg)` AND
  `--color-certainty-{level}-fg: var(--certainty-{level}-fg)` — so
  `bg-certainty-high` and `text-certainty-high-fg` resolve to
  DIFFERENT OKLCH (the iter-4 P2-001 fix).
- Original `--certainty-*-fg` vars retained for inline-style consumers
  (Inspector's `inspector_proof_header.tsx` reads them via `style={{
  color: 'var(--certainty-high-fg)' }}`).

### Test updates

- `f1_a11y.spec.ts`: home selector updated to `home-h1` + `home-primary-cta`
  + `proof-as-cta`. `header-sign-in-link` preserved.
- `demo_journey.spec.ts`: step-1 click target swaps from
  `home-hero-search` + Verify button to `home-primary-cta`. Nav-parity
  test scope reduced to authed routes only (`/intake`, `/dashboard`,
  `/inspector/*`); home is marketing chrome, not authed nav.
- `demo_walkthrough.spec.ts`: same primary-CTA swap; second test
  rewritten around v6 selectors (eyebrow + H1 + subtitle + proof-as-CTA),
  asserts old surfaces (`template-grid`, `home-hero-search`) are gone.

### New tests

- `home_proof_as_cta.spec.ts`: 8 Playwright cases — eyebrow/H1/subtitle
  copy, proof-as-CTA loaded state + REAL claim text, bolded-green
  numerics via `proof-numeric` spans, matched-numbers stamp shape +
  null-safe source tail, tri-state signature pill, primary CTA → /intake,
  proof-as-CTA deep-link to inspector, sign-in link preserved, Ctrl+K
  opens palette.
- `home_aa.spec.ts`: axe WCAG 2.2 AA at desktop 1440×900 + mobile
  390×844. Isolated scan so axe failures surface to this PR's scope
  (f1_a11y also covers home but combines with palette-open + intake).

### Deletions

- `web/app/components/home_keyboard_shell.tsx` — superseded by
  HomePaletteShell.
- `web/app/components/proof_showcase.tsx` — absorbed into proof_as_cta.tsx
  + home_brief_loader.ts.
- `web/app/components/recent_runs_strip.tsx` — out of sub-PR scope; not
  imported anywhere else.
- `web/tests/e2e/home_g1_g8.spec.ts` — superseded by home_proof_as_cta +
  home_aa.

## Files I have ALSO checked and they're clean

- `web/components/app_shell.tsx` — `/` is chromeless per AppShellGate
  (verified by Codex iter-3 grounded repo check); AppShell renders no
  chrome on Home, no change required.
- `web/components/app_shell_gate.tsx` — same; no change required.
- `web/components/primary_nav.tsx` — Home no longer renders it; other
  routes (Intake/Dashboard/Inspector) still use it.
- `web/components/site_footer.tsx` — still rendered by Home, unchanged.
- `web/components/signature/maple_leaf_signature_lazy.tsx` — still
  rendered by Home, unchanged.
- `web/lib/nav.ts` — comment references `HomeKeyboardShell` historically;
  not a functional dependency.
- `web/tests/e2e/intake_g1_g8.spec.ts` — comment references
  `home_g1_g8.spec.ts` pattern historically; no functional dependency.
- `web/tests/e2e/command_palette.spec.ts`, `command_palette_adversarial.spec.ts`,
  `command_palette_suggest.spec.ts` — pass unchanged; palette + sign-in-link
  preserved by HomePaletteShell.
- `web/tests/e2e/f1_multi_tab.spec.ts` — depends on `header-sign-in-link`
  only; preserved.

## Carry-forwards (Codex iter-4 P3 / future follow-ups)

- P3-001: templates array duplicated in `page.tsx` from the deleted
  HomeKeyboardShell — fold into a shared module in a future cleanup PR.
- P3-002: `recent_runs_strip.tsx` could be salvaged for the Dashboard
  rebuild (sub-PR 3+) rather than the cold delete here. Tracked.
- P3-003: §0 brief cap block is the shortened-but-equivalent version;
  archive briefs should use the full canonical block from CLAUDE.md
  §8.3.1 next iteration.

## Verdict

Ready for Codex diff review.
