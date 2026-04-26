# Codex V30 Phase-2 run-14 substance-density re-audit

**7-dimension verdict (substance-density framing)**: BB=2/7 | BO=4/7 | LB=1/7

## Methodology change

The prior `Narrative depth` call leaned too hard on raw competitor word count. That was a methodology error once the competitor outputs diverged this sharply in substance quality.

Inference from PRISMA/GRADE-style reporting norms, not a literal checklist item: depth should be weighted first by effect-estimate density, uncertainty reporting, claim traceability, and confidence calibration, then secondarily by length. Under that standard, Gemini's 6,835 words do not outrank run-14 just because they are longer. Length still matters as a breadth cue, which is why run-14 still loses depth to ChatGPT, but it should not dominate when one comparator is mostly filler.

Line refs below use `run-14 report.md` as shorthand for `outputs/full_scale_v30_phase2_run14/clinical/clinical_tirzepatide_t2dm/report.md`.

## Per-dimension re-scores

### 1. Citations (prior: BO; re-scored: BB)

Run-14 is the only artifact with systematic inline `[N]` citation markers across the body plus an explicit strict-verify traceability statement: 112 inline markers in the report, versus 0 in the ChatGPT comparator artifact and 0 in the Gemini comparator artifact. The report also keeps a T1-anchored bibliography and tells the reader that body claims are individually bound to cited evidence IDs (`run-14 report.md:7-79,107-124,127-153`).

This is not perfect. The `Trial Summary` refs are still misbound from `SURPASS-3` onward, and `Limitations` / `Methods` still contain uncited telemetry prose (`run-14 report.md:85-88,92,95-104`). But relative scoring matters here. ChatGPT is dense but uncited inline. Gemini is uncited inline and its works cited visibly include weaker media / PR sources such as Pharmacy Times, Lilly press releases, PR Newswire, and CBC (`state/compare_gemini_dr.txt:680-704,852-854`). Under audit-grade traceability, run-14 beats both.

### 2. Regulatory (prior: LB; re-scored: LB)

This remains the blocker. Run-14 names five regulatory buckets, but four are still stub-level or gap-level: EMA is one obesity-use sentence, `TA924` is just a contact email, `TA1026` is only a funding sentence, and Health Canada remains an explicit gap (`run-14 report.md:55,59,63,67`).

ChatGPT materially outperforms it here by doing actual U.S. vs EMA warning/contraindication comparison and practical prescribing synthesis (`state/compare_chatgpt_dr.txt:966-982`). Gemini overclaims, but it still supplies a fuller FDA / Health Canada warning narrative and 2025-2026 update coverage than run-14 does (`state/compare_gemini_dr.txt:530-645`). Substance density does not rescue missing regulatory synthesis. `LB` stays.

### 3. Jurisdiction (prior: BO; re-scored: BO)

Run-14 still explicitly covers the U.S., EU, U.K., and Canada in-body (`run-14 report.md:45-67`). That breadth still beats Gemini's effectively FDA / Health Canada-centric jurisdictional treatment, even when Gemini goes much longer (`state/compare_gemini_dr.txt:530-645`).

It still loses to ChatGPT because ChatGPT does usable cross-jurisdiction comparison rather than just naming authorities; it explains that U.S. and EMA labeling are not interchangeable (`state/compare_chatgpt_dr.txt:974-982`). So `BO` still fits.

### 4. Claim-frames (prior: BO; re-scored: BO)

Run-14 remains more disciplined than Gemini because it preserves slot-bound claim framing and explicit gap language instead of smoothing over missing evidence. `SURPASS-5` and `SURPASS-6` are populated with identity, baseline, endpoint, and safety content, while `SURPASS-CVOT` is honestly left as a verified gap (`run-14 report.md:21-31`).

That still beats Gemini's broader but more inflated framing around `SURPASS-5/6`, `SURMOUNT-2`, and `SURPASS-CVOT` (`state/compare_gemini_dr.txt:191-213,329-352,419-457`). It still loses to ChatGPT on completeness and granularity of pivotal-trial framing, especially for `SURPASS-6` and CVOT (`state/compare_chatgpt_dr.txt:455-540`). `BO` holds.

### 5. Structure (prior: BO; re-scored: BO)

Run-14 keeps the more auditable scaffold: efficacy slots, mechanism, jurisdictional regulation, safety, comparative, subgroups, summary table, limitations, methods, contradictions, bibliography, and retrieval disclosure (`run-14 report.md:3-167`). That still beats Gemini's long essay structure for audit use because run-14 exposes methods and contradiction handling explicitly (`run-14 report.md:95-124`; `state/compare_gemini_dr.txt:664-679`).

