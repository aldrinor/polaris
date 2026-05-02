M-15b — authz retrofit + endpoint sweep — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Phase C plan v2 GREEN-locked. M-15a (auth substrate) GREEN-locked
across 2 review rounds.

M-15b is the authz retrofit per FINAL_PLAN.md Phase C deliverable
#6 + Phase C plan v2 split: every M-8..M-13 endpoint that
returns workspace-scoped data must gate on workspace ownership.

The DOMINANT Phase C risk is cross-tenant leakage. Codex M-15b
mandate: "M-15b v1 review will enumerate every endpoint added in
M-1..M-13 and verify the gate. Easy to miss one — Codex must do
an exhaustive pass."

## What landed (commit 23e6c42)

### auth_middleware.py (NEW, ~340 lines)
- `Caller` dataclass: (user_id, org_id, role, via).
- `require_authenticated_caller`: resolves caller from
    1. `Authorization: Bearer <api_key>` via M-15a
       AuthStore.verify_api_key (which already caps effective
       role at current membership per M-15a v2).
    2. `X-Polaris-Caller: <org>:<user>:<role>` header — TEST
       PATH ONLY, gated by `PG_AUTH_TRUSTED_TEST_HEADER` env
       (must stay off in prod).
- Closure factories `_workspace_dep_with_role`, `_upload_dep_with_role`,
  `_job_dep_with_role` build FastAPI deps that:
    1. Resolve resource → owning org (via store lookups).
    2. Require caller's org_id == resource's org_id.
    3. Require caller's role >= required role.
- Pre-built: `require_workspace_viewer/member/admin`,
  `require_upload_viewer/member`, `require_job_viewer/member`.
- 403 on org mismatch (NOT 404) — does NOT leak existence.

### workspace_store.py
- `Workspace` dataclass + create_workspace + schema get `org_id`
  (default 'org_default'). New `list_workspaces_for_org`. ALTER
  TABLE migration runs in `_init_schema`.

### job_queue.py
- `Job` dataclass + enqueue + schema get `org_id` + `workspace_id`.
  New `list_by_org`. ALTER TABLE migration. job_to_dict surfaces
  both fields.

### inspector_router.py — endpoint retrofit

