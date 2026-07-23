# Morning summary — 2026-07-23 overnight

## 1. What shipped (committed + pushed, gated)
- Commit 73cd081c on branch fix/race-batch1-evidence-substrate (pushed to GitHub):
  Batch 3 pre-gen levers + Batch-2b hermetic test fixes + the 429 rate-limit hardening that
  unblocked the kimi-k3 generator. Fable full-scope audit: hard-rules clean, faithfulness byte-identical.
- kimi-k3 outage ROOT-CAUSED + FIXED: half was a config-name bug (PG_OPENROUTER_REQUIRE_PARAMETERS
  ignored; correct name OPENROUTER_REQUIRE_PARAMETERS), half Moonshot single-provider 429 throttling
  (now absorbed by PG_RATE_LIMIT_MAX_RETRIES=40 + jitter). Confirmed working on the live run.

## 2. RACE measurement — 3 arms, 3 draws each, tonight's judge (gpt-5.5)
| arm | levers | mean | spread | draws |
|---|---|---|---|---|
| max | 8 champion + Batch3 | 0.4933 | 0.0107 | 0.4875/0.4943/0.4982 |
| full | 8 champion levers | 0.4966 | 0.0066 | 0.4946/0.4943/0.5009 |
| baseline | all off | 0.5009 | 0.0166 | 0.5088/0.5017/0.4922 |

**VERDICT: the three arms are statistically INDISTINGUISHABLE.** Between-arm gaps (0.003-0.008) are
below the ~0.014 noise floor and smaller than within-arm spreads (up to 0.0166; baseline draw3=0.4922
fell below full's mean). => The compose-lever stack (the 8 champion levers AND Batch 3) is **FLAT** —
no detectable RACE effect, positive or negative. (Earlier I called it "net-negative"; that was reading
noise as signal — corrected.)

## 3. Judge drift (critical caveat)
Drift check: a stored champion report re-scored 0.4718 on tonight's judge (vs ~0.508 historically).
=> tonight's judge is ~0.02-0.04 LOWER. Historical 0.5084, ADORE 0.5265, Tavily 0.5244 are NOT
comparable to tonight's numbers. A cross-judge "we beat everyone" claim is NOT defensible. Benchmark
page left UNCHANGED (correct call).

## 4. Per-dimension (tonight's judge, avg across draws)
Insight ~0.507 (our highest), Comprehensiveness ~0.493, Instruction-Following ~0.492, Readability ~0.490.
All four within 0.017 — no single weak dimension internally. Readability sub-score is very noisy
(±0.027 draw-to-draw), so small formatting effects are undetectable at n=3.

## 5. Competitive study (scratchpad/COMPETITIVE_STUDY.md) — why leaders hit ~0.58
- The gap vs leaders is almost entirely **Insight** (leaders 59-61, field incl. us lower). IF & Readability
  are compressed 44-54 for everyone — they separate nobody.
- RACE STRIPS citations before judging => our 90% faithfulness = 0 RACE points.
- Retrieval VOLUME is a trap (Kimi 70+ queries -> Insight 42, near last). Our search stack isn't the bottleneck.
- Insight comes from the WRITER reasoning with an analytical framework, fed PRE-structured conflict —
  NOT from evidence reshuffling (why Batch3 was flat) and NOT from a post-hoc pass (proven to regress 16-27%).
- **Lever #1 (biggest): stronger-reasoning generator on the section-writer role** (measure the ceiling).
- Lever #2: draft-feedback deepening (detect thin sections -> targeted re-research). Lever #3: pre-writing
  claim-graph + contradiction adjudication fed to the writer. All pre-generation, inside the no-post-gen firewall.

## 6. Readability track (operator-directed, in progress)
RACE Readability rubric = "clarity of structure, fluency, EFFECTIVENESS OF DATA PRESENTATION, ease of
understanding" — and the weight is DYNAMIC (0.25 for data-heavy tasks like ours, not fixed 0.14). Our
reports bury lots of numbers in prose with only 1-2 thin tables. We NEVER maxed formatting. Running a
fast, paired, noise-beating loop: reformat existing checkpoints (render-only, no content change) into
proper data tables + bold + bullets, score plain-vs-formatted paired + replicated, port winners to
pre-gen. Honest ceiling: +0.006-0.012 Overall, but real + better for humans. NOT the field-beating lever.

## 7. Recommendation
Stop investing in compose-side levers (flat). Two tracks: (A) [big] stronger-writer-model A/B to
measure the Insight ceiling; (B) [cheap parallel] the readability formatting loop. Fix the measurement
harness to always run a same-judge baseline + more draws so gains are detectable above the ±0.027 noise.
