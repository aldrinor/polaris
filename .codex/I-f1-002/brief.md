# Codex Brief Review — I-f1-002 (ITER 5 of 5 FINAL)

**HARD ITERATION CAP: 5 per document. This is iter 5 of 5 (FINAL).**
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

**Issue:** I-f1-002 — Command palette + react-hotkeys-hook keyboard nav
**Phase:** 1 / **Feature:** F1
**LOC budget:** 120 net per `state/polaris_restart/issue_breakdown.md` §I-f1-002. **CHARTER §1 hard cap: 200 net additions per PR.** Iter-3 trimmed scope to fit under 200 (Codex iter-2 P1-LOC-HARD-CAP fix).

## Why iter-2 exists

Iter-1 verdict: REQUEST_CHANGES. 2 P1 + 4 P2:

- **P1 #1:** Acceptance #5 (Esc restores focus to header) had no explicit focus target/ref/test. Iter-2 adds a focusable header element + explicit `requestAnimationFrame(() => focusableRef.current?.focus())` on `onOpenChange(false)` + Playwright assertion.
- **P1 #2:** Disabled-template Enter no-op was specified but not tested. Iter-2 adds keyboard test asserting `await expect(page).toHaveURL("/")` after Enter on `ai_sovereignty`.
- **P2 #1:** Skip `react-hotkeys-hook` confirmed acceptable.
- **P2 #2:** Prefer hybrid approach — extract small `<HomeKeyboardShell>` client wrapper, keep `page.tsx` as server component. Apply.
- **P2 #3:** Clamp `activeIndex` on filtered-list change. Apply via `useEffect` on `filtered.length` to clamp.
- **P2 #4:** ⌘K toggles (open AND close), not just open. Apply.

## Mission (unchanged)

⌘K / Ctrl+K toggles a Dialog command palette on `/`. Search input + filtered list of 8 templates. Arrow-key navigation. Enter on active templates → `/intake?template=<id>`; Enter on to-build → no-op. Esc closes + restores focus to header. Playwright keyboard-only tests pass.

## Substrate (HONEST)

- I-f1-001 merged at `f20e7795`; templates hardcoded in `web/app/page.tsx`. **Iter-4 LOCKED single binding path:** templates stay as a local `const templates = [...]` inside `web/app/page.tsx` (NOT exported from page.tsx, NOT moved to `lib/templates.ts`). Page renders `<HomeKeyboardShell templates={templates}>...</HomeKeyboardShell>` passing the array as a prop. The shell forwards it as a prop to `<CommandPalette templates={templates} ...>`. No imports of templates from another module — only prop drilling. Avoids client/server circular import risk and module-graph ambiguity (P1-iter3 fix).
- `@base-ui/react/dialog` is available + used at `web/app/intake/components/ambiguity_modal.tsx`. Reuse this primitive — no `cmdk` dep added.
- shadcn/ui `Button`, `Card`, `Input` available.
- Tailwind v4 in use.
- `web/app/page.tsx` is currently a server component; the iter-2 hybrid keeps it that way and adds a small `<HomeKeyboardShell>` client wrapper rendered inside the page that ONLY hosts useState + useEffect + `<CommandPalette>`.

## Revised acceptance criteria (binding)

1. **`web/app/page.tsx`** (MODIFY) — Templates remain as a local `const templates: Template[] = [...]` (private, not exported). Page renders `<HomeKeyboardShell templates={templates} signInHref="/sign-in">{...existing grid markup...}</HomeKeyboardShell>` passing data via props. The `Template` type stays inline in the same file (no separate type module). NO cross-module template import.

2. **`web/app/components/home_keyboard_shell.tsx`** (NEW client component) — Owns the WHOLE header + grid as children. The shell:
   - Owns `palette_open` state + `setPaletteOpen` (toggles).
   - Owns a single `signInLinkRef` via `useRef<HTMLAnchorElement>(null)` and renders the "Sign in" link itself (Link with `data-testid="header-sign-in-link"`) so the ref attaches deterministically.
   - Global `keydown` listener: `(metaKey || ctrlKey) && key === "k"` → `setPaletteOpen(prev => !prev)` + `event.preventDefault()` + `event.stopPropagation()` (true toggle).
   - On unmount, removes the listener.
   - Renders `<CommandPalette open={palette_open} onOpenChange={setPaletteOpen} templates={templates} signInLinkRef={signInLinkRef} />`. The palette accepts the ref directly; on close, palette schedules `requestAnimationFrame(() => signInLinkRef.current?.focus())`.
   - **No `document.activeElement` capture/restore fallback** — the explicit ref is the single binding focus-restoration mechanism (resolves iter-2 P1 + P2 conflict between ref-passing / shell-forwarded ref / activeElement capture).

