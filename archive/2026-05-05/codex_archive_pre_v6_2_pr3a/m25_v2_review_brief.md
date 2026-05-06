M-25 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-25 v1 verdict: PARTIAL with 2 specific edits.

1. Race between approval check and sync_runs insert (separate
   transactions).
2. Missing common raw-secret shapes (Slack, Google, Azure).

Both integrated in v2 (commit 45a70eb).

## What changed in v2

`private_corpus_sync.py`:
- `record_sync_run` now wraps the whole operation in
  BEGIN IMMEDIATE / COMMIT. Source status is re-read INSIDE
  the lock; if a concurrent revoke landed, SyncBlockedError
  fires and no sync row is written.
- `_looks_like_raw_secret` now also rejects:
    - Slack: xoxb-/xoxp-/xoxa-/xoxs-/xapp-
    - Google API: AIza... (39+ chars)
    - Google OAuth: ya29. / 1//
    - Azure: AccountKey= / SharedAccessKey= / SharedAccessSignature=
    - GitHub fine-grained PAT: github_pat_
    - OpenSSH/EC private keys: BEGIN OPENSSH/EC PRIVATE KEY

Tests added (2 + 12 parametrized):
- test_record_sync_run_atomic_check_and_insert (revoke between
  syncs — second record_sync_run must refuse, no second row).
- test_register_rejects_codex_m25_secret_patterns x12.

Module: 41/41 private_corpus_sync tests green.

## Your job

Final verdict on M-25. GREEN / PARTIAL / DISAGREE.

If GREEN, M-25 v2 locks (registry substrate; connector wire-up
ships in M-25 v3).

## Output

Write to `outputs/codex_findings/m25_v2_review/findings.md`:

```markdown
# Codex re-review of M-25 v2

## Verdict
GREEN / PARTIAL / DISAGREE

## v1 fix integration
- [x/no] approval check + insert atomic under BEGIN IMMEDIATE
- [x/no] Slack/Google/Azure secret patterns rejected

## Final word
GREEN to lock M-25 + proceed / PARTIAL with edits.
```

Be terse. Under 60 lines.
