# Public-Compatibility Inventory (Plan V4 · Item 2A)

**Audience:** independent Telus code reviewer
**Scope:** everything in `src/polaris_graph` (and adjacent `scripts/`) that a **rename or delete** could silently break, because the reference is *not* an ordinary Python `import`/attribute access that a static analyzer or IDE "rename symbol" would follow.
**Status:** analysis only. No runtime code was modified. This inventory MUST run and be cleared **before** any rename/delete pass in the worklist.

**Worktree note.** This document lives in the `deliverables` worktree (`/home/polaris/wt/deliverables`, package `src.polaris_graph`). The rename worklist it cross-references,
`NAME_RENAME_WORKLIST_validated.tsv`, is not present in this worktree; it was read from the sibling checkout `/home/polaris/polaris_project/NAME_RENAME_WORKLIST_validated.tsv` (346 rows, same package). All `src/polaris_graph/...` line numbers below are from this worktree and were read/grepped directly.

---

## TL;DR — the load-bearing conclusion

> **"Zero static importers" is NOT sufficient to declare a symbol safe to rename.**

A symbol can have zero `from x import y` / `import x` references and still be reached through **five** non-static channels, every one of which is present in this codebase:

1. **String-path dynamic dispatch** — module paths stored as *strings* (`STAGE_TYPE_REGISTRY`), invisible to grep-for-import.
2. **Environment-variable control surface** — 1,500+ `PG_*` reads; the *string literal* is the contract with operators/`.env`/Helm/compose.
3. **Persisted state keys** — LangGraph checkpoint SQLite stores TypedDict *field keys* and *graph node-name strings*, plus a `pg_{vector_id}` thread-id prefix.
4. **String-keyed dispatch/config tables** — gate-config dicts in `scripts/dr_benchmark/run_gate_b.py` inject env keys by name.
5. **External HTTP surface** — FastAPI route path literals and `Literal[...]` wire enums that clients depend on.

The rest of this document enumerates each channel with `file:line` evidence, then maps the 210 proposed `RENAME` rows onto them.

---

## 1. Dynamic imports

Greps run: `importlib`, `import_module`, `__import__`, `pkgutil`, `getattr(<module>…)`, `entry_points`, `console_scripts`, string-literal module paths.

### 1.1 `STAGE_TYPE_REGISTRY` — string-path module dispatch table (HIGH interest)

`src/polaris_graph/pipeline_definition.py:47-59`

```python
# Maps stage types to their module paths for dynamic import
STAGE_TYPE_REGISTRY: dict[str, str] = {
    "plan":             "src.polaris_graph.agents.planner",
    "search":           "src.polaris_graph.agents.searcher",
    "storm_interviews": "src.polaris_graph.agents.storm_interviews",
    "analyze":          "src.polaris_graph.agents.analyzer",
    "verify":           "src.polaris_graph.agents.verifier",
    "evaluate":         "src.polaris_graph.graph",
    "synthesize":       "src.polaris_graph.agents.synthesizer",
    "search_gaps":      "src.polaris_graph.agents.synthesizer",
    "custom_llm":       "src.polaris_graph.graph",
    "filter":           "src.polaris_graph.graph",
    "merge":            "src.polaris_graph.graph",
}
```

These are **module paths written as strings** (confirmed: `grep -oE '"src\.polaris_graph\.[a-z_.]+"'` returns exactly these 11 lines and nothing else in the package). If `agents/planner.py` → `agents/plan_agent.py` is renamed, **grep-for-import and IDE "rename symbol" will NOT touch this table** — the string just goes stale.

**Mitigating fact (verify before acting):** `grep -rn STAGE_TYPE_REGISTRY` across `src/`, `scripts/`, `tests/`, `web/` returns **only its own definition line**. There is currently **no runtime consumer** that calls `importlib.import_module()` on these strings — the comment says "for dynamic import" but the loader is not wired in this worktree. So today this is an *aspirational / dead* dispatch table.
→ **Reviewer implication:** it is safe *only because it is dead*. It is a latent trap: if the pipeline-editor compiler is ever wired up (the docstring at `pipeline_definition.py:1-14` describes exactly that), a prior naive module rename becomes a silent runtime `ModuleNotFoundError`. Treat the module-path strings as a **future dynamic surface**: either delete the table in the same pass as any `agents/*` rename, or keep the strings in lock-step.

### 1.2 Other dynamic-import primitives — all benign

