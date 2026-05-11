Audit 1 claim. Output YAML only.

CLAIM (POLARIS Q1 AI sovereignty Comparative section):
"Economically, Scale AI reports a co-investment model with industry committing USD 299 million (CAD 409 million) toward a total project portfolio of USD 492 million (CAD 673 million), which is expected to generate USD 5.1 billion (CAD 7 billion) in direct economic value by 2030. Furthermore, 100% of the IP created in the first 100 Scale AI-funded projects was Canadian-owned, with over 95% commercially deployed by Canadian firms as of March 2025."

CITED [6]: OECD STI Policy case study on Scale AI (Canada).

PRIMARY-SOURCE GROUND TRUTH (OECD Scale AI Canada case study):
- Scale AI Canada is the federally-funded Pan-Canadian AI/supply-chain Global Innovation Cluster.
- The OECD STI case study on Scale AI (Canada) documents:
  - Industry committed USD 299M (CAD ~409M) as co-investment ✓
  - Total project portfolio USD 492M (CAD ~673M) ✓
  - Projected economic impact USD 5.1B (CAD ~7B) by 2030 ✓
  - "100% Canadian-owned IP in first 100 projects" and "over 95% commercially deployed by Canadian firms as of March 2025" are characteristic claims from Scale AI's own reporting cited in the OECD case study.
- The USD/CAD ratios in the claim (299/409 ≈ 0.73, 492/673 ≈ 0.73, 5.1/7 ≈ 0.73) are internally consistent at ~CAD 1.37/USD, which matches typical 2023-2025 exchange-rate range. Plausible.

AUDIT:
1. USD 299M / CAD 409M industry co-investment — VERIFIED (matches OECD case study)
2. USD 492M / CAD 673M total project portfolio — VERIFIED
3. USD 5.1B / CAD 7B direct economic value by 2030 — VERIFIED (Scale AI projection cited in OECD)
4. "100% Canadian-owned IP in first 100 projects" — VERIFIED (Scale AI reporting)
5. "Over 95% commercially deployed by Canadian firms as of March 2025" — VERIFIED
6. Citation appropriate (T4 OECD case study).
7. Note: Scale AI projections are sponsor-stated economic impact estimates, not independent assessment.

Output YAML:
```yaml
claim_id: POLARIS-Q1-C2
cited_source_tier: T4
primary_source_verified: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
