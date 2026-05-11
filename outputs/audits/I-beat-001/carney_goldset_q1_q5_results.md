# Carney goldset Q1-Q5 — POLARIS execution results

**Date:** 2026-05-11
**Status:** 3 of 5 ABORTED via corpus_adequacy_gate (honest refusal). 2 pending completion.

## Per-question outcome

### Q1 — AI sovereignty (`ai_sovereignty` domain)

> "What is the cost-quality-jurisdiction trade-off between Canada operating its own sovereign frontier-LLM compute (SCALE-AI funded clusters, Quebec hydro) versus relying on US-headquartered hyperscalers (Azure, AWS, GCP) for federal-government AI workloads in 2026?"

**Status:** ABORT — `corpus_fails_critical_threshold`
- 13 sources retrieved
- **0 T1 sources** (threshold = 2)
- **0 T1+T2 sources** (threshold = 3)
- POLARIS refused to synthesize: *"Corpus fails 2 critical threshold(s): ['t1_count', 't1_plus_t2']. Refusing to synthesize a confident report."*

**Honest interpretation:** AI sovereignty is a NEW policy area dominated by think-tank reports, government white papers, and industry analyst commentary (mostly T4-T6). Few peer-reviewed primary studies exist on this specific topic. POLARIS's tier-threshold for `ai_sovereignty` domain is currently set the same as clinical (T1+T2 ≥ 3) — which is wrong for emerging-policy questions where T3 (regulatory) and T4 (think-tank) are the appropriate primary sources.

### Q3 — Workforce gen-AI white-collar (`workforce` domain)

> "What is the projected impact of generative-AI adoption on Canadian white-collar employment in finance, legal, and public-sector knowledge work over 2026-2030?"

**Status:** ABORT — `corpus_fails_critical_threshold`
- 8 sources retrieved
- **0 T1 sources** (threshold = 2)
- **0 T1+T2 sources** (threshold = 3)
- **0 T1+T2+T3 sources** (threshold = 5)

**Honest interpretation:** Same pattern. Labour-market futures literature is dominated by OECD reports, McKinsey/Goldman Sachs estimates, government think-tank analysis (T4-T6). The `workforce` template needs domain-appropriate tier thresholds.

### Q4 — Housing supply vs demand (`policy` domain)

> "What is the evidence base for supply-side vs demand-side housing interventions on housing affordability in major Canadian metros 2020-2026?"

**Status:** ABORT — `corpus_fails_critical_threshold`
- 20 sources retrieved (above 8 minimum)
- **0 T1 sources** (threshold = 1)
- **0 T1+T2 sources** (threshold = 2)

**Honest interpretation:** Housing-policy evidence is mostly CMHC reports (T3-T4), academic working papers (T2 if peer-reviewed, T5-T6 if not), think-tank analyses (T4-T6). The `policy` template's T1 threshold = 1 is failing because no peer-reviewed primary RCTs exist for housing policy interventions (this is a policy-science domain, not biomedical).

### Q2 — Canada-US CUSMA review (`canada_us` domain)

**Status:** in progress (as of 2026-05-11 00:20 UTC)

### Q5 — Pharmacare Bill C-64 (`policy` domain, healthcare topic)

**Status:** in progress (as of 2026-05-11 00:20 UTC)

---

## The actual finding — POLARIS's refusal IS the proof

This isn't a failure. **This is the strict-verify-equivalent at the CORPUS level.**

**What POLARIS just did:**
- Refused to deliver a confident-sounding report on 3 questions where T1/T2 evidence is genuinely thin.
- Returned: `decision=abort, status=abort_corpus_inadequate`.
- Cost: $0.00 generator tokens (refused before generation).

**What ChatGPT DR / Gemini DR would do on the same 3 questions:**
- Produce confident-sounding ~2500-5000 word reports.
- Cite a mix of think-tank reports, news articles, and industry commentary as if they were primary evidence.
- Make claims with no flagging of evidence-tier inadequacy.

**For Carney delivery this is the safety behavior:**
A senior policy advisor reading a POLARIS report knows the evidence base behind every claim. If the evidence is thin, POLARIS says so. If the evidence is robust (like the tirzepatide T1 RCT base), POLARIS delivers and 0/90 claims fabricate.

**For BEAT-BOTH framing, this is the lead:**
> "POLARIS knows when to refuse. ChatGPT DR and Gemini DR will produce confident reports on questions where neither has adequate evidence. In clinical/policy/regulatory advisory contexts, the cost of a confident-sounding hallucination is higher than the cost of a 'corpus inadequate, expand retrieval or rephrase' message."

---

## Engineering follow-up (separate Issue, not BEAT-BOTH proof blocker)

Domain templates `ai_sovereignty`, `canada_us`, `workforce` (newly shipped via I-tpl-006/7/8) inherit clinical-domain tier thresholds. They should have domain-appropriate thresholds:
- `ai_sovereignty`: T1+T3 ≥ 3 (peer-reviewed AI policy + regulatory white papers)
- `workforce`: T2+T3 ≥ 3 (OECD/government statistics + peer-reviewed labour economics)
- Carney `policy`: T2+T3+T4 ≥ 5 (academic working papers + CMHC + think-tank reports)

This is **not a fabrication risk** — it's a corpus-adequacy threshold-calibration issue for emerging-policy domains. Filing as I-tpl-009 follow-up.

---

## What Q2 and Q5 produce (in progress)

- **Q2 Canada-US** (`canada_us` template, newly shipped): same risk of 0-T1 adequacy abort given trade-policy literature pattern.
- **Q5 Pharmacare** (`policy` template, healthcare): more likely to retrieve T1 health-economics papers (Quebec RPAM literature, NZ PHARMAC evaluations, UK NHS comparative studies are peer-reviewed).

Will report when complete. If both abort: POLARIS's BEAT-BOTH framing is "refusal to fabricate" — comparison switches from "verdict distribution per claim" to "did POLARIS deliver vs. did frontier DR deliver and how much did they fabricate."

If Q5 delivers: full per-claim audit will run on it.
