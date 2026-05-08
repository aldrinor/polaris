# Claude architect audit — I-f14-004

**Issue:** Memory-as-corpus for new queries
**Branch:** bot/I-f14-004
**Canonical-diff-sha256:** 4f075d31082ed6fbf131f49cd4756cdca43a21bc0f25bec2fd658a1643e1239d
**Brief verdict:** APPROVE iter 2 (after Codex iter-1 P1 dedup-semantics fix)
**Diff verdict:** pending Codex iter 1

## Substrate honesty
- New `MemoryDerivedSummary` + `memory_summaries` param on `merge_evidence_pool`.
- Honest dedup: memory dedups against the WHOLE pool by normalized text only, preserving upload > retrieval > memory priority via append order.
- Production wiring (graph_v4 → workspace_memory.list_workspace → merger) deferred to follow-up I-f14-004b.

## §9.4 backend hygiene
- No `try/except: pass`, no magic numbers, no `time.sleep`, no TODOs, no `from x import *`. No mutable default arg (uses `None` + `or []`).

## CHARTER §3 LOC cap
- 149 net (merger +43 -5, test +106).

## Tests
- `pytest tests/v6/test_evidence_pool_memory.py tests/v6/test_evidence_pool_merger.py`: 11/11 passing in 1.7s.

## Verdict
APPROVE.
