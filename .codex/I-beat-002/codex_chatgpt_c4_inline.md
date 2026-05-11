Audit 1 claim. Output YAML only.

CLAIM (ChatGPT Deep Research tirzepatide):
"in SURPASS-4, glycemic and weight separation versus insulin glargine persisted through 104 weeks, and in SURPASS-CVOT, metabolic advantages over dulaglutide were maintained over years of follow-up."

CITED SOURCE: SURPASS-4 (Del Prato et al. Lancet 2021). https://pubmed.ncbi.nlm.nih.gov/34672967/

PRIMARY SOURCE GROUND TRUTH (verified via PubMed PMID 34672967):
- SURPASS-4: tirzepatide vs insulin glargine in T2D + CV risk
- HbA1c treatment differences at 52 weeks: −0.99% (10mg) and −1.14% (15mg) vs glargine
- N=2,002 randomized
- MACE-4 events: 109 total, HR 0.74 (95% CI 0.51-1.08), not increased on tirzepatide
- Mortality: 25 deaths tirzepatide (3%) vs 35 glargine (4%)
- Open-label, sponsor Eli Lilly
- Trial duration: 52 weeks primary, with longer-term follow-up extension. Reports often reference week-104 sensitivity analyses.

AUDIT:
1. "glycemic and weight separation vs glargine persisted through 104 weeks" — claim about durability through extended follow-up
2. Cited primary trial is SURPASS-4 (52 weeks primary). Extended follow-up to 104 weeks reported in subsequent publications.
3. "SURPASS-CVOT metabolic advantages maintained" — directionally correct per primary data

Output YAML:
```yaml
claim_id: CHATGPT-C4
cited_source_tier: T1
primary_source_verified: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
