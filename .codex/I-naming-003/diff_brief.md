# Codex DIFF review — I-naming-003 / GH #437: rename v30_sweep_integration.py → honest_sweep_integration.py

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #437 — `git diff origin/polaris...HEAD` excluding
`.codex/I-naming-003/` and `outputs/audits/I-naming-003/` (the canonical diff
in `.codex/I-naming-003/codex_diff.patch`, sha256 trailer). It implements the
Codex-APPROVE'd brief `.codex/I-naming-003/brief.md` (brief APPROVE iter 1).
Pure rename — 3 files, +24/-24, 2 history-preserving `git mv`.

## 2. The diff

- `git mv` `src/polaris_graph/v30_sweep_integration.py` →
  `honest_sweep_integration.py` (100%); `tests/polaris_graph/test_v30_sweep_integration.py`
  → `test_honest_sweep_integration.py` (96%).
- Import-path token `v30_sweep_integration` → `honest_sweep_integration`:
  3 occurrences in `scripts/run_honest_sweep_r3.py` (import + 2 comments),
  21 in the renamed test (20 `from` + 1 bare `import`).

## 3. Verify against the brief

1. Zero `v30_sweep_integration` residue in `src/` + `tests/` + `scripts/`.
2. The `V30`/`v30` IDENTIFIERS are unchanged — `V30SweepResult`,
   `merge_v30_into_manifest`, `run_v30_post_generation`, the `v30_*` manifest
   keys/fields, `PG_V30_ENABLED` env var, the `## V30 Phase-1 ...` report
   heading, `[V30]` log tags (all schema/config/output — confirmed correct in
   the brief-review).
3. `git mv` preserved history (diff shows `rename ... (NN%)`).
4. `run_honest_sweep_r3.py:2842`'s `PG_V30_ENABLED` guard is intact; the
   guarded import resolves to the renamed module.
5. No behaviour change — pure rename.

## 4. Files I have ALSO checked and they're clean

- `grep -rn "v30_sweep_integration"` whole repo (excl. `.codex/`, `archive/`,
  `codex_tmp*`, `state/`, `__pycache__`): the only code refs were the module,
  the test, and `run_honest_sweep_r3.py`'s import + 2 comments — all updated.
  `outputs/audits/**` + `outputs/codex_findings/**` historical mentions are
  audit-trail records — deliberately NOT rewritten.
- No `importlib` / dynamic / string-path reference to the module.

## 5. Test state

`ast.parse` 3/3 clean. `import src.polaris_graph.honest_sweep_integration`
resolves. `PYTHONPATH='src;.' pytest tests/polaris_graph/test_honest_sweep_integration.py`
→ 20/20.

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
