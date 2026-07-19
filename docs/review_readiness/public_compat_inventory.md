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

**Source of truth:** `/home/polaris/polaris_project/NAME_RENAME_WORKLIST_validated.tsv`, 346 rows total = **210 `RENAME`** + 81 `KEEP` + 50 `KEEP-NOTED` + 4 `KEEP-BUT-NOTED` (counts verified with `awk`). Only the 210 `RENAME` rows can break a public-compat contract; the 135 `KEEP*` rows change nothing and are not enumerated here (they are "leave as-is" verdicts). Every `RENAME` row is dispositioned below under codex's four risk classes.

**How the worklist's own `SAFETY` column maps onto codex's four classes** (this is a 1:1 mapping, then hand-corrected for the public-class cases from §2.4):

| Worklist `SAFETY` value | Count (of 210) | codex class |
|---|---|---|
| `SAFE (symbol rename)` | 105 | **SAFE-static** (see caveat below) |
| `TEXT-ONLY (safe)` | 12 | **SAFE-static** (docstring/comment/log text only) |
| `FILE-RENAME (verify importers first)` | 45 | **FILE-RENAME-fix-importers** |
| `NEEDS-ALIAS (control-surface string)` + `NEEDS-ALIAS (control-surface/persisted string)` | 8 + 24 = 32 | **NEEDS-ALIAS** or **DYNAMIC-HAZARD** (split below) |
| `DOMAIN-REVIEW` | 16 | mixed — dispositioned individually below |
| **Total** | **210** | |

**Caveat on the 105 `SAFE (symbol rename)` rows (codex-relevant correction):** "SAFE" in the worklist means *the persistence channel is clear and the reference is a normal Python symbol a refactor tool follows.* For a **module-private (`_`-prefixed) name or a local variable, that is fully SAFE-static.** But **~a dozen of the 105 are public (non-underscore) functions/classes that are re-exported and imported cross-file** — an in-repo refactor tool moves the in-repo importers, but a static grep still cannot see an *out-of-repo* importer. The notable ones (verified importers this worktree):
- `lethal_retrieve` (`lethal.py:94`) — **re-exported** at `wiki/mesh/retrieve/__init__.py:4,11`, imported by `qa/ask.py:34`, `compose/composer.py`, `tests/integration/test_mesh_e2e.py`. Public API of the mesh package → treat as **NEEDS-ALIAS** (keep `lethal_retrieve = retrieve_claims` export), not bare SAFE.
- `run_honest_pipeline` (`honest_pipeline.py:173`) — imported by `scripts/run_honest_full_cycle.py:24` and `tests/battery/cases/calc_lane.py:251`.
- `run_v30_post_generation` / `merge_v30_into_manifest` (`honest_sweep_integration.py:156,99`) — imported by `scripts/run_honest_sweep_r3.py:20233-20234`.
- `HonestSweepJobRunner` / `make_default_honest_sweep_job_runner` (rows 217-219, 221-222, listed `SAFE` in the worklist) — **package-re-exported** (`audit_ir/__init__.py`); reclassified **NEEDS-ALIAS** in §2.4.
- `EnhancedSourceScore` (`source_quality.py:74`) — no in-repo importer of the symbol found; still a public class name → cheap alias recommended.

For all other `SAFE`/`TEXT-ONLY` rows — `_jo_*`, `_w2_*`, `_mv_*`, `_R7_*`, `dice`, `passced`, the per-launcher `_V##_ENV` constants, and the BEAT-BOTH docstring text — the name is `_`-private or local or comment-only: **SAFE-static, IDE rename is sufficient.**

---

### Class SAFE-static — 117 rows (105 `SAFE` + 12 `TEXT-ONLY`), minus the ~5 public-symbol exceptions promoted to NEEDS-ALIAS above

These touch none of §1–§5. Reason: module-private (`_`-prefixed) identifier, function-local variable, or comment/docstring/log-string text only. Representative roster (all rows in this class, grouped by file for brevity — full list is the worklist `SAFE`/`TEXT-ONLY` rows):

