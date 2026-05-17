# Codex BRIEF review — I-modref-005 / GH #564: de-qwen residual doc prose

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 1. Issue

GH #564 (I-modref-005) — follow-up from #530 (I-modref-004) Codex diff-review
iter-1, which flagged 2 non-blocking P2 doc-residue findings (accepted at
APPROVE, captured here). After the Class B rename (`qwen_*` identifiers +
`live_qwen_judge.py` → `live_judge.py`), three current docs/docstrings still
describe the judge as `Qwen3-8B`.

**Acceptance (verbatim from the issue):** model-name-neutral judge prose;
zero `Qwen3-8B` in current docs/docstrings *except accurate changelog history*.

This is a **doc-only** change — zero code logic, zero behaviour change.

## 2. The exact edits (3 sites)

### Site 1 — `src/polaris_graph/evaluator/live_judge.py` module docstring

Current (lines 4-12):
```
Calls the REAL evaluator model via OpenRouter (default Gemma 4 31B as
of 2026-05-08 per I-bug-087; previously Qwen3-8B per HONEST-REBUILD
Phase 1c) to produce per-axis structured verdicts on a completed
report. Module name retained for backward compat; the actual model is
read from PG_EVALUATOR_MODEL at runtime.

This is the NON-SAME-FAMILY judge: generator is DeepSeek V4 Pro,
judge is Gemma 4 31B. `check_family_segregation()` must succeed before
this is called.
```
Proposed:
```
Calls the REAL evaluator model via OpenRouter (model read from
PG_EVALUATOR_MODEL at runtime; default Gemma 4 31B as of 2026-05-08
per I-bug-087, previously Qwen3-8B per HONEST-REBUILD Phase 1c) to
produce per-axis structured verdicts on a completed report.

This is the NON-SAME-FAMILY judge: the judge model must be from a
different training family than the generator. `check_family_segregation()`
must succeed before this is called.
```
Rationale: the genuinely-stale claim is "Module name retained for backward
compat" — post-#530 the module IS `live_judge.py`, a model-neutral name; there
is nothing "retained for backcompat". That clause is dropped. The
`Gemma 4 31B as of 2026-05-08 ... previously Qwen3-8B per HONEST-REBUILD
Phase 1c` parenthetical is an **accurate dated changelog entry** — the issue
explicitly says keep accurate changelog history, so the `Qwen3-8B` token
remains there as history (not as a current-state claim). The runtime-model
fact is promoted to the front so the prose leads model-neutral.
**iter-1 P2-1 fold-in:** lines 10-11 (`generator is DeepSeek V4 Pro, judge is
Gemma 4 31B`) are in the same docstring and are also model-specific; they are
made model-neutral in the same edit so the whole `live_judge.py` docstring is
consistently model-neutral judge prose. Family-segregation semantics preserved.

### Site 2 — `architecture.md:320`

Current: `Separate from the in-pipeline \`strict_verify\`, a Qwen3-8B evaluator`
`runs after generation:`
Proposed: `Separate from the in-pipeline \`strict_verify\`, an LLM evaluator`
`(different model family from the generator) runs after generation:`
Rationale: model-neutral; the section header is already `## 7. Evaluator
(two-family)`. Correct regardless of the configured `PG_EVALUATOR_MODEL`.

### Site 3 — `docs/pipeline_audit_context/02_prompt_templates.md:142-144`

Current:
```
- Given the final `report.md` + corpus tier distribution, asks
  Qwen3-8B to score: groundedness, comprehensiveness, citation
  accuracy, hedging
```
Proposed:
```
- Given the final `report.md` + corpus tier distribution, asks
  the LLM judge to score: groundedness, comprehensiveness,
  citation accuracy, hedging
```

## 3. Scope boundary (deliberately NOT touched — confirm sound)

An exhaustive `grep -rn 'Qwen3-8B'` (whole tree, `.py`+`.md`, excluding
`.codex/**` audit-trail history and the stray `codex_tmp_i_rdy005_review_*/`
temp dir) found these residuals beyond the 3 named judge-prose sites. Each is
deliberately left alone — confirm the classification is sound:

