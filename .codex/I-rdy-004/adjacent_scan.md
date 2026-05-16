# I-rdy-004 (#500) — auth/SSE operability — §-1.2 adjacent-file scan

Scan done 2026-05-15. Grounded picture of the auth surface before building.

## What exists

- **Backend auth (works):** `src/polaris_v6/api/auth.py` — `POST /auth/login`
  → 12h HS256 JWT. `require_auth` global dependency; `PUBLIC_PATH_PREFIXES`
  (auth.py:35) allowlists `/health`, `/transparency*`, `/auth/login`, `/docs`.
  Everything else (incl. `/stream`) is auth-gated.
- **Frontend API client:** `web/lib/api.ts` — `BACKEND_URL = "/api/v6"`
  (same-origin; Next rewrites `/api/v6/*` → `INTERNAL_API_URL`). **26 `fetch()`
  calls, 0 `Authorization` headers.**
- **SSE client:** `web/lib/sse_client.ts` — `new EventSource(this.url)`,
  native EventSource (cannot set request headers).
- **Sign-in page:** `web/app/sign-in/page.tsx` — disabled placeholder, no form.
- **No auth context / no login function / no token storage** anywhere in `web/`.

## I-rdy-004 build scope (the fix)

1. **Real sign-in page** — working form POSTing to `/api/v6/auth/login`,
   stores the returned JWT.
2. **Token store + auth context** — a small client-side auth context;
   token in memory + a persistence choice (httpOnly cookie preferred since
   the browser already talks same-origin through the Next proxy).
3. **Token injection** — every `fetch()` in `web/lib/api.ts` (26 calls)
   sends `Authorization: Bearer <jwt>`; central helper, not 26 edits.
4. **SSE auth** — native `EventSource` can't set headers. Fix: accept the
   JWT via query param on `/stream/{id}?access_token=<jwt>` and have the
   backend's `require_auth` (or a stream-specific dependency) read it; OR a
   same-origin cookie the EventSource sends automatically. Pick one in the
   Codex brief.
5. **401 handling** — on 401, redirect to `/sign-in`; on token expiry,
   re-auth.

## Next loop iteration

Write `.codex/I-rdy-004/brief.md` (Codex brief, §8.3.1 cap directive
verbatim + this scan), run Codex iter 1, then build.
