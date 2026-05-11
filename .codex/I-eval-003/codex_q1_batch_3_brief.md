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

# Q1 batch 3: claims 15-21
schema_version: tier1_v2
claims:
  - claim_id: Q1-T1-015
    section: "Efficacy"
    sentence: "The Canadian Sovereign AI Compute Strategy is a direct response to a recognized gap in affordable, domestic computing resources, as highlighted by a public consultation with more than 1,000 stakeholders from research, industry, and civil society.[1]"
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

  - claim_id: Q1-T1-016
    section: "Efficacy"
    sentence: "The parallel intake for \"sovereign, large-scale AI data centres\" targets facilities exceeding 100 megawatts (MW) in scale.[3]"
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

  - claim_id: Q1-T1-017
    section: "Efficacy"
    sentence: "The overarching objective is to provide secure, reliable access to critical digital infrastructure to advance AI research and innovation in areas like health care and scientific discovery while safeguarding national interests and Canadian data and intellectual property.[9][1]"
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

  - claim_id: Q1-T1-018
    section: "Efficacy"
    sentence: "One vision describes this infrastructure as a \"bold, nation-building project\" and a \"digital backbone\" intended to power the largest models and discoveries.[10]"
    cited_evidence:
      - evidence_id: ev_008
        bibliography_num: 10
        url: "https://ai.alliancecan.ca/en"
        tier: T4
        span: '0-500'
        title: "Sovereign AI Compute - Digital Research Alliance of Canada"
        span_text: |
          Public Infrastructure for Public Good. We’re uniting researchers, government and industry behind one national vision: secure, scaled-up and sovereign public data and AI infrastructure, integrated across Canada to power the largest models, datasets and discoveries. Like roads, railways and hydro, this digital backbone is a bold, nation-building project that can transform Canada’s future — fueling our economy, strengthening society and securing our place on the world stage. This is our moment to make a generational investment — sovereign public infrastructure for a stronger, more resilient tomor
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-019
    section: "Efficacy"
    sentence: "The strategy aims to ensure Canadian researchers and companies have the computing power needed to compete globally, with the goal of strengthening Canada's position as a global leader in artificial intelligence.[9][2]"
    cited_evidence:
      - evidence_id: ev_010
        bibliography_num: 2
        url: "https://ised-isde.canada.ca/site/ised/en/canadian-sovereign-ai-compute-strategy"
        tier: T3
        span: '0-500'
        title: "Canadian Sovereign AI Compute Strategy"
        span_text: |
          To strengthen Canada's position as a global leader in artificial intelligence (AI), it is essential for Canadian AI industries and researchers to have access to affordable, cutting‑edge compute infrastructure. By boosting access to powerful computing resources right here in Canada, we can drive innovation, create new opportunities and ensure that Canada stays competitive in the global AI race. What is AI compute? AI compute refers to the computational resources required for AI systems to perform tasks, such as processing data, running algorithms and training machine learning models. In other w
      - evidence_id: ev_007
        bibliography_num: 9
        url: "https://www.canada.ca/en/innovation-science-economic-development/news/2026/04/canada-launches-national-initiative-to-build-large-scale-ai-supercomputing-capacity.html"
        tier: T3
        span: '0-500'
        title: "Canada launches national initiative to build large-scale AI ..."
        span_text: |
          Canada launches national initiative to build large-scale AI supercomputing capacity News release Applications to develop Canada’s sovereign AI supercomputing infrastructure now open April 15, 2026 – Ottawa, Ontario Canada is launching a national effort to build one of the most advanced artificial Intelligence (AI) supercomputing systems, ensuring Canadian researchers, innovators and institutions have the computing power they need to innovate, compete and lead. The Government of Canada is launching the call for applications for the [AI Sovereign Compute Infrastructure Program](https://ised-isde
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-020
    section: "Efficacy"
    sentence: "However, evidence notes that the demand for processing power is soaring and supply is perceived as limited, raising questions about how much compute capacity Canada needs and can build to secure its place in the AI race.[7]"
    cited_evidence:
      - evidence_id: ev_000
        bibliography_num: 7
        url: "https://thelogic.co/news/event/canada-ai-compute-event/"
        tier: UNKNOWN
        span: '0-500'
        title: "The true cost of Canada's sovereign AI ambitions - The Logic"
        span_text: |
          Presented by:
          The race for AI dominance isn’t just about code; it’s about processing power. As the ambition of the industry soars, there’s never been more demand for the infrastructure to support it.
          As a result, compute has become the hot commodity in AI. It’s why tech giants and asset managers are proposing and building data centres that consume as much power as entire neighbourhoods. It’s also why companies like Nvidia, whose GPUs are used to help run and train AI models, are soaring in value.
          In Canada and across the world, governments and businesses are trying to grab a piece of the compu
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-021
    section: "Efficacy"
    sentence: "This public investment is structured across complementary elements, including mobilizing private sector investment with up to CAD $700 million through the AI Compute Challenge.[1]"
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
