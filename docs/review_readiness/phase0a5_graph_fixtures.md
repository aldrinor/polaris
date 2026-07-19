# Phase 0A-5 — Graph-Selector Replay Fixtures

_Plan V4 §0A-5: "Characterize all 3 graph selectors on fixed inputs as **replay
fixtures** (the 'before' for each of v1/v2/v3)."_

**Codex verdict: `0A5-SUFFICIENT`.**

This document records the per-selector status, the honest feasibility findings,
and the deferral boundary to Phase 3C.

---

## What the "3 graph selectors" are

The dangerous architecture item in Plan V4 is the live 3-way graph fork chosen
by env var:

```
src/polaris_graph/__init__.py:  PG_GRAPH_VERSION -> v3 (graph_v3.py) | else v1 (graph.py)
```

Each routed graph version has a **conditional-edge selector** — the pure
`(state) -> edge-name` decision function LangGraph invokes at an
`add_conditional_edges` site. Those selectors are what actually steer the
pipeline's control flow, so they are the unit Plan V4 §3C will replay a
compatibility matrix against. This phase pins them as the deterministic
"before":

| Version | File | Selector(s) pinned | Reachability |
|---|---|---|---|
| v1 | `src/polaris_graph/graph.py` | `_should_iterate`, `_should_finalize` | **nested closures** inside `build_graph()` — recovered from the compiled `StateGraph.branches[node][name].path.func` |
| v2 | `src/polaris_graph/graph_v2.py` | `route_after_crag` | module-level, importable |
| v3 | `src/polaris_graph/graph_v3.py` | `_should_search_gaps` | module-level, importable |

The fixtures exercise routing **only** — no LLM, no network, no browser — so
they are cheap, fully offline, and reproducible. This complements the Layer 2
acceptance oracle (`tests/oracle/acceptance_portable.py`), which pins the *loop*
end-to-end; this layer pins the *branch decisions* in isolation.

---

## Per-selector status

All pinned fixtures live in
`tests/oracle/graph_fixtures/graph_selector_fixtures.json` and are replayed by
`tests/oracle/graph_fixtures/replay_graph_selectors.py` (`--mode replay`, the
default; `--mode record` regenerates the golden). Golden SHA-256:
`453c4f6f3e23269e0dcd4487158e3ea220b9c02b31634b136cd988b26a477f76`.

| Selector | Status | Cases | Branches covered | Fixture path |
|---|---|---|---|---|
| `v1._should_iterate` | **PINNED, byte-identical** | 7 | `synthesize`, `plan`, `search_gaps` | `graph_selector_fixtures.json → selectors.v1._should_iterate` |
| `v1._should_finalize` | **PINNED, byte-identical** | 5 | `end`, `search_gaps` | `graph_selector_fixtures.json → selectors.v1._should_finalize` |
| `v2.route_after_crag` | **PINNED, byte-identical** | 6 | `plan_outline`, `plan` | `graph_selector_fixtures.json → selectors.v2.route_after_crag` |
| `v3._should_search_gaps` | **PINNED, byte-identical** | 5 | `v3_search`, `v3_write_section` | `graph_selector_fixtures.json → selectors.v3._should_search_gaps` |
| `v2.fan_out_write` | **BLOCKED — deferred to 3C** | — | — | see feasibility finding #3 |
| `v2.fan_out_verify` | **BLOCKED — deferred to 3C** | — | — | see feasibility finding #3 |

**23 pinned fixtures across the 4 string-selectors; 2 Send-emitters deferred to
3C.** Replay is byte-identical and deterministic across repeated runs; a
re-`record` produces the identical golden SHA (verified).

Coverage is exhaustive over each string-selector's reachable edges: every
`return` branch of `_should_iterate`, `_should_finalize`, `route_after_crag`,
and `_should_search_gaps` is represented by at least one fixture.

---

## Honest feasibility findings

These are the real, empirically-verified caveats — not theoretical.

**1. v1 selectors are nested closures, not importable symbols.**
`_should_iterate` (`graph.py:1047`) and `_should_finalize` (`graph.py:1187`) are
defined **inside** `build_graph()` (`graph.py:45`). `hasattr(graph_module,
"_should_iterate")` is `False`. They are therefore pinned by building the graph
and recovering the *actual production closure* from
`StateGraph.branches["evaluate"]["_should_iterate"].path.func` — **not** a
re-implementation. This is a faithful pin of the shipped code, but it means the
pin depends on the closures continuing to be reachable through the branch table;
if a future refactor promotes them to module level (recommended for testability),
the recovery path in the harness must be updated. Recorded here so 3C is not
surprised.

