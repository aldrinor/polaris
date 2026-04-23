# Claude's True Root Cause Diagnosis — V29 post-mortem

## What we learned from V28 → V29 (not a band-aid)

V28 diagnosis: "primary papers in live_corpus but dropped by
selector". V29 fix: M-51 hard-reserves primaries + M-52 pulls from
corpus + M-53 diagnoses precisely. **Result: same 3 BB + 0 BO + 4 LB
scoreboard.** Our V28 diagnosis was wrong, or at least incomplete.

V29 custody telemetry gives a sharper picture:
- 7/11 anchors failed at retrieval: V29's Serper/S2 returned a
  different set of primaries than V28's. Same queries, different
  results. SURPASS-4 (Del Prato) and SURPASS-CVOT (Nicholls) were
  in V28 corpus, not V29. SURPASS-1 was in V29 corpus, not V28.
- 4/11 anchors made it through M-51/M-44 but the LLM DID NOT CITE
  the injected ev_ids. They never reached bibliography.

These are two distinct failure modes, but they share one deeper
structural characteristic: **POLARIS is corpus-driven, not
frame-driven**.

## The root cause

Competitors (ChatGPT DR, Gemini DR) have an editorial frame baked
into them. "For a tirzepatide T2D review, the frame is SURPASS-1..6
+ SURPASS-CVOT + SURMOUNT-2 primaries + mechanism clamp paper +
FDA/EMA/NICE/HC." This frame exists BEFORE retrieval. Evidence fills
the frame's slots; slots that can't be filled get "limited evidence"
language, not omission.

POLARIS retrieves, scores, selects, and the generator emerges a
frame from whatever landed in evidence_pool. The frame is an
OUTPUT of the pipeline, not an INPUT. Different corpus → different
frame every cycle.

This explains BOTH V29 failure modes:

**Defect A (retrieval variance)**: POLARIS has no frame to
retrieve deterministically toward. M-48 variant queries fire
Serper/S2 and accept results. Result: non-deterministic primary
custody across cycles.

**Defect B (cite-rejection)**: Given an evidence subset and no
frame, the LLM picks whatever's most relevant to section heading
text — typically T4 reviews or T2 meta-analyses with stronger
lexical match to "Efficacy" / "Safety" than a dense T1 primary-
paper quote. M-44 injection puts primaries IN the subset; it
doesn't FORCE citation. The LLM picks from the subset.

Our V28 Strategy β diagnosis talked about "two-stage generator
primary-first skeleton". V29 did a narrow version (custody-only,
keeping the relevance scorer in control). It was correctly identified
as a direction but too narrow in scope. The REAL architecture change
is upstream of the selector.

## Three-layer frame-driven architecture (non-band-aid fix)

### Layer 1: Frame definition (YAML, per research question)

Extend `config/scope_templates/clinical.yaml` with a new
`frame` section:

```yaml
frame:
  pivotal_trials:
    - anchor: SURPASS-2
      primary_doi: 10.1056/NEJMoa2107519   # Frías NEJM 2021
      primary_pmid: 34010531
      required_fields:
        - N
        - comparator
        - baseline_hba1c
        - primary_endpoint
        - timepoint
        - etd_with_uncertainty
        - safety_signal
    - anchor: SURPASS-4
      primary_doi: 10.1016/S0140-6736(21)01443-4   # Del Prato Lancet 2021
      ...
    - anchor: SURPASS-CVOT
      primary_doi: ...  # Nicholls NEJM 2025 when published
      ...
  mechanism_primary:
    - doi: 10.1016/S2213-8587(22)00041-1   # Thomas L D&E 2022
      required_fields:
        - m_value_pct
        - insulin_secretion_rate
        - half_life
        - receptor_affinity_ratio
        - participant_n
  regulatory_sources:
    - jurisdiction: FDA
      required_docs: [mounjaro_label, zepbound_label, boxed_warning_source]
    - jurisdiction: EMA
      required_docs: [epar_mounjaro, spc_pediatric]
    - jurisdiction: NICE
      required_docs: [ta924_t2d, ta1026_obesity]
    - jurisdiction: HC
      required_docs: [product_monograph]
```

### Layer 2: Frame-first retrieval (deterministic)

New module `src/polaris_graph/retrieval/frame_fetcher.py`:

- For each pivotal_trial.primary_doi: call CrossRef `/works/{doi}`
  → metadata; then Unpaywall `/v2/{doi}` for OA PDF; if paywalled,
  PubMed `efetch` for abstract; if all fail, mark
  `frame_gap_unrecoverable: true` and continue.
- For mechanism_primary: same.
- For regulatory_sources: existing regulatory_expander per jurisdiction.

Output: `frame_retrieved_rows` list, each row tagged with
`frame_role: "pivotal_trial:SURPASS-2:primary"` etc.

These rows enter the evidence_pool BEFORE any Serper/S2 generic
retrieval. They carry `frame_required: true` flag.

### Layer 3: Frame-bound generation

