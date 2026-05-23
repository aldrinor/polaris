# Brief — I-p2-039 (#825): top-tier nav — auth-aware public/app split + kill "Intake" jargon + tablet budget

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the doc is force-APPROVE'd on remaining non-P0/P1 findings.
- If you're holding back a P1 for the next round — DON'T. Surface it now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Context
Your UI-direction decision (`.codex/I-p2-038/ui_direction_decision_verdict.txt`) ranked
this P2: "replace flat dev-tool nav with lean auth-aware public/app navigation and rename
Intake to plain user language." This brief implements it. (P1 = demo-journey-middle live
audit, blocked on operator demo cred — separate.)

## HARD CONSTRAINTS (operator-locked — do NOT reopen)
- Honest sovereignty wording preserved: "Canadian-hosted" mark + OpenRouter/`/transparency`
  disclosure stay; no "Sovereign"/"no US vendor" overclaim.
- Next.js 16 App Router; server vs client component boundaries; the nav is a client
  component (`primary_nav.tsx`).
- Top-tier bar = institutional/Perplexity-grade; "complete" = visually-verified live.

## Current state (grounded)
- `lib/nav.ts`: `PRIMARY_NAV` = 9 flat items (Home, Intake, Dashboard, Upload, Benchmark,
  Compare, Contracts, Pin Replay, Memory); each optionally role-filtered via `navForRole`,
  but ALL items have no `roles` → visible to everyone. `roles.ts` `DEFAULT_ROLE="analyst"`.
- `primary_nav.tsx` (client): renders `navForRole(PRIMARY_NAV, DEFAULT_ROLE)` inline at
  `md:`, hamburger below md. Consumed by both `app_shell.tsx` (every non-chromeless route)
  and `home_keyboard_shell.tsx` (home).
- `lib/auth.ts`: `isAuthenticated()` returns whether a non-expired token exists in
  sessionStorage (presence/expiry check, NOT signature). `AuthButton` (just shipped) reads
  it via `useSyncExternalStore` (SSR-safe).

## Proposed design
1. `lib/nav.ts`: add `visibility: "public" | "app"` to `NavItem`. Mark **public**: Home,
   Ask (renamed from Intake, href stays `/intake`). Mark **app**: Dashboard, Upload,
   Benchmark, Compare, Contracts, Pin Replay, Memory. Add pure `navForAuth(items, authed)`
   (public always; app only when authed). Keep `navForRole` (orthogonal, unused-by-default).
2. `primary_nav.tsx`: read auth via `useSyncExternalStore` (same pattern as AuthButton,
   hydration-safe → SSR/first-paint = unauthenticated = public-only). Filter via
   `navForAuth`. **Breakpoint (your iter-1 P1):** `lg` (1024) is NOT enough — the authed
   9-link set + brand + Canadian-hosted mark + AuthButton ≈ 1150px. Use **`xl:` (1280)** for
   the inline nav (hamburger below xl), which fits the full authed header; verify no overflow
   at 1024 (hamburger) / 1280 / 1440. Verification is LOCAL-authed (inject a sessionStorage
   token in the browser) at those widths, since live-authed needs the P1 demo cred I don't
   hold; the UNAUTH public nav is verified live.
3. No change to `app_shell.tsx` / `home_keyboard_shell.tsx` (they consume PrimaryNav).
   Home's own static Sign in (vs AppShell's AuthButton) is left as-is this issue —
   explicit follow-up (your iter-1 P2-3), not in scope here.

## The e2e-spec decision I need you to rule on
10 specs assert the nav contract (48 assertion lines): `{home,intake,dashboard,upload,
benchmark,contracts,pin_replay,memory,runs_runid}_g1_g8.spec.ts` + `demo_journey.spec.ts`.
Each "G1 nav parity" test does `page.goto("/<route>")` UNAUTHENTICATED and asserts ~8 app
labels visible in `nav[aria-label='Primary']`. The e2e env does NOT set
`POLARIS_AUTH_ENABLED`, so pages render and `isAuthenticated()` is false → after this change
those specs would see the PUBLIC nav (Home, Ask) only and FAIL.

Two ways to update them — **my recommendation: Option B**:
- **Option A:** rewrite each nav-parity test to assert the PUBLIC contract unauth (Home +
  Ask visible; app labels absent). Simple, but stops testing the authed reviewer nav.
- **Option B (recommended):** in each spec's nav test, inject a dummy non-expired token into
  sessionStorage in `beforeEach` (isAuthenticated only checks presence/expiry) so the test
  exercises the AUTHED app nav (the real reviewer experience) + assert the renamed "Ask"
  label; PLUS add one unauth assertion (public nav = Home/Ask only, tools hidden). Tests
  both states faithfully without real signing.

Please rule: A or B (or a third path)? And confirm the public/app item split.

## Files I have ALSO checked and they're clean
- `app_shell.tsx`, `home_keyboard_shell.tsx` (consume PrimaryNav only — no change needed),
  `nav_link.tsx` (pure styling), `auth_button.tsx` (the useSyncExternalStore pattern to reuse),
  `app_shell_gate.tsx` (chromeless = `/`,`/sign-in` — unaffected). `lib/auth.ts`
  (`isAuthenticated`, token-key in sessionStorage). No spec asserts footer-absence.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
spec_approach: A | B | other
public_app_split_ok: true | false  # + correction if false
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
