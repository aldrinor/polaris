M-25 v1 (private-corpus sync registry) — first review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-25 ships the narrow private-corpus sync registry per
FINAL_PLAN Phase C deliverable #7:
  Narrow private-corpus sync (Drive/SharePoint/Confluence —
  approved-only, NOT broad connector parity).

v1 is the registry + status surface. v2 wires actual connectors.
The approval gate is the FINAL_PLAN-mandated control: only
operator-APPROVED sources can record sync runs.

## What changed in v1 (commit 0bcc46a)

New module: `src/polaris_graph/audit_ir/private_corpus_sync.py`

  Schema (SQLite, WAL):
    corpus_sources(source_id, workspace_id, org_id, connector,
      name, external_uri, credential_ref, status, approved_by,
      revoked_by, created_at, updated_at)
    sync_runs(sync_run_id, source_id FK, triggered_by_user_id,
      status, doc_count, bytes_synced, error_message,
      started_at, finished_at)

  Closed enums:
    SourceConnector: google_drive | sharepoint | confluence
    SourceStatus: pending → approved → revoked → approved cycle
    SyncRunStatus: succeeded | failed | partial

  Approval gate: register_source lands in PENDING. Only
  approve_source() flips to APPROVED. record_sync_run() raises
  SyncBlockedError on non-APPROVED sources.

  Defense in depth: register_source has `_looks_like_raw_secret`
  heuristic that rejects credential_ref shapes resembling JWTs,
  AWS access keys, PEM private keys, GitHub PATs, OpenAI keys.
  credential_ref is meant to be a vault POINTER — secrets must
  not be stored here.

  Cross-tenant invariants:
    - Every method takes org_id and SQL-filters on it
    - get_source returns None for cross-org
    - Mutators raise on cross-org write attempts
    - record_sync_run verifies source-in-org before logging
    - list_sync_runs returns [] for cross-org

Tests (28): registration, raw-secret rejection, approval/revocation
lifecycle, cross-tenant isolation, approval-gate enforcement,
history-preserved-after-revocation, list filters, serialization.

## Your job

Verdict on M-25 v1. GREEN / PARTIAL / DISAGREE.

Look for:

1. **Cross-tenant bypass.** Same dominant Phase C failure mode.
   Can org_b register/approve/revoke/sync against org_a's source
   via any path?
2. **Approval-gate bypass.** Can a sync land for a non-APPROVED
   source via any code path? My read: no — record_sync_run is
   the only sync entry point and it gates on source.status ==
   APPROVED.
3. **Raw-secret heuristic completeness.** _looks_like_raw_secret
   catches JWT, AWS, PEM, GitHub PAT, OpenAI sk-. Are there
   common shapes I've missed (Slack tokens, Google service
   account JSON keys, Azure connection strings)?
4. **Sync-history integrity.** Is there any path that deletes a
   sync_runs row? My read: no public method.
5. **External_uri validation.** I accept any non-empty string —
   should I validate per-connector format (Drive: folder ID
   shape; SharePoint: URL; Confluence: space key)? My read:
   defer to connector implementation in v2.
6. **Anything else worth flagging before M-25 locks.**

If GREEN, M-25 v1 substrate locks. Connector wire-up ships in v2.

## Output

Write to `outputs/codex_findings/m25_review/findings.md`:

```markdown
# Codex review of M-25 v1

## Verdict
GREEN / PARTIAL / DISAGREE

## Cross-tenant isolation
- [defensible / list issues]

## Approval gate
- [defensible / list bypass paths]

## Raw-secret heuristic
- [defensible / list missed shapes]

## Final word
GREEN to lock M-25 + proceed / PARTIAL with edits.
```

Be terse. Under 100 lines.
