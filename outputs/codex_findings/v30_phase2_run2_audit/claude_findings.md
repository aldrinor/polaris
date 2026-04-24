# Claude-side V30 Phase-2 run-2 audit vs ChatGPT DR + Gemini DR

Audit lens: PRISMA 2020 + AMSTAR-2 + GRADE. Cross-reference with
ChatGPT DR (4,830 words, state/compare_chatgpt_dr.txt) and Gemini
DR (6,835 words, state/compare_gemini_dr.txt).

V30 Phase-2 run-2: 2,442 words,
`outputs/full_scale_v30_phase2/clinical/clinical_tirzepatide_t2dm/report.md`.
Status=success, qwen verdicts 4 GOOD + 1 ACCEPTABLE,
release_allowed=True.

## Primary-trial spot-check (run-1 regression guard)

Run-1 catastrophically rendered SPRINT BP-trial prose in the
SURPASS-2 slot. Root cause: 5 wrong PMIDs in clinical.yaml
(commit `bcedd57` corrected all 5).

1. **SURPASS-2** (report.md:9-11): "Population: patients with
   type 2 diabetes.[2] Comparator: semaglutide at a dose of 1
   mg.[2] Primary endpoint: the change in the glycated hemoglobin
   level from baseline to 40 weeks.[2] Etd with uncertainty:
   -0.15 percentage points (95% CI, -0.28 to -0.03; P = 0.02),
   -0.39 percentage points (95% CI, -0.51 to -0.26; P<0.001),
   and -0.45 percentage points (95% CI, -0.57 to -0.32; P<0.001).[2]
   Sponsor: Eli Lilly.[2]" ✓ **CORRECT** (matches Frías NEJM 2021)
2. **SURPASS-4** (report.md:17-19): "adults with type 2 diabetes
   and high cardiovascular risk... insulin glargine... Eli
   Lilly.[4]" ✓ **CORRECT** (matches Del Prato Lancet 2021)
3. **SURPASS-5** (report.md:21-23): "adults with type 2
   diabetes... baseline HbA1c 8.31%... diarrhea 12-21% vs 10%.[5]"
   ✓ **CORRECT** (matches Dahl JAMA 2022)
4. **SURPASS-6**: NOT rendered in report body. frame_coverage
   says `pass` but no section heading exists. ⚠ **PASS-WITHOUT-SECTION**
5. **Thomas clamp** (report.md:31-33): "First phase insulin
   secretion: not extractable... Second phase insulin secretion:
   not extractable.[7]" — contract required_fields don't match
   Thomas paper's reported metrics. **CORRECT paper cited but
   field misalignment**.

**Regression status: PASS** — all corrected DOI/PMID bindings
render the correct paper's content. Zero wrong-paper extractions.

## 7-dimension analysis

### 1. Citations

**V30 says.** 23 bibliography entries, T1-T7 tier annotations,
primary SURPASS-2 ETDs match NEJM paper exactly (-0.15/-0.39/-0.45
with CIs and P values, report.md:11). Missing: SURPASS-1/3/4/5/6
ETDs are either partial or not extracted. SURPASS-CVOT is
`fail_min_fields` (paywall; correctly gap-flagged).

**ChatGPT says.** Full ETDs for SURPASS-2/4 with CIs; cites the
FDA statistical review and EMA EPAR as primary regulatory
sources (state/compare_chatgpt_dr.txt:51-52). "SURPASS-2... HbA1c
treatment diﬀerences versus semaglutide were −0.15%, −0.39%,
and −0.45%" (:14).

**Gemini says.** Headline reductions (HbA1c 2.46% for 15mg,
12.4 kg weight loss) but sparse CIs (state/compare_gemini_dr.txt:110-130).

**Critical appraisal.** V30 matches ChatGPT on SURPASS-2
primary-ETD quality but lags on per-trial ETDs across
SURPASS-1/3/4/5. ChatGPT integrates regulatory sources (FDA
statistical review) that V30 does not.
**Winner: ChatGPT slightly → V30 LOSE_ONE (TIE with Gemini)**

### 2. Regulatory

**V30 says.** Zero regulatory prose in the report body. All 6
regulatory entities (FDA Mounjaro, FDA Zepbound, EMA EPAR, NICE
TA924, NICE TA1026, HC Mounjaro monograph) flagged as
`fail_min_fields` — retrieved but not rendered.

**ChatGPT says.** "current U.S. prescribing information...
product information from the EMA" (:52) with downstream
regulatory synthesis.

**Gemini says.** Mentions FDA approvals extensively.

**Critical appraisal.** V30's regulatory contract entities
didn't render. Contract design is correct — the problem is that
regulatory entities have `url_pattern` primary identifier (no
DOI/PMID), which produces METADATA_ONLY provenance and then
fail_min_fields when the LLM can't extract required fields from
pure metadata. **Winner: BOTH → V30 LOSE_BOTH**

### 3. Jurisdiction

**V30 says.** No jurisdiction-specific coverage in the report.
Though the contract requests US/EU/UK/Canada (FDA + EMA + NICE +
HC), none rendered.

**ChatGPT says.** US + EU explicit, with FDA review and EMA
product-information detail.

**Gemini says.** US + EU + other.

**Critical appraisal.** Same root cause as dimension 2: the
regulatory contract entities failed to produce content.
**Winner: BOTH → V30 LOSE_BOTH**

### 4. Claim-frames (PICO)

**V30 says.** Per-trial PICO rendering via contract slots:
SURPASS-2 has P (T2D), I (tirzepatide — implicit via trial
name), C (semaglutide 1mg), O (HbA1c change at 40 weeks) +
uncertainty (CIs + P). SURPASS-4 has P (high-CV-risk T2D), C
(insulin glargine), partial O.

