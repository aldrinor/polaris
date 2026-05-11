Audit 1 claim. Output YAML only.

CLAIM (POLARIS Q2 Canada-US CUSMA Regulatory section):
"The formal review process for the Canada-United States-Mexico Agreement (CUSMA) is mandated by Article 34.7, which requires the three parties to conduct a joint review at the six-year mark following the agreement's entry into force on July 1, 2020. This review, commencing in July 2026, is conducted through the Free Trade Commission to evaluate the agreement's effectiveness and consider recommendations for action. A critical outcome of this review is the requirement for each party to confirm whether they wish to extend CUSMA for a new 16-year term; unanimous agreement is required for an extension, otherwise the agreement is set to terminate on July 1, 2036."

CITED [1][2][3]: Various analyses of CUSMA Article 34.7.

PRIMARY-SOURCE GROUND TRUTH (CUSMA/USMCA Article 34.7):
- CUSMA/USMCA entered into force on July 1, 2020 ✓ VERIFIED.
- Article 34.7 mandates a joint six-year review (i.e., starting July 2026) by the Free Trade Commission ✓ VERIFIED.
- Article 34.7 requires the parties to confirm in writing if they wish to extend the agreement for a further 16-year period ✓ VERIFIED.
- If a party does not confirm extension, the agreement enters annual joint reviews until either extended or terminated at the 16-year mark (July 1, 2036) ✓ VERIFIED.
- "Unanimous agreement required for extension" is a fair characterization: all three parties must confirm extension; otherwise the agreement enters the joint-review-until-terminate phase.

AUDIT:
1. "July 1, 2020" entry into force — VERIFIED EXACT
2. "Six-year mark" / July 2026 review — VERIFIED
3. "Free Trade Commission" as the conducting body — VERIFIED
4. "16-year term" extension — VERIFIED EXACT
5. "Unanimous agreement required" — VERIFIED (all three parties must confirm)
6. "Terminate on July 1, 2036" — VERIFIED (16 years after July 1, 2020)
7. Citations appropriate (T3 regulatory primary text + T4 analyses)

Output YAML:
```yaml
claim_id: POLARIS-Q2-C1
cited_source_tier: T3
primary_source_verified: yes
verdict: VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | UNREACHABLE
reason: "one sentence"
```
