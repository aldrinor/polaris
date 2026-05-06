You are running Codex DR_output_audit_pass_4 as the FINAL JUDGE in
the Claude↔Codex auto-loop. Continuing from pass 3 (MATERIAL-GAPS).
This audit determines whether POLARIS pipeline A V10 output meets
top-tier Deep Research quality (OpenAI GPT-5.4 DR / Gemini 3.1 Pro
DR level) or requires more iteration.

── CRITICAL AUDIT DISCIPLINE (USER MANDATE — EXPANDED FOR PASS 4) ─
Direct quote: "he must not use pattern finding, and cherry picking,
he must need to read every line to really determine whether the
quality is up to standard."

New user question raised at 2026-04-19: "Did Codex really audit
the output content line-by-line, or just use metadata?"

THIS PASS MUST PROVE IT IS NOT METADATA-BASED.

Specifically, for EACH of the 20+ sampled citations below, you
MUST do ALL of the following:

1. Open report.md, read the sentence containing the citation.
2. Open bibliography.json, find the cited entry's URL and DOI.
3. FETCH the source live via either:
     - WebFetch tool, passing the URL
     - For DOI-bearing sources: fetch doi.org/{DOI} and follow
       the final resolved URL
4. Read at least 500 chars of the source BODY TEXT (not HTML head).
5. Compare the report sentence's quantitative claim to the source
   text VERBATIM. Example: if the sentence says "tirzepatide 15mg
   reduced HbA1c by 2.24% at 40 weeks [ev_023]", find the exact
   value in the fetched source. It must match or be a reasonable
   rounding of what the source says.
6. Categorize each citation as:
     - FAITHFUL   — claim supported by source text
     - FABRICATED — source text doesn't contain the claim
     - EMBELLISHED — source has the topic but a weaker or
       different claim than the sentence
     - UNVERIFIABLE — source behind paywall and no Unpaywall OA
       available. Note this as a coverage gap.

Your audit report MUST include a table with ALL 20+ citations
showing: sentence quote, source URL actually fetched, excerpt
from source supporting/contradicting claim, verdict.

