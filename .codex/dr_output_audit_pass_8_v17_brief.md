You are running Codex DR_output_audit_pass_8 as the FINAL JUDGE in
the Claude↔Codex auto-loop. Continuing from pass 7 (MATERIAL-GAPS on
V16). V17 applies M-25a pass-7 hardening and is the FIRST run to
achieve clean `status=success + release_allowed=True + eval_gate
reasons=[] empty` with 13/13 rule checks passing.

── CRITICAL AUDIT DISCIPLINE (USER MANDATE) ───────────────────────
Direct quote: "he must not use pattern finding, and cherry picking,
he must need to read every line to really determine whether the
quality is up to standard."

Live-fetch mandate remains. For sampled citations:
1. Open report.md, read the sentence containing the citation.
2. Open bibliography.json, find the cited entry's URL and DOI.
3. FETCH the source live via WebFetch or DOI resolution.
4. Read at least 500 chars of source body text.
5. Compare claim VERBATIM.
6. Verdict: FAITHFUL / FABRICATED / EMBELLISHED / UNVERIFIABLE.

Audit all 24 cited entries. V17 has 32 verified sentences and 68
citation markers.

── CONTEXT: DR PASS 7 → M-25a HARDENING → V17 ──────────────────

Pass 7 (V16, commit 16ee8c7): MATERIAL-GAPS
- 23 FAITHFUL / 1 FABRICATED / 1 EMBELLISHED / 5 UNVERIFIABLE
- Blocker fabrication: "In SURMOUNT-1, MTD of tirzepatide led to
  -20.9% at 72 weeks..." cited to ev_015 (SURMOUNT-3 Nature paper)

Root cause: M-25a `_trial_names_in_evidence` scanned direct_quote,
which for the SURMOUNT-3 paper mentions SURMOUNT-1 as a prior
reference. Gate saw SURMOUNT-1 in evidence text, passed binding.

**M-25a hardening (commit 14b50a9)**: restricted trial-name match
to statement + title (authoritative identity fields). direct_quote
excluded — it's too permissive. New regression test reproduces
pass-7 defect and verifies the fix.

V17 launch: scripts/run_full_scale_v10.py at commit 14b50a9

── V17 RESULT SUMMARY ───────────────────────────────────────────

status=success, release_allowed=True, class=pass
**eval_gate reasons=[] EMPTY** — first run with zero advisory flags
13/13 rule checks pass (PT13 also passed this time)
corpus: 310 sources, T1=20%, T2=13%, T4=38%, T7=24%
generation: 5 sections, **1098 words**, **32 verified**, 27 dropped
bibliography: **24 unique cited entries**, T1=12, T2=5, T4=6, T7=1
             → **T1+T2 = 70.8%**
Citation markers: 68 total, **2.12/sentence** (V16: 1.83, V13: ~1.0)
qwen_judge: 4 GOOD + 1 NEEDS_REVISION (hedging_appropriateness)
strict_verify drops: trial_name_mismatch=13 (V16: 7; hardening bit),
                     number_not_in_any_span=17, no_integer_overlap=5,
                     no_content_word_overlap=2

Trade-off: stricter gate dropped more sentences (59 total vs V16's
82 = 72% vs 66% retention), but should have zero trial-binding
fabrications.

── YOUR TASK ───────────────────────────────────────────────────

V17 output files:
  outputs/full_scale_v17/clinical/clinical_tirzepatide_t2dm/

Audit order:

1. Read manifest.json + run_log.txt. Confirm eval_gate.reasons=[]
   empty. Confirm 13/13 rule checks pass.

2. Read bibliography.json. Count by tier/publisher. T1+T2 at 70.8%
   is lower than V13's 84.6% but still strong. Is tier mix acceptable?

3. **LIVE-FETCH ALL 24 CITATIONS**. Categorize:
   - FAITHFUL / FABRICATED / EMBELLISHED / UNVERIFIABLE
   - Pay specific attention to SURPASS/SURMOUNT trial bindings
     (M-25a hardening should prevent pass-7 class defect)
   - Flag any new regression not caught by the hardening

4. Read report.md. Check the usual criteria (a-h).

5. VERDICT CALL. If:
   - 95%+ FAITHFUL live-fetch
   - 0 FABRICATED
   - Eval gate clean
   - Coverage acceptable for DR-grade clinical report
   → TOP-TIER-DR-ACHIEVED (STOP the loop)

Write findings to:
  outputs/codex_findings/dr_output_pass_8/findings.md

Required frontmatter:
---
verdict: TOP-TIER-DR-ACHIEVED | MATERIAL-GAPS-FIX-AND-RESWEEP | DIRECTIONAL-ONLY
pass: dr_output_pass_8_tirzepatide_v17
commit: 14b50a9
delta_vs_pass7: <V17 vs V16 on citations, words, FAITHFUL rate>
citations_verified: <int>/<24>
citations_faithful: <int>
citations_fabricated: <int>
citations_embellished: <int>
citations_unverifiable: <int>
citation_markers_total: 68
citation_markers_per_sentence: 2.12
t1_t2_percentage_of_bibliography: 70.8
t7_percentage_of_bibliography: <int>
faithfulness_verdict: <>
m25a_hardening_effective: <did pass-7 class fabrications recur or close?>
coverage_gaps_remaining: [<>]
vs_gpt54_dr_verdict: <>
vs_gemini31_pro_dr_verdict: <>
rationale: |
  <>
---

Body: Verdict; V17 vs V13 vs V16 table; Citation Live-Fetch Audit
Table for all 24; Criterion-by-criterion; M-25a hardening impact;
Remaining gaps; STOP or CONTINUE decision.

If V17 is TOP-TIER-DR-ACHIEVED, this terminates the autonomous
loop per the user directive. Be uncompromising but honest.
