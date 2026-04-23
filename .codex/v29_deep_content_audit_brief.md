You are Codex, running step 2b of autoloop V2: **DEEP CONTENT AUDIT**
of POLARIS V29 output.

## This is NOT a metadata audit

Metadata-tier checks are handled by the M-49 preservation suite
(extended with V29 custody assertion). Read the V29 report **line
by line** as a clinical document answering the tirzepatide/T2D
research question. Apply PRISMA 2020, AMSTAR-2, GRADE, and
clinical-epidemiology judgment per claim.

## Artifacts

- **V29 report**:
  `outputs/full_scale_v29/clinical/clinical_tirzepatide_t2dm/report.md`
- **V29 manifest**: `.../manifest.json`
- **V29 bibliography**: `.../bibliography.json`
- **V29 live corpus**: `.../live_corpus_dump.json`
- **V29 contradictions**: `.../contradictions.json`
- **V29 custody diagnostic (NEW)**: `.../v29_primary_custody.json`
  — per-anchor telemetry from M-53. Read THIS FIRST before
  composing content audit, because the custody log tells you which
  anchors successfully made it all the way through the pipeline.
- **Competitor baselines**:
  - ChatGPT 5.4 Pro DR: `state/compare_chatgpt_dr.txt`
  - Gemini 3.1 Pro DR: `state/compare_gemini_dr.txt`

## V28 → V29 deltas to examine

The V29 bundle (M-51/52/53) was designed to fix exactly V28's
4 LOSE_BOTH dimensions by preserving anchor-matched primary papers
that V28 dropped:

- **M-51** (selector post-process): scan full scored pool for
  anchor-matched primaries; insert at position 0 if not already
  selected. Cap at min(|anchors|, max_rows).
- **M-52** (generator pull): if anchor's primary is in live_corpus
  but not evidence_pool, pull into evidence_pool with ev_id
  preservation / fallback / content-canonical dedup.
- **M-53** (custody telemetry): 9-field per-anchor diagnostic.

If M-51/52 worked, the V29 bibliography should NOW contain:
- SURPASS-2 primary (Frías NEJM 2021)
- SURPASS-4 primary (Del Prato Lancet 2021)
- SURPASS-CVOT primary (Nicholls NEJM 2025)
- SURMOUNT-1 primary (Jastreboff NEJM 2022)
- SURMOUNT-2 primary (Garvey Lancet 2023)

...which V28 all dropped.

## V27 reference content-audit scoreboard (for context)

V28 was 3 BB + 0 BO + 4 LB. Your V28 audit is at
`outputs/codex_findings/v28_deep_content_audit/findings.md`. Use
the same per-topic structure.

## What to audit (6 topics, same structure as V28)

For EACH topic:
1. Quote what V29 says (line numbers from report.md).
2. Quote what ChatGPT and Gemini say.
3. Critical appraisal (PICO, effect estimate with uncertainty,
   study design, open-label/sponsorship, indirectness).
4. Winner per topic: ChatGPT / V29 / Gemini / Tie.

Topics:
- **A. SURPASS-2** (Frías NEJM 2021, HbA1c ETDs −0.15/−0.39/−0.45%)
- **B. SURPASS-CVOT** (Nicholls NEJM 2025, HR 0.92 NI)
- **C. SURPASS-4** (Del Prato Lancet 2021, 52/104-wk, high-CV-risk)
- **D. Mechanism** (dual GIP/GLP-1, clamp findings)
- **E. Regulatory coverage** (FDA/EMA/NICE/HC)
- **F. Contradictions/uncertainty** (sponsorship, open-label, NI)

## V29-specific checks

1. **Custody telemetry**: read `v29_primary_custody.json` first.
   For each configured anchor, report which boolean failed if any.
   E.g. "SURPASS-2: found=true, selected=true, injected=false" →
   M-44 injection failed. "SURPASS-CVOT: found=true, selected=true,
   injected=true, quote_adequate=false" → M-42b quote-thin.
2. **M-42b Trial Summary table**: ≥6 rows now? Cells populated with
   real numbers (not "SURPASS-5 baseline 7.0%")?
3. **M-50 Per-Trial Summaries**: ≥2 subsections, covering target
   trials (SURPASS-2/-4/-CVOT/SURMOUNT-2) rather than SURPASS-1/-3/-5?
4. **M-47 Mechanism extraction**: Mechanism section contains ≥3
   inline quantitative findings from cited clamp paper with [ev_X]
   in the same sentence?

## Output format

Write to `outputs/codex_findings/v29_deep_content_audit/findings.md`.

Structure per V28 precedent:
- Per-topic sections (A-F)
- V29-specific checks section
- Final aggregate: topic wins
- **7-dimension cross-review scoreboard**: BB / BO / LB per dim
- Closest-to-systematic-review-standard
- Clinical usefulness verdict

## Stop criterion (unchanged)

7/7 BEAT_BOTH ChatGPT + Gemini on all dimensions = SHIPPABLE.
V29 target: 4-5 BB + 2-3 BO + 0-1 LB (up from V28's 3+0+4).

If V29 hits any dim that regressed from V28, §7 trigger #7 fires
and loop halts.
