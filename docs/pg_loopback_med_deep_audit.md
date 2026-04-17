# PG_LOOPBACK_MED — Deep Content Audit

**Scope:** line-by-line audit of `outputs/polaris_graph/PG_LOOPBACK_MED_report.md` against
the routed evidence (`loopback/done/resp_*.json`) and the underlying source content
(`loopback/done/req_*.json`). Hard bans from advisor: no metadata counting, no circular
gate tables, no diplomatic softening, no session recap.

Query (fixed): *"What are the proven health benefits and risks of intermittent fasting?"*

---

## Section 1 — Claim-to-Source Trace

Method: for every factual sentence in abstract + 5 sections + key-findings bullets, extract
the sentence verbatim, locate its `[N]`/`[REF:N]` citation, open the `resp_*` file that
produced the underlying atomic fact, trace back to `source_content` inside `req_*`.

### 1.1 Verbatim-grounded claims (category A — faithful)

| # | Report claim | Cite | Source quote (`req_*`) | Verdict |
|---|---|---|---|---|
| A1 | "Alternate-day fasting is defined as a cyclical feeding pattern that entails complete fasting, meaning consumption of no calories, for a period of 24 hours, followed by ad libitum feeding for 24 hours" | [2] | Cochrane PMC6884959: "cyclical feeding pattern that entails complete fasting (consumption of no calories) for a period of 24 hours, followed by ad libitum feeding for 24 hours" | ✓ verbatim |
| A2 | "Time-restricted feeding is defined as complete fasting, meaning consumption of no calories, for at least 12 hours per day with ad libitum feeding for the rest of the day" | [2] | Cochrane: "complete fasting (consumption of no calories) for at least 12 hours per day with ad libitum feeding for the rest of the day" | ✓ verbatim |
| A3 | "umbrella review of 23 meta-analyses with 351 associations across 34 health outcomes" | [7] | PMC10945168: "A total of 351 associations from 23 meta-analyses with 34 health outcomes were included" | ✓ verbatim |
| A4 | "anthropometric (155) and lipid (83) associations over glycemic (57) and circulatory (41) endpoints" | [7] | PMC10945168: "anthropometric measures (n = 155), lipid profiles (n = 83), glycemic profiles (n = 57), circulatory system index (n = 41)" | ✓ verbatim |
| A5 | "WMD -0.89 microunits per milliliter, 95% CI -1.56 to -0.22, P=0.009, I-squared 0 percent" | [8] | Cioffi 2018: "WMD = -0.89 μU/mL, 95% CI -1.56 μU/mL to -0.22 μU/mL; P = 0.009; I2 = 0%" | ✓ numeric verbatim |
| A6 | "Caloric restriction is a popular approach to treat obesity and its associated chronic illnesses but is difficult to maintain for a long time" | [REF:4] | PMC9946909: identical sentence | ✓ verbatim |
| A7 | "IF has beneficial effects equivalent to caloric restriction" | [4] | PMC9946909: "intermittent fasting has beneficial effects equivalent to those of caloric restriction" | ✓ verbatim |
| A8 | "Cochrane protocol primary outcomes are cardiovascular mortality, myocardial infarction, and heart failure" | [2]/[REF:2] | Cochrane: "Primary outcomes: CV mortality, Myocardial infarction (MI), Heart failure" | ✓ verbatim |
| A9 | "Ramadan diurnal intermittent fasting over 29-30 days... on cardiometabolic risk factors in healthy adults" | [REF:6] | Semantic Scholar c3b3425: "Ramadan diurnal intermittent fasting (RDIF; 29-30 days) on cardiometabolic risk factors (CMRF) in healthy adults" | ✓ verbatim |

**Verdict:** 9/9 verbatim claims correctly attributed. No quote fabrication. No number drift.

### 1.2 Title-level-only claims (category B — thin but not unfaithful)

These sentences merely restate a source's **title or scope**, adding no finding.

