# Codex BRIEF review — I-naming-010 / GH #444: rename src/polaris_graph/graph_v4.py → pipeline_a_ui_adapter.py

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0.1 Review stage — PRE-IMPLEMENTATION brief review

This is the **brief** review (the plan). The working tree is intentionally
unmodified; the later diff review verifies the applied rename. Evaluate §2-§4
as a plan — especially the §3 scope-boundary calls (two landmines + a
test-file question).

## 1. Issue

GH #444 (I-naming-010) — naming-audit follow-up from #434.
`src/polaris_graph/graph_v4.py` is a version-only filename (§4.1) for the
production-default pipeline-B-UI-parity shim. Rename `graph_v4.py` →
`pipeline_a_ui_adapter.py` (the name Codex's #434 iter-1 plan-review
adjudicated). P3, mechanical. Branch `bot/I-naming-010` (a normal
`I-<prefix>-<NNN>` id — CI ISSUE_ID = `I-naming-010`, no re-cut). Last of the
#437-444 naming-audit series.

`graph_v4.py` is one of four sibling LangGraph variant entrypoints
(`graph.py`/`graph_v2.py`/`graph_v3.py`/`graph_v4.py`); ONLY `graph_v4` is in
scope here. It exports the async `build_and_run_v4(...)` + helpers
(`_infer_domain`, `_adapt_pipeline_a_to_ui_json`, `_write_ui_json`,
`_load_uploaded_documents`).

## 2. The rename — file + import-machinery ONLY (targeted, 4 patterns)

### File rename (`git mv`, history-preserving)
- `src/polaris_graph/graph_v4.py` → `src/polaris_graph/pipeline_a_ui_adapter.py`

### Token map — 39 `graph_v4` occurrences, classified

`graph_v4` is the module name. It is NOT embedded in any non-module
identifier (the public fn is `build_and_run_v4` — `v4`, not `graph_v4`). It
appears as: real import paths, module-alias attribute references, the
module's own title docstring, test function names, test docstrings, prose in
other modules, ONE coupled test-assertion string, and ONE runtime
output-path default. A blind `graph_v4` → `pipeline_a_ui_adapter` replace is
UNSAFE (it would corrupt the output-path landmine — §3a). The rename is
applied as **4 targeted substring patterns**:

1. `polaris_graph.graph_v4 import` → `polaris_graph.pipeline_a_ui_adapter import`
   — the 7 dotted-import lines: `test_b102_graph_v4.py:37/56/75/127`,
   `test_graph_v4_documents.py:21`, `live_server.py:557/570`.
2. `polaris_graph import graph_v4` → `polaris_graph import pipeline_a_ui_adapter`
   — the 3 bare-module imports: `test_b102_graph_v4.py:150/247`,
   `test_graph_v4_documents.py:91`.
3. `graph_v4.build_and_run_v4(` → `pipeline_a_ui_adapter.build_and_run_v4(`
   — the 3 module-alias attribute calls bound by the pattern-2 imports:
   `test_b102_graph_v4.py:164/285`, `test_graph_v4_documents.py:109`.