If you cannot fetch the source for N citations, EXPLICITLY SAY SO.
Do NOT substitute metadata-based assessment ("bibliography says
T1 so I trust it"). That is exactly what the user is warning
against.

── CONTEXT: DR PASS 3 → M-20/M-22 → M-23 + M-24 → V10 ──────────

DR pass 3 (V6, commit 35a0bc2) verdict: MATERIAL-GAPS.
Primary gaps flagged:
- Citations count too low (~24 total for a DR report vs 50-200
  in GPT-5.4/Gemini DR-grade clinical reports)
- NEJM / Lancet SURPASS primary papers often returned paywall
  stubs (400-500 chars of "Subscribe to read" instead of article
  body)
- Contradiction handling sometimes mechanical

Between V6 and V10 the following were applied:

M-23 (commits 6c999e8 + ff68b86): access_bypass.py
- M-23a: Unpaywall step 0. For DOI-bearing URLs (NEJM, Lancet,
  JAMA, Elsevier, etc.), query api.unpaywall.org for legal OA
  PDFs. Preferred over publisher paywalled URLs.
- M-23b: Strip nav boilerplate BEFORE paywall detection (previously
  false-positived on 50K article bodies containing "Sign In" in
  footer).
- M-23c: Quality-scored winner selection. Concurrent Crawl4AI +
  Jina + Trafilatura — highest content-quality score wins, not
  first-success. Scorer combines length + structural markers
  (Abstract/Methods/Results/Conclusion) + numeric density.
- M-23d: HTTP-error stub detection (403/404/5xx). Jina proxies
  upstream errors as success=True with 200-500 char body — now
  detected as failed fetch.
- M-23e: Unpaywall PDF-preference. Only swap to OA URL when a
  PDF URL is available across all oa_locations — repository
  landing pages (figshare, etc.) that 403 on headless fetch are
  skipped.
- M-23f: Tighten paywall regex patterns. Old `sign.*in.*to.*access`
  was greedy and false-positived on 50K NEJM articles. Split into
  strict (always) and short-only (<2K chars) pattern lists.

M-24 (commit 6c999e8): multi_section_generator.py
- M-24a: OUTLINE_SYSTEM_PROMPT — removed "no overlap" rule. One
  SURPASS paper can now legitimately cite into BOTH Efficacy and
  Safety sections. Parser records overlap as info telemetry, not
  failure. Per-section target raised from ≥2 to ≥8 ev_ids (aim
  12-20).
- M-24b: SECTION_SYSTEM_PROMPT_TEMPLATE — sentence target raised
  from 6-10 → 10-18. Added citation diversity rule: ≥5 distinct
  sources per section.

V10 launch: scripts/run_full_scale_v10.py at commit ff68b86
  - PG_SWEEP_MAX_SERPER=50, MAX_S2=50, FETCH_CAP=500
  - PG_LIVE_MAX_EV_TO_GEN=600 (generator pool cap; was 400)
  - PG_MAX_COST_PER_RUN=10.00
  - PG_UNPAYWALL_ENABLED=1, PG_FIRECRAWL_ENABLED=0
  - Single query: clinical_tirzepatide_t2dm
  - Output: outputs/full_scale_v10/clinical/clinical_tirzepatide_t2dm/

── YOUR TASK ────────────────────────────────────────────────────

V10 output files:
  outputs/full_scale_v10/clinical/clinical_tirzepatide_t2dm/
    - report.md
    - bibliography.json (citations with URL + DOI per entry)
    - manifest.json (gate_class, release_allowed, tier_fractions)
    - run_log.txt (sweep execution log — check M-23a Unpaywall
      hit rate, M-23c winner selection, circuit-breaker events)
    - classified_urls.json (all URLs with tier/rule)
    - corpus_adequacy.json, completeness.json
    - verification_details.json (strict_verify per-sentence results)
    - qwen_judge_output.json (evaluator verdict + rubric scores)
    - contradictions.json

Audit order (NEW: STEP 3 IS EXPANDED WITH LIVE-FETCH VERIFICATION):

1. Read manifest.json, qwen_judge_output.json, evaluator rule
   checks. Record status, release_allowed, qwen axes flagged.

2. Read bibliography.json in full. Count:
   - Total unique citations
   - By tier: T1, T2, T3, T4, T5, T6, T7
   - By publisher: NEJM / Lancet / JAMA / Diabetes Care /
     PMC / FDA / other
   Are named SURPASS/SURMOUNT papers cited as primary T1 entries?

3. **LIVE-DOI CITATION AUDIT** (the user's mandate):
   Pick AT LEAST 25 citations spanning the full report — first 5
   sentences, mid-document, last 5 sentences, plus any
   quantitative claim (numbers / percentages / confidence
   intervals). For EACH:

   a. Extract sentence + [ev:N] token
   b. Look up ev:N in bibliography.json → URL + DOI
   c. Fetch the source via WebFetch. If the URL is paywalled:
      query api.unpaywall.org/v2/{doi}?email=anon@example.com
      for an OA copy, and fetch that instead. If still no OA
      available, mark UNVERIFIABLE (and note as a pipeline gap
      worth flagging — M-23 should have resolved more of these).
   d. Read the source's body text (abstract + first 2K of full
      text). Compare the sentence's claim to the source.
   e. Verdict: FAITHFUL / FABRICATED / EMBELLISHED / UNVERIFIABLE.

   Write all 25 verdicts into a table in the findings.

4. Read report.md cover to cover, line by line. Check:
   (a) Argumentation: evidence INTEGRATED or listed?
   (b) Quantification: plain-English + numerics? ("2.24% HbA1c
       reduction at 40 weeks" vs "significant improvement")
   (c) Scope fidelity: T1D / obesity-only content properly
       flagged as population mismatch where used?
   (d) Contradictions: surfaced and adjudicated, or hidden?
   (e) Structural hallucinations: all headings within scope
       template?

5. Make the verdict call. User demands top-tier DR or continue.

Write your findings to:
  outputs/codex_findings/dr_output_pass_4/findings.md

Required frontmatter:
---
verdict: TOP-TIER-DR-ACHIEVED | MATERIAL-GAPS-FIX-AND-RESWEEP | DIRECTIONAL-ONLY
pass: dr_output_pass_4_tirzepatide_v10
commit: ff68b86
delta_vs_pass3: <summary of M-23 + M-24 impact>
citations_verified: <int fetched live>/<int total cited>
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
rationale: |
  <>
---

Then body:
**Verdict**
**Quantitative V10 vs V6 Summary**
**Citation Live-Fetch Audit Table (≥25 citations with source excerpts)**
**Criterion-by-criterion** (a-h)
**M-23 + M-24 Impact Assessment**
  - Did Unpaywall hit rate rise? (check run_log.txt for M-23a logs)
  - Did Crawl4AI content length improve? (check M-23c winner
    selection logs)
  - Did citation count rise in line with M-24 prompt changes?
  - Did T1/T2 fraction hold?
**Remaining DR Gaps**
**Required Fix** (if not TOP-TIER-DR-ACHIEVED)

Verdict definitions:
  TOP-TIER-DR-ACHIEVED: V10 meets or exceeds GPT-5.4 DR / Gemini
    3.1 Pro DR on all 8 criteria. Live-fetch audit confirms >95%
    of sampled citations are FAITHFUL. STOP the auto-loop.
  MATERIAL-GAPS-FIX-AND-RESWEEP: specific substantive defects
    remain. Name them precisely.
  DIRECTIONAL-ONLY: directionally correct but not DR-grade.

Be UNCOMPROMISING but HONEST about what you actually did. If you
skipped live fetches for citation N because of tool timeouts or
paywalls, mark those UNVERIFIABLE — don't bluff them as FAITHFUL.
