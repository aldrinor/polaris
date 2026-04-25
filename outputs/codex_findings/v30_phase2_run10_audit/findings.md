# Codex V30 Phase-2 run-10 audit

**7-dimension verdict**: BB=1/7 | BO=4/7 | LB=2/7 | TIE=0/7

## Ship classification

- Gate: `ITERATE`
- Net progress vs run-9: `BB+0, BO+0, LB+0`
- Regressions: no dimension-level regressions
- Slot-level regressions: `SURMOUNT-2` fell from a populated primary-trial frame in run-9 to all-gap in run-10 (`outputs/full_scale_v30_phase2_run9/clinical/clinical_tirzepatide_t2dm/report.md:33-35`; `outputs/full_scale_v30_phase2_run10/clinical/clinical_tirzepatide_t2dm/report.md:33-35`)
- Slot-level regressions: the Thomas clamp subsection lost the glucagon-suppression extraction (`outputs/full_scale_v30_phase2_run9/clinical/clinical_tirzepatide_t2dm/report.md:39-41`; `outputs/full_scale_v30_phase2_run10/clinical/clinical_tirzepatide_t2dm/report.md:39-41`)
- Table-level regression: the `Trial Summary` ref column is shifted and still not body-derived (`outputs/full_scale_v30_phase2_run10/clinical/clinical_tirzepatide_t2dm/report.md:83-88,131-136`)

## 7-dim analysis

### 1. Citations — BO

Delta vs run-9: stronger, but not enough to lift category. The decisive repair is real: `SURPASS-6` now binds to the correct Rosenstock JAMA/PMC record instead of the run-9 glioblastoma PDF (`run-10 report.md:25-27,135-137`; `run-9 report.md:25-27,140-142`). `SURPASS-1` regains population/design/sponsor framing and `SURPASS-2` preserves the full HbA1c ETD+CI+P frame while adding baseline HbA1c (`run-10 report.md:7,11`; `run-9 report.md:7,11`). But `SURPASS-5`, `SURPASS-6`, and `SURPASS-CVOT` still do not render substantive primary-trial estimates in-body, regulatory bibliography entries remain bare entity IDs, and the `Trial Summary` cites the wrong references for multiple rows (`run-10 report.md:23-31,45-67,83-88,139-144`). ChatGPT still wins on primary-source density and trial-level coverage across the pivotal program (`state/compare_chatgpt_dr.txt:50-53,161-218,309-520,966-982`). Run-10 still beats Gemini on source hierarchy because Gemini's core claim stack visibly includes PR, investor, trade, and news items (`state/compare_gemini_dr.txt:687-704,730-756,810-856`).

### 2. Regulatory — LB

Delta vs run-9: structural improvement only. All six regulatory subsections now render multi-field scaffolding instead of the run-9 mix of `contract-bound content did not survive` disclosures and one-line stubs (`run-10 report.md:45-67`; `run-9 report.md:45-67`). Substantively, though, only `NICE TA1026` carries usable text; FDA Mounjaro, FDA Zepbound, EMA, NICE TA924, and Health Canada are still all-`not extractable` stubs (`run-10 report.md:47,51,55,59,63,67`). That is still well behind ChatGPT's actual U.S./EMA dosing-warning comparison (`state/compare_chatgpt_dr.txt:966-982`) and Gemini's FDA/Health Canada warning-update narrative (`state/compare_gemini_dr.txt:530-625`). Net: still LB, not BO.

### 3. Jurisdiction — BO

Delta vs run-9: no categorical change, slightly cleaner rendering. Run-10 still explicitly covers the four requested jurisdictions in-body: U.S., EU, U.K., and Canada (`run-10 report.md:45-67`). The scaffolding is cleaner than run-9, but the substance is not materially broader. ChatGPT remains more clinically usable because it actually contrasts U.S. and EMA label language (`state/compare_chatgpt_dr.txt:36-48,966-982`). Run-10 still beats Gemini on breadth because Gemini remains concentrated on FDA plus Health Canada, without equivalent NICE/EMA handling (`state/compare_gemini_dr.txt:28-32,530-625`).

### 4. Claim-frames — BO

Delta vs run-9: mixed. Positive: `SURPASS-1` regains a real PICO shell, `SURPASS-2` keeps the strongest ETD/CI/P frame in the report, and `SURPASS-5/6` are at least rendered as field-labelled gaps rather than single-sentence contract failures (`run-10 report.md:7,11,23-27`). Negative: `SURMOUNT-2` regresses from a populated primary-trial frame in run-9 to universal `not extractable`, and the Thomas clamp subsection loses the glucagon-suppression field (`run-9 report.md:35,41`; `run-10 report.md:35,41`). ChatGPT still clearly leads on full-trial PICO completeness across `SURPASS-2/4/5/6` (`state/compare_chatgpt_dr.txt:161-218,309-520`). Run-10 still edges Gemini because its surviving claims are tighter and more uncertainty-disciplined even when incomplete (`state/compare_gemini_dr.txt:86-210,322-359`), but the margin is thinner than the optimistic run-10 framing suggests.

### 5. Structure — BO

