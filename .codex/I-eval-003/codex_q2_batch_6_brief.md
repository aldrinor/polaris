Independent Tier-1 audit of 7 Q2 Canada-US CUSMA claims. Output YAML records only.

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

- Do NOT skip a claim. ALL 7 must have records.
- Do NOT auto-VERIFIED just because a span exists. Read the span_text and confirm the decimal is there.
- Do NOT exceed one paragraph of rationale per claim.

# Batch (the claims to audit are below; each has cited_evidence with span_text inline)

# Q2 batch 6: claims 36-42
schema_version: tier1_v2
claims:
  - claim_id: Q2-T1-036
    section: "Efficacy"
    sentence: "The review process requires the three governments, through the Free Trade Commission, to decide whether to extend CUSMA for a new 16-year term.[1][2]"
    cited_evidence:
      - evidence_id: ev_009
        bibliography_num: 1
        url: "https://www.csis.org/analysis/usmca-review-2026"
        tier: T4
        span: '0-500'
        title: "USMCA Review 2026 - CSIS"
        span_text: |
          USMCA Review 2026 Table of Contents - The Issue - Introduction - The USMCA at Five - President Trump’s Reindustrialization Drive Through Tariffs - Understanding the 2026 Review Clause: Pathways, Risks, and Leverage - Mapping Six Possible Pathways for the USMCA - What Will Be on the Table: Disputes, Demands, and Deal-Breakers - Keeping Sights High: Options to Deepen Cooperation Under the USMCA Available Downloads The Issue The United States–Mexico–Canada Agreement (USMCA), the backbone of North America’s competitiveness, will undergo a formal review starting in July 2026. What was once expected
      - evidence_id: ev_011
        bibliography_num: 2
        url: "https://www.fasken.com/en/knowledge/2025/10/2026-cusma-review-consultation"
        tier: UNKNOWN
        span: '0-500'
        title: "2026 CUSMA Review Consultation | Knowledge - Fasken"
        span_text: |
          In advance of the July 2026 joint review of the Canada-United States-Mexico Agreement (CUSMA) that will be held between Canada, Mexico, and the United States, Canada has opened formal public consultations on the operation of the CUSMA, providing an important opportunity for Canadians to help shape Canada’s negotiating positions. Given the instability in North American free trade under the Trump 2.0 Administration, the joint review has assumed central importance as a means for Canada to restore certainty to its key trade relationships, thus making the consultations all the more critical for Can
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-037
    section: "Efficacy"
    sentence: "However, the article leaves critical gaps, lacking explicit criteria for evaluating stakeholder proposals or prioritizing which suggestions will be considered.[1]"
    cited_evidence:
      - evidence_id: ev_009
        bibliography_num: 1
        url: "https://www.csis.org/analysis/usmca-review-2026"
        tier: T4
        span: '0-500'
        title: "USMCA Review 2026 - CSIS"
        span_text: |
          USMCA Review 2026 Table of Contents - The Issue - Introduction - The USMCA at Five - President Trump’s Reindustrialization Drive Through Tariffs - Understanding the 2026 Review Clause: Pathways, Risks, and Leverage - Mapping Six Possible Pathways for the USMCA - What Will Be on the Table: Disputes, Demands, and Deal-Breakers - Keeping Sights High: Options to Deepen Cooperation Under the USMCA Available Downloads The Issue The United States–Mexico–Canada Agreement (USMCA), the backbone of North America’s competitiveness, will undergo a formal review starting in July 2026. What was once expected
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-038
    section: "Efficacy"
    sentence: "Canada's approach appears cautious, with one analysis of Prime Minister Carney's early meeting with President Trump noting he carefully chose his words and left most of Trump's bluster unchallenged, suggesting a strategy of avoiding immediate confrontation.[11]"
    cited_evidence:
      - evidence_id: ev_003
        bibliography_num: 11
        url: "https://cdhowe.org/publication/urgency-and-caution-charting-a-careful-path-to-the-cusma-review/"
        tier: T4
        span: '0-500'
        title: "Urgency and Caution: Charting a Careful Path to the CUSMA Review"
        span_text: |
          [Home](https://cdhowe.org/) / [Publications](https://cdhowe.org/publication/) / [Research](https://cdhowe.org/publication-type/public-policy-research/) / Urgency and Caution: Charting a Careful Path to the CUSMA Review - [Media Releases](https://cdhowe.org/media-releases/) - Research - | Urgency and Caution: Charting a Careful Path to the CUSMA Review Summary: | Citation | Meredith Lilly. 2025. Urgency and Caution: Charting a Careful Path to the CUSMA Review. ###. Toronto: C.D. Howe Institute. | | Page Title: | Urgency and Caution: Charting a Careful Path to the CUSMA Review – C.D. Howe Instit
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-039
    section: "Efficacy"
    sentence: "This caution is likely warranted, as experts assess the U.S. will use the review process to apply maximum pressure on Canada, for example by demanding concessions to address the U.S. trade imbalance excluding hydrocarbons.[5]"
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

  - claim_id: Q2-T1-040
    section: "Efficacy"
    sentence: "Trade Representative's 2026 National Trade Estimate report, which outlines American trade concerns with Canada, is expected to play a significant role in setting the review's priorities.[8]"
    cited_evidence:
      - evidence_id: ev_004
        bibliography_num: 8
        url: "https://www.pwc.com/ca/en/services/tax/publications/tax-insights/preparing-cusma-2026-review.html"
        tier: T5
        span: '0-500'
        title: "Tax Insights: Preparing for the CUSMA 2026 review US trade ... - PwC"
        span_text: |
          Issue 2026-16 In brief What happened? The Canada‑United States‑Mexico Agreement (CUSMA) will have its first mandatory joint review on July 1, 2026, six years after its entry into force. While the review is not a comprehensive renegotiation of the agreement, it provides an opportunity for the parties to assess how CUSMA is functioning, consider recommendations for potential updates and influence how the agreement is administered and enforced, including whether targeted changes or commitments are pursued. On March 31, 2026, the Office of the United States Trade Representative (USTR) released its
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-041
    section: "Efficacy"
    sentence: "The strategic environment is highly uncertain, with President Trump having called CUSMA \"transitional\" and suggesting it may have served its purpose, undermining confidence in the agreement's future.[12]"
    cited_evidence:
      - evidence_id: ev_007
        bibliography_num: 12
        url: "https://www.cbc.ca/news/politics/cusma-review-2026-what-trump-wants-9.7026216"
        tier: UNKNOWN
        span: '0-500'
        title: "CUSMA is up for review in 2026, and here's what Trump might want"
        span_text: |
          CUSMA is up for review in 2026, and here's what Trump might want Canada and the U.S. will launch formal talks to review free-trade deal in mid-January A mandatory review of the Canada-U.S.-Mexico-Agreement on trade kicks into high gear next year as U.S. President Donald Trump continues his campaign to realign global trade and poach key industries from America's closest neighbours. Negotiations on the trade pact, better known as CUSMA, were a stress test for Ottawa during the first Trump administration. The trade talks were tense at times, but ultimately the pact that replaced the North America
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q2-T1-042
    section: "Efficacy"
    sentence: "One analysis warns that while a full U.S. withdrawal is considered far-fetched due to the economic self-harm, the threat itself could be used as political leverage.[5]"
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



# Output

Single YAML block. List of records in claim_id order. Then a summary:

```yaml
- claim_id: ...
  ...
- claim_id: ...
  ...

batch_summary:
  total: 7
  per_verdict: {VERIFIED: N, PARTIAL: N, UNSUPPORTED: N, FABRICATED: N, UNREACHABLE: N}
  per_context_match: {yes: N, partial: N, no: N}
  notable: ["..."]
```

Output the YAML directly. No commentary outside.
