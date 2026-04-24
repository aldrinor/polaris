You are doing a deep line-by-line comparison of three research reports
answering the SAME clinical question, plus cross-checking Claude's
parallel read of the same materials. This is NOT a metadata audit,
NOT a pattern-matching exercise, NOT cherry-picking.

USER MANDATE (direct quote): "do a line by line comparison, not just
compare the metadata, or pattern finding, you and codex must do a
very in-depth comparison, and think deeply, and cross check which
others, and give me the solid plan to move forwards. Remember, we
cannot hard code it to get a narrow win, we need to make sure it is
going to be generalized for many different kinds of queries"

## Three reports to compare

All three answer:
"What is the efficacy and safety of tirzepatide for glycemic control
and weight loss in adults with type 2 diabetes?"

1. **POLARIS V17** (our pipeline, released at commit `14b50a9`)
   - File: `outputs/full_scale_v17/clinical/clinical_tirzepatide_t2dm/report.md`
   - Bibliography: `outputs/full_scale_v17/clinical/clinical_tirzepatide_t2dm/bibliography.json`
   - 2077 words, 5 sections, 24 unique cites, 68 citation markers
   - You audited this at pass 8 and verdicted TOP-TIER-DR-ACHIEVED

2. **ChatGPT Deep Research** (tier-1 competitor)
   - File: `state/compare_chatgpt_dr.txt` (PDF extracted to text)
   - 4830 words, 21 unique URLs, 14 domains
   - Includes comparison tables, FDA/EMA label, pi.lilly.com prescribing info

3. **Gemini 3.1 Pro Deep Research** (tier-1 competitor)
   - File: `state/compare_gemini_dr.txt` (PDF extracted to text)
   - 6835 words, 43 unique URLs, 21 domains
   - Includes per-trial sub-sections, Health Canada + FDA + clinicaltrials.gov

## What you must do

### Part 1 — Line-by-line read of all three

Read each report COVER TO COVER. For each one, take notes on:

- **Structural pattern**: how is the report organized? (topic vs trial vs drug-attribute vs chronology)
- **Claim architecture**: how does a typical claim sentence get built? (trial name → design → N → baseline → endpoint → result → comparator)
- **Citation binding**: does each claim cite the PRIMARY publication, or a secondary review? When multiple citations support one claim, how are they chosen?
- **Hedging grammar**: how is uncertainty conveyed? ("In one trial", "pooled across", "modeled to", "pre-specified subgroup")
- **Contradiction handling**: when sources disagree (e.g., conference abstract vs peer-reviewed paper on the same effect), how is it resolved?
- **Regulatory framing**: how are FDA boxed warnings, EMA SmPC, Health Canada alerts discussed? Jurisdiction-aware?
- **Quantification discipline**: do numbers come with 95% CI, p-values, baselines, endpoints? Or bare?
- **Transitions**: how does the report move between trials/topics? Is synthesis present or is it a list?

Don't summarize what you found in metadata terms ("V17 has 24 cites, Gemini has 43"). Describe what the prose ACTUALLY does differently.

### Part 2 — Specific line-level comparisons (at least 10)

For each of these specific claim-types, pick the corresponding sentence/
paragraph in ALL THREE reports and compare side-by-side:

1. SURPASS-1 monotherapy efficacy result
2. SURPASS-2 head-to-head vs semaglutide efficacy
3. SURPASS-3 vs insulin degludec
4. SURPASS-4 high-CV-risk cohort
5. SURPASS-5 / SURPASS-6 (adjunct to basal insulin)
6. GI adverse events (most common + rates by dose)
7. Hypoglycemia risk (unadjunctive)
8. MTC / thyroid C-cell tumors and boxed warning
9. Pancreatitis / gallbladder signal
10. Cardiovascular outcomes (SURPASS-CVOT)

For EACH: which report is deepest/most rigorous? Which is thinnest?
What SPECIFIC line or missing line in V17 is the gap?

### Part 3 — Cross-check Claude's analysis

Claude's comparison is at `state/v17_vs_tier1_headtohead.md`. Read it
end-to-end. For each claim Claude made:

- Do you AGREE based on your own read? If yes, note.
- Do you DISAGREE? Cite the specific line in Gemini/ChatGPT/V17 that
  contradicts Claude's claim.
- Did Claude MISS something material that line-by-line reading shows?

Be independent. Do not defer to Claude's framing.

### Part 4 — Generalizable fix proposals

CRITICAL CONSTRAINT: "we cannot hard code it to get a narrow win,
we need to make sure it is going to be generalized for many different
kinds of queries"

That rules OUT:
- Hard-coded trial names (SURPASS, SURMOUNT, SELECT, LEADER...)
- Hard-coded drug lists (tirzepatide, semaglutide)
- Hard-coded clinical taxonomies (T2D, obesity, CV-risk cohorts)
- Domain-specific allowlists (pharma company URLs, journal specific)
- Hard-coded section titles tailored to clinical questions only
- Any rule that wouldn't work if the same pipeline answered a
  materials-science, energy-policy, or regulatory-compliance query

Propose fixes that are ABSTRACTIONS over the observed gaps. Examples
of the right level of abstraction:

- "retrieve regulatory primary sources for queries whose domain
  protocol specifies regulatory applicability" (not "add FDA to
  amplified queries")
- "outline generator should detect when the evidence pool has N+
  primary studies of a single type (trials, materials, policies)
  and emit one sub-section per primary source" (not "emit a
  SURPASS-1 sub-section if SURPASS-1 is in corpus")
- "claim-framing rule: for each primary-study citation, require
  baseline context fields derived from structured metadata" (not
  "require N, baseline HbA1c, diabetes duration")

For each proposed fix, state:
- What gap it closes (from parts 1-3)
- What abstraction level makes it generalizable
- What would break the generalization (e.g. a query where this fix
  fires but should not)
- Rough implementation location (retrieval / selector / outline
  prompt / section writer prompt / post-synthesis stage)
- Estimated risk to V17 baseline (low / medium / high)

### Part 5 — Ranked plan

Propose a plan of MAXIMUM 4 fixes, in order. Each fix must:
- Close a concrete line-by-line gap (not a speculation)
- Be generalizable (survives the Part 4 constraint)
- Not regress V17's pass-8 TOP-TIER verdict
- Have a measurable signal (what changes in V18 output tells us it
  worked)

If fewer than 4 fixes are justified by your read, propose fewer.
Don't pad.

## Output

Write your analysis to:
  `outputs/codex_findings/v17_vs_tier1_deep_comparison/findings.md`

Structure:
```
---
analysis_type: line_by_line_comparison
reports_compared: [POLARIS_V17, ChatGPT_DR, Gemini_31_Pro_DR]
cross_check_target: state/v17_vs_tier1_headtohead.md
---

## Part 1: Structural and stylistic patterns
   (one sub-section per report)

## Part 2: Line-level comparisons (10 claim-types)
   (for each: V17 quote, ChatGPT quote, Gemini quote, delta)

## Part 3: Cross-check of Claude's analysis
   (agree / disagree / missing)

## Part 4: Generalizable fix proposals
   (each fix: gap, abstraction, break-cases, location, risk)

## Part 5: Ranked plan (≤4 fixes)
```

Be uncompromising about the generalization constraint. If a fix
looks good but would only work for clinical queries, flag that as a
break-case and propose a broader abstraction.

Claude is doing the same exercise independently. When you return,
Claude will cross-check your findings against its own. Disagreements
will be reconciled before any fix is committed.
