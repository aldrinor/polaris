Tier-1 v2 audit on Gemini Ultra Deep Research Q1 output. Output YAML.

# Context

Auditing Gemini Ultra Deep Research on Q1 "Canada sovereign frontier-LLM compute vs US hyperscalers for federal AI workloads 2026". POLARIS scored 96.8% V on same question. ChatGPT Pro DR scored 71% V on 7 audited claims. Gemini's textContent did NOT include inline citation markers (they were rendered as superscripts that dropped during text extraction), so audit each claim against general knowledge.

# Audit instruction

Apply Tier-1 v2 schema per claim:
- claim_type, materiality, citation_context_match (yes/partial/no/unverifiable), verdict, rationale, reviewer_confidence

# Banned

- Don't auto-VERIFIED. Decimals/dates/dollars must be plausible.

# Claims (cleanest 7 from Gemini Q1)

```yaml
- claim_id: GM-Q1-A
  sentence: |
    By the end of 2025, total global AI data center power capacity exceeded 30 gigawatts—a figure comparable to the peak power usage of entire industrialized states such as New York, and substantially larger than the baseline demand of many developed nations.

- claim_id: GM-Q1-B
  sentence: |
    Canada has launched a $2 billion Sovereign AI Compute Strategy to secure domestic capacity, committing approximately $890 million to the Infrastructure Build Layer of SCIP alone.

- claim_id: GM-Q1-C
  sentence: |
    The Canadian Sovereign AI Compute Strategy is a national policy framework designed to address a recognized gap in affordable, domestic computing resources for Canadian AI researchers, businesses, and innovators.

- claim_id: GM-Q1-D
  sentence: |
    A separate federal intake process launched in February 2026 aims to identify and advance sovereign, large-scale AI data centre projects exceeding 100 megawatts (MW) in capacity.

- claim_id: GM-Q1-E
  sentence: |
    Budget 2025 proposed $925.6 million over five years starting in 2025-26 to establish a sovereign, large-scale public AI computing infrastructure.

- claim_id: GM-Q1-F
  sentence: |
    Under the US CLOUD Act, US authorities can compel US-based companies or foreign subsidiaries under US control to produce data, regardless of where it is stored and even if it belongs to a Canadian person or organization.

- claim_id: GM-Q1-G
  sentence: |
    The May 2026 collaboration between the federal government and TELUS to build massive, highly-efficient AI clusters using next-generation Nvidia architectures, highlight this shift.
```

# Output schema

```yaml
records:
  - claim_id: ...
    claim_type: ...
    materiality: ...
    citation_context_match: ...
    verdict: ...
    rationale: ...
    reviewer_confidence: ...

batch_summary:
  total: 7
  per_verdict: {VERIFIED: N, PARTIAL: N, UNSUPPORTED: N, FABRICATED: N, UNREACHABLE: N, UNVERIFIABLE: N}
  per_context_match: {yes: N, partial: N, no: N, unverifiable: N}
```
