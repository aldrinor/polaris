# Claude architect audit — I-naming-004 (#438)

**Issue:** GH #438 — rename the package `src/polaris_graph/generator2/` →
`clinical_generator/` (naming-audit follow-up from #434; sibling-numbered
name, §4.1).
**Branch:** `bot/I-naming-004`
**Commit 1 (rename):** `69534120` — 50 files, +86/-86, 18 history-preserving renames.
**Brief:** `.codex/I-naming-004/brief.md` — Codex APPROVE iter 1 (0 P0/P1; 1
non-blocking P2 — `create_followup_issues.sh`, dispositioned below).

## 1. What shipped

| Change | Detail |
|---|---|
| `git mv` ×18 | `src/polaris_graph/generator2/` → `clinical_generator/` (7 modules); `tests/polaris_graph/generator2/` → `clinical_generator/` (11 modules). All renames detected at 97-100% similarity. |
| Import-path token | `generator2` → `clinical_generator` — 86 occurrences across 46 files (44 `.py` + `README.md` + `docs/crown_jewels.md`), applied as one substring substitution. |

File + import-path ONLY. The token `generator2` was grep-verified to occur
exclusively as an import path / directory path / doc-comment — never inside
an identifier (there is no variable/class/function named `generator2`).

## 2. Per-finding verification

- **VERIFIED — token is path-only**: pre-rename `grep -rnE "generator2"` in
  `src/`+`tests/`+`scripts/` → every hit is an import statement, a directory
  path, or a doc-comment referencing the module path. No identifier carries
  the token. Post-rename `grep -rc "generator2" --include=*.py src/ tests/
  scripts/` → **0 files**.
- **VERIFIED — sibling package untouched**: the distinct `generator/` package
  (no digit) is not matched by the `generator2` substring — `generator/`
  paths are unchanged.
- **VERIFIED — target name is clean**: pre-rename `grep "clinical_generator"`
  → zero pre-existing hits, so the rename introduces no collision.
- **VERIFIED — import closure**: `import src.polaris_graph.clinical_generator`
  resolves; all 6 submodules (`generator`, `provenance`, `real_completion`,
  `section_blueprint`, `strict_verify`, `verified_report`) import.
- **VERIFIED — history preserved**: `git mv` → diff shows 18 `rename ...
  (97-100%)` entries, not delete+add.
- **VERIFIED — zero regression**: the 4 failures in
  `test_provenance_generator_entailment.py` (lines 101/126/160/250) are
  **identical on clean `polaris` HEAD** — confirmed by `git stash` + run on
  the unmodified tree (4 failed / 6 passed, same test names, same lines).
  Pre-existing, not introduced here.

## 3. Test / smoke

`ast.parse` clean on all 44 edited `.py` files.
`import src.polaris_graph.clinical_generator` resolves.
`PYTHONPATH='src;.' pytest tests/polaris_graph/clinical_generator/` (the 11
renamed test modules) + the dependent suites (`tests/crown_jewels/test_cj_002/
003/004`, `tests/polaris_graph/evidence_contract/test_gate.py`,
`tests/polaris_graph/test_provenance_generator_entailment.py`) →
**259 passed, 4 pre-existing-failed, 4 skipped**. No behaviour test applies —
pure rename.

## 4. Codex P2 disposition — `scripts/create_followup_issues.sh:26-27`

Codex's iter-1 brief P2: the one-shot script `create_followup_issues.sh`
mentions `generator2` at lines 26-27. **Classified historical/one-shot — NOT
rewritten.** That script has already executed; lines 26-27 are the verbatim
body text of GH issue #356 (I-bug-102, since `completed`) as it was filed.
Editing the script would falsify a historical record of what the issue body
said at creation time — analogous to the `outputs/audits/**` /
`outputs/codex_findings/**` audit-trail records the #436/#437 renames
deliberately excluded. The live module path is fully consistent; only this
frozen issue-creation log retains the old string, by design.

## 5. Scope + residuals

- Commit-1 diff is +86/-86 across 50 files = 172 combined LOC — **under the
  200-LOC cap**; no exemption needed (a package rename is atomic regardless).
- `docs/tests/i_tests_001_triage.md` (a point-in-time triage record) and the
  `outputs/`/`.codex/`/`archive/`/`codex_tmp_*` historical mentions are
  deliberately left intact as audit-trail records.
- One of the #437-444 naming-audit series; #439 (`retrieval2/`) is the
  sibling package rename.

## 6. Risk assessment

Pure rename — no logic change. The token was grep-proven path-only before
implementation, so the substring substitution carried zero collision risk
into identifiers / schema keys / env vars. The 259-test dependent suite
passes; the only failures are independently confirmed pre-existing.

## 7. Verdict

Rename complete, faithful to the iter-1 APPROVE'd brief; offline suite green
with zero regression. Ready for Codex diff review.