- `src/polaris_graph/llm/openrouter_client.py:102` — `__import__("threading").Lock()`. Stdlib module name; not a rename target.
- `src/polaris_graph/tools/package_installer.py:86` — `__import__(base_name.replace("-", "_"))`. Imports **third-party** packages by user-supplied name; not an internal symbol.
- `src/polaris_graph/tools/code_executor.py:70,80,99,202` — `"importlib"`, `"pkgutil"`, `"__import__"`, `"pickle"` appear inside a **sandbox blocklist** (denied-import list for executed code), not as live imports.
- **No** `importlib.import_module`, `pkgutil.iter_modules`, `entry_points`, or `console_scripts` anywhere in `src/polaris_graph` or `pyproject.toml`. `pyproject.toml` defines **no** `[project.scripts]` console entry points.
- `getattr(<module>, …)` / `globals()[...]` dynamic function lookup: **none found.** Every `getattr(...)` hit (e.g. `nodes/journal_only_filter.py`, `nodes/weighted_corpus_gate.py`, `synthesis/consolidation_nli.py`) reads a **data attribute off an instance** (`getattr(row, "url", "")`), not a module/function by name — safe under rename because the attribute names are model fields, addressed separately below.

**Category verdict:** the only dynamic-import risk is `STAGE_TYPE_REGISTRY` (§1.1), and it is currently dead. No live `importlib`/`getattr`-by-name dispatch exists.

---

## 2. String-based references (class/function/module names as strings)

### 2.1 LangGraph node-name strings — dispatch + persisted (see §3)

`src/polaris_graph/graph.py:1242-1274`, `graph_v2.py:630-676`, `graph_v3.py:680-703` register nodes by **string name**:

```python
graph.add_node("plan", _plan)          # graph.py:1242
graph.add_node("search", _search)      # graph.py:1243
graph.add_edge("plan", "search")       # graph.py:1254
graph.set_entry_point("plan")          # graph.py:1253
...
Send("write_one_section", {...})       # graph_v2.py:457
graph.add_node("v3_search", search_node)  # graph_v3.py:681
```

The Python *function* (`_plan`, `search_node`) can be renamed freely — the edges reference the **string** `"plan"`, not the function. But the **string names themselves** are a dual control surface: (a) internal edge wiring (rename all occurrences together within one file), and (b) **persisted into checkpoints** (§3.2). They are also mirrored in `StageType` enum values (§4.1).

### 2.2 Gate-config env-key dispatch tables

`scripts/dr_benchmark/run_gate_b.py` builds env-injection dicts keyed by the **string** env-var name:

```python
"PG_S15_CORROBORATED_HONEST_LABEL": "1",   # run_gate_b.py:643
"PG_CONTRADICTION_RENDER_HONEST": "1",     # run_gate_b.py:654
# ...and the same names re-listed at :2086, :2097, :2407, :3988
```

Renaming the underlying env var (§4) without editing these string keys breaks the gate harness silently (the gate would run with the *default*, not the intended value).

### 2.3 Checkpoint thread-id prefix literal

`src/polaris_graph/checkpoint_manager.py:53-55`

```python
def get_thread_id(vector_id: str) -> str:
    return f"pg_{vector_id}"
```

The `pg_` prefix is baked into every persisted `thread_id` and every `DELETE ... WHERE thread_id = ?` (`checkpoint_manager.py:93-94, 97`). Changing it orphans **all** existing on-disk checkpoints (`state/pg_checkpoints.sqlite`, `CHECKPOINT_DB` at `checkpoint_manager.py:30`). This is a persisted-string constant, not a symbol.

### 2.4 No `"cls": "Name"` / class-name serialization found

Grep for `"cls"`, `'cls'`, `__class__.__name__`, `type(self).__name__`, `class_name`, `clsname` across `src/polaris_graph` returns **no** hits where a Python class name is serialized to a persisted `type`/`cls` tag. Pydantic models here are (de)serialized by **field**, not by a class-name discriminator string (except the wire `Literal` fields in §4.2, which are value strings, not class names). **→ Renaming a Python class name (e.g. `ResearchStateV2` → …) does not orphan any saved payload**, provided its *fields* are unchanged.

---

## 3. Saved-state references (checkpoints, snapshots)

### 3.1 What is persisted, and how

- **Checkpointer:** LangGraph `AsyncSqliteSaver` over `state/pg_checkpoints.sqlite` (`checkpoint_manager.py:29-45`). Gated behind `PG_CHECKPOINT_ENABLED` (`checkpoint_manager.py:26`, default `"0"` per `config_defaults.py:97`), so **off by default** — but any operator who enabled it has on-disk state.
- **State shape:** `ResearchStateV2` (`graph_v2.py:71`) and `ResearchState` (`state.py:469`) are `TypedDict`s. LangGraph serializes the **field keys** and the **node/channel names**, NOT the TypedDict *class* name.

