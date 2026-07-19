# Phase 2 — FILE-RENAME (static-safe module/script renames)

Part of the code-review-readiness initiative. This phase renames vestigial-named
modules and scripts to descriptive names. Every change committed here is
**behavior-preserving**: 28 renames are `git mv` (27 R100 — file bytes 100%
identical after the move — plus one R099 that differs from its source by a single
sibling-module import line), and the only other edits are `import`/`from`
statement path fixes in importers plus one by-path `.read_text()` reference to a
renamed file.

## Codex gate outcome: FILE-RENAME-REVISE → committed the safe subset

The initial change set also folded in a launcher consolidation, a retired-script
import repair, and script self-reference usage-string edits. Codex (max reasoning)
returned **FILE-RENAME-REVISE**, ruling that the pure R100 renames + updates of
already-working references are safe, but that three items are behavior-changing
and must be split into separately tested commits:

1. **Launcher consolidation** (`run_full_scale_v10..v29` → one parameterized
   `run_full_scale.py` + shims) is a refactor, not a rename — matching env dicts and
   `override=False` does not prove identical import timing / module API / `sys.argv`
   handling / exit codes / exception behavior. **Reverted here; deferred to a
   separate commit with differential subprocess tests.**
2. **Retired-script import repair**: two retired scripts imported
   `from scripts.pg_compose_openai_validation …` — a path that *never* resolved.
   Rewriting it to a resolvable archive path is a correctness fix, not a rename.
   **Reverted here; the import is left failing as before.** (The file itself is
   still moved to `archive/` as a pure R100 rename — only the two sibling
   *import-repair* edits were reverted.)
3. **Script usage/help-string self-references** (docstrings, an `argparse prog=`,
   a logger name, an auto-generated output string) change runtime-visible output,
   so the moved files could not stay R100. **Reverted here** so every script move is
   byte-identical; the usage-string refresh is deferred.

The two stale comment/docstring path references (below) do not perform path
resolution and are deferred to human review, per the same gate.

## What this commit contains

| Category | Count |
|---|---|
| `git mv` renames | 28 |
| — R100 (byte-identical move) | 27 |
| — R099 (move + 1 sibling-import line) | 1 |
| Importer / by-path reference-fix files (src + scripts + tests, `import`-only) | 50 |
| — of which `tests/` (non-oracle) | 27 |

### src module renames (11) — importers updated

| Old | New |
|---|---|
| `audit_ir/honest_sweep_job_runner.py` | `audit_ir/v30_sweep_job_runner.py` |
| `benchmark/pathB_capture.py` | `benchmark/benchmark_run_capture.py` |
| `benchmark/pathB_runner.py` | `benchmark/benchmark_gate_runner.py` |
| `honest_pipeline.py` | `provenance_verified_pipeline.py` |
| `honest_sweep_integration.py` | `v30_sweep_integration.py` |
| `state_v3.py` | `state_lightweight.py` |
| `synthesis/report_assembler_v2.py` | `synthesis/grounded_bibliography_assembler.py` |
| `synthesis/synthesizer_v2.py` | `synthesis/section_synthesizer_parallel.py` |
| `synthesis/verifier_v2.py` | `synthesis/verifier.py` |
| `v30_contract_synthesizer.py` | `contract_synthesizer.py` |
| `wiki/mesh/retrieve/lethal.py` | `wiki/mesh/retrieve/retrieval.py` |

Each rename's dotted-import paths (`polaris_graph.<old>` / `... import <old>` and
relative `from .<old> import`) were updated in every importing module under `src/`,
`scripts/`, and `tests/` (excluding `tests/oracle/`, see below). One by-path
reference in `scripts/architecture/weekly_drift_report.py`
(`… / "benchmark" / "pathB_runner.py").read_text()`) was updated to the new
filename — a necessary update of an already-working reference.

### script renames (16) — pure moves (usage-string refresh deferred)