Outline planner consumes the frame:
- Efficacy section decomposes into per-trial subsections for each
  `pivotal_trial` with `frame_gap_unrecoverable: false`.
- Mechanism section has a mandatory paragraph for each
  mechanism_primary that retrieved.
- Regulatory section has mandatory paragraph per jurisdiction with
  present docs.

Per-subsection prompt binds to a specific frame-element:

```
Write the SURPASS-2 subsection. Evidence row: ev_frás_nejm
(direct_quote below). You MUST extract and report:
- N (extract from direct_quote)
- baseline HbA1c
- comparator arm (semaglutide 1 mg)
- primary endpoint (HbA1c change at week 40)
- ETDs with 95% CI for 5/10/15 mg doses
- one safety signal
Every claim must cite [ev_frás_nejm]. If a required field can't be
extracted from direct_quote, write "<field not extractable from
primary publication available content>" verbatim.
```

The LLM no longer picks from a relevance-ordered subset. It fills a
specified slot from a specified row.

### Layer 4 (unchanged): Enrichment

After frame-bound sections complete, existing POLARIS machinery
(M-42 bundle + M-44/45/47/50) runs as ENRICHMENT: meta-analyses,
reviews, real-world studies, POLARIS-specific transparency
(contradiction detector, tier disclosure, per-sentence provenance).

POLARIS's current strengths (Regulatory breadth, Contradictions,
transparency) preserve into the enrichment layer. The frame-bound
skeleton provides the pivotal-primary spine POLARIS currently lacks.

## Honest risk assessment

### Risk 1: Paywalled primaries

Even with CrossRef + Unpaywall + PubMed, ~40-60% of Lancet / NEJM /
JAMA primaries are paywalled without institutional access. Best-case
POLARIS gets the abstract (200-400 words) via PubMed efetch, which
may not contain the full 95% CI for every dose. Frame-element
extraction will sometimes hit "field not extractable" boundaries.

Mitigation: the FRAME explicitly allows `field not extractable`
language rather than silent omission. This is GOOD epistemically —
transparent about primary-source reach. The report becomes more
honest about reach than ChatGPT/Gemini (which fabricate from
training memory when paywalled).

### Risk 2: Frame maintenance burden

Every research question needs its frame authored. For tirzepatide/T2D
it's ~12 trials + 1 mechanism paper + 4 regulatory jurisdictions.
Template authors become editorial curators, not just query designers.

Mitigation: this is actually a strength. Templates are version-
controlled; the frame encodes 2026-current expert consensus on
"what this clinical question's evidence base looks like".

### Risk 3: Engineering cost

Frame schema, CrossRef/Unpaywall/PubMed fetcher, outline-planner
frame integration, prompt rewrites for frame-bound subsections,
test coverage.

My honest estimate: **12-15 days engineering + 2-3 sweep cycles for
validation**. This is genuinely larger than V30 original scope.

### Risk 4: Is 7/7 BEAT_BOTH even achievable autonomously?

Honest answer: **probably not on Narrative depth** even with
frame-driven architecture. Gemini's Mechanism section draws on
material not publicly indexed (specific pharmacology reviews,
off-web sources). ChatGPT's trial table has uncertainty estimates
for every dose-timepoint cell that's extractable only from full-
text primaries.

Frame-driven architecture should lift POLARIS to **5-6 BB + 1-2
BO + 0 LB**. 7/7 BEAT_BOTH likely requires institutional primary
access (university subscription to Lancet/NEJM/JAMA), which is
infrastructure, not engineering.

## Non-architectural alternative to consider

**Complementary positioning**: POLARIS ships at 3 BB + 4 LB vs
competitors BUT WINS on axes competitors don't optimize:
- Transparent per-sentence provenance (unique)
- 4-jurisdiction regulatory breadth
- 14+ contradiction enumeration
- No fabrication from training memory

Position POLARIS as the RIGOROUS REFERENCE used alongside ChatGPT/
Gemini DR for verification, not a replacement. The "transparent
companion" framing. This is REAL VALUE even at 3 BB — no competitor
offers per-sentence ev_id provenance.

Zero further engineering; ship V28 (stronger structural artifacts
than V29) with explicit positioning.

## Recommendation

If user goal is **"highest quality autonomous report"**: commit to
frame-driven architecture (12-15 days). Projected 5-6 BB + 1-2 BO +
0 LB. Real, non-band-aid fix addressing the true root cause
(corpus-driven → frame-driven).

If user goal is **"highest honest value with current architecture"**:
complementary positioning. Ship V28 + clear positioning docs. Zero
further engineering. POLARIS becomes a verification companion.

If user goal is **"test the architecture hypothesis cheaply"**: run
V29's pipeline on a non-clinical question (e.g. materials chemistry,
ML benchmarking) to see if the primary-custody gap is clinical-
question-specific or fundamental. 1-2 days. Informs the frame-
driven investment decision.

My pick: **frame-driven architecture** if goal is true quality,
**complementary positioning** if goal is honest value-per-cost.
Both are real answers; neither is a band-aid.
