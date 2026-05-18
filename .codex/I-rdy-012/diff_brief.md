# Codex DIFF review — GH #508 (I-rdy-012): durable workspace-scoped memory with cited recall

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #508 (I-rdy-012) — `git diff origin/polaris...HEAD`
excluding `.codex/I-rdy-012/` and `outputs/audits/I-rdy-012/` (canonical
diff in `.codex/I-rdy-012/codex_diff.patch`, sha256 trailer). Implements the
Codex-APPROVE'd brief `.codex/I-rdy-012/brief.md` (brief APPROVE iter 1; 0
P0/P1/P2). **4 files, +436/-7.**

## 2. Recut provenance (front-loaded so you VERIFY)

This is a **recut** of PR #540 (`bot/I-rdy-012-durable-workspace-memory`),
which earned Codex brief APPROVE iter-1 + **diff APPROVE** for this exact
#508 implementation. PR #540 became unmergeable (43 commits stale; its
`.codex/I-rdy-012/` committed 63 KB / 208 KB raw Codex transcripts — a
verdict-only-rule violation). The recut re-applies #540's APPROVE'd source
onto current `polaris` HEAD `488d1fef`. `polaris`'s 43 commits touched
**none** of the 4 source files — every file is re-applied **verbatim** from
#540, zero divergence. This is the same code Codex already diff-APPROVE'd on
#540; confirm the verbatim re-application introduced no NEW P0/P1.

## 3. The change

- **`memory/sqlite_store.py`** (NEW, 250) — `SqliteWorkspaceMemoryStore`:
  durable SQLite-backed workspace memory. WAL + idempotent additive
  `_migrate_schema` (mirrors `queue/run_store`); DB path env
  `POLARIS_V6_MEMORY_DB`, default `state/v6_workspace_memory.sqlite`.
  `workspace_id` normalized identically on write + read.
  `derived_from_run_ids` round-trips → cited recall. Recall reuses the
  in-memory store's keyword-cosine scoring.
- **`api/memory.py`** — `_store` swapped `WorkspaceMemoryStore()` →
  `SqliteWorkspaceMemoryStore()`; HTTP contract unchanged.
- **`tests/v6/test_sqlite_workspace_memory.py`** (NEW, 10) +
  **`test_api_memory.py`** updated.

## 4. Verify

1. **Durability.** Memory persists to SQLite and a fresh store instance
   over the same DB path reads prior entries — confirm no in-memory-only
   state that would lose data on restart.
2. **Workspace isolation.** `workspace_id` normalized identically on write
   AND read; recall filtered by the normalized id — confirm no
   cross-workspace leak path (a leak is a P0 governance issue).
3. **Cited recall.** `derived_from_run_ids` round-trips (write → DB →
   recall) and surfaces in `MemoryRecallResult`.
4. **Migration safety.** `api/memory.py` swaps the store; the HTTP contract
   is unchanged; `_migrate_schema` is idempotent + additive (safe on an
   existing DB).
5. **No fabricated data.** Recall returns stored entries with real
   `derived_from_run_ids`; no invented citations.
6. **Recut fidelity.** The 4-file diff matches #540's APPROVE'd #508
   implementation verbatim.
7. **Scope.** The semantic (Chroma) recall upgrade is deferred and
   untouched — confirm not a P0/P1 that must block #508.

## 5. Files I have ALSO checked and they're clean

- `src/polaris_v6/memory/schema.py` — `MemoryEntry` / `MemoryKind` /
  `MemoryQuery` / `MemoryRecallResult`; consumed as-is, NOT modified.
- `src/polaris_v6/memory/store.py` — in-memory demo store; left intact;
  NOT modified.
- `src/polaris_v6/memory/chroma_store.py` — semantic store; deferred, NOT
  modified.

## 6. Smoke state

`ast.parse` 4/4. `pytest tests/v6/test_sqlite_workspace_memory.py` 10/10 +
`test_api_memory.py` 6/6 + 21 adjacent memory tests green (37 total).

## 7. Required output schema (§8.3.9)

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
