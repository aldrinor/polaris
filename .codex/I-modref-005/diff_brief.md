# Codex DIFF review — I-modref-005 / GH #564: de-qwen residual judge prose

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. What you are reviewing

The commit-1 diff for #564 — `git diff origin/polaris...HEAD` excluding
`.codex/I-modref-005/` and `outputs/audits/I-modref-005/` (the canonical diff
in `.codex/I-modref-005/codex_diff.patch`, sha256 trailer). It implements the
Codex-APPROVE'd brief `.codex/I-modref-005/brief.md` (brief review APPROVE
iter 1, 0 P0 / 0 P1 / 2 P2). Verify the diff faithfully executes that brief.

This is a **doc-only** change — one Python module docstring + two `.md` files.
Zero code logic, zero behaviour change.

## 2. The diff (3 files, ~12 insertions / ~13 deletions)

- **`src/polaris_graph/evaluator/live_judge.py`** — module docstring only.
  Dropped the now-false "Module name retained for backward compat" clause
  (post-#530 the module IS `live_judge.py`); led with the runtime-
  `PG_EVALUATOR_MODEL` fact; made the NON-SAME-FAMILY sentence model-neutral
  (was naming `DeepSeek V4 Pro` + `Gemma 4 31B` — iter-1 P2-1 fold-in). The
  dated changelog parenthetical `Gemma 4 31B as of 2026-05-08 per I-bug-087,
  previously Qwen3-8B per HONEST-REBUILD Phase 1c` is kept verbatim as accurate
  history (issue acceptance exempts changelog).
- **`architecture.md:320`** — `a Qwen3-8B evaluator` → `an LLM evaluator
  (different model family from the generator)`.
- **`docs/pipeline_audit_context/02_prompt_templates.md:143`** —
  `asks Qwen3-8B to score` → `asks the LLM judge to score`.

## 3. Verify against the brief

1. The 3 sites are exactly the issue-named ones; no scope creep into the
   model-SKU residuals reserved for #502 (brief §3).
2. `live_judge.py` still parses (`ast.parse`); the docstring is a docstring,
   not code; `check_family_segregation()` semantics described unchanged.
3. No `Qwen3-8B` survives in current judge prose; the only remaining token in
   the edited files is the `live_judge.py` changelog parenthetical (intended).
4. No identifier / no logic / no test touched — confirm the diff is
   docstring + `.md` prose only.

## 4. Files I have ALSO checked and they're clean

- Exhaustive `grep Qwen3-8B` whole tree (brief §3): all other hits are
  model-SKU/pricing prose (#502 scope), `.codex/**` audit history, a
  commit-log line (changelog-exempt), or the stray `codex_tmp_*` temp dir.
- No test asserts the edited docstring/`.md` prose; the #530 rename test suite
  is untouched.
- `live_judge.py` code body below the docstring — not touched.

## 5. Known scope calls (not defects — confirm sound)

- Model-SKU / pricing `Qwen3-8B` residuals (`architecture.md:176/339`,
  `runbook.md:274`, `file_directory.md:252`, `ground_rules.md:316`,
  `openrouter_client.py` comments, `test_b4_budget_imputation.py:31`) →
  **#502 (I-rdy-006)** scope per `.codex/I-modref-004/diff_brief.md:72-74` +
  `.codex/I-rdy-002/verification_findings.md:14`. Not touched here.
- `docs/pipeline_audit_context/16_pass_9_sweep_content_audit.md:116` is
  same-class judge prose not named by the issue → flagged for #502 in the
  close-comment rather than silently widening #564's "trivial 3-site" scope.
- `CLAUDE.md:289` (`live_qwen_judge` in repo-layout tree) is
  canonical-pin-protected — documented residual.

## 6. Test state

`python -c "import ast; ast.parse(...)"` on `live_judge.py` — clean. No
behavioural test applies (doc-only).

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
