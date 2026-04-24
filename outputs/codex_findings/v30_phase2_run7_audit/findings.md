# Codex V30 Phase-2 run-7 audit vs ChatGPT DR + Gemini DR

**7-dimension verdict**: BB=1/7 | BO=3/7 | LB=3/7 | TIE=0/7

## Ship classification

- Gate: `ITERATE`
- Regressions vs run-2: none. The key failures are persistent, not new: SURPASS-6 is still absent from the body, the regulatory drop-on-verify bug remains, and the Trial Summary/Timeline are still materially underfilled (`outputs/codex_findings/v30_phase2_run2_audit/findings.md:10,45-50,72-75`; `report.md:21-27,35-47,61-73`; `manifest.json:435-437,639-818`).

## Primary-trial + regulatory spot-check

- SURPASS-2: rendered with correct trial binding and HbA1c ETD+CI+P; weight ETDs are still absent from the trial subsection (`report.md:9-11`).
- SURPASS-4: rendered, but only population/comparator/sponsor survive into the body (`report.md:17-19`).
- SURPASS-5: rendered with baseline HbA1c, endpoint, and GI safety signal, but not HbA1c ETD+CI+P (`report.md:21-23`).
- SURPASS-6: manifest `pass`, body absent; the report jumps from SURPASS-5 to SURMOUNT-2 (`manifest.json:435-437`; `report.md:21-27`).
- SURMOUNT-2: rendered, but all 10 requested slots are still `not extractable` despite `open_access` retrieval and `pass` status in the manifest (`report.md:25-27`; `manifest.json:494-547`).
- Thomas clamp: rendered with 7 populated fields and no longer all-gap; this is a real M-66c recovery (`report.md:31-33`; `manifest.json:558-605`).
- FDA Mounjaro: manifest `pass`, body absent (`manifest.json:639-641`; no corresponding subsection in `report.md:35-47`).
- FDA Zepbound: rendered as heading plus one gap statement only (`report.md:37-39`; `manifest.json:675-677`).
- EMA EPAR: manifest `pass`, body absent (`manifest.json:711-713`; no corresponding subsection in `report.md:35-47`).
- NICE TA924: rendered as heading plus one gap statement only (`report.md:41-43`; `manifest.json:747-749`).
- NICE TA1026: rendered with 2 extracted fields; this is the first substantive NICE recovery in-body (`report.md:45-47`; `manifest.json:781-783`).
- Health Canada monograph: manifest `pass`, body absent (`manifest.json:815-818`; no corresponding subsection in `report.md:35-47`).

## 7-dimension analysis

### 1. Citations

V30 says: SURPASS-2 now carries the correct semaglutide comparator plus HbA1c ETD+CI+P, and the bibliography is mostly T1 for the core rendered trials (`report.md:9-11,116-126`). But SURPASS-6 is still absent from both body and bibliography, and SURPASS-4/5 are under-cited at the claim level (`report.md:17-23`).

ChatGPT says: it explicitly prioritizes core SURPASS publications plus FDA and EMA primary regulatory sources, then renders detailed trial-level estimates for SURPASS-2/4/5/6 with dose-specific effects and uncertainty (`compare_chatgpt_dr.txt:51-53,161-218,309-520`).

Gemini says: it narrates SURPASS-2/4/5/6 in depth, but its evidence stack leans heavily on PR Newswire, Lilly investor releases, and other secondary sources for several pivotal claims (`compare_gemini_dr.txt:117-130,205-212,700-708,730-758`).

Critical appraisal: AMSTAR-2 and GRADE favor direct primary-trial sourcing with precise effect estimates. Run-7 has fixed the worst binding errors and is now more trustworthy than Gemini on source hierarchy, but it still trails ChatGPT on completeness because missing SURPASS-6 and thin SURPASS-4/5 rendering leave major citation gaps.

Winner: **ChatGPT** → BO

### 2. Regulatory

V30 says: the body renders only FDA Zepbound, NICE TA924, and NICE TA1026, and only TA1026 is substantive; FDA Mounjaro, EMA EPAR, and Health Canada are still absent despite manifest `pass` states (`report.md:35-47`; `manifest.json:639-818`).

ChatGPT says: it substantively compares U.S. prescribing information with EMA product information and explains why local labeling should not be treated as interchangeable (`compare_chatgpt_dr.txt:968-981`).

Gemini says: it substantively covers FDA boxed warnings and Health Canada serious warnings, then adds 2025-2026 regulatory safety updates and monograph changes (`compare_gemini_dr.txt:530-549,578-603,609-625`).

Critical appraisal: PRISMA completeness for this dimension requires FDA, EMA, NICE, and Health Canada to appear in the body with real content. TA1026 is a genuine recovery, but one substantive subsection cannot offset three silently dropped regulatory slots plus two heading-only stubs. Both comparators are incomplete, yet each delivers more substantive regulatory analysis than V30.