It still does not beat ChatGPT. ChatGPT has the stronger continuous evidence arc and an explicit milestone timeline (`state/compare_chatgpt_dr.txt:1096-1111`), while run-14 still carries the trial-summary ref misbinding defect (`run-14 report.md:85-88`). `BO` remains the right score.

### 6. Contradictions (prior: BB; re-scored: BB)

This remains the cleanest `BB`. Run-14 discloses 14 numeric contradiction clusters, explains detector over-grouping, preserves source-tier labels, and states that body claims are strict-verify traceable (`run-14 report.md:106-124`).

Neither comparator has an equivalent contradiction inventory. ChatGPT is careful about uncertainty, but it does not expose the disagreement surface in a machine-auditable appendix. Gemini does the opposite: it trends toward definitive language even around non-superiority cardiovascular results (`state/compare_chatgpt_dr.txt:952-959`; `state/compare_gemini_dr.txt:432-439,664-679`). Under GRADE/AMSTAR-style confidence discipline, this is a real quality win for run-14.

### 7. Narrative depth (prior: LB; re-scored: BO)

This is the core methodology correction. On pure word count, run-14 loses to both competitors. On substance density, it clearly beats Gemini and still loses to ChatGPT.

Against Gemini, the density gap is decisive: run-14 has 37.6 numeric facts per 1K words versus Gemini's 19.3, includes 3 reported confidence intervals versus 0, includes 1 HR/RR/OR versus 0, has 112 inline citations versus 0, and uses 1 promotional adjective versus Gemini's 58. Gemini's length advantage is therefore mostly narrative inflation, not deeper audit substance. The text itself supports that reading: phrases such as "decisively established," "definitive head-to-head," "massive," "astonishing," and "definitively confirmed" recur throughout the comparator (`state/compare_gemini_dr.txt:199-205,338-348,419-457,664-679`).

Against ChatGPT, run-14 still loses. ChatGPT carries the top-end density profile: 59.0 numeric facts per 1K words, 12 confidence intervals, 11 p-values, 5 HR/RR/OR mentions, and stronger sustained cross-trial quantitative synthesis (`state/compare_chatgpt_dr.txt:952-959`; audit-brief density table). So the right correction is `LB -> BO`, not `LB -> BB`.

## Hedging cross-cut

Hedging should change the comparative read, but not by becoming an eighth scored dimension in this file.

Gemini's confidence language is a quality defect, not a depth strength. It repeatedly converts non-superiority or indirect evidence into definitive-seeming claims (`state/compare_gemini_dr.txt:432-439,457,664-679`). Run-14 is better calibrated because it exposes contradiction clusters and avoids promotional tone (`run-14 report.md:106-124`; `outputs/full_scale_v30_phase2_run14/clinical/clinical_tirzepatide_t2dm/qwen_judge_output.json:24-26`).

But run-14 does not earn a separate hedging lift against both competitors. Qwen still flags `hedging_appropriateness` as `needs_revision` in run-14 (`outputs/full_scale_v30_phase2_run14/clinical/clinical_tirzepatide_t2dm/qwen_judge_output.json:20-22`). So hedging is best treated as a modifier that invalidates Gemini's apparent "depth" rather than as an independent V30 win.

## Ship classification

- Gate: `PHASE2_CHECKPOINT`
- Difference vs prior word-count framing: `BB+1, BO+0, LB-1`
- Dimension changes: `Citations BO->BB`; `Narrative depth LB->BO`

Run-14 does **not** reach `BEAT_BOTH_SHIP` because Regulatory remains `LB`, so the zero-`LB` requirement is still missed. It **does** reach `PHASE2_CHECKPOINT` because 6/7 dimensions are now at least `BO` and only 1 dimension remains `LB`.

## Verdict on prior ACCEPT_CEILING

`ACCEPT_CEILING` does not survive unchanged. The prior verdict was too pessimistic because it used a flawed primary proxy for `Narrative depth`: raw word count rewarded Gemini's filler and obscured run-14's higher effect-estimate density, uncertainty discipline, and traceability.

The stronger corrected diagnosis is narrower: run-14 did **not** hit a universal narrative ceiling against both competitors; it beat Gemini on substance-density depth and citation discipline. What remains is a **regulatory ceiling** and a **ChatGPT-density ceiling**, not an across-the-board depth ceiling. So the earlier `ITERATE` / `ACCEPT_CEILING` call was a methodology error in the `Narrative depth` dimension, even though the final output still falls short of `BEAT_BOTH_SHIP`.

## Recommended action

Ship run-14 as `PHASE2_CHECKPOINT`, not as `BEAT_BOTH_SHIP`.

Do not keep using raw word count as the primary `Narrative depth` gate. For the next ship attempt, the shortest path to `BEAT_BOTH_SHIP` is concentrated Regulatory repair: replace the EMA / NICE / Health Canada stubs with actual cross-jurisdiction synthesis while preserving the current citation and contradiction discipline.
