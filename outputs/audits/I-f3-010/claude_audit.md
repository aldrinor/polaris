# Claude Architect Audit — I-f3-010 (sovereignty walkthrough)

**Branch:** bot/I-f3-010
**Diff SHA256:** `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855` (empty post-audit-exclusion; deliverable lives in audit-excluded path)
**LOC:** 0 net source-code; walkthrough doc in audit-excluded path.

## Files

```
outputs/audits/I-f3-010/sovereignty_walkthrough.md   NEW (audit-excluded from canonical SHA)
```

## Iter-2 brief P1 fixes (line refs corrected)

- `classification.py:25-32` for EXTERNAL_LEAK_FORBIDDEN
- `router.py:43` (`filter_for_external_egress`), `:71` (`assert_safe_for_external`)
- `test_red_team.py:25` / `:31` / `:37` for the 3 red-team tests
- `test_router.py:49` for PUBLIC_SYNTHETIC permit
- `upload.py:43` (classification field), `:56` (Form default)
- Iter-2 P2 fix: CI gating qualified as INACTIVE pending user-rename of `.yml.pending_workflow_scope`.

## Verdict

APPROVE for Codex diff review.
