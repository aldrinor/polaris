# Claude architect audit — I-naming-010 (#444)

**Issue:** GH #444 — rename `src/polaris_graph/graph_v4.py` →
`pipeline_a_ui_adapter.py` (naming-audit follow-up from #434; version-only
filename, §4.1). Last of the #437-444 naming-audit series.
**Branch:** `bot/I-naming-010`
**Commit 1 (rename):** `6f2053c5` — 4 files, +15/-15, 1 history-preserving rename.
**Brief:** `.codex/I-naming-010/brief.md` — Codex APPROVE iter 1 (0 P0/P1; 1
P2 — `config/scope_templates/custom.yaml:3` prose mention, dispositioned §4).

## 1. What shipped

| Change | Detail |
|---|---|
| `git mv` ×1 | `graph_v4.py` → `pipeline_a_ui_adapter.py` (99% similarity). |
| Pattern 1 | `polaris_graph.graph_v4 import` → `…pipeline_a_ui_adapter import` — 7 dotted imports (`live_server.py` ×2, `test_b102_graph_v4.py` ×4, `test_graph_v4_documents.py` ×1). |
| Pattern 2 | `polaris_graph import graph_v4` → `…import pipeline_a_ui_adapter` — 3 bare-module imports (`test_b102_graph_v4.py` ×2, `test_graph_v4_documents.py` ×1). |
| Pattern 3 | `graph_v4.build_and_run_v4(` → `pipeline_a_ui_adapter.build_and_run_v4(` — 3 module-alias calls. |
| Pattern 4 | The renamed module's title docstring `graph_v4 — BUG-B-102` → `pipeline_a_ui_adapter — BUG-B-102`. |
| Coupled | `test_b102_graph_v4.py:197` assertion string `'graph_v4 import build_and_run_v4'` → `'pipeline_a_ui_adapter import build_and_run_v4'`. |

**Targeted, not blind.** A blind `graph_v4` → `pipeline_a_ui_adapter` replace
would corrupt the §2 landmine. Each of patterns 1-3 is an unambiguous
substring matching only real import / module-alias code.

## 2. Per-finding verification

- **VERIFIED — output-path landmine LEFT INTACT**: `pipeline_a_ui_adapter.py:246`
  `os.getenv("PG_V4_OUT_ROOT", "outputs/polaris_graph_v4_runs")` — the
  default runtime output-directory string *contains* the substring
  `graph_v4`. It is a behaviour/artifact-location value, NOT filename
  hygiene (the #437 `PG_V30_ENABLED` precedent). Post-rename `grep -rc
  "polaris_graph_v4_runs"` → still **1** (unchanged). The 4 targeted
  patterns provably cannot match it.
- **VERIFIED — coupled assertion**: `test_b102_graph_v4.py:197` reads
  `live_server.py`'s source and asserts the import substring is present.
  `live_server.py:557` was rewritten to `…pipeline_a_ui_adapter import
  build_and_run_v4`; the assertion string was updated in lockstep. The test
  `test_b102_live_server_dispatches_v4_by_default` passes (one of the 9 in
  that suite).
- **VERIFIED — no import residue**: `grep -rnE
  "polaris_graph\.graph_v4 import|polaris_graph import graph_v4|graph_v4\.build_and_run_v4"`
  in `src/`+`tests/`+`scripts/` → **0**.
- **VERIFIED — siblings untouched**: the 3 other LangGraph entrypoints
  (`graph.py`/`graph_v2.py`/`graph_v3.py`) are distinct modules — `live_server.py`'s
  `PG_GRAPH_VERSION` selector branches for v3/v2/v1 are unchanged.
- **VERIFIED — import closure**: `from
  src.polaris_graph.pipeline_a_ui_adapter import build_and_run_v4,
  _infer_domain, _adapt_pipeline_a_to_ui_json, _write_ui_json,
  _load_uploaded_documents` resolves.
- **VERIFIED — history preserved**: `git mv` → diff shows `rename …
  graph_v4.py => pipeline_a_ui_adapter.py (99%)`.

## 3. Test / smoke

`ast.parse` clean on the renamed module + the 3 edited importers. Import
smoke resolves `build_and_run_v4` + 4 helpers. `PYTHONPATH='src;.' pytest`
`tests/polaris_graph/test_b102_graph_v4.py` +
`tests/polaris_graph/test_graph_v4_documents.py` → **16 passed** (9 + 7),
including the coupled live-server source-assertion test. No behaviour test
applies — pure rename.

## 4. Scope + residuals

- Commit-1 diff is +15/-15 across 4 files — trivially under the 200-LOC cap.
- **Codex iter-1 P2** — `config/scope_templates/custom.yaml:3` carries a
  prose `graph_v4` mention. Left intact: it is a YAML comment / descriptive
  prose, not an import or a code path — consistent with the §3d disposition
  of all other conceptual `graph_v4` prose (other modules' docstrings,
  `docs/**` audit records). Accounted-for, deliberately not rewritten.
- LEFT INTACT (scope boundary, Codex-confirmed): the 2 test files'
  filenames + test function names (`test_b102_graph_v4_*` — named after a
  bug-id/feature, not the clean `test_<module>` pattern); the
  `build_and_run_v4` API + `PG_V4_OUT_ROOT` / `PG_GRAPH_VERSION="v4"` (the
  `v4` version token); conceptual prose mentions in other modules + `docs/**`.
- This completes the #437-444 naming-audit rename series.

## 5. Risk assessment

Pure rename — no logic change. The two landmines (the `polaris_graph_v4_runs`
output-path default that *contains* the token; the coupled source-text
assertion) were identified up front and handled — the output path is
provably untouched, the assertion updated in lockstep. The 16-test
renamed-module suite passes.

## 6. Verdict

Rename complete, faithful to the iter-1 APPROVE'd brief + Codex's scope
adjudication; offline suite green. Ready for Codex diff review.