Winner: **TIE** → LB

### 3. Jurisdiction

V30 says: the report body now reaches the U.S. via FDA Zepbound, the U.K. via NICE TA924/TA1026, and the EU via EudraVigilance safety synthesis (`report.md:37-47,51`). Canada is still absent.

ChatGPT says: it gives the most clinically usable jurisdictional comparison between the U.S. label and EMA SmPC, and explicitly warns that U.S. and EU texts should not be treated as interchangeable (`compare_chatgpt_dr.txt:36-37,968-981`).

Gemini says: it is strongest on North America, especially FDA plus Health Canada warnings and updates, but it does not provide equivalent EU or U.K. coverage (`compare_gemini_dr.txt:31-32,530-549,578-603`).

Critical appraisal: GRADE indirectness and PRISMA applicability both favor covering the target care settings, not just one regulator. Run-7 is the only draft with explicit in-body U.K. coverage and therefore no longer clearly loses on breadth; however, ChatGPT still beats it on jurisdictional usability because V30's U.S./EU signals are thinner and Canada is missing. That leaves V30 ahead of Gemini on breadth, but behind ChatGPT on substance.

Winner: **V30** → BO

### 4. Claim-frames

V30 says: SURPASS-2 now has a strong PICO frame with comparator, endpoint, ETD, CI, P value, design, and sponsor; Thomas clamp is materially repaired; but SURPASS-4 is skeletal, SURPASS-6 is absent, and SURMOUNT-2 is rendered as universal `not extractable` despite open-access retrieval (`report.md:9-11,17-19,25-33`; `manifest.json:494-605`).

ChatGPT says: SURPASS-2/4/5/6 are consistently framed with population, baseline, dose stratification, comparator, timepoint, effect estimate, uncertainty, and key safety signals (`compare_chatgpt_dr.txt:161-218,309-520`).

Gemini says: it has good dose stratification, but the prose is much more assertive and less uncertainty-disciplined, including phrases such as "decisively established" and "definitive" without the same CI/P-density (`compare_gemini_dr.txt:117-130,205-212`).

Critical appraisal: GRADE rewards precise, qualified, population-specific effect framing. The M-66c Thomas-clamp fix is real and lifts run-7 above Gemini's looser claim language, but it does not overcome the missing SURPASS-6 slot and the collapsed SURMOUNT-2 frame. ChatGPT remains the best PICO implementation.

Winner: **ChatGPT** → BO

### 5. Structure

V30 says: the report still jumps from SURPASS-5 directly to SURMOUNT-2, drops three regulatory subsections that the manifest marks `pass`, and ends with a 2-row Trial Summary plus 2-row Timeline whose cells are not reliable abstractions of the body (`report.md:21-27,35-47,61-73`; `manifest.json:435-437,639-818`). It also claims "Completeness checklist: 7/7 topics covered" despite those omissions (`report.md:88-89`).

ChatGPT says: it has a clear arc from evidence architecture to a detailed per-trial matrix, integrated efficacy/safety/regulatory interpretation, NNT/NNH table, evidence gaps, and timeline (`compare_chatgpt_dr.txt:50-66,161-520,966-1055,1096-1110`).

Gemini says: it is verbose, but it still preserves a recognizable sequence from mechanism to trial program to safety/regulation to final synthesis (`compare_gemini_dr.txt:33-70,110-213,321-359,469-679`).

Critical appraisal: PRISMA reporting quality depends on complete section rendering and auditably correct tables. A heading-with-gap statement is acceptable disclosure; silent loss of a manifest-passed subsection is not. Because run-7 still silently loses SURPASS-6, FDA Mounjaro, EMA, and Health Canada, this remains a structural loss against both comparators.

Winner: **ChatGPT** → LB

### 6. Contradictions

V30 says: it explicitly discloses 18 contradiction clusters, labels the source tiers, explains why the detector over-flags mixed endpoints/populations, and points the reader to raw outputs (`report.md:91-113`).

ChatGPT says: it discusses evidence gaps and trial-design caveats, but it does not enumerate contradictions or tie them to evidence tiers (`compare_chatgpt_dr.txt:60-66,1065-1086`).

Gemini says: it offers little explicit inconsistency handling and finishes with high-certainty synthesis language that outruns its own evidence base (`compare_gemini_dr.txt:539-541,653-679`).

Critical appraisal: PRISMA and GRADE both reward transparent handling of inconsistency. Run-7 is still the only draft that operationalizes contradiction disclosure with tier labels, even if the detector remains coarse. This remains V30's clearest Beat-Both dimension.

Winner: **V30** → BB

### 7. Narrative depth

V30 says: the best synthesis is concentrated in Safety, Comparative, and Population Subgroups, where it integrates GI tolerability, indirect comparisons, HFpEF subgroup results, and AP-Combo subgroup heterogeneity (`report.md:49-59`). But the core efficacy body remains terse and extraction-bound (`report.md:5-27`).