| # | Report claim | Cite | Evidence depth |
|---|---|---|---|
| B1 | "A systematic review of the impact of intermittent fasting on body composition and cardiometabolic outcomes [3] establishes that IF has been formally evaluated for these outcomes" | [3] | title only — no numbers, no outcome direction |
| B2 | "a study of effects of intermittent fasting combined with exercise on serum leptin and adipokines [5] examines whether adding exercise to IF produces incremental metabolic benefit" | [5] | title only — no finding, no direction |
| B3 | "A review describes time-restricted eating as the clock ticking behind the scenes [REF:9]" | [REF:9] | title metaphor only — zero mechanistic content |
| B4 | "A comparative analysis examines intermittent energy restriction versus continuous energy restriction on cardiometabolic outcomes [REF:10]" | [REF:10] | title only — no pooled estimate, no direction |
| B5 | "A practitioner-oriented review covers intermittent fasting approaches, benefits, and risks [REF:11]" | [REF:11] | title only — no actual benefit or risk enumerated |

**Verdict:** 5 claims are paraphrased titles. The `resp_*.json` files for these sources contain
only 1–2 shallow facts per source (e.g. `"direct_quote": "Time-restricted eating, the clock ticking behind the scenes"`).
The report surfaces them as standalone sentences, which is technically honest but communicates
nothing beyond "a source with this title exists." These bloat the section word counts.

### 1.3 Synthesizer-added interpretive claims (category C — NOT in any `resp_*.json` fact)

Scanned all 11 routed `resp_*.json` files. None contain these phrasings. They were generated by
the synthesizer/composer on top of the extracted facts.

| # | Report sentence | Extraction status | Risk |
|---|---|---|---|
| C1 | "Clinical translation should present intermediate-outcome benefits without extrapolating to disease-prevention claims" (abstract, uncited) | **not in any atomic_fact** | fabricated clinical recommendation |
| C2 | "The Cochrane-protocol primary outcomes... have not yet been established for IF; current evidence remains biomarker-focused" | reasonable inference (a protocol ≠ a finding), but not source-extracted | unsupported hedging framed as finding |
| C3 | "The most robust glycemic signal is a reduction in fasting insulin" | editorial qualifier; Cioffi 2018 found this was the **only** significant secondary outcome — "most robust" implies comparison across many strong signals when in fact the other glycemic outcomes were null | misleading compression |
| C4 | "Formal Cochrane-protocol definitions anchor a three-protocol taxonomy — alternate-day fasting, time-restricted feeding, and 5:2" | Cochrane source defines **five** types (PF, ADF, mADF, TRF, religious). 5:2 is a **subset of PF** (25% cal 1–2 days/wk), not a protocol parallel to ADF/TRF complete-fast | synthesizer fabricated a taxonomy that conflicts with the source it cites |
| C5 | "Taken together, the routed claims support an equivalence framing rather than a superiority framing" | synthesis overlay; supported loosely by [4] | editorial framing, acceptable |
| C6 | "emphasises adherence as a plausible first-order mechanism mediating equivalence with continuous energy restriction" | no atomic_fact mentions "first-order mechanism" or "mediating equivalence" | synthesizer philosophizing |
| C7 | "This framing provides public-health context but is not a peer-reviewed effect estimate" | epistemic caveat, useful but not extracted | editorial overlay |

**Verdict (C):** 7 interpretive sentences were invented by the synthesizer. C1 is the worst
offense — a medical-practice recommendation with no citation. C4 is factually wrong about
what the cited source says.

### 1.4 Missing content (category D — gap versus query)

The query explicitly asks for **"benefits AND risks"**. The report has detailed benefit
analysis and **zero risk analysis**. The underlying sources contain risk content that never
propagated to the report:

| Source | Risk evidence in `source_content` | In report? |
|---|---|---|
| PMC9946909 (narrative review) | "some participants who participated in IF trials experienced reductions in bone density and lean body mass" | ❌ |
| PMC10945168 (umbrella review) | "Cienfuegos et al. reported adverse events from 4- and 6-h TRE interventions, such as dizziness, nausea, headache, and diarrhea. Harvie et al. also reported side effects of IF interventions, including physical symptoms like feeling cold and constipation, as well as psychological symptoms like headache, lack of energy, irritability, and difficulty concentrating" | ❌ |
| PMC10945168 | "our UR did not perform a quantitative analysis of the side effects of IF" | ❌ |
| Cochrane PMC6884959 | Secondary outcomes include "Incidence of headaches (side-effect), Incidence of dizziness, Incidence of weakness" and quality of life scales | ❌ |

