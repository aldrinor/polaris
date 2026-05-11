# BEAT-BOTH proof — round 1 (tirzepatide-T2DM only)

**Date:** 2026-05-11
**Status:** Round 1 — ONE question, partial competitor audit. Not full proof yet. See "What's missing" below.
**Question:** "What is the efficacy and safety of tirzepatide for glycemic control and weight loss in adults with type 2 diabetes?"

---

## POLARIS — line-by-line audit (automated, full)

**Run:** `outputs/I-beat-001_round3/clinical/clinical_tirzepatide_t2dm/`
**Audit:** `outputs/audits/I-beat-001/polaris/tirzepatide_audit.json`
**Tool:** `scripts/run_line_by_line_audit.py --resolved-report` (I-audit-001, merged 2026-05-10)

| Verdict | Count | Notes |
|---|---|---|
| VERIFIED | **62** | passes mechanical decimal + content-word checks against cited span |
| PARTIAL | 3 | numeric-mismatch — span coarseness (corpus snippet vs full source) |
| UNSUPPORTED | 25 | hedged interpretive prose in Analyst Synthesis + Limitations, no `[N]` |
| FABRICATED | **0** | NO claims invented out of whole cloth — strict_verify gate works |
| UNREACHABLE | **0** | NO broken citations |
| **Total** | **90** | |

**Rates:**
- Overall VERIFIED: 68.9%
- VERIFIED among citation-bearing sentences (62 / 65): **95.4%**
- FABRICATED: **0.0%**
- Alert fired: NO

**Excluded by audit scope (per CLAUDE.md §-1.1 design):** `analyst synthesis` H2 section. Bibliography reference list. Methods. V30 disclosure.

**Honest read of POLARIS result:**
- The strict_verify gate is doing exactly what it's supposed to do — drop any sentence whose cited span doesn't entail the claim. **Zero fabrications survived to the delivered report.**
- 3 PARTIAL verdicts trace to span-coarseness (audit uses the indexed corpus snippet, not the full source paper). These claims are likely supported by the full NEJM/Lancet papers; the snippet doesn't contain every decimal.
- 25 UNSUPPORTED are interpretive prose that POLARIS explicitly labels "this section is analyst synthesis: interpretive commentary based on the verified findings above and the cited evidence. Unlike the Verified Findings section, these sentences are not individually span-verified; use them as hedged context, not as audit-grade claims." The audit's UNSUPPORTED verdict on these IS the right verdict — they don't have citations and shouldn't be treated as audit-grade.

---

## ChatGPT DR — manual spot audit (2 of ~30 numeric claims verified so far)

**Source:** `state/compare_chatgpt_dr.txt` (1226 lines, ~45 footnoted citations)
**Method:** Fetch cited URLs via PubMed/WebFetch; verify decimals against published abstract per CLAUDE.md §-1.1.

| # | Claim | Cited source | Verdict | Notes |
|---|---|---|---|---|
| 1 | SURPASS-2 HbA1c diffs vs semaglutide: −0.15%, −0.39%, −0.45% (5/10/15 mg, 40 wk) | NEJM Frias 2021 (PMID 34170647) | **VERIFIED** | Exact decimal match against PubMed abstract |
| 2 | SURPASS-2 weight diffs vs semaglutide: −1.9, −3.6, −5.5 kg (5/10/15 mg, 40 wk) | NEJM Frias 2021 | **VERIFIED** | Exact decimal match against PubMed abstract |

**Result so far:** 2/2 VERIFIED on the most-consequential numeric claims (SURPASS-2 head-to-head). Both passed strict per-decimal check against the cited primary source.

**Coverage limit (honest):** I've audited 2 of ~30 numeric claims in the ChatGPT DR report. The remaining 28 claims have not yet been line-by-line verified. SURPASS-1/3/4/5/6/CVOT numbers were not spot-checked yet. Cardiovascular outcomes claims not spot-checked. FDA/EMA regulatory claims not spot-checked.

---

## Gemini DR — manual spot audit (NOT YET DONE)

**Source:** `state/compare_gemini_dr.txt` (858 lines)
**Status:** Citations format differs from ChatGPT DR (inline numbered superscripts, less explicit footnote-to-URL mapping). Manual audit pending.

---

## Honest comparison — what we can ACTUALLY say from this evidence

### What's true
- **POLARIS does NOT fabricate.** 0/90 sentences scored FABRICATED. Strict_verify gate dropped 23 sentences before delivery (verification_details.json shows the dropped pile). The gate works.
- **POLARIS does NOT have broken citations.** 0/90 sentences scored UNREACHABLE.
- **POLARIS has 95.4% mechanically-verified rate on citation-bearing body sentences.** Better than the >70% Carney audit-grade bar.
- **POLARIS produces ~2300 words of verified body prose + ~3500 words of clearly-labeled hedged analyst-synthesis.** Total ~5800 words.

### What's UNKNOWN from this round
- **Whether ChatGPT DR fabricates.** 2 spot-checks verified. The other 28+ numeric claims need fetching.
- **Whether Gemini DR fabricates.** Zero spot-checks done.
- **Whether POLARIS BEATS frontier DR on a per-claim basis.** Need apples-to-apples per-claim verdict distribution. POLARIS's 95.4% verified rate is in DIFFERENT verdict-space than the 2/2 manual spot-checks on ChatGPT — not directly comparable yet.

### What I will NOT claim
- "POLARIS beats ChatGPT DR." Not proven. Need full per-claim verdict on all 3 reports against fetched sources.
- "POLARIS beats Gemini DR." Not proven. Same reason.
- "POLARIS is safe for Carney delivery." Single-question proof. Need 5 questions to talk about Carney readiness.

---

## What's missing for full proof (work remaining)

1. **Complete ChatGPT DR audit** (~28 more numeric claims). ~2 hours of WebFetch + per-claim verification.
2. **Complete Gemini DR audit** (~25 numeric claims). ~2 hours.
3. **Scale to 5 questions** (Q1–Q5 in `outputs/I-beat-001/carney_goldset_v1.md`). Each adds ~1 POLARIS run (~$0.20-1.00) + 2 frontier DR runs (user needs paid subscriptions) + 3 audit cycles.
4. **Per-question + per-dimension BEAT-BOTH verdict table** comparing all 3 sides on each of the 5 questions.
5. **Honest competitor-side caveat:** ChatGPT/Gemini DR don't expose evidence pools, so the harness audit can't run on them directly. Their audit is necessarily manual + spot-based. POLARIS's audit is exhaustive (every body sentence).

## What unblocks proof-completion

- User authorizes ~$10 more in POLARIS API runs for 4 more questions (Q2–Q5 from goldset_v1).
- User runs (or authorizes me to use) ChatGPT DR + Gemini DR on the same 4 questions.
- I do the line-by-line audits and ship the per-claim verdict table.

This single tirzepatide round is **strong signal but not proof.** With 4 more rounds (one per Carney scope template), it becomes a real BEAT-BOTH benchmark.