ChatGPT says: it extends beyond extraction into clinically usable synthesis on target attainment, time-course, weight trajectories, safety tradeoffs, NNT/NNH framing, evidence gaps, and ongoing trials (`compare_chatgpt_dr.txt:592-630,916-985,1004-1095`).

Gemini says: it is the longest draft and provides broad mechanistic, efficacy, safety, regulatory, and forward-looking narrative, even though parts are overstated (`compare_gemini_dr.txt:25-32,55-67,329-359,469-679`).

Critical appraisal: Narrative depth is not raw word count alone, but depth still requires sustained synthesis across the whole report. Run-7 shows real progress beyond slot filling, yet it remains materially thinner than both comparators because the efficacy core and regulatory body never fully develop.

Winner: **ChatGPT** → LB

## Reconciliation with Claude's verdict

Agreement with Claude:

- **Citations = BO**: agreed. SURPASS-2 is fixed, but SURPASS-6 absence and thin SURPASS-4/5 rendering still keep V30 behind ChatGPT (`report.md:9-11,17-23`; `compare_chatgpt_dr.txt:161-218,309-520`).
- **Regulatory = LB**: agreed. NICE TA1026 is real recovery, but it is not enough to offset missing FDA Mounjaro, EMA, and Health Canada plus two heading-only stubs (`report.md:35-47`; `manifest.json:639-818`).
- **Claim-frames = BO, not BB**: agreed. Thomas clamp helps, but GRADE precision still collapses where SURPASS-6 is missing and SURMOUNT-2 is all-gap (`report.md:25-33`; `manifest.json:494-605`).
- **Structure = LB**: agreed. SURPASS-6 belongs in Structure scoring because the user-facing report drops a manifest-passed efficacy subsection. But this is **not** a regression vs run-2; it is a persistent unfixed defect (`outputs/codex_findings/v30_phase2_run2_audit/findings.md:10,45-50`; `report.md:21-27`; `manifest.json:435-437`).
- **Contradictions = BB** and **Narrative depth = LB**: agreed (`report.md:91-113`; `compare_chatgpt_dr.txt:1004-1095`; `compare_gemini_dr.txt:653-679`).

Disagreement with Claude:

- **Jurisdiction = BO, not LB**. Claude scored V30 as losing both. I do not think that holds after run-7. The body now explicitly covers the U.S., the U.K., and an EU pharmacovigilance signal (`report.md:37-47,51`). ChatGPT still beats V30 on jurisdictional usability because its U.S./EMA comparison is more clinically actionable (`compare_chatgpt_dr.txt:968-981`), but Gemini remains narrower because it is concentrated on FDA + Health Canada without equivalent EU/U.K. coverage (`compare_gemini_dr.txt:530-549,578-603`). That is enough to lift V30 from LB to BO on this dimension.

Tie-breakers on the expected disagreement points:

- SURPASS-6 drop: counts as a **Structure LB driver**, but not as a run-7 regression versus run-2.
- NICE TA1026: counts as **real regulatory recovery**, but not enough to lift Regulatory out of LB.
- Thomas clamp fix: counts as **real claim-frame recovery**, but not enough for BB while SURPASS-6 and SURMOUNT-2 remain defective.
- FDA Zepbound heading with zero content: still a structure defect, but **less severe than silent omission** because it at least discloses the gap. The worse bug is silent loss of manifest-passed subsections.

Claude's final gate call also needs adjustment: under the user's stated rule, `PHASE2_CHECKPOINT` requires `>=4/7 >=BO` **and** `<=1 LB`. Even with my more favorable jurisdiction scoring, run-7 still has 3 LBs, so it cannot be checkpointed on this gate.

## Summary + Next

- Tally: BB=1 BO=3 LB=3
- Recommended action: `ITERATE`
- Why not ship/checkpoint: run-7 is materially better than run-2 and has no new regressions, but PRISMA completeness still fails in the rendered body because Regulatory and Structure remain broken, and GRADE/AMSTAR-2 precision is still incomplete for several pivotal trial frames.
- Fix plan if ITERATE:
- 1. Fix the M-63 / `run_contract_section` drop-on-verify path so manifest-passed slots always render at least a heading plus explicit gap text, starting with `efficacy_surpass_6`, `regulatory_fda_t2d`, `regulatory_ema`, and `regulatory_hc` (`manifest.json:435-437,639-818,870`).
- 2. Regenerate the Trial Summary and Timeline from rendered slot outputs, not partial sentence leftovers; fail the section if fewer than 6 efficacy rows survive or if cells contradict the body (`report.md:61-73`).
- 3. Repair extraction/rendering for SURMOUNT-2 and missing dose/weight ETDs so the efficacy core carries the same effect-size discipline already restored for SURPASS-2 (`report.md:11,25-27,55`; `manifest.json:494-547`).
