# Codex diff review — sub-PR 2 (#883) CI-wiring amend per #892

## §0 cap directive (CLAUDE.md §8.3.1, verbatim — abbreviated for delta review)

```
HARD ITERATION CAP: 5. This is iter 1. Front-load all real findings.
Verdict APPROVE iff zero P0+P1.
```

## Phase

Diff re-review on ONLY the new commit `8fb55bb4` appended to PR #883's branch (`bot/I-ux-001c-sub-pr-2-home`).

## What changed

`.github/workflows/web_ci.yml` — added 16 lines: two new steps (`run_e2e_home_proof_as_cta`, `run_e2e_home_aa`) enumerating the two existing v6 specs added in the original sub-PR 2 commits. NO other files changed.

## Why

Follow-up issue #892: original sub-PR 2 added `web/tests/e2e/home_proof_as_cta.spec.ts` + `web/tests/e2e/home_aa.spec.ts` but did NOT enumerate them in `.github/workflows/web_ci.yml`. Per LAW II "no fake working" — un-enumerated specs are CI-dead.

Both specs:
- Read from the static canonical_bundles fixture (`web/public/canonical_bundles/v1_canonical_success/`) — NO backend call
- Use the existing `start_fastapi_backend` block's defaults (no new env needed)
- home_aa runs axe at desktop 1440×900 + mobile 390×844; asserts zero violations across ALL impacts (the brief locked this at iter-1 P2-003 tightening)

## Risk

home_aa.spec.ts has never executed against the actual built page — only typechecked. CI is the first execution. If axe finds minor violations not visible in the iter-3 visual screenshots, the CI step will fail. Operator can run locally first or accept this as a check on the v6 home page's accessibility before merge.

## Specific checks

- `ci_yaml_syntax_valid`: PASS / FAIL — yaml structure parses (indentation, key spelling, env block shape)
- `step_names_unique`: PASS / FAIL — run_e2e_home_proof_as_cta and run_e2e_home_aa don't collide with existing step names
- `spec_files_exist`: PASS / FAIL — home_proof_as_cta.spec.ts and home_aa.spec.ts exist on this branch
- `no_other_changes`: PASS / FAIL — diff vs ead68a2c contains ONLY web_ci.yml additions

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
  ci_yaml_syntax_valid: PASS | FAIL_with_detail
  step_names_unique: PASS | FAIL_with_detail
  spec_files_exist: PASS | FAIL_with_detail
  no_other_changes: PASS | FAIL_with_detail
```
