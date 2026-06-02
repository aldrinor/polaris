# Codex diff review — I-ux-001c sub-PR 9 (/sign-in v6 chrome + CI wiring)

## §0 cap directive (CLAUDE.md §8.3.1, verbatim)

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Phase

Diff review. Brief APPROVED iter-3 (5/6 PASS + 1 non-blocking P2).

## Diff under review

`.codex/I-ux-001c-9/codex_diff.patch` — sign-in page header rebuild + new test case in sign_in.spec.ts + web_ci.yml updates (auth env on start_fastapi_backend + new run_e2e_sign_in step).

## Approved brief acceptance criteria

1. Brand-red eyebrow "SIGN IN · POLARIS CLINICAL RESEARCH"
2. Display H1 "Sign in to verify every claim."
3. Tightened subtitle locked verbatim
4. MapleLeafSignatureLazy + login form + ?next= validation + TRUST_POINTS + error/loading states UNCHANGED
5. NEW v6 chrome test in sign_in.spec.ts
6. web_ci.yml updated:
   - start_fastapi_backend block has POLARIS_JWT_SECRET + POLARIS_STATIC_ACCOUNTS_PATH env
   - NEW run_e2e_sign_in step
7. typecheck PASS

## Specific checks

- `visual_only_rebuild`: PASS / FAIL
- `existing_testids_preserved`: PASS / FAIL (sign-in-form, sign-in-submit, sign-in-error)
- `chromeless_preserved`: PASS / FAIL
- `next_validation_preserved`: PASS / FAIL
- `ci_auth_env_added`: PASS / FAIL (POLARIS_JWT_SECRET + POLARIS_STATIC_ACCOUNTS_PATH on start_fastapi_backend)
- `ci_sign_in_step_added`: PASS / FAIL (run_e2e_sign_in step exists)
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
  visual_only_rebuild: PASS | FAIL_with_detail
  existing_testids_preserved: PASS | FAIL_with_detail
  chromeless_preserved: PASS | FAIL_with_detail
  next_validation_preserved: PASS | FAIL_with_detail
  ci_auth_env_added: PASS | FAIL_with_detail
  ci_sign_in_step_added: PASS | FAIL_with_detail
  no_signed_bundle_overclaim: PASS | FAIL_with_detail
```

## Context

- Brief (APPROVE iter-3): `.codex/I-ux-001c-9/brief.md`
- Diff: `.codex/I-ux-001c-9/codex_diff.patch`
- Branch: `bot/I-ux-001c-sub-pr-9-sign-in`
