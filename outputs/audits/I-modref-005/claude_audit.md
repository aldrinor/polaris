# Claude architect audit — I-modref-005 (#564)

**Issue:** GH #564 — de-qwen residual judge prose (follow-up from #530
I-modref-004 diff-review iter-1, 2 P2 doc-residue findings).
**Branch:** `bot/I-modref-005-de-qwen-doc-prose`
**Commit 1 (doc):** `81db9400`
**Brief:** `.codex/I-modref-005/brief.md` — Codex APPROVE iter 1 (0 P0, 0 P1, 2 P2).

## 1. What shipped

Model-name-neutral judge prose at the 3 issue-named sites + the same-docstring
P2-1 fold-in. Doc-only — zero code logic, zero behaviour change.

| Site | Change |
|---|---|
| `src/polaris_graph/evaluator/live_judge.py` docstring | Dropped the now-false "Module name retained for backward compat" claim (post-#530 the module IS `live_judge.py`); led with the runtime-`PG_EVALUATOR_MODEL` fact; made the NON-SAME-FAMILY line model-neutral (was "generator is DeepSeek V4 Pro, judge is Gemma 4 31B"). Kept the dated changelog parenthetical (`Gemma 4 31B as of 2026-05-08 ... previously Qwen3-8B per HONEST-REBUILD Phase 1c`) as accurate history. |
| `architecture.md:320` | `a Qwen3-8B evaluator` → `an LLM evaluator (different model family from the generator)`. |
| `docs/pipeline_audit_context/02_prompt_templates.md:143` | `asks Qwen3-8B to score` → `asks the LLM judge to score`. |

## 2. Per-finding verification

- **VERIFIED — issue point 1** (`live_judge.py` docstring): the stale
  "retained for backcompat" clause is removed; `Qwen3-8B` survives only in the
  accurate dated changelog parenthetical, which the issue acceptance explicitly
  exempts. `python -c "import ast"` parses the file clean.
- **VERIFIED — issue point 2** (`architecture.md:320` + `02_prompt_templates.md`):
  both reworded model-neutral; `grep Qwen3-8B` on the 3 edited files returns
  only the intended `live_judge.py:6` changelog line.
- **VERIFIED — iter-1 P2-1** (`live_judge.py:10-11` model-specific): folded into
  the same docstring edit; the whole docstring is now consistently model-neutral.
  `check_family_segregation()` semantics preserved (the line still states the
  judge must be a different training family from the generator).
- **VERIFIED — iter-1 P2-2** (`docs/runbook.md:274` residual `Qwen3-8B`): this
  is a *cheaper-generator* pricing example, not judge prose — left to #502
  (model/config alignment) scope, as Codex itself classified it ("likely
  #502-adjacent"). See brief §3.

## 3. Scope discipline

An exhaustive whole-tree `grep Qwen3-8B` (brief §3) shows the token also in
model-SKU / pricing prose (`architecture.md:176/339`, `runbook.md:274`,
`file_directory.md:252`, `ground_rules.md:316`, `openrouter_client.py` rationale
comments, `test_b4_budget_imputation.py:31`) and one commit-log line
(`06_recent_commits.md:32`, exempt as changelog). Per the documented
`.codex/I-modref-004/diff_brief.md:72-74` + `.codex/I-rdy-002/verification_
findings.md:14` boundary, all model-SKU residuals are **#502 (I-rdy-006)**
scope. #564 is held to its stated "trivial 3-site" judge-prose scope; the
model-SKU sweep + the one same-class `pipeline_audit_context/16_pass_9...:116`
audit-note line are flagged in the close-comment for #502.

## 4. Test / smoke

`python -c "import ast; ast.parse(...)"` on `live_judge.py` — clean. No
behavioural test applies (doc-only). The #530 rename test suite is untouched.

## 5. Risk assessment

Zero production-code risk — one Python module *docstring* + two `.md` files.
No identifier, no logic, no test touched. No import-closure impact.

## 6. Verdict

Implementation complete, faithful to the iter-1 APPROVE'd brief, model-neutral
judge prose at all 3 named sites + P2-1. Ready for Codex diff review.
