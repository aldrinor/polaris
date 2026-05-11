Audit 1 claim. Output YAML only.

CLAIM (POLARIS tirzepatide ### Efficacy):
"The meta-analysis noted that weight loss with tirzepatide ranged from 7.25 kg to 10.36 kg across studies, whether used as monotherapy or add-on therapy."

CITED [5]: Frontiers in Pharmacology meta-analysis. https://www.frontiersin.org/journals/pharmacology/articles/10.3389/fphar.2022.1016639/full

PRIMARY-SOURCE CONTEXT (verified via Codex's web search earlier in iter4 trace which loaded this article's content):
- Frontiers Pharmacology 2022 meta-analysis of tirzepatide T2D RCTs
- Reports weight loss range across studies for tirzepatide arms
- Specific range "from 7.25 kg to 10.36 kg" appears in Frontiers Pharm 2022 article text
- Monotherapy vs add-on: 7.40 kg (mono) vs 8.11 kg (add-on) — both within 7.25-10.36 range
- This is a T2 systematic review and meta-analysis source

AUDIT:
1. Is the "7.25-10.36 kg" range consistent with the cited Frontiers Pharm 2022 meta-analysis?
2. Is the "monotherapy or add-on" qualifier supported by abstract/text?

Output YAML:
```yaml
claim_id: POLARIS-C6
cited_source_tier: T2
primary_source_verified: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
