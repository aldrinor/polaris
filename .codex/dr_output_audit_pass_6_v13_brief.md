You are running Codex DR_output_audit_pass_6 as the FINAL JUDGE in
the Claude↔Codex auto-loop. Continuing from pass 5 (MATERIAL-GAPS).
V13 is the FIRST run to achieve status=success + release_allowed=True.
This audit determines whether V13 meets top-tier Deep Research
quality (OpenAI GPT-5.4 DR / Gemini 3.1 Pro DR level) or requires
more iteration.

── CRITICAL AUDIT DISCIPLINE (USER MANDATE) ───────────────────────
Direct quote: "he must not use pattern finding, and cherry picking,
he must need to read every line to really determine whether the
quality is up to standard."

Continuing the live-fetch mandate from passes 4 and 5. For EACH
sampled citation you MUST:

1. Open report.md, read the sentence containing the citation.
2. Open bibliography.json, find the cited entry's URL and DOI.
3. FETCH the source live via WebFetch or DOI resolution.
4. Read at least 500 chars of the source BODY TEXT.
5. Compare the report sentence's quantitative claim VERBATIM.
6. Categorize: FAITHFUL / FABRICATED / EMBELLISHED / UNVERIFIABLE.

Audit ALL 26 cited entries OR all ~44 citation-bearing sentences
(whichever is more citations).

── CONTEXT: DR PASS 5 → M-25e → V13 ──────────────────────────────

DR pass 5 (V11, commit 59b8f4a) verdict: MATERIAL-GAPS.
- 16 FAITHFUL / 0 FABRICATED / 1 EMBELLISHED / 3 UNVERIFIABLE
- 3 sections, 710 words, 12 citations
- PT08 still failing (V10 + V11 failed)

V12 (commit 5df838f) still MATERIAL-GAPS-caliber (no DR audit run)
but achieved breakthroughs:
- 5 sections (M-25b retry hardening worked)
- 35 citations, 45 verified, 1590 words
- T1+T2 = 71.4%
- Qwen 4 GOOD + 1 ACCEPTABLE
- PT08 STILL failed (V12 was 3rd consecutive round)

Root cause of PT08 deadlock identified: scripts/run_honest_sweep_r3.py
line 1073 replaced per-contradiction enumeration with an M-22
narrative paragraph to placate Codex's "mechanical list" complaint.
But PT08 evaluator requires `subject` AND `predicate` substrings to
appear verbatim in report text. Narrative dropped the literal
"body weight (10 mg)" strings.

M-25e (commit 451f382): restore per-flag enumeration BELOW the M-22
context paragraph:
  "Most are extraction artifacts... detector does NOT adjudicate...
   Per-flag enumeration (PT08 disclosure):
   - tirzepatide / body weight (10 mg): cited values range X to Y kg
     (source tiers: T1, T2)."

V13 result: **status=success, release_allowed=True**, 12/13 pass,
PT13 advisory only. First successful release after 6 MATERIAL-GAPS
iterations.

V13 launch: scripts/run_full_scale_v10.py at commit 451f382
  - Same capacity knobs
  - Output: outputs/full_scale_v13/clinical/clinical_tirzepatide_t2dm/

── V13 RESULT SUMMARY (for context, verify independently) ────────

status=success, release_allowed=True, class=pass
corpus: 310 sources, T1=18%, T2=14%, T4=39%, T7=23%
generation: 5 sections, 1474 words, 44 verified, 26 dropped
bibliography: 26 unique cited entries. T1=16, T2=6, T4=2, T6=1, T7=1
              → T1+T2 = 84.6%
evaluator: 12/13 rule checks pass, PT13 unhedged "superior" is
           advisory-only (non-gating)
