You are Codex, running step 2b of the autoloop V2 protocol:
**DEEP CONTENT AUDIT** of POLARIS V28 output.

## This is NOT a metadata audit

The metadata tier (URL counts, word counts, heading counts) is already
covered by the M-49 preservation suite
(`tests/polaris_graph/test_m49_v28_preservation.py`).

Read the V28 report **line by line** as a clinical document answering
the tirzepatide/T2D research question. Apply PRISMA 2020, AMSTAR-2,
GRADE, and clinical-epidemiology judgment per claim.

## Artifacts

- **V28 report**: `outputs/full_scale_v28/clinical/clinical_tirzepatide_t2dm/report.md`
- **V28 manifest**: `.../manifest.json`
- **V28 bibliography**: `.../bibliography.json`
- **V28 live corpus**: `.../live_corpus_dump.json`
- **V28 contradictions**: `.../contradictions.json`
- **Competitor baselines**:
  - ChatGPT 5.4 Pro DR: `state/compare_chatgpt_dr.txt`
  - Gemini 3.1 Pro DR: `state/compare_gemini_dr.txt`
- **V27 reference audit (prior cycle)**:
  - `outputs/audits/v27/claude_deep_content_audit.md`
  - `outputs/codex_findings/v27_deep_content_audit/findings.md`

## V27 content-audit scoreboard (for context)

| Topic | ChatGPT | Gemini | V27 |
|---|:-:|:-:|:-:|
| A. SURPASS-2 primary ETDs | WIN | 2nd | LOSE (cited T4 post-hoc) |
| B. SURPASS-CVOT MACE | 2nd | WIN | LOSE (omitted entirely) |
| C. SURPASS-4 52/104-wk | WIN | 2nd | LOSE (one sentence, no data) |
| D. Mechanism clamp data | 2nd | WIN | LOSE (paper cited, not mined) |
| E. Regulatory breadth | LOSE | 2nd | WIN (only FDA+EMA+NICE+HC) |
| F. Contradictions/transparency | 2nd | LOSE | WIN (13-item enumeration) |

Aggregate: ChatGPT 2 wins / Gemini 2 wins / V27 2 wins.

## V28 bundle interventions targeting the 4 V27 losses

- **M-44** (primary-trial scorer/subset injection + same-sentence
  validator + one-shot regen): should fix topics A, B, C.
- **M-45** (refetch diagnostics + targeted acquisition): enables the
  M-42b trial-summary table and M-50 subsections.
- **M-46** (selector no-bypass): floors now fire regardless of pool
  size.
- **M-47** (evidence-linked clamp/PK validator + regen): should fix
  topic D.
- **M-48** (first-author variants + population-scope labels): raises
  primary-trial retrieval coverage from 4/11 to target ≥9/11.
- **M-50** (per-trial subsections for T2D-direct primaries): new
  structural artifact covering topics A, C, and (if CVOT in subset)
  topic B.

Preserve V27 wins on topics E, F (Regulatory + Contradictions).

## What to audit (6 topics)

Use the same topic structure as your V27 audit. For EACH topic:

1. Quote what V28 says about this topic (line numbers from report.md).
2. Quote what ChatGPT and Gemini say (line numbers from state/compare_*.txt).
3. Critical appraisal (PICO, effect estimate with uncertainty, study
   design, open-label/sponsorship, indirectness).
4. Winner per topic: ChatGPT / V28 / Gemini / Tie.

Topics (in this order):
- **A. SURPASS-2** (vs semaglutide 1 mg, N=1,879, 40 weeks).
  Primary frame = HbA1c ETDs −0.15/−0.39/−0.45%, weight ETDs
  −1.9/−3.6/−5.5 kg, Frías NEJM 2021.
- **B. SURPASS-CVOT** (N=13,299, MACE-3 HR 0.92 95.3% CI 0.83-1.01
  P=0.003 NI, P=0.09 sup trend, Nicholls et al.).
- **C. SURPASS-4** (N=1,995, high-CV-risk 87% prior CVD, 52 wk primary
  + 104 wk durability, vs insulin glargine, Del Prato Lancet 2021).
- **D. Mechanism** — dual GIP/GLP-1 agonism. Key clamp findings
  (Thomas Lancet D&E 2022): 63% M-value rise, biphasic insulin
  secretion, 5-day half-life, 39-aa peptide with C20 fatty diacid,
  receptor-affinity asymmetry (imbalanced dual agonist).
- **E. Regulatory coverage** — FDA / EMA / UK NICE / Health Canada.
  Jurisdiction-specific facts (NICE TA924 triple-therapy criteria +
  BMI-by-ethnicity thresholds; HC Product Monograph + KwikPen +
  counterfeit advisories; EMA pediatric ≥10 indication).
- **F. Contradictions and uncertainty** — sponsor disclosure,
  open-label bias, comparator-evolution caveat (sema 1 mg vs current
  2 mg), numeric heterogeneity enumeration.

## Additional V28-specific checks

Beyond the 6 topics:

1. **M-42b Trial Summary table** (if present in report):
   - ≥6 rows? N/baseline/comparator/endpoint/result/ref cells populated?
   - Each row cites a real bibliography [N] marker?
2. **M-50 Per-Trial Summaries block** (if present):
   - ≥2 subsections? Each covers all 7 elements (N, population,
     comparator, endpoint, timepoint, effect-with-uncertainty, safety
     caveat)?
   - Subsections only for T2D-direct trials (SURMOUNT-2 yes;
     SURMOUNT-1/3/4 no unless template relabels)?
3. **M-47 Mechanism extraction**:
   - Mechanism section contains ≥3 inline quantitative findings from
     the cited clamp paper with [ev_X] in the same sentence?
4. **M-44 primary-trial coverage**:
   - Primary publications cited for ≥7 of 11 pivotal trials?
   - Trial-name mentions have same/adjacent-sentence primary [N] cite?
5. **M-48 SURMOUNT population-scope discipline**:
   - SURMOUNT-1/3/4 (if cited) framed as obesity-only / indirect for
     T2D? Not merged into T2D efficacy claims?

## Output format

Write to `outputs/codex_findings/v28_deep_content_audit/findings.md`.

Structure per V27 precedent:
- Per-topic sections (A-F) each with V28 / ChatGPT / Gemini quotes +
  critical appraisal + winner.
- "Additional V28 checks" section covering items 1-5 above.
- **Final aggregate**: topic wins (ChatGPT / V28 / Gemini counts).
- **Closest-to-systematic-review-standard**: ChatGPT / V28 / Gemini.
- **Clinical usefulness verdict**: which report best for each
  physician question.

## Stop criterion (unchanged)

BEAT-BOTH ChatGPT DR + Gemini 3.1 Pro DR on ALL 7 dimensions
(measured via per-dim table in `outputs/audits/v27/cross_review.md`
precedent). Shippable = 7/7 BEAT_BOTH.

V28 target per approved plan: 5 BB + 2 BO + 0 LB. Your deep-content
audit is what proves or disproves that projection.
