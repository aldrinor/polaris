# Codex diff review — I-ux-001c sub-PR 2 (Home v6 marketing-auth hero)

## §0 cap directive (CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## What you're reviewing

The diff at `.codex/I-ux-001c-2/codex_diff.patch` implementing sub-PR 2 against the brief at `.codex/I-ux-001c-2/brief.md` (APPROVED iter 4, accept_remaining).

PR scope (sub-PR 2 of approximately 7 for I-ux-001c):
- NEW `web/components/home/home_palette_shell.tsx` — minimal Ctrl+K shell
- NEW `web/components/home/proof_as_cta.tsx` — v6 verified-claim hero card
- NEW `web/lib/home_brief_loader.ts` — server-side bundle reader
- REBUILD `web/app/page.tsx` — v6 marketing-auth hero
- EDIT `web/app/globals.css` — paired certainty bg/fg Tailwind v4 tokens
- DELETE `web/app/components/home_keyboard_shell.tsx`
- DELETE `web/app/components/proof_showcase.tsx`
- DELETE `web/app/components/recent_runs_strip.tsx`
- DELETE `web/tests/e2e/home_g1_g8.spec.ts`
- NEW `web/tests/e2e/home_proof_as_cta.spec.ts` (8 Playwright cases)
- NEW `web/tests/e2e/home_aa.spec.ts` (axe WCAG 2.2 AA, desktop + mobile)
- UPDATED 3 existing tests (`f1_a11y`, `demo_journey`, `demo_walkthrough`)

## Brief acceptance criteria (must verify)

1. Eyebrow + H1 + subtitle render with the locked v6 copy
2. Proof-as-CTA card pulls a REAL verified claim from the canonical
   bundle (`v1-canonical-success`) — NEVER a synthesized claim or count
3. Honest-fail: when bundle is missing or no real span resolves,
   `bundle_loaded: false` → "still loading" copy, NO numeric stamp,
   NO signature pill (LAW II)
4. Numerics in the claim are bolded green via `proof-numeric` spans;
   the highlighter regex MUST match the loader's `extractNumerics`
   regex (visual and count in sync)
5. Matched-numbers stamp uses the null-safe source-tail templates
   (4 fallbacks for journal/year combinations)
6. Tri-state signature pill: only `gpg_verified` may render the green
   "Signed bundle" pill; the other two states render their own honest
   copy (Codex sub-PR-1 iter-1 P1-005 carry-forward)
7. HomePaletteShell preserves `Ctrl+K`, `<CommandPalette>` mount, and
   `data-testid="header-sign-in-link"` focus-restore target so the 3
   `command_palette*.spec.ts` files pass UNCHANGED
8. `--color-certainty-{level}` (bg) and `--color-certainty-{level}-fg`
   (fg) Tailwind v4 tokens resolve to DIFFERENT OKLCH values
   (iter-4 P2-001 fix)
9. AppShellGate keeps `/` chromeless — no AppShell-move; HomePaletteShell
   adds NO chrome beyond the sign-in escape hatch
10. typecheck PASS · lint PASS · `_nav_auth` helper is preserved
11. The 4 deletions are surgical — no orphaned imports anywhere
12. Honest sovereignty wording: "Canadian-hosted clinical research
    system, built toward sovereign Canadian deployment" — never
    present-tense "Sovereign" overclaim

## Specific checks I want explicit verdicts on (`specific_check_responses`)

- `verified_claim_is_real`: PASS / FAIL — does the loader's selection
  logic actually grab a real verified sentence from the canonical
  fixture, and does the highlighter's numeric-extraction regex match
  the loader's so the bolded numerics line up with the matched count?
- `honest_fail_no_synthesis`: PASS / FAIL — when `bundle_loaded:
  false`, is the rendered copy free of fake counts/signatures and
  does the UI link out instead of silently fabricating?
- `tri_state_sig_pill`: PASS / FAIL — only `gpg_verified` renders
  the green pill; `present_unverified` and `missing` render their
  own honest copy with distinct styling
- `palette_preserved`: PASS / FAIL — HomePaletteShell preserves the
  `Ctrl+K`, `<CommandPalette>`, and `header-sign-in-link` selectors
  such that the 3 `command_palette*.spec.ts` files PASS unchanged
- `tailwind_v4_certainty_tokens`: PASS / FAIL — the paired
  `--color-certainty-{level}` + `--color-certainty-{level}-fg` tokens
  resolve to DIFFERENT OKLCH values, not the same one
- `chromeless_home_preserved`: PASS / FAIL — AppShellGate still marks
  `/` chromeless; HomePaletteShell adds no chrome beyond the small
  sign-in escape hatch
- `orphaned_imports_clean`: PASS / FAIL — the 4 deletions leave no
  orphaned imports or stale references in `web/`
- `playwright_test_assertions_real`: PASS / FAIL — `home_proof_as_cta.spec.ts`
  asserts on real DOM shape, not just presence of testids (e.g. the
  `proof-numeric` test asserts `count > 0`, the matched stamp asserts
  the regex shape, the primary CTA asserts text + URL behavior)

## Output schema (BIND)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
specific_check_responses:
  verified_claim_is_real: PASS | FAIL_with_detail
  honest_fail_no_synthesis: PASS | FAIL_with_detail
  tri_state_sig_pill: PASS | FAIL_with_detail
  palette_preserved: PASS | FAIL_with_detail
  tailwind_v4_certainty_tokens: PASS | FAIL_with_detail
  chromeless_home_preserved: PASS | FAIL_with_detail
  orphaned_imports_clean: PASS | FAIL_with_detail
  playwright_test_assertions_real: PASS | FAIL_with_detail
```

## Read these for context

- Brief (APPROVED iter 4): `.codex/I-ux-001c-2/brief.md`
- Diff (this PR): `.codex/I-ux-001c-2/codex_diff.patch`
- Claude audit: `outputs/audits/I-ux-001c-2/claude_audit.md`
- Sub-PR 1 brief / iter trail (sister PR, same I-ux-001c initiative):
  `.codex/I-ux-001c/brief.md`, `codex_brief_verdict.txt`,
  `codex_diff_audit.txt`
- Project §-1.1 audit standard: `CLAUDE.md`
- Repo HEAD as of this submission: `bot/I-ux-001c-sub-pr-2-home`
