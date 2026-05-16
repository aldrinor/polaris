# Codex DIFF review — I-rdy-014 (#510): coherent demo journey + global nav

## §0. HARD ITERATION CAP (verbatim, CLAUDE.md §8.3.1)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

**This is iter 1 of 5.** DIFF review (code correctness vs the APPROVE'd brief).

## §1. What to review

Diff: `.codex/I-rdy-014/codex_diff.patch`
(canonical-diff-sha256 trailer = `f6b59b4d0c631bb30e6f4f37cb31860dd30e48b1c4f4b0ce389145577f2b1873`).
APPROVE'd brief: `.codex/I-rdy-014/brief.md` (Codex APPROVE iter 4,
`.codex/I-rdy-014/codex_brief_verdict.txt`). 15 files, +349 / −186,
frontend-only. **Scope = B-split** (Codex iter-3 ruling): #510 ships the
nav/journey skeleton; follow-up UI / run-compare UI / real-run bundle bridge
are carved to #542 / #543 / #544 and #510 acceptance amended on the issue.

## §2. Implementation summary (verify against the diff)

- `global_nav.tsx` (NEW) — single header, `usePathname()` suppression on
  `/sign-in` + harness URL prefixes; mounted in `layout.tsx`.
- `page.tsx` + `command_palette.tsx` — `/intake?template=` →
  `/dashboard?template=` (both the click and keyboard entry).
- `home_keyboard_shell.tsx` — brand `<header>` removed; keyboard + palette
  kept; `signInLinkRef` removed (close-focus → `querySelector` on the
  GlobalNav sign-in link, `data-testid="header-sign-in-link"`).
- `dashboard/page.tsx` — dup header removed; `?template=` preselect via
  `useSearchParams` + lazy `useState` initializer; `<Suspense>` wrapper.
- `runs/[runId]` + `inspector/[runId]` — dup brand headers removed;
  "View report & inspect" link; authenticated `.tar.gz` download;
  inspector renders an honest pending state on bundle-404.
- `lib/api.ts` — `downloadBundleTarball` (authFetch blob → object URL).
- `benchmark/page.tsx` — dead `/generation` link removed.
- e2e — `demo_journey.spec.ts` (NEW); 3 stale `/intake` click-path specs
  repointed; `demo_walkthrough.spec.ts` (slice-era path) removed.

## §3. Suggested focus (Red-Team checklist)

1. **GlobalNav suppression** — `isSuppressed` URL-prefix logic: correct for
   `/sentence_hover_test/coverage` etc.? Does it wrongly suppress a real
   route? `usePathname()` null-guard.
2. **Auth tarball** — `downloadBundleTarball` uses `authFetch`; non-OK
   throws; object URL revoked. Both `runs[]` and `inspector[]` buttons
   catch and surface the error.
3. **Inspector 404** — `notReady` distinguishes `status===404` from real
   errors; the pending panel is `role="status"`, not a dead end.
4. **Dashboard `?template=`** — lazy `useState` initializer (no
   setState-in-effect); `<Suspense>` wraps the `useSearchParams` consumer;
   invalid `?template=` falls back to `clinical`.
5. **No dead ends / no harness links** — does any journey page still link
   to a harness or slice-era route? (`demo_journey.spec.ts` asserts this.)
6. **Removed imports** — `Button`/`Link`/`useRef`/`RefObject` drops leave
   no dangling reference (tsc + eslint both clean — see §4).
7. **Stale specs** — the repointed click-path specs + the
   `demo_walkthrough` removal; no other spec still expects `/intake` via a
   click. Specs that `goto('/intake')` directly are intentionally kept
   (the `/intake` route still exists).
8. No backend change; no secret material in the diff; no `git add -A`.

## §4. Evidence

- `npx tsc --noEmit` — exit 0.
- `npx eslint` — 0 errors across all 13 changed `app/`+`lib/` files + the
  new spec. 1 pre-existing warning (`inspector/[runId]/page.tsx:558`,
  untouched `ExecutiveSummaryTab`).
- Playwright not run here (no dev server); `demo_journey.spec.ts` is
  navigation-only against the wiring this diff lands.

## §5. Output schema (CLAUDE.md §8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
