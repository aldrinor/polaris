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

The rest of this document enumerates each channel with `file:line` evidence, then (**§6.5**) gives a **row-by-row disposition of ALL 210 `RENAME` rows** — each classified `SAFE-static` / `FILE-RENAME-fix-importers` / `NEEDS-ALIAS` / `DYNAMIC-HAZARD` with a one-line reason and location.

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

### 2.4 No `"cls": "Name"` / class-name serialization found — but "not persisted" ≠ "safe to rename"

Grep for `"cls"`, `'cls'`, `__class__.__name__`, `type(self).__name__`, `class_name`, `clsname` across `src/polaris_graph` returns **no** hits where a Python class name is serialized to a persisted `type`/`cls` tag. Pydantic/TypedDict models here are (de)serialized by **field**, not by a class-name discriminator string (except the wire `Literal` fields in §4.2, which are value strings, not class names). **→ Renaming a Python class name (e.g. `ResearchStateV2` → …) does not orphan any saved payload**, provided its *fields* are unchanged.

**Correction (codex finding): "checkpoint-serialization-safe" does NOT imply "public import-name safe."** The paragraph above only clears the *persistence* channel. A public (non-underscore) class name is *also* an **import-name contract** — any external package or notebook doing `from src.polaris_graph.graph_v2 import ResearchStateV2` breaks on rename, and no static analyzer in *this* repo can see an importer that lives *outside* this repo. So the class-name renames must be cleared against the **import** channel separately, with evidence:

| Renamed public class (worklist row) | Defined | In-repo importers (grep, this worktree) | External-importer risk | Disposition |
|---|---|---|---|---|
| `ResearchStateV2` → `CragResearchState` (row 256) | `graph_v2.py:71` | **none** — every use is an intra-file type annotation in `graph_v2.py`; the only cross-file import of `graph_v2` is `scripts/live_server.py:561`, which imports `build_and_run`, **not** `ResearchStateV2`. `graph_v2.py` has **no `__all__`** (verified: `grep -n __all__ graph_v2.py` → empty), so the name is `import *`-reachable; no `from src.polaris_graph… import *` exists in-repo (verified). | **Cannot be proven zero** — public name, no `__all__` gate, module *is* imported by external entrypoints. | **NEEDS-ALIAS (recommend), not SAFE.** Keep `ResearchStateV2 = CragResearchState` as a module-level alias for ≥1 deprecation cycle. See §7. |
| `V3State` → `LightweightResearchState` (row 302) | `state_v3.py:15` | `graph_v3.py:25` (`from …state_v3 import V3State, create_v3_state`) + `tests/v3/test_graph.py`. **Live cross-file importers.** | Same public-name exposure. | **FILE/SYMBOL rename — fix importers in the same commit**, and alias-recommend for the public class name (§7). |
| `V30SweepResult` → `FrameCoverageSweepResult` (row 264) | `honest_sweep_integration.py:73` | no cross-file importer of the *symbol* found (only intra-module use). | Public name; module is a documented integration surface. | Alias-recommend (cheap; one line). |
| `HonestSweepJobRunner` / `…Config` / `make_default_honest_sweep_job_runner` (rows 217-219, 221-222) | `audit_ir/honest_sweep_job_runner.py` | **re-exported** at `audit_ir/__init__.py:29-32,144-145`; imported by `audit_ir/inspector_router.py:417`, and by `tests/polaris_graph/test_honest_sweep_job_runner.py:28-31`. | Re-exported from a package `__init__` → this is a **published package symbol**. | **NEEDS-ALIAS**: update the `__init__` re-export + the string-dispatch registration in the same commit (see below), and keep an alias export. |

**Additional dynamic hazard for `HonestSweepJobRunner`:** it is wired into a **string-keyed runner registry**. `audit_ir/job_runner.py:114-117` `register_runner()` stores `_RUNNERS[runner.template_id] = runner`, and `inspector_router.py:418` registers `make_default_honest_sweep_job_runner()` under the **string** `template_id="v30_clinical"` (`inspector_router.py:406,1452,1469-1476`; the enqueue path does `queue.enqueue(req.template_id, …)`). The **class name** is *not* the dispatch key (the `"v30_clinical"` string is), so renaming the class does not break dispatch — **but the factory-function name and the `__init__` re-export are real import-name contracts** that must move together. The `"v30_clinical"` template string is itself a separate persisted/wire control surface (an API client selects it) and is **not** on the worklist — leave it, or version it, never silently rename it.

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

