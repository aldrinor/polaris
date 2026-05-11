Audit 1 claim. Output YAML only.

CLAIM (ChatGPT Deep Research tirzepatide):
"In SURPASS-6, adding tirzepatide to basal insulin was superior to adding prandial lispro, with a pooled HbA1c difference of −0.98% and a pooled weight difference of −12.2 kg at 52 weeks."

CITED SOURCE: SURPASS-6 (Rosenstock et al. JAMA 2023). https://jamanetwork.com/journals/jama/fullarticle/2810386

PRIMARY SOURCE GROUND TRUTH (verified from JAMA 2023 via WebFetch 2026-05-11):
- HbA1c treatment difference pooled tirzepatide vs insulin lispro: −0.98% (95% CI −1.17% to −0.79%, p<0.001) at 52 weeks
- Body weight treatment difference: −12.2 kg (95% CI −13.4 to −10.9)
- Sample N=1,428 (717 tirzepatide pooled, 708 lispro)
- Open-label, sponsor Eli Lilly

AUDIT: do the cited decimals exactly match the JAMA primary source?

Output YAML:
```yaml
claim_id: CHATGPT-C2
cited_source_tier: T1
primary_source_verified: yes
decimals_match: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
