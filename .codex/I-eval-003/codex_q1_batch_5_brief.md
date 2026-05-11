Independent Tier-1 audit of 3 Q1 AI Sovereignty claims. Output YAML records only.

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

- Do NOT skip a claim. ALL 3 must have records.
- Do NOT auto-VERIFIED just because a span exists. Read the span_text and confirm the decimal is there.
- Do NOT exceed one paragraph of rationale per claim.

# Batch (the claims to audit are below; each has cited_evidence with span_text inline)

# Q1 batch 5: claims 29-31 (re-run with full direct_quote)
schema_version: tier1_v2
claims:
  - claim_id: Q1-T1-029
    section: "Dose Response"
    sentence: "The anticipated outcome of this scaled investment is to enable breakthroughs in key sectors like health care and advanced manufacturing, strengthen global competitiveness, and ensure secure, reliable access to critical digital infrastructure.[9]"
    cited_evidence:
      - evidence_id: ev_007
        bibliography_num: 9
        url: "https://www.canada.ca/en/innovation-science-economic-development/news/2026/04/canada-launches-national-initiative-to-build-large-scale-ai-supercomputing-capacity.html"
        tier: T3
        span: '0-500'
        title: "Canada launches national initiative to build large-scale AI ..."
        span_text: |
          Canada launches national initiative to build large-scale AI supercomputing capacity News release Applications to develop Canada’s sovereign AI supercomputing infrastructure now open April 15, 2026 – Ottawa, Ontario Canada is launching a national effort to build one of the most advanced artificial Intelligence (AI) supercomputing systems, ensuring Canadian researchers, innovators and institutions have the computing power they need to innovate, compete and lead. The Government of Canada is launching the call for applications for the [AI Sovereign Compute Infrastructure Program](https://ised-isde.canada.ca/site/ised/en/ai-sovereign-compute-infrastructure-program), supported by historic investments announced in Budget 2024 and Budget 2025. This program, part of the [Canadian Sovereign AI Compute Strategy](https://ised-isde.canada.ca/site/ised/en/canadian-sovereign-ai-compute-strategy), will enable the development of large-scale, Canadian-based compute infrastructure to advance AI research and innovation, while safeguarding Canada’s national interests. These systems will form a core part of Canada’s digital backbone, enabling breakthroughs in areas like health care, energy, advanced manufacturing and scientific discovery. This will strengthen Canada’s global competitiveness, support world-leading research and ensure secure, reliable access to critical digital infrastructure for Canadian innovators. This transformational investment, via a competitive call for applications, invites
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-030
    section: "Dose Response"
    sentence: "The Government of Canada's sovereign AI compute strategy addresses a recognized gap in affordable, domestic computing resources.[1]"
    cited_evidence:
      - evidence_id: ev_013
        bibliography_num: 1
        url: "https://oecd.ai/en/dashboards/policy-initiatives/canadian-sovereign-ai-compute-strategy"
        tier: T4
        span: '0-500'
        title: "Canadian Sovereign AI Compute Strategy - OECD.AI"
        span_text: |
          Initiative overview The Canadian Sovereign AI Compute Strategy responds to a recognised gap in affordable, domestic computing resources for Canadian AI researchers, businesses and innovators. During a public consultation conducted over the summer of 2024, more than 1,000 stakeholders from research, industry and civil society highlighted the high cost of compute resources and the limited availability of domestic capacity as key barriers. The strategy is guided by the findings of this consultation, published in a What We Heard Report, and is designed to safeguard Canadian data and intellectual property while enabling made-in-Canada AI solutions. The strategy comprises three complementary elements. The first, mobilising private sector investment, allocates up to CAD $700 million through the AI Compute Challenge, which seeks proposals from companies, consortiums and academic-industry partnerships to establish commercial AI data-centre solutions in Canada. Projects must build or expand AI-specific data centre capacity, offer flexible and affordable compute, contribute to anchoring Canadian AI companies, and advance sustainable solutions. The second element, building public supercomputing infrastructure, commits up to CAD $1 billion, including a new state-of-the-art AI supercomputing system through the AI Sovereign Compute Infrastructure Program (SCIP), a smaller secure facility led by Shared Services Canada and the National Research Council for government and industry R&D includin
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence

  - claim_id: Q1-T1-031
    section: "Dose Response"
    sentence: "This national effort aims to build large-scale AI compute infrastructure to form a core part of Canada\u2019s digital backbone.[9]"
    cited_evidence:
      - evidence_id: ev_007
        bibliography_num: 9
        url: "https://www.canada.ca/en/innovation-science-economic-development/news/2026/04/canada-launches-national-initiative-to-build-large-scale-ai-supercomputing-capacity.html"
        tier: T3
        span: '0-500'
        title: "Canada launches national initiative to build large-scale AI ..."
        span_text: |
          Canada launches national initiative to build large-scale AI supercomputing capacity News release Applications to develop Canada’s sovereign AI supercomputing infrastructure now open April 15, 2026 – Ottawa, Ontario Canada is launching a national effort to build one of the most advanced artificial Intelligence (AI) supercomputing systems, ensuring Canadian researchers, innovators and institutions have the computing power they need to innovate, compete and lead. The Government of Canada is launching the call for applications for the [AI Sovereign Compute Infrastructure Program](https://ised-isde.canada.ca/site/ised/en/ai-sovereign-compute-infrastructure-program), supported by historic investments announced in Budget 2024 and Budget 2025. This program, part of the [Canadian Sovereign AI Compute Strategy](https://ised-isde.canada.ca/site/ised/en/canadian-sovereign-ai-compute-strategy), will enable the development of large-scale, Canadian-based compute infrastructure to advance AI research and innovation, while safeguarding Canada’s national interests. These systems will form a core part of Canada’s digital backbone, enabling breakthroughs in areas like health care, energy, advanced manufacturing and scientific discovery. This will strengthen Canada’s global competitiveness, support world-leading research and ensure secure, reliable access to critical digital infrastructure for Canadian innovators. This transformational investment, via a competitive call for applications, invites
    # tier1_to_fill: claim_type, materiality, citation_context_match, verdict, rationale, reviewer_confidence


# Output

Single YAML block. List of records in claim_id order. Then a summary:

```yaml
- claim_id: ...
  ...
- claim_id: ...
  ...

batch_summary:
  total: 3
  per_verdict: {VERIFIED: N, PARTIAL: N, UNSUPPORTED: N, FABRICATED: N, UNREACHABLE: N}
  per_context_match: {yes: N, partial: N, no: N}
  notable: ["..."]
```

Output the YAML directly. No commentary outside.