Delta vs run-9: better, but still not BB. The core structural repair persists: all 15 contract slots render in-body, and the `SURPASS-6` bibliography binding is corrected (`run-10 report.md:25-27,129-144`; `outputs/full_scale_v30_phase2_run10/clinical/clinical_tirzepatide_t2dm/manifest.json:821-828`). Run-10 also removes the stale 2-row timeline from run-9 and expands the `Trial Summary` to four rows (`run-10 report.md:81-88`; `run-9 report.md:81-93`). But the table is still not body-derived: `SURPASS-3` cites `[2]` although the body uses `[3]`, `SURPASS-4` cites `[3]` although the body uses `[4]`, and `SURMOUNT-2` cites `[4]` although its body subsection is all-gap and its correct bibliography entry is `[5]` (`run-10 report.md:15,19,35,85-88,131-135`). The checklist also still says `7/7 topics covered` despite large efficacy and regulatory gaps (`run-10 report.md:103-104`). ChatGPT remains the structural leader on evidence architecture and chronology (`state/compare_chatgpt_dr.txt:50-66,1096-1110`), but run-10 still beats Gemini on auditable slot preservation.

### 6. Contradictions — BB

Delta vs run-9: none at the category level. Run-10 keeps the explicit 16-item contradiction disclosure, explains why the detector over-flags mixed endpoints/populations/doses, and states that body claims remain strict-verify bound to evidence IDs (`run-10 report.md:106-126`). The unresolved weakness is unchanged: this hedging still sits mostly in the appendix rather than being propagated into the main Safety and Comparative prose (`run-10 report.md:69-79,90-92,106-126`). Even so, neither comparator offers an equivalent contradiction audit or disclosure layer (`state/compare_chatgpt_dr.txt:952-959`; `state/compare_gemini_dr.txt:664-679`). BB holds.

### 7. Narrative depth — LB

Delta vs run-9: materially richer locally, but still globally thin. Safety now carries meta-analytic sample size, FAERS disproportionality metrics, and clearer class-comparison language; Comparative adds SURPASS-2 time-to-target, SURPASS-5 insulin-background weight data, and more quantitative indirect evidence; Population Subgroups is denser and broader (`run-10 report.md:71,75,79`; `run-9 report.md:71,75,79`). But the report still collapses wherever the efficacy and regulatory spine is gap-bound (`run-10 report.md:5-67`). ChatGPT still delivers sustained whole-report synthesis across efficacy, safety, regulation, and time-course (`state/compare_chatgpt_dr.txt:592-630,907-982,1096-1112`). Gemini is still broader on `SURPASS-5/6`, `SURMOUNT-2`, `SURPASS-CVOT`, and regulatory updates, even though parts are overclaimed (`state/compare_gemini_dr.txt:191-210,322-359,408-625`). Run-10 therefore remains LB on depth.

## Reconciliation with run-9 trajectory

Run-10 is ahead of run-9 as an artifact even though the categorical scoreboard does not move. The real gains are specific: `SURPASS-6` citation repair (`run-10 report.md:136` vs `run-9 report.md:141`), `SURPASS-1` frame recovery (`run-10 report.md:7` vs `run-9 report.md:7`), fuller regulatory rendering (`run-10 report.md:45-67` vs `run-9 report.md:45-67`), richer Safety/Comparative/Subgroups prose (`run-10 report.md:71-79` vs `run-9 report.md:71-79`), and restored evaluator release (`outputs/full_scale_v30_phase2_run10/clinical/clinical_tirzepatide_t2dm/manifest.json:34-40,847-853`; `outputs/full_scale_v30_phase2_run9/clinical/clinical_tirzepatide_t2dm/manifest.json:34-46,854-860`).

What still blocks a categorical lift is concentrated and specific:

- regulatory substance is still mostly stubbed, so Regulatory cannot leave LB
- the efficacy core still has unresolved primary-trial failures in `SURPASS-5/6`, `SURPASS-CVOT`, and now regressed `SURMOUNT-2`, so Citations and Claim-frames do not catch ChatGPT
- the `Trial Summary` still presents a cleaner report than the body actually supports, so Structure remains below BB
- contradiction-aware hedging still is not propagated into the main narrative, so Narrative depth stays below both competitors

Under the written 7-dimension gate, this is still `ITERATE`, the same top-level classification run-9 received in the prior Codex audit (`outputs/codex_findings/v30_phase2_run9_audit/findings.md:3-8`). `release_allowed=True` is a real improvement, but it reflects recovery from the run-9 citation-binding blocker more than a full resolution of the two persistent LB dimensions.

## Recommended action

`ITERATE-narrow-fix-list`

- repair `SURMOUNT-2` slot extraction/regeneration first; it is the clearest run-10 regression and the fastest route to a real Claim-frames/Narrative lift (`run-10 report.md:33-35`; `run-9 report.md:33-35`)
- fix regulatory sentence synthesis at the subsection surface so FDA/EMA/NICE/HC emit at least one verified substantive sentence instead of multi-field `not extractable` scaffolds (`run-10 report.md:45-67`)
- regenerate `Trial Summary` strictly from rendered body slots and enforce bibliography-alignment checks (`run-10 report.md:83-88,131-136`)
- propagate contradiction-aware hedging into Safety and Comparative body text, not only the disclosure appendix (`run-10 report.md:69-79,106-126`)
