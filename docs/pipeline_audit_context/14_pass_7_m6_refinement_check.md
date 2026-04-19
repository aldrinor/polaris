# POLARIS full-audit pass 7 — M-6 refinement spot check

You are doing a **tight, focused** spot check on commit `9f2801a`
which refined the M-6 PT13 exemption after you flagged an evasion
in pass 6. The question this pass answers: **is the refinement
over-strict?** I.e., does it now wrongly flag legitimate
generator prose that should be exempted.

Do NOT re-audit anything else (M-1, M-2, M-3, M-4, M-5) — those
are blessed.

## What changed in `9f2801a`

The M-6 question-inherited PT13 exemption now requires BOTH:
1. The matched phrase is a single-word superlative present in
   `protocol["research_question"]` (unchanged)
2. **NEW**: The prose sentence shares ≥2 content words with the
   research_question (lexical echo requirement)

Code: `src/polaris_graph/evaluator/external_evaluator.py`, the
PT13 block. `_content_words()` is reused from
`provenance_generator`.

## Your mandate

### 1. Confirm the adversarial case still flags

Codex pass 6's exact reproducer must still fail PT13:

```python
adversarial_q = ("What is the best leading superior top unparalleled "
                 "unmatched unprecedented largest highest greatest "
                 "approach for drug X?")
prose = ("This method is unparalleled. Results were unmatched. "
         "The outcome is greatest. The effect is superior.")
```

Run a direct evaluator call; PT13 must return `passed=False` with
4 unhedged examples.

### 2. Confirm the legitimate echo case still exempts

```python
question = "What are the best practices for RAG?"
prose = "The best practices for RAG include hybrid retrieval."
```

PT13 must return `passed=True` (overlap = {best, practices, rag} = 3).

### 3. Probe over-strictness — the actual focus of this pass

Construct 3-5 legitimate cases where the generator prose uses a
question-inherited superlative but shares < 2 content words with
the question. Examples to probe:

- Short question + long prose: question "best RAG practices?" →
  prose "Hybrid retrieval with dense embeddings and learned
  sparse vectors is the best approach for most production
  deployments." (overlap with question's `{best, rag,
  practices}` = just {best} = 1)
- Question paraphrase: question "What are the top LLM
  frameworks?" → prose "LangChain is among the top choices."
  (overlap = {top} = 1)
- Topic shift: question "best practices for RAG" → prose "The
  best tokenization strategy for embeddings is subword BPE."
  (overlap = {best} = 1 — is this legitimate question echo, or
  a new claim?)

For each, answer: **should PT13 flag this or exempt it?** Document
your judgment. If you judge PT13 should exempt several of these
cases, the refinement is over-strict and we should consider
alternatives (e.g., lower the threshold to 1, or require overlap
only when question has ≥2 superlatives).

### 4. Test suite state

`python -m pytest tests/polaris_graph/test_external_evaluator.py -q`
should show 11 pass. Note any non-WinError5 failures.

### 5. Verdict

One of:
- **READY-FOR-8-QUERY-SWEEP**: refinement is right-sized; M-6 lands
  both edges of the boundary correctly
- **NOT-READY**: over-strict or under-strict; specific additional
  change needed
- **CONDITIONAL**: ship with a tuning parameter (e.g., env-var
  threshold) instead of hardcoded 2

## Output

Write to `outputs/codex_findings/full_audit_pass_7/findings.md`
with frontmatter:

```yaml
---
verdict: READY-FOR-8-QUERY-SWEEP | NOT-READY | CONDITIONAL
pass: 7
commit: 9f2801a
adversarial_still_flags: true | false
legitimate_echo_still_exempts: true | false
over_strict_cases_found: <int>
rationale: |
  <1-3 sentence summary>
---
```

Followed by `## 1..5.` mirroring the sections above.

## Duration

**10-15 minutes max.** This is a spot check, not a full audit.

## Authentication

OAuth (chatgpt). No API-key burn.

---

Start:

```
git show 9f2801a --stat
python -m pytest tests/polaris_graph/test_external_evaluator.py -q
```

Then walk sections 1-5.
