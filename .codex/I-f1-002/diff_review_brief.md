# Codex Diff Review Brief — I-f1-002 (ITER 1 of 5)

**HARD ITERATION CAP: 5 per document. This is iter 1 of 5.**
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE'd; do not bank.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Context

Second of two Codex review gates for I-f1-002. Brief Codex APPROVE'd iter 5 (zero P0/P1). This iter reviews the actual code diff against the iter-5 spec.

- **Brief:** `.codex/I-f1-002/brief.md` (Codex APPROVE iter 5 with 1 cosmetic P2)
- **Diff:** `.codex/I-f1-002/codex_diff.patch` (canonical sha256 `c91934f09869cc4b628ab1698f6de234b92da03300f59e5dcb71efb36feedb5e`)
- **Audit:** `outputs/audits/I-f1-002/claude_audit.md`

## Empirical verification (Claude verified)

- `npx tsc --noEmit -p .` from `web/` → no errors.
- `npx eslint <my files>` → no errors.
- Playwright not run locally (requires dev server + Chromium download).

## Files (4 in canonical diff, +198 net)

```
web/app/page.tsx                                 MOD +3 / -20  (remove inline header; wrap in shell)
web/app/components/home_keyboard_shell.tsx       NEW +49       (palette state + signInLinkRef + header)
web/app/components/command_palette.tsx           NEW +102      (Dialog + filter + arrow nav + Enter)
web/tests/e2e/command_palette.spec.ts            NEW +64       (3 keyboard-only tests)
```

CHARTER §1 200-LOC hard cap: +198 net (under cap with 2 LOC headroom).

## Specific risks for Codex Red-Team

1. **CHARTER §1 200-LOC cap.** +198 net. Under cap. Verify `git diff --cached -- :(exclude).codex/I-f1-002/ :(exclude)outputs/audits/I-f1-002/ | numstat` matches.

2. **Focus restoration single-source binding.** Verify ONLY `signInLinkRef` (HTMLAnchorElement, ref attached on the Link in HomeKeyboardShell) is used for focus return. No `document.activeElement` capture. No parent-passed ref. The CommandPalette accepts the ref via prop and calls `requestAnimationFrame(() => signInLinkRef.current?.focus())` on Dialog close.

3. **Templates source single-binding.** Verify templates stay as a private local `const` in `web/app/page.tsx` (not exported, not moved to `lib/templates`). Page passes `templates={templates}` as prop to `<HomeKeyboardShell>`, which forwards to `<CommandPalette templates={templates}>`. NO cross-module template import.

4. **No `useEffect` setState anti-pattern.** Active-index clamping done inline as `clamped = filtered.length === 0 ? 0 : Math.max(0, Math.min(active_index, filtered.length - 1))`. No `useEffect(() => set_active_index(...), [filtered.length])` (that would trigger `react-hooks/set-state-in-effect`).

5. **Hydration race avoidance.** Every Playwright test starts with `await expect(page.getByTestId("header-sign-in-link")).toBeVisible()` after `goto('/', { waitUntil: 'networkidle' })`. Guarantees client shell hydrated before keypress.

6. **Disabled-Enter no-op test URL agnosticism.** Test 2 captures `const before = page.url()` and asserts `expect(page).toHaveURL(before)` — works against any Playwright base URL.

7. **Sign-in selector.** Test 3 uses `getByTestId("header-sign-in-link")` to assert focused — selects by stable testid (Link, not Button role).

8. **Toggle-on-second-Ctrl+K not test-asserted.** Implementation does `set_palette_open(p => !p)`. Acceptable per claude_audit (test count trimmed to fit 200-cap).

9. **`canonical-diff-sha256` trailer correctness.** `c91934f09869cc4b628ab1698f6de234b92da03300f59e5dcb71efb36feedb5e` produced via `git diff --cached -- :(exclude).codex/I-f1-002/ :(exclude)outputs/audits/I-f1-002/`.

10. **No regressions** to `landing_template_grid.spec.ts` or `demo_walkthrough.spec.ts` (those still target `template-card-*` testids; this Issue does not change the grid).

## Output schema (mandatory)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
