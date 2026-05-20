HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# ⚠ HARD CONSTRAINTS — NOT CODEX-NEGOTIABLE ⚠

- **Backend auth substrate exists** (I-carney-004, `src/polaris_v6/api/auth.py`).
- **Frontend auth substrate exists** (I-rdy-004, `web/lib/auth.ts`).
- **NEVER commit real bcrypt hashes**; operator provisions at deployment.
- **`config/static_accounts.yaml` MUST NOT exist in repo OR Docker build context** per Codex iter-2 P1.
- **`<AuthRedirect>` is UX-only**, not an authorization boundary. Authz is FastAPI bearer-auth at API layer.

# Codex brief review — I-cd-014 / GH#610

Closes #610. Acceptance: "carney_office/ops log in; gated routes reachable; /sign-in passes G1-G8 + screenshot."

## §0 — Iter-2 fold-in (1 continuing P1 + 3 P2)

**iter-2 P1 (Docker context + deploy docs)**: `.gitignore` alone doesn't close the static_accounts leak. Resolution:
- (a) Add `config/static_accounts.yaml` to `.dockerignore` (`Dockerfile.v6` does `COPY config/ config/`; without this exclusion, any local copy in dev gets baked into images).
- (b) Update `docs/carney_demo_runbook.md`:36 (table entry) + :58 (scp command): point operator at `/etc/polaris/static_accounts.yaml` instead of `config/static_accounts.yaml`. The "T-3 setup" section (line 174+) already uses `/etc/polaris/` — make the EARLIER references consistent.
- (c) Update `infra/vexxhost/README.md`:22 (prereq) + :31 (scp command): same pattern.

**iter-2 P2 #1 (URL validation)**: `?next=` accepting `/\evil.com` could route via backslash-as-segment-separator. Resolution: use `new URL(next, window.location.origin)` + assert `parsed.origin === window.location.origin`; fall back to `/` on any error or mismatch.

**iter-2 P2 #2 (page.tsx comment wording)**: my iter-2 wording was contradictory. Resolution: comment says "this route's fixture-only data path is intentionally unwrapped because the v1_canonical_* fixtures are public test data; future real-bundle integration at I-B-08 MUST fetch from FastAPI with `Authorization: Bearer <jwt>` headers — that is where real authorization lives, not in client-side `<AuthRedirect>` UX redirects."

**iter-2 P2 #3 (Playwright invocation)**: `next start` fails without a prior `npm run build`. Resolution: e2e spec header documents EITHER `npm run build && next start` OR `next dev` for local iteration.

## §A — Final scope: 9 file edits + 2 NEW + 1 NEW fixture

| # | File | Action |
|---|---|---|
| 1 | `.gitignore` | Add `config/static_accounts.yaml`. |
| 2 | `.dockerignore` | Add `config/static_accounts.yaml` **(iter-2 P1)**. |
| 3 | `config/static_accounts.example.yaml` | Verify/add `carney_office` + `ops` placeholder accounts + header warning operator-only. |
| 4 | `docs/carney_demo_runbook.md` | :36 table entry + :58 scp command → point at `/etc/polaris/static_accounts.yaml`. Add note that operator generates the file OUTSIDE the repo via `/tmp/polaris_secrets/` or equivalent. |
| 5 | `infra/vexxhost/README.md` | :22 prereq + :31 scp command → same pattern. |
| 6 | `web/components/auth_redirect.tsx` (NEW) | UX-only redirect; module docstring documents security framing. Client component. `useEffect` checks `isAuthenticated()`; redirects to `/sign-in?next=<current-path>` if false; renders `null` while resolving. |
| 7 | `web/app/inspector/[runId]/page.tsx` | Add comment (iter-2 P2 #2 wording) explaining fixture-only intentionally unwrapped + future real-data MUST use FastAPI bearer-auth. NO `<AuthRedirect>` wrap in this PR. |
| 8 | `web/app/sign-in/page.tsx` | (a) `?next=` validation via `new URL` + same-origin (iter-2 P2 #1); (b) data-testid attributes for e2e grip; (c) verify G1-G8 via e2e. |
| 9 | `web/tests/e2e/sign_in.spec.ts` (NEW) | Header docs env orchestration (POLARIS_JWT_SECRET + POLARIS_STATIC_ACCOUNTS_PATH) + `npm run build && next start` OR `next dev` (iter-2 P2 #3). Covers: render, invalid creds error, valid creds redirect, `?next=` same-origin honor, `?next=` cross-origin fallback, axe-clean (G6), responsive (G5), console-error-free (G8), visual baseline as `test.fixme()`. |
| 10 | `tests/fixtures/auth/test_static_accounts.yaml` (NEW) | Test-only `carney_office` + `ops` with KNOWN-test-only bcrypt hashes. Header documents test-only constants. |

## §B — What this PR does NOT do

- Real production bcrypt hashes (operator-provisioned).
- Real `config/static_accounts.yaml` (gitignored + dockerignored; operator provisions outside repo).
- `/inspector/[runId]` `<AuthRedirect>` wrap (deferred — fixture-only data path needs no UX redirect; real-data wiring at I-B-08 is the integration point).
- Other-route `<AuthRedirect>` wrappers (subsequent A-route rebuilds, I-cd-022..030).
- Cookie-based session migration (stays sessionStorage per I-rdy-004).
- SSO integration.

## §C — Smoke + acceptance

- `cd web && npm run lint && npm run typecheck && npm run format:check`: clean.
- `pytest tests/polaris_v6/api/` regression: no auth endpoint regression.
- `cd web && (npm run build && npx next start -p 3738) &; npx playwright test --project=chromium tests/e2e/sign_in.spec.ts` (per the spec header invocation; requires POLARIS_JWT_SECRET + POLARIS_STATIC_ACCOUNTS_PATH env).
- Visual baseline test.fixme() deferred.

## §D — Risk surface

- **Docker context + deploy docs leak CLOSED** per iter-2 P1.
- **AuthRedirect UX-only framing** explicit in module docstring + comment in page.tsx.
- **URL validation hardened** via `new URL()` parser + same-origin check.
- **Test fixture credentials**: committed test-only bcrypt hashes; documented as test-only.

## §E — Residual questions for Codex iter-3

1. iter-2 P1 close (3-file deploy-doc + .dockerignore update + .gitignore) — sufficient to lock the static_accounts substrate?
2. iter-2 P2 #1 (`new URL` + same-origin) — exhaustive vs other URL injection patterns?
3. iter-2 P2 #2 (page.tsx comment wording) — security framing clear?
4. iter-2 P2 #3 (Playwright invocation docs) — sufficient for the e2e author?

## §F — Output schema — return EXACTLY this

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
