# Codex V30 Phase-2 run-14 audit

**7-dimension verdict**: BB=1/7 | BO=4/7 | LB=2/7 | TIE=0/7

## Ship classification

- Gate: `ITERATE`
- Net progress vs run-12: `BB+0, BO+0, LB+0`
- Regressions: narrative-surface compression in `Safety`, `Comparative`, and `Population Subgroups` (`run-14 report.md:71,75,79` vs `run-12 report.md:71,75,79`); thinner FDA/NICE prose inside already-LB Regulatory (`run-14 report.md:47-63` vs `run-12 report.md:47-63`); Thomas clamp lost population + glucagon detail (`run-14 report.md:41`; `run-12 report.md:41`)

## V33 (M-72) effectiveness

Verdict: **M-72 did not lift Narrative depth from `LB` to `BO`**. The telemetry confirms the cross-trial layer fired in exactly the intended places (`outputs/full_scale_v30_phase2_run14_stdout.log:10619-10622,10628,10639`), but the rendered report is shorter and less synthesizing than run-12 where that lift was supposed to land.

The pattern looks like constraint, not enrichment. Pre-bibliography body length falls from about 2,564 words in run-12 to about 1,966 in run-14; in-body citation markers fall from 101 to 86; unique cited sources in the body fall from 33 to 26. The specific M-72 target sections are the clearest evidence:

- `Safety`: 6 cited synthesis sentences in run-12 collapse to 3 in run-14 (`run-12 report.md:71`; `run-14 report.md:71`)
- `Comparative`: 7 cited synthesis sentences collapse to 3 (`run-12 report.md:75`; `run-14 report.md:75`)
- `Population Subgroups`: 9 cited synthesis sentences contract to 7 (`run-12 report.md:79`; `run-14 report.md:79`)

Qwen also cuts against the idea of a clean narrative win: `citation_tightness` improves to `acceptable`, but `hedging_appropriateness` worsens from `acceptable` in run-12 to `needs_revision` in run-14 (`run-12 qwen_judge_output.json:20-22`; `run-14 qwen_judge_output.json:20-22`). On the core V33 thesis, the answer is no: the cross-trial prompt block behaved more like an upper bound than a floor.

## 7-dim analysis

Line refs below use `run-14 report.md` and `run-12 report.md` as shorthand for the two report paths.

### 1. Citations — BO

Still `BO`, not `BB`. Run-14 still beats Gemini on source hierarchy because the bibliography remains anchored in T1 primary trials and official regulatory labels across the pivotal SURPASS program plus FDA/EMA/NICE/Health Canada (`run-14 report.md:128-142`). That basic source stack is still stronger than Gemini's known tendency to mix in weaker media/promotional material.

It still loses to ChatGPT on density/tightness. The `Trial Summary` references are still off from `SURPASS-3` onward (`run-14 report.md:85-88` vs bibliography `run-14 report.md:129-134`), and `Limitations`, `Methods`, and most of `Contradiction disclosures` still expose uncited telemetry prose (`run-14 report.md:92,95-104,107-124`). Qwen's citation verdict improves (`run-14 qwen_judge_output.json:8-10` vs `run-12 qwen_judge_output.json:8-10`), but the human comparator ranking does not change because the report is still less densely and less adjacently supported than ChatGPT's narrative style.

Delta vs run-12: same category, slightly weaker inside the category. Marker density per 1K words rises only because the body got shorter; the actual citation surface regresses in absolute terms.

### 2. Regulatory — LB

Flat at `LB`. V33 did not touch the architecture here, and the section remains too thin to beat either comparator. All four jurisdictions still appear in-body (`run-14 report.md:45-67`), but the content is mostly stub-level:

- FDA Mounjaro is two short label facts (`run-14 report.md:47`)
- FDA Zepbound repeats the coadministration limitation rather than building a fuller risk/use frame (`run-14 report.md:51`)
- EMA is a single obesity-use sentence that still does not satisfy the pediatric-heavy heading (`run-14 report.md:55`)
- NICE TA924 is just a contact email (`run-14 report.md:59`)
- NICE TA1026 is only a funding-arrangements sentence (`run-14 report.md:63`)
- Health Canada remains gap-only (`run-14 report.md:67`)

Delta vs run-12: flat category, slightly thinner prose. Run-12 at least gave fuller FDA Mounjaro/Zepbound sentences and a somewhat longer TA1026 block (`run-12 report.md:47-63`).

### 3. Jurisdiction — BO

