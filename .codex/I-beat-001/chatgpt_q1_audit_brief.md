Tier-1 v2 audit on ChatGPT Pro Deep Research Q1 output. Output YAML.

# Context

Auditing the ChatGPT Pro Deep Research report on Q1 "Canada sovereign frontier-LLM compute vs US hyperscalers for federal AI workloads 2026". POLARIS scored 96.8% VERIFIED on the same question (30V / 1P / 0U across 31 audit-grade claims). The ChatGPT report has 25 citations total / 451 web searches across 12 min of DR. We're testing whether ChatGPT's claims hold under the same line-by-line standard.

# Audit instruction

For each claim below, assess against your general knowledge + ChatGPT's stated citation source. ChatGPT's DR output uses inline URL annotations and `turn<N>search<N>` citation markers; the latter are internal to ChatGPT's research session and not externally resolvable, but you can judge plausibility against the named source title.

Apply Tier-1 v2 schema per claim:
- claim_type: efficacy | safety | regulatory | economic | technical | comparative | mechanism | epidemiology | background
- materiality: critical | major | minor | background
- citation_context_match: yes | partial | no | unverifiable
- verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
- rationale: one sentence
- reviewer_confidence: 0.0 - 1.0

# Banned shortcuts

- Do NOT auto-VERIFIED. Specific decimals, dollar figures, and dates must be plausible against your knowledge.
- Flag UNVERIFIABLE if the claim depends on a session-internal source (`turn<N>search<N>`) you cannot resolve.
- Flag UNSUPPORTED if the claim contradicts what you know about the named source.

# Claims (cleanest 7 from ChatGPT Q1)

```yaml
- claim_id: CG-Q1-A
  sentence: |
    Canada has committed up to C$700 million for private-sector compute capacity, up to C$1 billion for public supercomputing, and up to C$300 million for an AI Compute Access Fund; the AI Sovereign Compute Infrastructure Program alone will provide about C$890 million to the build layer beginning in fiscal 2026-27.
  cited_sources: ["Government of Canada (multiple official docs)"]

- claim_id: CG-Q1-B
  sentence: |
    A 1,024-GPU H100/H200-class Canadian cluster amortized over five years lands at roughly US$2.8/GPU-hour at 80% utilization, but rises to US$5.5/GPU-hour at 40% utilization.
  cited_sources: ["ChatGPT internal model"]

- claim_id: CG-Q1-C
  sentence: |
    A TELUS facility in Rimouski said in May 2026 that its first sovereign AI factory was already fully sold out.
  cited_sources: ["TELUS press release / multiple news sources"]

- claim_id: CG-Q1-D
  sentence: |
    Hydro-Quebec proposed in February 2026 that all new data centres over 5 MW in Quebec move to a new average rate of about 13c/kWh, approximately double what current large-power customers pay, and said data-centre electricity use in the province could rise sevenfold by 2035 to more than 1,000 MW.
  cited_sources: ["Hydro-Quebec (https://www.hydroquebec.com)"]

- claim_id: CG-Q1-E
  sentence: |
    Treasury Board's cloud-guardrail material says Protected B supply contracts were established with Amazon Web Services Canada and Microsoft Canada in August 2019 and with Google Cloud Canada in December 2022.
  cited_sources: ["Treasury Board of Canada Secretariat"]

- claim_id: CG-Q1-F
  sentence: |
    Microsoft Azure publicly indexed 2026 retail snapshots for ND96isr H100 v5 show roughly US$98.32/h in East US and US$117.98/h in Canada Central, or about US$12.29-14.75/GPU-hour.
  cited_sources: ["Microsoft Azure (https://azure.microsoft.com)"]

- claim_id: CG-Q1-G
  sentence: |
    Official AWS examples retrieved show p5.48xlarge at US$55.04/h on-demand in N. Virginia, or US$6.88/GPU-hour. A recent AWS official example also showed Capacity Blocks at US$34.608/h, or about US$4.33/GPU-hour.
  cited_sources: ["Amazon Web Services (https://aws.amazon.com)"]
```

# Output schema

```yaml
records:
  - claim_id: CG-Q1-A
    claim_type: economic
    materiality: critical
    citation_context_match: yes
    verdict: VERIFIED
    rationale: "..."
    reviewer_confidence: 0.9
  - ...

batch_summary:
  total: 7
  per_verdict: {VERIFIED: N, PARTIAL: N, UNSUPPORTED: N, FABRICATED: N, UNREACHABLE: N, UNVERIFIABLE: N}
  per_context_match: {yes: N, partial: N, no: N, unverifiable: N}
```
