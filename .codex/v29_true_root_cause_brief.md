You are Codex, giving brutally honest architectural diagnosis after
V29. User explicitly said "I don't want bandaid fix" — so we both
need to identify the TRUE root cause and non-band-aid fix.

## The puzzle

V28 and V29 landed IDENTICAL cross-reviewed scoreboards
(3 BEAT_BOTH + 0 BEAT_ONE + 4 LOSE_BOTH). §7 trigger #9 fired.
Our V28 diagnosis was "selector-to-generator custody fails for
primary papers". V29 fixed custody (M-51 hard-reserves primaries
into selected_rows, M-52 pulls from live_corpus into evidence_pool
when selector missed, M-53 diagnoses precisely per anchor). Yet
the dimensional outcome didn't budge.

V29 custody telemetry shows two distinct failure modes:

**A. Retrieval non-determinism (7/11 anchors)**:
V28 had SURPASS-4 (Del Prato Lancet 2021) and SURPASS-CVOT
(Nicholls NEJM 2025) primaries in live_corpus. V29, running
IDENTICAL M-48 first-author variant queries, did NOT land either.
Instead V29 landed SURPASS-1 primary (which V28 lacked). Serper/S2
results vary cycle-to-cycle for paywalled primary publications.

**B. Generator cite-rejection (4/11 anchors)**:
For SURPASS-1/4/5, M-51 + M-44 successfully put primary ev_ids
into section ev_ids lists. The LLM DID NOT cite them. The
injected ev_ids never reached the bibliography. M-44 validator
is empty (0 violations) because the LLM never named the trials
by short-name in prose, so the same-sentence check has nothing
to enforce.

## The deeper question

Our V28 fix-plan diagnosed "pipeline-ordering" and Strategy β said
"invert the order, do primary-skeleton-first, enrichment-second".
V29 implemented a NARROW version of that (selector custody only).
It didn't work at the dimension level.

**Is the true root cause even deeper?**

My honest read: POLARIS is CORPUS-DRIVEN, not FRAME-DRIVEN.

- Competitors (ChatGPT, Gemini) appear to start from an editorial
  frame baked into their training / editing process: "for a
  tirzepatide/T2D review, the frame is SURPASS-1..6 + SURPASS-CVOT
  + SURMOUNT-2 primaries + Mechanism clamp + FDA/EMA/NICE/HC
  regulatory". The frame exists BEFORE any evidence retrieval.
  Evidence fills the frame; if evidence doesn't fill a slot, the
  competitor writes "limited evidence" rather than omitting the
  frame element.

- POLARIS retrieves broadly, classifies by tier, selects by
  relevance score, and the GENERATOR EMERGES a frame from whatever
  landed in evidence_pool. Different corpus → different frame.

This explains BOTH V29 failure modes:
- Defect A exists because POLARIS has no frame to retrieve
  deterministically toward. It fires keyword + anchor queries and
  accepts what Serper returns. Result: non-deterministic primary
  custody.
- Defect B exists because the LLM, given an evidence subset and
  no frame, picks WHATEVER is most relevant to the section topic
  — which is often a T4 review or meta-analysis that scores higher
  than a T1 primary on lexical match to the section heading text.
  The LLM has no "this trial MUST be reported with these 7 fields"
  mandate; it has "cite what's relevant".

## The honest fix (non-band-aid)

Make POLARIS frame-driven, not corpus-driven:

### Frame definition

For a research question, define the FRAME before retrieval:

```yaml
frame:
  pivotal_trials:  # each must be present; "limited data" acceptable
    - anchor: SURPASS-1
      primary_doi: 10.1016/S0140-6736(21)01324-6  # Rosenstock Lancet 2021
      required_fields: [N, population, comparator, endpoint, timepoint, ETD, uncertainty]
    - anchor: SURPASS-2
      primary_doi: 10.1056/NEJMoa2107519  # Frías NEJM 2021
      required_fields: [...]
    ...
  mechanism_primary:
    - doi: 10.1016/S2213-8587(22)00041-1  # Thomas Lancet D&E 2022
      required_fields: [M-value, insulin_secretion_rate, half-life, ...]
  regulatory_sources:
    - jurisdiction: FDA
      host: accessdata.fda.gov
      required: [boxed_warning, indications, contraindications]
    ...
```

### Stage 1: frame-first retrieval

