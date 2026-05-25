Sub-PR 2 of approximately 7 for I-ux-001c. Rebuilds `/` (Home) to the
v6 marketing-auth hero from the I-ux-001d Figma design lock.

## Status

- Brief: APPROVED Codex iter-4 (`accept_remaining`, 0 P0/P1)
- Diff: APPROVED Codex iter-3 (`accept_remaining`, 0 P0/P1)
- Typecheck: PASS · Lint: PASS (0 errors; 2 pre-existing warnings outside this PR)
- Playwright e2e + axe: NOT YET RUN (requires `npm run dev`)
- Codex visual audit on LIVE render: PENDING (requires deployed page)

## What ships

10 files (≈600 LOC added, ≈770 LOC deleted via 4 orphan removals):

NEW
1. `web/components/home/home_palette_shell.tsx` (~85 LOC) — minimal client
   shell with `Ctrl+K` + `<CommandPalette>` + `<Link data-testid="header-sign-in-link">`
   focus-restore target. Drops marketing-header chrome since `/` is
   chromeless per AppShellGate.
2. `web/components/home/proof_as_cta.tsx` (~165 LOC) — v6 verified-claim
   hero card. Bolded-green numerics via `proof-numeric` spans; null-safe
   `against <journal> <year> source span` tail (4 fallback templates);
   tri-state signature pill (only `gpg_verified` renders green);
   honest-fail fallback when `bundle_loaded: false`.
3. `web/lib/home_brief_loader.ts` (~190 LOC) — server-side reader.
   STRICTER verified-gate than the Inspector: `verifier_pass` AND real
   resolvable span AND (pure-prose OR matched===total). Home renders
   under "VERIFIED CLAIM" with no PARTIAL variant, so a partial-numeric
   claim must not slip through.
4. `web/tests/e2e/home_proof_as_cta.spec.ts` (~120 LOC) — 8 Playwright cases.
5. `web/tests/e2e/home_aa.spec.ts` (~55 LOC) — axe WCAG 2.2 AA, desktop +
   mobile, asserts zero violations across ALL impacts (not just
   serious/critical).

REBUILD
6. `web/app/page.tsx` — v6 marketing-auth hero, wrapped in HomePaletteShell.

EDIT
7. `web/app/globals.css` (+20 LOC) — paired `--color-certainty-{level}` (bg)
   + `--color-certainty-{level}-fg` (fg) Tailwind v4 tokens. Addresses
   the brief iter-4 P2-001 (bg/fg can't share one Tailwind color namespace).

DELETE
8. `web/app/components/home_keyboard_shell.tsx` — superseded by HomePaletteShell.
9. `web/app/components/proof_showcase.tsx` — absorbed into proof_as_cta + loader.
10. `web/app/components/recent_runs_strip.tsx` — out of sub-PR scope.

UPDATED
- `web/tests/e2e/f1_a11y.spec.ts` — new home selectors
- `web/tests/e2e/demo_journey.spec.ts` — primary CTA replaces hero search
- `web/tests/e2e/demo_walkthrough.spec.ts` — primary CTA + proof-as-cta

ALSO DELETED
- `web/tests/e2e/home_g1_g8.spec.ts` — superseded by home_proof_as_cta + home_aa

KEPT UNCHANGED (HomePaletteShell preserves selectors)
- `web/tests/e2e/command_palette.spec.ts`
- `web/tests/e2e/command_palette_adversarial.spec.ts`
- `web/tests/e2e/command_palette_suggest.spec.ts`
- `web/tests/e2e/f1_multi_tab.spec.ts` (header-sign-in-link only)

## Locked v6 spec

- Brand-red eyebrow: "POLARIS · CANADIAN-HOSTED CLINICAL RESEARCH"
- H1 (display): "Every sentence proves itself."
- Subtitle: honest Canadian-hosted sovereignty wording (never present-tense
  "Sovereign" — LLM inference is routed via OpenRouter-US, disclosed at
  `/transparency`)
- Proof-as-CTA card with REAL verified claim from the canonical bundle
- ONE primary CTA: "Try a verified brief →" → `/intake`
- Chromeless page (AppShellGate); palette + sign-in link preserved via
  HomePaletteShell

## Honest-fail rules verified (LAW II)

- Loader gates on `verifier_pass` AND real span AND (pure-prose OR
  matched===total). No silent fabrication.
- `bundle_loaded: false` → "Verified clinical brief loading — see the full
  proof now." with deep link. NO numeric stamp, NO signature pill.
- `signature_state === "gpg_verified"` is the ONLY state that renders the
  green "Signed bundle" pill; other states render their own honest copy.
- Numerics highlighter regex matches the loader's `extractNumerics`; visual
  and count are guaranteed in sync.

## Iter trail (brief + diff cycles)

- Brief iter-1: REQUEST_CHANGES (3 P1 + 2 P2)
- Brief iter-2: REQUEST_CHANGES (1 continuing P1 — palette-ownership grounded check)
- Brief iter-3: REQUEST_CHANGES (1 P1 ambiguity + 1 P2 null-safe footer + 1 P3 file count)
- Brief iter-4: APPROVE (accept_remaining)
- Diff iter-1: APPROVE (accept_remaining, 3 P2 carry-forwards)
- Diff iter-2: REQUEST_CHANGES (P2-001 elevated to P1 — Home verified-gate)
- Diff iter-3: APPROVE (accept_remaining, 1 out-of-scope P2 on legacy routes)

## Carry-forward to subsequent sub-PRs

- P2 (Codex iter-3): legacy `web/app/retrieval/page.tsx:80` and
  `web/app/generation/page.tsx:92` still contain present-tense "Sovereign"
  copy. Out of sub-PR 2 scope; fold into a future AppShell sweep.
- P3 (brief iter-4): templates array duplicated in `page.tsx` from the
  deleted HomeKeyboardShell. Fold into a shared module in a cleanup PR.

## Per-Issue 5-artifact triple

All present in `.codex/I-ux-001c-2/` + `outputs/audits/I-ux-001c-2/`:
- `brief.md`
- `codex_brief_verdict.txt` (iter-4 APPROVE)
- `codex_diff.patch` (with canonical-diff-sha256 trailer)
- `codex_diff_audit.txt` (iter-3 APPROVE)
- `claude_audit.md`

## Next per operator military-order directive

- Codex visual audit via `codex exec -i` on LIVE render (requires `npm run dev` + screenshots)
- Codex lively audit (motion + interaction stills)
- E2E + axe Playwright runs (locally + on CI)
- After merge: live-verify on polarisresearch.ca

Co-Authored-By: Claude Opus 4.7 (1M context) <noreply@anthropic.com>

🤖 Generated with [Claude Code](https://claude.com/claude-code)