### 3.2 The rename-orphan hazards in saved state

| Persisted token | Where | Rename effect |
|---|---|---|
| Field key `registry_data` | `graph_v2.py:96-97, 359, 412, 460, 476, 545, 721, 835` | Rename the TypedDict field → old checkpoints lose the source registry on resume. |
| Nested keys `"entries"`, `"counter"` | `graph_v2.py:941, 950` (`_serialize_registry` / `_deserialize_registry`) | Serialized `SourceRegistry` shape; rename orphans registry restore. |
| Node names `"plan"`,`"search"`,…,`"v3_*"`,`"write_one_section"` | `graph.py:1242-1274`, `graph_v2.py:630-676`, `graph_v3.py:680-703` | LangGraph keys pending-writes by node name; renaming a node string breaks *resume* of an in-flight checkpoint. |
| `thread_id` prefix `pg_` | `checkpoint_manager.py:55` | Orphans all existing checkpoint rows (§2.3). |

**Class name `ResearchStateV2` itself is SAFE to rename** for checkpoint purposes (fields are what's persisted). Its risk is purely the ~static importers, handled by ordinary refactor.

### 3.3 Snapshot files — no pickle, keyed by field

`generator/corpus_snapshot.py:29`, `generation_snapshot.py:60`, `fetch_snapshot.py:40` all explicitly state "**No pickle, no code execution on load**" and (de)serialize plain `list[dict]` by field name. No class-name tag to orphan. Field-name renames inside those dicts would break older snapshots, but no Python *symbol* rename touches them.

---

## 4. Env-var / enum / persisted-string control surface (require ALIAS, never naive rename)

This is the **largest and highest-risk** category.

### 4.1 `PG_*` environment variables — the operator contract

- **839** `PG_*` keys are enumerated in `src/polaris_graph/config_defaults.py` (the "AUTO-GENERATED central registry of config defaults", `config_defaults.py:1`).
- **1,592** distinct `PG_*` literals are read across the package via `os.getenv` / `os.environ` / `resolve()`.
- `settings.py:88-98` `resolve(key)` = `os.getenv(key, CONFIG_DEFAULTS[key])` — **byte-identical** to the scattered `os.getenv` it replaces. The *string key* is the contract; the literal must match `config_defaults.py`, every call site, `.env.example` (24 documented keys), `docker-compose*.yml`, and Helm values.

An env-var name is a **published control surface**. Renaming `PG_FOO` → `PG_BAR` means every deployment that sets `PG_FOO=…` is silently ignored (falls back to default) with **no error**. → Env-var renames REQUIRE an **alias** (read the new name, fall back to the old, warn on old), never a naive rename.

**Live-env control-surface renames proposed in the worklist** (each read directly from the environment, none carry an alias today):

| Env var (current) | Read at | In `config_defaults`? | Worklist target |
|---|---|---|---|
| `PG_V30_ENABLED` | `honest_sweep_integration.py:92,96` (`os.environ.get(_ENABLED_ENV,"0")`) | no | `PG_FRAME_COVERAGE_ENABLED` |
| `PG_V2_ENABLED` | `scripts/live_server.py:560` (`os.getenv(...,"0")`) | no | `PG_LEGACY_GRAPH_ENABLED` |
| `PG_JUNK_SOURCE_SCREEN` | `scripts/run_honest_sweep_r3.py:1280` (kill-switch, `…=="0"`) | no | `PG_LOW_QUALITY_SOURCE_SCREEN` |
| `PG_CONTRADICTION_RENDER_HONEST` | `scripts/run_honest_sweep_r3.py:4856` (`os.environ.get(...,"1")`) | no | `PG_CONTRADICTION_RENDER_VERBATIM` |
| `PG_S15_CORROBORATED_HONEST_LABEL` | string key in gate dicts, `run_gate_b.py:643,2086,2407,3988` | no | `PG_S15_CORROBORATED_ORIGIN_LABEL` |
| `PG_LETHAL_SEED_K` | `wiki/mesh/retrieve/lethal.py:50` via `resolve(...)` | **yes** (`config_defaults.py:390` = `'80'`) | `PG_RETRIEVE_SEED_K` |

Note `PG_JUNK_SOURCE_SCREEN`/`PG_CONTRADICTION_RENDER_HONEST` are **kill-switches** whose own comments say `=0` "reverts byte-identically (LAW VI)". A silent rename removes an operator's documented emergency off-switch. `PG_LETHAL_SEED_K` is worse in one way: its literal is duplicated in **both** `config_defaults.py:390` and the `resolve()` call site, so a rename must touch both *and* alias the old env name.

→ **All six REQUIRE an alias shim.** None is a naive rename.

### 4.2 `Literal[...]` wire enums and `StageType` — persisted/wire values

`StageType(str, Enum)` values (`pipeline_definition.py:31-43`: `"plan"`,`"search"`,…) are the **string values** of a `str`-Enum that serialize into pipeline-definition YAML/JSON (`pipeline_definition.py` loads via `yaml`, `import yaml` at :23). Renaming an *enum member* (Python name) is safe; renaming the **value string** breaks any saved `PipelineDefinition`. The worklist does **not** propose renaming any `StageType` value (checked).

Wire-facing `Literal` value sets that a UI/API client depends on (rename = breaking API change, alias impossible for a closed literal set):

- `api/graph_route.py:37-40, 99` — `NodeType`, `EdgeType`, `Tier = Literal["T1".."T7"]`, `FrameStatus`, `schema_version: Literal["1.0"]`.
- `audit_bundle/bundle_schema.py:41, 152` — `ContentType`, `bundle_version: Literal["1.0"]`.
- `clinical_generator/verified_report.py` — many (`SectionStatus`, `PipelineVerdict`, tiers `Literal["T1","T2","T3"]`, `Jurisdiction`, …).
- `adequacy/plan_sufficiency_gate.py:60` `SufficiencyVerdict = Literal["proceed","expand","abort"]`; `anti_sycophancy/stance_delta.py:16` `StanceLabel`.

These string *values* are a data/wire contract. None is on the worklist as a value rename, but any future rename needs versioning, not a symbol rename.

---

## 5. External consumers (callers outside the repo)

### 5.1 FastAPI route paths — HTTP surface

`src/polaris_graph/api/*.py` register routes by **path-string literal** (breaking to rename; external clients call these URLs):

- `graph_route.py:250` `GET /runs/{run_id}/graph`
- `retrieval_route.py:100` `POST /retrieval…`, `:140` `GET /retrieval/health`
- `intake_route.py:66` `POST /intake` (`:5` documents "→ POST /api/intake"), `:98` `GET /intake/health`
- `audit_bundle_route.py:169,183,249` `POST /audit-bundle`, `/audit-bundle/preview`, `GET /audit-bundle/health`
- `disambiguation_route.py:82,108`; `benchmark_route.py:95,106,116,129`; `generation_route.py:137`.

Router *variable* / handler-function renames are internal (safe). The **path strings** and the `response_model` field names are the external contract.

### 5.2 Cross-module string import via `audit_ir.registry`

`api/graph_route.py:256` and `audit_ir/auth_middleware.py:95` do `from src.polaris_graph.audit_ir.registry import ...` — these are **static** imports (a refactor tool follows them), listed only to note that a module named `registry` exists and is imported by path; a file rename there is a normal multi-file edit, not a hidden dynamic hazard.

### 5.3 No `[project.scripts]` / plugin entry points

`pyproject.toml` declares none — there is no console-script name or setuptools entry-point group that an external installer/CLI resolves by string. CLI is via `scripts/*.py` run directly (`python scripts/live_server.py`), so **script filenames are themselves an external invocation contract** — the ~80 `scripts/*.py` `file`-kind RENAME rows change how operators/CI invoke them (grep your CI/compose for the old filenames before renaming).

---

## 6. Cross-reference against the rename worklist

`NAME_RENAME_WORKLIST_validated.tsv`: 346 rows — **210 RENAME**, 81 KEEP, 50 KEEP-NOTED, 4 KEEP-BUT-NOTED. Of the RENAMEs, 87 touch `src/polaris_graph/**`; the majority of the remainder are `scripts/*.py` file renames.

**RENAME rows that touch a dynamic/persisted/external surface identified above** (these need special handling, NOT a naive rename):

| Worklist NAME | Location | Category | Required handling |
|---|---|---|---|
| `PG_V30_ENABLED` → `PG_FRAME_COVERAGE_ENABLED` | `honest_sweep_integration.py:92` | §4.1 env control | **ALIAS** (read new, fall back to old, deprecation-warn) |
| `PG_V2_ENABLED` → `PG_LEGACY_GRAPH_ENABLED` | `scripts/live_server.py:560` | §4.1 env control | **ALIAS** |
| `PG_JUNK_SOURCE_SCREEN` → `PG_LOW_QUALITY_SOURCE_SCREEN` | `scripts/run_honest_sweep_r3.py:1280` | §4.1 env kill-switch | **ALIAS** (preserves `=0` off-switch) |
| `PG_CONTRADICTION_RENDER_HONEST` → `..._VERBATIM` | `scripts/run_honest_sweep_r3.py:4856` | §4.1 env kill-switch | **ALIAS** |
| `PG_S15_CORROBORATED_HONEST_LABEL` → `..._ORIGIN_LABEL` | gate dicts, `run_gate_b.py` (4 sites) | §2.2 + §4.1 | **ALIAS** + update all string dict keys together |
| `PG_LETHAL_SEED_K` → `PG_RETRIEVE_SEED_K` | `lethal.py:50` + `config_defaults.py:390` | §4.1 (in registry) | **ALIAS** + edit both registry entry and call site |
| `state_v3.py` → `state_lightweight.py`/`pipeline_state.py` | `state_v3.py:1` | file/module | Static-import rename, BUT verify no string-path ref; safe once §1.1/§3 checked |
| `honest_sweep_integration.py` → `v30_sweep_integration.py` | file | file/module | contains `PG_V30_ENABLED` — do the env alias in the **same** pass |
| `honest_sweep_job_runner.py` + `HonestSweepJobRunner` etc. | `audit_ir/…` | class/func/file | re-exported in `audit_ir/__init__.py:29-32` — static, safe, but update the `__init__` re-exports together |
| ~80 `scripts/*.py` `file` renames (`run_full_scale_v10..v27.py`, `iarch*/iwire*` harnesses, etc.) | `scripts/` | §5.3 invocation contract | grep CI / compose / docs for old filenames before renaming |

**RENAME rows that are SAFE** (ordinary refactor — the bulk of the 87 in-package rows): the long tail of **local variables and private helpers** inside `retrieval/live_retriever.py` (`_jo_doi`, `_w5_loop_idx`, `_w2_weight`, `_mv_now`, `_row0`, … lines 7142-8150), `generator/*` private funcs (`is_row_content_junk`, `_JUNK_SCREEN`, `_make_junk_screen`, …), and `benchmark/*` "BEAT-BOTH"→"head-to-head" docstring/const cleanups. These are function-local or module-private, have only static references, and touch **none** of §1-§5.

**Not touched by any RENAME row (verified):** `STAGE_TYPE_REGISTRY` module-path strings, `StageType` enum *values*, LangGraph node-name strings, `registry_data`/`entries`/`counter` state keys, the `pg_` thread-id prefix, all FastAPI path literals, and all wire `Literal[...]` value sets. Good — but they remain live traps for *future* renames and must stay on this checklist.

---

## 7. Conclusion — SAFE vs REQUIRES-ALIAS

**SAFE to rename** (static references only; IDE "rename symbol" is sufficient):
- Local variables and module-private helper functions (`_jo_doi`, `_JUNK_SCREEN`, `_make_junk_screen`, `_relevance_honest_drop_enabled`, …).
- Python **class names** whose payloads serialize by field, not by class-name tag — including `ResearchStateV2`, `HonestSweepJobRunner` (update its `audit_ir/__init__.py` re-export in the same commit).
- Router variables, handler functions, and other symbols behind FastAPI **path strings** (rename the symbol, keep the path).
- `str`-Enum **member names** (Python identifiers) as long as their **value strings** are unchanged.
- Ordinary intra-package modules/functions **after** confirming they are absent from the STAGE_TYPE_REGISTRY string table and from persisted state keys.

**REQUIRES AN ALIAS / versioning — never a naive rename:**
- **Every `PG_*` environment variable** that is a control surface — concretely the six on the worklist (§4.1). Provide a read-new-fall-back-to-old shim with a deprecation warning; update `config_defaults.py`, `.env.example`, compose/Helm, and any `run_gate_b.py` string-key dicts in lock-step.
- **Persisted-string constants:** the `pg_` checkpoint thread-id prefix, TypedDict field keys serialized into checkpoints (`registry_data`,`entries`,`counter`), LangGraph **node-name strings**, and any `StageType` / wire `Literal[...]` **value** — these are data-format changes requiring migration or schema-version bumps, not symbol renames.
- **External invocation names:** FastAPI route path literals and `scripts/*.py` filenames operators/CI call directly — treat as a deprecation with a redirect/shim, or coordinate the caller change.

**Governing rule for the reviewer and for the rename pass:**

> A "0 static importers" result narrows the risk but does not clear it. Before renaming any symbol, additionally confirm it is **not** (1) a string in a dispatch/registry table, (2) an env-var literal, (3) a persisted state/enum/wire value, or (4) an externally-invoked route/filename. Only when all five channels are clear is a rename safe; otherwise it needs an alias or a versioned migration.