- **`scripts/run_honest_sweep_r3.py` private helpers/consts:** `_junk_ev_row_text:1187`, `_junk_ev_row_url:1196`, `_junk_ev_row_direct_quote:1203`, `_junk_src_url:1241`, `_screen_junk_evidence:1248`, `:14016`, `_detect_ci_junk:14655`, `_ci_zyte_saved:15675`, `_run_junk_deleted_disclosed:15745`, `_junk_deleted_for_disclosure:15760`, `build_known_words_from_evidence:17850`, `apply_honest_scorecard_to_manifest:21366`, `_PAID_PATH_WINNER_FLAGS:21675`, `_depth_d8_true_drop:452`, `_contradiction_render_honest_enabled:4855`, `_depth_true_drop_when_all_verified:564`, `_ARTIFACT_KIND_HEADINGS:6700`, `reset_token_honesty_telemetry:9281`.
- **`retrieval/live_retriever.py` locals (all `_`-private, function-local):** `_jo_doi:7142`, `_w5_loop_idx:7192`, `_w2_weight:7220`, `_w2_label:7221`, `_m2_dt:7261`, `_jo_doi_resolved:7304`, `_jo_doi_m:7306`, `_jo_canon:7309`, `_u21_repaired:7339`, `_u21_recovered:7341`, `_cf_quote:7572`, `_pd_res:7678`, `_w5_tier_batch_idx:7774`, `_b4_relevance_weights:7783`, `_row0:7916`, `_auth0:7935`, `_mv_now:7963`, `_mv_checked:7964`, `_mv_rejected:7965`, `_mv_failopen:7966`, `_w2_on:8057`, `_b4_gate:8146`, `_w2_report:8150`.
- **`generator/*` private predicates/caches:** `_uncovered_fact_disclosure_is_junk` (`verified_compose.py:1771`), `_JUNK_SCREEN:377`, `_compose_junk_screen:380`, `_base_junk` (`weighted_enrichment.py:3072`), `_is_new_chrome_category:3185`, `_make_junk_screen:4825`, `is_junk:5212` (local var).
- **`tools/react_agent.py` `_`-private constants:** `_R5_LEGIT_DOUBLES:221`, `_R6_SCI_LENS_WORDS:224`, `_R3_SCALE_WORDS:231`, `_R7_TRANSITIVE_VERBS:238`, `_R7_IRREGULAR_PP:249`, `_R7_SINGULAR_S:267`, `_TEMPLATE_ECHO_DEMONSTRATES:172` (text-only).
- **Per-launcher duplicated constants:** `_V10_ENV` … `_V30_PHASE2_ENV` across `scripts/run_full_scale_v*.py` (module-private, one per file).
- **`wiki/mesh` locals:** `lethal_scored` (`lethal.py:210`), `lethal` local (`lethal.py:239`), `lethal_snowball_score` (`snowball.py:105`, module-private-ish helper).
- **Diagnostic/harness locals & consts:** `OpenAIShimClient` (retired dir), `passced`, `rhsr_patched`, `rhsr3_canary`, `_BANKED_RUN`, `_R`, `an`, `wfe`, `cw_cov`, `ej`, `verds`, `_REFY`, `_is_junk`, `junk`, `_GARBAGE_URL`, `_SYN`, `_check_redaction_landmine`, `bad`, `cs`, `hs`, `dice`, `V1_ARCHIVE_DIR`.
- **Text/docstring/log-only (`TEXT-ONLY`):** `Gemini-class` (`deep_gemini_verify.py:2`), `real box2 junk fixtures` (`_wave2_assert.py:1`), `_run_honest_sweep_r3` comment (`iwire014_quantified_replay.py:63`), `build_and_run_v4` (`live_server.py:557`, `pipeline_a_ui_adapter.py:187`), the four `BEAT-BOTH` docstring rows (`benchmark/benchmark_config.py:1`, `dimension_scorers.py:1`, `extended_metrics.py:1`, `external_loader.py:1`), `honest-rebuild` (`telemetry/__init__.py:1`), `HONEST-REBUILD Phase 2f` (`openalex_client.py:78`), `POLARIS BEAT-BOTH` HTML title (`report_renderer.py:126`), `honest-rebuild run` (`tool_tracer.py:4`), `mineru_fire_canary_enabled` (`tool_tracer.py:469`), `contracts_v3` import-alias (`analysis_notebook.py:14`).

