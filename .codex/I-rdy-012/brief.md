# Codex BRIEF review — GH #508 (I-rdy-012): durable workspace-scoped memory with cited recall

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. Stage

Review-stage **brief** — reviewing the *plan + recut rationale*. This is a
**recut** of an already-Codex-APPROVE'd implementation (see §1); the code
already exists on the branch. Confirm the recut is faithful and the scope
is honest. The diff gets a separate Codex diff review next.

## 1. Why this is a recut (front-loaded so you VERIFY)

#508 was implemented as PR #540 (`bot/I-rdy-012-durable-workspace-memory`).
That PR earned **Codex brief APPROVE iter-1 AND Codex diff APPROVE**. PR
#540 is now unmergeable:

1. **43 commits stale** behind `polaris`.
2. **Verdict-only-rule violation** — `.codex/I-rdy-012/` committed
   `codex_brief_verdict.txt` (63 KB) + `codex_diff_audit.txt` (208 KB) +
   `_iter_1` duplicates — raw Codex transcripts, not the ~130-byte slim
   YAML verdict. Raw transcripts must never reach `polaris` (CLAUDE.md
   §8.3; the raw-transcript secret-exposure surface is #535).

Decision (same as the #506/#507 recuts, Codex-advisor-confirmed): **recut**
onto a clean `bot/I-rdy-012` off current `polaris` HEAD `488d1fef`,
re-applying #540's APPROVE'd #508 source with proper slim verdict
artifacts. PR #540 is closed.

### 1.1 Recut fidelity

`polaris`'s 43 commits touched **none** of the 4 #540 source files
(`api/memory.py`, `memory/sqlite_store.py`, `tests/v6/test_api_memory.py`,
`tests/v6/test_sqlite_workspace_memory.py`). So every file was re-applied
**verbatim** via `git checkout origin/bot/I-rdy-012-durable-workspace-memory
-- <file>` — no manual re-anchoring, no divergence. This is the same code
Codex already brief-APPROVE'd + diff-APPROVE'd on #540.

## 2. Issue + acceptance

#508 (I-rdy-012, Phase 3.9): "F14 real durability + workspace isolation +
cited recall + migration from the in-memory demo store. Acceptance: memory
survives restart, is workspace-scoped, cited recall surfaces which past run
contributed; Codex APPROVE." Depends on I-rdy-007 (#503, CLOSED).

## 3. The change (4 files, +436/-7)

- **`memory/sqlite_store.py`** (NEW, 250) — `SqliteWorkspaceMemoryStore`,
  the durable replacement for the in-memory demo `WorkspaceMemoryStore`
  (`memory/store.py`, left intact). Memory survives a process restart;
  `workspace_id` is normalized identically on write + read (a mismatch is
  a P0 governance issue per CLAUDE.md); `derived_from_run_ids` round-trips
  so recall surfaces which past run contributed (cited recall). Storage
  mirrors `queue/run_store` (WAL, idempotent additive `_migrate_schema`);
  DB path env `POLARIS_V6_MEMORY_DB`, default
  `state/v6_workspace_memory.sqlite` (gitignored).
- **`api/memory.py`** — the F14 `/workspaces` memory endpoints swap
  `_store = WorkspaceMemoryStore()` → `SqliteWorkspaceMemoryStore()`; the
  HTTP contract is unchanged.
- **`tests/v6/test_sqlite_workspace_memory.py`** (NEW, 10 tests) +
  **`test_api_memory.py`** updated for the durable backend.

## 4. Scope boundary (Codex: confirm)

#508 = durability + workspace isolation + cited recall + migration off the
in-memory demo store. Recall keeps the in-memory store's **keyword-cosine**
scoring verbatim — #508's acceptance is durability/isolation/cited-recall,
NOT semantic recall. The semantic upgrade (`ChromaWorkspaceMemoryStore` +
a real sentence-transformers embedder) is left untouched and wired by a
separate deferred issue. Codex: confirm this boundary is honest and #508 is
not under-scoped for the issue's "cited recall" acceptance.

## 5. Smoke

`ast.parse` 4/4 clean. `PYTHONPATH='src;.' pytest
tests/v6/test_sqlite_workspace_memory.py` 10/10; `test_api_memory.py` 6/6;
21 adjacent memory tests (`test_workspace_memory`,
`test_chroma_workspace_memory`, `test_evidence_pool_memory`) green — 37
total, no regression.

## 6. Files I have ALSO checked and they're clean

- `src/polaris_v6/memory/schema.py` — `MemoryEntry` / `MemoryKind` /
  `MemoryQuery` / `MemoryRecallResult`; consumed as-is, NOT modified.
- `src/polaris_v6/memory/store.py` — the in-memory demo store; left intact
  (the keyword-cosine scoring is reused by the new store); NOT modified.
- `src/polaris_v6/memory/chroma_store.py` — the semantic store; deferred,
  NOT modified.

## 7. Output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Loose verdict prose is rejected — emit the schema.