**Root cause:** the source-analysis prompt extracted mostly statistics and methodology facts
from these sources. The **risk-relevant sentences** were available in the `source_content`
delivered to the analyzer but the analyzer prioritized pooled effect sizes and taxonomy. The
downstream pipeline (STORM, outline, section routing) never forced "Risks" as a required
section. Abstract claims to cover "benefits and risks" but there is no section on risks.

### 1.5 Cherry-picking / selection bias (category E)

Cioffi 2018's **primary** finding (body weight, the main outcome):

> "no significant benefit of IER over CER on weight loss (WMD -0.61 kg, 95% CI -1.70 to 0.47;
> P = 0.27), glucose (WMD -0.49 mg/dL, 95% CI -1.98 to 0.99; P = 0.51), glycated haemoglobin
> (HbA1c) (WMD -0.02%, 95% CI -0.10% to 0.06%; P = 0.62) and triglyceride concentrations
> (WMD -3.11 mg/dL; P = 0.36)"

The report mentions **only** the one significant secondary outcome (fasting insulin) and
labels it "most robust glycemic signal." It omits that Cioffi's headline result was that
IER did **not** outperform CER on weight loss, glucose, HbA1c, or triglycerides. A faithful
summary of Cioffi would read: *"IER matched but did not exceed CER on weight loss and most
glycemic/lipid outcomes, with a single exception: fasting insulin, where IER reduced levels
by -0.89 μU/mL (p=0.009)."* Instead the report presents the positive signal without the null
context. This is the **orphaned-positive-outcome** pattern that AMSTAR-2 and PRISMA flag as
reporting bias.

### 1.6 Citation-format inconsistency (category F — code bug)

Same citations appear in two formats within the same document:

- Abstract + §1 + §2 + §5's "A practitioner-oriented review" line → `[1]`, `[2]`, `[4]`, `[7]`, `[8]`, `[11]`
- §3 + §4 + §5's other lines → `[REF:6]`, `[REF:8]`, `[REF:7]`, `[REF:4]`, `[REF:9]`, `[REF:10]`, `[REF:2]`

The `[REF:N]` token is the **pre-resolution** marker used internally before citation_mapper
substitutes `[N]`. Its presence in the final report means citation_mapper did not process
sections 3/4/5 for at least some citations. This is a real downstream bug: either
(a) `citation_mapper.py` is running on only the first N sections, or (b) some late-added
post-remediation sections were composed with `[REF:N]` and never re-resolved.

Impact on readers: the report looks unprofessional and cross-references break for any tool
that parses `[N]` back to bibliography position.

---

## Section 2 — Node-by-Node Reasoning Audit

Inspected `logs/pg_loopback_medium.log` for decisions made by each pipeline node.

### Node: `plan` (QueryPlan)
- Produced the queries that fed Serper/S2. Loopback responses are Tier-A auto-served.
  Not visible in the run log at claim level — queries went into the search node.
- **Gap:** no log line confirms the query plan actually specified a "risks" vector. This
  aligns with §1.4: absence of risk-specific queries means risk content was never searched for.

### Node: `search` + `fetch`
- Fetched 11 sources (Cioffi, Cochrane, PMC10945168, PMC9946909, Ramadan RDIF, UIC, MGB,
  Mass General, Frontiers TRE mechanisms, Frontiers IER vs CER, NPJournal practitioner review).
- **BUG-5 fix fired:** `"BUG-5 FIX: Dropped 1 stub-content sources... 'are you a robot' in short content (351 chars)"` — correctly caught a paywall/captcha stub.
  - Trigger marker was "are you a robot" + 351-char content length (well below 2 KB).
  - This validates the STRONG-marker path. WEAK-marker path did not fire — no evidence of regression.

