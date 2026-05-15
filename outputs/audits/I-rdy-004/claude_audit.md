# I-rdy-004 (#500) — Claude architect self-review

Scope: auth/SSE operability for the deployed UI (verified broken in I-rdy-002).

Acceptance met:
- Real sign-in page replacing the disabled placeholder — web/app/sign-in/page.tsx (client component, POSTs /api/v6/auth/login, inline 401 error).
- Token store — web/lib/auth.ts (sessionStorage, 12h expiry, clear-on-401).
- Bearer injection on all 26 v6 fetch calls — authFetch wrapper, web/lib/api.ts; preserves caller headers, FormData-safe.
- SSE auth — ?access_token= on /stream/* only; require_auth reads it; uvicorn --no-access-log prevents token log leak.
- 401 handling — authFetch → /sign-in; login-401 stays inline (no redirect loop).

Tests: tests/v6/test_sse_query_auth.py — 5 tests, all pass (PYTHONPATH=src pytest).
Codex: brief APPROVE iter 1; diff APPROVE iter 2 (iter-1 1 P1 + 2 P2 all fixed).
Out of scope (noted): audit_live/_panels.tsx uses /api/audit/stream (a different, query-param-driven endpoint) — not the v6 run SSE.
