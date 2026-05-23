# Claude architect audit — I-p2-039 (#825): auth-aware public/app nav

## Scope (per Codex UI-direction decision, P2)
Replace the flat 9-item public nav (read like an internal tool suite) with a lean
auth-aware public/app split; rename "Intake"→"Ask"; fix the tablet/small-desktop budget.

## Shipped (web/ only)
- `lib/nav.ts`: `visibility: public|app` + `navForAuth`; public = Home + Ask; app = the 7 tools.
- `components/primary_nav.tsx`: hydration-safe auth read (useSyncExternalStore) + navForAuth
  filter + inline breakpoint md→xl (Codex P1: lg/1024 overflows).
- `tests/e2e/_nav_auth.ts` + 9 g1_g8 specs (authed nav, Option B token seed) + home (public
  nav) + demo_journey (authed nav across routes).

## Verification (LAW II)
- next build compiled; eslint + prettier clean on touched files.
- Playwright link assertions: unauth@1440 = [Home, Ask]; authed@1024 = hamburger (no
  overflow); authed@1280 & @1440 = full 9-item nav fits (screenshot confirms brand+nav+mark+
  Sign-out fit at 1280 with room). Honest sovereignty wording preserved.

## Codex
Brief APPROVE (iter 2); diff APPROVE (iter 1), zero P0/P1. One non-blocking P2 (helpers
assert required+absent labels, not exact total link set) — "current diff is correct".

## Residual / follow-up
- P1 (separate): demo-journey-middle LIVE audit — blocked on operator demo cred.
- Home's own static Sign in not yet auth-aware (Codex brief P2-3) — follow-up.
- Live-authed nav verification pending the demo cred (local-authed verified here).