**Class name `ResearchStateV2` is safe *for the checkpoint channel only*** (fields are what's persisted, not the class name). It is **not** thereby cleared for the **import-name** channel: it is a public symbol in a module external entrypoints import from, with **no `__all__`** gating it. Because no static tool can see an importer outside this repo, we cannot *prove* zero external importers — so this is **NEEDS-ALIAS (recommended)**, not SAFE. See §2.4 and §7.

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

> **§6 is the highlight reel; §6.5 below is the authoritative ROW-BY-ROW disposition of ALL 210 RENAME rows** (every row classified SAFE-static / FILE-RENAME-fix-importers / NEEDS-ALIAS / DYNAMIC-HAZARD with a reason + location). The tables in §6 call out the highest-risk rows; where §6 and §6.5 differ in nuance, §6.5 governs.

**RENAME rows that touch a dynamic/persisted/external surface identified above** (these need special handling, NOT a naive rename):

| Worklist NAME | Location | Category | Required handling |
|---|---|---|---|
| `PG_V30_ENABLED` → `PG_FRAME_COVERAGE_ENABLED` | `honest_sweep_integration.py:92` | §4.1 env control | **ALIAS** (read new, fall back to old, deprecation-warn) |
| `PG_V2_ENABLED` → `PG_LEGACY_GRAPH_ENABLED` | `scripts/live_server.py:560` | §4.1 env control | **ALIAS** |
| `PG_JUNK_SOURCE_SCREEN` → `PG_LOW_QUALITY_SOURCE_SCREEN` | `scripts/run_honest_sweep_r3.py:1280` | §4.1 env kill-switch | **ALIAS** (preserves `=0` off-switch) |
| `PG_CONTRADICTION_RENDER_HONEST` → `..._VERBATIM` | `scripts/run_honest_sweep_r3.py:4856` | §4.1 env kill-switch | **ALIAS** |
| `PG_S15_CORROBORATED_HONEST_LABEL` → `..._ORIGIN_LABEL` | gate dicts, `run_gate_b.py` (4 sites) | §2.2 + §4.1 | **ALIAS** + update all string dict keys together |
| `PG_LETHAL_SEED_K` → `PG_RETRIEVE_SEED_K` | `lethal.py:50` + `config_defaults.py:390` | §4.1 (in registry) | **ALIAS** + edit both registry entry and call site |
| `state_v3.py` → `state_lightweight.py`/`pipeline_state.py` | `state_v3.py:1` | file/module | Fix importers (`graph_v3.py:25`, `tests/v3/test_graph.py`); verify no `STAGE_TYPE_REGISTRY` string-path ref (§1.1). The **public class `V3State`** it exports is separately alias-recommended (§2.4). |
| `honest_sweep_integration.py` → `v30_sweep_integration.py` | file | file/module | contains `PG_V30_ENABLED` — do the env alias in the **same** pass |
| `honest_sweep_job_runner.py` + `HonestSweepJobRunner`/`…Config`/`make_default_…` | `audit_ir/…` | class/func/file | **NEEDS-ALIAS** — re-exported in `audit_ir/__init__.py:29-32,144-145`, imported by `inspector_router.py:417` + tests, and registered under string `template_id="v30_clinical"`. Public package symbol → keep an alias export + move the `__init__` re-exports and the factory import together (§2.4). NOT a bare "static, safe" rename. |
| `ResearchStateV2`→`CragResearchState`, `V3State`→`LightweightResearchState`, `V30SweepResult`→`FrameCoverageSweepResult` | `graph_v2.py:71`, `state_v3.py:15`, `honest_sweep_integration.py:73` | public class | **NEEDS-ALIAS (recommended)** — "fields serialize, not class name" clears only the checkpoint channel, NOT the import-name channel; no `__all__` gate, module imported by external entrypoints. Add a module-level backward-compat alias (§2.4). |
| ~80 `scripts/*.py` `file` renames (`run_full_scale_v10..v27.py`, `iarch*/iwire*` harnesses, etc.) | `scripts/` | §5.3 invocation contract | grep CI / compose / docs for old filenames before renaming |

**RENAME rows that are SAFE-static** (ordinary refactor — the bulk of the 87 in-package rows): the long tail of **local variables and `_`-private helpers** inside `retrieval/live_retriever.py` (`_jo_doi`, `_w5_loop_idx`, `_w2_weight`, `_mv_now`, `_row0`, … lines 7142-8150), `generator/*` **`_`-private** funcs (`_JUNK_SCREEN`, `_make_junk_screen`, `_compose_junk_screen`, …), and `benchmark/*` "BEAT-BOTH"→"head-to-head" **docstring/const** cleanups. These are function-local or module-private, have only static references, and touch **none** of §1-§5. (Full roster in §6.5.)

> **Correction — not every "junk" row is a private helper.** `is_row_content_junk` (`generator/junk_deletion_gate.py:105`) is a **public** function of a module with **6 importers**, and `content_integrity_junk` (`:110,244,270`) is a **persisted row-state dict key**. Those are **NEEDS-ALIAS / DYNAMIC-HAZARD**, not SAFE — see §6.5. Do not fold public/persisted "junk" names into the SAFE bucket on a name-pattern basis.

**Not touched by any RENAME row (verified):** `STAGE_TYPE_REGISTRY` module-path strings, `StageType` enum *values*, LangGraph node-name strings, `registry_data`/`entries`/`counter` state keys, the `pg_` thread-id prefix, all FastAPI path literals, and all wire `Literal[...]` value sets. Good — but they remain live traps for *future* renames and must stay on this checklist.

---

## 6.5 Row-by-row disposition of the authoritative worklist (ALL 210 RENAME rows)

**Source of truth:** `/home/polaris/polaris_project/NAME_RENAME_WORKLIST_validated.tsv`, 346 rows total. Filtering on the `VERDICT` column gives **exactly 210 `RENAME`** rows (verified: `awk -F'\t' '$1=="RENAME"' | wc -l` = 210) + 81 `KEEP` + 50 `KEEP-NOTED` + 4 `KEEP-BUT-NOTED` = 346. Only the 210 `RENAME` rows can break a public-compat contract; the 135 `KEEP*` rows change nothing and are not enumerated here. **The worklist has exactly 210 RENAME rows — the count the rest of this document asserts holds.**

**Class assignment.** Each of the 210 rows below carries exactly one class from {`SAFE-static`, `TEXT-ONLY`, `FILE-RENAME`, `NEEDS-ALIAS`, `DYNAMIC-HAZARD`, `DOMAIN-REVIEW`}, derived deterministically from the worklist `SAFETY` column and then hand-corrected for the public-symbol / persisted-key cases established in §2.4 and §6:

- `SAFE (symbol rename)` → **SAFE-static**, *except* the five `HonestSweepJobRunner` / `HonestSweepJobRunnerConfig` / `make_default_honest_sweep_job_runner` rows (rows 125–127, 129–130), which are **promoted to NEEDS-ALIAS** — they are package-re-exported public symbols (`audit_ir/__init__.py`), not private names (§2.4).
- `TEXT-ONLY (safe)` → **TEXT-ONLY** (docstring / comment / log-string text only).
- `FILE-RENAME (verify importers first)` → **FILE-RENAME**.
- `NEEDS-ALIAS (control-surface string)` + `NEEDS-ALIAS (control-surface/persisted string)` → **NEEDS-ALIAS**, *except* the ten string-dispatch / persisted-row-state-key / many-importer string-imported-module rows (`content_integrity_junk`; the `junk_deletion_gate` / `is_row_content_junk` cluster; the `beat_both_scorer` cluster), which are **DYNAMIC-HAZARD** (rows 92, 94, 118, 131, 132, 134, 141, 142, 143, 144).
- `DOMAIN-REVIEW` → **DOMAIN-REVIEW** (codex's own second-pass judgment calls; residual public-compat risk noted per row).

The corrections from §2.4 are preserved here: the `HonestSweepJobRunner` cluster is **NEEDS-ALIAS (not SAFE)**, and `is_row_content_junk` / `content_integrity_junk` are **DYNAMIC-HAZARD (not SAFE)**. (`ResearchStateV2`, `V3State`, `V30SweepResult` are analyzed in §2.4 as NEEDS-ALIAS *class-name* concerns; note they are **not** themselves worklist `RENAME` NAME entries — the worklist renames the surrounding files/state helpers (`state_v3.py`, `create_v3_state`, `honest_sweep_integration.py`), and those file/symbol rows appear below.)

### The exact per-row table (one row per rename; 210 rows)

| # | old_name | new_name | location | class | reason |
|---|---|---|---|---|---|
| 1 | `_basket_workers_ab_cert.py` | `compose_basket_workers_ab_certification_test.py` | `scripts/_basket_workers_ab_cert.py:1` | FILE-RENAME | leading underscore + informal filename for a certification/test script; unprofessional for external review |
| 2 | `_m54_append_contract.py` | `append_report_contract_yaml.py` | `scripts/_m54_append_contract.py:1` | FILE-RENAME | internal milestone-ticket code "m54" embedded in filename; cryptic ticket abbreviation, unprofessional for external audit |
| 3 | `_retired_2026_06_14` | `archive/2026_06_14_retired_scripts/ (or delete if truly dead)` | `scripts/_retired_2026_06_14/pg_compose_openai_validation.py:1` | FILE-RENAME | directory name is a dead/retired-code marker (leading underscore + retirement date) left in the shipped tree… |
| 4 | `OpenAIShimClient` | `-` | `scripts/_retired_2026_06_14/pg_compose_openai_validation.py:58` | SAFE-static | Shim is acceptable engineering term but combined with ad-hoc one-off script context and retired dir, borderline; keep name but note dir issue covers it |
| 5 | `lethal_retrieve` | `prioritized_retrieve or ranked_retrieve` | `scripts/_retired_2026_06_14/pg_mesh_preflight.py:28` | DOMAIN-REVIEW | imported name "lethal_retrieve" -- aggressive/marketing-style adjective "lethal" used as a real function name in the retrieval module… |
| 6 | `_v24_compare.py` | `compare_report_versions.py (or delete)` | `scripts/_v24_compare.py:1` | FILE-RENAME | version-number-in-filename ("v24"/"v23") one-shot script explicitly marked "Delete after use" in its own docstring… |
| 7 | `aggregate_beat_both_runs.py` | `-` | `scripts/aggregate_beat_both_runs.py:1` | DOMAIN-REVIEW | BEAT-BOTH is an established internal benchmark taxonomy term used consistently and meaningfully; borderline but descriptive of an actual comparison scheme |
| 8 | `Gemini feature / GEMINI-ARCH` | `STRUCTURED_DATA_ARCH or similar internal tag` | `scripts/anti_tunnel_view_test.py:52` | NEEDS-ALIAS | internal code repeatedly labels application features "Gemini" (a third-party model/product name) as an architecture tag baked into state keys… |
| 9 | `audit_v3_report.py` | `audit_report_forensics.py` | `scripts/audit_v3_report.py:1` | FILE-RENAME | version marker "v3" baked into filename/module name for an external audit tool |
| 10 | `compare_live_vs_pg_lb_sa_02.py` | `compare_live_vs_prerebuild_run.py` | `scripts/compare_live_vs_pg_lb_sa_02.py:1` | FILE-RENAME | filename embeds a terse cryptic internal run-ID token "pg_lb_sa_02" with no expansion, opaque to an external reviewer |
| 11 | `compose_agentic_report_s3gear329.py` | `compose_agentic_report.py` | `scripts/compose_agentic_report_s3gear329.py:1` | FILE-RENAME | filename embeds a cryptic internal codename/task suffix ("s3gear329") that reads as opaque internal jargon to an external reviewer |
| 12 | `dashboard_PG_TEST_060_BTG.html` | `dashboard_test_output.html` | `scripts/dashboard_visual_audit.py:30` | NEEDS-ALIAS | hardcoded path literal references a cryptic internal test codename ("PG_TEST_060_BTG") with no meaning to an external reviewer |
| 13 | `deep_gemini_verify.py` | `integration_quality_verify.py` | `scripts/deep_gemini_verify.py:1` | FILE-RENAME | file/module named and described around "Gemini-class" quality marketing language… |
| 14 | `Gemini-class` | `high-quality output` | `scripts/deep_gemini_verify.py:2` | TEXT-ONLY | docstring repeatedly uses the marketing/comparative phrase "Gemini-class output" as a quality tier name instead of a neutral descriptive term |
| 15 | `slice_005_beat_both_benchmark` | `slice_005_comparative_benchmark` | `scripts/demo_smoke.py:38` | NEEDS-ALIAS | beat_both is an informal/marketing comparative name ("beat both competitors") baked into a public API health-check identifier… |
| 16 | `passced` | `passed` | `scripts/diagnostics/entailment_shape_bakeoff.py:205` | SAFE-static | misspelled variable name ("passced" instead of "passed") left in shipped diagnostic code |
| 17 | `real box2 junk fixtures` | `real box2 chrome/noise fixtures` | `scripts/dr_benchmark/_wave2_assert.py:1` | TEXT-ONLY | docstring uses informal/slang word "junk" to describe test fixture data |
| 18 | `strip_junk` | `strip_non_answer_content` | `scripts/dr_benchmark/pack_drb2.py:90` | DOMAIN-REVIEW | uses informal word "junk" as part of a public function name; function is well-scoped (strips masthead/base64/oversized-line noise) but "junk" reads informally f… |
| 19 | `run_honest_sweep_r3.py` | `run_sweep_evaluation.py` | `scripts/harness_render_boundary_screen.py:53` | FILE-RENAME | Referenced module name uses marketing adjective "honest" plus a bare version marker "r3"; unprofessional for external review |
| 20 | `rhsr_patched` | `honest_sweep_module` | `scripts/harness_render_boundary_screen.py:57` | SAFE-static | Cryptic unexplained abbreviation for a loaded module object |
| 21 | `i_naming_001_migrate.py` | `migrate_bpei_to_ambiguity_detector.py` | `scripts/i_naming_001_migrate.py:1` | FILE-RENAME | Filename is an opaque internal ticket/ID reference (I-naming-001) rather than a descriptive name |
| 22 | `iarch007_behavioral_canary.py` | `behavioral_canary_release_fixes.py` | `scripts/iarch007_behavioral_canary.py:1` | FILE-RENAME | Filename keyed to an opaque internal issue ID (iarch007) rather than describing content |
| 23 | `rhsr3_canary` | `sweep_module_canary` | `scripts/iarch007_behavioral_canary.py:157` | SAFE-static | Cryptic abbreviation for an imported module reference |
| 24 | `run_honest_sweep_r3.py` | `run_sweep_evaluation.py` | `scripts/iarch007_behavioral_canary.py:21` | FILE-RENAME | Referenced module name uses marketing adjective "honest" plus version marker "r3 |
| 25 | `iarch007_release_invariant_check.py` | `release_invariant_check.py` | `scripts/iarch007_release_invariant_check.py:1` | FILE-RENAME | Filename keyed to an opaque internal issue ID (iarch007) rather than descriptive content |
| 26 | `iarch010_replay_breadth_faithfulness_harness.py` | `replay_breadth_faithfulness_harness.py` | `scripts/iarch010_replay_breadth_faithfulness_harness.py:1` | FILE-RENAME | Filename keyed to an opaque internal issue ID (iarch010) prefix rather than describing content alone |
| 27 | `iarch011_b11_compose_repetition_harness.py` | `compose_repetition_harness.py` | `scripts/iarch011_b11_compose_repetition_harness.py:1` | FILE-RENAME | Filename keyed to opaque internal issue IDs (iarch011, b11) rather than descriptive content |
| 28 | `_BANKED_RUN` | `BANKED_RUN_DIR (configurable)` | `scripts/iarch011_b11_compose_repetition_harness.py:35` | SAFE-static | hardcoded absolute Windows path constant baked into module, not a naming-quality issue per se but combined with cryptic scope is fragile… |
| 29 | `iarch011_binding_and_judge_probe.py` | `binding_and_judge_probe.py` | `scripts/iarch011_binding_and_judge_probe.py:1` | FILE-RENAME | Filename keyed to opaque internal issue ID (iarch011) rather than descriptive content |
| 30 | `_R` | `_REPO_ROOT` | `scripts/iarch011_binding_and_judge_probe.py:10` | SAFE-static | Single-letter cryptic variable for repo root path |
| 31 | `an` | `credibility_analysis` | `scripts/iarch011_binding_and_judge_probe.py:34` | SAFE-static | Two-letter cryptic variable name for credibility analysis result |
| 32 | `wfe` | `unbound_supports_diag` | `scripts/iarch011_binding_and_judge_probe.py:36` | SAFE-static | Cryptic abbreviation for weighted-enrichment/unbound-supports diagnostic result |
| 33 | `verb` | `verbatim_count` | `scripts/iarch011_binding_and_judge_probe.py:58` | SAFE-static | Cryptic terse abbreviation (verbatim count) shadowing the word "verb |
| 34 | `cw_cov` | `content_word_coverage_count` | `scripts/iarch011_binding_and_judge_probe.py:59` | SAFE-static | Cryptic terse abbreviation for content-word coverage count |
| 35 | `ej` | `entailment_judge_mod` | `scripts/iarch011_binding_and_judge_probe.py:82` | SAFE-static | Cryptic two-letter abbreviation for imported entailment_judge module |
| 36 | `verds` | `verdict_counts` | `scripts/iarch011_binding_and_judge_probe.py:93` | SAFE-static | Cryptic terse abbreviation for verdict counts dict |
| 37 | `iarch011_fixb_pair_dump` | `iarch011_verbatim_entailment_pair_diagnostic.py` | `scripts/iarch011_fixb_pair_dump.py:1` | FILE-RENAME | filename uses informal 'dump'; also encodes internal 'fixb' label |
| 38 | `_REFY` | `_REFERENCE_LIST_RE` | `scripts/iarch011_parallel_verify_gate.py:54` | SAFE-static | '_REFY' is a jokey/informal contraction ('ref-y') for a reference-list regex |
| 39 | `_is_junk` | `_is_non_citable_unit` | `scripts/iarch011_parallel_verify_gate.py:55` | SAFE-static | 'junk' is informal/vague vocabulary for low-value units |
| 40 | `junk` | `non_citable_units` | `scripts/iarch011_parallel_verify_gate.py:58` | SAFE-static | informal/vague vocabulary |
| 41 | `run_honest_sweep_r3` | `run_sweep` | `scripts/iarch011_prb_corroboration_replay_harness.py:51` | DOMAIN-REVIEW | imported module name carries marketing adjective 'honest' + version marker 'r3'; defined in another shard, flagged where referenced |
| 42 | `_GARBAGE_URL` | `_UNVERIFIED_URL` | `scripts/iarch011_prb_corroboration_replay_harness.py:69` | SAFE-static | 'garbage' is informal/vague vocabulary for an unverified test fixture |
| 43 | `_SYN` | `_SYNTHETIC_FIXTURE_ROWS` | `scripts/iarch011_prd_abstract_conclusion_replay_harness.py:104` | SAFE-static | terse informal abbreviation; unclear without context |
| 44 | `_check_redaction_landmine` | `_check_redaction_duplicate_edge_case` | `scripts/iarch011_prd_abstract_conclusion_replay_harness.py:386` | SAFE-static | 'landmine' is a jokey/informal metaphor for an edge-case; reads unprofessional |
| 45 | `run_honest_sweep_r3` | `run_sweep` | `scripts/iwire014_cwf_header_diagnostic.py:18` | DOMAIN-REVIEW | imported module name carries the marketing adjective 'honest' plus version marker 'r3'; defined elsewhere but referenced here |
| 46 | `bad` | `junk_header_count` | `scripts/iwire014_cwf_header_diagnostic.py:74` | SAFE-static | local variable named 'bad' is vague/informal for the count of junk headers |
| 47 | `JUNK HEADER` | `non-renderable header` | `scripts/iwire014_cwf_header_diagnostic.py:77` | DOMAIN-REVIEW | printed string literal 'JUNK HEADER'/'REAL HEADER' is informal; output text, not an identifier |
| 48 | `run_honest_sweep_r3` | `run_sweep` | `scripts/iwire014_quantified_replay.py:60` | DOMAIN-REVIEW | same imported module name with 'honest' quality adjective and 'r3' version suffix |
| 49 | `_run_honest_sweep_r3` | `run_sweep` | `scripts/iwire014_quantified_replay.py:63` | TEXT-ONLY | same as above, comment/import reference to 'honest'/'r3' named module |
| 50 | `run_honest_sweep_r3` | `run_sweep` | `scripts/iwire014_render_proof.py:2` | DOMAIN-REVIEW | imported module name with 'honest' adjective and 'r3' version marker |
| 51 | `cs` | `content_sample` | `scripts/iwire016_chrome_classifier_bakeoff.py:109` | SAFE-static | opaque 'cs' (content sample) is throwaway naming |
| 52 | `hs` | `chrome_sample` | `scripts/iwire016_chrome_classifier_bakeoff.py:110` | SAFE-static | single-letter/opaque 'hs' (chrome sample) reads as throwaway naming |
| 53 | `token_explosion` | `high_output_token_count` | `scripts/live_monitor.py:654` | NEEDS-ALIAS | rule label 'token_explosion' is an informal/vague metaphor for an output-token spike |
| 54 | `build_and_run_v4` | `build_and_run (drop version suffix once dead branches removed)` | `scripts/live_server.py:557` | TEXT-ONLY | version-number-as-name (v4) used as the production default function alias; comment admits it is "now the production default" so v4 is a stale/confusing marker |
| 55 | `PG_V2_ENABLED` | `PG_LEGACY_GRAPH_ENABLED` | `scripts/live_server.py:560` | NEEDS-ALIAS | env flag name bakes in version number v2 for what the code calls a legacy/compat path |
| 56 | `Legacy run, pre-honest-rebuild` | `LEGACY_MODE_LABEL = "Legacy run, pre-rebuild"` | `scripts/migrate_old_runs.py:59` | NEEDS-ALIAS | uses marketing/quality adjective "honest" in a persisted mode_label string constant |
| 57 | `_honest_rebuild_migration` | `_pre_rebuild_migration` | `scripts/migrate_old_runs.py:60` | NEEDS-ALIAS | uses marketing/quality adjective "honest" embedded in a stored migration-marker key |
| 58 | `DICED` | `pipeline_stage_invariant_preflight.py` | `scripts/pipeline_diced_preflight.py:2` | FILE-RENAME | file/harness named after an undefined coined acronym "DICED" (never spelled out anywhere in the file)… |
| 59 | `dice` | `StageCheckResult / rename dice_* functions to check_<stage_name>` | `scripts/pipeline_diced_preflight.py:217` | SAFE-static | DiceResult dataclass and the whole "dice"/"dice_dN_*" naming scheme (dice_d0_scope_no_source_drop, dice_fx06_population_coupling… |
| 60 | `OFFLINE_DICE` | `OFFLINE_CHECKS` | `scripts/pipeline_diced_preflight.py:838` | DOMAIN-REVIEW | same slang-metaphor naming as DiceResult; consistent internal usage but inherits the unprofessional "dice" terminology |
| 61 | `playwright_fire_test.py` | `playwright_exhaustive_ui_audit.py` | `scripts/playwright_fire_test.py:1` | FILE-RENAME | informal slang "fire test" for what is an exhaustive 79-check UI/DOM audit script; unprofessional in an external client review |
| 62 | `run_full_scale_v10.py` | `run_full_scale.py (single script with a --profile/--config flag selecting the knob set)` | `scripts/run_full_scale_v10.py:1` | FILE-RENAME | bare version-number suffix (v10) with no semantic meaning outside a changelog; one of 10 near-duplicate versioned launcher scripts |
| 63 | `_V10_ENV` | `LAUNCH_ENV` | `scripts/run_full_scale_v10.py:26` | SAFE-static | version-numbered constant name duplicated across 10 files instead of a shared parameterized config |
| 64 | `run_full_scale_v23.py` | `run_full_scale.py (parameterized by config file)` | `scripts/run_full_scale_v23.py:1` | FILE-RENAME | bare version-number suffix; near-identical duplicate of v10/v24-v30 launcher scripts differing only in embedded knob values |
| 65 | `_V23_ENV` | `LAUNCH_ENV` | `scripts/run_full_scale_v23.py:28` | SAFE-static | version-numbered constant name, duplicated boilerplate across 10 files |
| 66 | `run_full_scale_v24.py` | `run_full_scale.py (parameterized)` | `scripts/run_full_scale_v24.py:1` | FILE-RENAME | bare version-number suffix; near-identical duplicate launcher |
| 67 | `_V24_ENV` | `LAUNCH_ENV` | `scripts/run_full_scale_v24.py:35` | SAFE-static | version-numbered constant name, duplicated boilerplate |
| 68 | `run_full_scale_v25.py` | `run_full_scale.py (parameterized)` | `scripts/run_full_scale_v25.py:1` | FILE-RENAME | bare version-number suffix; near-identical duplicate launcher |
| 69 | `_V25_ENV` | `LAUNCH_ENV` | `scripts/run_full_scale_v25.py:37` | SAFE-static | version-numbered constant name, duplicated boilerplate |
| 70 | `run_full_scale_v26.py` | `run_full_scale.py (parameterized)` | `scripts/run_full_scale_v26.py:1` | FILE-RENAME | bare version-number suffix; near-identical duplicate launcher |
| 71 | `_V26_ENV` | `LAUNCH_ENV` | `scripts/run_full_scale_v26.py:52` | SAFE-static | version-numbered constant name, duplicated boilerplate |
| 72 | `run_full_scale_v27.py` | `run_full_scale.py (parameterized)` | `scripts/run_full_scale_v27.py:1` | FILE-RENAME | bare version-number suffix; near-identical duplicate launcher |
| 73 | `_V27_ENV` | `LAUNCH_ENV` | `scripts/run_full_scale_v27.py:43` | SAFE-static | version-numbered constant name, duplicated boilerplate |
| 74 | `run_full_scale_v28.py` | `run_full_scale.py (parameterized)` | `scripts/run_full_scale_v28.py:1` | FILE-RENAME | bare version-number suffix; near-identical duplicate launcher |
| 75 | `_V28_ENV` | `LAUNCH_ENV` | `scripts/run_full_scale_v28.py:51` | SAFE-static | version-numbered constant name, duplicated boilerplate |
| 76 | `run_full_scale_v29.py` | `run_full_scale.py (parameterized)` | `scripts/run_full_scale_v29.py:1` | FILE-RENAME | bare version-number suffix; near-identical duplicate launcher |
| 77 | `_V29_ENV` | `LAUNCH_ENV` | `scripts/run_full_scale_v29.py:35` | SAFE-static | version-numbered constant name, duplicated boilerplate |
| 78 | `run_full_scale_v30_phase2.py` | `run_full_scale.py (parameterized) or full_scale_launcher.py` | `scripts/run_full_scale_v30_phase2.py:1` | FILE-RENAME | bare version+phase suffix; another near-identical duplicate launcher in the same version series |
| 79 | `_V30_PHASE2_ENV` | `LAUNCH_ENV` | `scripts/run_full_scale_v30_phase2.py:38` | SAFE-static | version-numbered constant name, duplicated boilerplate |
| 80 | `run_honest_sweep_r3.py` | `run_cross_domain_readiness_sweep.py` | `scripts/run_honest_sweep_r3.py:1` | FILE-RENAME | honest is a marketing/quality adjective and "r3" is a version/revision marker; module filename reads as boastful + versioned rather than descriptive |
| 81 | `_junk_ev_row_text` | `_low_quality_ev_row_text` | `scripts/run_honest_sweep_r3.py:1187` | SAFE-static | junk is informal slang for the low-quality-source concept; reads unprofessionally in an external review |
| 82 | `_junk_ev_row_url` | `_low_quality_ev_row_url` | `scripts/run_honest_sweep_r3.py:1196` | SAFE-static | junk is informal slang |
| 83 | `_junk_ev_row_direct_quote` | `_low_quality_ev_row_direct_quote` | `scripts/run_honest_sweep_r3.py:1203` | SAFE-static | junk is informal slang |
| 84 | `_junk_src_url` | `_low_quality_src_url` | `scripts/run_honest_sweep_r3.py:1241` | SAFE-static | junk is informal slang |
| 85 | `_screen_junk_evidence` | `_screen_low_quality_evidence` | `scripts/run_honest_sweep_r3.py:1248` | SAFE-static | junk is informal slang for low-quality/non-assertional sources |
| 86 | `PG_JUNK_SOURCE_SCREEN` | `PG_LOW_QUALITY_SOURCE_SCREEN` | `scripts/run_honest_sweep_r3.py:1280` | NEEDS-ALIAS | env-var name embeds the informal slang "junk |
| 87 | `_screen_junk_evidence` | `_screen_low_quality_evidence` | `scripts/run_honest_sweep_r3.py:14016` | SAFE-static | 'junk' is informal/vague slang for low-quality evidence rows; a descriptive term is more professional |
| 88 | `_gate_injected_prepend_rows` | `-` | `scripts/run_honest_sweep_r3.py:14426` | DOMAIN-REVIEW | 'gate' is a real domain term here; retained despite density |
| 89 | `_detect_ci_junk` | `_detect_content_integrity_defect` | `scripts/run_honest_sweep_r3.py:14655` | SAFE-static | local alias uses informal 'junk'; also 'ci' is an unexplained abbreviation |
| 90 | `_final_zyte` | `-` | `scripts/run_honest_sweep_r3.py:15664` | DOMAIN-REVIEW | 'Zyte' is a real third-party scraping product name, legitimately referenced |
| 91 | `_ci_zyte_saved` | `_content_integrity_recovered_count` | `scripts/run_honest_sweep_r3.py:15675` | SAFE-static | 'ci' unexplained abbreviation for content-integrity in a saved-count variable |
| 92 | `content_integrity_junk` | `content_integrity_defect` | `scripts/run_honest_sweep_r3.py:15688` | DYNAMIC-HAZARD | dict key / class label uses informal 'junk' |
| 93 | `_run_junk_deleted_disclosed` | `_run_nonsource_deleted_disclosed` | `scripts/run_honest_sweep_r3.py:15745` | SAFE-static | informal 'junk' in an identifier |
| 94 | `junk_deletion_gate` | `nonsource_deletion_gate` | `scripts/run_honest_sweep_r3.py:15747` | DYNAMIC-HAZARD | imported module name uses informal 'junk' |
| 95 | `_junk_deleted_for_disclosure` | `_nonsource_deleted_for_disclosure` | `scripts/run_honest_sweep_r3.py:15760` | SAFE-static | informal 'junk' in an identifier |
| 96 | `build_known_words_from_evidence` | `build_corpus_vocabulary_from_evidence` | `scripts/run_honest_sweep_r3.py:17850` | SAFE-static | 'known_words' is vague; a corpus-vocabulary term would be clearer (borderline) |
| 97 | `_QUANTIFIED_HONEST_EMPTY_STATUSES` | `_QUANTIFIED_LEGITIMATE_EMPTY_STATUSES` | `scripts/run_honest_sweep_r3.py:1846` | DOMAIN-REVIEW | honest_empty uses "honest" as a quality adjective; borderline domain term (ran-and-legitimately-empty) but reads as praise at a strict bar |
| 98 | `honest_sweep_integration` | `sweep_integration` | `scripts/run_honest_sweep_r3.py:20231` | FILE-RENAME | imported module name carries the marketing/quality adjective 'honest' |
| 99 | `apply_honest_scorecard_to_manifest` | `apply_release_quality_scorecard_to_manifest` | `scripts/run_honest_sweep_r3.py:21366` | SAFE-static | 'honest' is a marketing/quality adjective describing the scorecard; the function name should describe what it computes |
| 100 | `run_honest_sweep_r3.py` | `run_verification_sweep.py` | `scripts/run_honest_sweep_r3.py:21658` | FILE-RENAME | 'honest' is a marketing/quality adjective and 'r3' is a temporal/version marker; both read unprofessional in a module name |
| 101 | `_WINNER_SLATE_ON_PAID_PATH_ENV` | `_ENRICHMENT_SLATE_ON_PAID_PATH_ENV` | `scripts/run_honest_sweep_r3.py:21674` | NEEDS-ALIAS | 'WINNER' is a marketing/quality adjective in a constant name |
| 102 | `_PAID_PATH_WINNER_FLAGS` | `_PAID_PATH_ENRICHMENT_FLAGS` | `scripts/run_honest_sweep_r3.py:21675` | SAFE-static | 'WINNER' is a marketing/quality adjective in a constant name |
| 103 | `winner_slate_on_paid_path_enabled` | `enrichment_slate_on_paid_path_enabled` | `scripts/run_honest_sweep_r3.py:21689` | NEEDS-ALIAS | 'winner' is a marketing/quality adjective (implies best-of-breed) rather than a descriptive term |
| 104 | `apply_winner_slate_on_paid_path` | `apply_enrichment_slate_on_paid_path` | `scripts/run_honest_sweep_r3.py:21696` | NEEDS-ALIAS | 'winner' is a marketing/quality adjective; the slate is a set of enrichment flags, not a 'winner' |
| 105 | `honest_sweep_r3` | `verification_sweep` | `scripts/run_honest_sweep_r3.py:21826` | DOMAIN-REVIEW | default output-dir string 'honest_sweep_r3' carries the same 'honest'/'r3' markers as the module; noted as it tracks the file rename |
| 106 | `PG_S15_CORROBORATED_HONEST_LABEL` | `PG_S15_CORROBORATED_ORIGIN_LABEL` | `scripts/run_honest_sweep_r3.py:3987` | NEEDS-ALIAS | env-var name embeds the quality adjective "honest |
| 107 | `_depth_d8_true_drop` | `_depth_d8_drop_not_sink` | `scripts/run_honest_sweep_r3.py:452` | SAFE-static | true is an emphasis/quality adjective ("true drop" vs sink); reads as boastful rather than descriptive |
| 108 | `_contradiction_render_honest_enabled` | `_contradiction_render_verbatim_enabled` | `scripts/run_honest_sweep_r3.py:4855` | SAFE-static | honest is a quality/marketing adjective; the flag gates a verbatim render mode, not a truth property |
| 109 | `PG_CONTRADICTION_RENDER_HONEST` | `PG_CONTRADICTION_RENDER_VERBATIM` | `scripts/run_honest_sweep_r3.py:4856` | NEEDS-ALIAS | env-var name embeds the quality adjective "honest |
| 110 | `_depth_true_drop_when_all_verified` | `_depth_drop_when_all_verified` | `scripts/run_honest_sweep_r3.py:564` | SAFE-static | true_drop embeds the emphasis adjective "true |
| 111 | `_ARTIFACT_KIND_REFUSAL` | `_ARTIFACT_KIND_DECLINED (value "declined-refusal")` | `scripts/run_honest_sweep_r3.py:6650` | NEEDS-ALIAS | value string "honest-refusal" embeds the quality adjective "honest"; user-facing artifact kind reads as a self-praising quality claim |
| 112 | `_ARTIFACT_KIND_HEADINGS` | `value "Declined — no report produced"` | `scripts/run_honest_sweep_r3.py:6700` | SAFE-static | heading value "Honest refusal" embeds the quality adjective "honest |
| 113 | `token_honesty (manifest key / module concept)` | `token_accounting` | `scripts/run_honest_sweep_r3.py:9279` | NEEDS-ALIAS | same "honesty" framing propagated into a serialized manifest field name, visible to an external reviewer of run artifacts |
| 114 | `reset_token_honesty_telemetry` | `reset_token_accounting_telemetry` | `scripts/run_honest_sweep_r3.py:9281` | SAFE-static | honesty is a quality/marketing adjective baked into a function name… |
| 115 | `run_live_honest_cycle.py` | `run_live_verified_cycle.py` | `scripts/run_live_honest_cycle.py:1` | NEEDS-ALIAS | marketing adjective "honest" implies other pipelines are dishonest; vague self-praise not a domain term |
| 116 | `LIVE_HONEST` | `LIVE_VERIFIED` | `scripts/run_live_honest_cycle.py:98` | NEEDS-ALIAS | run_id prefix embeds the "honest" marketing adjective in artifact identifiers |
| 117 | `run_m_live_2_beat_both.py` | `-` | `scripts/run_m_live_2_beat_both.py:1` | DOMAIN-REVIEW | same BEAT-BOTH framework name, used descriptively/consistently as the actual comparison methodology, not vague hype |
| 118 | `BEAT_BOTH_SCORERS` | `-` | `scripts/run_m_live_2_beat_both.py:37` | DYNAMIC-HAZARD | beat-both reads as marketing bravado but is a real, consistently-implemented competitive-benchmark methodology (POLARIS vs two named competitors) documented in … |
| 119 | `run_r5_rerun.py` | `run_denylist_subject_content_starved_fixes_rerun.py` | `scripts/run_r5_rerun.py:1` | FILE-RENAME | cryptic round-number marker "R-5" with no domain meaning; reads as an internal iteration label, not a stable script name |
| 120 | `run_r6_validation.py` | `run_gap_fix_validation.py` | `scripts/run_r6_validation.py:1` | FILE-RENAME | cryptic round-number marker "R-6" with no domain meaning carried into the filename |
| 121 | `V1_ARCHIVE_DIR` | `PREVIOUS_RUN_ARCHIVE_DIR` | `scripts/screenshot_all_states.py:44` | SAFE-static | bare "V1" version marker baked into a persistent directory-path constant |
| 122 | `ui_review_v2.pdf` | `ui_review.pdf` | `scripts/screenshot_all_states.py:45` | NEEDS-ALIAS | bare "v2" version marker in the deliverable output filename (PDF_OUTPUT path) |
| 123 | `visual_final.py` | `visual_full_viewport_capture.py` | `scripts/visual_final.py:1` | FILE-RENAME | final is a temporal/version marker (this-version-is-the-last-one framing) rather than a descriptive name of what the script does (tall-viewport visual capture) |
| 124 | `MONEY-TRAP / money-trap (docstring term)` | `budget-leak gate / spend-before-verification bug` | `src/polaris_graph/adequacy/__init__.py:3` | DOMAIN-REVIEW | informal slang label ("MONEY-TRAP") used repeatedly as if it were a formal defect/pattern name in docstrings across the module… |
| 125 | `HonestSweepJobRunner` | `SweepJobRunner` | `src/polaris_graph/audit_ir/__init__.py:29` | NEEDS-ALIAS | marketing/quality adjective "Honest" used in a class name implying other runners are dishonest; unprofessional for external review |
| 126 | `HonestSweepJobRunnerConfig` | `SweepJobRunnerConfig` | `src/polaris_graph/audit_ir/__init__.py:30` | NEEDS-ALIAS | same "Honest" adjective issue, propagated to config class name |
| 127 | `make_default_honest_sweep_job_runner` | `make_default_sweep_job_runner` | `src/polaris_graph/audit_ir/__init__.py:32` | NEEDS-ALIAS | same "honest" adjective issue in factory function name |
| 128 | `honest_sweep_job_runner.py` | `v30_sweep_job_runner.py` | `src/polaris_graph/audit_ir/honest_sweep_job_runner.py:1` | FILE-RENAME | module name uses marketing/quality adjective "honest" instead of describing what the module does (wraps the V30 sweep as a subprocess job) |
| 129 | `HonestSweepJobRunner` | `V30SweepJobRunner` | `src/polaris_graph/audit_ir/honest_sweep_job_runner.py:177` | NEEDS-ALIAS | class name embeds "Honest" quality-adjective instead of describing the runner (wraps a V30 sweep subprocess) |
| 130 | `make_default_honest_sweep_job_runner` | `make_default_v30_sweep_job_runner` | `src/polaris_graph/audit_ir/honest_sweep_job_runner.py:450` | NEEDS-ALIAS | factory function name inherits the "honest" adjective from the class/module |
| 131 | `beat_both_scorer.py` | `head_to_head_dimension_scorer.py` | `src/polaris_graph/benchmark/beat_both_scorer.py:1` | DYNAMIC-HAZARD | informal competitive-marketing codename ("beat both" ChatGPT/Gemini) as a module name… |
| 132 | `BEAT-BOTH` | `HEAD_TO_HEAD` | `src/polaris_graph/benchmark/beat_both_scorer.py:3` | DYNAMIC-HAZARD | informal marketing/competitive codename embedded in docstring, mirrors the banned scorer name |
| 133 | `BEAT-BOTH` | `head-to-head benchmark` | `src/polaris_graph/benchmark/benchmark_config.py:1` | TEXT-ONLY | docstring references the informal "BEAT-BOTH" codename for slice 005 |
| 134 | `beat_both_scorer` | `head-to-head scorer` | `src/polaris_graph/benchmark/claim_dedup.py:1` | DYNAMIC-HAZARD | docstring calls the module "the beat-both scorer" (informal competitive codename) as the consumer of this dedup pass |
| 135 | `BEAT-BOTH` | `head-to-head benchmark` | `src/polaris_graph/benchmark/dimension_scorers.py:1` | TEXT-ONLY | module docstring names the informal "BEAT-BOTH" competitive codename |
| 136 | `beat-both scorer` | `head-to-head scorer` | `src/polaris_graph/benchmark/extended_metrics.py:1` | TEXT-ONLY | docstring title uses informal "beat-both scorer" codename for the metric-extension module |
| 137 | `BEAT-BOTH` | `head-to-head scoring` | `src/polaris_graph/benchmark/external_loader.py:1` | TEXT-ONLY | docstring references informal "BEAT-BOTH scoring" codename |
| 138 | `pathB_capture.py` | `benchmark_run_capture.py` | `src/polaris_graph/benchmark/pathB_capture.py:1` | FILE-RENAME | mixed-case "pathB" segment violates snake_case module-naming convention and is a vague internal-plan codename ("Path B") rather than a descriptive name |
| 139 | `pathB_runner.py` | `benchmark_gate_runner.py` | `src/polaris_graph/benchmark/pathB_runner.py:1` | FILE-RENAME | mixed-case "pathB" segment violates snake_case convention and is a vague internal-plan codename rather than a descriptive name |
| 140 | `POLARIS BEAT-BOTH` | `POLARIS Benchmark Report` | `src/polaris_graph/benchmark/report_renderer.py:126` | SAFE-static | HTML/markdown title literal embeds informal competitive marketing codename "BEAT-BOTH" shown to demo viewers |
| 141 | `is_row_content_junk` | `is_row_content_low_quality` | `src/polaris_graph/generator/junk_deletion_gate.py` | DYNAMIC-HAZARD | referenced module also defines is_row_content_junk using the same "junk" slang term for what is actually a content-quality/off-topic classifier |
| 142 | `junk_deletion_gate.py` | `content_integrity_deletion_gate.py` | `src/polaris_graph/generator/junk_deletion_gate.py:1` | DYNAMIC-HAZARD | colloquial "junk" as a module name in an external client-facing codebase… |
| 143 | `is_row_content_junk` | `is_row_content_integrity_violation` | `src/polaris_graph/generator/junk_deletion_gate.py:105` | DYNAMIC-HAZARD | uses slang "junk" in a public function name |
| 144 | `junk_deletion_gate (module)` | `off_topic_deletion_gate` | `src/polaris_graph/generator/multi_section_generator.py:10673` | DYNAMIC-HAZARD | Slang word "junk" used as a real module/import name in production code path (imported here to call is_row_deletable_offtopic)… |
| 145 | `_uncovered_fact_disclosure_is_junk` | `_uncovered_fact_disclosure_is_low_quality` | `src/polaris_graph/generator/verified_compose.py:1771` | SAFE-static | informal slang "is_junk" as a predicate name |
| 146 | `_JUNK_SCREEN` | `_CHROME_SCREEN_FN` | `src/polaris_graph/generator/verified_compose.py:377` | SAFE-static | informal slang "junk" used as a global cache variable name in client-facing code |
| 147 | `_compose_junk_screen` | `_compose_boilerplate_screen` | `src/polaris_graph/generator/verified_compose.py:380` | SAFE-static | informal slang "junk" in a widely-reused function name (chrome/boilerplate screen) |
| 148 | `_base_junk` | `_is_base_boilerplate_chrome` | `src/polaris_graph/generator/weighted_enrichment.py:3072` | SAFE-static | junk is vague/informal slang for a boilerplate-detection predicate |
| 149 | `_is_new_chrome_category` | `_is_i_wire_012_chrome_category` | `src/polaris_graph/generator/weighted_enrichment.py:3185` | SAFE-static | uses temporal marker "new" (ages poorly, does not describe function) instead of naming the actual chrome-category source (I-wire-012 categories) |
| 150 | `_make_junk_screen` | `_make_chrome_screen` | `src/polaris_graph/generator/weighted_enrichment.py:4825` | SAFE-static | junk is vague/informal slang; function returns the shared chrome/boilerplate predicate |
| 151 | `is_junk` | `is_chrome_or_junk_screen -> rename to is_chrome_screen` | `src/polaris_graph/generator/weighted_enrichment.py:5212` | SAFE-static | local var named with vague/informal "junk" (bound to _make_junk_screen() result) instead of describing it as a chrome/boilerplate predicate |
| 152 | `honest_pipeline.py` | `provenance_verified_pipeline.py` | `src/polaris_graph/honest_pipeline.py:1` | FILE-RENAME | marketing/quality adjective "honest" implies other pipelines are dishonest |
| 153 | `run_honest_pipeline` | `run_provenance_verified_pipeline` | `src/polaris_graph/honest_pipeline.py:173` | SAFE-static | function name carries "honest" marketing adjective |
| 154 | `honest_sweep_integration.py` | `v30_sweep_integration.py or frame_coverage_sweep_integration.py` | `src/polaris_graph/honest_sweep_integration.py:1` | FILE-RENAME | marketing/quality adjective "honest" in filename |
| 155 | `run_v30_post_generation` | `run_frame_coverage_post_generation` | `src/polaris_graph/honest_sweep_integration.py:156` | SAFE-static | bare version number "v30" used as the core function identifier |
| 156 | `_ENABLED_ENV / PG_V30_ENABLED` | `PG_FRAME_COVERAGE_ENABLED` | `src/polaris_graph/honest_sweep_integration.py:92` | NEEDS-ALIAS | bare version number "V30" baked into an env-var/const name |
| 157 | `merge_v30_into_manifest` | `merge_frame_coverage_into_manifest` | `src/polaris_graph/honest_sweep_integration.py:99` | SAFE-static | bare version number "v30" in function name |
| 158 | `build_and_run_v4` | `build_and_run_pipeline_a_ui (or run_ui_pipeline)` | `src/polaris_graph/pipeline_a_ui_adapter.py:187` | TEXT-ONLY | bare version-number suffix ("v4") as a function name in an external review reads as an internal-milestone marker rather than a descriptive name… |
| 159 | `_relevance_honest_drop_enabled` | `_relevance_actual_drop_logging_enabled` | `src/polaris_graph/retrieval/evidence_selector.py:1876` | DOMAIN-REVIEW | honest reads as an informal/marketing qualifier in an external review… |
| 160 | `_jo_doi` | `_journal_only_doi` | `src/polaris_graph/retrieval/live_retriever.py:7142` | SAFE-static | cryptic two-letter internal codename "jo" (journal_only) prefixing many names |
| 161 | `_w5_loop_idx` | `_llm_tiering_batch_index` | `src/polaris_graph/retrieval/live_retriever.py:7192` | SAFE-static | internal wave-codename "W5" baked into variable name, meaningless out of context |
| 162 | `_w2_weight` | `_content_relevance_weight` | `src/polaris_graph/retrieval/live_retriever.py:7220` | SAFE-static | internal wave-codename "W2" baked into variable name |
| 163 | `_w2_label` | `_content_relevance_label` | `src/polaris_graph/retrieval/live_retriever.py:7221` | SAFE-static | internal wave-codename "W2 |
| 164 | `_m2_dt` | `_stamp_document_genre` | `src/polaris_graph/retrieval/live_retriever.py:7261` | SAFE-static | cryptic internal codename "M2" plus abbreviation "dt" (document-type stamp function alias) |
| 165 | `_jo_doi_resolved` | `_journal_only_doi_resolved` | `src/polaris_graph/retrieval/live_retriever.py:7304` | SAFE-static | cryptic abbreviation "jo |
| 166 | `_jo_doi_m` | `_journal_only_doi_match` | `src/polaris_graph/retrieval/live_retriever.py:7306` | SAFE-static | cryptic abbreviation "jo" plus terse "m" (regex match) |
| 167 | `_jo_canon` | `_journal_only_canon_url` | `src/polaris_graph/retrieval/live_retriever.py:7309` | SAFE-static | cryptic abbreviation "jo" for a canonicalization helper |
| 168 | `_u21_repaired` | `_empty_fetch_repaired` | `src/polaris_graph/retrieval/live_retriever.py:7339` | SAFE-static | internal ticket-number "U21" embedded in variable name, cryptic to external readers |
| 169 | `_u21_recovered` | `_recovered_from_refetch` | `src/polaris_graph/retrieval/live_retriever.py:7341` | SAFE-static | internal ticket-number "U21" embedded in variable name |
| 170 | `_cf_quote` | `_cleaned_fetch_result` | `src/polaris_graph/retrieval/live_retriever.py:7572` | SAFE-static | cryptic abbreviation "cf" (clean_fetch) baked into name |
| 171 | `_pd_res` | `_pubdate_resolved_flag` | `src/polaris_graph/retrieval/live_retriever.py:7678` | SAFE-static | cryptic two-letter abbreviations, unclear meaning ("pd res") |
| 172 | `_w5_tier_batch_idx` | `_tier_batch_index` | `src/polaris_graph/retrieval/live_retriever.py:7774` | SAFE-static | internal wave-codename "W5" baked into variable/dict-key name |
| 173 | `_b4_relevance_weights` | `_relevance_gate_weights` | `src/polaris_graph/retrieval/live_retriever.py:7783` | SAFE-static | internal codename "B4" baked into variable name |
| 174 | `_row0` | `_zero_weight_row` | `src/polaris_graph/retrieval/live_retriever.py:7916` | SAFE-static | terse numeric-suffix name instead of descriptive name (this is the zero-weight disclosed row) |
| 175 | `_auth0` | `_zero_weight_authority` | `src/polaris_graph/retrieval/live_retriever.py:7935` | SAFE-static | terse numeric-suffix name distinguishing a second authority-score computation |
| 176 | `_mv_now` | `_match_validate_snapshot_now` | `src/polaris_graph/retrieval/live_retriever.py:7963` | SAFE-static | cryptic abbreviation "mv" plus vague "now |
| 177 | `_mv_checked` | `_match_validate_checked` | `src/polaris_graph/retrieval/live_retriever.py:7964` | SAFE-static | cryptic two-letter abbreviation "mv" (match_validate) baked into name |
| 178 | `_mv_rejected` | `_match_validate_rejected` | `src/polaris_graph/retrieval/live_retriever.py:7965` | SAFE-static | cryptic abbreviation "mv |
| 179 | `_mv_failopen` | `_match_validate_failopen` | `src/polaris_graph/retrieval/live_retriever.py:7966` | SAFE-static | cryptic abbreviation "mv |
| 180 | `_w2_on` | `_content_relevance_enabled_flag` | `src/polaris_graph/retrieval/live_retriever.py:8057` | SAFE-static | internal wave-codename "W2 |
| 181 | `_b4_gate` | `_relevance_gate` | `src/polaris_graph/retrieval/live_retriever.py:8146` | SAFE-static | internal codename "B4 |
| 182 | `_w2_report` | `_content_relevance_report` | `src/polaris_graph/retrieval/live_retriever.py:8150` | SAFE-static | internal wave-codename "W2 |
| 183 | `state_v3.py` | `state_lightweight.py or pipeline_state.py` | `src/polaris_graph/state_v3.py:1` | FILE-RENAME | temporal/version marker "_v3" baked into filename for what is just the current pipeline state module |
| 184 | `create_v3_state` | `create_lightweight_state` | `src/polaris_graph/state_v3.py:64` | SAFE-static | version-marker function name ("v3") rather than descriptive name |
| 185 | `report_assembler_v2.py` | `grounded_bibliography_assembler.py (or merge into report_assembler.py)` | `src/polaris_graph/synthesis/report_assembler_v2.py` | FILE-RENAME | version-suffixed filename ("_v2") coexisting with report_assembler.py; unclear which is canonical/current to an external reviewer |
| 186 | `synthesizer_v2.py` | `section_synthesizer_parallel.py` | `src/polaris_graph/synthesis/synthesizer_v2.py:1` | FILE-RENAME | version marker "v2" in filename and module docstring ("v2 Section Synthesizer") for an external review; not a real domain term, just an iteration label |
| 187 | `verifier_v2.py` | `verifier.py` | `src/polaris_graph/synthesis/verifier_v2.py:1` | FILE-RENAME | version marker "_v2" in filename with no v1/v3 distinguishing meaning left in the codebase |
| 188 | `honest-rebuild` | `pipeline A / rebuild pipeline` | `src/polaris_graph/telemetry/__init__.py:1` | TEXT-ONLY | docstring/pipeline codename "honest-rebuild pipeline" uses marketing-style self-praising adjective "honest" as a proper pipeline name |
| 189 | `honest-rebuild run` | `pipeline-A run` | `src/polaris_graph/telemetry/tool_tracer.py:4` | SAFE-static | same "honest-rebuild" marketing-adjective codename reused as a run descriptor |
| 190 | `mineru_firing` | `mineru_degraded` | `src/polaris_graph/telemetry/tool_tracer.py:461` | NEEDS-ALIAS | slangy manifest key name "mineru_firing" (colloquial "fires/firing") for what is really a degrade-disclosure flag |
| 191 | `mineru_fire_canary_enabled` | `mineru_degrade_canary_enabled` | `src/polaris_graph/telemetry/tool_tracer.py:469` | SAFE-static | informal "fire" verb combined with jargon "canary" in a public function name |
| 192 | `contracts_v3` | `contracts (or descriptive submodule name)` | `src/polaris_graph/tools/analysis_notebook.py:14` | SAFE-static | version-numbered module import name "contracts_v3" is a temporal marker, not a description of contents |
| 193 | `GEMINI-ARCH 2A` | `Python analysis (structured data)` | `src/polaris_graph/tools/data_analyzer.py:2` | NEEDS-ALIAS | module docstring/log-tag names a competitor product ("Gemini") as an internal codename, repeated in every log line |
| 194 | `HONEST-REBUILD Phase 2f` | `Rebuild Phase 2f` | `src/polaris_graph/tools/openalex_client.py:78` | TEXT-ONLY | docstring for authority_tier_t7 uses marketing-style self-praising codename "HONEST-REBUILD |
| 195 | `_TEMPLATE_ECHO_DEMONSTRATES` | `_TEMPLATE_ECHO_SUBJECT_PREDICATE` | `src/polaris_graph/tools/react_agent.py:172` | TEXT-ONLY | internal patch-history name (D2-FIX) baked into a permanent identifier via comment/adjacent naming convention… |
| 196 | `_R5_LEGIT_DOUBLES` | `_LEGITIMATE_DOUBLED_WORDS` | `src/polaris_graph/tools/react_agent.py:221` | SAFE-static | cryptic ticket-label prefix (R5) on a real constant; unclear to external reviewer |
| 197 | `_R6_SCI_LENS_WORDS` | `_SCIENTIFIC_LENS_CONTEXT_WORDS` | `src/polaris_graph/tools/react_agent.py:224` | SAFE-static | cryptic ticket-label prefix (R6) on a real constant |
| 198 | `_R3_SCALE_WORDS` | `_SCALE_TRANSFORM_WORDS` | `src/polaris_graph/tools/react_agent.py:231` | SAFE-static | cryptic ticket-label prefix (R3) used as a real module constant name, meaningless outside internal history |
| 199 | `_R7_TRANSITIVE_VERBS` | `_TRANSITIVE_VERBS` | `src/polaris_graph/tools/react_agent.py:238` | SAFE-static | cryptic ticket-label prefix (R7) on a real constant |
| 200 | `_R7_IRREGULAR_PP` | `_IRREGULAR_PAST_PARTICIPLES` | `src/polaris_graph/tools/react_agent.py:249` | SAFE-static | cryptic ticket-label prefix (R7) plus unexplained abbreviation PP (past participle) |
| 201 | `_R7_SINGULAR_S` | `_SINGULAR_WORDS_ENDING_IN_S` | `src/polaris_graph/tools/react_agent.py:267` | SAFE-static | cryptic ticket-label prefix (R7) on a real constant |
| 202 | `v30_contract_synthesizer.py` | `contract_synthesizer.py` | `src/polaris_graph/v30_contract_synthesizer.py:1` | FILE-RENAME | version marker "v30" baked into filename as a permanent identifier rather than a description of behavior |
| 203 | `build_v30_contract` | `build_report_contract` | `src/polaris_graph/v30_contract_synthesizer.py:78` | SAFE-static | version marker "v30" embedded in a permanent function name |
| 204 | `lethal.py` | `retrieval.py` | `src/polaris_graph/wiki/mesh/retrieve/lethal.py:1` | FILE-RENAME | informal/jokey adjective "lethal" used as the permanent name for the retrieval algorithm module, inappropriate for external client review |
| 205 | `lethal_scored` | `ranked_scored` | `src/polaris_graph/wiki/mesh/retrieve/lethal.py:210` | SAFE-static | jokey adjective "lethal" used as a variable name for the ranked-claims list |
| 206 | `lethal (local var)` | `composite_score` | `src/polaris_graph/wiki/mesh/retrieve/lethal.py:239` | SAFE-static | jokey adjective "lethal" used as the composite score variable name |
| 207 | `PG_LETHAL_SEED_K` | `PG_RETRIEVE_SEED_K` | `src/polaris_graph/wiki/mesh/retrieve/lethal.py:49` | NEEDS-ALIAS | jokey adjective "lethal" baked into an env-var constant name, user-facing configuration surface |
| 208 | `lethal_retrieve` | `retrieve_claims` | `src/polaris_graph/wiki/mesh/retrieve/lethal.py:94` | SAFE-static | jokey adjective "lethal" in a public API function name |
| 209 | `lethal_snowball_score` | `compute_snowball_score` | `src/polaris_graph/wiki/mesh/snowball.py:105` | SAFE-static | jokey adjective "lethal" combined into the composite-score function name, consistent with lethal.py naming issue |
| 210 | `EnhancedSourceScore` | `SourceQualityScore` | `src/polaris_graph/wiki/source_quality.py:74` | SAFE-static | marketing adjective "Enhanced" in a permanent class name rather than a description of what the class contains |

---

### Roll-up — exact integer counts per class (sums to precisely 210)

| codex class | Rows | Contract at risk |
|---|---|---|
| SAFE-static | 100 | none — `_`-private / function-local / comment-only identifier |
| TEXT-ONLY | 12 | none — docstring / comment / log-string text only |
| FILE-RENAME | 45 | module import path / `scripts/*.py` on-disk filename (§5.3) |
| NEEDS-ALIAS | 27 | operator env var, persisted string, or public import name |
| DYNAMIC-HAZARD | 10 | persisted row-state key / string-dispatched or many-importer string-imported module |
| DOMAIN-REVIEW | 16 | codex second-pass judgment calls (each reduces to one of the classes above) |
| **Total** | **210** | |

**Arithmetic (exact, no `~`):** `100 + 12 + 45 + 27 + 10 + 16 = 210`. This equals the 210 `RENAME` rows found in the worklist, so every RENAME row is accounted for exactly once.

**Reconciliation to the worklist `SAFETY` column** (also exact): the raw `SAFETY` distribution over the 210 RENAME rows is `105 SAFE + 12 TEXT-ONLY + 45 FILE-RENAME + 8 NEEDS-ALIAS(control-surface) + 24 NEEDS-ALIAS(control-surface/persisted) + 16 DOMAIN-REVIEW = 210`. The codex-class roll-up above is that distribution after two deterministic corrections: (a) **5** SAFE rows → NEEDS-ALIAS (the `HonestSweepJobRunner` cluster), so SAFE-static = 105 − 5 = **100** and the `8 + 24 = 32` NEEDS-ALIAS rows become `32 + 5 = 37`; (b) **10** of those 37 NEEDS-ALIAS rows → DYNAMIC-HAZARD, so NEEDS-ALIAS = 37 − 10 = **27** and DYNAMIC-HAZARD = **10**. Check: `100 + 12 + 45 + 27 + 10 + 16 = 210`. ✓

> **Nothing on the worklist touches `STAGE_TYPE_REGISTRY` module-path strings, `StageType` enum *values*, LangGraph node-name strings, the `pg_` thread-id prefix, FastAPI path literals, or wire `Literal[...]` values** (re-verified). Those remain live traps for *future* renames (§1.1, §2, §4.2) and stay on this checklist.

---

## 7. Conclusion — SAFE vs REQUIRES-ALIAS

**SAFE to rename** (static references only; IDE "rename symbol" is sufficient):
- Local variables and module-private (`_`-prefixed) helper functions (`_jo_doi`, `_JUNK_SCREEN`, `_make_junk_screen`, `_relevance_honest_drop_enabled`, …). These have no external import surface and serialize nothing.
- Router variables, handler functions, and other symbols behind FastAPI **path strings** (rename the symbol, keep the path).
- `str`-Enum **member names** (Python identifiers) as long as their **value strings** are unchanged.
- Ordinary intra-package modules/functions **after** confirming they are absent from the STAGE_TYPE_REGISTRY string table and from persisted state keys.

**REQUIRES AN ALIAS / versioning — never a naive rename:**
- **Every `PG_*` environment variable** that is a control surface — concretely the six on the worklist (§4.1). Provide a read-new-fall-back-to-old shim with a deprecation warning; update `config_defaults.py`, `.env.example`, compose/Helm, and any `run_gate_b.py` string-key dicts in lock-step.
- **Persisted-string constants:** the `pg_` checkpoint thread-id prefix, TypedDict field keys serialized into checkpoints (`registry_data`,`entries`,`counter`), LangGraph **node-name strings**, and any `StageType` / wire `Literal[...]` **value** — these are data-format changes requiring migration or schema-version bumps, not symbol renames.
- **External invocation names:** FastAPI route path literals and `scripts/*.py` filenames operators/CI call directly — treat as a deprecation with a redirect/shim, or coordinate the caller change.
- **Renamed public (non-underscore) class/factory names whose module is imported by external code and is not `__all__`-gated:** `ResearchStateV2`→`CragResearchState`, `V3State`→`LightweightResearchState`, `V30SweepResult`→`FrameCoverageSweepResult`, and the package-re-exported `HonestSweepJobRunner`/`HonestSweepJobRunnerConfig`/`make_default_honest_sweep_job_runner`. "Fields serialize, not the class name" clears only the checkpoint channel — it does **not** clear the import-name channel. Add a module-level backward-compat alias (`ResearchStateV2 = CragResearchState`) for ≥1 deprecation cycle; for the `audit_ir` names, keep the old symbol in `audit_ir/__init__.__all__` alongside the new one and update the `inspector_router.py:417` factory import in the same commit. Do **not** declare these SAFE on a "zero static importers" basis — a static grep cannot see importers outside this repo.

**Governing rule for the reviewer and for the rename pass:**

> A "0 static importers" result narrows the risk but does not clear it. Before renaming any symbol, additionally confirm it is **not** (1) a string in a dispatch/registry table, (2) an env-var literal, (3) a persisted state/enum/wire value, or (4) an externally-invoked route/filename. Only when all five channels are clear is a rename safe; otherwise it needs an alias or a versioned migration.
