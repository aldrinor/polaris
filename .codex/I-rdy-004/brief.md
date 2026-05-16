# Codex brief — I-rdy-004 (#500): auth/SSE operability for the deployed UI

**Type:** BRIEF review (acceptance-criteria correctness). Phase 3.1 of the
Carney demo execution plan.

## §0. Iteration cap directive (CLAUDE.md §8.3.1, verbatim)

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## §1. The problem (verified, I-rdy-002 #498)

The deployed orchestrator runs with `POLARIS_AUTH_ENABLED=1`. But the UI
cannot operate under auth:
- `web/app/sign-in/page.tsx` is a disabled placeholder — no form, all inputs `disabled`, copy says "placeholder for Phase 0".
- `web/lib/api.ts` — 26 `fetch()` calls, **0 `Authorization` headers**.
- `web/lib/sse_client.ts` — `new EventSource(url)`; native EventSource cannot set request headers, and `/stream/{id}` is auth-gated.
- No auth context / login function / token store anywhere in `web/`.

Backend auth WORKS: `src/polaris_v6/api/auth.py` — `POST /auth/login` → 12h
HS256 JWT; `require_auth` global dependency; `PUBLIC_PATH_PREFIXES` allowlists
`/health`, `/transparency*`, `/auth/login`, `/docs`.

## §2. Proposed build + acceptance criteria

**A. Real sign-in page** — replace the placeholder with a working form
(email/username + password) that POSTs to `/api/v6/auth/login`, on 200 stores
the JWT + redirects to `/`, on 401 shows an inline error.

**B. Token store + auth context** — a small client-side auth context holding
the JWT; persisted so a refresh doesn't lose the session.

**C. Token injection** — a single central fetch helper in `web/lib/api.ts`
attaches `Authorization: Bearer <jwt>` to all 26 calls (one helper, not 26
edits). On 401 → clear token, redirect to `/sign-in`.

**D. SSE auth** — native `EventSource` cannot send headers. Proposed: pass the
JWT as a query param `/api/v6/stream/{id}?access_token=<jwt>`; add a
stream-route auth dependency (or extend `require_auth`) that reads the token
from the query param for the `/stream` path only. (Alternative: same-origin
cookie. Brief proposes query-param as the surgical option — Codex: confirm or
push to cookie.)

**E. Acceptance:** with `POLARIS_AUTH_ENABLED=1`, the UI logs in, every API
call carries the bearer token, protected SSE connects and streams, a 401
cleanly routes to `/sign-in`. Codex APPROVE on brief + diff.

## §3. Files scanned (adjacent-file check — clean / context only)

`web/lib/api.ts`, `web/lib/sse_client.ts`, `web/app/sign-in/page.tsx`,
`web/app/layout.tsx`, `src/polaris_v6/api/auth.py`, `src/polaris_v6/api/stream.py`,
`src/polaris_v6/api/app.py` (global `Depends(require_auth)` + CORS).
Full scan: `.codex/I-rdy-004/adjacent_scan.md`.

## §4. Questions for Codex

1. Is the query-param SSE-token approach (§2.D) sound, or is a same-origin cookie cleaner/safer given the Next `/api/v6/*` proxy?
2. Token persistence: `localStorage` (XSS-readable) vs httpOnly cookie (needs backend cookie support) — which for a single-venue demo?
3. Is the acceptance set complete, or is a gap (CORS, token-refresh, multi-tab) missing?
4. Any P0/P1 execution risk in this plan.

## §5. Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: []
p1: [...]
p2: [...]
sse_auth_recommendation: <query-param | cookie + reasoning>
token_persistence_recommendation: <text>
acceptance_gaps: [...]
convergence_call: continue | accept_remaining
verdict_reasoning: <text>
```
