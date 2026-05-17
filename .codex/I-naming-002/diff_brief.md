# Codex DIFF review — I-naming-002 / GH #436: rename v30_runner.py → honest_sweep_job_runner.py

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #436 — `git diff origin/polaris...HEAD` excluding
`.codex/I-naming-002/` and `outputs/audits/I-naming-002/` (the canonical diff
in `.codex/I-naming-002/codex_diff.patch`, sha256 trailer). It implements the
Codex-APPROVE'd brief `.codex/I-naming-002/brief.md` (brief APPROVE iter 1 —
the iter-1 P2 was Codex's scope adjudication confirming the full rename).
Pure rename — 7 files, +35/-35, 2 history-preserving `git mv`.

## 2. The diff

- `git mv` `src/polaris_graph/audit_ir/v30_runner.py` →
  `honest_sweep_job_runner.py` (97%); `tests/polaris_graph/test_v30_runner.py`
  → `test_honest_sweep_job_runner.py` (95%).
- Identifiers: `V30JobRunner` → `HonestSweepJobRunner`; `V30RunnerConfig` →
  `HonestSweepJobRunnerConfig`; `make_default_v30_runner` →
  `make_default_honest_sweep_job_runner`.
- Import paths + `__all__` in `audit_ir/__init__.py`; import + call site +
  docstring/log mentions in `inspector_router.py`; docstring mentions in
  `job_runner.py` / `progress_surfaces.py`; comment filename in
  `openrouter_client.py`.

## 3. Verify against the brief

1. Zero `v30_runner` / `V30JobRunner` / `V30RunnerConfig` residue in `src/` +
   `tests/` (only protocol strings remain — see §4).
2. The protocol/registry strings `"v30_clinical"`, `"v30_phase1/2"`,
   `"[v30]"`/`"[v30-p2]"` are UNCHANGED (renaming them is a behaviour change —
   confirmed correct by your own brief-review P2).
3. `git mv` preserved history (diff shows `rename ... (NN%)`).
4. `import src.polaris_graph.audit_ir` resolves; the package re-exports
   `HonestSweepJobRunner` + `make_default_honest_sweep_job_runner`.
5. No behaviour change — pure rename.

## 4. Files I have ALSO checked and they're clean

- `grep -rn "v30_runner" --include=*.py` (excl. `.codex/`, `archive/`,
  `codex_tmp*`, `__pycache__`): the 3 real importers + the module + the test
  were the entire footprint; all updated. `.codex/**` / `outputs/audits/**` /
  `state/**` historical mentions of `v30_runner` are audit-trail records —
  deliberately NOT rewritten.
- No `importlib` / dynamic / string-path reference to the old module.
- The `"v30_clinical"` template_id stays — `inspector_router` still registers
  the runner under that key (unchanged registry behaviour).

## 5. Test state

`ast.parse` 7/7 clean. `PYTHONPATH='src;.' pytest`:
`test_honest_sweep_job_runner.py` 15/15, `test_inspector_router.py` 60/60.

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
