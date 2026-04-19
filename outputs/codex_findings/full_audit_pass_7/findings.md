---
verdict: NOT-READY
pass: 7
commit: 9f2801a
adversarial_still_flags: true
legitimate_echo_still_exempts: true
over_strict_cases_found: 4
rationale: |
  The adversarial stuffed-question reproducer still fails PT13, and the direct lexical-echo RAG case still exempts. However, the >=2 content-word threshold is over-strict for short questions and natural paraphrases: I found four legitimate direct-answer sentences that would be counted as unhedged only because they share the inherited superlative but not a second exact content token.
---

## 1. Adversarial Case Still Flags

Confirmed with a direct `run_external_evaluation` call.

- `research_question`: "What is the best leading superior top unparalleled unmatched unprecedented largest highest greatest approach for drug X?"
- Prose: "This method is unparalleled. Results were unmatched. The outcome is greatest. The effect is superior."
- PT13 result: `passed=False`
- Details start with `4 unhedged`, with examples for `unparalleled`, `unmatched`, and `greatest` shown in the truncated details.

This edge of the refinement is still working.

## 2. Legitimate Echo Case Still Exempts

Confirmed with a direct `run_external_evaluation` call.

- `research_question`: "What are the best practices for RAG?"
- Prose: "The best practices for RAG include hybrid retrieval."
- Question content words: `{best, practices, rag}`
- Sentence overlap: `{best, practices, rag}` = 3
- PT13 result: `passed=True`

The intended lexical-echo exemption still works when the prose repeats the question wording.

## 3. Probe Over-Strictness

I treated "flag" here as "the sentence is counted in PT13's unhedged examples"; for isolated single-sentence cases PT13 can still pass because the rule tolerates up to one unhedged example.

1. Short question, direct answer paraphrase
   - Question: "best RAG practices?"
   - Prose: "Hybrid retrieval with dense embeddings and learned sparse vectors is the best approach for most production deployments."
   - Exact overlap: `{best}` = 1
   - Current behavior: counts as unhedged.
   - Judgment: should exempt. This is a direct answer to the "best RAG practices" question; "hybrid retrieval" is the RAG practice, and "approach" is a natural paraphrase of "practice."

2. Framework question, answer names specific frameworks
   - Question: "What are the top LLM frameworks?"
   - Prose: "LangChain is among the top choices."
   - Exact overlap: `{top}` = 1
   - Current behavior: counts as unhedged.
   - Judgment: should exempt. The sentence is a concise direct answer; the framework identity is supplied by "LangChain" rather than repeating "LLM frameworks."

3. Largest model paraphrase
   - Question: "What are the largest open-source LLMs?"
   - Prose: "Llama 3.1 405B is among the largest openly available models."
   - Expected exact overlap: `{largest}` = 1 because `open-source`/`openly available` and `LLMs`/`models` do not exact-match.
   - Current behavior: would count as unhedged under the same threshold.
   - Judgment: should exempt. This is a legitimate paraphrase of the question, not a new unrelated superlative.

4. Domain-specific method paraphrase
   - Question: "What are the top CRISPR delivery methods?"
   - Prose: "Lipid nanoparticles are a top option for liver-targeted editing."
   - Expected exact overlap: `{top}` = 1 because "CRISPR delivery methods" is answered by the domain-specific phrase rather than repeated.
   - Current behavior: would count as unhedged under the same threshold.
   - Judgment: should exempt. This is a direct-answer paraphrase where the second topical content word is semantic, not lexical.

5. Topic shift control
   - Question: "best practices for RAG"
   - Prose: "The best tokenization strategy for embeddings is subword BPE."
   - Exact overlap: `{best}` = 1
   - Current behavior: counts as unhedged.
   - Judgment: should flag. This shifts from RAG practices to an independent tokenization claim.

Over-strict cases found: 4. This exceeds the brief's 2+ case threshold for an over-strict signal.

## 4. Test Suite State

`python -m pytest tests/polaris_graph/test_external_evaluator.py -q` result:

- 11 passed
- One warning: pytest could not create `.pytest_cache` due `[WinError 5] Access is denied`
- No non-WinError5 failures observed

## 5. Verdict

NOT-READY.

The hard `>=2` exact content-word threshold preserves the adversarial fix but is too strict for legitimate short-question/direct-answer paraphrases. A better next refinement would keep the adversarial stuffed-question protection while reducing false positives for normal questions, for example by lowering the echo threshold to 1 when the question has only one superlative-family term, or by requiring the stricter overlap only when the research question contains multiple superlatives.
