# RACE measurement — running results (tonight's judge, task-72)

ALL scores below are from TONIGHT's RACE judge (gpt-5.5). They are NOT comparable to historical
numbers (champion 0.5084, ADORE 0.5265, Tavily 0.5244) — the drift check proved tonight's judge is
~0.036 lower (see PREREGISTRATION_race_max.md). Only WITHIN-tonight comparisons are valid.

## Drift check (calibration)
- champ_clean_1 (OLD champion-recipe report, Jul-21, predates the 8-lever set): **0.4718**
  (Comp .4842 / Insight .4728 / IF .4652 / Read .4541)

## Arm: max = 8 champion levers + Batch3 (contradiction mining + relation packs)
- draws: [0.4875, 0.4943, 0.4982]
- **mean = 0.4933, spread = 0.0107**  (DONE 13:43Z)
- note: throttle events during gen handled by the 429 retry-harden (worked)

## Arm: full = 8 champion levers only  (RUNNING, task btx0d1qak, then baseline)
- draws: [0.4946, 0.4943, 0.5009]
- **mean = 0.4966, spread = 0.0066**  (DONE 15:27Z)
- BATCH3 EFFECT = max(0.4933) − full(0.4966) = **-0.0033** => FLAT / marginally NEGATIVE (within noise).
  full (WITHOUT Batch3) scored slightly HIGHER. Batch3 does not help; do not enable it for champion.

## Arm: baseline = all levers off  (RUNNING, draw 3 pending)
- draw 1: **0.5088**  draw 2: **0.5017**  (draw 3 pending)
- mean-so-far (2 draws): **0.5053**  => baseline(0.5053) > full(0.4966) > max(0.4933).
  THE COMPOSE-LEVER STACK IS NET NEGATIVE: report scores HIGHEST with all levers OFF.
  full-stack "gain" = full − baseline = -0.0087; Batch3 = max − full = -0.0033. Both hurt. Confirm w/ draw 3.

## Per-dimension finding (tonight's judge, all draws)
- Our 4 dims are clustered ~0.49-0.51; Insight is our HIGHEST (~0.507), Readability our lowest (~0.490) but by a hair.
- Readability: reports WITH tables (max/full, 8 table-rows) scored 0.47-0.49; the NO-table baseline scored 0.502.
  => adding our (thin) tables did NOT raise Readability. Formatting is minimal (1-2 tiny tables, 0 bullets, 0 charts).
- PENDING PROBE (operator asked): rich-format A/B — reformat one report's SAME content with proper tables+bullets+bold,
  RACE-score vs original, measure Readability delta. Settles whether formatting quality matters or ceiling is real.

## Within-judge verdict (fill when arms complete)
- Batch3 effect = max_mean − full_mean  (real if ≥ ~0.014, spreads ≤ ~0.010)
- Full-stack gain = max_mean − baseline_mean
- Honest headline: (TBD)
