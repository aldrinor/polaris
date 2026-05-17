# Codex BRIEF review — I-naming-004 / GH #438: rename src/polaris_graph/generator2/ → clinical_generator/

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
as a plan — especially the §3 scope-boundary calls (docs + the 200-LOC cap).

## 1. Issue

GH #438 (I-naming-004) — naming-audit follow-up from #434. The package
directory `src/polaris_graph/generator2/` is a sibling-numbered name; the `2`
hides that this is the clinical strict-verify generator. Rename the package
`generator2` → `clinical_generator`. P2, mechanical. Branch `bot/I-naming-004`
(a normal `I-<prefix>-<NNN>` id — CI ISSUE_ID = `I-naming-004`, no re-cut).

## 2. The rename — package directory + import-path token ONLY

### Directory renames (`git mv`, history-preserving)

- `src/polaris_graph/generator2/` → `src/polaris_graph/clinical_generator/`
  (7 modules: `__init__.py`, `generator.py`, `provenance.py`,
  `real_completion.py`, `section_blueprint.py`, `strict_verify.py`,
  `verified_report.py`).
- `tests/polaris_graph/generator2/` → `tests/polaris_graph/clinical_generator/`
  (11 test modules).

### Import-path token: `generator2` → `clinical_generator`

Applied as ONE substring substitution over every `.py` file that contains the
token. **Verified path-only** — `grep -rnE "generator2"` in
`src/`+`tests/`+`scripts/` shows the token occurs ONLY as (a) an import path
(`polaris_graph.generator2.X` / `from src.polaris_graph.generator2.X import`),
(b) the directory path, or (c) doc-comments/docstrings referencing the module
path (e.g. `provenance_generator.py:744-755`, `entailment_judge.py:3/33/65`,
`artifact_to_slice_chain.py:55/62`). It is **NOT embedded inside any
identifier** — there is no variable/class/function named `generator2`. So the
substring replace is exactly the package-rename scope and cannot touch logic.

Footprint (grep, py, excl. the moved dirs' own internal refs counted once):
**44 files, 82 token occurrences** — 17 `src/`, 26 `tests/`, 1 `scripts/`.
The 18 moved files that themselves contain the token get the substitution as
part of their moved content.

Target name `clinical_generator` is **clean** — `grep -rln "clinical_generator"`
in `src/`+`tests/`+`scripts/` → zero pre-existing hits.

## 3. Scope-boundary calls — for Codex adjudication

### 3a. Live docs — INCLUDED (README.md + docs/crown_jewels.md)

Two live architecture docs reference the path and would go stale:
- `README.md:19` — the pipeline-3 table cell `polaris_graph/generator2/`.
- `docs/crown_jewels.md:8-10` — the I-cj-002/003/004 crown-jewel index rows
  point at `src/polaris_graph/generator2/{provenance,strict_verify,verified_report}.py`.

These are current-state architecture references; a stale module path in them
is a real (if minor) defect, so the rename updates them (4 lines total).

### 3b. Historical triage doc — EXCLUDED (docs/tests/i_tests_001_triage.md)

`docs/tests/i_tests_001_triage.md` references `generator2/` at lines 17 +
103/123-125. This is a **point-in-time triage record** of the I-tests-001
test-fix pass ("generator2/ (10 errors)" describes a past failure state).
Per the #436/#437 precedent that excluded `outputs/audits/**` /
`outputs/codex_findings/**` as audit-trail records, this triage snapshot is
left unmodified. **Codex: confirm this exclusion** — or, if you judge a
`docs/` file should track current paths regardless of its historical framing,
say so and it will be folded in (5 more lines).

### 3c. 200-LOC cap — mechanical-rename exemption invoked

A package rename is atomic — it cannot be split into <200-LOC sub-PRs without
leaving the tree in a broken half-renamed state. The diff is ~82 py
token-lines + 4 doc lines + 18 `git mv`s; `git diff --shortstat` will be
reported in the diff brief. Per CLAUDE.md §3.0/§8.3.10 the 200-LOC cap admits
a mechanical-exemption; this PR is 100% mechanical (zero logic change, every
changed line is a path token). **Codex: confirm the mechanical-rename
exemption applies** if the diff exceeds 200 combined +/- lines.

### 3d. NOT renamed

- The sibling `src/polaris_graph/generator/` package (no digit) is a
  DIFFERENT, separate package — untouched. The token `generator2` is
  distinctive and the substring replace cannot affect `generator/` paths.
- No identifiers, class names, API surface, env vars, or output strings —
  there are none named `generator2` (verified §2).

## 4. Files I have ALSO checked and they're clean

- `grep -rnE "generator2"` whole repo: beyond the 44 `.py` files + 3 `.md`
  docs above, the only hits are under `outputs/`, `.codex/`, `archive/`,
  `codex_tmp_*` (historical / audit-trail / scratch — deliberately NOT
  rewritten) and `__pycache__` (build artifact).
- No `importlib` / dynamic-import / string-path reference to the package.
- No `conftest.py` / `pytest.ini` / `pyproject.toml` / `setup.cfg` / `tox.ini`
  references the `generator2` test path — no test-discovery config to update.
- The sibling `generator/` package is unaffected (distinct token).

## 5. Test / smoke (planned)

`git mv` preserves history. After: `ast.parse` every edited/moved `.py`;
`PYTHONPATH='src;.' python -m pytest tests/polaris_graph/clinical_generator/`
(the 11 renamed test modules) + the dependent suites that import the package
(`tests/polaris_graph/audit_bundle/`, `tests/crown_jewels/`,
`tests/polaris_graph/evidence_contract/`, `tests/polaris_graph/benchmark/`,
`tests/polaris_graph/golden/`); plus a
`python -c "import src.polaris_graph.clinical_generator"` import smoke. No
behaviour test applies — pure rename.

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
