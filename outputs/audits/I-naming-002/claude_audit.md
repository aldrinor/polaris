# Claude architect audit — I-naming-002 (#436)

**Issue:** GH #436 — rename `v30_runner.py` → `honest_sweep_job_runner.py`
(naming-audit follow-up from #434; version-only filename, §4.1).
**Branch:** `bot/I-naming-002`
**Commit 1 (rename):** `4708cad0` — 7 files, +35/-35, 2 history-preserving renames.
**Brief:** `.codex/I-naming-002/brief.md` — Codex APPROVE iter 1 (0 P0/P1; the
1 P2 is Codex's scope adjudication confirming the full file+identifier rename).

## 1. What shipped

| Change | Detail |
|---|---|
| `git mv` ×2 | `src/polaris_graph/audit_ir/v30_runner.py` → `honest_sweep_job_runner.py` (97% similarity); `tests/polaris_graph/test_v30_runner.py` → `test_honest_sweep_job_runner.py` (95%). |
| Identifiers | `V30JobRunner` → `HonestSweepJobRunner`; `V30RunnerConfig` → `HonestSweepJobRunnerConfig`; `make_default_v30_runner` → `make_default_honest_sweep_job_runner`. |
| Importers updated | `audit_ir/__init__.py` (import path + 2 names in the import list + `__all__`); `inspector_router.py` (import + call + docstring/log mentions); `job_runner.py` + `progress_surfaces.py` (docstring mentions); `openrouter_client.py:61` (comment filename). |

The rename was applied as 3 ordered substring substitutions
(`V30JobRunner`, `V30RunnerConfig`, `v30_runner`) over exactly the 7 affected
source/test files — `v30_runner` is a distinctive token that also correctly
carries `make_default_v30_runner` and `test_v30_runner`.

## 2. Per-finding verification

- **VERIFIED — full rename, no residue**: `grep -rn "v30_runner|V30JobRunner|
  V30RunnerConfig" src/ tests/` → zero hits post-rename.
- **VERIFIED — scope boundary (Codex-adjudicated APPROVE)**: the protocol/
  registry strings are deliberately untouched — `template_id = "v30_clinical"`
  (a registry key the inspector router registers under), the `"v30_phase1"` /
  `"v30_phase2"` phase-map keys and `"[v30]"` / `"[v30-p2]"` log tags (they
  match the bracketed tags `scripts/run_honest_sweep_r3.py` actually emits —
  renaming would desync the phase classifier), and "V30 Phase-2 sweep"
  docstring prose (an accurate sweep-generation description). Codex's iter-1
  P2 explicitly confirms this scope is correct.
- **VERIFIED — import closure**: `import src.polaris_graph.audit_ir` resolves;
  `HonestSweepJobRunner` and `make_default_honest_sweep_job_runner` are
  exported from the package (`dir()` check). No dynamic/`importlib`/string
  reference to the old module path exists (brief §4 grep).
- **VERIFIED — history preserved**: `git mv` → the diff shows
  `rename ... (97%)` / `(95%)`, not delete+add.

## 3. Test / smoke

`ast.parse` clean on all 7 files. `PYTHONPATH='src;.' pytest`:
`test_honest_sweep_job_runner.py` 15/15, `test_inspector_router.py` 60/60
(the changed import + `make_default_*()` call site). No behaviour test applies
— pure rename.

## 4. Scope + residuals

- Commit-1 diff is +35/-35 across 7 files — well under the 200-LOC cap.
- The sibling naming-audit issues (#437-444) each rename one further
  version-/cryptic-named file; #436 is one file of that series.

## 5. Risk assessment

Pure rename — no logic change. The blast radius (3 real importers) was
grep-verified before implementation; protocol/registry string values were
deliberately excluded so no registry key / emitted-tag / phase-classifier
behaviour changes. Both renamed test files + the inspector-router test pass.

## 6. Verdict

Rename complete, faithful to the iter-1 APPROVE'd brief + Codex's scope
adjudication; offline suites green. Ready for Codex diff review.