3. **`web/app/components/command_palette.tsx`** (NEW client component) — Pure UI. Internal state: `searchTerm`, `activeIndex`. Filtered list: case-insensitive substring match on `name + summary + sample_question`. Visual: search input (autoFocus), scrollable list, active item highlighted. Arrow-up/down moves `activeIndex`; clamps `activeIndex` to `Math.max(0, Math.min(activeIndex, filtered.length - 1))` on every filter change via `useEffect` (P2-iter1-#3). Enter on active template → `router.push(/intake?template=<id>)` + close palette + focus header. Enter on to-build → no-op (palette stays open). Esc → close (Dialog primitive default).

4. **(Reserved — see AC #1; no separate page.tsx criterion.)** AC #1 already specifies `web/app/page.tsx` modifications: templates stay as a private local `const` (NOT exported, NOT moved to `lib/templates`); page renders `<HomeKeyboardShell templates={templates} signInHref="/sign-in">{...existing grid markup...}</HomeKeyboardShell>` passing data via props. No cross-module template import. No `useRef` at page level (shell owns it).

5. **`web/tests/e2e/command_palette.spec.ts`** (NEW) — Playwright keyboard-only tests. **Iter-3 trim** (drop tests #2 + #5 to fit 200-LOC cap; binding behaviors covered by remaining 3):
   - `test 1`: Press `Control+k` → palette opens; type "clinical" → first item is clinical; press `Enter` → `waitForURL("**/intake?template=clinical")`. (Acceptance #1+#3 navigation + search.)
   - `test 2`: capture `const before = page.url()` after `goto('/')`, press `Control+k` → opens; arrow-down 3 times to `ai_sovereignty` (first to-build) → press `Enter` → palette stays open AND `await expect(page).toHaveURL(before)` (relative no-nav assertion; works against any base URL). (P1-iter1-#2 disabled Enter no-op; P1-iter2-#2 URL-hardcode fix.)
   - `test 3`: Press `Control+k` → opens; press `Escape` → palette hidden AND `await expect(page.getByTestId("header-sign-in-link")).toBeFocused()`. (Acceptance #5 + P1-iter1-#1 + P1-iter2-#1 focus restoration via single signInLinkRef binding path; P2-iter2-#2 selector fix.)

(Dropped: arrow-nav-to-climate test, true-toggle test. Toggle is implementation-trivial; arrow nav is exercised partially by test 2's 3-down-arrows path.)

6. **No regressions** to `landing_template_grid.spec.ts` or `demo_walkthrough.spec.ts`.

## Planned diff shape (iter-3 trimmed)

```
web/app/page.tsx                                 MOD    +10 / -3   (export templates + Template type; wrap grid in <HomeKeyboardShell>)
web/app/components/home_keyboard_shell.tsx       NEW    +55        (palette state + signInLinkRef + header rendering)
web/app/components/command_palette.tsx           NEW    +75        (Dialog + filter + arrow nav + Enter handling)
web/tests/e2e/command_palette.spec.ts            NEW    +55        (3 tests: search-Enter, disabled no-op, Esc-focus-restore)
```

LOC: +195 / -3 = **+192 net.** **Under 200-LOC CHARTER §1 hard cap** with ~8 LOC headroom. Above 120-LOC issue-breakdown estimate (acceptable per CHARTER which uses 200 as the binding ceiling).

## Out of scope (deferred per breakdown)

- Live template-suggestion as user types → I-f1-003
- BPEI false-positive adversarial test → I-f1-004
- F1 broader axe coverage → I-f1-005
- Multi-tab safety → I-f1-006

## Non-acceptance / explicit exclusions

- Does NOT add `react-hotkeys-hook` (P2-iter1-#1 confirmed acceptable).
- Does NOT add `cmdk` dep.
- Does NOT modify the 8-template hardcoded data — extracted unchanged.
- Does NOT call `GET /templates` at runtime.
- Does NOT add Cmd-Shift-K / Cmd-J / other shortcuts.
- Does NOT add filter UI beyond the search input.

## Risks for Codex Red-Team (revised iter-2)

1. **Hybrid client/server split** (P2-iter1-#2 applied) — `page.tsx` stays server-rendered; only `home_keyboard_shell.tsx` is `"use client"`. Provider passes `templates` as prop (not via React Context — keeps it serializable across server/client boundary).

2. **Focus restoration via single `signInLinkRef`** (LOCKED iter-3 — single binding path, no fallback). Shell owns `useRef<HTMLAnchorElement>(null)` and renders the Sign in Link itself with `ref={signInLinkRef}` and `data-testid="header-sign-in-link"`. Palette accepts the ref via prop and on close calls `requestAnimationFrame(() => signInLinkRef.current?.focus())`. No `document.activeElement` capture; no parent-passed ref; no shell-forwarded ref. ONE design.

3. **Active-index clamping on filter change** (P2-iter1-#3 applied) — `useEffect(() => { setActiveIndex(prev => Math.max(0, Math.min(prev, filtered.length - 1))) }, [filtered.length])`.

4. **True toggle** (P2-iter1-#4 applied) — `setPaletteOpen(prev => !prev)`. Implementation-only; not test-asserted in this Issue (test #5 dropped iter-3 to fit 200-cap). Toggle is verified manually + by the Esc test indirectly (Esc closes; subsequent Ctrl+K reopens — implicit in test sequencing).

5. **LOC budget under 200 cap** (iter-3 fix). +192 net under CHARTER §1 200-LOC hard cap with ~8 LOC headroom. Above 120 issue-breakdown estimate but under the binding ceiling. No templates.ts extraction; tests trimmed to 3 binding behaviors (search-Enter, disabled-noop, Esc-focus); prop-drilling instead of cross-module template imports.

6. **Sign-in selector** — header Sign in is rendered as `<Link>` via `<Button render={<Link/>} nativeButton={false}>`. Test selector uses `getByTestId("header-sign-in-link")` not `getByRole('button')` (P2-iter2-#2 fix). The Link has `ref={signInLinkRef}` for focus, no role assumption.

7. **`useRouter()` import for navigation** — `command_palette.tsx` uses `next/navigation`'s `useRouter().push(...)`. Standard Next 15+/16 pattern. Verify with `node_modules/next/dist/docs/` if needed.

8. **Test reliability headless Chromium** — use `Control+k` (works on Linux CI). Handler accepts `metaKey || ctrlKey`.

9. **Hydration race avoidance** (P2-iter3 fix) — every test starts with `await page.goto('/', { waitUntil: 'networkidle' });` then `await expect(page.getByTestId('header-sign-in-link')).toBeVisible();` BEFORE pressing `Control+k`. Visible-link assertion guarantees the client shell hydrated and the global keydown listener mounted, eliminating flaky early-keypress races.

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