### Node: `analyze` (SourceAnalysisBatch)
- 11 operator-served batches (7 in `_serve_batch_sources.py`, 4 in `_serve_batch_sources2.py`).
- Atomic facts extracted: total ~30 `atomic_fact` entries across all batches.
- **Concern:** per-source fact counts are low (2–5 per source vs the 8–15 the prompt
  requires). The loopback responses under-delivered because the operator (me) authored them
  conservatively. A real GLM-5.1 run would produce more facts per source.
- **Quality-of-extraction issue:** facts skew heavily toward methodology and stats; almost
  no facts were extracted about side-effects despite multi-paragraph risk content in the
  narrative review and umbrella review. This is the root cause of the §1.4 gap.

### Node: `verify` (claim verification)
- Log shows claims were verified but `NLI_ENABLED` status and `is_faithful` distribution
  not surfaced at top of log. The final report has high reported faithfulness because
  verifier defaults are permissive when quotes match. The verifier catches **quote drift**
  but not the **synthesizer-added interpretive claims** (C1–C7) because those have no quote
  to verify against — the synthesizer invented them on top of verified atomic facts.

### Node: `synthesize` (section writer + composer)
- Wrote 5 sections. Per-section claims are anchored to `[CITE:ev_xxx]` tokens that resolve
  to `[N]`. This is where C1–C7 were introduced — the writer expanded terse atomic facts
  into prose and injected glue sentences.
- `_compose_abstract` called twice (per BUG-70 fix): once pre-remediation, once post.
  Log confirms: `"REMEDIATE: Abstract regenerated from rewritten sections (1353 chars)"`.
  - The final abstract is the post-remediation version. Compared to pre-remediation, this
    change is invisible in the final artifact (no pre-remediation text leaked through).

### Node: `remediate` (hallucination rewrite)
- Log: `"REMEDIATE: 3/3 flagged sections rewritten"`.
- Inspected `hallucination_audit` field in `PG_LOOPBACK_MED.json`. Per-section state **as
  stored is pre-rewrite**:

  | section | pre-rewrite ratio | needs_rewrite | unsupported / total |
  |---|---|---|---|
  | s01 Definitions | 27.27% | **False** | 3/11 |
  | s02 Efficacy | 30.00% | **False** | 3/10 |
  | s03 Cardiometabolic | 72.73% | True | 8/11 |
  | s04 Mechanisms | 84.62% | True | 11/13 |
  | s05 Methodology | 93.33% | True | 14/15 |

- Sections 3, 4, 5 were rewritten (matches log "3/3"). Compared flagged pre-rewrite spans
  against the current report text:
  - s03 pre-rewrite: `"A foundational meta-analysis (Cioffi 2018) reports..."` → **replaced**
    in final by `"A pooled analysis reported fasting insulin levels significantly lower..."`
    Rewrite stripped the "foundational" characterization and the unverified narrative overlay
    `"This insulin-sensitivity signal is among the most statistically robust findings in the
    IF versus CER comparison literature."` → gone from final. **Rewrite worked here.**
  - s04 pre-rewrite: `"Adherence is the first-order mechanism."` → **gone**. Overlay
    `"Intermittent fasting's potential advantage is therefore adherence-mediated..."` →
    **gone**. Current s04 is terse (3 paragraphs, 3 facts).
  - s05 pre-rewrite: 14/15 claims flagged. The massive `"Research priorities are
    straightforward..."` paragraph → **gone** from final. Final s05 is stripped to 3 facts.
- Sections 1 and 2 were **not rewritten** (ratio below 0.40 threshold). Interpretive overlays
  in those sections **survived to final report**:
  - s01: `"This framing provides public-health context but is not a peer-reviewed effect
    estimate"` (nli=0.414) — survived. This is audit-category C7.
  - s02: `"Specific pooled effect sizes with confidence intervals were not included in this
    section's claim set and therefore cannot be quoted here"` (nli=0.104) — survived.

