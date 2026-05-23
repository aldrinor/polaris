# Brief — I-p2-038 (#821) app-shell slice: shared SiteFooter + auth-aware AuthButton

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the doc is force-APPROVE'd on remaining non-P0/P1 findings.
- If you're holding back a P1 for the next round — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Context
Umbrella issue #821 = top-tier visual overhaul across ALL P2 pages. This slice fixes
two every-page defects found by screenshotting the live site. (This brief replaces
stale content the shared `.codex/I-p2-038/` dir carried from an earlier sub-task.)

## Problem (acceptance-criteria correctness review)
1. Only the home route (`/`) renders a `<footer>`. Every AppShell route (intake,
   upload, contracts, pin_replay, dashboard, benchmark, memory, compare, …) ends in
   an empty void below the fold — the operator's explicit "empty space" complaint.
2. The auth affordance is inconsistent: home has a static "Sign in" button; every
   AppShell route has NONE (no way to sign in once off home); there is NO "Sign out"
   anywhere in the product.

## Acceptance criteria
- AC1: a single shared footer renders on home AND every AppShell (non-chromeless)
  route. One source of truth (no per-shell duplication).
- AC2: footer microcopy is HONEST (§-1.1 / LAW II): no sovereignty overclaim;
  states OpenRouter (US) inference + links /transparency; matches the existing
  header "Canadian-hosted" framing. All footer links are PUBLIC routes (no
  auth-gated dead-ends).
- AC3: AppShell header shows an auth affordance: "Sign in" unauthenticated,
  "Sign out" authenticated. Hydration-safe (no SSR/client mismatch).
- AC4: NO nav-item-visibility change → the G1 nav-parity e2e contract
  (`nav[aria-label='Primary']` shows all labels) stays intact.
- AC5: home does not get a double Sign-in (home is chromeless → AppShell's button
  must not render there; home keeps its own button).
- AC6: prod `next build` green; prettier `--check` clean; CI `lint` lane clean.

## Approach
- `web/components/site_footer.tsx` (new): the shared footer.
- `web/components/auth_button.tsx` (new): `useSyncExternalStore`-based Sign in/out
  (SSR-safe, effect-free — avoids react-hooks/set-state-in-effect).
- `web/components/app_shell.tsx`: mount both.
- `web/app/page.tsx`: replace the thin inline home footer with the shared one.

## Out of scope (deferred to a follow-up nav-IA issue)
- Auth-aware nav-item visibility / de-clutter / "Intake"→"Ask" rename (rewrites the
  G1 nav-parity e2e contract + needs e2e auth; #720 e2e lane is broken).
- Header horizontal-budget at tablet/small-desktop (raise inline nav breakpoint).
- Making home's own Sign-in button auth-aware.

## Files I have ALSO checked and they're clean
- `web/app/layout.tsx` (body flex-col + main flex-1 → sticky footer), `app_shell_gate.tsx`
  (CHROMELESS = `/` + `/sign-in` → no double Sign-in on home), `lib/auth.ts`
  (`isAuthenticated`/`clearToken` exported), `home_keyboard_shell.tsx` (own button left
  untouched), e2e g1_g8 + demo_journey specs (assert nav labels + header/main counts —
  unaffected; no spec asserts footer-absence), `/transparency` (200 live).

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
