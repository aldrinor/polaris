# Claude architect audit — I-naming-003 (#437)

**Issue:** GH #437 — rename `v30_sweep_integration.py` →
`honest_sweep_integration.py` (naming-audit follow-up from #434; version-only
filename, §4.1).
**Branch:** `bot/I-naming-003`
**Commit 1 (rename):** `b1ab8394` — 3 files, +24/-24, 2 history-preserving renames.
**Brief:** `.codex/I-naming-003/brief.md` — Codex APPROVE iter 1 (0 P0/P1; 2
non-blocking P2 wording notes).

## 1. What shipped

| Change | Detail |
|---|---|
| `git mv` ×2 | `src/polaris_graph/v30_sweep_integration.py` → `honest_sweep_integration.py` (100% similarity); `tests/polaris_graph/test_v30_sweep_integration.py` → `test_honest_sweep_integration.py` (96%). |
| Import-path token | `v30_sweep_integration` → `honest_sweep_integration` — 3 occurrences in `scripts/run_honest_sweep_r3.py` (1 import + 2 comments), 21 in the renamed test (20 `from` imports + 1 bare `import`). The renamed module itself had 0 token occurrences (its docstring uses the "V30 sweep integration" prose form, kept). |

File + import-path ONLY — applied as one substring substitution
(`v30_sweep_integration`). The token was verified to occur exclusively as an
import path / the test filename / 2 doc-comments — never inside an identifier.

## 2. Per-finding verification

- **VERIFIED — token is path-only**: `grep -rn "v30_sweep_integration"` in
  `src/`+`tests/`+`scripts/` minus import/comment/test-filename lines → zero
  hits, so the substring replace could not touch any identifier. Post-rename
  `grep` → zero residual `v30_sweep_integration` in `src/`+`tests/`+`scripts/`.
- **VERIFIED — scope boundary (Codex-adjudicated APPROVE)**: the `V30`/`v30`
  identifiers are deliberately untouched — `V30SweepResult`,
  `merge_v30_into_manifest` / `run_v30_post_generation` (public API imported
  by `run_honest_sweep_r3.py`), the `v30_*` manifest keys / result fields
  (serialized schema), `PG_V30_ENABLED` (feature-flag env var), the
  `## V30 Phase-1 Retrieval Coverage Disclosure` report heading, `[V30]` log
  tags. `import src.polaris_graph.honest_sweep_integration` confirms
  `V30SweepResult` + `run_v30_post_generation` still exported.
- **VERIFIED — guarded import still works**: `run_honest_sweep_r3.py:2842`
  guards the import behind `PG_V30_ENABLED` — that env var is unchanged, so
  the renamed-module import inside the guard resolves.
- **VERIFIED — history preserved**: `git mv` → diff shows `rename ... (100%)`
  / `(96%)`, not delete+add.

## 3. Test / smoke

`ast.parse` clean on all 3 files. `import src.polaris_graph.honest_sweep_integration`
resolves. `PYTHONPATH='src;.' pytest tests/polaris_graph/test_honest_sweep_integration.py`
→ 20/20 pass. No behaviour test applies — pure rename.

## 4. Scope + residuals

- Commit-1 diff is +24/-24 across 3 files — well under the 200-LOC cap.
- One of the #437-444 naming-audit series; #438/#439 (package-dir renames)
  have a wider blast radius and are separate issues.

## 5. Risk assessment

Pure rename — no logic change. The token was grep-proven path-only before
implementation, so the substring substitution carried zero collision risk
into identifiers / schema keys / env vars / report-output strings. The test
suite (20 cases, all importing the renamed module) passes.

## 6. Verdict

Rename complete, faithful to the iter-1 APPROVE'd brief + Codex's scope
adjudication; offline suite green. Ready for Codex diff review.
