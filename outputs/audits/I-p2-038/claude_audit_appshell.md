# Claude architect audit — I-p2-038 (#821) global app-shell pass (footer + auth button)

## Scope
Two every-page top-tier defects found by screenshotting the LIVE site:
1. Only `/` had a `<footer>`; every AppShell route ended in an empty void.
2. Auth affordance was inconsistent: home had a static "Sign in"; AppShell routes
   had none; nothing had "Sign out".

## What shipped
- `web/components/site_footer.tsx` (new) — single shared footer (home + AppShell).
- `web/components/auth_button.tsx` (new) — hydration-safe Sign in / Sign out.
- `web/components/app_shell.tsx` — mount both.
- `web/app/page.tsx` — replace thin inline footer with the shared one.

## Verification (LAW II — evidence)
- `next build` (prod) GREEN; prettier (local 3.8.3 == CI) `--check` clean on all 4.
- Local `next start` screenshots: `/` (single Sign in, shared footer),
  `/upload` (AppShell Sign in button + footer fills former void), `/pin_replay`.
- Honesty (§-1.1 / LAW II): footer microcopy makes NO sovereignty overclaim —
  states OpenRouter (US) inference + links /transparency, mirroring the existing
  header "Canadian-hosted" honest framing. Every footer link is a PUBLIC route
  (`/intake`, `/inspector/v1-canonical-success`, `/transparency` — all 200), so
  no auth-gated dead-ends.
- No PRIMARY_NAV / nav-item-visibility change → G1 nav-parity e2e contract intact.

## Codex
APPROVE iter 1 (zero P0, zero P1). One P2: header horizontal-budget risk at
tablet/small-desktop (9-item inline nav + mark + button). `accept_remaining`.

## Residual / follow-up (captured, not blocking)
- P2 header crowding → folds into the planned **nav-IA redesign** issue
  (auth-aware lean public nav, group/de-clutter power tools, raise the inline
  breakpoint to lg, kill "Intake" jargon — deliberately deferred because it
  rewrites the G1 nav-parity e2e contract and needs e2e auth, which is its own
  scope; #720 e2e lane is currently broken).
- Home's own Sign in button is not yet auth-aware (no Sign out on home);
  reconcile into the same nav-IA issue.