> One-line reason for the whole class: **name is `_`-private / function-local / comment-text → no import-name contract, no persisted value, no string dispatch. IDE "rename symbol" (plus moving in-repo comment text) is sufficient.**

---

### Class FILE-RENAME-fix-importers — 45 rows

Renaming the **file** changes the module import path; every `import`/`from … import` of it must move in the same commit. These are ordinary multi-file refactors (a refactor tool follows in-repo importers), **but** for `scripts/*.py` the *filename itself* is an external invocation contract (§5.3 — grep CI/compose/docs first), and for `src/…` modules confirm the module is absent from `STAGE_TYPE_REGISTRY` (§1.1) before renaming.

**`src/polaris_graph/**` module renames (live in-repo importers verified — must fix importers):**

| Worklist NAME | Location | Importers (this worktree) | One-line reason |
|---|---|---|---|
| `honest_sweep_job_runner.py` | `audit_ir/honest_sweep_job_runner.py:1` | re-exported `audit_ir/__init__.py:29-32`; import at `inspector_router.py:417` | module file rename; fix `__init__` re-export + factory import together (also NEEDS-ALIAS on the symbol, §2.4) |
| `pathB_capture.py` | `benchmark/pathB_capture.py:1` | referenced across `benchmark/*` | mixed-case + codename module rename; fix importers |
| `pathB_runner.py` | `benchmark/pathB_runner.py:1` | `benchmark/*` importers | fix importers |
| `honest_pipeline.py` | `honest_pipeline.py:1` | `scripts/run_honest_full_cycle.py:24`, `tests/battery/cases/calc_lane.py:251` | fix importers (also public func alias, §6.5 caveat) |
| `honest_sweep_integration.py` | `honest_sweep_integration.py:1` | `scripts/run_honest_sweep_r3.py:20231-20234` | **do the `PG_V30_ENABLED` env alias in the same pass** (§4.1) |
| `state_v3.py` | `state_v3.py:1` | `graph_v3.py:25`, `tests/v3/test_graph.py` | fix importers; `V3State` public class also alias-recommended (§2.4) |
| `report_assembler_v2.py` | `synthesis/report_assembler_v2.py` | in-repo importer(s) | fix importers |
| `synthesizer_v2.py` | `synthesis/synthesizer_v2.py:1` | in-repo importer(s) | fix importers |
| `verifier_v2.py` | `synthesis/verifier_v2.py:1` | in-repo importer(s) | fix importers |
| `v30_contract_synthesizer.py` | `v30_contract_synthesizer.py:1` | in-repo importer(s) | fix importers |
| `lethal.py` | `wiki/mesh/retrieve/lethal.py:1` | re-exported `retrieve/__init__.py:4`, `qa/ask.py:34`, `tests/integration/test_mesh_e2e.py:31` | module rename; also `PG_LETHAL_SEED_K` env alias + `lethal_retrieve` symbol alias in same pass |

**`scripts/*.py` file renames (34 rows) — filename is the invocation contract (§5.3):** `_basket_workers_ab_cert.py`, `_m54_append_contract.py`, `_retired_2026_06_14/` (dir), `_v24_compare.py`, `audit_v3_report.py`, `compare_live_vs_pg_lb_sa_02.py`, `compose_agentic_report_s3gear329.py`, `deep_gemini_verify.py`, `i_naming_001_migrate.py`, `iarch007_behavioral_canary.py`, `iarch007_release_invariant_check.py`, `iarch010_replay_breadth_faithfulness_harness.py`, `iarch011_b11_compose_repetition_harness.py`, `iarch011_binding_and_judge_probe.py`, `iarch011_fixb_pair_dump.py`, `pipeline_diced_preflight.py` (row `DICED`), `playwright_fire_test.py`, `run_full_scale_v10.py`, `…v23.py`, `…v24.py`, `…v25.py`, `…v26.py`, `…v27.py`, `…v28.py`, `…v29.py`, `…v30_phase2.py`, `run_honest_sweep_r3.py` (rows 134/159, and the *referenced-module* rows at `harness_render_boundary_screen.py:53`, `iarch007_behavioral_canary.py:21`, `run_honest_sweep_r3.py:20231` importing `honest_sweep_integration`), `run_r5_rerun.py`, `run_r6_validation.py`, `visual_final.py`.
> One-line reason: **the file's module path (and, for `scripts/`, its on-disk filename) is referenced by importers/CI/compose. Grep those references and move them atomically; not a hidden dynamic hazard, but not a single-file edit either.**