qwen_judge: 4 GOOD + 1 ACCEPTABLE (hedging_appropriateness:
           "Claims are presented with citations but lack explicit
           hedging for numeric discrepancies")
strict_verify: 44 verified / 26 dropped / 70 total

── YOUR TASK ────────────────────────────────────────────────────

V13 output files:
  outputs/full_scale_v13/clinical/clinical_tirzepatide_t2dm/
    - report.md (~1474 words, 5 sections + limitations + contradictions)
    - bibliography.json (26 unique entries)
    - manifest.json (status=success, release_allowed=True)
    - run_log.txt
    - verification_details.json
    - qwen_judge_output.json (4 GOOD + 1 ACCEPTABLE)
    - contradictions.json (13 entries)

Audit order:

1. Read manifest.json, qwen_judge_output.json, evaluator rule
   checks. Confirm status=success, release_allowed=True.

2. Read bibliography.json in full. Count unique citations by tier
   and publisher. V13 claims T1+T2 = 84.6% — verify independently.

3. **LIVE-DOI CITATION AUDIT** (user mandate):
   Audit ALL 26 cited entries with live source fetch.
   - Pay specific attention to SURPASS-2 (citation [17] NEJM),
     SURPASS-3 ([21] Lancet), SURPASS-CVOT ([29] NEJM) —
     these are the primary RCTs V13 should anchor on.
   - Verify any trial-name binding (SURPASS-N, SURMOUNT-N) is
     correct (M-25a trial gate should have caught any mismatches).
   - Check if any non-tirzepatide evidence leaked into safety/
     efficacy sections (M-25c scope gate NOT YET implemented —
     this is a leading candidate for next iteration if found).

4. Read report.md cover to cover, line by line. Check:
   (a) Argumentation: evidence INTEGRATED or listed?
   (b) Quantification: plain-English + numerics?
   (c) Scope fidelity: T2D adult focus maintained?
   (d) Contradictions: now enumerated per M-25e — are they
       disclosed enough, or now too mechanical?
   (e) Structural hallucinations: 5 sections within scope template?
   (f) PT13 unhedged superlatives: what's the context — valid
       source-attributed language or genuine overreach?

5. Make the verdict call.

Write your findings to:
  outputs/codex_findings/dr_output_pass_6/findings.md

Required frontmatter:
---
verdict: TOP-TIER-DR-ACHIEVED | MATERIAL-GAPS-FIX-AND-RESWEEP | DIRECTIONAL-ONLY
pass: dr_output_pass_6_tirzepatide_v13
commit: 451f382
delta_vs_pass5: <summary of M-25e + V12/V13 cumulative impact>
citations_verified: <int live-fetched>/<int total cited>
citations_faithful: <int>
citations_fabricated: <int>
citations_embellished: <int>
citations_unverifiable: <int>
t1_t2_percentage_of_bibliography: <percent>
t7_percentage_of_bibliography: <percent>
live_fetch_method_used: <WebFetch | Unpaywall+Fetch | mixed>
faithfulness_verdict: <>
coverage_gaps_remaining: [<>]
structural_hallucinations: [<>]
quantification_quality: <>
contradiction_handling: <>
pt13_superlative_context: <is "superior" here a valid source paraphrase or overreach?>
m25_cumulative_impact: <a/b/e — what delivered, what didn't>
vs_gpt54_dr_verdict: <>
vs_gemini31_pro_dr_verdict: <>
rationale: |
  <>
---

Then body:
**Verdict**
**Quantitative V13 vs V11 vs V10 Summary**
**Citation Live-Fetch Audit Table (ALL 26 citations)**
**Criterion-by-criterion** (a-h)
**M-25 Impact Assessment** (a/b/e cumulative)
**Remaining DR Gaps** (if any)
**STOP or CONTINUE decision** (if STOP, explicit justification)

Verdict definitions (unchanged):
  TOP-TIER-DR-ACHIEVED: V13 meets or exceeds GPT-5.4 DR / Gemini
    3.1 Pro DR on all 8 criteria. Live-fetch confirms >95%
    FAITHFUL. STOP the auto-loop.
  MATERIAL-GAPS-FIX-AND-RESWEEP: substantive defects remain.
  DIRECTIONAL-ONLY: directionally correct, not DR-grade.

V13 is the first sweep to pass the pipeline's own release gate. If
you judge it TOP-TIER-DR-ACHIEVED the loop terminates per the
user's directive. Be uncompromising but honest.
