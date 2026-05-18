# Claude architect audit — GH #508 (I-rdy-012)

**Issue:** GH #508 (I-rdy-012) — Phase 3.9: durable workspace-scoped memory
with cited recall. Acceptance: memory survives restart, is workspace-scoped,
cited recall surfaces which past run contributed; Codex APPROVE.
**Branch:** `bot/I-rdy-012` off `polaris` HEAD `488d1fef`.
**Commit 1:** `df12d16c` — 4 files, +436/-7.
**Brief:** Codex brief review APPROVE iter 1 (0 P0/P1/P2, accept_remaining).

## 1. Recut provenance

Recut of PR #540 (`bot/I-rdy-012-durable-workspace-memory`). #540 earned
Codex brief APPROVE iter-1 + diff APPROVE but became unmergeable: 43 commits
stale, and its `.codex/I-rdy-012/` committed 63 KB / 208 KB raw Codex
transcripts as the verdict files (verdict-only-rule violation, CLAUDE.md
§8.3 / the #535 secret-exposure surface). The recut re-applies #540's
APPROVE'd #508 implementation onto current `polaris` HEAD with proper slim
artifacts; PR #540 is closed. `polaris`'s 43 commits touched **none** of
the 4 source files, so all 4 were re-applied verbatim — no divergence, no
manual re-anchoring.

## 2. What shipped

F14 Phase 3.9 — replace the in-memory demo `WorkspaceMemoryStore` with a
durable, workspace-scoped `SqliteWorkspaceMemoryStore`:
- `memory/sqlite_store.py` (NEW, 250) — SQLite-backed store.
- `api/memory.py` — `/workspaces` memory endpoints back onto the durable
  store; HTTP contract unchanged.
- `tests/v6/test_sqlite_workspace_memory.py` (NEW, 10 tests) +
  `test_api_memory.py` updated.

## 3. Per-finding verification (against the APPROVE'd brief)

- **VERIFIED — memory survives restart.** `SqliteWorkspaceMemoryStore`
  persists to a SQLite DB (`POLARIS_V6_MEMORY_DB`, default
  `state/v6_workspace_memory.sqlite`); storage mirrors `queue/run_store`
  (WAL, idempotent additive `_migrate_schema`). A new store instance over
  the same DB path reads prior entries — `test_sqlite_workspace_memory.py`
  exercises a fresh-instance round-trip.
- **VERIFIED — workspace-scoped.** `workspace_id` is normalized identically
  (`_normalize_workspace_id` — strip+lower) on write AND read; recall is
  filtered by the normalized id. A cross-workspace leak would be a P0
  governance issue; the test suite includes a workspace-isolation case.
- **VERIFIED — cited recall.** `derived_from_run_ids` round-trips through
  the store (JSON column) and is surfaced in `MemoryRecallResult`, so
  recall shows which past run contributed.
- **VERIFIED — migration off the demo store.** `api/memory.py` swaps
  `WorkspaceMemoryStore()` → `SqliteWorkspaceMemoryStore()`; the in-memory
  `memory/store.py` is left intact (its keyword-cosine scoring is reused),
  the HTTP contract is unchanged (`test_api_memory.py` 6/6 green on the
  durable backend).
- **VERIFIED — scope boundary honest.** Recall keeps the keyword-cosine
  scoring verbatim — #508's acceptance is durability + isolation + cited
  recall, NOT semantic recall. The Chroma semantic upgrade
  (`ChromaWorkspaceMemoryStore`) is untouched and deferred. The issue body
  asks for "cited recall", which is delivered; semantic ranking is not in
  #508's acceptance text.

## 4. Smoke

`ast.parse` 4/4. `pytest tests/v6/test_sqlite_workspace_memory.py` 10/10 +
`test_api_memory.py` 6/6 + 21 adjacent memory tests (`test_workspace_memory`,
`test_chroma_workspace_memory`, `test_evidence_pool_memory`) green — 37
total, no regression.

## 5. Codex iteration trail

- PR #540 (recut-from): brief APPROVE iter-1 + diff APPROVE.
- Recut brief: Codex brief review APPROVE iter 1 — 0 P0/P1/P2,
  accept_remaining.

## 6. Verdict

Faithful recut of #540's Codex-APPROVE'd #508 implementation onto current
`polaris` HEAD (all 4 files verbatim, zero divergence). Workspace memory is
now durable (survives restart), workspace-scoped (normalized id on
write+read), and surfaces cited recall via `derived_from_run_ids`; the
demo-store migration keeps the HTTP contract stable. Ready for Codex diff
review.
