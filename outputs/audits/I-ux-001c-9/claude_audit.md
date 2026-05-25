# I-ux-001c sub-PR 9 — claude_audit

## Scope
Visual-only marketing-auth chrome of `/sign-in` (institutional sign-in surface). Brief APPROVED iter-3 (after iter-1+iter-2 fixes for CI auth-env). Diff APPROVED iter-1 (accept_remaining, 0 P0/P1, 7/7 PASS).

## Surface (header chrome only)
- Brand-red eyebrow "SIGN IN · POLARIS CLINICAL RESEARCH"
- Display H1 "Sign in to verify every claim."
- Tightened subtitle (institutional access + honest proof claim)
- MapleLeafSignatureLazy + login form + ?next= same-origin validation + TRUST_POINTS list + error/loading states preserved verbatim

## CI wiring (NEW)
- web_ci.yml `start_fastapi_backend` block adds POLARIS_JWT_SECRET + POLARIS_STATIC_ACCOUNTS_PATH env (per Codex brief iter-1 P1)
- NEW run_e2e_sign_in step after runs_runid_g1_g8

## Iter trail
- Brief iter-1: REQUEST_CHANGES (CI wiring incomplete — needed auth env)
- Brief iter-2: REQUEST_CHANGES (Edit didn't land — no prior Read)
- Brief iter-3: APPROVE (auth env spec landed)
- Diff iter-1: APPROVE clean

## Verdict
Ready for operator merge queue.
