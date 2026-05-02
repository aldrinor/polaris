M-21 v1 — first review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-21 ships retrieval-active workspace memory per FINAL_PLAN Phase
C deliverable #4:
  - User-visible, attributable, removable
  - Retrieved priors LABELED in Evidence Inspector view 1 as
    "memory-derived"
  - Workspace boundaries strict; no cross-customer leakage
  - Freshness/staleness rules

This is the substrate the V30 runner will retrieve from before
generating an audit (so previously-seen claims can be cited
without re-fetching). The runner integration is a separate
milestone; M-21 is just the store + endpoints + isolation
guarantees.

## What changed in v1 (commit bb7207a)

New module: `src/polaris_graph/audit_ir/workspace_memory.py`

Schema (SQLite, WAL):
  workspace_memory(entry_id, workspace_id, claim_text,
    source_url, source_tier, source_evidence_id,
    created_at, last_used_at)
  + idx_workspace_memory_ws_created (DESC) for the freshness path

Cross-workspace isolation: every method takes workspace_id and
SQL filters on it. The retrieve()/list_entries()/get_entry()/
delete_entry()/delete_all_for_workspace methods all scope to
that single workspace; cross-workspace bleed is impossible via
the API surface.

Public API:
- append_entry(workspace_id, claim_text, source_url,
  source_tier, source_evidence_id=None)
  Validates: non-empty workspace_id / claim_text / source_url /
  source_tier (LAW II — no silent empty-default attribution).
- get_entry(workspace_id, entry_id) → MemoryEntry | None
- list_entries(workspace_id, max_age_days=None) → newest-first
- retrieve(workspace_id, query, top_k=10, max_age_days=None)
  → list[(MemoryEntry, score)]. Jaccard overlap on stopword-
  filtered tokens (matches M-10 tokenizer convention).
  Side effect: bumps last_used_at on retrieved entries so future
  ranking can favor recently-useful memory.
- delete_entry(workspace_id, entry_id) → bool. Hard-delete.
- delete_all_for_workspace(workspace_id) → int. Bulk purge.

Endpoints (auth-gated, reusing existing workspace deps):
  POST   /api/inspector/workspaces/{ws}/memory          (member+)
  GET    /api/inspector/workspaces/{ws}/memory          (viewer+)
  POST   /api/inspector/workspaces/{ws}/memory/retrieve (viewer+)
  DELETE /api/inspector/workspaces/{ws}/memory/{id}     (member+)

Tests (28):
  - 18 store unit tests (append validation, cross-workspace
    isolation across all reads/writes, retrieve scoring +
    freshness cutoff at 7 vs 60 days, last_used_at bump, top_k
    cap, stopword behavior, serialization)
  - 6 endpoint integration tests (member-required for write,
    cross-org rejection, retrieve+list payload shape, delete
    200/404)

Combined Phase C suite (M-16/M-17/M-18/M-20/M-23/M-21):
227/227 green.

## Your job

Verdict on M-21 v1. GREEN / PARTIAL / DISAGREE.

I'm asking you to look for:

1. **Cross-workspace bleed.** Can a caller with workspace_a
   credentials read/write/delete a workspace_b memory entry by
   any path? Endpoint, store API, retrieve query, etc.
2. **Cross-org bleed.** Can a caller from org_b access org_a's
   workspace_id via the URL? (The workspace dep should already
   handle this — confirm there's no path that bypasses it.)
3. **Hard-delete completeness.** Is there any path where a
   "deleted" entry persists somewhere (audit log, retrieve cache,
   etc.)? Per FINAL_PLAN, customers must be able to guarantee a
   deletion request actually purges the underlying data.
4. **Retrieval correctness.** Does the keyword-overlap scoring
   match the FINAL_PLAN attribution requirement, or do we need
   embeddings even in v1? My read is keyword overlap is
   sufficient for v1 because the runner will only present
   retrieved entries to the human reviewer (not generate from
   them autonomously).
5. **Freshness rule reasonableness.** max_age_days is optional —
   should the default be tighter? Tighter would risk hiding
   useful memory; looser would risk surfacing stale claims.
6. **Stopword + tokenization edge cases.** A query like "tirzepatide"
   (one content word) — does this give reasonable results? A query
   in lowercase vs Title Case?
7. **Anything else worth flagging before M-21 locks.**

If GREEN, M-21 locks. Phase C continues to M-19 / M-NEW (billing).

## Output

Write to `outputs/codex_findings/m21_review/findings.md`:

```markdown
# Codex review of M-21 v1

## Verdict
GREEN / PARTIAL / DISAGREE

## Cross-workspace isolation
- [list bypass attempts and results]

## Cross-org isolation
- [list bypass attempts and results]

## Hard-delete completeness
- [defensible / list issues]

## Retrieval / freshness
- [defensible / list issues]

## Final word
GREEN to lock M-21 + proceed / PARTIAL with edits.
```

Be terse. Under 100 lines.
