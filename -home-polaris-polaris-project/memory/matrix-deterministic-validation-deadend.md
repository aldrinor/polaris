---
name: matrix-deterministic-validation-deadend
description: "CONFIRMED (Sol, 3 adversarial rounds): validating LLM-generated synthesis-matrix rows for faithfulness by deterministic string-matching is a dead end — needs a structured-claim-tuple builder, not a validator patch"
metadata:
  node_type: memory
  type: project
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

**2026-07-22 overnight — the synthesis-matrix (cross-study comparison table, the RACE Insight lever) capability + validation outcome.**

**WHAT WORKED (committed 9cbb2f60, Sol-gated PASS, pushed):** the matrix was shipping 0 tables because kimi-k3
is reasoning-first but was in NEITHER openrouter reasoning registry, so no reasoning budget was transmitted and
it burned the whole max_tokens on reasoning -> content="" -> every call truncated (finish_reason=length). FIX:
add moonshotai/kimi-k3 to _REASONING_FIRST_MODELS (openrouter_client.py — NOT _ALWAYS_REASON_MODELS, which is
checked first + applies GLM-specific temp/CoT-stripping); register 'synthesis_matrix' in reasoning_trace CALL_
TYPES; raise PG_TRIAL_TABLE_MIN_MAX_TOKENS 6000->24576 + REASONING 2048->16384. RESULT: truncation 6/10 -> 0/10;
K3 now emits genuinely faithful rows. This capability fix is REAL and durable.

**WHAT'S A DEAD END (reverted; do NOT retry as a validator patch):** with truncation fixed, the strict
verbatim-equal-clause validator dropped 100% of faithful rows (generic labels like "one forecast" + close
paraphrase aren't verbatim spans). I tried a deterministic 'subset' relaxation (grounding a row against the
citation-scoped unit; verbatim Context/Measure/Finding/Design; relaxed Study; clause-touch + polarity guards;
sign-binding + contraction normalization). Sol GATED IT 3 ADVERSARIAL ROUNDS and kept finding surviving
fabrications: token-set loses order/binding; same-clause binding swap; Study cross-clause remap; digit-comma
edge; and-clause intersection; "cannot increase"; Unicode signs (−/≈/₹); although/despite/versus remapping;
verb-scoped negation (only entailment catches it — BANNED). Sol's DEFINITIVE conclusion (verbatim): "arbitrary
prose-span recombination cannot guarantee semantic binding through a finite delimiter/negation list. Accept
subset rows only from an anchored single-predicate deterministic grammar or structured claim tuple; otherwise
drop." Each fix traded yield for safety and never converged — the SAME wall that produced the earlier (banned)
entailment attempt. See [[no-entailment-ever-rule]].

**THE ONLY CORRECT PATH (a dedicated effort, not a one-night patch):** build tables by CONSTRUCTION-BY-VALIDITY
— a deterministic extractor that pulls structured claim TUPLES (subject, measure, value+unit+sign, design,
citation) from the ALREADY-VERIFIED prose via an anchored single-predicate grammar, then assembles the table
from tuples. Because each cell IS a bound prose span (never LLM-recombined), binding is preserved by
construction and it's fabrication-safe without entailment. This is Sol's ReportBlock/typed-claim design from
the deep audit. Until it exists, the matrix stays STRICT (suppresses safely; 0 tables; no regression, no
fabrication). Do NOT enable a relaxed string-match validator — Sol will always find a hole, and shipping
fabrication into a faithfulness-differentiated product is unacceptable. See [[race-scoring-mechanics]].
