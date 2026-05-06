You are running Codex DR_output_audit_pass_10 as the FINAL JUDGE in
the Claude↔Codex auto-loop. This is a BEAT-BOTH head-to-head verdict.

## Stop condition (user mandate 2026-04-20)

The autoloop terminates when POLARIS beats BOTH ChatGPT Deep
Research AND Gemini 3.1 Pro Deep Research head-to-head on the
tirzepatide/T2D query. Not "matches", not "tier-1 quality" — must
BEAT BOTH on the 7 agreed dimensions.

## The three artifacts

1. POLARIS V21: `outputs/full_scale_v21/clinical/clinical_tirzepatide_t2dm/report.md`
   - bibliography: `outputs/full_scale_v21/clinical/clinical_tirzepatide_t2dm/bibliography.json`
   - manifest (rule/eval gate): `outputs/full_scale_v21/clinical/clinical_tirzepatide_t2dm/manifest.json`
2. ChatGPT Deep Research: `state/compare_chatgpt_dr.txt`
3. Gemini 3.1 Pro Deep Research: `state/compare_gemini_dr.txt`

All three answer the EXACT SAME research question:
"What is the efficacy and safety of tirzepatide for glycemic control
and weight loss in adults with type 2 diabetes?"

## Audit discipline (user mandate, reconfirmed 2026-04-20)

Direct quote: "he must not use pattern finding, and cherry picking,
he must need to read every line to really determine whether the
quality is up to standard."

- Line-by-line reading, not metadata summary.
- Cross-check claims against cited sources where feasible.
- No constructed probes; ground criticism in observed content.

## 7 dimensions (strict scoring)

For each dimension, award one of: `BEAT_BOTH`, `BEAT_ONE`, `TIE`,
`LOSE_ONE`, `LOSE_BOTH`. Brief reasoning required, with line
references.

1. **Citations (count + diversity)**: V21 bibliography count,
   ChatGPT references count, Gemini references count. Also note
   % unique primary trials cited in each.
2. **Regulatory retrieval**: FDA/EMA/NICE/Health Canada/EU sources
   cited by each report. Note specific regulatory documents.
3. **Jurisdictional precision**: does each report correctly
   attribute claims to specific jurisdictions (e.g. boxed warning
   = FDA-specific)? Flag any "both agencies / regulators require"
   style overclaims.
4. **Claim frames (per-trial rigor)**: for each named trial, does
   the report give N + baseline HbA1c + baseline weight + primary
   endpoint? This is a trial-framing completeness check.
5. **Structural depth**: per-trial sub-sections, trial-comparison
   tables, dose-response tables, regulatory sub-section, etc.
6. **Contradiction handling**: adjudicated by
   endpoint/population/comparator vs mechanical enumeration.
   Evidence-strength labels (noninferiority vs superiority).
7. **Narrative depth**: body word count, sentences per cited claim,
   mechanism/pharmacology framing, context depth.

## V21 known issues (for context, not to re-litigate)

- V21 `eval_gate.release_allowed=False` due to two ADVISORY items:
  `advisory_pt13_unhedged_superlatives` (2 unhedged superlatives
  in prose) and `qwen_citation_tightness_needs_revision`. These
  are advisories, not hard aborts. Do not let them alter the
  head-to-head verdict — assess V21 on content, not on advisory
  flags.
- V21 tier mix: 50% T1+T2, 89.5% T1+T2+T3. Regulatory (T3) count
  is 15, significantly higher than competitors.

## Expected verdict outcomes

- **BEAT-BOTH (all 7 dimensions BEAT_BOTH or BEAT_ONE on ≥5)**:
  terminate loop; V21 becomes the baseline.
- **PARTIAL (BEAT_BOTH on some, LOSE_BOTH on others)**: specify
  which dimensions POLARIS must close; claude iterates Fix
  B/C/A in the ranked order.
- **LOSE (LOSE_BOTH on majority)**: large gaps; claude iterates
  multiple fixes.

## Verdict format

Write `outputs/codex_findings/dr_output_pass_10/findings.md`:

```
# DR output audit pass 10 — V21 BEAT-BOTH head-to-head

## Dimension scores
1. Citations:              BEAT_BOTH | BEAT_ONE | TIE | LOSE_ONE | LOSE_BOTH
   reason: ...
2. Regulatory:             ...
3. Jurisdictional:         ...
4. Claim frames:           ...
5. Structural depth:       ...
6. Contradiction handling: ...
7. Narrative depth:        ...

## Overall verdict
BEAT_BOTH | PARTIAL | LOSE_BOTH

## Specific gaps POLARIS must close
<ranked list, if PARTIAL or LOSE_BOTH>

## Notes / quality observations
<anything else worth surfacing>
```

Be strict. We can't declare victory if V21 loses on narrative
depth to both competitors by 3x. That's a real gap.

## Cost discipline

This is one expensive audit. Deep read, one pass. Don't re-do on
your own — the next iteration launches from your verdict.
