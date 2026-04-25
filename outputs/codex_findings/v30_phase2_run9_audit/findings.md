# Codex V30 Phase-2 run-9 audit

**7-dimension verdict**: BB=1/7 | BO=4/7 | LB=2/7 | TIE=0/7

## Ship classification

- Gate: `ITERATE`
- Net progress vs run-7: `BB+0, BO+1, LB-1`
- Regressions: no dimension-level regressions; slot-level regression remains in `SURPASS-5`, which had substantive primary-trial content in run-7 but falls back to a cited gap disclosure in run-9 (`outputs/full_scale_v30_phase2_run7/clinical/clinical_tirzepatide_t2dm/report.md:21-23`; `outputs/full_scale_v30_phase2_run9/clinical/clinical_tirzepatide_t2dm/report.md:21-23`)

## Doctrine call

Run-9 gets the higher score. `release_allowed=False` on a report that renders all contract slots with explicit, cited gap disclosure is doctrinally better than `release_allowed=True` on a report that silently loses manifest-passed sections. Under the run-7 doctrine, silent omission is a structural fault; disclosed absence is acceptable transparency (`outputs/codex_findings/v30_phase2_run7_audit/findings.md:75-85`). So for scoring, run-9 outranks run-7 on Structure and on overall trajectory even though Qwen's release gate moved the other way.

Qwen's `completeness=needs_revision` is fair on substantive completeness but unfair if used as a release rule that rewards silent drops. It is correct that SURPASS-5/6/CVOT primary content and most regulatory slots are still missing in substance (`outputs/full_scale_v30_phase2_run9/clinical/clinical_tirzepatide_t2dm/report.md:21-31,45-67`). It is not correct to treat run-7's hidden omissions as better than run-9's disclosed omissions.

For ship/checkpoint framing, `release_allowed` should be advisory, not a hard gate. The primary gate should remain the 7-dimension audit, otherwise the system is incentivized to hide unverifiable slots instead of rendering them honestly. On that standard, run-9 is ahead of run-7, but it is still not a release ship because Regulatory and Narrative depth remain LB and citation integrity still has unresolved defects.

## 7-dimension analysis

### 1. Citations — BO

Run-9 now puts citation markers on every rendered slot and keeps most core bibliography entries at T1, with real trial-level uncertainty in SURPASS-2 and SURMOUNT-2 (`outputs/full_scale_v30_phase2_run9/clinical/clinical_tirzepatide_t2dm/report.md:9-11,33-35,134-149`). But three pivotal slots are still gap-only (`report.md:21-31`), the SURPASS-6 marker is misbound to an unrelated glioblastoma PDF (`report.md:27,141`), and SURPASS-CVOT still cites a placeholder entry rather than a publication (`report.md:31,142`). The downstream Safety and Comparative prose also leans on T4/T7 material for key claims (`report.md:69-79,150-163`). That means Qwen's citation criticism is partly fair.

ChatGPT still leads because it explicitly prioritizes core SURPASS trials plus FDA/EMA sources and gives dense ETD/CI/P trial framing across the pivotal program (`state/compare_chatgpt_dr.txt:50-53,161-218,309-357`). Gemini still trails on source hierarchy because its citation stack visibly includes secondary and promotional material such as Pharmacy Times and Lilly press/PR items (`state/compare_gemini_dr.txt:680-689,700-704`). Run-9 therefore still beats Gemini, but only narrowly and less cleanly than run-7.

### 2. Regulatory — LB

All six regulatory slots now render in-body, which is a structural repair, but substantive regulatory content is still thin. FDA Mounjaro, EMA, and Health Canada are pure cited gap disclosures; FDA Zepbound and NICE TA924 are one-field stubs; only NICE TA1026 contains genuinely usable content (`report.md:45-67`). On the user's stated criterion, this is not yet substantive FDA + EMA + NICE + HC coverage.

ChatGPT gives a real U.S./EMA dosing and warning comparison (`state/compare_chatgpt_dr.txt:966-982`). Gemini gives substantive FDA and Health Canada safety and update narrative (`state/compare_gemini_dr.txt:530-625`). Run-9 is now transparent about what is missing, but on regulatory substance it still loses to both comparators.

### 3. Jurisdiction — BO

Run-9 now explicitly marks all requested jurisdictions in the body: U.S., EU, U.K., and Canada (`report.md:45-67`). That breadth is better than Gemini's North-America-heavy regulatory focus, which concentrates on FDA and Health Canada and does not provide equivalent NICE/EMA handling (`state/compare_gemini_dr.txt:29-32,530-625`).

ChatGPT still beats run-9 on jurisdictional usability because it materially contrasts U.S. and EMA labeling rather than merely naming the authorities (`state/compare_chatgpt_dr.txt:966-982`). So this stays BO, but it is a stronger BO than run-7 because Canada is now at least explicitly disclosed instead of absent.

### 4. Claim-frames — BO

Run-9 has real PICO/uncertainty framing where extraction survives: SURPASS-2 carries comparator plus ETD/CI/P, and SURMOUNT-2 now has N, population, baseline HbA1c/weight, endpoint, dose-stratified effect estimates, and safety signal (`report.md:9-11,33-35`). Missing pivotal trials are now at least disclosed as gaps rather than silently dropped (`report.md:21-31`), which is a claim-frame improvement over run-7 on honesty.

