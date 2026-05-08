# Codex Brief Review — I-f14-004 (ITER 2 of 5)

## Iter 2 changes per Codex iter 1

- **P1 fix (dedup semantics):** memory entries dedup against the ENTIRE pool by normalized text only (NOT (url, text)). Implementation: after building pool from upload + retrieval, gather their normalized_text into a `text_seen: set[str]`. For each memory summary, skip if its normalized text is in `text_seen`. Existing (url, text) dedup between upload + retrieval is preserved (no breaking change for current callers).
- **P2 fix:** use `memory_summaries: list[MemoryDerivedSummary] | None = None` default + `memory_summaries or []` inside.
- **P2 fix:** drop the "8 tests" hard count — say "existing tests in test_evidence_pool_merger.py still pass."
- **P2 fix:** strengthen memory-test assertions to verify `source_tier == "T3"`, `source_url == "memory://{entry_id}"`, span_start/span_end correct.

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Pre-flight

- **Issue:** I-f14-004 — Memory-as-corpus for new queries. Scope: prior runs join evidence pool. Acceptance: integration test. LOC estimate 130.
- **Substrate today:** `src/polaris_v6/adapters/evidence_pool_merger.py::merge_evidence_pool` accepts retrieval_spans + uploaded_chunks. No memory input.
- **Honest framing per CLAUDE.md §9.4:** extend the merger with an optional `memory_summaries` param that converts `prior_run_summary` MemoryEntry items into deterministic SourceSpan items with stable evidence_ids. Production wiring (graph_v4 / generation pipeline reading workspace memory and passing it to the merger) is a follow-up I-f14-004b. This issue ships ONLY the merger function + integration test that proves the pool contains memory-derived spans.

## Plan

### `src/polaris_v6/adapters/evidence_pool_merger.py` (extend)

1. Add `MemoryDerivedSummary` dataclass: `entry_id: str`, `content: str`, `created_at: str`.
2. Add `_evidence_id_for_memory(summary)`: stable id `ev_memory_<sha256[:12]>` from `entry_id + content`.
3. Extend `merge_evidence_pool` signature with optional `memory_summaries: list[MemoryDerivedSummary] | None = None`.
4. Memory summaries shipped LAST (after upload + retrieval). Tier "T3" (prior-run-summary is user-derived, not primary-source).
5. Source URL: `f"memory://{entry_id}"`.
6. **Dedup (per Codex iter-1 P1):** keep existing (url, text) dedup for upload + retrieval. After both are appended, build `text_seen: set[str]` of all normalized pool texts. Iterate memory summaries; skip if normalized content already in `text_seen`. This preserves upload > retrieval > memory priority via append order, AND deduplicates memory across the WHOLE pool by text-only.

### Tests `tests/v6/test_evidence_pool_memory.py` (NEW)

7. `test_memory_summaries_appear_in_pool`: pool contains memory-derived spans with `ev_memory_*` ids, `source_tier == "T3"`, `source_url == "memory://{entry_id}"`, `span_start == 0`, `span_end == len(content)`.
8. `test_memory_summaries_dedup_internal`: two memory entries with identical normalized text → only one in pool.
9. `test_uploaded_takes_priority_over_memory`: same span_text in upload + memory → memory dropped (only upload entry).
10. `test_retrieval_takes_priority_over_memory`: same span_text in retrieval + memory → memory dropped (only retrieval entry).
11. `test_pool_with_all_three_kinds`: retrieval + upload + memory all present, no duplicates by normalized text.

## Risks for Codex Red-Team

1. **Tier choice T3:** prior-run-summary is genuinely user-derived; T3 honest for "operator-asserted" tier. Documentation note in the brief.
2. **Production wiring deferred:** I-f14-004b will wire workspace_memory.list_workspace → merger. This issue's scope is the merger surface only.
3. **§9.4 backend hygiene:** no `try/except: pass`, no magic numbers, no `time.sleep`, no TODOs.
4. **CHARTER §3 LOC cap:** estimated merger +30, test +80 = ~110. Under 200.

## Acceptance criteria

1. New `MemoryDerivedSummary` dataclass.
2. `merge_evidence_pool` accepts `memory_summaries`.
3. Memory spans get `ev_memory_*` ids and `memory://{entry_id}` URLs.
4. Dedup honored across all three sources (upload > retrieval > memory priority).
5. 5 tests in `tests/v6/test_evidence_pool_memory.py` pass.
6. Existing `test_evidence_pool_merger.py` unchanged and still passes.
7. CHARTER §3 LOC cap respected (≤200 net).

**Forced enumeration:** before verdict, write one line per criterion 1-7.
**Completeness check:** list files actually read.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero NOVEL P0 + zero continuing P0 + zero P1.
