V30 Phase-2 run-2 deep content audit — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh (project default).

## Target

`outputs/full_scale_v30_phase2/clinical/clinical_tirzepatide_t2dm/report.md`
(2,442 words, status=success, qwen=4 GOOD + 1 ACCEPTABLE,
release_allowed=True)

## Context

This is the first V30 Phase-2 sweep run that passed ALL gates.
Run-1 had wrong-PMID extraction (SURPASS-2 rendered SPRINT BP
trial prose). Run-2 launched after fixing 5 contract DOI/PMID
mismatches in `config/scope_templates/clinical.yaml` and adding
an M-56 DOI-consistency guard that refuses PubMed fallback content
when the returned DOI doesn't match the bound DOI.

## Competitors

- `state/compare_chatgpt_dr.txt` — ChatGPT Deep Research (4,830 words)
- `state/compare_gemini_dr.txt` — Gemini Deep Research (6,835 words)

## The 7 BEAT-BOTH dimensions (memory: autoloop_beat_tier1_mandate)

1. **Citations**: primary-trial publication coverage, cited ETDs
   + uncertainty, correct paper/DOI bindings, bibliography quality
2. **Regulatory**: FDA label, EMA EPAR, NICE TA, HC monograph —
   named, cited, with regulatory conclusions
3. **Jurisdiction**: multi-jurisdiction coverage
   (US / EU / UK / Canada), not drug-centric-only
4. **Claim-frames**: PICO (population, intervention, comparator,
   outcome), dose stratification, timepoint specification,
   uncertainty language
5. **Structure**: logical section order, narrative arc, subsection
   granularity (per-trial subsections, dose tables, timeline)
6. **Contradictions**: explicit contradiction disclosure, tier
   transparency, numeric-range reporting
7. **Narrative depth**: word count in context, synthesis beyond
   per-trial extraction, comparative framing, clinical reasoning

## Your job

For each dimension:
- What does V30 Phase-2 run-2 say? (quote with report.md:LINE refs)
- What does ChatGPT DR say? (quote with compare_chatgpt_dr.txt:LINE)
- What does Gemini DR say? (quote with compare_gemini_dr.txt:LINE)
- Verdict: **V30 BEAT_BOTH | V30 BEAT_ONE | V30 LOSE_BOTH | TIE**
- Critical appraisal: PRISMA 2020 / AMSTAR-2 / GRADE lens

## Known V30 architectural differences vs V28/V29

V30 Phase-2 uses the Report Contract Architecture (M-54..M-63):
- 15 contract-required entities per clinical slug (11 trials + 4
  regulatory)
- M-58 slot-bound prose format: `Field: value [id].` terse
  extraction, NOT free-form LLM synthesis, for contract sections
- Non-contract sections (Safety, Comparative, Population
  Subgroups, Limitations) still use legacy LLM synthesis
- Per-entity `not_extractable` verdict when the primary
  content isn't available (cleaner than V29's hallucination-risk
  behavior)

This explains why V30 contract sections (Efficacy lines 5-27)
read as terse bullet-like prose while Safety/Comparative read as
paragraph synthesis.

## Primary audit targets (spot-check first)

The five entities whose PMIDs/DOIs were corrected in commit bcedd57:

1. **SURPASS-2** (Frías NEJM 2021) — report.md lines 9-11. Must
   describe tirzepatide vs semaglutide 1 mg, NOT the SPRINT BP
   trial. Verify: comparator=semaglutide, ETD with uncertainty,
   Eli Lilly sponsor.
2. **SURPASS-4** (Del Prato Lancet 2021) — report.md lines 17-19.
   Must describe high-CV-risk T2D + insulin glargine, NOT a
   placeholder. Verify: comparator=insulin glargine, CV risk
   mention.
3. **SURPASS-5** (Dahl JAMA 2022) — report.md lines 21-23. Must
   describe add-on to insulin glargine.
4. **SURPASS-6** (Rosenstock JAMA 2023) — NOT in report (see if
   contract rendered it correctly or if it fell to `not_extractable`).
5. **Thomas clamp 2022** — report.md lines 31-33. Note: both
   fields show `not_extractable` — is that a retrieval gap or a
   contract-field misalignment?

## Competitor baseline reference (from V29 audit)

V29 lost all three SURPASS trials above to ChatGPT DR on deep
content. Has V30 closed the gap? Key question: does V30 match
ChatGPT's level of ETD + CI + P-value detail?

## Output

Write to `outputs/codex_findings/v30_phase2_run2_audit/findings.md`.

Format:
```markdown
# V30 Phase-2 run-2 audit vs ChatGPT DR + Gemini DR

**7-dimension verdict**: BB=<int>/7 | BO=<int>/7 | LB=<int>/7 | TIE=<int>/7

## Primary-trial spot-check (run-1 regression guard)

1. SURPASS-2: <correct tirzepatide content | WRONG paper> — <evidence>
2. SURPASS-4: <correct | WRONG paper | placeholder>
3. SURPASS-5: <correct | WRONG paper>
4. SURPASS-6: <present | missing | correct>
5. Thomas clamp: <correct | WRONG paper | retrieval gap>

Regression status: <ALL CORRECT | PARTIAL | FAILED>

## 7-dimension analysis

### 1. Citations
V30 says: ...
ChatGPT says: ...
Gemini says: ...
Critical appraisal: ...
Winner: **V30 | ChatGPT | Gemini | TIE** → <BB|BO|LB|TIE>

### 2. Regulatory
<same format>

### 3. Jurisdiction
<same format>

### 4. Claim-frames
<same format>

### 5. Structure
<same format>

### 6. Contradictions
<same format>

### 7. Narrative depth
<same format>

## Summary

Tally: BB=<N> BO=<N> LB=<N> TIE=<N>

## Next

<SHIP if BB ≥ 5/7 | ITERATE with specific fix plan | HALT + diagnose>
```

Keep under 300 lines. Full xhigh reasoning budget. This is the
ship/iterate decision gate.