For each DOI in frame.pivotal_trials, call CrossRef/Unpaywall/PubMed
for DIRECT document fetch. Bypass Serper/S2 keyword retrieval for
known primaries. This eliminates Defect A (non-determinism).

If DOI fetch fails (paywall, 404), record EXPLICITLY as
frame-gap-unrecoverable. Don't silently fail.

### Stage 2: frame-first outline

The outline planner consumes the frame. Each frame element becomes
a required section or subsection slot:
- Efficacy section: per-trial subsection for each pivotal trial in
  frame.pivotal_trials that successfully retrieved.
- Mechanism section: if frame.mechanism_primary retrieved, that
  paper's direct_quote drives the section's quantitative content.
- Regulatory section: one paragraph per jurisdiction present in
  frame.regulatory_sources.

### Stage 3: frame-bound generation

Section prompt includes frame-element assignment. Example for
per-trial subsection:

```
You are writing the SURPASS-2 subsection. The primary publication
is ev_frás_nejm. You MUST:
1. Report N (1879), baseline HbA1c (8.28%), comparator (semaglutide 1 mg).
2. Report primary endpoint HbA1c change at week 40.
3. Report ETDs −0.15 / −0.39 / −0.45 for 5 / 10 / 15 mg doses WITH CIs.
4. Cite [ev_frás_nejm] for each numeric claim.
5. Mention open-label design and Eli Lilly sponsorship.
Do not write the subsection if you cannot extract these from
ev_frás_nejm's direct_quote.
```

The LLM no longer picks from a relevance-ordered subset; it fills a
specified slot from a specified evidence row. This eliminates
Defect B (cite-rejection).

### Stage 4: enrichment

After frame-bound sections complete, run existing POLARIS tier-
balanced retrieval + selector + generator to ENRICH the frame-bound
skeleton with meta-analyses, reviews, real-world studies, and any
retrieval-surfaced primaries NOT in the frame. This is where
POLARIS's transparency + tier discipline + contradiction detection
continue to shine — but in the enrichment layer, not the
frame-bound spine.

## Three-step frame-driven architecture

- **Frame (YAML)**: per-question scope template extended with
  pivotal-trial DOIs + mechanism DOIs + regulatory hosts-per-
  jurisdiction.
- **Frame-bound retrieval**: CrossRef DOI fetch for trials + PubMed
  for mechanism + existing regulatory_expander. Reliable, deterministic.
- **Frame-bound generator**: outline planner gates sections on
  retrieved-frame coverage; each section's prompt binds to a
  specific frame-element.

Post-frame: existing M-42 bundle + M-44/45/47/50 runs as enrichment
atop the frame.

## My honest questions for you

1. **Is "frame-driven" the true root cause diagnosis, or am I
   still missing something deeper?** Consider honestly:
   - Is the real issue that POLARIS has strict_verify, which only
     works on retrieved content — so any frame-element whose
     content can't be retrieved (paywalled NEJM PDF) fails the
     gate and gets dropped, regardless of architecture? Is
     strict_verify itself the wall?
   - Is this really achievable autonomously, or does "highest
     quality" for clinical research reports fundamentally require
     licensed access to primary papers that POLARIS can't
     institutionally obtain?

2. **Frame-driven architecture cost estimate**: my gut says 10-15
   days engineering (frame YAML schema, CrossRef/Unpaywall
   retrieval, outline-planner frame integration, prompt rewrites
   for frame-bound generation, test coverage). Does that match
   your sense?

3. **Would frame-driven architecture actually hit 7/7 BEAT_BOTH,
   or are some dimensions (e.g. Narrative depth) fundamentally
   harder than that?** Specifically: can a pipeline using only
   retrieved content match Gemini's clamp-study extraction when
   the clamp paper is paywalled on Lancet D&E?

4. **Non-band-aid alternative**: is there a different architecture
   I'm not seeing? E.g. hybrid retrieval (POLARIS for
   regulatory/transparency, human-in-loop for primary trials)?
   Or fundamentally accept that POLARIS cannot be a ChatGPT-DR
   replacement for clinical and position it as a
   complementary/transparency tool?

## Output format

500-1000 words max. Be direct. Pick a position, defend it. No
"it depends" hedging. User wants actionable direction.

Write to `outputs/codex_findings/v29_true_root_cause/findings.md`.

## V2 protocol

Your diagnosis will be cross-reviewed against Claude's independent
take in `outputs/audits/v29/claude_true_root_cause.md` (written
in parallel). Disagreement is fine — lower-verdict-controls applies.