- **False-positive on verbatim quote:** s01 flagged the ADF definition sentence at nli=0.387
  even though the sentence is near-verbatim from the Cochrane source. NLI model
  (MiniCheck flan-t5-large) is scoring the added framing word `"defined as"` as unsupported
  because the direct_quote premise starts at `"cyclical feeding pattern..."`. Same false-
  positive pattern noted in MEMORY.md item 19 (niche-domain over-strictness).

- **Abstract is not audited.** The `hallucination_audit` list contains only `s01`–`s05`,
  no `abstract` entry. The compose_from_wiki BUG-70 fix regenerates the abstract post-remediation
  but **no second NLI pass runs on the regenerated abstract**. Interpretive overlays in the
  abstract (C1 clinical recommendation, C3 "most robust glycemic signal", C4 three-protocol
  taxonomy) are therefore **guaranteed to survive** because nothing audits them.

### Node: `entropy` (FIX-ENTROPY)
- Log: `"FIX-ENTROPY: perspective_entropy=0.786 (24 evidence, 5 perspectives: {Scientific: 12, Methodological: 5, Regional: 1, Emerging_Trends: 1, Public_Health: 5})"`
- 5 perspectives represented, entropy 0.786 > 0.55 threshold. No perspective-starvation
  gate triggered.
- **But:** `Regional=1, Emerging_Trends=1` are single-source perspectives. The Regional
  evidence (Ramadan RDIF) gets its own section. Emerging_Trends (TRE mechanisms review)
  gets a paragraph that contains only a title metaphor (B3). Entropy computation rewards
  representation, not substance, so single-fact perspectives pass the gate with near-zero
  actual content.

---

## Section 3 — Industrial-Standards Evaluation

### 3.1 PRISMA 2020 (systematic-review reporting)

The report claims to be a "systematic review" in its abstract. PRISMA 2020 checklist items:

| Item | Status |
|---|---|
| 4. Eligibility criteria | ❌ not stated |
| 5. Information sources | ❌ not named (Serper, S2, DDG never surfaced) |
| 6. Search strategy | ❌ full strings not shown |
| 7. Selection process | ❌ not described |
| 10. Effect measures | ⚠️ one effect measure (WMD -0.89) reported |
| 12. Risk of bias | ❌ not assessed |
| 13. Synthesis methods | ❌ not described |
| 14. Certainty assessment | ❌ GRADE/AMSTAR mentioned once but not applied to this review's own findings |
| 18. Study selection flow | ❌ no PRISMA flow diagram |
| 23. Limitations | ❌ not discussed |

**Verdict:** the report calls itself a "systematic review" but fails ≥8 PRISMA items. It is
a **narrative overview**, not a PRISMA-compliant SR. Using the term "systematic review" in
the abstract is misleading.

### 3.2 AMSTAR-2 (critical appraisal of SRs)

The umbrella review [7] applied AMSTAR to its inputs. But this report itself would fail
AMSTAR-2 as a review: no protocol registration, no PICO statement, no exhaustive search
description, no list of excluded studies, no risk-of-bias per study, no discussion of
heterogeneity or publication bias.

### 3.3 GRADE (evidence certainty)

No GRADE certainty ratings attached to any claim. The report cites a source that used GRADE
(`"53% of associations supported by over moderate quality"` — from PMC10945168) but does
not propagate those certainty tiers into its own claims. Claims are presented with
equivalent authority whether they are single-RCT findings (Cioffi 2018 WMD -0.89 is a
meta-analytic pooled estimate from 11 RCTs) or single-study observational title-paraphrases.

### 3.4 RAGAS / faithfulness metrics

- **Faithfulness (claims provably derived from evidence):** ~9/~23 verifiable factual
  sentences are verbatim-grounded. The rest are either title paraphrases (thin but not
  unfaithful) or synthesizer interpretive overlays (unsupported).
- **Answer relevance:** moderate. The query has two axes (benefits, risks). The report
  covers benefits in depth and omits risks entirely. This is a ~50% axis coverage failure.
- **Context precision:** most cited evidence is directly on-topic for IF. Off-topic paper
  PMC10474717 (physical-activity SR) was correctly tagged OFF-TOPIC with `source_quality=0.4`
  in `_serve_batch_sources.py:36` and did not propagate into claims.

