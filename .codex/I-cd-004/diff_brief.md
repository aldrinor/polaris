HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. The COMPLETE diff under review is the single
committed file `.codex/I-cd-004/codex_diff.patch` (250 lines incl. trailer).
Read ONLY that one file.

# Codex DIFF review — I-cd-004 / GH#607: global app shell

## §A — What this is

The diff implements the Codex-APPROVED brief `.codex/I-cd-004/brief.md`
(brief APPROVE iter 1, all P2s confirmations). 5 source files + the §8.3.5
trajectory log:

- `web/components/app_shell.tsx` (NEW, ~50 LOC) — server-component header +
  8-item primary nav.
- `web/components/nav_link.tsx` (NEW, ~25 LOC) — client component, active
  highlight via `usePathname()`.
- `web/app/layout.tsx` (+2/-1) — wrap `{children}` in `<AppShell>`.
- `docs/web/route_map.md` (NEW) — the locked route map (KEEP 10 / CUT 3 /
  ABSORB 1 / HARNESS 17).
- `docs/web/design_tokens.md` (NEW) — locks the existing shadcn token set as
  canonical; `globals.css` itself unchanged.

Total canonical diff ~200 LOC; the code surface is ~75 LOC of TSX.

## §B — Smoke

- `tsc --noEmit` clean.
- `eslint` clean on `app/layout.tsx`, `components/app_shell.tsx`,
  `components/nav_link.tsx`.
- The CI's path-filtered `lint + format + typecheck + build` WILL run on this
  PR (touches `web/`) — local smoke covered the same surface.

## §C — Red-team focus

1. **Active-route logic in `NavLink`** — `pathname === href || (href !== "/"
   && pathname.startsWith(\`${href}/\`))`. Does the `/`-special-case prevent
   the Home link from being permanently active? Does the trailing-`/` rule
   correctly handle nested routes (e.g. `/runs/abc` does NOT activate
   `/intake`)? Any edge case (trailing slash on `pathname`, hash, query)?
2. **Server vs client boundary** — `AppShell` is a server component (no
   `"use client"`), `NavLink` is a client component (uses `usePathname`).
   Confirm the import path (`@/components/nav_link`) doesn't accidentally
   force `AppShell` to a client component, and `usePathname` is the right
   Next-16 app-router hook here.
3. **Token usage** — every class on the rendered elements (`bg-background`,
   `text-foreground`, `text-muted-foreground`, `bg-accent`, `text-accent-foreground`,
   `border-border`, `text-foreground`, `font-mono`, `font-medium`, `rounded-md`)
   maps to an entry in the locked `docs/web/design_tokens.md` set. Any ad-hoc
   non-token class?
4. **Route map doc accuracy** — does `docs/web/route_map.md` correctly mirror
   every iter-1 Codex confirmation? In particular the `/audit_live` framing
   ("RETIRED at I-cd-025, not merely hidden from nav").
5. **Scope discipline** — does the diff touch ONLY the shell + docs, with no
   per-route page edits or `globals.css` changes that would belong to
   I-cd-013..030?
6. **Accessibility** — `aria-label="Primary"` on `<nav>`,
   `aria-current="page"` on active `NavLink`. Sufficient?

## §D — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
