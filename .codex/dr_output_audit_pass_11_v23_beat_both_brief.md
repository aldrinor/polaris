You are Codex DR output audit pass 11. V23 just re-gated clean
(PT11 widened in M-34, release_allowed=True). Head-to-head V23 vs
ChatGPT DR + Gemini 3.1 Pro DR on the same tirzepatide/T2D query.

## Stop criterion (user mandate, carried from V19+)

BEAT-BOTH across all 7 dimensions. Anything less = loop back.

Dimensions:
1. Citations (count + unique primary-trial coverage + URL diversity)
2. Regulatory (FDA / EMA / NICE / Health Canada specificity)
3. Jurisdictional precision (claims attributed to specific authority,
   not generalized "both agencies require...")
4. Claim frames (per-pivotal-trial N + baseline HbA1c + baseline weight
   + comparator + primary endpoint + timepoint)
5. Structural depth (trial-comparison table, dose-response table,
   direct-vs-indirect comparator table, regulatory subsection breakdown,
   limitations/gaps section)
6. Contradiction handling (endpoint, dose, population, comparator,
   estimand, timepoint separation + evidence-strength language; esp.
   noninferiority vs superiority for SURPASS-CVOT)
7. Narrative depth (total prose words + per-claim explanatory sentences
   + mechanism/pharmacology context + clinical-practice guidance)

Per user memory: no pattern matching, no cherry-picking — read every
cited claim line-by-line, cross-check against fetched source content,
apply PRISMA 2020 / AMSTAR-2 / GRADE, flag operator-fabrication, no
metadata / PASS-FAIL string-presence tables.

## Artifacts

POLARIS V23:
- `outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/report.md`
- `outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/manifest.json`
  (status=success, release_allowed=true as of M-34 regate)
- `outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/bibliography.json`
  (31 citations)
- `outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/contradictions.json`
- `outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/evaluator_rule_checks.json`

Competitors (raw DR exports, same query):
- `state/compare_chatgpt_dr.txt` — ChatGPT DR (~4830 words, ~45 cite slots, ~21 unique URLs)
- `state/compare_gemini_dr.txt` — Gemini 3.1 Pro DR (~6054 words, ~43 unique URLs)

## Session discipline

- You will hit the context budget; that is known. Write partial
  findings as you go.
- Write `outputs/codex_findings/dr_output_pass_11/findings.md`
  incrementally. Do NOT spend the first 50% of your budget enumerating
  the whole repo file tree.
- For each dimension, produce a concrete verdict
  (BEAT_BOTH / BEAT_ONE / LOSE_BOTH) and cite the evidence line
  numbers in report.md / bibliography.json / competitor files.
- Overall verdict at the end: BEAT_BOTH / PARTIAL / LOSE_BOTH.
- If PARTIAL or LOSE_BOTH: enumerate the specific gaps POLARIS must
  close for V24. Be concrete enough that the next iteration's fix
  is actionable (e.g. "add SURPASS-CVOT primary trial to retrieval
  queries", not "expand retrieval").

## V23 key delta from V21 (pass 10 reference)

V21 pass 10 (Codex DR audit): PARTIAL.
  - Regulatory: BEAT_BOTH (unchanged — V23 retains FDA+EMA+NICE+HC)
  - Claim frames: LOSE_BOTH (M-32 prompt added; measure how much
    V23 closed the gap now)
  - Structural depth: LOSE_BOTH
  - Narrative depth: LOSE_BOTH (V23 prose ~1455 words; ChatGPT 4830;
    Gemini 6054 — still a gap; M-33 raised section_max_tokens but
    generator didn't fill the headroom)
  - Contradiction handling: BEAT_ONE
  - Citations: BEAT_ONE
  - Jurisdictional: BEAT_ONE

## Verdict format

`outputs/codex_findings/dr_output_pass_11/findings.md`:

```
# DR output audit pass 11 — V23 BEAT-BOTH head-to-head

## Dimension scores
1. Citations:              BEAT_BOTH|BEAT_ONE|LOSE_BOTH
   reason: <cite line numbers in report.md / competitor txt>
2. Regulatory:             ...
3. Jurisdictional:         ...
4. Claim frames:           ...
5. Structural depth:       ...
6. Contradiction handling: ...
7. Narrative depth:        ...

## Overall verdict
BEAT_BOTH | PARTIAL | LOSE_BOTH

## Specific gaps POLARIS must close (if not BEAT_BOTH)
1. <actionable gap with concrete fix hint>
2. ...

## Notes / quality observations
<any primary-source checks, evidence-grounding flags, or operator
fabrication signals>
```

If BEAT_BOTH: autoloop stops. User's quality mandate met.
If PARTIAL/LOSE_BOTH: next iteration needs the specific gaps above.