---

### Class NEEDS-ALIAS — env-vars, persisted keys, run-id / manifest / label strings (the 32 `NEEDS-ALIAS` rows, split into ALIAS vs DYNAMIC-HAZARD)

**NEEDS-ALIAS (env/enum/persisted string — read-new-fall-back-to-old shim; no data on disk keyed by it):**

| Worklist NAME → target | Location (re-verified this worktree) | One-line reason |
|---|---|---|
| `PG_V2_ENABLED` → `PG_LEGACY_GRAPH_ENABLED` | `scripts/live_server.py:560` (`os.getenv("PG_V2_ENABLED","0")`) | operator env control surface; silent fallback on rename |
| `PG_JUNK_SOURCE_SCREEN` → `PG_LOW_QUALITY_SOURCE_SCREEN` | `scripts/run_honest_sweep_r3.py:1280` (+ kill-switch comments :1185,:12192,:13388) | env **kill-switch** (`=0` reverts, LAW VI); rename removes documented off-switch |
| `PG_CONTRADICTION_RENDER_HONEST` → `…_VERBATIM` | `scripts/run_honest_sweep_r3.py:4856` | env kill-switch |
| `PG_S15_CORROBORATED_HONEST_LABEL` → `…_ORIGIN_LABEL` | `scripts/run_honest_sweep_r3.py:3987` **and** string dict keys `run_gate_b.py:643,2086,2407,3988` | env control surface **+** string-keyed gate dict (§2.2) — alias + update all four dict keys together |
| `PG_V30_ENABLED` (`_ENABLED_ENV`) → `PG_FRAME_COVERAGE_ENABLED` | `honest_sweep_integration.py:92,96` | env control surface; not in `config_defaults.py` |
| `PG_LETHAL_SEED_K` → `PG_RETRIEVE_SEED_K` | `lethal.py:50` (`resolve("PG_LETHAL_SEED_K")`) **+** `config_defaults.py:390` (`'80'`) | **in the central registry**; alias + edit both registry entry and call site. **LINE DRIFT: worklist row 343 cites `lethal.py:49`; the `resolve()` literal is on `:50` in this worktree.** |
| `PG_TEST_060_BTG` html path (`dashboard_PG_TEST_060_BTG.html`) | `scripts/dashboard_visual_audit.py:30` | hardcoded output-path literal; alias/redirect the filename |
| `slice_005_beat_both_benchmark` → `…_comparative_benchmark` | `scripts/demo_smoke.py:38` | health-check identifier consumed as an API/monitoring key |
| `token_explosion` → `high_output_token_count` | `scripts/live_monitor.py:654` | rule label; monitoring config may key on it |
| `Legacy run, pre-honest-rebuild` (mode_label) | `scripts/migrate_old_runs.py:59` | **persisted `mode_label` string** written into run records |
| `_honest_rebuild_migration` (migration-marker key) | `scripts/migrate_old_runs.py:60` | **stored migration marker** — old records carry the old key |
| `_WINNER_SLATE_ON_PAID_PATH_ENV` → `_ENRICHMENT_…` | `scripts/run_honest_sweep_r3.py:21674` | env-const name (paired with the function pair below) |
| `winner_slate_on_paid_path_enabled` → `enrichment_…` | `scripts/run_honest_sweep_r3.py:21689` | reads the env const above; move together |
| `apply_winner_slate_on_paid_path` → `apply_enrichment_…` | `scripts/run_honest_sweep_r3.py:21696` | same slate; move together |
| `_ARTIFACT_KIND_REFUSAL` (value `"honest-refusal"`) → `"declined-refusal"` | `scripts/run_honest_sweep_r3.py:6650` | **user-facing artifact-kind value string** persisted into run artifacts |
| `token_honesty` (manifest key) → `token_accounting` | `scripts/run_honest_sweep_r3.py:9279` | **serialized manifest field name** |
| `run_live_honest_cycle.py` → `run_live_verified_cycle.py` | `scripts/run_live_honest_cycle.py:1` | file rename **+** it drives `LIVE_HONEST` run-id prefix (below) |
| `LIVE_HONEST` (run-id prefix) → `LIVE_VERIFIED` | `scripts/run_live_honest_cycle.py:98` | **run-id prefix baked into persisted artifact identifiers** |
| `ui_review_v2.pdf` → `ui_review.pdf` | `scripts/screenshot_all_states.py:45` | deliverable output filename; downstream consumers reference it |
| `mineru_firing` → `mineru_degraded` | `telemetry/tool_tracer.py:461` | **serialized manifest key** (degrade-disclosure flag) |
| `GEMINI-ARCH 2A` → "Python analysis" | `tools/data_analyzer.py:2` | log-tag repeated every log line; log-scrapers may key on it |
| `Gemini feature / GEMINI-ARCH` | `scripts/anti_tunnel_view_test.py:52` | tag baked into **state keys** + code-search patterns |

