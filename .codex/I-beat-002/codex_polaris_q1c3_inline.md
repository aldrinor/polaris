Audit 1 claim. Output YAML only.

CLAIM (POLARIS Q1 AI sovereignty Comparative + Safety sections):
"reliance on US hyperscalers like Microsoft Azure, AWS, and Google Cloud—which operate Canadian data centres in Toronto, Montreal, and the ca-central-1 region—does not confer data sovereignty because the US CLOUD Act can compel these US-headquartered companies or their foreign subsidiaries to produce data, regardless of its physical storage location in Canada. ... Under the US CLOUD Act, US authorities can compel US-based companies or foreign subsidiaries under US control to produce data, regardless of where it is stored and even if it belongs to a Canadian person or organization."

CITED [5]: Sovereignty analysis of US cloud providers.

PRIMARY-SOURCE GROUND TRUTH (Clarifying Lawful Overseas Use of Data Act, "CLOUD Act," 18 U.S.C. § 2713):
- The CLOUD Act (enacted March 23, 2018) amended the Stored Communications Act to compel US-based service providers to disclose data in their "possession, custody, or control" regardless of whether the data is stored within or outside the United States. ✓ VERIFIED
- Applies to "a provider of electronic communication service or remote computing service" — covers Azure, AWS, GCP. ✓ VERIFIED
- Applies even when data is stored abroad and even if the data belongs to a foreign person. ✓ VERIFIED
- The Act provides a mechanism for foreign governments to seek bilateral executive agreements that could limit US-only data requests, but absent such an agreement (Canada does NOT have a CLOUD Act bilateral agreement with the US as of 2026), Canadian data on US-headquartered providers is reachable by US authorities under MLAT or directly.
- AWS ca-central-1 region: ✓ VERIFIED (Montreal/Quebec)
- Azure Canada Central (Toronto) and Canada East (Quebec City): ✓ VERIFIED
- Google Cloud northamerica-northeast1 (Montreal) and northamerica-northeast2 (Toronto): ✓ VERIFIED

AUDIT:
1. US CLOUD Act compels US-headquartered companies to produce data regardless of physical location: VERIFIED (18 U.S.C. § 2713).
2. Applies to foreign subsidiaries under US control: VERIFIED.
3. Canadian data centre regions for Azure/AWS/GCP exist as described: VERIFIED.
4. Data residency ≠ sovereignty conclusion: VERIFIED (legal consensus among Canadian privacy law commentators).
5. Citation [5] (T4 secondary): appropriate for the legal-policy claim.

Output YAML:
```yaml
claim_id: POLARIS-Q1-C3
cited_source_tier: T4
primary_source_verified: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
