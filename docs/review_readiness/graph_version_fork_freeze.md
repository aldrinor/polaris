# Graph-Version Fork — FREEZE + DOCUMENT (Q1)

**Status: FROZEN. This is inventory only. No file was deleted; no behavior was changed.**

Codex Q1 decision: freeze and document the live multi-way graph fork selected by
`PG_GRAPH_VERSION`. Do not delete, do not refactor, do not change any dispatch
behavior. This document is the authoritative map of the fork as it exists today.

## 1. The fork is now 5-way (v4/v3/v2/v1), not the 3-way in the brief

The Q1 brief described a 3-way fork (`graph.py` / `graph_v2.py` / `graph_v3.py`).
The live code has since grown a **v4** path (`pipeline_a_ui_adapter.build_and_run_v4`,
pipeline-A-backed) that is now the **production default**. The three legacy graphs
still exist and remain explicitly selectable. Inventory below reflects reality.

## 2. Two independent selector sites (they disagree)

There are TWO places that read `PG_GRAPH_VERSION`, with **different default and
different routing**. This divergence is load-bearing and is preserved as-is.

### 2a. Production selector — `scripts/live_server.py:555-570`
This is the real product path (`Dockerfile` `CMD ["serve"]` →
`scripts/docker_entrypoint.sh:28` → `uvicorn scripts.live_server:app` →
`_run_pipeline`).

```
graph_version = os.getenv("PG_GRAPH_VERSION", "v4")   # default v4
  "v4"            -> pipeline_a_ui_adapter.build_and_run_v4   (DEFAULT / production)
  "v3"            -> graph_v3.build_and_run_v3
  PG_V2_ENABLED=1 -> graph_v2.build_and_run                  (OR graph_version=="v2")
  "v2"            -> graph_v2.build_and_run
  "v1"            -> graph.build_and_run
  <anything else> -> pipeline_a_ui_adapter.build_and_run_v4  (safe fallback, warns)
```
Note: `PG_V2_ENABLED` is a second, independent selector env var (read directly,
default `"0"`; it is NOT in `config_defaults.py`). If set to `"1"` it forces v2
regardless of `PG_GRAPH_VERSION` (as long as the value is not `"v4"`/`"v3"`, which
are checked first).

### 2b. Library selector — `src/polaris_graph/__init__.py:37-41`
`run_research()` reads `resolve("PG_GRAPH_VERSION")` (registry default `"v1"` from
`config_defaults.py:365`) and routes only 2 ways:
```
  "v3"     -> graph_v3.build_and_run_v3
  <else>   -> graph.build_and_run   (v1)   # includes v4/v2/unset -> v1
```
This entry point is **not on the production path**. No runtime caller imports
`src.polaris_graph.run_research` (the `run_research` used by scripts/full_cycle.py,
scripts/run_s1v1_full.py comes from a *different* module, `src.orchestration.graph`).
It is effectively dormant but is left untouched under the freeze.

## 3. Valid selector values (production selector, live_server)

| value           | routes to                              | notes |
|-----------------|----------------------------------------|-------|
| `"v4"`          | `pipeline_a_ui_adapter.build_and_run_v4` | DEFAULT (unset ⇒ v4) |
| unset           | v4                                     | via `getenv(..., "v4")` |
| `"v3"`          | `graph_v3.build_and_run_v3`            | |
| `"v2"`          | `graph_v2.build_and_run`               | |
| `"v1"`          | `graph.build_and_run`                  | |
| any other value | v4 (fallback, logs a warning)          | |
| `PG_V2_ENABLED="1"` | `graph_v2.build_and_run`           | second selector; forces v2 unless value is v4/v3 |

Library selector (`__init__.py`) valid values: `"v3"` ⇒ v3, everything else
(default `"v1"`) ⇒ v1.

## 4. Default / production version

**v4** (`pipeline_a_ui_adapter.build_and_run_v4`, pipeline-A-backed) via the
live_server selector. This is what a UI/Docker user gets with no env override.
The v4 adapter delegates to `scripts.run_honest_sweep_r3.run_one_query`; it holds
no state TypedDict of its own.

## 5. Saved-state schemas (persistence)

| version | State class | file | checkpointer | final output |
|---------|-------------|------|--------------|--------------|
| v1 | `ResearchState` (TypedDict) | `state.py:469` | SQLite via `checkpoint_manager.get_checkpointer` (`graph.py:1421-1437`, `PG_CHECKPOINT_ENABLED`) | `outputs/polaris_graph/{vector_id}.json` |
| v2 | `ResearchStateV2` (TypedDict) | `graph_v2.py:71` | none — `graph.compile()` w/o saver (`graph_v2.py:678`) | JSON dump `graph_v2.py:840-841` |
| v3 | `V3State` (TypedDict) | `state_v3.py:15` (evidence content off-state in side-channel `evidence_store`) | none — `graph.compile()` (`graph_v3.py:705`) | `PG_OUTPUT_DIR/{vector_id}.json` `graph_v3.py:843-851` |
| v4 | none (delegates to pipeline A) | `pipeline_a_ui_adapter.py:187` | pipeline-A internal | JSON dump `pipeline_a_ui_adapter.py:335` |

Only v1 uses the LangGraph SQLite checkpointer (crash-recovery/resume). v2 and v3
compile with no checkpointer and only write a final result JSON. A commented-out
`ResearchStateV2` sketch also exists at `state.py:375` (dead comment, left as-is).

## 6. Non-default usage in prod/CI/scripts/docs — NONE at runtime

- No `Dockerfile`, `docker_entrypoint.sh`, shell script, CI YAML, `.env`, or config
  file sets `PG_GRAPH_VERSION` or `PG_V2_ENABLED` to a non-default value. Grep over
  `*.sh`/`Dockerfile`/`*.yml`/`*.yaml` returned zero setter hits.
- The only runtime **reads** are the two selector sites (§2).
- `tests/v3/test_graph.py:189-196` sets `PG_GRAPH_VERSION=v3` but only asserts the
  env-var round-trips (`getenv == "v3"`); it does not exercise real routing.
- `tests/polaris_graph/test_b102_graph_v4.py` is a **source-assertion** test: it
  greps `live_server.py` to confirm the literal `os.getenv("PG_GRAPH_VERSION","v4")`.
- Docs (`docs/pipeline_audit_context/*`, `outputs/**`, `.codex/**`) reference the
  fork but set nothing.

Conclusion: production always runs v4 via the default. v1/v2/v3 are reachable only
by manually exporting the env var; nothing in the tracked repo does so.

## 7. External consumers of graph_v2 / graph_v3 / v4 symbols

Only the two selector sites import these build_and_run symbols:
- `scripts/live_server.py:557,559,561,570` (v4/v3/v2 + fallback)
- `src/polaris_graph/__init__.py:39` (v3)

No other runtime module imports `graph_v2`, `graph_v3`, `ResearchStateV2`, `V3State`,
or `build_and_run_v4`. `graph.build_and_run` (v1) is imported by both selectors and
by `__init__.py`.

## Freeze contract
All four graph modules, both state modules, the `pipeline_a_ui_adapter`, the two
selector sites, and the `config_defaults['PG_GRAPH_VERSION']='v1'` registry entry
are FROZEN in place. Any consolidation is a later, separate decision.