But the frame quality is still uneven. SURPASS-4 remains skeletal (`report.md:17-19`), SURPASS-5 regresses from substantive primary content in run-7 to a gap-only disclosure in run-9 (`outputs/full_scale_v30_phase2_run7/clinical/clinical_tirzepatide_t2dm/report.md:21-23`; `report.md:21-23`), and the Comparative section still makes broad numeric claims without integrating the contradiction/limitations disclosures into the main text (`report.md:73-79,95-97,111-131`). ChatGPT remains the best dose-stratified PICO implementation (`state/compare_chatgpt_dr.txt:161-218,309-357`); Gemini remains more assertive and less uncertainty-disciplined (`state/compare_gemini_dr.txt:117-127`). That keeps run-9 at BO, not BB.

### 5. Structure — BO

This is the major lift. Run-9 renders all 15 contract slots with headings and citation markers, including the four run-7 silent losses: SURPASS-6, FDA Mounjaro, EMA, and Health Canada (`report.md:25-27,45-47,53-55,65-67`). That directly resolves the structural defect identified in the run-7 audit, where silent loss of manifest-passed subsections was the decisive LB driver (`outputs/codex_findings/v30_phase2_run7_audit/findings.md:75-85`). Relative to run-7's 11 rendered slots, this is a BO lift, not BB: it now beats Gemini on auditable slot preservation, but it does not beat ChatGPT's cleaner architecture.

It is not BB because table integrity is still poor. The Trial Summary and Timeline remain only two rows and materially contradict the body: SURPASS-5 is shown as `N=586`, baseline `7.0%`, comparator `placebo`, result `10.5%` despite the body saying baseline HbA1c `8.31%` and background insulin glargine; SURMOUNT-2 is shown as `N=1514`, comparator `people without diabetes`, endpoint `HbA1c`, result `-10%` despite the body saying `N=938` and a weight endpoint (`report.md:23,35,83-93`). The checklist also still says `7/7 topics covered` despite multiple gap-only subsections (`report.md:108-109`). ChatGPT still has the best overall information architecture and timeline (`state/compare_chatgpt_dr.txt:50-66,1096-1110`), while Gemini is coherent but not contract-auditable in the same way (`state/compare_gemini_dr.txt:73-80,321-359,653-679`).

### 6. Contradictions — BB

Run-9 still provides the clearest contradiction handling of the three drafts: an explicit contradiction section, tier labels, numeric ranges, and a raw-output pointer (`report.md:111-131`). That is exactly the kind of inconsistency disclosure the run-7 audit treated as a Beat-Both strength.

ChatGPT discusses uncertainty and evidence gaps, but it does not enumerate contradictions in this explicit, tier-labeled way (`state/compare_chatgpt_dr.txt:1065-1086`). Gemini does not surface contradiction handling in an equivalent form. This remains run-9's clearest BB dimension.

### 7. Narrative depth — LB

Run-9 is the deepest V30 artifact so far, and the Safety, Comparative, and Population Subgroups sections do real synthesis rather than pure slot dumping (`report.md:69-79`). But the efficacy and regulatory core is still dominated by terse slot outputs and gap disclosures (`report.md:5-67`), so the report remains locally rich and globally thin.

ChatGPT sustains broader clinical synthesis, including target-attainment framing, time-course interpretation, benefit-risk concretization, and timeline reasoning (`state/compare_chatgpt_dr.txt:592-630,1004-1045,1096-1110`). Gemini is still broader on mechanism, SURMOUNT-2, safety, and forward trajectory, even if parts are overstated (`state/compare_gemini_dr.txt:321-359,469-520,653-679`). Run-9 therefore still loses both on narrative depth.

## Reconciliation with run-7 + run-8 trajectory

Run-9 is ahead, not stuck. The run-7 to run-8 move fixed slot presence but left uncited gap disclosures (`outputs/full_scale_v30_phase2_run8/clinical/clinical_tirzepatide_t2dm/report.md:25-31,45-67`). The run-8 to run-9 move adds citation markers to those fallback disclosures (`outputs/full_scale_v30_phase2_run9/clinical/clinical_tirzepatide_t2dm/report.md:25-31,45-67`), which is the correct completion of the M-68 doctrine: every contract slot renders and every rendered slot is citation-bound.

Net dimension movement versus run-7 is one-way positive:

- `Structure`: LB -> BO
- `Citations`: stays BO, but with a narrower margin because of the `[7]` misbinding and the loss of substantive SURPASS-5 primary content
- `Regulatory`: stays LB
- `Jurisdiction`: stays BO, slightly stronger
- `Claim-frames`: stays BO
- `Contradictions`: stays BB
- `Narrative depth`: stays LB

So the BB count does not increase, but the report still makes real net progress: `BO+1`, `LB-1`, with no dimension-level regressions. The only meaningful regression is local, not dimensional: SURPASS-5's primary subsection fell back to a gap disclosure.

## Recommended action

`CHECKPOINT-and-escalate-M-69`

Rationale: checkpoint the M-68 architecture because the PRISMA-critical structural doctrine is now correct and all 15 slots render with citation markers. Do not ship the report yet. The next narrow fix list is:

- repair bibliography/citation binding for SURPASS-6 and SURPASS-CVOT (`report.md:27,31,141-142`)
- restore substantive primary-trial rendering for SURPASS-5 if verification permits, or downgrade downstream claims that still lean on secondary/T7 evidence (`report.md:21-23,69-79,150-163`)
- regenerate Trial Summary and Timeline from rendered body rows instead of stale leftovers (`report.md:81-93`)
- propagate contradiction-aware hedging into the Comparative and Safety narrative so Qwen's hedging objection is answered in the main text, not only in the limitations appendix (`report.md:69-79,95-97,111-131`)