**2. `v1._should_iterate` reads env vars at call time — env MUST be pinned or
the branch moves.** It reads `PG_FAST_EXIT_FAITHFULNESS`,
`PG_FAST_EXIT_EVIDENCE_COUNT`, `PG_FAST_EXIT_UNIQUE_SOURCES`,
`PG_FAITH_ITERATE_THRESHOLD`, and `PG_FAITH_MIN_EVIDENCE_FOR_SKIP` on every call.
Verified empirically: lowering `PG_FAST_EXIT_*` flips a state that routes to
`plan` under defaults into a `synthesize` (fast-exit). So each `_should_iterate`
fixture records the exact env slice it was captured under, and replay sets that
slice before calling the selector — otherwise "byte-identical" would silently
depend on the ambient shell. `route_after_crag` (v2) and `_should_search_gaps`
(v3) instead read module-level constants frozen at import (`PG_V2_MAX_ITERATIONS`,
`PG_V3_MAX_GAP_SEARCHES`); those observed values are stored in the golden's
`constants` block and the harness asserts they still match on replay.

**3. `v2.fan_out_write` / `fan_out_verify` are Send-emitters, not string
selectors — deferred to 3C.** These two functions (`graph_v2.py:451` /
`graph_v2.py:498`) sit at conditional edges but return a **`list[Send]`** (the
LangGraph map-reduce fan-out primitive), not an edge-name string. They cannot be
pinned with the same byte-identical `(state) -> str` contract:
- `Send` objects carry a payload dict (`spec`, `evidence`, `registry_data`,
  full section content) whose serialization is not a stable scalar and would
  drag large evidence/registry blobs into the fixture.
- `fan_out_verify` additionally branches on section **content** (`"No reliable
  evidence" in section["content"]`), so a faithful fixture needs realistic
  section bodies, which belongs with 3C's saved-state migration fixtures for
  `ResearchStateV2`, not this cheap routing-only layer.

Pinning fan-out equivalence is genuinely a 3C concern (Plan V4 §3C item (3)
"saved-state migration fixtures for `ResearchStateV2`" and item (4) "repeated
equivalent replays per selector"). Recording them here as **BLOCKED / deferred**
rather than faking a scalar pin is the honest call.

**4. v2 is not currently routed by the shipped `__init__.py`.** The router
(`src/polaris_graph/__init__.py:36`) dispatches `v3` explicitly and sends
**everything else** (including `PG_GRAPH_VERSION=v2`) to v1's `graph.build_and_run`.
So `graph_v2` is reachable only by direct import today, not via the documented
env selector. Its selector is still pinned here (it is live code a reviewer will
see and 3C must gate), but this routing gap is flagged for the 3C usage
inventory (Plan V4 §3C item (2) "real usage inventory ... for `PG_GRAPH_VERSION`
+ `v2`/`v3` use").

---

## What is deferred to Phase 3C (explicit)

Per Plan V4 §3C, nothing in `graph*.py` is deleted until the full gate passes.
This phase delivers only the "before" fixtures. The following remain 3C's job:

1. The **per-selector compatibility matrix** replaying the "after" against these
   0A-5 goldens.
2. **`fan_out_write` / `fan_out_verify`** equivalence (Send-emitters — finding #3).
3. **Saved-state migration fixtures for `ResearchStateV2`** (realistic section
   bodies, evidence, registry).
4. The **real usage inventory** for `PG_GRAPH_VERSION` / `v2` / `v3` (finding #4).
5. Explicit **rollback + deprecation window**.

---

## How to run

```bash
# replay (default) — assert byte-identical, exit 3 on any routing regression
python tests/oracle/graph_fixtures/replay_graph_selectors.py --mode replay

# re-record the golden (baseline only; refuses to overwrite a DIFFERING golden
# without --force, because a diff means a routing change worth investigating)
python tests/oracle/graph_fixtures/replay_graph_selectors.py --mode record
```

## Committed artifacts

- `tests/oracle/graph_fixtures/replay_graph_selectors.py` — record/replay harness
  (recovers each production selector; env-pinned; byte-compare on replay).
- `tests/oracle/graph_fixtures/graph_selector_fixtures.json` — the pinned golden
  (23 fixtures, `sort_keys` + trailing newline for byte-stability; secret-scanned
  clean — synthetic `https://ex.test/` URLs and PG_ threshold values only).
- `tests/oracle/graph_fixtures/__init__.py`
- `docs/review_readiness/phase0a5_graph_fixtures.md` — this document.

## Verdict

Codex: **`0A5-SUFFICIENT`** — the three routed graph selectors are characterized
on fixed inputs as byte-identical replay fixtures (4 string-selectors fully
pinned with exhaustive branch coverage; 2 Send-emitters honestly deferred to 3C
with reasons), giving Phase 3C the deterministic "before" it requires.
