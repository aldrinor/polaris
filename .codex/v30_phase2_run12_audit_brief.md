V30 Phase-2 run-12 deep content audit — xhigh reasoning.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Target

`outputs/full_scale_v30_phase2_run12/clinical/clinical_tirzepatide_t2dm/report.md`
(3,338 words, status=partial_qwen_advisory, qwen=1G+2A+2NR,
release_allowed=False).

## Run history

| Run | release | qwen | tally | notes |
|-----|---------|------|-------|-------|
|  9 | False | 1G+1A+3NR | 1+4+2 CHECKPOINT | first 15/15 cited |
| 10 | True | 3G+1A+1NR | 1+4+2 ITERATE | SURMOUNT/Thomas regressed |
| 11 | True | 2G+2A+1NR | 1+4+2 ITERATE | SURMOUNT/Thomas/SURPASS-5 recovered |
| 12 | **False** | **1G+2A+2NR** | TBD | V31 (M-70) + V32 (M-71) active |

## What V31 (M-70) + V32 (M-71) delivered

V31 — M-70 regulatory_synthesizer: 4 of 6 regulatory subsections
now render MULTI-SENTENCE PROSE PARAGRAPHS instead of all-stub
not_extractable lists:

  - **FDA Mounjaro**: 3-sentence paragraph quoting MOUNJARO
    indication + concomitant insulin warning + dose escalation
    rules
  - **FDA Zepbound**: 3-sentence paragraph quoting Limitations
    of Use + GLP-1 RA combination warning + MTC contraindication
  - **EMA Mounjaro**: 1-sentence quote about obesity indication
    + OSA extension
  - **NICE TA924**: 1-sentence about commercial access agreement

NICE TA1026 + HC monograph remained gap-disclosed (M-70
segmentation didn't match for those entities — likely heading
table miss).

V32 — M-71 contradiction-aware hedging: Qwen
hedging_appropriateness moved from `needs_revision` (runs 9/10/11)
to `acceptable` (run-12). The note acknowledges discrepancies
explicitly. Word count rose 3,112 → 3,338 (+7%).

## Why release_allowed=False

Qwen citation_tightness=needs_revision flagged:
  "Several factual claims lack adjacent citations, such as the
   statement about the corpus being dominated by lower-tier
   sources and the pipeline detecting contradictions. Some
   sections (e.g., 'Limitations' and 'Methods') contain uncited
   assertions."

This is DIFFERENT from run-9 (gap citations not valid sources).
Run-12's issue is that the Limitations + Methods sections — not
M-58/M-70/M-71 territory — contain pipeline-telemetry statements
(like "16% T1 sources") without [N] markers. The Limitations
section is intentionally telemetry-grounded, not evidence-grounded.

## Competitors

- `state/compare_chatgpt_dr.txt` (4,830 words)
- `state/compare_gemini_dr.txt` (6,835 words)

## Decision gate

- BEAT_BOTH_SHIP = ≥5/7 BB/BO AND zero LB
- PHASE2_CHECKPOINT = ≥4/7 ≥BO AND ≤1 LB
- ITERATE = otherwise

## Audit ask

Apply 7-dim framework. Score deltas vs run-11. Specifically:

1. **Regulatory** — does M-70 prose lift LB → BO? 4/6 substantive
   subsections + 2 gap-disclosed. ChatGPT comparison says U.S./EMA
   contraindication-warning compare; run-12 has FDA contraindication
   + EMA indication but not a U.S./EMA cross-comparison.

2. **Narrative depth** — does M-71 hedging + +7% word count lift
   LB → BO? Hedging_appropriateness ACCEPTABLE now. Run-12 still
   3,338 vs ChatGPT 4,830 / Gemini 6,835. Codex's run-9 prediction
   was target ~4-4.5K after V32; we hit 3.3K.

3. **Citation tightness flag** — is Qwen right that Limitations
   + Methods need [N] citations? The strict_verify
   limitations_paragraph_pass_through warning grants Limitations
   the right to cite tier_fractions/contradiction-detector
   telemetry without [N] markers. Is Qwen overflagging vs PRISMA
   actual rule? Or is this a real gap?

4. **Net BB+BO+LB tally** vs run-11.

5. **Recommended action**: SHIP | CHECKPOINT | ITERATE.

## Output

Write to `outputs/codex_findings/v30_phase2_run12_audit/findings.md`:

```markdown
# Codex V30 Phase-2 run-12 audit

**7-dimension verdict**: BB=<n>/7 | BO=<n>/7 | LB=<n>/7 | TIE=<n>/7

## Ship classification

- Gate: BEAT_BOTH_SHIP | PHASE2_CHECKPOINT | ITERATE
- Net progress vs run-11: <BB+/-, BO+/-, LB+/->
- Regressions: <none | list>

## V31 + V32 effectiveness

<did M-70 lift Regulatory? did M-71 lift Narrative depth?>

## Qwen citation_tightness flag

<is the Limitations + Methods uncited-assertion criticism fair
under PRISMA, or is Qwen overflagging telemetry-grounded prose
that strict_verify intentionally allows?>

## 7-dim analysis

<per-dim with line refs>

## Recommended action

<SHIP | CHECKPOINT | ITERATE-narrow>
```

Under 350 lines. Full xhigh budget. This is the BEAT_BOTH_SHIP
verdict gate after architectural V31+V32 cycle.
