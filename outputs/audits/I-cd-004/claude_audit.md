# I-cd-004 — Claude architect audit

**Issue:** GH#607 — Global app shell + design tokens + finalize route map.
**Deliverable:** the global `<AppShell>` server component, a `<NavLink>` client
component for active-route highlight, the locked route-map doc, the locked
canonical-token doc, and the minimal `web/app/layout.tsx` wiring.

## What this changes

- `web/components/app_shell.tsx` (NEW, ~50 LOC) — server-component header with
  brand-mark + 8-item primary nav.
- `web/components/nav_link.tsx` (NEW, ~25 LOC) — client component using
  `usePathname()` for `aria-current="page"` + active styling via the locked
  shadcn tokens.
- `web/app/layout.tsx` (+2/-1) — wraps `{children}` in `<AppShell>`.
- `docs/web/route_map.md` (NEW, ~44 LOC) — the Codex-APPROVED route map:
  KEEP 10 prod routes, CUT 3, ABSORB 1 into `/runs/[runId]` (with the explicit
  "RETIRED not merely hidden" framing per Codex P2), HARNESS 17 deferred to
  I-cd-015.
- `docs/web/design_tokens.md` (NEW, ~52 LOC) — locks the shadcn default theme
  in `globals.css` as the canonical set. No new tokens added; no `globals.css`
  edit.

## Scope discipline

This issue ships ONLY the shell + locks. The per-route rebuilds (I-cd-013..030)
re-skin their pages against the locked surface in their own PRs. Auth gating
of the shell is deferred to I-cd-014. Prod-build exclusion of harness routes
is I-cd-015.

## Verification

- Codex brief APPROVE iter 1; 0 P0, 0 P1; 5 P2s, every one a confirmation of
  an explicit `§G` open question — no real-issue findings.
- Offline: `tsc --noEmit` clean; `eslint` clean on the 3 changed/new TS files.
- The CI's path-filtered `lint + format + typecheck + build` job WILL run on
  this PR (touches `web/`) — the smoke covered the same surface locally.

## Risk surface

- The shell is rendered unconditionally; some current routes (e.g. `/sign-in`)
  will show the nav too. Acceptable per Codex P2 ("Auth gating can be
  deferred"); the auth rebuild owns hiding the nav from anonymous users.
- The 8 nav links point at routes whose per-page rebuilds haven't happened yet
  — they'll render the existing (not-yet-rebuilt) page content under the new
  shell. That's the intended interim state: the shell wraps EVERYTHING from
  now, and each rebuild improves the inside.
