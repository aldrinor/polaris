# Claude V30 Phase-2 run-7 audit vs ChatGPT DR + Gemini DR

Audit lens: PRISMA 2020 + AMSTAR-2 + GRADE + 7 BEAT-BOTH
dimensions (autoloop_beat_tier1_mandate). Target:
`outputs/full_scale_v30_phase2_run7/clinical/clinical_tirzepatide_t2dm/report.md`
(2,489 words, status=success, release_allowed=True).

## Headline

V30 Phase-2 run-7 is the **first run to pass all release gates**
post-M-66. Headline delta vs run-2:

| Metric                     | Run-2 | Run-7          |
|----------------------------|-------|----------------|
| status                     | partial_qwen_advisory | **success** |
| release_allowed            | False | **True**       |
| qwen verdicts              | 3 GOOD + 2 NEEDS_REVISION | 2 GOOD + 2 ACCEPTABLE + 1 NEEDS_REVISION |
| frame coverage (pass)      | 8/15  | **14/15**      |
| metadata_only regulatory   | 6/6   | **0/6**        |
| Thomas clamp extractions   | 2 not_extractable | **7 fields extracted** |
| NICE TA1026 extractions    | 0     | **2 extracted** |
| M-63 parse failures        | 1     | 3 (down from 6 in run-5) |
| Trial Summary rows (real)  | 2     | 2              |
| SURPASS-6 rendered         | NO    | **NO** (regression unfixed) |

## Primary-trial spot-check

1. **SURPASS-2**: correct Frías content, full ETD+CI+P. ✓
2. **SURPASS-4**: CV-risk, insulin glargine comparator. Only 3
   fields extracted (population/comparator/sponsor). ⚠ partial
3. **SURPASS-5**: baseline_hba1c 8.31%, primary endpoint, safety
   signal with specific AEs. ✓
4. **SURPASS-6**: **STILL not rendered** in report body despite
   frame_coverage=pass. Same M-63 drop bug as run-5. ✗
5. **SURMOUNT-2**: All 10 fields "not extractable". Direct_quote
   from PubMed clearly available. M-58 extraction failed. ✗
6. **Thomas clamp**: **7 of 10 fields extracted** (was 0 in run-5).
   M-66c yaml realignment worked. ✓

## Regulatory spot-check

| Entity           | Render | Fields extracted | Notes                                |
|------------------|--------|------------------|--------------------------------------|
| FDA Mounjaro     | ✗      | 0                | DROPPED from report body entirely    |
| FDA Zepbound     | ✓      | 0 (1 not_ext)    | Renders heading but all not_ext      |
| EMA Mounjaro EPAR| ✗      | 0                | DROPPED                              |
| NICE TA924       | ✓      | 0 (1 not_ext)    | Heading only                         |
| NICE TA1026      | ✓      | **2 extracted**  | First successful regulatory extract  |
| HC Mounjaro      | ✗      | 0                | DROPPED                              |

FDA Mounjaro, EMA EPAR, HC Mounjaro: frame_coverage=pass BUT
all 3 dropped from report body (same M-63 drop-on-verify bug as
SURPASS-6).

## 7-dimension analysis

### 1. Citations
V30 now has correct SURPASS-2 ETD+CI+P, Thomas clamp fields,
Trial Summary still thin. ChatGPT DR maintains fuller per-trial
coverage (SURPASS-1/3/4/6 all rendered with ETD detail). Gemini
thinner on CIs.
Winner: **ChatGPT → BO**

### 2. Regulatory
V30: 2 regulatory subsections rendered with content
(NICE TA1026: 2 fields extracted; FDA Zepbound: heading only).
4 regulatory subsections DROPPED from body. ChatGPT names FDA
+ EMA prescribing info substantively. Gemini covers FDA boxed
warning + HC safety review.
Winner: **BOTH → LB** (V30 improved retrieval but generator
drop-bug blocks actual rendering)

