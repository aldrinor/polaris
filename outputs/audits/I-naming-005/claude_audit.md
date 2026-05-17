# Claude architect audit — I-naming-005 (#439)

**Issue:** GH #439 — rename the package `src/polaris_graph/retrieval2/` →
`clinical_retrieval/` (naming-audit follow-up from #434; sibling-numbered
name, §4.1).
**Branch:** `bot/I-naming-005`
**Commit 1 (rename):** `3b9a544f` — 54 files, +63/-63, 13 history-preserving renames.
**Brief:** `.codex/I-naming-005/brief.md` — Codex APPROVE iter 1 (0 P0/P1; 1
P2 — the `evidence_pool.py` stale docstring, fixed inline in commit 1).

## 1. What shipped

| Change | Detail |
|---|---|
| `git mv` ×13 | `src/polaris_graph/retrieval2/` → `clinical_retrieval/` (7 modules); `tests/polaris_graph/retrieval2/` → `clinical_retrieval/` (6 modules). Renames detected at 96-100% similarity. |
| Import-path token | `retrieval2` → `clinical_retrieval` — 63 occurrences across 51 files (50 `.py` + `README.md`), one substring substitution. |
| Stale docstring | `evidence_pool.py` module docstring `(note the `2`)` parenthetical removed — Codex's brief-review P2; fixed inline rather than as a follow-up. |

File + import-path ONLY. The token `retrieval2` was grep-verified to occur
exclusively as an import path / directory path / doc-comment — never inside
an identifier (no variable/class/function named `retrieval2`).

## 2. Per-finding verification

- **VERIFIED — token is path-only**: pre-rename `grep -rnE "retrieval2"` →
  every hit is an import statement, directory path, or doc-comment. Post-rename
  `grep -rn "retrieval2" --include=*.py src/ tests/ scripts/` → **0**.
- **VERIFIED — target name safe + harmonizing**: the 4 pre-existing
  `clinical_retrieval` occurrences are all the string literal
  `"slice_002_clinical_retrieval"` (an API `slice`-field value + assertions +
  `demo_smoke.py`). A string-ID literal is a different namespace from a
  package path — no collision; the package name now aligns with slice 002's
  own established name.
- **VERIFIED — sibling package untouched**: the distinct `retrieval/` package
  (no digit) is not matched by the `retrieval2` substring.
- **VERIFIED — import closure**: `import src.polaris_graph.clinical_retrieval`
  resolves; all 6 submodules (`clinical_retriever`, `clinical_source_registry`,
  `corpus_adequacy_gate`, `evidence_pool`, `query_planner`, `real_fetcher`)
  import.
- **VERIFIED — history preserved**: `git mv` → diff shows 13 `rename ...
  (96-100%)` entries.

## 3. Test / smoke

`ast.parse` clean on all 52 files referencing `clinical_retrieval`.
`import src.polaris_graph.clinical_retrieval` resolves.
`PYTHONPATH='src;.' pytest tests/polaris_graph/clinical_retrieval/` (the 6
renamed test modules) + dependent suites (`api/test_retrieval_route.py`,
`crown_jewels/test_cj_003`, `evidence_contract/test_gate.py`,
`golden/test_slice_002_goldens.py`) → **197 passed, 0 failed**. No behaviour
test applies — pure rename, and unlike #438 there is no pre-existing failure
in the touched suites.

## 4. Scope + residuals

- Commit-1 diff is +63/-63 across 54 files = 126 combined LOC — **under the
  200-LOC cap**.
- `docs/tests/i_tests_001_triage.md:33` (`### retrieval2/ (6 errors)`, a
  point-in-time triage record) and the `outputs/`/`.codex/`/`archive/`/
  `codex_tmp_*` historical mentions are deliberately left intact as
  audit-trail records (same disposition as #436/#437/#438).
- `docs/crown_jewels.md` has no `retrieval2` reference (unlike #438).
- One of the #437-444 naming-audit series; #438 (`generator2/`) was the
  immediately-preceding sibling package rename.

## 5. Risk assessment

Pure rename — no logic change. The token was grep-proven path-only before
implementation; the target name was verified non-colliding. The 197-test
dependent suite passes with zero failures.

## 6. Verdict

Rename complete, faithful to the iter-1 APPROVE'd brief; offline suite fully
green. Ready for Codex diff review.
