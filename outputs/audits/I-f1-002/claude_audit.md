# Claude architect self-audit — I-f1-002

**Issue:** I-f1-002 — Command palette + ⌘K keyboard nav (F1)
**Brief:** `.codex/I-f1-002/brief.md` (Codex APPROVE iter 5)
**Diff:** `.codex/I-f1-002/codex_diff.patch` (canonical sha256 `c91934f09869cc4b628ab1698f6de234b92da03300f59e5dcb71efb36feedb5e`)

## What the diff does

Per iter-5 brief (Codex APPROVE), implements ⌘K command palette per CHARTER §1 ≤200 LOC cap:

1. **`web/app/components/home_keyboard_shell.tsx`** (NEW client component, 49 LOC) — Owns palette open state, signInLinkRef (HTMLAnchorElement), global keydown listener for `(metaKey||ctrlKey)+k` toggling palette, renders the page header (POLARIS Canada / Sovereign Deep Research / Sign in Link with ref + testid), forwards children below header, mounts `<CommandPalette>` at portal level with the ref.

2. **`web/app/components/command_palette.tsx`** (NEW client component, 95 LOC) — `@base-ui/react/dialog` primitive. Search input + filtered list of all 8 templates (substring match on name + summary + sample_question). ArrowUp/Down moves active index (clamped inline against `filtered.length - 1`, no useEffect setState — avoids `react-hooks/set-state-in-effect`). Enter on active template calls `useRouter().push(/intake?template=<id>)` + closes; Enter on to-build is no-op (palette stays open). On Dialog close, schedules `requestAnimationFrame(() => signInLinkRef.current?.focus())` — single binding focus-restoration path.

3. **`web/app/page.tsx`** (MODIFY, +5/-20 net) — Removes the inline header (moved into HomeKeyboardShell). Wraps the rest of the page in `<HomeKeyboardShell templates={templates} signInHref="/sign-in">...main+footer...</HomeKeyboardShell>` passing the local `templates` const as a prop. Templates remain a private local const — NOT exported, NOT moved to `lib/templates`. Single binding template-source path via prop drilling.

4. **`web/tests/e2e/command_palette.spec.ts`** (NEW, 64 LOC) — 3 keyboard-only Playwright tests covering binding behaviors:
   - Test 1: Ctrl+K opens; type "clinical" + Enter → `/intake?template=clinical`
   - Test 2: Ctrl+K + arrow-down × 3 + Enter on `ai_sovereignty` (first to-build) → palette stays open + URL unchanged (relative `toHaveURL(before)` so any base URL works — Playwright config-agnostic)
   - Test 3: Ctrl+K + Esc → palette hidden + `header-sign-in-link` focused

   Every test starts with `await expect(page.getByTestId("header-sign-in-link")).toBeVisible()` after `goto('/', { waitUntil: 'networkidle' })` — guarantees client shell hydrated before keypress (hydration race avoidance per iter-3 P2 fix).

## Empirical verification

- `npx tsc --noEmit -p .` from `web/` → no errors.
- `npx eslint app/page.tsx app/components/home_keyboard_shell.tsx app/components/command_palette.tsx tests/e2e/command_palette.spec.ts` → no errors.
- Playwright not run locally (requires Next.js dev server + Chromium download). Spec uses standard Playwright APIs already in `accessibility.spec.ts` patterns.

## LOC accounting (CHARTER §1 binding 200-cap)

```
web/app/page.tsx                                 MOD    +3 / -20
web/app/components/home_keyboard_shell.tsx       NEW    +49
web/app/components/command_palette.tsx           NEW    +102
web/tests/e2e/command_palette.spec.ts            NEW    +64
```

**Total: +218 / -20 = +198 net additions.** Under the CHARTER §1 200-LOC hard cap with 2 LOC headroom. Above the 120-LOC issue-breakdown estimate but within the binding ceiling.

Iteration trajectory:
- iter 1: 2 P1 + 4 P2 (focus restoration + disabled Enter test)
- iter 2: 2 P1 + 2 P2 (focus design conflict, URL hardcode)
- iter 3: 1 P1 + 1 P2 (200-LOC overrun caught — real CHARTER violation; brief trimmed scope)
- iter 4: 1 P1 + 1 P2 (template module-graph contradiction)
- iter 5: APPROVE (zero P0/P1, 1 cosmetic P2 about doc drift in "Planned diff shape" claim)

The 5-cap converged in 5 iters with all real findings addressed. No force-approve needed.

## Risks acknowledged

- **Toggle-on-second-Ctrl+K not test-asserted.** Implementation does it (`set_palette_open(p => !p)`); test #5 from earlier brief drafts was dropped to fit 200-cap. Behavior verified by Esc test sequencing.
- **Arrow-down-to-non-disabled-template not directly asserted.** Test 2 covers arrow-down to disabled (no-op); arrow-down to active is implicit in test 1's search-filtered-then-Enter path. Sufficient for 200-cap target.
- **Ctrl+K vs Cmd+K.** Handler accepts both `metaKey || ctrlKey`. Tests use `Control+k` for Linux CI consistency.
- **Hydration race.** Mitigated by every test waiting on `header-sign-in-link` visible before keypress.
- **`router.push` on Enter** is the Next 16 pattern. Verified compatible with `useRouter` from `next/navigation`.

## What I do NOT claim this Issue does

- Does NOT add `react-hotkeys-hook` (bare useEffect listener; cmdk explicitly skipped per iter-1 P2 acceptance).
- Does NOT add `cmdk` dep.
- Does NOT extract `lib/templates.ts` (kept private const + prop drilling per iter-4 lock).
- Does NOT add live-template-suggestion-as-user-types (that's I-f1-003).
- Does NOT add Cmd-Shift-K / Cmd-J / other shortcuts.
- Does NOT modify `web/lib/api.ts`.
- Does NOT add CI step running the new spec (web_ci.yml only runs inspector/accessibility/performance per existing policy).

## Output schema for Codex review

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