Flat at `BO`. The breadth is still there: U.S., EU, U.K., and Canada are all explicitly represented (`run-14 report.md:45-67`), so the report still clears the minimum cross-jurisdiction footprint and likely still edges Gemini on breadth.

But it still does not become `BB`, because the section does not do meaningful cross-jurisdiction comparison. There is no explicit U.S. vs EMA contraindication/warning framing, no NICE-vs-label access interpretation, and no usable Health Canada synthesis. It names jurisdictions; it does not yet synthesize them.

### 4. Claim-frames — BO

Flat at `BO`. M-72 did not add claim-frame architecture, but run-14 does have mixed slot-level effects relative to run-12.

Positive: `SURPASS-5` is restored to a substantive primary-trial frame and `SURPASS-6` now has real population/comparator/baseline/endpoint/safety content (`run-14 report.md:23,27`) versus run-12's all-gap `SURPASS-5` and all-gap `SURPASS-6` (`run-12 report.md:23,27`).

Negative: `SURPASS-CVOT` is still gap-only (`run-14 report.md:31`), `SURPASS-1/3/4` remain skeletal (`run-14 report.md:7,15,19`), and the Thomas clamp subsection loses the population and glucagon-suppression detail that run-12 had (`run-14 report.md:41`; `run-12 report.md:41`). Net: better pivotal-trial coverage than run-12, but not enough to change the dimension.

### 5. Structure — BO

Flat at `BO`. The scaffold is effectively unchanged from run-12: efficacy slots, mechanism, five regulatory subheads, safety, comparative, population subgroups, trial summary, limitations, methods, contradictions, bibliography, and retrieval disclosure are all still present (`run-14 report.md:3-158`; `run-12 report.md:3-164`). So the 24-block contract structure is materially the same.

The remaining structural defect also persists: `Trial Summary` row references are still misbound from `SURPASS-3` onward (`run-14 report.md:85-88` vs bibliography `run-14 report.md:129-134`). Run-14 is cleaner than run-11 because it avoids the stale 2-row timeline/table problem, but versus run-12 the structural category is simply unchanged.

### 6. Contradictions — BB

Flat at `BB`. This remains the strongest dimension. Run-14 keeps the explicit contradiction count, explains detector over-grouping, enumerates tier-labeled numeric ranges, and preserves the strict-verify traceability statement (`run-14 report.md:107-124`).

The count moves from 13 to 14 disagreements (`run-12 report.md:107-122`; `run-14 report.md:107-122`), but that does not weaken the category. The contradiction layer is still clearer and more machine-auditable than the comparator narratives.

### 7. Narrative depth — LB

No lift. This is the decisive verdict on V33.

The targeted synthesis sections are materially thinner than run-12:

- `Safety` drops from 6 cited synthesis sentences to 3 (`run-12 report.md:71`; `run-14 report.md:71`)
- `Comparative` drops from 7 to 3 (`run-12 report.md:75`; `run-14 report.md:75`)
- `Population Subgroups` drops from 9 to 7 (`run-12 report.md:79`; `run-14 report.md:79`)

Regulatory also shortens inside an already weak category (`run-14 report.md:47-63` vs `run-12 report.md:47-63`). The body did not become more layered; it became more bounded. Run-14 replaces run-12's broader free-form synthesis with a smaller number of prescribed cross-trial inferences, especially in `Safety` and `Comparative`. That is why the report is shorter without being deeper.

Verdict: `LB` holds. M-72 did **not** break the persistent Narrative depth ceiling.

## Recommended action

`ACCEPT_CEILING`

The formal gate is still `ITERATE`, but after five architectural cycles the scoreboard has stopped moving: run-9, run-11, run-12, and now run-14 all sit at the same basic category shape of `1 BB | 4 BO | 2 LB`, and the one cycle aimed directly at Narrative depth made the target sections shorter. That is the signature of an architecture ceiling, not of a near-miss that warrants one more prompt-layer pass.

No candidate is a true `PHASE2_CHECKPOINT` under the stated gate. If you accept the ceiling and need a canonical surrogate to ship as `AUDIT_GRADE_PREVIEW`, use **run-14**. It is the least-bad releasable artifact among the offered options: `release_allowed=True`, `SURPASS-5` and `SURPASS-6` are both populated (`run-14 report.md:23,27`), and it avoids run-11's stale timeline/table defect and run-9's release-blocked gap/misbinding profile. The tradeoff is explicit: run-14 is the cleanest preview artifact, but **not** evidence that V33 solved Narrative depth.
