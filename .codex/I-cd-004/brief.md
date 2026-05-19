HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

DO NOT explore the repository. Everything you need is in this brief.

# Codex brief review — I-cd-004 / GH#607: Global app shell + design tokens + route map

This issue's acceptance ("route map (consolidate/cut) locked via **Codex consult**")
explicitly invites your judgement on the route-map decisions in §C. Confirm or
push back per-route.

## §A — Context (grounded this session via `find web/app -name page.tsx`)

- **Stack:** Next 16.2.4 (app router, Turbopack), React 19.2.4, Tailwind v4
  (`@import "tailwindcss"`), shadcn-ui (MIT) via `@import "shadcn/tailwind.css"`.
- **33 page.tsx files** in `web/app/`:
  - 16 "real" routes: `/`, `audit_live`, `benchmark`, `contracts`, `dashboard`,
    `generation`, `inspector/[runId]`, `intake`, `memory`, `pin_replay`,
    `retrieval`, `runs/[runId]`, `runs/[runId]/graph`, `sign-in`, `sse`,
    `upload`.
  - 17 test-harness routes: 1 in `(test_harness)/`, 5 in `charts_test/*`, 11 in
    `sentence_hover_test/*`. Prod-exclusion of these is **I-A-15 / I-cd-015**
    (separate issue) — not this issue's job.
- **Current root layout** (`web/app/layout.tsx`, 41 lines): minimal — html/body
  wrapper with Geist fonts + Sonner toaster. **No nav, no shell.** Every route
  renders with zero shared chrome.
- **Tokens** (`web/app/globals.css`, 137 lines): the shadcn default theme set is
  already present via `@theme inline` — `--color-primary`, `--background`,
  `--ring`, `--radius-*`, the sidebar tokens, the chart-1..5 set. They exist;
  what's missing is a **lock** (a canonical doc identifying which tokens are
  in scope) so the I-A-NN per-route rebuilds (Seq 13-30) can rely on them.
- **No nav/header/shell components** in `web/components/`.

## §B — Scope boundary (what I-cd-004 does vs the I-A-NN rebuilds)

**This issue ships:** the global shell + the locked route map + the locked
canonical token doc. The per-route rebuilds (`/inspector` → I-A-03 / I-cd-013,
`/sign-in` → I-A-04 / I-cd-014, `/` → I-A-05 / I-cd-022, etc.) are SEPARATE
issues in Seq 13-31 and re-skin their pages against the shell + tokens this
issue locks. I-cd-004 does NOT rewrite per-page content; it only provides the
chrome around them.

**Prod-exclusion of harness routes** is I-cd-015 (Seq 15) — out of scope here.

## §C — Proposed route map (Codex confirm/push-back)

Decisions, all explicitly tied to the breakdown's later rebuild rows:

| Status | Routes | Rationale |
|---|---|---|
| **KEEP-prod (10)** | `/`, `/sign-in`, `/intake`, `/dashboard`, `/inspector/[runId]`, `/runs/[runId]`, `/upload`, `/benchmark`, `/contracts`, `/pin_replay` | Each has a Seq-13..30 rebuild issue (I-A-03..12). The shell wraps them. |
| **KEEP-prod, sub-route (1)** | `/runs/[runId]/graph` | Nested under `/runs/[runId]` (I-A-08); no separate rebuild row, stays. |
| **ABSORB (1)** | `/audit_live` → `/runs/[runId]` | I-A-08 acceptance: "Rebuild `/runs/[runId]` (absorbs audit_live)". The standalone `/audit_live` is retired at the I-A-08 rebuild. |
| **CONDITIONAL — Codex decide (1)** | `/memory` | I-A-13 acceptance: "Rebuild `/memory` if route map keeps it." Recommend KEEP (campaign-memory is part of the substrate); confirm or cut. |
| **CUT-from-prod (3)** | `/generation`, `/retrieval`, `/sse` | None appear in any I-A-NN rebuild row. They look like in-progress dev test surfaces (SSE smoke, retrieval inspector, generator probe). Cut from the prod nav + handled by I-cd-015's prod-build exclusion. Confirm. |
| **HARNESS (17)** | `(test_harness)/...`, `charts_test/*`, `sentence_hover_test/*` | I-cd-015 (Seq 15) excludes these from the prod build. The shell-nav obviously doesn't list them. |

