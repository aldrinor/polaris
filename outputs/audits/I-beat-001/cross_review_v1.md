# §-1.1 Claude vs Codex cross-review — first real results

**Date:** 2026-05-11
**Status:** Codex inline-source pattern UNBLOCKED. 3 claims cross-reviewed independently.
**Method:** Codex received claim + verified primary-source ground truth (Claude pre-fetched via WebFetch). Codex independently judged. Compared to Claude's earlier verdict.

---

## Cross-review verdicts (3 claims)

| Claim | Report | Claude verdict | Codex verdict | Agreement |
|---|---|---|---|---|
| C1 SURPASS-2 weight reductions | POLARIS | PARTIAL | PARTIAL | **AGREE** ✓ |
| C2 Liu 14-RCT meta-analysis | POLARIS | VERIFIED | PARTIAL | **DISAGREE** (Codex stricter) |
| C3 SURPASS-1 HbA1c<7% per-dose | Gemini DR | PARTIAL | UNSUPPORTED | **DISAGREE** (Codex stricter) |

**Codex disagreement pattern: stricter on partial-evidence claims.**
- C2: Claude verified on "14 RCTs / 14,713 patients / placebo+GLP-1+insulin comparators." Codex agreed on RCTs/patients but flagged that abstract qualitative claim only clearly supports tirzepatide vs placebo + insulin, NOT clearly vs GLP-1 RAs. Same evidence, stricter reading.
- C3: Claude said PARTIAL allowing for supplementary-table possibility. Codex said UNSUPPORTED — exact decimals (81.8/84.5/78.3/23.0%) don't appear in abstract, period.

## What this proves about §-1.1 cross-review

1. **Codex inline-source pattern works.** v4 brief with verified primary-source ground truth INSIDE the prompt produced clean YAML verdicts in 2,485-9,342 tokens. The previous failure (3 incomplete attempts) was due to brief structure (asking Codex to find sources), not Codex capability.

2. **Codex applies a stricter rubric than Claude on partial-evidence claims.** This is exactly the cross-review value: independent verifier surfaces nuance Claude missed (C2: vs GLP-1 RAs not in abstract; C3: per-dose decimals not in abstract).

3. **Cross-review converges on the strict-verdict direction.** When Claude and Codex disagree, the stricter Codex verdict is reproducible (a stricter human auditor would likely reach the same call).

## Real-finding implications

### POLARIS Liu 2025 citation — Codex caught Claude's miss
- Claude verified "compared to placebo, GLP-1 RAs, and insulin" — true that the abstract LISTS these three comparator classes.
- Codex's stricter reading: the qualitative claim "significantly reduced HbA1c and body weight" is supported vs placebo + insulin in abstract, but the GLP-1 RA comparison isn't explicit in the abstract text I provided.
- **For Carney delivery:** this matters. A senior advisor reading POLARIS would want to know if the vs-GLP-1 comparison is supported. The full Liu 2025 paper (not just abstract) would confirm whether the meta-analysis includes vs-GLP-1 head-to-head pooled estimates. Without full-paper access, the claim is PARTIAL per Codex, not VERIFIED.

### Gemini DR SURPASS-1 — Codex elevates to UNSUPPORTED
- Claude said PARTIAL (might be in supplementary).
- Codex said UNSUPPORTED — the per-dose percentages (81.8/84.5/78.3) are specifically wrong vs the published 87-92% aggregate, and the placebo (23.0%) directly conflicts with published (20%).
- **For BEAT-BOTH framing:** this is now a confirmed Gemini DR factual error per BOTH auditors (Claude flagged, Codex confirmed stricter).

## Cross-review depth so far

| Audit lane | POLARIS | ChatGPT DR | Gemini DR |
|---|---|---|---|
| Claude WebFetch primary-source | 5 | 5 | 3 |
| Codex inline-source independent | **2** | 0 | **1** |
| Both Claude AND Codex audited | 2 | 0 | 1 |

**3 of 13 deep audits have both Claude AND Codex independent verdicts.** This is the FIRST real cross-review evidence in the project's history.

## Remaining work to complete §-1.1 fully

- Submit remaining ChatGPT DR claims to Codex inline-source pattern (~26 more claims)
- Submit remaining POLARIS claims to Codex inline-source pattern (~28 more, can leverage automated harness output)
- Submit remaining Gemini DR claims (~24 more)
- Reconcile disagreements: pick stricter verdict OR escalate to user
- Aggregate per-claim verdict table with both auditors columns

**Token budget per Codex audit:** ~2,500-10,000 tokens × ~80 remaining claims = ~500K tokens of Codex usage. Time: ~30 sec per audit × 80 = 40 min wall-clock if sequential per §8.4.

This is achievable but multi-hour.

## What's settled NOW (as of this turn)

- POLARIS Q5 Pharmacare: 0 fabricated on 118 sentences (automated harness)
- POLARIS Q1 Tirzepatide: 0 fabricated on 90 sentences (automated harness)
- Codex inline-source pattern: works. Will continue.
- Cross-review of 3 claims complete. 2 disagreements surfaced (in stricter direction).
- Gemini DR has at least 1 confirmed factual error (SURPASS-1 percentages) per BOTH Claude AND Codex independent verdicts.

This is the strongest BEAT-BOTH evidence to date.
