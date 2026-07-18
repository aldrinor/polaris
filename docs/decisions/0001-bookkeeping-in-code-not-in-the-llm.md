# 0001. Do provenance bookkeeping in code, not in the LLM

Status: accepted

Date: 2026-03-24

## Context

Two independent failures pointed at the same root cause: a token-prediction model is bad at deterministic bookkeeping, and asking it to do that bookkeeping degrades output.

- Citations. Trying to make a base model emit citations by putting distinctive phrasing in the prompt template failed. Any distinctive phrase in a qualitative-claim template gets copied verbatim into the output. Across sessions 51-53 (2026-03-23/24) three approaches — Generate-Then-Attribute, targeted template patches, and a hybrid numbered-evidence scheme — all regressed below the 83.5 baseline. The commercial systems that solve citation (OpenAI, Cohere, Perplexity, Gemini) do it by fine-tuning or a server-side grounding engine, not by prompting.
- Evidence-ID lists. Asking an LLM to preserve or merge long lists of evidence IDs produced ~50% error at 200+ items (PRE-032, 2026-02-18, Prosus research). Remapping to short IDs before the call gave 99.3% ID preservation; doing the theme merge in code preserved 850/850 IDs in zero LLM calls.

## Decision

Do not ask the LLM to carry, preserve, or generate machine provenance. Attach citations programmatically after generation (or use a model actually trained/served for grounding). Remap long evidence-ID lists to short IDs before any LLM call, and do the actual merge/dedup in code.

## Consequences

- The citation failure is inherent to a non-grounding model, so more prompt engineering cannot fix it. Do not spend another cycle patching templates — that path failed three times before the conclusion stuck.
- Programmatic ID handling is cheaper, deterministic, and near-lossless. Bookkeeping is exactly what code does perfectly and what the model does worst.
- The prompt now stays free of distinctive citation phrasing that the model would echo, which keeps qualitative-claim output clean.
- This is the meta-principle behind later decisions (ADR 0016): whenever a machine token or an exact string must survive a generation step, compute it deterministically, never let the model hand-type it.