### 3. Jurisdiction
V30 mentions US (NICE TA1026 indicates UK), EudraVigilance (EU
pharmacovigilance). ChatGPT: US + EU explicit. Gemini: US + EU +
HC Canada + pan-regional.
Winner: **BOTH → LB** (V30 closer but still behind)

### 4. Claim-frames (PICO)
SURPASS-2 PICO now complete (population, comparator, primary
endpoint, ETD, sponsor). Thomas clamp PICO now populated.
SURPASS-4/5 partial. SURMOUNT-2 all fields "not extractable".
Winner: **ChatGPT (still deeper across all trials) → BO**

### 5. Structure
V30 emits 6 efficacy subsections + 1 mechanism + 3 regulatory
subsections rendered + 4 cross-section subsections. **3
regulatory + SURPASS-6 subsections silently drop** (passed M-59
but dropped post-strict_verify). Trial Summary still 2 rows
(vs M-66 acceptance gate ≥6). Timeline 2 entries.
Winner: **ChatGPT → LB** (structural regression: more
subsection slots produced but generator drops them)

### 6. Contradictions
V30 enumerates contradictions with tier labels (unique
affordance). Neither competitor.
Winner: **V30 → BB**

### 7. Narrative depth
V30 2,489 words. ChatGPT 4,830. Gemini 6,835. Safety + Comparative
+ Population Subgroups sections show strong narrative synthesis
in V30 (e.g., SUMMIT HFpEF subgroup HR 0.64/0.61 detail), but
overall word count lags.
Winner: **BOTH → LB**

## Summary

| # | Dimension       | Claude verdict |
|---|-----------------|----------------|
| 1 | Citations       | BO             |
| 2 | Regulatory      | LB             |
| 3 | Jurisdiction    | LB             |
| 4 | Claim-frames    | BO             |
| 5 | Structure       | LB             |
| 6 | Contradictions  | BB             |
| 7 | Narrative depth | LB             |

**Tally: 1 BB + 2 BO + 4 LB** (net ≥BEAT_ONE: 3)

**Ship gate**: `BEAT_BOTH_SHIP` requires ≥5/7 BB/BO AND zero
LB. Run-7 hits 3/7 ≥BO with 4 LB. **NOT SHIP**. Classifies as
`PHASE2_CHECKPOINT` if no regressions vs run-2.

Vs run-2 (1 BB + 2 BO + 4 LB net 3): identical tally but
qualitatively better (all gates pass, regulatory retrieval
working, Thomas clamp correct, SURPASS-2 full ETD).

## Pinned blocker for run-8

**M-63 generator drop-on-verify bug**: 4 contract slots with
frame_coverage=pass (SURPASS-6, FDA Mounjaro, EMA EPAR, HC
Mounjaro) silently drop from report body. The
`run_contract_section` sentence re-grouping logic loses them
somewhere between strict_verify output and slot-body assembly.

This is Codex-predicted: pass-3 findings.md Medium #3 warned
the Trial Summary "real content" filter surface might drift,
and pass-3 findings Blocker-1 warned about "extraction starvation
vs verifier drop". Run-7 confirms the latter.

## Next: M-66a-T telemetry (data-indicated now)

Codex pass-3 deferred M-66a-R verifier relaxation but approved
M-66a-T telemetry. Run-7 data now calls for M-66a-T:
instrument `run_contract_section` with per-slot
drop-cause telemetry (raw_sentences, kept_sentences,
drop_reasons, entity_to_slot_id resolution). Diagnose why 4
pass-retrieved entities silently drop before implementing the
fix.

## Codex cross-review ask

Launch Codex at gpt-5.4 xhigh on the same `findings.md` target.
Reconcile disagreements. Expected key disagreement points:
- Whether SURPASS-6 drop is Structure LB or a regression
- Whether NICE TA1026 extraction counts as Regulatory recovery
- Whether M-66c Thomas clamp fix is enough to move Claim-frames
  to BB