**DYNAMIC-HAZARD (string dispatch / persisted row-state key / module imported by string) — subset of the above needing extra care beyond a simple env alias:**

| Worklist NAME | Location | Why it is a DYNAMIC-HAZARD, not just an alias |
|---|---|---|
| `content_integrity_junk` → `content_integrity_defect` | `scripts/run_honest_sweep_r3.py:15688` **and** `generator/junk_deletion_gate.py:110,244,270` | **persisted row-state dict key** — `row["content_integrity_junk"]` is written, read, and embedded into deletion **reason strings** (`"content_integrity_junk:" + …`). Renaming the key silently drops the flag on any in-flight/replayed row and changes disclosure reason strings. Rename the *stamp*, the *reader*, and the *reason prefix* atomically; alias the read side. |
| `junk_deletion_gate` module → `nonsource_deletion_gate` | `scripts/run_honest_sweep_r3.py:15747` (imports the module by name) | string/import module reference; the real module is renamed in §6.5 FILE-RENAME (`junk_deletion_gate.py`, 6 importers) — keep this reference in lock-step |
| `beat_both_scorer.py` → `head_to_head_dimension_scorer.py` | `benchmark/beat_both_scorer.py:1` | module rename with **10+ importers** (`report_renderer.py`, `claim_audit_scorer.py`, `scripts/aggregate_beat_both_runs.py`, `scripts/run_benchmark.py`, 4 test files); the codebase already calls it "the banned/rigged beat_both_scorer" — mass importer fix, alias the module |
| `BEAT-BOTH` / `beat_both_scorer` docstring refs | `beat_both_scorer.py:3`, `claim_dedup.py:1` | mirror the module rename above |
| `BEAT_BOTH_SCORERS` | `scripts/run_m_live_2_beat_both.py:37` | scorer-slate const consumed by the benchmark methodology; move with the module rename |
| `is_row_content_junk` → `is_row_content_low_quality` / `…_integrity_violation` | `generator/junk_deletion_gate.py:105` (def) + module docstring ref | **public function of a module with 6 importers**; the two worklist rows (105 + module-level) are the same function — alias the public name |
| `junk_deletion_gate.py` module → `content_integrity_deletion_gate.py` | `generator/junk_deletion_gate.py:1` | **6 importers** (`multi_section_generator.py`, `scripts/run_honest_sweep_r3.py`, `scripts/orchestrator_lab/*`, tests); alias module, fix importers |
| `junk_deletion_gate (module)` import | `generator/multi_section_generator.py:10673` (imports to call `is_row_deletable_offtopic`) | production-path import of the renamed module; lock-step |

