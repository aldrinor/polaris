# SourceAnalysisBatch Sub-Agent Prompt Template

When serving SourceAnalysisBatch loopback requests, use these rules:

## Perspective Assignment (FIX: was hardcoded "Scientific")
Assign perspective based on source content:
- "Scientific" — academic papers, meta-analyses, systematic reviews, clinical trials, lab studies
- "Regulatory" — government docs, FDA/EFSA/EMA/IEC/ASTM standards, compliance requirements
- "Industry" — manufacturer datasheets, industry scorecards (PVEL), market reports, product specs
- "Economic" — cost analyses, market size, QALY/cost-effectiveness studies
- "Public_Health" — epidemiological data, population-level outcomes, WHO/CDC reports
- "Regional" — country-specific studies, geographic comparisons, Ramadan/LMIC data
- "Methodological" — study design papers, GRADE frameworks, risk-of-bias assessments
- "Emerging_Trends" — preprints, novel materials/techniques, future-direction reviews
- "Historical" — foundational studies, evolution-of-knowledge reviews

## Direct Quote Length (FIX: was 250 chars, too short for NLI)
- direct_quote MUST be 400-600 chars — long enough for the NLI detector to verify prose against
- Include the full relevant passage, not a truncation
- The NLI model (flan-t5-large, 512 tokens ≈ 2K chars) needs substantial overlap between the quote and the section prose to score SUPPORTED

## Atomic Fact Quality
- 2-4 facts per substantive source
- Every fact MUST include specific numbers with units and conditions
- Good: "EVA peel strength decreased from 120 N/cm to 45 N/cm after 3000h damp heat at 85°C/85%RH, with failure mode transitioning from cohesive to adhesive (IEC 61215, 180° peel test, 50mm/min, n=12 specimens)"
- Bad: "EVA adhesion decreased under damp heat conditions"
