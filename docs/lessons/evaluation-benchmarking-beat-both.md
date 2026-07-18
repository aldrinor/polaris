# Lessons: Evaluation, benchmarking & beat-both scoring

Canonical home: memory `project_goal_number_one_deeptrace_drbench2_2026_06_20.md`, `feedback_prove_internal_scorer_correct_not_official_harness_flag_2026_07_05.md`, `feedback_benchmark_the_tool_not_a_component_2026_05_28.md`; `docs/benchmark/scoring_rubric.md`.

The pinned goal is #1 on BOTH DeepTRACE and DeepResearch-Bench-II (all-GLM), benchmarked like FS-Researcher (RACE). This hub covers coverage as a co-equal workstream, honest scoring, and proving our own scorer.

## Coverage is a co-equal, first-class workstream — a defect audit is structurally blind to absence

A §-1.1 defect audit only finds what is PRESENT and wrong (fabrications, bad citations, off-topic drift) — all faithfulness problems. Coverage, breadth, and completeness gaps are an ABSENCE (rubric points never addressed, sources never cited), and you cannot audit a thing that isn't there. Stand coverage up from the start as its own deliberate workstream with equal rigor (built + dual-gated + measured on a real run), never derived from a defect list. To attack coverage, measure the retrieved-vs-cited breadth funnel and widen it, never cap it.

Why: The standing goal is #1 on BOTH faithfulness (DeepTRACE) AND coverage (DeepResearch-Bench-II). Three traps drift the campaign to faithfulness alone: letting the audit's item list become the whole mission; streetlight bias (faithfulness fixes have clean offline RED/GREEN, coverage needs a real run); and leaning to the board we are already strong on.

Evidence: `feedback_defect_audit_blind_to_coverage_always_coequal_workstream_2026_07_05.md` (operator flagged hard 2026-07-05).

Recurrence: Operator flagged hard; a recurring drift.

## Never present a faithfulness number alone — pair it with coverage, and treat a removal-driven rise as a regression

A faithfulness/precision number over a shrunken denominator is a lie. faithfulness_score=1.0 was reported while ZERO citations reached the prose, because it was computed only over the handful of surviving claims. Never present a faithfulness or precision number alone; pair it with coverage (how many claims/sources survived versus started). A rising faithfulness number caused by content removal is a regression, not a win.

Why: High precision at the cost of recall reads as excellent (23/24 = 95.8%) while hiding that 19 of 43 original claims were dropped. This connects the metric-gaming mindset to a concrete reporting rule and matches the coverage-is-co-equal rule.

Evidence: `logs/bug_log.md` BUG-WIKI-REF0 (faithfulness=1.0 "computed on surviving claims, masks that none made it into prose"), BUG-025/029 (95.8% on 24 of 43), BUG-FAITHLOG (summary log showed 0.0% while JSON had 1.0).

Recurrence: Recurring — appears as both inflation and misleading-log across multiple runs.

## Before committing spend to a new metric or harness, run a small REAL probe

Diff-review and stub smoke tests pass on metrics that are fatally slow or that cannot tell candidates apart. Run a small REAL probe first.

Why: A metric can be logically correct yet useless; only a real run exposes cost blow-up and zero discriminating power. The qgen metric was killed ~40 min and $16.7 in: an early behavioral read showed it would take ~10k GLM calls and hours, AND scored 0-vs-0 (non-discriminating) because the DRB-II info_recall rubric demanded citing an exact named study neither method retrieved — yet diff-review had approved it.

Evidence: qgen metric KILLED (2026-06-23); memory `feedback_offline_tests_not_real_preflight`.

Recurrence: Recurring theme — "offline tests are not a preflight" is a standing rule.

## Prove our own scorer correct, then trust it — stop caveating "not the official harness"

When we build or use an internal scorer (e.g. our DeepTRACE metrics), the deliverable is to GATE its correctness (Codex + Fable line-by-line against the published formulas), then treat the number as valid for our A/B and beat-both optimization and STOP re-flagging "this is our own computation, not the official harness." Do not spend money chasing the official harness's dependencies before the internal one is proven sound; pursue official parity only if the operator asks or a leaderboard submission needs it.

Why: An unverified self-scorer is the actual danger — it could silently mis-score and make us optimize the wrong thing. A verified-correct internal scorer is fully usable, and the "not official" label, once stated, adds only noise.

Evidence: `feedback_prove_internal_scorer_correct_not_official_harness_flag_2026_07_05.md` (operator flagged sharply 2026-07-05).

Recurrence: Operator flagged the repeated caveat as noise.
