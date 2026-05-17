# Codex DIFF review — I-naming-005 / GH #439: rename src/polaris_graph/retrieval2/ → clinical_retrieval/

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #439 — `git diff origin/polaris...HEAD` excluding
`.codex/I-naming-005/` and `outputs/audits/I-naming-005/` (the canonical diff
in `.codex/I-naming-005/codex_diff.patch`, sha256 trailer). It implements the
Codex-APPROVE'd brief `.codex/I-naming-005/brief.md` (brief APPROVE iter 1).
Pure package rename — 54 files, +63/-63, 13 history-preserving `git mv`.

## 2. The diff

- `git mv` `src/polaris_graph/retrieval2/` → `clinical_retrieval/` (7 modules)
  and `tests/polaris_graph/retrieval2/` → `clinical_retrieval/` (6 modules);
  renames detected at 96-100% similarity.
- Import-path token `retrieval2` → `clinical_retrieval`: 63 occurrences in
  50 `.py` files + `README.md:18`.
- `evidence_pool.py` module docstring `(note the `2`)` parenthetical removed
  (your brief-review P2 — fixed inline in commit 1, not deferred).

## 3. Verify against the brief

1. Zero `retrieval2` residue in `src/` + `tests/` + `scripts/` `.py` files.
2. The token is path-only — confirm no identifier was named `retrieval2` and
   thus none was wrongly renamed.
3. The pre-existing string literal `"slice_002_clinical_retrieval"` (in
   `retrieval_route.py` + 3 assertions) is UNCHANGED — no collision; the
   package name now aligns with that slice ID.
4. The sibling `src/polaris_graph/retrieval/` package (no digit) is UNCHANGED.
5. `git mv` preserved history (13 `rename ... (NN%)`).
6. `import src.polaris_graph.clinical_retrieval` resolves all 6 submodules.
7. The `evidence_pool.py` docstring no longer says "(note the `2`)".
8. No behaviour change — pure rename.

## 4. Files I have ALSO checked and they're clean

- `grep -rnE "retrieval2"` whole repo: beyond the 50 `.py` + `README.md` in
  the diff, the only remaining hits are `docs/tests/i_tests_001_triage.md:33`
  (a point-in-time triage record — classified historical, NOT rewritten) and
  `outputs/` / `.codex/` / `archive/` / `codex_tmp_*` / `__pycache__`
  (audit-trail / scratch / build artifacts). No `.sh` script references it.
- No `importlib` / dynamic-import / string-path reference to the package.
- No `conftest.py` / `pytest.ini` / `pyproject.toml` references the
  `retrieval2` test path.

## 5. Test state — fully green

`ast.parse` 52/52 clean. `import src.polaris_graph.clinical_retrieval`
resolves. `PYTHONPATH='src;.' pytest tests/polaris_graph/clinical_retrieval/`
+ `api/test_retrieval_route.py` + crown_jewels + evidence_contract + golden
→ 197 passed, 0 failed.

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