**Net prod nav: 10 top-level entries** (+ `/sign-in` is auth, not in nav; +
`/runs/[runId]` and `/inspector/[runId]` are run-scoped, surfaced contextually
from `/dashboard`). The actual top-nav set is more like **6-7** primary items:
e.g. Home · Intake · Dashboard · Upload · Benchmark · Contracts · Pin Replay
(+ Memory if kept). `/inspector` + `/runs/[runId]` are deep-linked from
`/dashboard`. Auth is handled by `/sign-in`.

## §D — Proposed global shell

Minimal Next-16 app-router root layout pattern:

- `web/app/layout.tsx` — wraps `{children}` with a single `<AppShell>` server
  component.
- `web/components/app_shell.tsx` (NEW, ~50 LOC) — `<header>` with brand-mark +
  top nav (the 6-7 primary items above) + a slot for `{children}`. Server
  component (no client-state); auth-gated visibility is per-page or via a
  separate client-island when needed (deferred to I-A-04 / I-cd-014's auth
  work).
- The nav uses Next's `<Link>` + `usePathname` (client component thin wrapper
  for active-route highlight). Active-style purely uses existing shadcn tokens
  (`--color-accent`, `--color-foreground`).

Why this minimal shape: I-cd-004's job is to put a roof on every prod page so
the I-A-NN rebuilds inherit consistent chrome. Bigger shell features
(breadcrumbs, command-K, persistent left nav, theme toggle, user menu) belong
in the per-route rebuilds where they're needed or in a deliberate
shell-evolution issue.

## §E — Proposed canonical token set (locked, documented)

`docs/web/design_tokens.md` (NEW) — names the canonical token set as the
**shadcn default theme** currently in `web/app/globals.css`'s `@theme inline`
block: `--color-{background,foreground,primary,secondary,muted,accent,
destructive,border,input,ring}` (+ -foreground variants where present);
`--color-card{,-foreground}`, `--color-popover{,-foreground}`;
`--color-sidebar{,-foreground,-primary,-primary-foreground,-accent,
-accent-foreground,-border,-ring}`; `--color-chart-{1..5}`; `--radius-{sm,md,
lg,xl,2xl,3xl,4xl}`; `--font-{sans,mono,heading}`. No new tokens invented —
the lock IS the documentation. I-A-NN rebuilds use ONLY these.

`globals.css` itself is unchanged in I-cd-004.

## §F — Files this PR changes

- `web/app/layout.tsx` — wrap children in `<AppShell>` (small).
- `web/components/app_shell.tsx` — NEW, ~50 LOC.
- `web/components/nav_link.tsx` — NEW, ~20 LOC (client component for active
  highlight via `usePathname`).
- `docs/web/route_map.md` — NEW, ~30 LOC (the §C table + the Seq-NNN
  cross-refs).
- `docs/web/design_tokens.md` — NEW, ~40 LOC (the §E lock).
- `state/polaris_restart/iteration_trajectory.md` — §8.3.5 log.

Estimated canonical diff ~150-180 LOC.

## §G — Open questions for Codex

1. **`/memory`** — KEEP or CUT? Recommendation: KEEP (campaign-memory is real
   substrate per `project_phase_d_status`). Counter-argument: it has no proven
   live-run consumer in the demo journey; could defer to a later issue.
2. **`/generation`, `/retrieval`, `/sse`** — CUT-from-prod OK? They're not in
   any rebuild row. Should any be kept as an operator-only diagnostic route
   (e.g. behind an auth role)?
3. **Shell shape** — top nav with brand-mark + 6-7 links: right minimal
   default, or do you want a different shape (e.g. sidebar)?
4. **Auth gating** — is it fine for I-cd-004's shell to render the nav
   unconditionally (rely on per-page auth), with the actual auth gate landing
   in I-A-04 / I-cd-014?

## §H — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
