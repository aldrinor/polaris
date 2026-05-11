Independent Tier-1 audit of 4 Q2 Canada-US CUSMA claims. Output YAML records only.

You are populating Tier-1 audit fields for each claim in the BATCH below.

# Tier-1 schema (per claim)

```yaml
- claim_id: Q2-T1-NNN
  claim_type: efficacy | safety | diagnostic | dosing | regulatory | mechanism | epidemiology | economic | guideline | background
  materiality: critical | major | minor | background
  citation_context_match: yes | partial | no
  verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
  rationale: "one sentence quoting or paraphrasing the span_text"
  reviewer_confidence: 0.0 - 1.0
```

# Decision rules

- **citation_context_match: yes** iff the decimal/year/range/figure in the claim is EXPLICITLY present in the cited span_text. **partial** if the span is on-topic and broadly consistent but the specific decimal is not in the visible span. **no** if the span is about a different topic.
- **materiality**:
  - critical = the headline policy-decision number (e.g., CUSMA July-2026 review trigger, USMCA dispute counts, tariff schedules, federal procurement thresholds)
  - major = supporting policy-decision-grade decimal
  - minor = supporting context decimal that policy decision would not turn on; ALSO repeated facts already cited elsewhere
  - background = pure framing
- **verdict**: VERIFIED requires citation_context_match=yes AND the claim is consistent with the span. PARTIAL covers framing/attribution issues even when decimals match. UNSUPPORTED covers cases where the span doesn't support the claim.
- **reviewer_confidence < 0.7 → flag for human deferral**.

# Banned shortcuts

- Do NOT skip a claim. ALL 4 must have records.
- Do NOT auto-VERIFIED just because a span exists. Read the span_text and confirm the decimal is there.
- Do NOT exceed one paragraph of rationale per claim.

# Batch (the claims to audit are below; each has cited_evidence with span_text inline)

