# I-bug-104 — Per-decimal extraction prompt rewrite (FAILED)

**Status:** FAILED, reverted, archived for future reference.

## Hypothesis (2026-05-09)

A 100-line rewrite of the generator prompt emphasizing **per-decimal extraction discipline** ("for every numeric value in your sentence, the EXACT digits MUST appear in the cited span — no rounding, no approximation, no near-miss") would reduce strict_verify drops on the `numeric_mismatch` failure mode.

**Reasoning:** the 2026-05-09 audit surfaced sentences like "tirzepatide reduced HbA1c by ~1.5%" cited against a span containing "1.55%" — the 0.05% rounding triggered `numeric_mismatch` drop. A stricter prompt might suppress these near-miss approximations.

## Setup

- Branch: `bot/I-bug-104-prompt-rewrite` (subsequently abandoned, never PR'd)
- Modified: `src/polaris_graph/generator/multi_section_generator.py` — replaced ~80-line prompt with 180-line version emphasizing per-decimal discipline + 6 worked examples of "say the same digits or say nothing".
- Goldset: same 5 Carney-track questions as I-bug-103.
- Run: full sweep against live OpenRouter (DeepSeek V3.2-Exp generator + Gemma 4 31B evaluator).

## Result

**Catastrophic regression:**

| Metric | Baseline | Experiment | Δ |
|---|---|---|---|
| Verified-sentence rate | ~28% | ~13% | **−15 pp** |
| `numeric_mismatch` drops | dominant | reduced ~30% | improvement |
| `no_provenance_token` drops | minor | dominant | **major regression** |
| `overlap_too_low` drops | secondary | tertiary | (relative) |
| Total verified output (chars) | ~1500 | ~600 | −60% |

The over-strict prompt caused the generator to **omit citations** rather than risk a mismatch. Sentences came back without `[#ev:...]` tokens at all — `no_provenance_token` drops shot up from minor to dominant. Net: we traded a small-grain failure (numeric_mismatch on near-miss decimals) for a coarse-grain failure (no provenance at all). Verified output shrank to <40% of baseline.

The prompt's "say nothing if you can't say it exactly" instruction was misread by the generator as "skip the citation if the value is approximate" rather than "use the exact digits from the span".

## Why archived (not closed silent)

The lesson generalizes: **prompt over-discipline can shift failure modes laterally, not reduce them**. Future prompt-engineering attempts on the strict_verify failure-rate problem should A/B compare ALL drop-reason buckets, not just the targeted one.

The 100-line prompt rewrite was reverted on the same day. No production change shipped from this experiment.

## Follow-up direction (different issues)

- **I-bug-101 (FPR audit):** distinguishes "judge dropped legit sentence" (FPR) from "generator emitted unverifiable sentence" (real generator gap). The right framing for prompt iteration.
- **I-bug-105 + I-bug-108 (already shipped):** two-layer report contract + sentence repair loop. Solved the underlying "don't drop everything just because one sentence fails" problem at the architecture level, not the prompt level.
- **Path A bakeoff (I-bakeoff-A-001):** if a different generator (Qwen 3.5 Plus, Opus 4.7, GPT-5) handles per-decimal discipline natively without prompt over-engineering, the right move is a model swap, not a prompt rewrite.

Closing as superseded by these forward-looking follow-ups, with no code shipped from this experiment.
