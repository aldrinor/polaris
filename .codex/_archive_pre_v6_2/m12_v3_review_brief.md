M-12 v3 — final GREEN check.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-12 v2 verdict: PARTIAL with 2 HIGH:
1. /brief 500s: passing `thinking_mode=False` to OpenRouterClient.
   generate() — kwarg doesn't exist in the real signature.
2. Soft-delete during the LLM await still let deleted chunks
   stay in the validation set; final brief could return supported
   citing a now-deleted chunk.

Both integrated in v3 (commit 47e4ec1).

## What changed in v3

`corpus_brief.OpenRouterBriefClient.draft_brief`:
- Removed `thinking_mode=False`. Real generate() signature is
  (prompt, system, max_tokens, temperature, timeout,
  reasoning_max_tokens, reasoning_exclude). The prose path runs
  with reasoning OFF by default.

`corpus_brief.compose_brief`:
- After `await llm.draft_brief(...)`, re-snapshot
  `eligible_now = store.list_eligible_chunks(workspace_id)`.
- `chunks_by_id` is now built from the intersection
  (pre-await chunks ∩ post-await eligible IDs).
- Citations to chunks deleted during the await are dropped.
- `retrieved_chunks` in the response also filters to the
  post-await eligible set.

`tests/test_corpus_brief.py`:
- `test_compose_brief_drops_citation_when_upload_deleted_mid_await`:
  `_DeletingLlm` fake calls `store.soft_delete_upload(target)`
  INSIDE its draft_brief, then returns a paragraph citing the
  now-deleted chunk. Asserts brief returns `insufficient_support`
  and the deleted chunk is absent from `retrieved_chunks`.
- `test_openrouter_brief_client_does_not_pass_thinking_mode_kwarg`:
  `StrictAsyncOpenRouter` fake has NO `thinking_mode` parameter
  (mirrors the real signature). Asserts OpenRouterBriefClient
  passes only kwargs the real generate() accepts.

Phase B suite 370 → 372 green.

## Your job

Final verdict on M-12. GREEN / PARTIAL / DISAGREE.

If you find another race or signature mismatch, please include
the exact reproducer.

If GREEN, M-12 is locked and Phase B can proceed to M-13.

## Output

Write to `outputs/codex_findings/m12_v3_review/findings.md`:

```markdown
# Codex final review of M-12 v3

## Verdict
GREEN / PARTIAL / DISAGREE

## v2 fix integration
- [x/no] thinking_mode kwarg removed; real signature respected
- [x/no] Mid-await delete race closed (post-await re-snapshot)

## Final word
GREEN to lock M-12 + proceed to M-13 / PARTIAL with edits.
```

Be terse. Under 60 lines.
