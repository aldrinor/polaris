# I-ux-001c sub-PR 9 — /sign-in v6 chrome (GH #898)

## Phase: BRIEF REVIEW

Repo equals polaris HEAD. Per CLAUDE.md §3.0.

## §0 cap directive (CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Scope (visual-only marketing-auth chrome, sub-PR 4-8 pattern)

Rebuild `/sign-in` page chrome to v6 marketing-auth lock. Current 239 LOC `web/app/sign-in/page.tsx` (per I-cd-014 #610) is the institutional sign-in page (login form + ?next= same-origin redirect validation + trust-points list). ALL backend logic preserved verbatim.

v6 changes (header region only, lines ~119-126):
- Brand-red eyebrow "SIGN IN · POLARIS CLINICAL RESEARCH" ABOVE the MapleLeafSignatureLazy + H1
- Display H1 — bump from `text-3xl font-semibold` → `text-4xl font-bold` + leading tighten
- Locked H1 copy: "Sign in to verify every claim."
- Tightened subtitle (NEW): "Institutional access for POLARIS — Canadian-hosted clinical research that proves every sentence against its primary source."
- TRUST_POINTS list preserved verbatim (mirrors v6 home pillar pattern)

PRESERVED contracts:
- `data-testid="sign-in-form"`, `sign-in-submit`, `sign-in-error`, `sign-in-loading`
- login + same-origin ?next= validation + handleSubmit logic
- MapleLeafSignatureLazy decorative
- POLARIS · Canada brand line
- TRUST_POINTS list (3 trust statements)
- Card/form structure
- ChromelessRoute (sign-in is its own surface, no AppShell)

## Operator-locked constraints

Brand-red THREE paths preserved (eyebrow, evidence-T1 not applicable, text-primary trust-point icons).

Honest sovereignty — no "signed bundle" overclaim. Subtitle uses "proves every sentence against its primary source" (honest, exists today).

## File plan (surgical)

REBUILD
1. `web/app/sign-in/page.tsx` — header region (lines ~119-128):
   - Add brand-red eyebrow
   - Bump H1 to display weight + new copy
   - Add subtitle
   - Rest of the page (login form, TRUST_POINTS, ?next= validation, error/loading states) PRESERVED VERBATIM

UPDATE
2. `web/tests/e2e/sign_in.spec.ts` — add v6 chrome cases (eyebrow + H1 + subtitle render) at the end.
3. `.github/workflows/web_ci.yml` — sign_in.spec.ts is NOT currently in CI. ADD BOTH (per Codex iter-1 P1):
   (a) NEW run_e2e_sign_in step enumerating tests/e2e/sign_in.spec.ts
   (b) auth-fixture env on the existing `start_fastapi_backend` block:
       - POLARIS_JWT_SECRET: "test_jwt_secret_for_ci_only_must_not_be_used_in_production"
       - POLARIS_STATIC_ACCOUNTS_PATH: "${{ github.workspace }}/tests/fixtures/auth/test_static_accounts.yaml"
   Without these envs the FastAPI backend startup fails loud, so the new step would crash before reaching sign-in assertions.

## Files I have ALSO checked

- web/lib/auth.ts — login contract unchanged
- web/components/app_shell_gate.tsx — /sign-in is chromeless (correctly)
- web/tests/e2e/sign_in.spec.ts EXISTS but may not be in web_ci.yml — will verify on impl

## Brief-review check requests

- `scope_visual_only`: PASS / FAIL
- `existing_testids_preserved`: PASS / FAIL (sign-in-form, sign-in-submit, sign-in-error)
- `chromeless_preserved`: PASS / FAIL (sign-in stays chromeless, not in AppShell)
- `next_validation_preserved`: PASS / FAIL (?next= same-origin guard unchanged)
- `ci_wiring_addressed`: PASS / FAIL (if sign_in.spec.ts not in CI, web_ci.yml updated to enumerate)
- `no_signed_bundle_overclaim`: PASS / FAIL

## Output schema (BIND)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
specific_check_responses:
  scope_visual_only: PASS | FAIL_with_detail
  existing_testids_preserved: PASS | FAIL_with_detail
  chromeless_preserved: PASS | FAIL_with_detail
  next_validation_preserved: PASS | FAIL_with_detail
  ci_wiring_addressed: PASS | FAIL_with_detail
  no_signed_bundle_overclaim: PASS | FAIL_with_detail
```
