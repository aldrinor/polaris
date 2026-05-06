You are Codex DR output audit pass 11 (compact retry). Prior run hit
context exhaustion dumping contradictions.json. This pass narrows
source set.

## Context budget discipline (HARD)

Read ONLY these files. Do NOT read:
- `contradictions.json` (too large; V23 already summarizes 13 items
  in the body)
- `live_corpus_dump.json` (too large)
- `verification_details.json` (not needed)
- Any source fetches via WebFetch

Read THESE, and only these:

1. `outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/report.md`
   — the V23 artifact under audit (2502 total words, 1455 prose)
2. `outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/bibliography.json`
   — 31 citations
3. `state/compare_chatgpt_dr.txt` — competitor 1
4. `state/compare_gemini_dr.txt` — competitor 2

Optional skim if needed (but don't dump):
- `outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/manifest.json`
  (ONLY the generator.outline_sections, generator.words, and
  evaluator_gate.reasons fields — skim, don't dump)

## Your task — dimension-by-dimension

For each of the 7 dimensions, produce a verdict and a 2-sentence
reason that cites line ranges. No enumeration, no source-tables, no
rechecking every citation.

Dimensions (same as pass 10):
1. Citations (count + primary-trial coverage + URL diversity)
2. Regulatory (FDA / EMA / NICE / Health Canada specificity)
3. Jurisdictional precision (specific authority attribution)
4. Claim frames (per-trial N + baseline + comparator + endpoint +
   timepoint)
5. Structural depth (tables, subsections, limitations/gaps)
6. Contradiction handling (body-level adjudication vs detector dump)
7. Narrative depth (total prose words, explanatory sentences,
   mechanism/pharmacology)

Verdict keywords: BEAT_BOTH | BEAT_ONE | LOSE_BOTH (per dimension).

## User mandate (from memory)

- "he must not use pattern finding, and cherry picking, he must need
  to read every line" — but also do NOT blow context. Compromise:
  read the full V23 report.md and the full competitor files, but
  DON'T read auxiliary JSON artifacts that don't add content signal.
- No metadata/string-presence audits. Actual content read.
- BEAT_BOTH criterion strict. PARTIAL / LOSE_BOTH → enumerate
  specific gaps for V24.

## Output (WRITE THIS FIRST before any re-reading)

Write `outputs/codex_findings/dr_output_pass_11/findings.md`:

```
# DR output audit pass 11 — V23 BEAT-BOTH head-to-head (compact)

## Dimension scores
1. Citations:              <verdict>
   reason: <2 sentences + report.md / competitor line citations>
2. Regulatory:             <verdict>
   reason: ...
3. Jurisdictional:         <verdict>
   reason: ...
4. Claim frames:           <verdict>
   reason: ...
5. Structural depth:       <verdict>
   reason: ...
6. Contradiction handling: <verdict>
   reason: ...
7. Narrative depth:        <verdict>
   reason: ...

## Overall verdict
BEAT_BOTH | PARTIAL | LOSE_BOTH

## Specific gaps POLARIS must close (if not BEAT_BOTH)
1. <actionable>
2. ...

## Notes
<any primary-source checks or evidence-grounding flags>
```

Write the file skeleton first with placeholder verdicts, then fill
in as you read. If you run out of context, the partial file still
records what you determined. DO NOT do a full-tree enumeration
before starting to write.