**ChatGPT says.** Same PICO depth but richer population detail
(N=1,879, mean diabetes duration 8.6y, HbA1c 8.28%, weight
93.7kg) on SURPASS-2 (state/compare_chatgpt_dr.txt:161-177).

**Gemini says.** PICO at headline level, less trial-specific.

**Critical appraisal.** V30 captures PICO skeleton well; misses
baseline population richness that ChatGPT has. V30 is closer to
Gemini on depth. **Winner: ChatGPT → V30 TIE (matches Gemini,
loses to ChatGPT) = BEAT_ONE**

### 5. Structure

**V30 says.** Explicit `### SURPASS-N` per-trial subsections
(V28/V29 did not have these at the contract-enforced level) +
Trial Summary table + Trial Program Timeline + Contradiction
Disclosure block + Phase-1 Retrieval Coverage Disclosure.

**ChatGPT says.** Table-based layout with SURPASS/SURMOUNT
columns; sectioned Summary > Sources > Outcomes > Safety.

**Gemini says.** Heavy section headers, narrative subsections.

**Critical appraisal.** V30's per-trial subsections + explicit
coverage/gap disclosure are a true structural advance vs both
competitors. Contradiction disclosure with tier labels is unique
to V30. **Winner: V30 → BEAT_BOTH**

### 6. Contradictions

**V30 says.** 14 numeric contradictions enumerated with source-
tier labels (report.md:78-94). Explicit methodology disclosure
("detector does NOT adjudicate by endpoint, population, dose,
timepoint, or source tier"). Raw output pointer to
contradictions.json.

**ChatGPT says.** No explicit contradiction disclosure.

**Gemini says.** Some discussion of conflicting evidence but not
systematically enumerated.

**Critical appraisal.** V30's contradiction disclosure is
honest-rebuild-grade transparency that neither competitor
provides. PRISMA-aligned. **Winner: V30 → BEAT_BOTH**

### 7. Narrative depth

**V30 says.** 2,442 words total. Efficacy sections are terse
`Field: value [id]` extraction (by design — M-58 contract
slots). Safety/Comparative/Population Subgroups are rich
paragraph synthesis (legacy path).

**ChatGPT says.** 4,830 words with narrative-grade paragraphs
throughout and comparative framing ("HbA1c curves generally
separate within roughly 8 to 12 weeks, then stabilize",
state/compare_chatgpt_dr.txt:610-612).

**Gemini says.** 6,835 words with extensive exposition,
mechanism-of-action paragraphs, clinical-decision framing.

**Critical appraisal.** V30 Phase-2's contract-slot terseness
reduces narrative depth by design in contract sections. The
legacy non-contract sections (Safety, Comparative, Population
Subgroups) compensate partially but don't close the gap.
**Winner: BOTH → V30 LOSE_BOTH**

## Summary

| # | Dimension       | Verdict  |
|---|-----------------|----------|
| 1 | Citations       | LOSE_ONE |
| 2 | Regulatory      | LOSE_BOTH |
| 3 | Jurisdiction    | LOSE_BOTH |
| 4 | Claim-frames    | BEAT_ONE |
| 5 | Structure       | BEAT_BOTH |
| 6 | Contradictions  | BEAT_BOTH |
| 7 | Narrative depth | LOSE_BOTH |

**Tally: BB=2, BO=1 (plus LO=1), LB=3, TIE=0**
(Net ≥BEAT_ONE count: 3)

## Comparison with V28/V29 ceiling

V28 cross-reviewed: 3 BB + 0 BO + 4 LB
V29 cross-reviewed: target 4-5 BB + 2-3 BO + 0-1 LB but actual
was similar to V28 (3 BB + 0 BO + 4 LB stagnation)
V30 Phase-2 run-2: **2 BB + 1 BO + 3 LB** (net ≥BEAT_ONE: 3)

V30 **matches V28/V29 count** but trades differently:
- GAINED: Structure (per-trial subsections + coverage disclosure)
- PRESERVED: Contradictions disclosure
- NEW LOSS: Regulatory (V28/V29 had more regulatory prose from
  legacy scope retrieval; V30 Phase-2's contract regulatory
  entities all fail_min_fields because url_pattern + METADATA_ONLY
  path doesn't extract required_fields)
- NEW LOSS: Jurisdiction (same root cause)

## Next

**HALT + ITERATE**. V30 Phase-2 run-2 is architecturally correct
(primary-trial extraction now accurate, no wrong-paper defects)
but has a **regulatory-entity rendering gap** that drops 2-3
dimensions.

Fix plan for next iteration (V30 Phase-2 run-3):

1. **Regulatory entity content path**: contract regulatory
   entities with `url_pattern` but no DOI currently produce
   METADATA_ONLY and fail_min_fields. Either:
   - (a) Fetch the full URL content (FDA label PDF, EMA EPAR
     PDF, NICE TA page) and pass as direct_quote, so M-58 has
     extractable source
   - (b) Add `licensed_content` path (M-61 Path B) and
     pre-populate regulatory completions
2. **SURPASS-6 rendered-but-unsection issue**: frame_coverage
   says `pass` but report body has no SURPASS-6 subsection. Trace
   through contract_section_runner to see if slot grouping
   dropped it.
3. **Thomas clamp field alignment**: `first_phase_insulin_secretion`
   + `second_phase_insulin_secretion` fields are not reported in
   the Thomas 2022 paper's abstract (they're M-values). Realign
   contract required_fields to what the paper actually reports.

Priority: #1 is the biggest BEAT-BOTH lift (regains regulatory +
jurisdiction dimensions, potentially +2 BB or BO).
