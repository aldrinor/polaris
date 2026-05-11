Audit 1 claim. Output YAML only.

CLAIM (POLARIS Q5 Pharmacare):
"8.7% of Quebec households incurring more than $1000 in out-of-pocket costs for prescriptions in 2007, compared to 4.8% in the rest of Canada and less than 3% in countries like New Zealand, the UK, Germany, and the Netherlands."

CITED [4][5]: Pharmacare comparative analysis literature (Canadian Centre for Policy Alternatives + similar pharmacare-policy academic papers).

PRIMARY-SOURCE CONTEXT:
- The 8.7%/4.8% Quebec-vs-rest-of-Canada out-of-pocket comparison is a frequently-cited statistic from Canadian pharmacare policy literature (Morgan et al., Steve Morgan UBC research, CIHI reports).
- The "<3% in NZ/UK/Germany/Netherlands" comparator stat is from international health-system comparative studies.
- Specific year 2007 anchor suggests this comes from a specific Canadian Community Health Survey (CCHS) cycle or comparable international survey.
- Without direct WebFetch access to the specific cited source PDFs (Canadian Centre for Policy Alternatives reports), the audit relies on consistency with broader pharmacare-policy literature.

AUDIT:
1. Are the specific decimals (8.7%, 4.8%, <3%) consistent with widely-cited Canadian pharmacare statistics?
2. The 8.7% / 4.8% comparison is a well-documented Morgan et al. statistic (often cited from 2007 CCHS data).
3. The international comparators (<3% NZ/UK/Germany/Netherlands) align with Commonwealth Fund international health policy surveys.
4. Reasoning soundness: comparing Quebec to ROC and international peers is the standard frame.

Output YAML:
```yaml
claim_id: POLARIS-Q5-C1
cited_source_tier: T2_T3_mixed
primary_source_verified: partial_via_consistency_with_literature
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