4. The renamed module's own title docstring line 2 `graph_v4 — BUG-B-102 R2c`
   → `pipeline_a_ui_adapter — BUG-B-102 R2c` (the file's own title; leaving
   it stale is the exact defect Codex flagged on #438's `verified_report.py`).

Plus one **coupled** edit (§3c): `test_b102_graph_v4.py:197`.

Each of patterns 1-3 is an unambiguous substring that matches ONLY real
import / module-alias code — never a test function name (`def
test_b102_graph_v4_*`), never docstring prose, never the output path.

## 3. Scope-boundary calls — for Codex adjudication

### 3a. LANDMINE — `outputs/polaris_graph_v4_runs` is LEFT INTACT

`graph_v4.py:246` — `os.getenv("PG_V4_OUT_ROOT", "outputs/polaris_graph_v4_runs")`.
The string `outputs/polaris_graph_v4_runs` is the **default runtime
output-directory** for pipeline-A v4 artifacts. It *contains* the substring
`graph_v4` (`polaris_` + `graph_v4` + `_runs`). Renaming it would relocate
where artifacts are written on disk — a behaviour / artifact-location change,
NOT filename hygiene (exact analogue of the `PG_V30_ENABLED` env var / `v30_*`
manifest keys left intact in #437). **LEFT INTACT.** The 4 targeted patterns
above cannot match it.

### 3b. Test files / test function names — LEFT INTACT (file + import-path only)

The 2 test files `tests/polaris_graph/test_b102_graph_v4.py` and
`test_graph_v4_documents.py` carry `graph_v4` in their filenames, and ~13
test function names are `test_b102_graph_v4_*`. These are NOT renamed: they
are named after a bug-id (`b102`) and a feature (`documents` = I-f3-001),
not the clean `test_<module>.py` pattern, and the issue is scoped strictly to
`src/polaris_graph/graph_v4.py`. Renaming test identifiers is cosmetic churn
beyond P3 filename hygiene — same call as #437/#440 (file + import-path only,
metaphor/version identifiers left). **Codex: confirm** — or, if you judge the
test files should be renamed to track the module, that is a folded-in
follow-up; say so and it will be done.

### 3c. COUPLED edit — `test_b102_graph_v4.py:197` assertion string

`test_b102_live_server_dispatches_v4_by_default` reads `live_server.py`'s
source and asserts `'graph_v4 import build_and_run_v4' in source`. Pattern 1
rewrites `live_server.py:557` to `…pipeline_a_ui_adapter import
build_and_run_v4`, so that substring will no longer be present. The
assertion string MUST be updated in lockstep to
`'pipeline_a_ui_adapter import build_and_run_v4'` or the test breaks. This
is an in-scope coupled change (1 line).

### 3d. Prose mentions — LEFT INTACT

Conceptual `graph_v4` mentions in other modules' docstrings/comments
(`decomposer.py:25`, `followup/__init__.py:4`, `nodes/scope_gate.py:67`,
`polaris_v6/adapters/evidence_pool_merger.py:4/14`,
`polaris_v6/schemas/run_request.py:36` field-description string,
`graph_v4.py:210` internal comment), the test docstrings, the
`tests/v6/test_evidence_pool_merger.py:4` docstring, and the
`scripts/autoloop/backfill_pre_bootstrap_verdicts.py:84` historical
data-record string — all descriptive prose referring to the module
conceptually; leaving them keeps the diff minimal and is the #440 precedent
(docstring prose left). The `docs/**` mentions (substrate_audit, agent_architecture,
carney plans, pipeline_audit_context, task_acceptance_matrix) are
point-in-time audit/plan records — left, per the #436-443 precedent.

### 3e. NOT renamed — `build_and_run_v4` and `_v4` identifiers

The public function `build_and_run_v4`, `PG_V4_OUT_ROOT`, the
`PG_GRAPH_VERSION="v4"` selector value — `v4` is the pipeline-version token,
distinct from the module name `graph_v4`; none is filename hygiene.

## 4. Files I have ALSO checked and they're clean

- `grep -rn "graph_v4"` whole repo: every `.py` hit is accounted for in §2/§3.
  10 `.py` importers/mentioners + the module + 2 test files = the full
  footprint. The 3 sibling LangGraph entrypoints
  (`graph.py`/`graph_v2.py`/`graph_v3.py`) are distinct and untouched.
- No `importlib` / dynamic-import / string-path reference to `graph_v4`.
- `live_server.py` selects the variant by the `PG_GRAPH_VERSION` env value
  (`"v4"`), not by module-name string — the selector logic is unaffected.
- Target name `pipeline_a_ui_adapter` — `grep` → zero pre-existing hits.
- No `.github/workflows/*`, `conftest.py`, `pytest.ini` reference `graph_v4`.

## 5. Test / smoke (planned)

`git mv` preserves history. After: `ast.parse` the renamed module + every
edited importer (`live_server.py`, the 2 test files); `python -c "from
src.polaris_graph.pipeline_a_ui_adapter import build_and_run_v4"` import
smoke; `PYTHONPATH='src;.' python -m pytest
tests/polaris_graph/test_b102_graph_v4.py
tests/polaris_graph/test_graph_v4_documents.py` (both renamed-module test
suites — they must stay green, incl. the updated `:197` assertion). Any
pre-existing failure verified identical on clean `polaris` HEAD via `git
stash` before commit. No behaviour test applies — pure rename.

## 6. Required output schema (§8.3.9)

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
