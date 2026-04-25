# Codex V30 Phase-2 strategic review

## Recommended path

other

Checkpoint the 2026-04-25 run-11 artifact now, skip a standalone run-12, and move directly into `V31` then `V32`, folding only the no-regret `C` fixes into that branch rather than spending another sweep on them first.

## Reasoning

- On strict ship-gate progress per hour, the options are not symmetric.
  - `A` is the only path with a real chance to turn the frozen `1 BB + 4 BO + 2 LB` board into `>=5/7 >=BO` with zero `LB`.
  - `B` is mostly mislabeled `A`: its regulatory synthesis and summary/timeline rebuild are already architectural work.
  - `C` as a standalone run is low-EV. It may polish `BO` dimensions, but it does not plausibly remove either persistent `LB`, so it likely burns another sweep to preserve the same scoreboard.

- The two remaining `LB` dimensions are genuinely architectural.
  - Regulatory is failing even when the underlying entities are already `open_access` in the manifest. The problem is not access; it is that `M-58` demands field-level verbatim extraction from noisy 25K-character HTML/PDF label text.
  - Narrative depth is failing even after the slot fixes because the body prose is still mostly slot-stacked, while contradiction-aware uncertainty lives in the appendix instead of shaping the main sections.

- `V31` is the right architecture, and it should be a separate module.
  - Do not route regulatory out of Phase 2 by default via `M-61`.
  - `M-61` is the right fallback for inaccessible or licensed evidence. FDA/EMA/NICE/HC label pages are mostly accessible already, so pushing them to human completion would be solving the wrong problem.
  - The right move is a dedicated `regulatory_synthesizer` that:
    1. segments fetched label text by jurisdiction-specific headings,
    2. selects the snippet(s) relevant to each target subsection,
    3. emits `2-4` verified prose sentences per subsection, and
    4. falls back to explicit gap language when no sentence verifies.
  - That is better than forcing regulatory prose through the generic M-58 field contract, which is too rigid for page-scale prose synthesis.

- `V32` is more tractable than it looks.
  - Run-11 Qwen is mainly objecting to hedging, not to section layout or missing section types.
  - You already have contradiction JSON and the relevant body sections. The missing step is section-local injection: feed only high-severity, same-endpoint/same-population disagreement clusters into `Safety`, `Comparative`, and `Population Subgroups`, and require one hedged sentence when a contradiction materially changes interpretation.
  - I would not treat this as a deep architecture rewrite. It is mostly prompt/routing work plus a relevance filter so noisy detector artifacts do not flood the prose.

- My disagreement with the current framing: a standalone run-12 is the wrong sequence.
  - If you do `C` first, you are optimizing inside a score box that still contains `2 LB`.
  - The selective `C` items are still worth doing, but only as branch hygiene inside the `V31/V32` cycle:
    - body-derived `Trial Summary` / `Timeline`,
    - `SURPASS-1` truncation guard,
    - `SURPASS-6` repair if it is quick and isolated.
  - They should not get their own sweep before the architectural work.

- On the word-count gap: it is partly verbosity, but not mostly a trick.
  - The current artifact is about `3114` words because much of `Efficacy` and `Regulatory` is terse slot prose or stub text.
  - ChatGPT and Gemini are not just padding; they are spending words on cross-trial interpretation, regulatory comparison, and uncertainty in the main body.
  - So this is an honest synthesis gap. I would not chase Gemini's length. I would target denser analytical prose after `V32`, likely in the `4.0k-4.5k` range, not `6.8k`.

- If the user goal is "audit-grade" rather than "deepest narrative," run-11 is already useful.
  - Strong contradiction handling plus auditable slot structure is valuable.
  - But that is a different claim from `BEAT_BOTH_SHIP`.
  - Do not blur those two claims by changing the gate mid-cycle.

## Ship gate clarification

- Keep `BEAT_BOTH_SHIP` strict: `>=5/7` dimensions at `BB` or `BO` and `zero LB`.
- Do **not** lower the bar now and call the result "ship." That would just rename the miss.
- The 2026-04-25 run-11 artifact is still `5/7 >=BO`, not `6/7`, so even a lenient gate like `>=6/7 >=BO + <=1 LB` would **not** ship it.
- What should change is the labeling, not the victory rule:
  - `BEAT_BOTH_SHIP`: external-quality claim; unchanged.
  - `PHASE2_CHECKPOINT`: internal milestone; commit-worthy, useful, audit-grade, but not beat-both.
- If you want an external label for the current artifact, use something like `AUDIT_GRADE_PREVIEW`, not `ship`.

## Concrete next 3 actions

1. Freeze the target and label run-11 as `PHASE2_CHECKPOINT`; stop using "ship" for this artifact.
2. Implement `V31` first: add the new regulatory synthesis path, and fold in only the no-regret structural guards from `C` that prevent obvious regressions.
3. Implement `V32` second: inject contradiction-aware hedging into `Safety`, `Comparative`, and `Population Subgroups`, then run the next full sweep only after both `V31` and `V32` land.