Every endpoint in M-8..M-13 that returns workspace-scoped data
gets the appropriate Depends:

  POST   /api/inspector/workspaces                    → require_authenticated_caller (creates ws in caller's org)
  GET    /api/inspector/workspaces                    → require_authenticated_caller (lists caller's org's workspaces)
  GET    /api/inspector/workspaces/{ws_id}            → require_workspace_viewer
  POST   /api/inspector/workspaces/{ws_id}/uploads    → require_workspace_member
  GET    /api/inspector/workspaces/{ws_id}/uploads    → require_workspace_viewer
  POST   /api/inspector/workspaces/{ws_id}/brief      → require_workspace_member
  GET    /api/inspector/uploads/{upload_id}           → require_upload_viewer
  DELETE /api/inspector/uploads/{upload_id}           → require_upload_member
  GET    /api/inspector/uploads/{upload_id}/chunks    → require_upload_viewer
  POST   /api/inspector/jobs                          → require_authenticated_caller (enqueue tags org)
  GET    /api/inspector/jobs                          → require_authenticated_caller (lists caller's org's jobs)
  GET    /api/inspector/jobs/{job_id}                 → require_job_viewer
  POST   /api/inspector/jobs/{job_id}/pause           → require_job_member
  POST   /api/inspector/jobs/{job_id}/cancel          → require_job_member
  POST   /api/inspector/jobs/{job_id}/resume          → require_job_member
  GET    /api/inspector/jobs/{job_id}/surfaces        → require_job_viewer
  GET    /api/inspector/jobs/{job_id}/stream          → require_job_viewer

**Public endpoints (NOT retrofitted, by design)**:
  GET   /api/inspector/templates/catalog       (scope page)
  POST  /api/inspector/templates/route         (advisory only)
  GET   /inspector                             (HTML redirect)
  GET   /inspector/{slug}                      (HTML shell)

**Run endpoints (M-1..M-7) — deferred to M-15c**:
  GET   /api/inspector/runs
  GET   /api/inspector/runs/{slug}
  GET   /api/inspector/runs/{slug}/report.md
  GET   /api/inspector/runs/{slug}/audit-bundle.zip
These read pre-Phase B disk artifacts that don't have org_id
tags. Tagging them requires the V30 runner to write a manifest
with job_id, then resolving job_id → org via the queue. Out of
M-15b scope per Phase C plan v2 (M-15b is M-8..M-13 only).

## Tests

### test_authz_endpoints.py (NEW, 36 tests)
- 17 parametrized `test_endpoint_requires_auth` (every endpoint
  → 401 without Authorization).
- 13 cross-org-access tests (every workspace/upload/job endpoint
  → 403 when beta caller targets alpha resource).
- 5 same-org sanity checks (alpha caller can read alpha
  resources).
- 2 list-leakage tests (alpha listing → only alpha data).
- 1 trust-flag-off test (X-Polaris-Caller ignored when
  PG_AUTH_TRUSTED_TEST_HEADER off → 401).

### Existing M-8..M-13 fixtures updated
- All TestClient instantiations now include
  `headers={"X-Polaris-Caller": "org_default:usr_test:owner"}`.
- conftest autouse fixture sets `PG_AUTH_TRUSTED_TEST_HEADER=1`
  so the test header is honored.

Phase B + C suite: 294 passing.

## Anti-scope (per Phase C plan v2 split, please don't push back)

- Run endpoints (M-1..M-7) → M-15c.
- SSO / OAuth / SAML → Phase D.
- Audit log of authz decisions → Phase D.
- Per-workspace ACL (sharing within an org) → Phase D.
- Multi-tenancy at storage layer (separate SQLite DBs per org) →
  not planned; the org_id column gating is sufficient for Phase C.

## Your job — EXHAUSTIVE PASS

**This is the dominant Phase C risk.** Per your Phase C plan v2
mandate, please walk every endpoint in `inspector_router.py` and
verify each one has the appropriate `Depends(require_*)`. Missing
even ONE workspace-scoped endpoint is a cross-tenant leakage bug.

## Specific things to validate

1. **Endpoint enumeration completeness.** Walk `inspector_router.
   py` line-by-line. For every `@router.(get|post|put|delete)`,
   confirm:
     - Does it return workspace/upload/job-scoped data?
     - If yes, is it gated with the appropriate `Depends`?
     - If gated, is the role correct (viewer for reads, member
       for mutations, admin for destructive)?
     - If NOT gated, is that intentional (public endpoint)?

2. **Closure factory correctness.** `_workspace_dep_with_role`
   etc. — does the closure correctly look up org via store,
   call `require_org_member_of`, return the Caller? Any
   error-leaking paths (404 vs 403)?

3. **Test caller header trust gate.** `PG_AUTH_TRUSTED_TEST_HEADER`
   default behavior: ANY truthy value enables. Default = unset →
   header ignored → 401. Verify a malicious request with
   X-Polaris-Caller in production (no env) is rejected.

4. **Auth-substrate integration.** `require_authenticated_caller`
   calls `AuthStore.verify_api_key` which (per M-15a v2) caps
   effective role at current membership. So a stale key
   automatically gets the demoted role at every request. Confirm
   this chain is wired correctly in the dep.

5. **Listing endpoints don't leak across orgs.** GET workspaces +
   GET jobs use `list_workspaces_for_org` / `list_by_org` scoped
   to the caller's org. Verify no Phase A-vintage code path that
   returns the unscoped list still exists.

6. **Tests are sufficient.** Are there endpoint patterns I missed
   in test_authz_endpoints.py? Specifically, the SSE stream
   endpoint serves bytes via StreamingResponse — does the 403
   path work the same as for JSON endpoints?

7. **Anything else.**

## Output

Write to `outputs/codex_findings/m15b_review/findings.md`:

```markdown
# Codex review of M-15b

## Verdict
GREEN / PARTIAL / DISAGREE

## Endpoint enumeration
List every endpoint in inspector_router.py. For each:
  PATTERN | METHOD | gated by | required role | OK/MISSING

## Cross-org leakage holes (the dominant risk)
none / list

## Other issues
File:line bugs / gaps.

## Recommended changes
If PARTIAL.

## Final word
GREEN to lock M-15b + proceed to M-16 / PARTIAL with edits /
DISAGREE.
```

Be thorough — exhaustive endpoint enumeration is the point of
this review. Under 300 lines.
