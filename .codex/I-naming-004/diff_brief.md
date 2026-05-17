# Codex DIFF review — I-naming-004 / GH #438: rename src/polaris_graph/generator2/ → clinical_generator/

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #438 — `git diff origin/polaris...HEAD` excluding
`.codex/I-naming-004/` and `outputs/audits/I-naming-004/` (the canonical diff
in `.codex/I-naming-004/codex_diff.patch`, sha256 trailer). It implements the
Codex-APPROVE'd brief `.codex/I-naming-004/brief.md` (brief APPROVE iter 1).
Pure package rename — 50 files, +86/-86, 18 history-preserving `git mv`.

## 2. The diff

- `git mv` `src/polaris_graph/generator2/` → `clinical_generator/` (7 modules)
  and `tests/polaris_graph/generator2/` → `clinical_generator/` (11 modules);
  all renames detected at 97-100% similarity.
- Import-path token `generator2` → `clinical_generator`: 86 occurrences in
  44 `.py` files + `README.md:19` + `docs/crown_jewels.md:8-10`.

## 3. Verify against the brief

1. Zero `generator2` residue in `src/` + `tests/` + `scripts/` `.py` files
   (`grep -rc` → 0 files).
2. The token is path-only — confirm no identifier (class/function/variable)
   was named `generator2` and thus none was wrongly renamed.
3. The sibling `src/polaris_graph/generator/` package (no digit) is
   UNCHANGED — the `generator2` substring cannot match `generator/` paths.
4. `git mv` preserved history (diff shows 18 `rename ... (NN%)`).
5. `import src.polaris_graph.clinical_generator` resolves all 6 submodules.
6. No behaviour change — pure rename.

## 4. Files I have ALSO checked and they're clean

- `grep -rnE "generator2"` whole repo: beyond the 44 `.py` + 2 live docs in
  the diff, the only remaining hits are `scripts/create_followup_issues.sh`
  (a one-shot issue-creation script — lines 26-27 quote the frozen body text
  of already-filed issue #356; classified historical, NOT rewritten — see
  `outputs/audits/I-naming-004/claude_audit.md` §4), `docs/tests/i_tests_001_triage.md`
  (a point-in-time triage record), and `outputs/` / `.codex/` / `archive/` /
  `codex_tmp_*` / `__pycache__` (audit-trail / scratch / build artifacts).
- No `importlib` / dynamic-import / string-path reference to the package.
- No `conftest.py` / `pytest.ini` / `pyproject.toml` test-discovery config
  references the `generator2` path.

## 5. Test state — zero regression confirmed

`ast.parse` 44/44 clean. `import src.polaris_graph.clinical_generator`
resolves. `PYTHONPATH='src;.' pytest tests/polaris_graph/clinical_generator/`
+ crown_jewels + evidence_contract + `test_provenance_generator_entailment.py`
→ 259 passed, 4 failed, 4 skipped. The 4 failures
(`test_provenance_generator_entailment.py` lines 101/126/160/250) were
verified **identical on clean `polaris` HEAD** via `git stash` + run on the
unmodified tree — pre-existing, not introduced by this rename.

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
