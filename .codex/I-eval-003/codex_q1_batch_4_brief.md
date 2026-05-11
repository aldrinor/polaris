Independent Tier-1 audit of 7 Q1 AI Sovereignty claims. Output YAML records only.

You are populating Tier-1 audit fields for each claim in the BATCH below.

# Tier-1 schema (per claim)

```yaml
- claim_id: Q1-T1-NNN
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
  - critical = the headline policy-decision number (e.g., $2B Budget-2024 over 5y, 100MW data centre threshold, CAD $700M AI Compute Challenge, US CLOUD Act applicability)
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

# Q1 batch 4: claims 22-28
schema_version: tier1_v2
claims:
  - claim_id: Q1-T1-022
    section: "Efficacy"
    sentence: "The AI Sovereign Compute Infrastructure Program (SCIP) is intended to develop large-scale, Canadian-based compute infrastructure to form a core part of Canada\u2019s digital backbone.[9][1]"
    cited_evidence:
      - evidence_id: ev_013
        bibliography_num: 1
        url: "https://oecd.ai/en/dashboards/policy-initiatives/canadian-sovereign-ai-compute-strategy"
        tier: T4
        span: '0-500'
        title: "Canadian Sovereign AI Compute Strategy - OECD.AI"
        span_text: |
          Initiative overview The Canadian Sovereign AI Compute Strategy responds to a recognised gap in affordable, domestic computing resources for Canadian AI researchers, businesses and innovators. During a public consultation conducted over the summer of 2024, more than 1,000 stakeholders from research, industry and civil society highlighted the high cost of compute resources and the limited availability of domestic capacity as key barriers. The strategy is guided by the findings of this consultation, published in a What We Heard Report, and is designed to safeguard Canadian data and intellectual p
      - evidence_id: ev_007
        bibliography_num: 9
        url: "https://www.canada.ca/en/innovation-science-economic-development/news/2026/04/canada-launches-national-initiative-to-build-large-scale-ai-supercomputing-capacity.html"
        tier: T3
        span: '0-500'
        title: "Canada launches national initiative to build large-scale AI ..."
        span_text: |
          Canada launches national initiative to build large-scale AI supercomputing capacity News release Applications to develop Canada’s sovereign AI supercomputing infrastructure now open April 15, 2026 – Ottawa, Ontario Canada is launching a national effort to build one of the most advanced artificial Intelligence (AI) supercomputing systems, ensuring Canadian researchers, innovators and institutions have the computing power they need to innovate, compete and lead. The Government of Canada is launching the call for applications for the [AI Sovereign Compute Infrastructure Program](https://ised-isde
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-023
    section: "Safety"
    sentence: "Under the US CLOUD Act, US authorities can compel US-based companies or foreign subsidiaries under US control to produce data, regardless of where it is stored and even if it belongs to a Canadian person or organization.[5]"
    cited_evidence:
      - evidence_id: ev_001
        bibliography_num: 5
        url: "https://www.faradaymachines.com/canadian-ai-sovereignty/"
        tier: T4
        span: '0-500'
        title: "Why Canadian Businesses Can't Afford to Depend on US Cloud AI"
        span_text: |
          Why Canadian Businesses Can't Afford to Depend on US Cloud AI The CLOUD Act gives US agencies access to your AI data — even when it's stored in Canada. ChatGPT, Claude, and Copilot all fall under US jurisdiction. Quebec's Law 25 fines reach $25M. The only architecture that keeps Canadian data under Canadian law is on-premises. Data Residency Is Not Data Sovereignty Many Canadian organizations believe they've solved the sovereignty problem by choosing cloud providers with Canadian data centres. Microsoft Azure has regions in Toronto and Quebec. AWS operates in Montreal. Google Cloud runs in ca-
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-024
    section: "Safety"
    sentence: "However, reliance on a nascent sovereign Canadian cloud ecosystem, featuring providers like CanXP AI or Augure AI, may introduce resilience risks due to a thinner offering with potentially inferior model quality, shorter context windows, and narrower feature sets compared to US frontier models.[5]"
    cited_evidence:
      - evidence_id: ev_001
        bibliography_num: 5
        url: "https://www.faradaymachines.com/canadian-ai-sovereignty/"
        tier: T4
        span: '0-500'
        title: "Why Canadian Businesses Can't Afford to Depend on US Cloud AI"
        span_text: |
          Why Canadian Businesses Can't Afford to Depend on US Cloud AI The CLOUD Act gives US agencies access to your AI data — even when it's stored in Canada. ChatGPT, Claude, and Copilot all fall under US jurisdiction. Quebec's Law 25 fines reach $25M. The only architecture that keeps Canadian data under Canadian law is on-premises. Data Residency Is Not Data Sovereignty Many Canadian organizations believe they've solved the sovereignty problem by choosing cloud providers with Canadian data centres. Microsoft Azure has regions in Toronto and Quebec. AWS operates in Montreal. Google Cloud runs in ca-
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-025
    section: "Safety"
    sentence: "The primary risk for sensitive workloads using US-based public cloud providers is legal jurisdiction, as data residency in Canadian data centers does not guarantee data sovereignty.[5]"
    cited_evidence:
      - evidence_id: ev_001
        bibliography_num: 5
        url: "https://www.faradaymachines.com/canadian-ai-sovereignty/"
        tier: T4
        span: '0-500'
        title: "Why Canadian Businesses Can't Afford to Depend on US Cloud AI"
        span_text: |
          Why Canadian Businesses Can't Afford to Depend on US Cloud AI The CLOUD Act gives US agencies access to your AI data — even when it's stored in Canada. ChatGPT, Claude, and Copilot all fall under US jurisdiction. Quebec's Law 25 fines reach $25M. The only architecture that keeps Canadian data under Canadian law is on-premises. Data Residency Is Not Data Sovereignty Many Canadian organizations believe they've solved the sovereignty problem by choosing cloud providers with Canadian data centres. Microsoft Azure has regions in Toronto and Quebec. AWS operates in Montreal. Google Cloud runs in ca-
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-026
    section: "Safety"
    sentence: "In contrast, a fully on-premises compute strategy ensures data is subject exclusively to Canadian law.[5]"
    cited_evidence:
      - evidence_id: ev_001
        bibliography_num: 5
        url: "https://www.faradaymachines.com/canadian-ai-sovereignty/"
        tier: T4
        span: '0-500'
        title: "Why Canadian Businesses Can't Afford to Depend on US Cloud AI"
        span_text: |
          Why Canadian Businesses Can't Afford to Depend on US Cloud AI The CLOUD Act gives US agencies access to your AI data — even when it's stored in Canada. ChatGPT, Claude, and Copilot all fall under US jurisdiction. Quebec's Law 25 fines reach $25M. The only architecture that keeps Canadian data under Canadian law is on-premises. Data Residency Is Not Data Sovereignty Many Canadian organizations believe they've solved the sovereignty problem by choosing cloud providers with Canadian data centres. Microsoft Azure has regions in Toronto and Quebec. AWS operates in Montreal. Google Cloud runs in ca-
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-027
    section: "Dose Response"
    sentence: "This public investment is structured to mobilize further private capital, with one element of the strategy allocating up to CAD $700 million through an AI Compute Challenge to stimulate commercial AI data-centre solutions.[1]"
    cited_evidence:
      - evidence_id: ev_013
        bibliography_num: 1
        url: "https://oecd.ai/en/dashboards/policy-initiatives/canadian-sovereign-ai-compute-strategy"
        tier: T4
        span: '0-500'
        title: "Canadian Sovereign AI Compute Strategy - OECD.AI"
        span_text: |
          Initiative overview The Canadian Sovereign AI Compute Strategy responds to a recognised gap in affordable, domestic computing resources for Canadian AI researchers, businesses and innovators. During a public consultation conducted over the summer of 2024, more than 1,000 stakeholders from research, industry and civil society highlighted the high cost of compute resources and the limited availability of domestic capacity as key barriers. The strategy is guided by the findings of this consultation, published in a What We Heard Report, and is designed to safeguard Canadian data and intellectual p
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-028
    section: "Dose Response"
    sentence: "The scale of required infrastructure is substantial, as the federal intake specifically targets \"sovereign, large-scale AI data centres\" exceeding 100 megawatts (MW) in capacity.[3]"
    cited_evidence:
      - evidence_id: ev_014
        bibliography_num: 3
        url: "https://www.dlapiper.com/en/insights/publications/2026/02/government-of-canada-launches-call-for-proposals-for-large-scale-sovereign-ai-data-centres"
        tier: T4
        span: '0-500'
        title: "Government of Canada launches call for proposals ..."
        span_text: |
          5 February 2026 • 4 minute read Government of Canada launches call for proposals for large scale sovereign AI data centres The Government of Canada has launched a national process to identify and advance large‑scale sovereign AI data centre projects, marking a significant step in expanding the country’s AI infrastructure and strengthening its innovation ecosystem. As artificial intelligence becomes increasingly central to economic growth, the federal government aims to ensure that Canadian researchers, businesses, and institutions have access to the computing capacity needed to remain competit
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
