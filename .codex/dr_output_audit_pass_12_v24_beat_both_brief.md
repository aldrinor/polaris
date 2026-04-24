You are Codex DR output audit pass 12. V24 just completed with the
full V24 code stack active (M-35 primary-trial retrieval, M-36 trial
summary table, M-37 Health Canada tier fix + jurisdictional coverage
rule, M-38 claim-frame hard constraint, M-40 Mechanism section rule).
Head-to-head V24 vs ChatGPT DR + Gemini 3.1 Pro DR on the same
tirzepatide/T2D query as pass 11.

## Stop criterion (user mandate, unchanged)

BEAT-BOTH across all 7 dimensions. Anything less = PARTIAL.

Dimensions:
1. Citations (count + unique primary-trial coverage + URL diversity)
2. Regulatory (FDA / EMA / NICE / Health Canada specificity)
3. Jurisdictional (named-authority attribution, multi-agency coverage)
4. Claim frames (N / baseline / comparator / dose / endpoint / timepoint / effect size in the same claim clause)
5. Structural depth (tables, subsections, trial-level organization)
6. Contradiction handling (numeric disagreement enumeration + adjudication)
7. Narrative depth (mechanism / pharmacology / clinical interpretation)

For each dimension, return one of:
- BEAT_BOTH — V24 is stronger than BOTH competitors
- BEAT_ONE — V24 beats one competitor, loses the other
- LOSE_BOTH — V24 is weaker than BOTH

## Context budget discipline (HARD)

Read ONLY these files. Do NOT read:
- `contradictions.json` (large; V24 summarizes in body)
- `live_corpus_dump.json` (too large)
- `archive/`, `loopback/`
- `outputs/codex_findings/dr_output_pass_11/` — the prior verdict is already summarized below; no need to re-read

Sources you MAY read:
```
outputs/full_scale_v24/clinical/clinical_tirzepatide_t2dm/report.md
outputs/full_scale_v24/clinical/clinical_tirzepatide_t2dm/bibliography.json
outputs/full_scale_v24/clinical/clinical_tirzepatide_t2dm/manifest.json
state/compare_chatgpt_dr.txt
state/compare_gemini_dr.txt
```

## V24 headline metrics (already extracted)

- status=success, release_allowed=true, evaluator=13/13 pass
- Sections: Efficacy / Safety / Mechanism / Comparative / Dose Response
  + Trial Summary table + Limitations + Methods + Contradiction disclosures + Bibliography
- Prose body words: 1327, total report words: 2666
- Verified sentences: 38, dropped: 37
- Bibliography: 35 entries, Citations: 89 markers (35 unique)
- Corpus: 409 sources, tier mix T1=15.9% T2=11.0% T3=13.7% T4=32.8%
- SURPASS-2 mentions: 3, SURPASS-3: 7, SURPASS-4: 3, SURMOUNT-4: 4
- Mechanism section present (M-40 fired); Trial Summary table present (M-36 fired)

## Pass 11 (V23) baseline you are comparing against

Verdict on V23: PARTIAL. Dimension scores:
- Citations: LOSE_BOTH
- Regulatory: BEAT_ONE (beat ChatGPT, lost Gemini because Gemini had Health Canada)
- Jurisdictional: BEAT_ONE (beat ChatGPT, lost Gemini)
- Claim frames: LOSE_BOTH
- Structural depth: LOSE_BOTH (prose only, no tables)
- Contradiction handling: BEAT_BOTH
- Narrative depth: LOSE_BOTH (no mechanism)

## Known V24 potential regression flag

V24's outline picked Mechanism instead of Regulatory (swapped, not added).
V24 bibliography: FDA=0, EMA=0, NICE=0, Health Canada=0.
Regulatory and Jurisdictional were BEAT_ONE in V23; they may now be
LOSE_BOTH in V24 since there's no Regulatory section at all.

Verify this or refute it. Do not grade it more favorably than warranted
just because M-37 SHIPPED — the question is what V24's REPORT actually
covers.

## What to verify dimension-by-dimension

### 1. Citations
- Count unique URLs in V24 bibliography (35) vs ChatGPT (21) vs Gemini (43).
- Count unique primary-trial publications (SURPASS-1..6, CVOT, SURMOUNT-1..4) cited in V24 vs competitors. The M-35 fix was meant to put NEJM/Lancet/JAMA primaries as first-class sources. Did it succeed?

### 2. Regulatory
- V24 has no Regulatory section. Does any regulatory content appear in the Safety or Comparative section? How does it compare to ChatGPT's and Gemini's regulatory coverage (FDA label dosing, EMA SmPC, NICE TA, Health Canada monograph, counterfeit warnings)?

### 3. Jurisdictional
- Named-authority attribution in V24 prose. Does V24 ever say "FDA", "EMA", "NICE", "Health Canada" at all? If not, this dimension loses by default.

### 4. Claim frames
- Does V24's named-trial prose carry N / baseline / comparator / dose / endpoint / timepoint / effect size? Spot-check 3-5 named-trial sentences.
- ChatGPT has a trial architecture table; Gemini has narrative trial frames for each SURPASS. V24's Trial Summary TABLE now exists — how does it compare? Cell coverage?

### 5. Structural depth
- V24 has the new Trial Summary table. Compare: V24 table rows / ChatGPT table rows / Gemini subsection depth. Also compare other structural elements (charts, sub-sections, prescribing sections, limitations depth).

### 6. Contradiction handling
- V23 was BEAT_BOTH here. V24 output explicitly?

### 7. Narrative depth
- V24 now has a Mechanism section (5 mechanism mentions in report). How does it compare to Gemini's dual-GIP/GLP-1 mechanism coverage? ChatGPT's clinical interpretation?

## Deliverable

Write `outputs/codex_findings/dr_output_pass_12/findings.md` with:
- 7-dimension table (BEAT_BOTH / BEAT_ONE / LOSE_BOTH per dim)
- Overall verdict (BEAT_BOTH | PARTIAL | REGRESSED)
- Specific gaps V24 must close if not BEAT_BOTH
- Explicit note on whether M-35 / M-36 / M-37 / M-38 / M-40 moved their intended dimensions
- Notes on the Regulatory regression if confirmed

Keep it under 3000 words.
