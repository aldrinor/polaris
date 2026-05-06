You are running Codex DR_output_audit_pass_5 as the FINAL JUDGE in
the Claude↔Codex auto-loop. Continuing from pass 4 (MATERIAL-GAPS).
This audit determines whether POLARIS pipeline A V11 output meets
top-tier Deep Research quality (OpenAI GPT-5.4 DR / Gemini 3.1 Pro
DR level) or requires more iteration.

── CRITICAL AUDIT DISCIPLINE (USER MANDATE) ───────────────────────
Direct quote: "he must not use pattern finding, and cherry picking,
he must need to read every line to really determine whether the
quality is up to standard."

User question raised 2026-04-19 and enforced from pass 4 onward:
"Did Codex really audit the output content line-by-line, or just
use metadata?" This audit continues the live-fetch mandate.

Specifically, for EACH of the 12+ sampled citations below, you MUST
do ALL of the following:

1. Open report.md, read the sentence containing the citation.
2. Open bibliography.json, find the cited entry's URL and DOI.
3. FETCH the source live via either:
     - WebFetch tool, passing the URL
     - For DOI-bearing sources: fetch doi.org/{DOI} and follow
       the final resolved URL
4. Read at least 500 chars of the source BODY TEXT (not HTML head).
5. Compare the report sentence's quantitative claim to the source
   text VERBATIM.
6. Categorize each citation as:
     - FAITHFUL   — claim supported by source text
     - FABRICATED — source text doesn't contain the claim
     - EMBELLISHED — source has the topic but a weaker or
       different claim than the sentence
     - UNVERIFIABLE — source behind paywall and no OA available

Report has only 12 cited entries; audit ALL 12 (or as many
citation-bearing sentences as exist — V11 has 20 verified sentences,
many share citations).

── CONTEXT: DR PASS 4 → M-25 → V11 ───────────────────────────────

DR pass 4 (V10, commit ff68b86) verdict: MATERIAL-GAPS.
Live-fetch result: 18 FAITHFUL / 1 FABRICATED / 1 EMBELLISHED / 4
UNVERIFIABLE of 24 citation-bearing sentences.

The FABRICATED defect: sentence "SURMOUNT-1 tirzepatide 15 mg achieved
>=20% body-weight reduction in 20.9% of participants at 72 weeks
versus 3.1% placebo" was bound to ev_015 whose title is
"Tirzepatide after intensive lifestyle intervention: the SURMOUNT-3
phase 3 trial". strict_verify passed because numbers incidentally
appeared in SURMOUNT-3 span body and content words {tirzepatide,
surmount} overlapped.

The EMBELLISHED defect: Safety section imported ev_9 (Nature paper
s41467-026-71080-0) describing a PG-102 phase I bispecific GLP-1/GLP-2
agonist — NOT tirzepatide.

Between V10 and V11, Claude implemented:

**M-25a (trial-name match)** — commit 59b8f4a:
- New extract_trial_names() helper in provenance_generator.py
- Matches SURPASS-N, SURMOUNT-N, STEP-N, SURMOUNT-CN/OSA/AP/J/MMO
  numbered trials and ALLCAPS named programs (SELECT, LEADER,
  SUSTAIN, PIONEER, REWIND, AWARD, GRADE) as atomic tokens
- verify_sentence_provenance adds trial_name_mismatch failure when
  sentence names trial T but no cited evidence row's
  statement/direct_quote/title mentions T
- Sentences without named trials are not gated by this check
  (backward-compatible)
- 13 unit tests including exact reproduction of DR pass-4 FABRICATED
  #20 (passing)

**M-25b (outline expand to 5)** — commit 59b8f4a:
- OUTLINE_SYSTEM_PROMPT changed from "3-5 sections" to "4-5, EXACTLY
  5 when corpus supports"
- Parser min still accepts 3 (backward-compat for small corpora)

V11 launch: scripts/run_full_scale_v10.py at commit 59b8f4a
  - Same capacity knobs as V10
  - Output: outputs/full_scale_v11/clinical/clinical_tirzepatide_t2dm/
  - Suite: 667 passed at 59b8f4a

── V11 RESULT SUMMARY (for context, verify independently) ────────

