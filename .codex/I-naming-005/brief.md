# Codex BRIEF review — I-naming-005 / GH #439: rename src/polaris_graph/retrieval2/ → clinical_retrieval/

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
as a plan — especially the §3 target-name-safety call.

## 1. Issue

GH #439 (I-naming-005) — naming-audit follow-up from #434. The package
directory `src/polaris_graph/retrieval2/` is a sibling-numbered name; the `2`
hides that this is the clinical retrieval path. Rename the package
`retrieval2` → `clinical_retrieval` (the name Codex's #434 iter-1 plan-review
adjudicated). P2, mechanical. Branch `bot/I-naming-005` (a normal
`I-<prefix>-<NNN>` id — CI ISSUE_ID = `I-naming-005`, no re-cut).

This is the direct sibling of #438 (`generator2/` → `clinical_generator/`,
just merged) — same shape.

## 2. The rename — package directory + import-path token ONLY

### Directory renames (`git mv`, history-preserving)

- `src/polaris_graph/retrieval2/` → `src/polaris_graph/clinical_retrieval/`
  (7 modules: `__init__.py`, `clinical_retriever.py`,
  `clinical_source_registry.py`, `corpus_adequacy_gate.py`,
  `evidence_pool.py`, `query_planner.py`, `real_fetcher.py`).
- `tests/polaris_graph/retrieval2/` → `tests/polaris_graph/clinical_retrieval/`
  (6 test modules).

### Import-path token: `retrieval2` → `clinical_retrieval`

Applied as ONE substring substitution over every `.py` file containing the
token. **Verified path-only** — `grep -rnE "retrieval2"` in
`src/`+`tests/`+`scripts/` shows the token occurs ONLY as an import path
(`polaris_graph.retrieval2.X` / `from polaris_graph.retrieval2.X import`), the
directory path, or doc-comments referencing the module path. It is **NOT
embedded inside any identifier** — there is no variable/class/function named
`retrieval2`. So the substring replace is exactly the package-rename scope.

Footprint (grep, py): **39 importer files + the 13 moved files, 62 token
occurrences**. The moved files that contain the token get the substitution
as part of their moved content.

## 3. Target-name safety — `clinical_retrieval` is safe AND harmonizing

`grep "clinical_retrieval"` finds 4 pre-existing occurrences — **all the
identical string literal** `"slice_002_clinical_retrieval"` (a `slice` field
value in the `/api/retrieval/health` response + its 3 test assertions +
`demo_smoke.py`'s expected-value map). These are **string-ID literals in a
different namespace** from a Python package path; the substring substitution
`retrieval2` → `clinical_retrieval` does not touch them, and the resulting
package `polaris_graph.clinical_retrieval` does not collide with the string.

In fact this *harmonizes*: slice 002 already calls itself
`slice_002_clinical_retrieval`, so renaming the package to `clinical_retrieval`
aligns the module name with the slice's own established name. No ambiguity.

### NOT renamed

- The sibling `src/polaris_graph/retrieval/` package (no digit) is a
  DIFFERENT, separate package — untouched. The `retrieval2` substring cannot
  match `retrieval/` paths.
- The string literal `"slice_002_clinical_retrieval"` — a slice-ID value, not
  a module path; left exactly as is.
- No identifiers / class names / env vars — none are named `retrieval2`.

## 4. Scope-boundary calls

### 4a. Live doc — INCLUDED (README.md)

`README.md:18` — the pipeline-2 table cell `polaris_graph/retrieval2/` is a
current-state architecture reference; a stale path there is a minor defect,
so the rename updates it (1 line). `docs/crown_jewels.md` has no `retrieval2`
reference.

### 4b. Historical triage doc — EXCLUDED (docs/tests/i_tests_001_triage.md)

`docs/tests/i_tests_001_triage.md:33` (`### retrieval2/ (6 errors)`) is a
point-in-time triage record of the I-tests-001 test-fix pass. Per the
#436/#437/#438 precedent that excluded audit-trail records (`outputs/audits/**`,
`scripts/create_followup_issues.sh`), this triage snapshot is left unmodified.
**Codex: confirm this exclusion.**

### 4c. 200-LOC cap

Diff is ~62 py token-lines + 1 README line + 13 `git mv`s → well under 200
combined +/- lines (the diff brief reports `git diff --shortstat`). A package
rename is atomic and 100% mechanical regardless.

## 5. Files I have ALSO checked and they're clean

- `grep -rnE "retrieval2"` whole repo: beyond the `.py` files + `README.md`
  + `docs/tests/i_tests_001_triage.md`, the only hits are under `outputs/`,
  `.codex/`, `archive/`, `codex_tmp_*` (historical / scratch) and
  `__pycache__`. No `.sh` script references it.
- No `importlib` / dynamic-import / string-path reference to the package.
- No `conftest.py` / `pytest.ini` / `pyproject.toml` references the
  `retrieval2` test path — no test-discovery config to update.
- The sibling `retrieval/` package is unaffected (distinct token).

## 6. Test / smoke (planned)

`git mv` preserves history. After: `ast.parse` every edited/moved `.py`;
`PYTHONPATH='src;.' python -m pytest tests/polaris_graph/clinical_retrieval/`
(the 6 renamed test modules) + the dependent suites that import the package
(`tests/polaris_graph/api/test_retrieval_route.py`,
`tests/polaris_graph/audit_bundle/`, `tests/crown_jewels/`,
`tests/polaris_graph/clinical_generator/`, `tests/polaris_graph/golden/`);
plus a `python -c "import src.polaris_graph.clinical_retrieval"` import smoke.
Any pre-existing failure will be verified identical on clean `polaris` HEAD
(via `git stash`) before commit. No behaviour test applies — pure rename.

## 7. Required output schema (§8.3.9)

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
