# Codex DESIGN+DIFF review — I-p2-021 (#760): institutional split-screen sign-in

HARD ITERATION CAP: 5. iter 1. Canonical-diff-sha256 `e4f1ff5599d186eccf19bdbce85cba540d4566184f17dbadd29661c46d008419`. web/ only. MERGE AUTHORIZED if mergeable. APPROVE iff zero P0/P1.

## Direction (#760 "institutional, minimal" + operator "top-tier")
Was a plain centered card WITH the app nav bleeding onto the auth page.

## Diff
- app/sign-in/page.tsx: restructured to a split-screen — LEFT aside (hidden below lg) = "POLARIS · Canada" wordmark + maple leaf + "Deep research you can check, line by line." + 3 trust points (BadgeCheck/ShieldCheck/Network) + footer trust line; RIGHT = the form (a brand lockup shows above the form on <lg where the panel is hidden). ALL auth logic preserved verbatim: safeNextPath, handleSubmit, useSearchParams Suspense, the username/password fields + autoComplete + required, error role=alert, testids (sign-in-form/-submit/-error/-loading), "Continue" disabled gating, "Back to home".
- components/app_shell_gate.tsx: CHROMELESS_ROUTES = {"/", "/sign-in"} — sign-in now renders bare (no AppShell nav). Rationale: the primary nav is auth-gated; showing it pre-login is wrong + it broke the full-height split.

## Claude visual audit (standalone @1366 + @390, sent to operator): full-height split desktop (brand/trust left, form right), chromeless (verified no nav[aria-label=Primary] in DOM); clean form-only on mobile with brand lockup on top. "Continue" faded = correct disabled state (empty fields; disabled controls WCAG-exempt).

## Files ALSO checked clean: layout.tsx (AppShellGate is the only shell wrapper); home (also chromeless via the same set — still renders, unaffected); no other route depends on /sign-in having the nav.

## Review focus
1. Does CHROMELESS_ROUTES change affect any OTHER route or the home (still bare on /)? Any landmark (G1 double-header / G6 main) regression on sign-in (it has no <main> — acceptable for a standalone auth screen)?
2. a11y: form labels/autocomplete/error role intact; left panel decorative (icons aria-hidden); focus order sane; AA?
3. Responsive: lg: split → mobile form-only clean? Auth flow unchanged? Any P0/P1.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
merge_decision: MERGE AUTHORIZED | DO NOT MERGE
```