`_basket_workers_ab_cert` → `compose_basket_workers_ab_certification_test`,
`_m54_append_contract` → `append_report_contract_yaml`,
`_v24_compare` → `compare_report_versions`,
`audit_v3_report` → `audit_report_forensics`,
`compare_live_vs_pg_lb_sa_02` → `compare_live_vs_prerebuild_run`,
`deep_gemini_verify` → `integration_quality_verify`,
`harness_render_boundary_screen` → `run_sweep_evaluation`,
`i_naming_001_migrate` → `migrate_bpei_to_ambiguity_detector`,
`iarch007_behavioral_canary` → `behavioral_canary_release_fixes`,
`iarch011_b11_compose_repetition_harness` → `compose_repetition_harness`,
`iarch011_binding_and_judge_probe` → `binding_and_judge_probe`,
`iarch011_fixb_pair_dump` → `iarch011_verbatim_entailment_pair_diagnostic`,
`playwright_fire_test` → `playwright_exhaustive_ui_audit`,
`run_r5_rerun` → `run_denylist_subject_content_starved_fixes_rerun`,
`run_r6_validation` → `run_gap_fix_validation`,
`visual_final` → `visual_full_viewport_capture`.

These have no live `import` consumers; the self-referential usage/help strings
inside each were intentionally **not** rewritten in this commit (see gate item 3),
so every one of these moves stays byte-identical.

### retired-script archive move (1) — pure move

`scripts/_retired_2026_06_14/pg_compose_openai_validation.py` →
`archive/2026_06_14_retired_scripts/pg_compose_openai_validation.py` (R100). The two
sibling retired scripts' import edits were reverted (gate item 2), so the move is
clean and no dead import was "repaired" here.

## Verification

- **Collection neutral.** `pytest --collect-only tests/`: this tree collects 16738
  tests / 11 errors; the merge-base baseline collects 16501 / 23 errors. The set of
  collection errors introduced by the rename is **empty** (`comm -23` of the two
  error sets). All 11 remaining errors are pre-existing baseline debt with
  byte-identical root causes on both sides (missing modules / playwright / registry
  — e.g. `test_mesh_e2e` fails on `mesh.snapshot` missing in BOTH, unrelated to
  `lethal`→`retrieval`).
- **All 11 renamed modules import** cleanly (`importlib.import_module` each → 11/11).
- **Executable dangling references: empty.** No `import`/`from` statement references
  any old module path. (Remaining old-name substrings are function names such as
  `make_default_honest_sweep_job_runner` and local aliases like `as pathB_capture` —
  not module paths.)
- **Line-ending integrity.** Eight files (six under `src/`/`scripts/`, two under
  `tests/`) are CRLF files that the rename driver had LF-normalized, producing
  full-file whitespace churn around a 1–3 line change. The import-path swap was
  re-applied on the original CRLF bytes; each now shows only its real change with
  CRLF preserved. Zero line-ending delta remains across the staged diff.

## Excluded from this commit (guard)

`tests/oracle/` is **not** staged. `git add tests/` pulls in five `tests/oracle/`
entries (two cassette-harness files carrying unrelated debug instrumentation, plus
three untracked new oracle files); the staging guard
(`git diff --cached --name-only | grep -c tests/oracle == 0`) restored them out.

## DYNAMIC-REF items skipped for human review

Two stale path **strings inside comments/docstrings** (non-executable, no runtime
effect) are deliberately left untouched:

1. `src/polaris_graph/audit_ir/v30_sweep_job_runner.py` — a `#` comment referencing
   the old `honest_sweep_job_runner.py` path in a `parents[3]` note.
2. `scripts/run_console/run_console.py` — a docstring line citing
   `src/polaris_graph/benchmark/pathB_capture.py:219-247` as an observability
   source location.

## Deterministic oracle status (documented baseline waiver)

The initiative's cassette-replay oracle
(`tests/oracle/acceptance_portable.py --replay`) is currently **red independent of
this change**: it aborts in `retrieval_cassette.finalize()` with `CassetteError: 3
recorded request(s) never replayed … First: run_live_retrieval call_id='0'`. Running
the identical oracle against the **pre-rename** branch tip (old module names, renames
uncommitted) reproduces the **byte-identical** error. The committed retrieval
cassette is therefore misaligned with the current code state upstream of this phase.
Per the codex gate this is a documented baseline waiver: the identical failure
establishes "no new failure at that checkpoint," but does not prove end-to-end
equivalence (both runs abort before producing a result), so the cassette needs a
separate re-seed outside this phase.
