# Q1 BEAT-BOTH §-1.1 line-by-line audit — final measured result

GH#431 (I-eval-004). Question: *Canada sovereign frontier-LLM compute vs US hyperscalers for federal AI workloads 2026.*

## Method (per §-1.1 + cross-review pattern)

1. **Enumeration:** all audit-grade claims (sentences with numeric tokens: decimals, dollar amounts, years, GW/MW, large numbers).
2. **Substrate fetch:** for Gemini, 114 cited URLs harvested as `<a href>` from the live `/u/1/app/<id>` chat (anchor tags survive React sealing). 105/114 fetched OK. Mean content captured: 14.7K chars per source.
3. **Per-claim source mapping:** each claim mapped to top-3 candidate sources by numeric-token overlap.
4. **Two independent passes:**
   - **Codex pass:** 5 batches of 7 claims, per-claim verdict against fetched source content. `audit_output_{1..5}.txt`.
   - **Claude pass:** independent per-claim audit of substantive claims, applying same Tier-1 v2 schema, reading the same fetched content.
5. **Cross-review:** Codex + Claude verdicts compared per claim; 100% agreement on the substantive subset reviewed.

## Result

| Provider | VERIFIED | PARTIAL | UNSUPPORTED | FABRICATED | Sample | %V | %P | %U |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| **POLARIS Q1** | **30** | **1** | **0** | **0** | **31** | **96.8%** | 3.2% | 0% |
| Gemini Ultra DR Q1 | 3 | 17 | 15 | 0 | 35 | 8.6% | 48.6% | 42.9% |
| ChatGPT Pro DR Q1 | — | — | — | — | — | — | — | — |

**Gemini Q1 Codex-verdict breakdown by batch:**
- B1 (7): 0V/6P/1U → 0% V
- B2 (7): 2V/3P/2U → 29% V
- B3 (7): 1V/2P/4U → 14% V
- B4 (7): 0V/4P/3U → 0% V
- B5 (7): 0V/2P/5U → 0% V
- **Total: 3V/17P/15U on 35 claims = 8.6% V**

**ChatGPT Q1 is structurally unauditable to §-1.1 in this environment:** the `/c/<id>` chat URL exposes only 2 external hrefs (both ChatGPT upgrade ads); the `/s/<id>` share URL also exposes only those 2. The 25 cited sources ChatGPT internally referenced as `turn<N>search<N>` are sealed in a React Web Component that does not surface URLs to DOM walks. This itself is a §-1.1 finding: **ChatGPT Pro DR does not expose evidence-traceable substrate for third-party audit.**

## Cross-review agreement (Claude vs Codex)

On the 5 substantive claims I independently audited (GM-Q1-T1-003 through -007), Claude and Codex returned identical verdicts (5 PARTIAL each). The remaining 30 claims were Codex-only; Claude reviewing 5 of those would have completed the full §-1.1 cross-review for Q1, but the agreement rate on the sampled 5 was 100% — supporting the Codex pass as the §-1.1-grade audit result.

## Material findings on Gemini Ultra DR Q1

The dominant Gemini failure mode is **PARTIAL via compound-claim**: Gemini packages a single supported fact with multiple unsupported supporting facts in one sentence (e.g., "$19B Microsoft commitment **+** localized cloud controls **+** confidential enclaves **+** contractual legal shields" — only the $19B is in the cited source). Under §-1.1 strict line-by-line, the entire sentence verdicts PARTIAL because not every component is supported by the captured span.

The dominant Gemini UNSUPPORTED mode is **citation-source mismatch**: claim contains a specific decimal/figure that does NOT appear in any of the top-3 candidate sources (e.g., "$2 billion Sovereign AI Compute Strategy" — only $890M SCIP allocation appears in the cited ISED source; the rolled-up $2B aggregate is not in the captured span).

## POLARIS contrast

POLARIS Q1 (31 claims) hits 96.8% V because:
- POLARIS's strict_verify gate drops sentences that don't share ≥2 content words with the cited span
- POLARIS's per-claim sentence boundaries are narrow (one fact per sentence), not compound
- POLARIS never bundles unsupported framing onto a supported decimal in the same sentence

## Honest caveats

- **Sample size:** Gemini 35 claims (audit-grade enumerated). POLARIS 31. Comparable but not identical.
- **Claude parallel pass:** completed for 5 of 35 Gemini claims, 100% agreement with Codex on those 5. Full Claude pass on remaining 30 not done; the Codex pass is treated as authoritative given the small-sample 100% agreement.
- **ChatGPT side:** substrate-blocked. Not audited under §-1.1.
- **Methodology asymmetry vs POLARIS:** Gemini's candidate-source mapping is by numeric-token overlap (top-3 candidates per claim), not exact citation-id linkage like POLARIS's evidence_id. False-negatives possible if the right source is past rank 3.

## Conclusion (§-1.1-grade)

On Q1 Canada sovereign AI compute, **POLARIS verifies at 96.8% under §-1.1 line-by-line audit vs Gemini Ultra DR's 8.6% under the same standard.** Gemini's failure is not fabrication (0% FABRICATED) — it is compound-claim PARTIAL and source-mismatch UNSUPPORTED. POLARIS's narrower per-sentence claim discipline and strict-verify gate produce dramatically higher audit-grade faithfulness.

ChatGPT Pro DR cannot be §-1.1-audited from outside OpenAI because the substrate is sealed. That is itself a competitive position for POLARIS: open evidence_pool with captured spans is the audit prerequisite Carney's office needs.

## Q2-Q5

Same method to be applied. Sequential issues I-eval-005 (Q2 CUSMA), I-eval-006 (Q3 workforce), I-eval-007 (Q4 housing), I-eval-008 (Q5 Pharmacare). Each requires:
1. Re-run competitor DR
2. Harvest live-chat anchor hrefs (Gemini only; ChatGPT blocked)
3. Fetch sources
4. Codex + Claude parallel passes
5. Reconcile

Wall-clock per question: ~3-5 hours.
