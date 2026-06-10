# §-1.1 INDEPENDENT CODEX AUDIT — drb_75_metal_ions_cvd

**Question (DRB-EN #75, CLINICAL):** Therapeutic modulation of plasma metal ions / minerals (iron, magnesium, zinc, copper, calcium, selenium, and toxic metals lead/cadmium/arsenic) in cardiovascular disease — which interventions are clinically supported, by what evidence, with what efficacy, safety, dosing, and at-risk populations.

You are the **independent CODEX auditor**. A separate Claude auditor ran in parallel; you must NOT be told its verdict. Reason from the evidence below only.

---

## THE §-1.1 LAW (BINDING — this is clinical context; errors here are lethal)

This is a clinical research-output audit. You MUST audit **claim-by-claim** against the **actually-cited span text** (not titles, not abstracts, not your prior knowledge).

1. **Claim-by-claim** against the cited span text quoted below.
2. **Reasoning-step-by-reasoning-step** — each inference must follow from the cited span.
3. **Citation-by-citation** — the citation must actually support the claim.
4. Per-claim verdict, one of: **VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE**, EACH accompanied by the **exact span quote** that justifies the verdict.
   - VERIFIED = claim fully supported by the cited span (every number, direction, population, endpoint present).
   - PARTIAL = partly supported; some element (a number, a qualifier, a population) not in span.
   - UNSUPPORTED = claim not found in the cited span.
   - FABRICATED = claim contradicts the cited span, or invents a number/finding not derivable from it.
   - UNREACHABLE = the cited source/span is empty or unavailable, so the claim cannot be checked.

**STRICTLY BANNED (these violate §-1.1 and are themselves lethal in clinical context):**
- Word counts / citation counts / unique-source counts as a quality signal.
- Section counts / byte length / "longer report" as a completeness proxy.
- Pattern presence ("does it mention tirzepatide?").
- Sample-based audits ("I checked 5 of 70 claims").
- String-presence PASS/FAIL or metadata comparison ("X has 27 contradictions, Y has 3, so X is better").

**Completeness, when you assess it, MUST be content-based:** which clinically-relevant interventions does the QUESTION demand, and does each report address them? Name the specific clinical content gaps (e.g., IV iron in HFrEF, toxic-metal cardiotoxicity, TACT2 replication, selenium/calcium/copper outcome trials), not the length.

---

## EVIDENCE ASYMMETRY — READ CAREFULLY

- **POLARIS:** you have the resolved cited span text for every claim (each report sentence paired with the exact `direct_quote[start:end]` substring from POLARIS's evidence pool). You CAN do true span-verification on POLARIS. Do it on EVERY claim.
- **ChatGPT and Gemini:** you have ONLY their narrative text plus inline citation markers (`citeturn…` for ChatGPT, numeric footnotes for Gemini). The fetched source text is NOT available. So for the competitors you CANNOT span-verify; you are limited to (a) internal consistency, (b) clinical plausibility, (c) contradiction with well-established fact, (d) numbers/claims that are implausible or self-contradictory. Scrutinize hard specifics — trial names, effect sizes, p-values, guideline class — for internal coherence. Gemini in sibling questions has fabricated specific trial statistics; scrutinize its IRON-OUT / NNT=8 / RR 0.71 p=0.001 / ESC Class I type claims for internal consistency.

---

## POLARIS PIPELINE ARTIFACTS — NOT clinical claims (do not verdict these)

- Sentences of the form "A claim previously stated here did not survive 4-role verification and was redacted; this is a curator-actionable gap." = POLARIS HONEST DISCLOSURE of a dropped claim. This is a transparency feature, NOT a fabrication. Do not verdict it.
- The "Limitations" block auto-generated stats ("ttr 9.5e12%", "odds ratio 7207.7%", "rel_diff 81.8%") = pipeline contradiction-detector artifacts, NOT clinical claims. Do not verdict them as clinical content (you MAY note if they are misleading to a reader).
- The "V30 Phase-1 Retrieval Coverage Disclosure" + "Contract-bound content … did not survive strict verification … curator-actionable gap" = honest gap disclosures. Not fabrications.

---

## YOUR TASKS

**(1) POLARIS, claim-by-claim against cited spans:** Is there ANY fabrication or unsupported claim? Pay special attention to the UNKNOWN-tier magnesium-bioavailability numbers (87% solubility at 0.72 mEq, 43% at 24.2 mEq, 0.035 vs 0.008 mg/mg creatinine, plasma 0.72/0.69/0.65 mmol/L) and the T1 chelation numbers (N=1708, HR 0.82 [0.69–0.99], median 55 mo) and the iron-MR OR 0.94 [0.88–1.00]. Confirm each number appears in its cited span or flag it.

**(2) ChatGPT + Gemini, claim-by-claim for REAL defects:** within the asymmetry constraint above, find internal contradictions, implausible specifics, or claims that contradict well-established cardiology fact. Be specific (quote the claim).

**(3) Decide the two beat verdicts.** Definition: POLARIS "beats" a competitor iff POLARIS is **more faithful AND completeness is comparable**.
   - **This is an AND gate.** Finding a competitor fabrication does NOT by itself flip the verdict to true — POLARIS must ALSO have comparable clinical-content completeness.
   - Assess completeness by clinical content (see §-1.1 completeness rule above), not length.

---

## REQUIRED FINAL BLOCK (emit verbatim keys, last occurrence is parsed):

```
verdict_beat_chatgpt: true|false
verdict_beat_gemini: true|false
polaris_fabrication_found: true|false
```

Also give a 4–8 line reasoning summary: POLARIS faithfulness (fabrications yes/no with the worst case), POLARIS completeness gaps (named clinical content), and the single biggest defect you found in each competitor.

---
---

# PART A — POLARIS RESOLVED PER-CLAIM CITED SPANS (the §-1.1 audit substrate)

Each block is: report sentence (provenance tokens stripped for readability) + the EXACT cited span substring from POLARIS's evidence pool (`direct_quote[start:end]`). Audit each claim against ITS span. Note: spans derived from `four_role_claim_audit.json` (the report's provenance tokens) + `evidence_pool.json` (the fetched source text). All 7 cited evidence IDs were verified present with non-empty `direct_quote`.

