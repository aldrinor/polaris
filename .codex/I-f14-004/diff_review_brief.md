# Codex Diff Review — I-f14-004 (ITER 1 of 5)

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Static review only — DO NOT spawn dev servers.

**Issue:** I-f14-004 — Memory-as-corpus for new queries
**Brief:** APPROVED iter 2 (P1 dedup-semantics fix; 3 P2 fixes)
**Canonical-diff-sha256:** `4f075d31082ed6fbf131f49cd4756cdca43a21bc0f25bec2fd658a1643e1239d`
**LOC:** 149 net (under CHARTER §3 200-cap)

## Files

```
src/polaris_v6/adapters/evidence_pool_merger.py   +43 -5  (MemoryDerivedSummary + memory_summaries param)
tests/v6/test_evidence_pool_memory.py             NEW +106 (5 tests covering 4 dedup priorities)
```

## What changed

### `evidence_pool_merger.py`
- Added `MemoryDerivedSummary` dataclass: `entry_id`, `content`, `created_at`.
- Added `_evidence_id_for_memory(summary)` returning `ev_memory_<sha256[:12]>`.
- Extended `merge_evidence_pool` with `memory_summaries: list[MemoryDerivedSummary] | None = None` (no mutable default per Codex iter-1 P2).
- After upload + retrieval append: build `text_seen = {_normalize_for_dedup(s.span_text) for s in pool}`. For each memory summary, skip if normalized content already in `text_seen`. Otherwise append SourceSpan with tier=T3, url=`memory://{entry_id}`, span_start=0, span_end=len(content).
- Existing (url, text) dedup for upload + retrieval is preserved — no breaking change.

### `tests/v6/test_evidence_pool_memory.py` (NEW, 5 tests)
- `test_memory_summaries_appear_in_pool`: asserts evidence_id prefix, tier=T3, url=memory://{id}, span_start=0, span_end=len(content), text equals content.
- `test_memory_summaries_dedup_internal`: two memory entries with same normalized text → one in pool.
- `test_uploaded_takes_priority_over_memory`: upload + memory same text → memory dropped.
- `test_retrieval_takes_priority_over_memory`: retrieval + memory same text → memory dropped.
- `test_pool_with_all_three_kinds`: retrieval + upload + memory distinct → 3 entries with distinct tiers and `memory://m1` present.

## Verification

- `pytest tests/v6/test_evidence_pool_memory.py tests/v6/test_evidence_pool_merger.py`: 11/11 passing in 1.7s (5 new + 6 existing).
- No regression on existing merger tests.
- `polaris_v6.schemas.evidence_contract.SourceSpan` accepts tier="T3" (existing taxonomy).

## Risks for Codex Red-Team

1. **Production wiring deferred:** I-f14-004b will wire `WorkspaceMemoryStore.list_workspace(...) -> merge_evidence_pool(memory_summaries=...)`. This issue is the merger surface only.
2. **Tier T3 choice:** prior_run_summary is user-derived, not primary-source; T3 honest.
3. **§9.4:** no `try/except: pass`, no magic numbers, no `time.sleep`, no TODOs, no `from x import *`.
4. **CHARTER §3 LOC cap:** 149 net. Under 200.

## Output schema (mandatory)

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
