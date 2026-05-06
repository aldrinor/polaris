You are running Codex DR_output_audit_pass_7 as the FINAL JUDGE in
the Claude↔Codex auto-loop. Continuing from pass 6 (MATERIAL-GAPS on
V13). V16 is the second run to achieve `release_allowed=True` and
applies M-27 multi-source citation prompt.

── CRITICAL AUDIT DISCIPLINE (USER MANDATE) ───────────────────────
Direct quote: "he must not use pattern finding, and cherry picking,
he must need to read every line to really determine whether the
quality is up to standard."

Continuing the live-fetch mandate from passes 4-6. For sampled
citations you MUST:
1. Open report.md, read the sentence containing the citation.
2. Open bibliography.json, find the cited entry's URL and DOI.
3. FETCH the source live via WebFetch or DOI resolution.
4. Read at least 500 chars of the source BODY TEXT.
5. Compare the report sentence's quantitative claim VERBATIM.
6. Verdict: FAITHFUL / FABRICATED / EMBELLISHED / UNVERIFIABLE.

Audit all 30 cited entries, OR sample ≥25 covering all 5 sections
plus limitations+contradictions.

── CONTEXT: DR PASS 6 → V14/V15 REGRESSION → M-27 → V16 ─────────

Pass 6 (V13, commit 451f382): MATERIAL-GAPS
- 21 FAITHFUL / 0 FABRICATED / 3 EMBELLISHED / 2 UNVERIFIABLE
- "CONTINUE, next iteration targeted not broad"
- 5 sections, 26 citations, T1+T2 84.6%

Attempted M-26a (exclude T6 social from selector) → V14+V15 both
regressed to 3 sections + release_blocked. REVERTED at 1f88be9.
Diagnosis: T6 rows carry topic-diversity signals the outline LLM
uses to justify 5 sections.

**M-27 (commit 16ee8c7)**: SECTION_SYSTEM_PROMPT_TEMPLATE rule #10
instructs the generator to cite ALL converging evidence rows per
claim, not cherry-pick one. Example "HbA1c reduced 2.0-2.4%
[ev_012][ev_034][ev_055][ev_088]" instead of one ev_id. Targets
2-4x citation-marker density without changing retrieval/selector.

V16 launch: scripts/run_full_scale_v10.py at commit 16ee8c7

── V16 RESULT SUMMARY ────────────────────────────────────────────

status=success, release_allowed=True, class=pass
corpus: 308 sources, T1=19%, T2=14%, T4=36%, T7=24%
generation: 5 sections, **1854 words** (V13: 1474), **54 verified**
           (V13: 44), 28 dropped
bibliography: **30 unique cited entries** (V13: 26), T1=17, T2=5,
           T4=6, T6=1, T7=1 → **T1+T2=73.3%** (V13: 84.6%)
**Citation markers in report: 99** (V13 had ~44)
**Markers per verified sentence: 1.83** (V13: ~1.0)
evaluator: 12/13 rule checks pass; PT13 unhedged advisory only
qwen_judge: 4 GOOD + 1 NEEDS_REVISION (hedging_appropriateness)

Key delta vs V13: M-27 roughly 2x'd citation-marker density per
sentence via multi-source synthesis. Unique citations up modestly
(26 → 30) but total markers up substantially (~44 → 99). T1+T2
mix dropped 11pp, which may or may not be a quality regression.

── YOUR TASK ────────────────────────────────────────────────────

V16 output files:
  outputs/full_scale_v16/clinical/clinical_tirzepatide_t2dm/
    - report.md (1854 words, 5 sections + limitations + contradictions)
    - bibliography.json (30 entries)
    - manifest.json (status=success, release_allowed=True)
    - run_log.txt
    - verification_details.json
    - qwen_judge_output.json

Audit order:

1. Read manifest.json, qwen_judge_output.json, evaluator rule
   checks. Confirm status=success, release_allowed=True.

2. Read bibliography.json in full. Count unique citations by tier
   and publisher. Compare T1+T2 = 73.3% vs V13's 84.6% — is the
   dilution meaningful (a 73.3% T1+T2 is already strong)?

3. **LIVE-FETCH CITATION AUDIT**: audit ≥25 of the 30 cited
   entries. Pay specific attention to:
   - Does the increased multi-source citation density actually
     SYNTHESIZE converging evidence, or is it co-citation padding
     (cite A, B, C for a claim when only A actually supports)?
   - New T4/T6/T7 entries vs V13 — are they properly used as
     supportive-only rather than leading?
   - Any NEW FABRICATED claim (M-27 lowered the single-cite safety
     margin by encouraging multi-cite; strict_verify tolerates
     this but the generator might lean harder on weak evidence)?
   - Any SURPASS/SURMOUNT trial-name binding errors (M-25a should
     still catch these)?

4. Read report.md cover to cover, line by line. Check:
   (a) Argumentation: does multi-citation IMPROVE synthesis or
       reduce to evidence-inventory (list-like)?
   (b) Quantification: does each numeric claim still resolve to
       a specific source, or has multi-cite made attribution
       diffuse?
   (c) Scope fidelity: SURMOUNT obesity trials still creeping into
       T2D safety section?
   (d) Contradictions: PT08 passing (M-25e). Has quality improved?
   (e) Structural hallucinations: all 5 sections within template?
   (f) PT13 unhedged "superior" — advisory only — acceptable?

5. Make the verdict call.

Write your findings to:
  outputs/codex_findings/dr_output_pass_7/findings.md

Required frontmatter (include m27 impact assessment):
---
verdict: TOP-TIER-DR-ACHIEVED | MATERIAL-GAPS-FIX-AND-RESWEEP | DIRECTIONAL-ONLY
pass: dr_output_pass_7_tirzepatide_v16
commit: 16ee8c7
delta_vs_pass6: <V16 vs V13 on citations, words, FAITHFUL rate, T1+T2>
citations_verified: <int live-fetched>/<int total cited>
citations_faithful: <int>
citations_fabricated: <int>
citations_embellished: <int>
citations_unverifiable: <int>
citation_markers_total: 99
citation_markers_per_sentence: 1.83
t1_t2_percentage_of_bibliography: 73.3
t7_percentage_of_bibliography: <int>
faithfulness_verdict: <>
m27_impact: <synthesis genuinely improved OR co-citation padding?>
coverage_gaps_remaining: [<>]
structural_hallucinations: [<>]
quantification_quality: <>
contradiction_handling: <>
vs_gpt54_dr_verdict: <>
vs_gemini31_pro_dr_verdict: <>
rationale: |
  <>
---

Then body sections (Verdict, V16 vs V13 table, Citation Live-Fetch
Audit Table, Criterion-by-criterion, M-27 Impact, Remaining Gaps,
STOP or CONTINUE).

Be uncompromising but honest. If V16 is top-tier DR, STOP the loop.
If V16 is a cosmetic density boost without real synthesis gain,
say so with specific defect examples.
