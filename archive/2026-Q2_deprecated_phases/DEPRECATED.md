# Deprecated: `src/phases/` — pre-polaris_graph phase-based pipeline

**Archived:** 2026-04-17 (HONEST-REBUILD Phase 1d)
**Plan:** C:/Users/msn/.claude/plans/lovely-finding-firefly.md
**Git move commit:** branch `PL-honest-rebuild-phase-1`

## What this was

The `src/phases/` directory held the original 13-phase POLARIS pipeline
architecture (p00_init through p12_finalize). It predates the
`src/polaris_graph/` LangGraph-based architecture and was superseded by
`graph_v2.py` during the v3 rewrite.

## Why archived

MEMORY.md (user's persistent project memory) records this as "LEGACY":

> Two Systems: `src/phases/` = LEGACY. `src/orchestration/` +
> `src/agents/` = PRODUCTION (entry: graph.py::run_research())

The PG_LB_SA_02 content audit (2026-04-17,
`loopback/audit/PG_LB_SA_02_CONTENT_AUDIT.md`) identified four
coexisting half-built architectures in the repo. The honest-rebuild
plan (Phase 1d) formally archives them so sprint effort does not bleed
back into dead codebases. See plan's "Architecture cleanup (formal
deprecation)" section.

## Why only `src/phases/` was archived in this pass

The plan also lists `src/orchestration/` and `polaris_graph v1` for
archival, but both have active dependency chains that must be untangled
first:

- `src/orchestration/iteration_manager.py` is imported by 13 files in
  `src/agents/`
- `src/polaris_graph/agents/searcher.py` imports from
  `src.agents.search_agent` (which cascades into orchestration)
- Many scripts in `scripts/` import from `src.polaris_graph.graph` (v1
  entry point, distinct from `graph_v2.py`)

Cutting those dependencies is larger-scope work than a single Phase 1d
step. Deferred to a later honest-rebuild phase (tracked in
`docs/todo_list.md`).

## How to restore (if needed)

```
cd C:/POLARIS
git mv archive/2026-Q2_deprecated_phases/src_phases src/phases
```

Git history preserves blame and commit lineage. No content was deleted.