status=abort_evaluator_critical, release_allowed=False
corpus: 312 sources, T1=19%, T2=14%, T4=41%, T7=21%
generation: 3 sections (Efficacy/Safety/Comparative), 710 words,
            20 verified, 13 dropped
bibliography: 12 unique cited entries
evaluator: 12/13 rule checks pass (PT08 fails on contradiction
           disclosure); PT11 now passes
qwen_judge: 5/5 GOOD (citation_tightness upgraded GOOD from
            V10's needs_revision)
strict_verify drops: trial_name_mismatch=1, number_not_in_any_span=11,
                     no_content_word_overlap=3, no_integer_overlap=1

── YOUR TASK ────────────────────────────────────────────────────

V11 output files:
  outputs/full_scale_v11/clinical/clinical_tirzepatide_t2dm/
    - report.md
    - bibliography.json
    - manifest.json
    - run_log.txt
    - verification_details.json
    - qwen_judge_output.json

Audit order:

1. Read manifest.json, qwen_judge_output.json, evaluator rule
   checks. Record status, release_allowed, qwen axes flagged.

2. Read bibliography.json in full. Count:
   - Total unique citations (12)
   - By tier
   - By publisher
   Are named SURPASS/SURMOUNT papers cited as primary T1 entries?

3. **LIVE-DOI CITATION AUDIT** (user mandate):
   Audit ALL 12 cited entries OR all 20 citation-bearing sentences.
   For EACH:
   a. Extract sentence + [N] marker
   b. Look up in bibliography.json → URL + DOI
   c. Fetch the source via WebFetch. If URL is paywalled: try
      Unpaywall. If still no OA, mark UNVERIFIABLE.
   d. Read body text; compare sentence claim verbatim
   e. Verdict: FAITHFUL / FABRICATED / EMBELLISHED / UNVERIFIABLE

   Pay specific attention to:
   - Any SURPASS/SURMOUNT trial mentions — is the cited source
     actually the named trial?
   - Any non-tirzepatide evidence sneaking into safety/efficacy
     sections?
   - Citation [9] (drugtopics.com, SURMOUNT-5) — is SURMOUNT-5
     real? Do the numbers match a verifiable source?

4. Read report.md cover to cover, line by line. Check:
   (a) Argumentation: evidence INTEGRATED or listed?
   (b) Quantification: plain-English + numerics?
   (c) Scope fidelity: T1D / obesity-only content properly flagged?
   (d) Contradictions: surfaced and adjudicated, or hidden?
   (e) Structural hallucinations: all headings within scope
       template?

5. Make the verdict call.

Write your findings to:
  outputs/codex_findings/dr_output_pass_5/findings.md

Required frontmatter:
---
verdict: TOP-TIER-DR-ACHIEVED | MATERIAL-GAPS-FIX-AND-RESWEEP | DIRECTIONAL-ONLY
pass: dr_output_pass_5_tirzepatide_v11
commit: 59b8f4a
delta_vs_pass4: <summary of M-25a/b impact>
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
vs_gpt54_dr_verdict: <>
vs_gemini31_pro_dr_verdict: <>
m25a_trial_gate_effective: <observed trial_name_mismatch drops, any remaining fabrications>
section_count: <3 sections observed — is this sufficient for DR?>
rationale: |
  <>
---

Then body:
**Verdict**
**Quantitative V11 vs V10 Summary**
**Citation Live-Fetch Audit Table (ALL 12+ citations)**
**Criterion-by-criterion** (a-h)
**M-25a + M-25b Impact Assessment**
**Remaining DR Gaps**
**Required Fix** (if not TOP-TIER-DR-ACHIEVED)

Verdict definitions:
  TOP-TIER-DR-ACHIEVED: V11 meets or exceeds GPT-5.4 DR / Gemini
    3.1 Pro DR on all 8 criteria. Live-fetch audit confirms >95%
    of sampled citations are FAITHFUL. STOP the auto-loop.
  MATERIAL-GAPS-FIX-AND-RESWEEP: specific substantive defects
    remain. Name them precisely.
  DIRECTIONAL-ONLY: directionally correct but not DR-grade.

Be UNCOMPROMISING but HONEST. If you skip live fetches for citation
N because of tool timeouts or paywalls, mark UNVERIFIABLE — don't
bluff them as FAITHFUL.
