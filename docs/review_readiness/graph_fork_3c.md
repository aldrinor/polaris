# Graph-Version Fork — FREEZE + REMOVAL-GATES (3c)

**Scope:** Review-readiness inventory only. Nothing deleted, no behavior changed.
This document FREEZES the `PG_GRAPH_VERSION` graph fork and defines the gates
that must ALL pass before any `graph*.py` version is removed.

**Baseline:** collection `16738/11`.

---

## 1. STATUS — FROZEN

The graph fork (`graph.py` / `graph_v2.py` / `graph_v3.py` / `pipeline_a_ui_adapter`
via `PG_GRAPH_VERSION`) is **FROZEN** for this review — **documented, not deleted.**

The brief described a 3-way fork. It is in fact a **5-way selector** (v4 / v3 / v2 / v1
+ safe fallback), and a **v4 pipeline-A-backed path is now the production DEFAULT.**

- **Default = v4** (`pipeline_a_ui_adapter.build_and_run_v4`, pipeline-A-backed) on the
  production `live_server` path. **Unset `PG_GRAPH_VERSION` => v4.**
- The library `__init__.py` selector defaults to **v1**, but it is **NOT on the
  production path** (dormant — see §2).

### Selector routing (production: `scripts/live_server.py:555-570`, `_run_pipeline`)

Reads `os.getenv("PG_GRAPH_VERSION", "v4")`:

| Selector value | Routes to |
|---|---|
| `v4` (default / unset) | `pipeline_a_ui_adapter.build_and_run_v4` |
| `v3` | `graph_v3.build_and_run_v3` |
| `v2` | `graph_v2.build_and_run` |
| `v1` | `graph.build_and_run` |
| any-other-value | **v4 safe fallback** (logs a warning) |
| `PG_V2_ENABLED=1` | forces `graph_v2` — a **second, independent** selector env var (default `'0'`, read directly, not in `config_defaults`) |

The `PG_V2_ENABLED=1` branch is evaluated **before** `v1` and independently of
`PG_GRAPH_VERSION`, so `PG_V2_ENABLED=1` overrides `PG_GRAPH_VERSION=v1`.

### Second selector site (DORMANT — not production)

`src/polaris_graph/__init__.py:37-41` reads `resolve("PG_GRAPH_VERSION")`
(registry default `'v1'` — `config_defaults.py:365`) and distinguishes only
`v3 -> graph_v3` else `v1 -> graph.build_and_run`. This entry point
(`src.polaris_graph.run_research`) has **no runtime caller** — production scripts
import `src.orchestration.graph.run_research`, a different module. The two selector
sites **DISAGREE** on the default (`live_server`=v4, `__init__.py`=v1) and on routing
breadth.

---

## 2. USAGE INVENTORY

### Which selector is production
`scripts/live_server.py:555-570`. Docker `CMD serve` -> `live_server` always resolves
to **v4** unless `PG_GRAPH_VERSION` is explicitly overridden (it never is — see below).

### Is any non-default (v2/v3/v1) used anywhere?
**NO.** `nondefault_usage_found = false` at runtime, anywhere:

- No Dockerfile / entrypoint / shell / CI / `.env` / config sets `PG_GRAPH_VERSION`
  or `PG_V2_ENABLED` (grep over `*.sh`, `Dockerfile*`, `*.yml`, `*.yaml`, `*.env`
  returns nothing).
- `tests/v3/test_graph.py:189-196` only asserts env-var round-trip — **not** real routing.
- `tests/polaris_graph/test_b102_graph_v4.py` is a source-assertion test that greps
  `live_server` for the v4 literal.
- External consumers of `graph_v2` / `graph_v3` / `build_and_run_v4` symbols =
  **ONLY the two selector sites** (`live_server.py:557,559,561,570` and `__init__.py:39`).
  No other runtime module imports `graph_v2` / `graph_v3` / `ResearchStateV2` / `V3State` /
  `build_and_run_v4`.

Production therefore always runs **v4**; v1/v2/v3 are reachable only by a manual
env override that no deployment performs.

### State classes

| Version | State class | Location | Persistence |
|---|---|---|---|
| v1 | `ResearchState` (TypedDict) | `src/polaris_graph/state.py:469` | SQLite checkpointer (`checkpoint_manager.get_checkpointer`, `graph.py:1421-1437`, `PG_CHECKPOINT_ENABLED`) + final JSON `outputs/polaris_graph/{vector_id}.json` |
| v2 | `ResearchStateV2` (TypedDict) | `src/polaris_graph/graph_v2.py:71` | **NO checkpointer** (`graph.compile()` @ `graph_v2.py:678`); final JSON dump `graph_v2.py:840-841` |
| v3 | `V3State` (TypedDict) | `src/polaris_graph/state_v3.py:15` | evidence content off-state in side-channel `evidence_store`; **NO checkpointer** (`graph_v3.py:705`); final JSON `PG_OUTPUT_DIR/{vector_id}.json` `graph_v3.py:843-851` |
| v4 | **NO own State class** | `pipeline_a_ui_adapter.build_and_run_v4` (`py:187`) delegates to `scripts.run_honest_sweep_r3.run_one_query` | final JSON dump `pipeline_a_ui_adapter.py:335` |

Dead artifact: a commented-out `ResearchStateV2` sketch at `state.py:375` — left as-is.

**Persistence note:** only **v1** uses the LangGraph SQLite checkpointer. v2 / v3 / v4
only write a final result JSON. This matters for Gate (c) — saved-state resume fixtures
only exist meaningfully for v1.

---

## 3. DEPRECATION NOTICE

The non-default forks — **v1 (`graph.py`), v2 (`graph_v2.py`), v3 (`graph_v3.py`),
and `PG_V2_ENABLED`** — are hereby marked **DEPRECATED**.

**Removal is a SEPARATE, owner-driven project (codex Q1 decision).** This review does
**not** delete them. Deprecation here means: no new work targets these paths; they exist
only for migration compatibility; they are slated for removal once §4 gates pass.

---

## 4. REMOVAL GATES (codex-specified)

**ALL of the following must pass before ANY `graph*.py` version is deleted:**

- **(a) Full-graph deterministic oracle** covering EVERY `PG_GRAPH_VERSION` selector,
  including **unset** and **invalid** (safe-fallback) values, plus the `PG_V2_ENABLED=1`
  branch.
- **(b) Byte-identical RACE + faithfulness** across repeated replays per selector.
- **(c) Saved-state migration + resume fixtures** for `ResearchStateV2` and `V3State`
  (and v1's checkpointed `ResearchState`).
- **(d) External-consumer / deployment inventory**, including env overrides
  (`PG_GRAPH_VERSION`, `PG_V2_ENABLED`).
- **(e) Defined replacement + deprecation window + rollback switch + owner sign-off.**
- **(f) Shadow / canary replay evidence** on representative persisted states.

---

## 5. OUT OF SCOPE FOR THIS REVIEW

The **current deterministic oracle covers only the outline-agent path, NOT the graph
path.** Gate (a) is therefore unmet. Consequently, **deletion of any `graph*.py` version
is OUT OF SCOPE for this review.** This document freezes and inventories the fork; it
does not remove it.