> One-line reason for the class: **each name is a value that outlives the Python symbol — an operator's env var, a persisted row/manifest/run-id key, or a string-dispatched module — so a bare rename silently loses data or falls back to a default with no error. Provide an alias/shim or a versioned migration.**

---

### Class DOMAIN-REVIEW — 16 `RENAME` rows (codex's own second-pass verdict; dispositioned individually)

The worklist's `DOMAIN-REVIEW` + `codex:` annotations already resolve each of these to rename-or-keep. Their public-compat class:

| Worklist NAME | Location | Public-compat class | One-line reason |
|---|---|---|---|
| `lethal_retrieve` (import) | `scripts/_retired_2026_06_14/pg_mesh_preflight.py:28` | NEEDS-ALIAS | imports the public `lethal_retrieve` (aliased in §6.5 caveat); retired dir |
| `aggregate_beat_both_runs.py` | `scripts/aggregate_beat_both_runs.py:1` | FILE-RENAME-fix-importers | filename invocation contract; part of beat_both cluster |
| `strip_junk` | `scripts/dr_benchmark/pack_drb2.py:90` | SAFE-static | public-ish func but in a script; grep-confirm no cross-file caller before rename |
| `run_honest_sweep_r3` (import ref) ×4 | `iarch011_prb_…:51`, `iwire014_cwf_…:18`, `iwire014_quantified_replay.py:60`, `iwire014_render_proof.py:2` | FILE-RENAME-fix-importers | each imports the renamed sweep module; move with the file rename |
| `JUNK HEADER` (printed literal) | `iwire014_cwf_header_diagnostic.py:77` | SAFE-static | output text, not an identifier |
| `OFFLINE_DICE` | `scripts/pipeline_diced_preflight.py:838` | SAFE-static | module const in a script; part of the `dice`→`check` cleanup |
| `_gate_injected_prepend_rows` | `scripts/run_honest_sweep_r3.py:14426` | SAFE-static | `_`-private local |
| `_final_zyte` | `scripts/run_honest_sweep_r3.py:15664` | SAFE-static | `_`-private local (Zyte = real vendor, kept) |
| `_QUANTIFIED_HONEST_EMPTY_STATUSES` | `scripts/run_honest_sweep_r3.py:1846` | SAFE-static | `_`-private const |
| `honest_sweep_r3` (output-dir string) | `scripts/run_honest_sweep_r3.py:21826` | NEEDS-ALIAS | **default output-dir string** written to disk; tracks the file rename — keep old dir readable |
| `run_m_live_2_beat_both.py` | `scripts/run_m_live_2_beat_both.py:1` | FILE-RENAME-fix-importers | filename invocation contract; beat_both cluster |
| `MONEY-TRAP` (docstring term) | `src/polaris_graph/adequacy/__init__.py:3` | SAFE-static | docstring text only |
| `_relevance_honest_drop_enabled` | `src/polaris_graph/retrieval/evidence_selector.py:1876` | SAFE-static | `_`-private function |

> One-line reason: **codex re-reviewed these judgment calls; the residual public-compat risk in each reduces to one of the three classes above (mostly SAFE-static private names, a few file/output-string aliases in the beat_both / honest-sweep clusters).**

---

### Roll-up (all 210 RENAME rows accounted for)

| codex class | Rows | Contract at risk |
|---|---|---|
| SAFE-static | ~112 (105 `SAFE` + 12 `TEXT-ONLY` − ~5 public symbols promoted to NEEDS-ALIAS) | none — `_`-private/local/comment |
| FILE-RENAME-fix-importers | 45 + the 5 DOMAIN-REVIEW import/file rows | module path / script filename (§5.3) |
| NEEDS-ALIAS | ~24 (env/persisted/manifest/run-id/label) + ~5 promoted public symbols | operator env, persisted string, public import name |
| DYNAMIC-HAZARD | ~8 (`content_integrity_junk` row-state key; `junk_deletion_gate` / `beat_both_scorer` string-imported modules with many importers) | persisted row-state key / string-dispatched module |
| **Total** | **210** | |

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