# Q2 batch 7: claims 43-46
schema_version: tier1_v2
claims:
  - claim_id: Q2-T1-043
    section: "Efficacy"
    sentence: "In this context, Canada's stated strategy includes emphasizing areas of mutual advantage like critical minerals, where bilateral trade was valued at $95.6 billion in 2020, as a potential avenue for constructive engagement.[5]"
    cited_evidence:
      - evidence_id: ev_013
        bibliography_num: 5
        url: "https://www.cgai.ca/canadas_cusma_conundrum"
        tier: T4
        span: '0-500'
        title: "Canada's CUSMA Conundrum - Canadian Global Affairs Institute"
        span_text: |
          Image credit: Twitter/ @JustinTrudeau by [Lawrence L. Herman](Lawrence_Herman) December 2024 Table of Contents [Introduction](#Introduction)[End of the Special Relationship](#Relationship)[CUSMA Scenarios](#Scenarios)[Can CUSMA Be Kept in Play?](#CUSMA)[Bilateral Trade Outside of CUSMA](#Outside)[Conclusions – Avoiding the Cutting Room Floor](#Conclusions)[End Notes](#Endnotes)[About the Author](#Author)[Canadian Global Affairs Institute](#CGAI) Introduction Donald Trump’s egregious threat to impose 25 percent tariffs on all Canadian and Mexican imports shows the world that his administration 
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-044
    section: "Efficacy"
    sentence: "The overall efficacy of Canada's preparations is challenged by the high-stakes, unpredictable nature of dealing with an administration that one source states has signaled it \"will not be bound by America\u2019s treaty obligations\".[5]"
    cited_evidence:
      - evidence_id: ev_013
        bibliography_num: 5
        url: "https://www.cgai.ca/canadas_cusma_conundrum"
        tier: T4
        span: '0-500'
        title: "Canada's CUSMA Conundrum - Canadian Global Affairs Institute"
        span_text: |
          Image credit: Twitter/ @JustinTrudeau by [Lawrence L. Herman](Lawrence_Herman) December 2024 Table of Contents [Introduction](#Introduction)[End of the Special Relationship](#Relationship)[CUSMA Scenarios](#Scenarios)[Can CUSMA Be Kept in Play?](#CUSMA)[Bilateral Trade Outside of CUSMA](#Outside)[Conclusions – Avoiding the Cutting Room Floor](#Conclusions)[End Notes](#Endnotes)[About the Author](#Author)[Canadian Global Affairs Institute](#CGAI) Introduction Donald Trump’s egregious threat to impose 25 percent tariffs on all Canadian and Mexican imports shows the world that his administration 
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-045
    section: "Efficacy"
    sentence: "Consequently, while Canada is undertaking necessary procedural steps like consultations, the realism of its proposed negotiating strategies is severely tested by the prospect of extreme U.S. demands and the agreement's inherent vulnerability to political leverage in the review process.[1][5]"
    cited_evidence:
      - evidence_id: ev_009
        bibliography_num: 1
        url: "https://www.csis.org/analysis/usmca-review-2026"
        tier: T4
        span: '0-500'
        title: "USMCA Review 2026 - CSIS"
        span_text: |
          USMCA Review 2026 Table of Contents - The Issue - Introduction - The USMCA at Five - President Trump’s Reindustrialization Drive Through Tariffs - Understanding the 2026 Review Clause: Pathways, Risks, and Leverage - Mapping Six Possible Pathways for the USMCA - What Will Be on the Table: Disputes, Demands, and Deal-Breakers - Keeping Sights High: Options to Deepen Cooperation Under the USMCA Available Downloads The Issue The United States–Mexico–Canada Agreement (USMCA), the backbone of North America’s competitiveness, will undergo a formal review starting in July 2026. What was once expected
      - evidence_id: ev_013
        bibliography_num: 5
        url: "https://www.cgai.ca/canadas_cusma_conundrum"
        tier: T4
        span: '0-500'
        title: "Canada's CUSMA Conundrum - Canadian Global Affairs Institute"
        span_text: |
          Image credit: Twitter/ @JustinTrudeau by [Lawrence L. Herman](Lawrence_Herman) December 2024 Table of Contents [Introduction](#Introduction)[End of the Special Relationship](#Relationship)[CUSMA Scenarios](#Scenarios)[Can CUSMA Be Kept in Play?](#CUSMA)[Bilateral Trade Outside of CUSMA](#Outside)[Conclusions – Avoiding the Cutting Room Floor](#Conclusions)[End Notes](#Endnotes)[About the Author](#Author)[Canadian Global Affairs Institute](#CGAI) Introduction Donald Trump’s egregious threat to impose 25 percent tariffs on all Canadian and Mexican imports shows the world that his administration 
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-046
    section: "Efficacy"
    sentence: "Canada's preparations for the CUSMA review involve formal public consultations to shape its negotiating positions, recognizing the review's central importance for restoring trade certainty.[2]"
    cited_evidence:
      - evidence_id: ev_011
        bibliography_num: 2
        url: "https://www.fasken.com/en/knowledge/2025/10/2026-cusma-review-consultation"
        tier: UNKNOWN
        span: '0-500'
        title: "2026 CUSMA Review Consultation | Knowledge - Fasken"
        span_text: |
          In advance of the July 2026 joint review of the Canada-United States-Mexico Agreement (CUSMA) that will be held between Canada, Mexico, and the United States, Canada has opened formal public consultations on the operation of the CUSMA, providing an important opportunity for Canadians to help shape Canada’s negotiating positions. Given the instability in North American free trade under the Trump 2.0 Administration, the joint review has assumed central importance as a means for Canada to restore certainty to its key trade relationships, thus making the consultations all the more critical for Can
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence


# Output

Single YAML block. List of records in claim_id order. Then a summary:

```yaml
- claim_id: ...
  ...
- claim_id: ...
  ...

batch_summary:
  total: 4
  per_verdict: {VERIFIED: N, PARTIAL: N, UNSUPPORTED: N, FABRICATED: N, UNREACHABLE: N}
  per_context_match: {yes: N, partial: N, no: N}
  notable: ["..."]
```

Output the YAML directly. No commentary outside.
