# Codex BRIEF review — I-p2-029 (#768): global app shell + role model + unified nav

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; cosmetics → P2/P3.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; do not bank for iter 6.
- Surface held-back findings now.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Task (foundation — before pages, per the v3 sequence)
Establish the global app shell + a role model + a SINGLE source-of-truth nav.

## Verified current state (grounded)
- TWO shells each with a DUPLICATED `PRIMARY_NAV` const: `web/components/app_shell.tsx:22` + `web/app/components/home_keyboard_shell.tsx:26` — drift risk.
- NO role model exists in the frontend (grep for role/analyst/counsel found only bundle-loader false matches).
- Sovereign mark already added to both shells (I-ui-010).

## Acceptance criteria (the diff implements; this brief reviews the PLAN)
1. **Single nav source:** extract `PRIMARY_NAV` into one shared module (`web/lib/nav.ts`), consumed by BOTH shells — no duplication. Same routes/labels render in both.
2. **Role model:** `web/lib/roles.ts` — the 5 roles as a typed const + display labels: PMO analyst, policy advisor, legal counsel, clinical/regulatory reviewer, records/security officer. A `currentRole` mechanism (context/cookie, default = analyst) + a `navForRole(role)` filter so nav can be role-aware. (FULL per-route RBAC ENFORCEMENT is explicitly OUT OF SCOPE here → tracked under the security gate G-SEC / a follow-up; this issue ships the role MODEL + role-aware nav only.)
3. Shell stays Frontier Minimal (white + Canada-red tokens from #742); 1 header / Primary nav / 1 main preserved (home_g1_g8); a11y (keyboard, focus order).

## Files I have ALSO checked and they're clean
- web/app/globals.css (the #742 red-on-white tokens — shell consumes them).
- home_g1_g8 e2e (asserts 1 header / Primary nav / 1 main / focus-visible — the nav unify must preserve this).

## Review focus
1. Is "role MODEL + role-aware nav now, full RBAC enforcement later" the right scope split, or is shipping a role model without enforcement a security-theatre risk to flag?
2. Single-nav-source approach sound (both shells consume it; no SSR/client hydration pitfall)?
3. Anything that breaks home_g1_g8 or the Frontier-Minimal shell.

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
```