### 3.5 Ottawa Evidence-pyramid hygiene

The report cites:
- 1 umbrella review (highest) [7]
- 1 Cochrane protocol (highest design but not yet a finding) [2]
- 2 meta-analyses (Cioffi 2018, Ramadan RDIF) [8][6]
- 1 practitioner review (blog-grade) [11]
- 3 narrative reviews [4][9][10]
- 1 institutional press release [1] (UIC)
- 1 academic-medical-center public article [REF:?] (MGB — not cited in final)

**Mixing tiers without tiering:** claims from UIC press release [1] sit next to claims
from umbrella review [7]. No hierarchy indicator. Best practice: either weight claims by
tier or exclude lower tiers when higher-tier coverage exists.

### 3.6 CONSORT / STROBE

Not applicable (this is not a primary trial report).

### 3.7 Quote hygiene

All 9 verbatim quotes trace back to source text without alteration. No sign of quote-splicing
or word-swapping. Numeric claims match to the last digit (WMD -0.89, 155/83/57/41, 23/351/34).

---

## Section 4 — Three Decision Questions

### Q1. What is the actual defect rate at the claim level?

Denominator: ~23 factual sentences in the body of the report (excluding bibliography and
key-findings which repeat section content).

| Class | Count | % |
|---|---|---|
| A. Verbatim-grounded to source | 9 | 39% |
| B. Title/scope-level only (thin) | 5 | 22% |
| C. Synthesizer-added interpretive (unsupported) | 7 | 30% |
| Citation-format inconsistency ([REF:N] leak) | ~6 affected lines | — |

**Claim-level defect rate:** 30% unsupported synthesizer overlays + 22% thin title-paraphrases
= 52% of claims are below "verbatim-supported finding" grade.

**Systemic defect:** 100% of the "risks" axis of the query is missing from the report.

### Q2. What did the medium run prove versus the minimal run?

**Medium run's unique contributions (beyond minimal):**
1. BUG-5 stub-content filter **fired in production** — log confirms 1 paywall source dropped.
2. BUG-70 abstract-post-remediation **fired** — log confirms 2 compose calls.
3. BUG-3 perspective-tagged embeddings **did not fail** (entropy 0.786 ok) but cannot be
   confirmed to have routed perspective-specific evidence to safety/regulation sections because
   **those sections don't exist in the output** — there is no safety section to check.
4. Shape-drift guardrails (Pydantic) did not reject any response.
5. Citation-format inconsistency surfaced — a **new** defect that minimal would not have
   exposed because minimal ran fewer sections.

**What medium did not prove:**
- Did not prove the pipeline produces a balanced benefits/risks report for this query. It produced benefits-only.
- Did not prove hallucination-remediation catches interpretive overlays (C1–C7 survived).
- Did not exercise the GLM-5.1 code path, because the loopback serves canned responses.
- Did not exercise adversarial prompts (only one query).

### Q3. If the 3 code-level fixes (BUG-70, BUG-5, BUG-3) had been absent, which defects above would remain?

| Defect | Would BUG-70 fix affect it? | Would BUG-5 fix affect it? | Would BUG-3 fix affect it? |
|---|---|---|---|
| 30% synthesizer overlays (C1–C7) | no — BUG-70 regenerates abstract but does not audit prose for interpretation | no | no |
| 22% title-paraphrase thinness | no | no | no |
| 100% missing-risks axis | no | no | no — BUG-3 routes existing evidence better, does not generate new evidence |
| [REF:N] citation leak | no | no | no |
| Cherry-picked Cioffi positive | no | no | no |
| Five-vs-three-protocol taxonomy error | no | no | no |

**Conclusion:** the 3 code fixes validated in this run are **necessary but far from sufficient.**
None of them address the top-5 content defects. Production-readiness judgment based solely on
the 3 fixes firing is **premature**.

---

## Recommendations (ranked by ROI)

1. **Force a "Risks and Side Effects" section** via outline template. The query explicitly
   asks for risks; the pipeline must guarantee axis coverage independent of what evidence is
   retrieved. Either (a) outline schema requires a "risks" section when the query contains
   "risks"/"harms"/"side effects"/"adverse", or (b) the QueryPlan stage generates
   risk-specific search vectors alongside benefit ones.