- **Model-SKU / pricing references → #502 (I-rdy-006) scope.** Per
  `.codex/I-modref-004/diff_brief.md:72-74` ("Model-SKU strings ...
  #502/#527/#529 scope, not `qwen_*` identifiers") and
  `.codex/I-rdy-002/verification_findings.md:14` ("Fix tracked in I-rdy-006
  (#502)"). These are config/SKU/cost prose, NOT judge prose:
  - `architecture.md:176` (`**Evaluator**: \`qwen/qwen3-8b\``) and
    `architecture.md:339` (`PG_EVALUATOR_MODEL` default table row).
  - `docs/runbook.md:274` — generator-cost example (`Qwen3-8B is $0.05/$0.40
    per M`) — a *cheaper-generator* pricing option, not the judge. (Codex
    iter-1 P2-2 raised this; classified #502-adjacent, as Codex itself noted.)
  - `docs/file_directory.md:252` and `ground_rules.md:316` — `V3.2-Exp +
    Qwen3-8B` model-pair lines (I-rdy-001 already realigned
    `file_directory.md:250`; the residual pair lines are model-config, #502).
  - `src/polaris_graph/llm/openrouter_client.py:359,373` — code comments in the
    evaluator-model rationale block (`Predecessor Qwen3-8B retained ...` / cost
    comment). The issue states "not a code change"; the openrouter_client
    model-rationale comment is I-bug-087 / #502 territory.
  - `tests/polaris_graph/test_b4_budget_imputation.py:31` — a pricing comment
    (`# Qwen3-8B: $0.05 in / $0.40 out`); a budget-imputation fixture fact.
- **Accurate changelog / commit history → exempt** per the issue acceptance:
  - `docs/pipeline_audit_context/06_recent_commits.md:32` — a commit-log line
    (`7e637cc PL: finalize model pair — ... Qwen3-8B evaluator`). Dated history.
- **Same-class judge prose, NOT named by the issue → recommended for #502**
  sweep (flag for Codex): `docs/pipeline_audit_context/16_pass_9_sweep_content_
  audit.md:116` ("the evaluator is Qwen3-8B") is judge-describing prose in the
  same `pipeline_audit_context/` doc-set as named site 3. The issue scopes
  #564 to exactly 3 sites ("Trivial 3-site doc edit"); expanding to a 4th
  named-doc would exceed the stated scope. It is a point-in-time audit-context
  note. Recommendation captured in the close-comment: fold into #502
  (model/config alignment) rather than silently widening #564.
- `CLAUDE.md:289` (`live_qwen_judge` in the repo-layout tree) is
  canonical-pin-protected — out of scope; documented residual, same pattern as
  #535's CLAUDE.md §3.0 residual.

Confirm: is restricting #564 to its 3 stated judge-prose sites (+ the same-file
P2-1 fold-in) — and routing the model-SKU residuals to #502 — the correct call,
versus widening #564 to a literal zero-`Qwen3-8B` sweep?

## 4. Files I have ALSO checked and they're clean

- `grep -rn '[Qq]wen' --include=*.py --include=*.md` across the tree: every
  other hit is either (a) a `.codex/**` historical brief/audit file (accurate
  audit-trail history — never edited), (b) a model-SKU string under #502/#527/
  #529 scope, or (c) the `qwen` family-label in `.env.example` / `openrouter_
  client.py` family table (a real OpenRouter family name, correct as-is).
- `src/polaris_graph/evaluator/live_judge.py` — only the module docstring
  (lines 1-8) is touched; no code, no other docstring, no identifier.
- No test references `Qwen3-8B` as a doc string under test; the rename test
  suite (`test_*` from #530) asserts identifiers/reason-codes, not prose.

## 5. Test / smoke

`python -c "import ast; ast.parse(open('src/polaris_graph/evaluator/live_judge.py').read())"`
— docstring edit must keep the file parseable. No behavioural test applies
(doc-only). The #530 rename test suite remains untouched and green.

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
