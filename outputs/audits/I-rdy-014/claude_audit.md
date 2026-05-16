# Claude architect audit — I-rdy-014 (#510)

**Issue:** Phase 3.11 — coherent demo journey + global nav, hide 17 harness routes.
**Branch:** `bot/I-rdy-014-demo-journey-nav` off `polaris`.
**Canonical diff sha256:** `f6b59b4d0c631bb30e6f4f37cb31860dd30e48b1c4f4b0ce389145577f2b1873`
**Brief:** Codex APPROVE iter 4 (`.codex/I-rdy-014/codex_brief_verdict.txt`).
**Scope:** B-split (Codex iter-3 ruling) — follow-up UI / run-compare UI /
real-run bundle bridge carved to #542 / #543 / #544; #510 acceptance amended
on the issue. Frontend-only, no backend change.

## Diff-vs-brief verification (file by file)

### `web/app/components/global_nav.tsx` (NEW, +91)
Single global header: brand → `/`; links Home / Start a run / Workspace
memory / Pin & replay; right-side **Sign in** (`data-testid="header-sign-in-link"`
— preserves the id the command-palette specs use). `usePathname()` →
`isSuppressed()` returns `null` on `/sign-in` and URL prefixes
`/charts_test`, `/sentence_hover_test`, `/disambiguation_modal_preview`
(URL-prefix match, not the route-group filesystem — Codex iter-1 ruling).
**Verified.**

### `web/app/layout.tsx` (+2)
`<GlobalNav />` mounted once above `{children}`. **Verified.**

### `web/app/page.tsx` (+2/−2)
Template-card link `/intake?template=` → `/dashboard?template=`;
`HomeKeyboardShell` no longer passed `signInHref`. **Verified.**

### `web/app/components/command_palette.tsx` (+9/−6)
Active-template `router.push` `/intake` → `/dashboard?template=` (Codex
iter-1 P1-1 — the keyboard path). `signInLinkRef` prop removed; close-focus
now `document.querySelector('[data-testid="header-sign-in-link"]')` (works
across the layout/page boundary now that the link lives in GlobalNav).
`RefObject` import dropped. **Verified.**

### `web/app/components/home_keyboard_shell.tsx` (+11/−31)
Brand/sign-in `<header>` removed (GlobalNav owns it); keeps the Cmd/Ctrl-K
handler + `CommandPalette` mount. `Button`/`Link`/`useRef`/`signInHref`
dropped. **Verified.**

### `web/app/dashboard/page.tsx` (+25/−15)
Duplicate brand header removed. `?template=` preselect: `useSearchParams()`
+ a **lazy `useState` initializer** (derived initial state, no effect — the
ESLint `react-hooks/set-state-in-effect` rule that bit #505 is satisfied
by construction). Page wrapped in `<Suspense>` (App-Router requirement for
`useSearchParams`). **Verified.**

### `web/app/runs/[runId]/page.tsx` (+22/−9)
Duplicate brand header removed (page-action bar kept). "Open Inspector" →
**"View report & inspect"** (the integrated-report + inspect journey step).
New authenticated **Download signed bundle** button → `downloadBundleTarball`.
JSON export relabelled "Export bundle (JSON)" (secondary). No graph link
added (Codex iter-3 P1-3). **Verified.**

### `web/app/inspector/[runId]/page.tsx` (+58/−11)
Header brand wordmark made non-link; authenticated **Download signed bundle**
button added. **Codex iter-3 P1-1 graceful 404:** `getBundle` catch now
distinguishes `status === 404` → `notReady` → an honest "Report not yet
available" `role="status"` panel with a back-link to the run — never a
crash. Non-404 still → error panel. **Verified.**

### `web/lib/api.ts` (+28)
`downloadBundleTarball(runId)` — `authFetch` GET `/runs/{id}/bundle.tar.gz`
→ `response.blob()` → object-URL download → revoke. Throws on non-OK so
callers surface a pending/unavailable state (Codex iter-3 P1-2: a plain
`<a href>` cannot carry `Authorization: Bearer`). **Verified.**

### `web/app/benchmark/page.tsx` (−33)
Dead `/generation` link removed (Codex iter-2/3); the dup brand header
removed; `Button`/`Link` imports dropped. **Verified.**

### e2e specs
- `demo_journey.spec.ts` (NEW, +97): journey + GlobalNav reachability +
  harness suppression + a "no journey page links to a harness/slice-era
  route" assertion (Codex iter-2 P2 — assert the rendered link surface).
- `command_palette.spec.ts`, `command_palette_suggest.spec.ts`,
  `landing_template_grid.spec.ts`: `/intake` click-path assertions
  repointed to `/dashboard` (Codex iter-2 P1-4).
- `demo_walkthrough.spec.ts` (−69): the slice-era `home→intake→retrieval→
  generation→benchmark` path — superseded by `demo_journey.spec.ts`,
  removed (Codex iter-2 P1-4: do not leave the old path as expected).

## Test evidence
- `npx tsc --noEmit` — exit 0.
- `npx eslint` on all 13 changed `app/`+`lib/` files + the new spec — 0
  errors. 1 pre-existing warning (`inspector/[runId]/page.tsx:558`
  `ExecutiveSummaryTab` `chartTypes` exhaustive-deps) — untouched code,
  not introduced by #510.
- Playwright not run in this environment (no dev server); `demo_journey.spec.ts`
  is navigation-only and asserts against the journey wiring this diff lands.

## §-1.1 note
Not a clinical-content change — no report claims, citations, or evidence
spans. This is navigation/journey assembly; the line-by-line clinical audit
standard does not apply.

## Residual (carved, honest disclosure)
- Follow-up UI → #542 (I-rdy-014a). Run-compare UI → #543 (I-rdy-014b).
- Real-run bundle/EvidenceContract bridge → #544 (I-rdy-014c): until it
  lands, a freshly-created dashboard run's `/inspector` shows the honest
  "report not yet available" pending state (`bundle` 404).

## Verdict
Implementation matches the Codex-APPROVE'd iter-4 brief and all iter-1/2/3
P1 fixes. Amended acceptance met: the journey is navigable with no crash /
dead end; 17 harness routes unreachable from the demo nav. Recommend APPROVE.
