# POLARIS full-audit pass 8 — dynamic echo threshold verification

**Tight spot check.** 10-15 min max. Commit: `e38c43f`.

## What to verify

After pass 7 found the hard `>=2` threshold over-strict on 4 cases,
I implemented a dynamic threshold:

- Question has ≥2 superlatives → threshold = 2 (strict, adversarial defense)
- Question has ≤1 superlative → threshold = 1 (loose, paraphrase-friendly)

Code: `src/polaris_graph/evaluator/external_evaluator.py` PT13 block,
`echo_min_content_words` variable.

## Your mandate

### 1. Re-run the 4 over-strict cases from pass 7 section 3

Construct direct `run_external_evaluation` calls for each:

1. **Short-question direct answer** — Q: `"best RAG practices?"` +
   prose: `"Hybrid retrieval with dense embeddings and learned
   sparse vectors is the best approach for most production
   deployments."` → PT13 must now **exempt** (overlap `{best}=1`
   against 1-superlative question → threshold=1 → pass).

2. **Framework answer** — Q: `"What are the top LLM frameworks?"` +
   prose: `"LangChain is among the top choices."` → must exempt.

3. **Largest-LLM paraphrase** — Q: `"What are the largest
   open-source LLMs?"` + prose: `"Llama 3.1 405B is among the
   largest openly available models."` → must exempt.

4. **CRISPR paraphrase** — Q: `"What are the top CRISPR delivery
   methods?"` + prose: `"Lipid nanoparticles are a top option for
   liver-targeted editing."` → must exempt.

For each, run the evaluator, report `pt13.passed` + `pt13.details`.
All 4 should now show `passed=True`.

### 2. Re-run the adversarial reproducer

Q: `"What is the best leading superior top unparalleled unmatched
unprecedented largest highest greatest approach for drug X?"` +
prose: `"This method is unparalleled. Results were unmatched. The
outcome is greatest. The effect is superior."` — PT13 must still
**flag** with 4 unhedged (threshold=2 strict path for 10-superlative
question).

### 3. The topic-shift control case

Pass-7 Codex case 5: Q `"best practices for RAG"` + prose
`"The best tokenization strategy for embeddings is subword BPE."` —
under dynamic threshold=1, this now exempts. Codex originally
judged it *should* flag.

Run it. Report PT13 status. Is this a meaningful regression or a
trade-off I can accept?

Specifically: in a real report, would a lone topic-shift sentence
ever be the ONLY unhedged superlative? PT13 passes when unhedged
count ≤ 1, so a single case doesn't fail the rule. If 2+ topic-shift
sentences occurred in one report, PT13 would still fail (each only
shares `{best}=1` with the question, but the combined count > 1).

Judgment: is this acceptable or should we further refine?

### 4. Suite

`python -m pytest tests/polaris_graph/test_external_evaluator.py -q`
should show 13 pass.

### 5. Verdict

One of:
- **READY-FOR-8-QUERY-SWEEP**: dynamic threshold right-sized
- **NOT-READY**: still over-strict OR newly under-strict
- **CONDITIONAL**: one more targeted change recommended

## Output

Write to `outputs/codex_findings/full_audit_pass_8/findings.md`
with frontmatter:

```yaml
---
verdict: READY-FOR-8-QUERY-SWEEP | NOT-READY | CONDITIONAL
pass: 8
commit: e38c43f
four_over_strict_cases_now_exempt: true | false
adversarial_still_flags: true | false
topic_shift_acceptable_tradeoff: true | false
rationale: |
  <1-3 sentences>
---
```

Followed by `## 1..5.` sections.

## Duration

10-15 minutes.

## Auth

OAuth chatgpt.

---

Start:
```
git show e38c43f --stat
python -m pytest tests/polaris_graph/test_external_evaluator.py -q
```
