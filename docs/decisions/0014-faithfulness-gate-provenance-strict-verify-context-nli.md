# 0014. The faithfulness gate: provenance tokens, strict_verify, context-level NLI and numeric match (lexical overlap dropped)

Status: accepted

Date: 2026-07-10

## Context

The faithfulness engine is the pipeline's only hard gate for claims (ADR 0006). Its durable mechanical floor was long-standing: every generated sentence carries `[#ev:evidence_id:start-end]` provenance tokens, and `strict_verify` drops any sentence whose evidence-id is not in the pool, whose span bounds are invalid, or whose decimals do not all appear in the cited span. A section below the verified threshold regenerates once; a run with no verified section returns `abort_no_verified_sections` — a real verdict artifact, never an empty pseudo-report.

But one sub-check backfired. The old rule required a sentence to share at least two content words with its cited span (`PG_PROVENANCE_MIN_CONTENT_OVERLAP`, strict_verify condition d). That lexical gate forced near-verbatim COPYING of raw spans to pass, and same-meaning claims phrased in different words were wrongly failed. Copying spans drags chrome and quote-dump into the output and blocks real synthesis — a root cause of shallow reports. Operator-locked reversal (2026-07-10).

Separately, the live entailment check (f) was an LLM-as-judge (GLM-5.2) carrying socket-hang and per-claim cost, while the config's local fast-NLI slot sat declared-but-empty (`entailment_judge.py:82`, `verify_models_landscape_2026.md`).

## Decision

A sentence is faithful if and only if (1) its meaning is entailed by its cited evidence at the CONTEXT level (NLI-style), AND (2) every number and decimal in it matches the cited evidence. That is the whole bar.

Delete the ≥2-content-word lexical overlap rule and the verbatim-fallback-forced-copy. Keep the durable mechanical floor: evidence-id in pool, span bounds valid, numeric match, provenance tokens, and the zero-verified loud abort.

Fill the empty local fast-NLI slot with a small (0.15-8B) open-weight grounded-factuality model running as an always-on local first-pass and corroborator beside the LLM judge. Co-lead OSS candidates: FactCG-DeBERTa-L (0.4B, MIT) for pure NLI, LettuceDetect (ModernBERT, MIT) for token-level span-flagging, Granite Guardian 3.3-8B for the reasoning-judge lane. Bake-off discriminator: LLM-AggreFact balanced accuracy plus a clinical slice (MedHal/MedHallu).

## Consequences

- Numbers still need strict matching, because a wrong dose is lethal; meaning is judged by entailment, not by word overlap.
- Do not resurrect any word-match gate as if it proved grounding. Word presence is not entailment, and the lexical gate is exactly what starved depth.
- The local grounded-factuality model makes the SAME gate more accurate and kills the judge-hang and per-claim cost; it never widens a span or flips `is_verified`. Swapping the model inside the frozen engine is the safe place to improve.
- Bespoke-MiniCheck-7B (77.4% on the yardstick) is reference-only — its license is "contact us", not OSS, so it is a benchmark target, not a shippable component.
- The checked-in `CLAUDE.md` §9.1.3/§9.2 wording lags this reversal and needs an operator-signed update; §-1.1.1 already overrides it.
