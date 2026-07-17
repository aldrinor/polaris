# Codex review — consolidated #892 CI-wiring amends (sub-PRs 3, 4, 5)

## §0 cap directive (abbreviated)

```
HARD CAP 5 per document. iter 1 of 5.
Verdict APPROVE iff zero P0+P1.
```

## Phase

3 small follow-up commits across 3 sub-PR branches:

| Sub-PR | Branch | Commit | Adds |
|---|---|---|---|
| 3 | `bot/I-ux-001c-sub-pr-3-intake` | `27a96e3f` | `run_e2e_intake_v6` step + `intake_v6.spec.ts` enumeration |
| 4 | `bot/I-ux-001c-sub-pr-4-source-review` | `5fc70595` | `run_e2e_source_review_v6` step + `source_review_v6.spec.ts` enumeration |
| 5 | `bot/I-ux-001c-sub-pr-5-plan-review` | `4b9fb721` | `run_e2e_plan_v6` step + `plan_v6.spec.ts` enumeration |

Each commit modifies ONLY `.github/workflows/web_ci.yml` — adds a single playwright step block enumerating the existing v6 spec.

## Why

Follow-up issue #892 (filed at sub-PR 6 brief iter-3): standalone v6 specs from sub-PRs 2-5 weren't enumerated in `web_ci.yml` → CI-dead per LAW II "no fake working." Sub-PR 2's amend (commit `8fb55bb4`) already shipped with Codex APPROVE clean (iter-1).

## Specific checks (single yaml block each)

For EACH of the 3 sub-PR amends:

- `ci_yaml_syntax_valid`: PASS / FAIL — yaml structure parses
- `step_name_unique`: PASS / FAIL — new step name doesn't collide
- `spec_file_exists_on_branch`: PASS / FAIL — the spec file exists on the sub-PR's branch
- `mock_pattern_correct`: PASS / FAIL — the spec uses page.route to mock the auth-gated endpoint matching BACKEND_URL prefix (verified by reading the spec on each branch)
- `no_other_changes`: PASS / FAIL — diff vs each sub-PR's prior HEAD contains ONLY the web_ci.yml addition

## Output schema (BIND)

Return ONE block PER sub-PR with the schema below. If any sub-PR fails, list it; otherwise APPROVE all three.

```yaml
sub_pr_3_intake:
  verdict: APPROVE | REQUEST_CHANGES
  novel_p0: [...]
  continuing_p0: [...]
  p1: [...]
  p2: [...]
  specific_check_responses:
    ci_yaml_syntax_valid: PASS | FAIL_with_detail
    step_name_unique: PASS | FAIL_with_detail
    spec_file_exists_on_branch: PASS | FAIL_with_detail
    mock_pattern_correct: PASS | FAIL_with_detail
    no_other_changes: PASS | FAIL_with_detail

sub_pr_4_source_review:
  verdict: APPROVE | REQUEST_CHANGES
  ...same schema...

sub_pr_5_plan:
  verdict: APPROVE | REQUEST_CHANGES
  ...same schema...

overall_verdict: APPROVE | REQUEST_CHANGES
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
