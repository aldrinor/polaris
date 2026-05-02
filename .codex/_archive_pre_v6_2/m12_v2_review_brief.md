M-12 v2 — re-review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Your M-12 v1 verdict: PARTIAL with 2 HIGH:

1. OpenRouterBriefClient broken on production path:
   - OpenRouterClient.generate() is async + returns LLMResponse,
     not str
   - v1 called asyncio.run() from inside an async FastAPI route
   - Even on success, .strip() on LLMResponse → AttributeError
   - Tests passed only because FakeLlm was sync

2. retrieve_chunks() raced soft-delete:
   - Two-phase: list_uploads(include_deleted=False) → list_chunks
     per-upload
   - list_chunks didn't JOIN back to uploads.deleted_at
   - Delete landing between the two reads let deleted chunks
     leak into the retrieval set

Both integrated in v2 (commit c3a6d4e).

## What changed in v2

**Async OpenRouter bridge:**
- `LlmClient.draft_brief` is now async (Protocol).
- `compose_brief` is now async; awaits `llm.draft_brief(...)`.
- `OpenRouterBriefClient.draft_brief` is async; awaits
  `self._client.generate(...)` and reads `.content` via
  `getattr(response, "content", None)`. Validates that the result
  is a str; raises ValueError otherwise (LAW II — no silent str
  cast).
- Code-fence stripping now also trims trailing fences.
- Test fakes (`FakeLlm`) updated to `async def draft_brief`.
- API endpoint `compose_workspace_brief` awaits `compose_brief`.

**Atomic retrieval:**
- `WorkspaceStore.list_eligible_chunks(workspace_id)` — NEW
  single-query API. SQL:
    SELECT c.*, u.filename
    FROM upload_chunks c JOIN uploads u ON ...
    WHERE u.workspace_id = ?
      AND u.deleted_at IS NULL
      AND u.parser_status = 'parsed'
- `retrieve_chunks` now uses `list_eligible_chunks`. The v1
  two-phase pattern is gone; the deleted/parsed gates are checked
  atomically against `upload_chunks` so a soft-delete between
  reads cannot leak.

**Tests: 7 new.**
- `test_openrouter_brief_client_parses_llm_response_content`:
  real LLMResponse shape with .content attribute.
- `test_openrouter_brief_client_handles_code_fences`: ```json
  fence stripping.
- `test_openrouter_brief_client_raises_on_missing_paragraphs_key`
  / `..._on_non_list_paragraphs`: LAW II — no silent fallback.
- `test_openrouter_brief_client_e2e_through_compose_brief`: full
  end-to-end with real-shape async fake → would have caught v1.
- `test_retrieval_excludes_concurrently_deleted_uploads`:
  reproduces the v1 race (delete between would-be reads).
- `test_list_eligible_chunks_excludes_deleted_and_unparsed`:
  direct test of the new store API; covers parsed/pending/failed/
  parsed+deleted matrix.

Phase B suite 363 → 370 green.

## Your job

Final verdict on M-12. GREEN / PARTIAL / DISAGREE.

Probe with:
- More concurrency races on retrieval / brief composition
- Anything else that could let the production /brief endpoint
  500 or silently fabricate

If GREEN, M-12 is locked and Phase B can proceed to M-13
(Progressive in-run Inspector surfaces).

## Output

Write to `outputs/codex_findings/m12_v2_review/findings.md`:

```markdown
# Codex re-review of M-12 v2

## Verdict
GREEN / PARTIAL / DISAGREE

## v1 fix integration
- [x/no] OpenRouter bridge async-safe + LLMResponse.content parsed
- [x/no] Atomic retrieval via JOIN — no soft-delete race

## New issues
none / list

## Final word
GREEN to lock M-12 + proceed to M-13 / PARTIAL with edits.
```

Be terse. Under 100 lines.
