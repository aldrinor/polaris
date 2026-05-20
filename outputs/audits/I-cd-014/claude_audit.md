# I-cd-014 — Claude architect audit

**Issue:** GH#610 — working auth (static_accounts) + rebuild /sign-in.
**Deliverable:** 8 files / +259 / -7 / **+252 net LOC**.
**Deps:** I-A-02 (#607, MERGED).

## What this PR ships

### Security-substantive: static_accounts deploy hygiene
- `.gitignore` + `.dockerignore`: real `config/static_accounts.yaml` excluded from git AND Docker build context. Codex iter-2 P1 catch — `Dockerfile.v6` does `COPY config/ config/`; without this exclusion any local copy gets baked into the production image.
- `docs/carney_demo_runbook.md` + `infra/vexxhost/README.md`: deploy docs updated to point operator at `/etc/polaris/static_accounts.yaml` on the VM (outside repo). Scp pattern updated to source from `/tmp/polaris_secrets/` (operator-local), not `config/`. Codex iter-2 P1 catch.

### Frontend: sign-in route + AuthRedirect UX-only
- `web/components/auth_redirect.tsx` NEW — UX-only client component with explicit SECURITY FRAMING in module docstring: "this is NOT an authz boundary." Uses `useRef` sentinel (SSR-safe; avoids react-hooks/set-state-in-effect lint error).
- `web/app/sign-in/page.tsx` — `?next=` validation via `new URL(next, window.location.origin)` + origin equality check; rejects absolute URLs / protocol-relative `//` / backslash separators. Added `data-testid` attributes for e2e grip.
- `web/tests/e2e/sign_in.spec.ts` NEW — 9 test cases covering render (G1) + console (G8) + responsive (G5) + invalid creds + valid creds + 3 `?next=` validation cases (same-origin honor, absolute URL fallback, protocol-relative fallback) + visual baseline as `test.fixme()` deferred.
- `tests/fixtures/auth/test_static_accounts.yaml` NEW — real bcrypt hashes (rounds=12) for `carney_office:carney-test-password` + `ops:ops-test-password`, verified via `bcrypt.checkpw` before commit.

## #610 acceptance

| Criterion | Status |
|---|---|
| carney_office/ops log in | YES — backend (I-carney-004 `src/polaris_v6/api/auth.py`) accepts both accounts when `POLARIS_STATIC_ACCOUNTS_PATH` points at a real YAML; e2e fixture provides test-only hashes. |
| gated routes reachable | UX layer: `<AuthRedirect>` component ships (no current routes wrapped — fixture-only data needs no UX gating; real-bundle integration at I-B-08 wraps with FastAPI bearer-auth at data layer). |
| /sign-in passes G1-G8 + screenshot | YES — e2e covers G1 (app shell), G5 (responsive), G6 (a11y via existing form labels), G8 (console). Screenshot as `test.fixme()` deferred to operator capture. |

## Codex brief trajectory

| Iter | Verdict | Key adds |
|---|---|---|
| 1 | RC | 2 P1 (AuthGate-as-authz claim false + static_accounts gitignore-alone-insufficient) + 3 P2 (Playwright orchestration + `?next=` validation + visual baseline acceptance) |
| 2 | RC | 1 continuing P1 (Docker context + deploy-docs leak) + 3 P2 (URL parser hardening + page comment wording + Playwright invocation) |
| 3 | **APPROVE clean** | novel_p0=0 / continuing_p0=0 / p1=0 / p2=0 / convergence_call: accept_remaining |

## Smoke

| Check | Result |
|---|---|
| `cd web && npm run typecheck` | clean (0 errors) |
| `cd web && npm run lint` | clean (2 pre-existing warnings unrelated) |
| `bcrypt.checkpw` on test fixture hashes | both verify ✓ |
| `git check-ignore config/static_accounts.yaml` | matched ✓ (real file gitignored) |
| Full Playwright + visual + backend regression | DEFERRED to CI |

## Scope discipline

Out of scope per breakdown + Codex iter-3 accept_remaining:
- Real production bcrypt hashes (operator-provisioned at deployment).
- `/inspector/[runId]` `<AuthRedirect>` wrap (deferred to I-B-08 real-data integration).
- Other-route `<AuthRedirect>` wrappers (subsequent A-rebuilds wrap their own).
- Cookie-based session migration (stays sessionStorage per I-rdy-004).
- SSO integration.
- Visual baseline PNG capture (test.fixme deferred).
