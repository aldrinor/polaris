M-12 Question-Bound Corpus Brief — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-11 GREEN-locked across 3 review rounds. M-12 is the
Question-Bound Corpus Brief per FINAL_PLAN.md feature #6:

> "Narrow form: answer one user question over a SELECTED corpus,
> emit cited brief. Per-paragraph inline citations OR explicit
> 'insufficient support' labels. Dependent on bounded upload
> landing first. NOT 'Workspace Brief' or 'WikiLLM' in product
> copy."

Phase B trust risk: silent fabrication. Per LAW II, every
paragraph must either cite a real chunk_id from the retrieved set
OR be labeled `insufficient_support`. Never a hollow paragraph.

## What landed (commit 37715fd)

**`src/polaris_graph/audit_ir/corpus_retriever.py`** (~190 lines):
- BM25 retrieval over the workspace's parsed chunks. No
  embeddings — keeps Phase B deterministic + dep-free.
- Tokenizer reuses template_classifier primitives (hyphen split,
  Unicode hyphen normalize, stopword filter, Roman + compact
  drug-class normalization) so retrieval stays consistent with
  the routing classifier's content-token notion.
- Drops chunks from soft-deleted or non-`parsed` uploads.
- Unknown workspace raises ValueError (caller maps to 404). Per
  LAW II — NEVER silently returns [] for unknown workspace.
- Defaults: top_k=8, min_score=0.5.

**`src/polaris_graph/audit_ir/corpus_brief.py`** (~280 lines):
- `LlmClient` Protocol: `draft_brief(question, chunks) -> list[dict]`.
  Tests pass a fake; production wires `OpenRouterBriefClient`.
- `compose_brief()`:
  1. Retrieve top-K chunks.
  2. If 0 → emit single `insufficient_support` paragraph; LLM
     never called.
  3. Else → llm.draft_brief() returns paragraph dicts.
  4. **Validator** drops paragraphs that:
     - Are not dicts.
     - Have empty/whitespace claim.
     - Have `citations` that's not a list.
     - End up with zero VALID citations after filtering.
     A citation is valid only if its chunk_id is in the retrieved
     set (the soft-deleted, pending, and unrelated upload chunks
     are NOT in that set, so even an LLM that knows their IDs
     can't smuggle them through).
  5. If validator drops EVERY paragraph → emit
     `insufficient_support` fallback rather than a hollow brief.
- Per-paragraph citation dedup; tolerates malformed LLM responses
  by skipping rather than crashing.
- `OpenRouterBriefClient.draft_brief()` calls `OpenRouterClient.
  generate()`, parses JSON, raises if no `paragraphs` key (LAW II).
  No silent fallback to a stub paragraph.

**`inspector_router.py`** — one new endpoint:
  POST /api/inspector/workspaces/{ws_id}/brief
  Body: {question: str, top_k: int [1, 50], min_score: float >= 0}
  Returns: brief dict with paragraphs[*].support_status in
  {"supported", "insufficient_support"}.

**Test hook**: `_set_brief_llm_for_tests()` injects a fake
LlmClient so unit tests don't need network credentials.

**Tests: 30 new (12 retriever + 11 brief composition + 7 API).
Phase B suite 333 → 363 green.**

Test cases of note:
- `test_compose_brief_drops_paragraphs_with_unknown_chunk_ids`:
  LLM tries to cite `ck_does_not_exist` → paragraph dropped →
  insufficient_support fallback.
- `test_brief_endpoint_excludes_chunks_from_deleted_uploads`:
  end-to-end test that even if the LLM knows a soft-deleted
  chunk's ID, retrieval excludes it so the validator drops the
  citation.
- `test_compose_brief_propagates_llm_errors`: LLM RuntimeError
  propagates; no silent fallback.

## Anti-scope (deferred — please do NOT push back on these)

- Vector retrieval — Phase C M-12.5
- Async brief job — Phase C; Phase B sync is fine for small
  workspaces
- Multi-paragraph orchestration / sub-question decomposition —
  Phase C
- ACL beyond workspace scoping — Phase C

## Your job

Code review for M-12. Verdict: GREEN / PARTIAL / DISAGREE.

## Specific things to validate

1. **Citation integrity.** Can an attacker / hallucinating LLM
   smuggle a fabricated chunk_id into the brief? The validator
   should make this impossible — verify by reading
   `compose_brief` lines 165-200 and the retrieval-set membership
   check around line 175.

2. **Insufficient-support semantics.** Is the explicit
   insufficient_support label always the result when:
   - retrieval is empty
   - LLM returns no usable paragraphs
   - LLM returns paragraphs that all fail the validator
   No other path should produce a hollow brief.

3. **LLM error propagation.** `compose_brief` doesn't catch
   exceptions from `llm.draft_brief()`. Are there any subtle
   places where a fallback could leak?

4. **BM25 implementation.** Standard Robertson-Sparck-Jones
   formula in `_bm25_score`. Any obvious bugs (idf neg, divide
   by zero, fencepost)?

5. **Retrieval boundary integrity.** `retrieve_chunks` excludes
   soft-deleted + non-parsed uploads. Is there any way for a
   chunk from those to leak through?

6. **OpenRouterBriefClient JSON parsing.** Strips ```json fences,
   parses, raises on missing key. Any failure mode where a
   malformed response silently falls back to "no paragraphs"
   instead of raising?

7. **Anything else you'd push back on.**

## Output

Write to `outputs/codex_findings/m12_review/findings.md`:

```markdown
# Codex review of M-12

## Verdict
GREEN / PARTIAL / DISAGREE

## Specific issues
File:line bugs / gaps.

## Citation-fabrication defense
Is the validator airtight against fabricated chunk_ids?

## Insufficient-support label behavior
Always explicit when no real support exists?

## Recommended changes
If PARTIAL.

## M-13 readiness
Is the workspace + brief infrastructure ready for progressive
in-run Inspector surfaces?

## Final word
GREEN to lock M-12 / PARTIAL with edits / DISAGREE.
```

Be terse. Under 250 lines.