2. **Fix citation_mapper to normalize `[REF:N]` → `[N]` across all sections** including
   post-remediation ones. Add a post-compose assertion: no `[REF:` tokens survive.

3. **Synthesis-overlay audit:** LettuceDetect / NLI verifier catches quote drift but not
   interpretive synthesis. Add a second-pass check: each non-quote sentence in a section
   must be paraphrasable to at least one atomic_fact in that section's evidence pool.
   Sentences that cannot be grounded (C1 "Clinical translation should..." is the archetype)
   should be flagged for rewrite or deletion.

4. **Cherry-pick detection:** when reporting a significant finding from a meta-analysis,
   either cite all the outcomes the meta-analysis reported or note "only 1 of N outcomes
   reached significance." Do not compress a null-dominated study into a "most robust signal"
   headline.

5. **Taxonomy sourcing:** the three-protocol taxonomy in the abstract cites [2] but
   contradicts [2]'s five-type definition. Either cite a source that actually uses a
   three-protocol taxonomy, or reword to "three commonly studied protocols" (which is
   supported by [REF:4] narrative review's own framing).

6. **Bibliography authors:** the 100%-Unknown authors is a loopback artifact (my responses
   had `"authors": []`). In a real paid run, OpenAlex/Crossref metadata would fill this.
   Confirm this gap vanishes in the Phase-7 paid GLM-5.1 run before shipping.

7. **Do not label the report "systematic review"** unless PRISMA 2020 items 4-23 are met.
   Rename abstract framing to "narrative synthesis" or "evidence overview."

---

## Bottom line

The 3 bug fixes all fired correctly and the loopback dispatcher held together. But the
output content is a **benefits-only narrative overview with ~30% unsupported interpretive
overlays and 100% missing risks coverage**, labeled inaccurately as a "systematic review."

**Pipeline-level findings from the `hallucination_audit` field:**

- The NLI rewrite pass did its job on sections 3/4/5 (the worst offenders, 72%/85%/93%
  pre-rewrite). Those sections are now stripped to verifiable facts in the final report.
- The 0.40-ratio threshold that decides whether to rewrite is too lenient for sections 1
  and 2: s01 had 27% and s02 had 30% flagged, both below threshold, both shipped with
  interpretive overlays intact (C5, C7, and the section-2 caveat sentence).
- **The abstract is never audited at all.** There is no `abstract` entry in
  `hallucination_audit`. BUG-70 fix regenerates the abstract after remediation but does not
  run NLI on the regeneration. C1 (fabricated clinical recommendation), C3 (misleading
  "most robust" qualifier), and C4 (three-protocol taxonomy that contradicts the cited
  source) all live in the abstract and are therefore **systemically outside the verification
  loop**.
- NLI has **false positives on verbatim quotes** (s01 ADF definition flagged at nli=0.387
  despite being nearly word-for-word from source). This means the rewrite threshold is
  operating on noisy signal; a section could be rewritten to remove a verbatim quote because
  the NLI model didn't entail on added framing words.

**Green-lighting the paid GLM-5.1 Phase-7 run on the basis of this loopback alone is
optimistic.** Minimum additional gates before spending real money:

1. Outline schema must include a "Risks" or "Safety" section when the query contains
   "risks"/"harms"/"side effects"/"adverse".
2. `[REF:N]` tokens must not survive to final report — add assertion in composer.
3. The abstract must be audited by the same NLI pass as body sections (or subject to a
   stricter "only sentences paraphrasable to an atomic_fact from the body" rule).
4. Rewrite threshold for NLI ratio should be lowered from 0.40 to ~0.25 — or audit framing
   separately from substance so verbatim quotes don't pull a whole section below threshold.
5. The synthesizer prompt must forbid uncited clinical recommendations (C1 pattern).

None of these require the paid LLM — they are outline schema, composer logic, and NLI
threshold changes. Recommend tightening these **before** committing to the Phase-7 spend.
