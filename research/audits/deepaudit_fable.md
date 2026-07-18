# FABLE 5 DEEP AUDIT — run B (0.3610) vs A (0.3992) vs champion (0.4447)

Auditor: FABLE 5, maximum depth. Source: `deepaudit/pack.md` (read in full, 396 lines).
Scores used throughout: **A (faith OFF) 0.3992 | B (faith ON) 0.3610 | champ_ourcorpus 0.3671 | TRUE CHAMPION 0.4447 | fable5_scoped_calibration 0.5065.**

Two bookkeeping flags before the questions (neither changes the verdict, both should be fixed in the pack):

- The pack says "Raw LLM draft = ... ~145 sentences" but strict_verify adjudicated 147 dropped + 55 verified = **202** sentences. Either the ~145 estimate is wrong or verify splits sentences before judging. 
- `drop_reason_counts` sums to 66+21+15+11+9+8+1 = **131**, not 147. Sixteen drops are unaccounted in the histogram — at least one is `no_provenance_token` (DROP 20), which does not appear in the counts at all.

---

## Q1 — Were the 34 shown drops GOOD content, and what did the 147 drops cost?

**Verdict: ~22 of 34 (65%) are dense, true, on-topic, cited content wrongly killed; ~9 of 34 (26%) are the LLM's own content-free pointer sentences that deserved to die (though the verifier killed them for the wrong reason); ~3 are borderline interpretive add-ons whose base fact survived elsewhere.**

### Class 1 — Good content wrongly killed (DROPs 1, 2, 4, 5, 7, 8, 9, 10, 11, 13, 14, 15, 21, 22, 23, 24, 30, 31, 32, 33, plus 25)

Line-by-line on the strongest cases:

- **DROP 2 / 10 / 24 / 30 — the McKinsey range, killed FOUR times, zero copies survive.**
  > "The McKinsey Global Institute forecasts that automation could displace 75 to 375 million workers by 2030 [#ev:ev_225:2700-3500]..." — `REASON: no_integer_overlap_any_cited_span:...missing=['375']`
  The 75–375M-by-2030 figure is the single most-cited automation forecast in this literature (the true champion's intro is built on exactly this genre: "85 million jobs may be displaced while 97 million new roles may emerge... 75 million jobs redundant and create 133 million"). The sentence's other numbers (75, 800, 2030) matched; only `375` failed the byte-window test. The fact appears in FOUR sections of the draft and is **entirely absent from the final scored text** — final B carries only the companion "800 million jobs by 2030" clause. Comprehensiveness loss, direct.

- **DROP 3 / 11 / 23 / 31 — the retail-decline stat, killed FOUR times under THREE different reasons, zero copies survive.**
  > "retail sales occupations declined by 850,000 jobs between 2013 and 2023, with their employment share dropping from 7.5 to 5.7 percent, a reduction of 25 percent [#ev:ev_307:8100-8900]" — killed as `binding_qualifier_dropped` (3, 11, 23) and `number_not_in_any_cited_span:...missing=['5.7', '6.5', '7.5']` (31).
  This is true BLS-derived content from ev_307 — the same source the final successfully cites for the STEM stat ("STEM employment grew from 6.5% of all jobs in 2010 to nearly 10% in 2024" survives in final section 1). The verifier proved ev_307 contains 6.5 by verifying it in one sentence, then killed DROP 31 for `missing=['6.5']` because a different byte window was cited. **Same document, same number, different offset → drop.** The displacement half of the displacement/creation contrast is gone; final's "How AI Technologies Displace and Create Jobs" section now contains only the creation side ("light delivery service truck drivers grew by 29 percent... stockers and order fillers increased") with the dangling connective "Simultaneously, downstream job creation has occurred" — *simultaneously with what?* The antecedent was dropped.

- **DROP 5 / 14 — the 47% wage premium, killed twice, survived only by luck.**
  > "...earning 47% more on average than less-exposed workers [#ev:ev_312:0-800]" — `missing=['47']`
  The final scored text contains "earn 47 percent more on average" **twice** (Skill Demand section and AI's-Labor-Market-Effects section), verified from the same ev_312 via other spans. So `47` is demonstrably in the document; the window 0-800 just doesn't contain it. These two drops cost nothing only because a third copy happened to cite a luckier offset — the mechanism is a coin flip, not a check.

- **DROP 9 / 21 — the post-1987 displacement acceleration, killed twice, zero copies survive.**
  > "From 1987 to 2017... displacement accelerated to 0.7 percent per year while reinstatement slowed to 0.35 percent per year, contributing to weaker wage growth of 1.3 percent per year" — `number_not_in_any_cited_span:...missing=['0.35', '0.7', '1.3']`
  These are Acemoglu–Restrepo's actual JEP decomposition numbers — the *mechanism* behind the era comparison. Final B keeps the 1947–1987 side ("displacement effect reduced labor demand at about 0.48% per year... reinstatement effect of 0.47% per year") and the consequence ("deceleration of wage bill growth to 1.33 percent per year") but lost the modern-era displacement/reinstatement rates that make the comparison an insight. The true champion covers the same ground qualitatively: "stronger displacement effects and considerably weaker reinstatement effects in recent decades." We had it with numbers; the verifier deleted it.

- **DROP 8 — the reinstatement effect itself.**
  > "Acemoglu and Restrepo's task-based framework identifies a displacement effect... and a reinstatement effect, whereby new technologies generate new labor-demanding tasks" — `verdict=NEUTRAL:reason=The span mentions 'new task generation' but does not explicitly mention the 'rei[nstatement effect]'`
  The NLI judge concedes the span says "new task generation" — which IS the reinstatement effect — but drops the sentence because the span doesn't use the word. The final is left with the grammatically broken residue: "describes a displacement effect, whereby capital takes over tasks previously performed by labor, **and new task generation**." Compare the champion, which devotes a full section to this framework ("Countervailing the displacement effect is the reinstatement effect, which is the polar opposite of displacement..."). This single drop lobotomized the report's core theoretical framework.

- **DROP 22 — college wage premium, unique fact, gone.** "share of hours worked by college-educated workers nearly doubling from 20 percent in 1979 to 39 percent in 2018, and the experience premium rising from roughly 67 percent in 1980 to 91 percent in 2018" — `missing=['67', '91']`. Nothing like it survives; skill-biased technical change is now asserted in the final without its evidence.

- **DROPs 13 / 32 / 4 — the "through 2034" horizon.** The 0.6pp-per-10pp BLS fact survives in the final (three times, in fact), but every variant carrying the projection horizon was killed ("The sentence adds the specific timeframe 'through 2034' which is not present in [the span]"). The final states a growth-projection decline with no time horizon — degraded precision.

- **DROPs 1, 7, 15, 16, 25, 33 — synthesis/framing sentences killed as NEUTRAL** for "introduc[ing] specific claims" — i.e., for doing synthesis. DROP 33 (AI reshaping "political and economic landscapes") happens to survive via a near-duplicate in final section 1; DROP 15's developing-nations point survives partially. DROP 1 (Industry 4.0 debuting at the 2011 Hannover Fair, cyber-physical systems definition) is gone entirely — a definitional anchor the champion's intro provides via Schwab 2016.

### Class 2 — Deserved to die: the pointer sentences (DROPs 6, 17, 18, 19, 26, 27, 28, 29, 34)

> "The 13-fold surge in global AI business investment through 2023 **is detailed under AI and the Fourth Industrial Revolution: Context for Labor Market Transformation** [#ev:ev_000:1200-2000]."

Nine of the 34 shown drops are this template: a fact reduced to a cross-reference to another section. These carry zero Insight/Comp value and would hurt readability if kept. Two corrections to the record follow:

1. **The prior audit's "deferral-pointer disease" was not hallucinated out of nothing — it exists in the RAW DRAFT** (9/34 shown drops, likely ~25–30 of the 147 by extrapolation). It does not exist in the final text because strict_verify deleted every instance. The prior audit's error was locating it in the final text and treating it as the main disease; the operator's error is calling the draft fully "clean." The draft has a real prompt-side tic that wastes ~15–20% of its sentence budget on self-references.
2. strict_verify kills them for the wrong reason (`entailment_failed... The SENTENCE introduces a specific section title... not present in the SPAN` — trivially true forever: no source span can entail *our own section headings*), so the kills are right by accident. These sentences should never be generated, and the number matcher's `missing=['-1987']` on DROP 6 (see Q2) shows even the pointer kills route through buggy machinery.

### Class 3 — Borderline (DROPs 12, 16, 20)

DROP 12 and 16 append interpretive clauses ("reflecting rising demand for new technical skills", "underscoring the urgency") to facts that survive elsewhere; cost ≈ 0. DROP 20 is `no_provenance_token` on an uncited **topic sentence** ("AI adoption is fundamentally reshaping the task content of production..."). Requiring provenance tokens on framing/topic sentences is why final B's sections open mid-thought ("The BLS corroborates this productivity slowdown" — corroborates *what*? The antecedent was dropped).

### Quantified cost of the 147 drops

- **Measured, total:** A − B = 0.3992 − 0.3610 = **−0.0382 RACE (−9.6% relative)** from turning the faithfulness gate on. That is the whole-pipeline cost of the 147 drops net of everything.
- **Text:** −1,274 words net (−22%); since render *adds* chrome, verify alone removed more than that.
- **Unique high-value facts erased outright** (all copies killed): McKinsey 75–375M; retail 7.5%→5.7%/−850k/−25% plus retail productivity 4–5% vs 2%; post-1987 displacement 0.7 vs reinstatement 0.35; college-hours 20%→39% and experience premium 67%→91%; Hannover 2011 / cyber-physical definition; the "through 2034" horizon; the *named* reinstatement effect. That's ~7 distinct empirical anchors — Comprehensiveness — plus the discourse damage (orphaned anaphora: "this productivity slowdown", "over this later period", "This negative shift", "Simultaneously") — Readability/Insight.
- **Extrapolating shown→147** using the reason histogram: 45 number-class drops (essentially all good content, see Q2), 8 binding_qualifier (all four instances shown are the dense retail fact), ~38 of the 66 NEUTRAL drops good synthesis (in the shown sample, 8 of 19 NEUTRAL drops are pointers, 11 are substantive), 11 no_content_word_overlap unknown. **Estimate: ~90–100 of the 147 drops were good content; ~30–40 were self-inflicted pointer spam; only 2 sentences in the whole report were actually CONTRADICTED.** The gate ran at a 73% drop rate to catch 2 falsehoods.

---

## Q2 — The number-mismatch class (45 drops): faithfulness win or self-inflicted wound?

**Self-inflicted wound. Not one of the 45 is a wrong number; the check verifies citation-offset bookkeeping, not factual accuracy.** Three proofs from inside the pack:

1. **The verifier refutes itself on ev_312.** DROPs 5 and 14 die on `missing=['47']` against `ev_312:0-800`, while the final scored text — built exclusively from strict_verify-PASSED prose — says "Workers in the most AI-exposed professions **earn 47 percent more on average**... are **16 percentage points more likely to be female**... **17.4 percent** of the most exposed group versus **4.5 percent**," grounded in the same ev_312. The number is in the document. The sentence cited an 800-byte window that starts too early.
2. **The verifier refutes itself on ev_307.** DROP 31 dies on `missing=['5.7', '6.5', '7.5']`; the final carries "STEM employment grew from **6.5%** of all jobs in 2010 to nearly 10% in 2024," verified from ev_307. Same document, same digits, different window → one copy passes, one dies. A gate whose outcome depends on which byte offset the LLM guessed is a lottery, not a faithfulness check.
3. **The matcher has a parsing bug.** DROP 6: sentence "The **post-1987** weakening of wage growth..." → `REASON: no_integer_overlap_any_cited_span:ev_001:missing=['-1987']`. It tokenized "post-1987" as the signed integer −1987 and then demanded the string "-1987" appear in the source span — which no source will ever contain. Any drop class that can be triggered by a hyphen is not measuring faithfulness.

Additionally, the multi-citation cases show a design flaw: DROP 2/10/24 cite **two** spans (`ev_225:2700-3500` for the 75–375M clause, `ev_128:600-1400` for the 800M clause) and each clause is supported by its own span, but the checker requires every number to appear in *some* cited span as a bag, then fails on windowing anyway. Legitimate two-source synthesis — exactly what a literature review is for — is structurally penalized.

**What a real faithfulness win would look like:** catching a sentence whose number differs from the source. Count of those among the 45: **zero shown, and the pack stipulates the class is "correct number, not in exact cited byte-span."** With only 2 CONTRADICTED verdicts in 202 sentences, the number gate spent 45 kills to catch 0 lies. It converts the LLM's imprecise byte-offset guesses — a citation-format problem, fixable mechanically — into deleted content. Wound, entirely self-inflicted.

---

## Q3 — Raw draft vs final: what did verify + render each do?

**verify (strict_verify):** removed 147 of 202 sentences (73%), −1,274 net words. Secondary damage beyond deletion: broken discourse (section "Skill Demand..." opens "The BLS corroborates **this productivity slowdown**" with the slowdown sentence dropped; "Labor Market Polarization" opens "**The consequence** has been a deceleration..." with no cause in sight; "**this later period**", "**This negative shift**" dangle), a grammatically broken framework sentence ("describes a displacement effect... **and new task generation**" — DROP 8's residue), and one-sided arguments (creation without displacement in the sector section).

**render:** injected everything the raw draft does not contain. Confirmed by direct comparison:

- **Title — render-injected, confirmed by source.** Raw draft (Evidence 2) begins with the clean LLM title "AI Adoption Rates and Employment Outcomes by Industry" and clean section headings. Final (Evidence 3) begins:
  > `# Research report: Please write a literature review on the restructuring impact of Artificial Intelligence (AI) on the labor market. ... Ensure the review only cites high-quality, English-language journal articles.`
  The *prompt*, including its imperative instructions, as the H1 of the scored document. The mangling source is quoted in Evidence 5: `run_honest_sweep_r3.py:5945` — `f"# Research report: {_strip_injected_instruction_appendix(research_question)}\n\n"`. The code templates the research_question into the title verbatim. Compare the champion's title: "# A literature review on the restructuring impact of Artificial Intelligence (AI) on the labor market" — rewritten, clean.
- **Banner — render-injected.** "**STRONGEST VERIFIER (four-role D8) DID NOT RUN for this run — findings are UNVERIFIED-by-D8**... See `manifest.json` (`release_disclosure`)..." Absent from the raw draft; no LLM was asked to write it; it references internal pipeline artifacts (`manifest.json`, "four-role D8", "strict_verify / span-grounding / NLI"). The scored report opens by announcing its own QA did not run and telling the reader its findings are unverified. To a RACE grader this is a self-declared trust failure on line 3.
- **Telemetry — render-injected.** "Completeness checklist: 0/0" (hard facts; below the evidence-3 truncation). Also render-templated: the intro boilerplate "This report reviews the available evidence on How is Artificial Intelligence restructuring the labor market...**?.**" (raw question pasted mid-sentence, twice, with the "?." punctuation artifact), the "Scope: this review is bounded to..." paragraph, and the two "**Tension**" blocks that verbatim duplicate sentences already present in the body (the Schumpeter sentence and the contradictions sentence each appear twice within a screenful).

So the division of labor: **verify deleted the substance; render dressed the survivors in machine chrome.** Neither the banner, the title, the telemetry, the scope boilerplate, nor the Tension duplicates were written by the LLM. Confirmed.

---

## Q4 — Final B vs TRUE CHAMPION (0.4447): corpus, composition, or post-processing?

**Corpus first (≈ +0.078), post-processing second (≈ −0.038 measured), composition a distant third.** The pack's own score matrix decomposes this cleanly:

- **champ_ourcorpus = 0.3671 < A = 0.3992.** The champion's composition, run on OUR corpus, *loses* to our own unverified draft by 0.032. So the champion's text is not winning on prose style or structure — with our evidence it scores in our band.
- **0.4447 − 0.3671 = +0.0776 from the corpus swap alone**, holding champion composition constant. That is double the entire verify penalty.
- Read the champion's text and the corpus gap is visible on every line: it cites **dozens of distinct empirical studies** — Noy et al.'s preregistered ChatGPT experiment ("time taken decreased by 40% and output quality rose by 18%"), Autor's 1940–2018 job-title analysis ("more than 60 percent of employment in 2018 was found in job titles that did not exist in 1940"), Eloundou-style LLM exposure ("1.8% of jobs... jumps to just over 46%"), Korean firm surveys ("95.5% reported no workforce changes"), the ILO productivity brief, IMF/Cazzaniga, OECD exposure work, Chinese regional coefficients, platform-wage data ("$2 to $3 per hour... below the federal minimum wage of $7.25"). Our 34 drops cite only **~10 unique evidence IDs** (ev_001, 055, 128, 165, 225, 241, 256, 279, 307, 312) — and the draft's compulsive repetition (the McKinsey fact written in 4 sections, retail in 4, the 47% premium in 4, 0.6pp-per-10pp appearing 3 times *in the final*) is the signature of a generator squeezing a thin corpus.
- **The champion also ran faithfulness** — its own preamble: "claims that could not be verified against the underlying evidence were **removed rather than paraphrased**." So verification per se is compatible with 0.4447; what it does not have is *our* verifier's byte-window number gate and drop-on-NEUTRAL rule, nor our render chrome (its Limitations section discloses tier gaps as clean prose — "only 6% of sources classified as T1... 21% falling into T6" — the correct home for exactly the material our render shoves into a top-of-report banner).

What champion has that we lost, itemized: (1) breadth — sections we cannot write at all from this corpus (Productivity Effects of Generative AI, Occupational Exposure, Policy) — **corpus**; (2) the intact Acemoglu–Restrepo framework treatment and era decomposition we drafted and then deleted — **post-processing damage**; (3) coherent discourse with antecedents intact and a real title — **post-processing damage**; (4) one-fact-one-place economy instead of 4× repetition — **composition (draft-side)**.

---

## Q5 — ROOT CAUSE (named functions) and ROOT FIX (ranked by RACE leverage)

### Root cause

1. **`strict_verify`'s drop-on-fail rule — the primary mangler.** Three sub-rules, in damage order:
   - **The number/span matcher** (`no_integer_overlap_any_cited_span` 21 + `percent_not_in_cited_span` 15 + `number_not_in_any_cited_span` 9 = **45 drops**): requires each extracted number to appear as a string inside the exact cited byte window; proven offset-sensitive (Q2 proofs 1–2) and buggy (signed-integer parse of "post-1987", Q2 proof 3).
   - **The NLI entailment gate with NEUTRAL→DROP** (**66 drops**): NEUTRAL means "not contradicted, adds specifics" — i.e., synthesis, the whole point of a literature review. Only 2 verdicts in the report were CONTRADICTED; the other 98.6% of entailment kills removed non-false content, including the reinstatement-effect sentence the judge itself half-conceded ("The span mentions 'new task generation' but does not explicitly mention the 'rei[nstatement]'").
   - **`binding_qualifier_dropped` (8) and `no_provenance_token`**: the former killed the retail fact three times; the latter kills uncited topic/transition sentences and produces the orphaned-anaphora final.
   Note the pipeline convicts itself: `content_dedup_consolidate.py`'s docstring states the charter — "**the pipeline is WEIGHT-and-CONSOLIDATE, never FILTER-and-DROP**, which VIOLATES §-1.3" is the exact standard it applies to dedup — while strict_verify FILTER-and-DROPs 73% of the report's sentences one stage later. The dedup stage was lovingly engineered to keep-all; the verify stage is the §-1.3 violation nobody audited.
2. **`render` title/banner/telemetry** — `run_honest_sweep_r3.py:5945` (`# Research report: {research_question}` raw-prompt title) plus the D8 banner, "Completeness checklist: 0/0", the "?."-question boilerplate, and Tension-block duplication, all injected into the SCORED text instead of the manifest/appendix.
3. **`content_dedup_consolidate` — EXONERATED.** Its source is KEEP-ALL, MERGE-NOTHING, annotation-only ("every input row is returned... No row is removed"). It is not a mangler; do not spend a fix on it. The *repetition* problem (same fact drafted in 4 sections) is upstream in per-section generation, not in this consolidator.

### Root fix, ranked by RACE leverage

1. **[≈ +0.08] Fix the corpus, not the prose.** The largest measured gap (0.3671 → 0.4447 on corpus swap alone) is retrieval breadth/quality. No pipeline surgery reaches 0.4447 from a 10-source evidence pool. This is outside the mangling thesis but it is the number-one lever and must be said.
2. **[≈ +0.038, the full A−B gap] Convert strict_verify from FILTER-and-DROP to LOCATE-or-REPAIR-then-drop** — recovering the drafted content *without* abandoning faithfulness, because the drops were not lies:
   a. **Number mismatches → LOCATE:** search the *entire cited document* (or a ±2–4KB widened window) for the normalized number; on hit, rewrite the citation offset and PASS. This alone converts most of the 45 number drops — proven safe by the fact that `47`, `6.5`, `7.5` all verify at other offsets of the *same* documents. Also fix the tokenizer (strip "post-/pre-" prefixes; never emit signed integers from hyphenated years; normalize percent/decimal forms), and check multi-span sentences against the **union** of their cited spans.
   b. **NEUTRAL entailment → one bounded REPAIR pass:** feed the sentence + span back to the generator with "delete any specific not supported by the span, keep the rest," re-verify once; drop only on CONTRADICTED or second failure. Nothing false survives (contradictions still die — all 2 of them); the factual core of ~66 sentences survives. Same policy for `binding_qualifier_dropped`: reinstate the qualifier, don't delete the fact.
   c. **Exempt citation-free framing/topic/transition sentences** from `no_provenance_token` (they assert nothing not cited immediately after) — this repairs the orphaned-anaphora readability damage for free.
3. **[≈ +0.01–0.02, bounded] Strip render chrome from the SCORED text:** title = the LLM's own first line (the raw draft's was clean); D8 banner, telemetry, "Completeness checklist," scope boilerplate, and Tension duplicates → `manifest.json` / a Limitations section written as prose (the champion shows the pattern). The bound is small because A scores 0.3992 *with* all chrome present; chrome is real but not the ghost.
4. **[small, free] Kill the pointer-sentence tic at the prompt:** forbid "X is detailed under <section>"; state the fact once or omit. Recovers ~25–30 sentences of draft budget and removes a class of guaranteed entailment failures. Pair with cross-section claim budgeting so the McKinsey fact is drafted once, not four times, and its survival is not a 4-way offset lottery.

---

## Q6 — Adjudication: faithfulness ghost vs render chrome

**The operator is right, with two amendments. By the numbers:**

- **strict_verify cost: −0.0382 RACE, directly measured** (A 0.3992 vs B 0.3610, the only toggled variable). 147 sentences, −22% words, ~7 unique empirical anchors erased, the report's core framework sentence lobotomized, discourse broken — to catch **2** contradicted sentences.
- **render chrome cost: bounded below ~0.03 and probably ≈0.01–0.02, never directly measured.** A carries the full chrome (raw-prompt title, banner, telemetry) and still scores 0.3992 — only 0.046 under the champion despite a far thinner corpus. If chrome were the big killer, A could not sit that high. Chrome is ugly and self-sabotaging (a scored report that opens "findings are UNVERIFIED-by-D8" is begging the grader to distrust it), and stripping it is nearly free — but it is worth roughly a third of the verify damage at most.
- So within the pipeline: **faithfulness gate ≈ 0.038 > render chrome ≈ 0.01–0.02.** The ghost is real, it is the bigger of the two, and it is "invisible" in exactly the operator's sense: nothing in the final text shows a scar where 147 sentences used to be — you only see it in the checkpoint diff.

**Amendment 1:** the draft is not perfectly "clean." ~26% of the shown drops are the LLM's own zero-content pointer sentences, and the draft repeats its few facts up to 4×. The well-prompted-LLM half of the thesis is 75% true.
**Amendment 2:** both pipeline losses together (≈0.05) are smaller than the corpus gap (≈0.078). The mangling thesis correctly explains **B vs A**; it does not explain **B vs 0.4447**. Path to the champion: fix verify (→ ~0.40), strip chrome (→ ~0.41), champion-grade corpus (→ ~0.48–0.49), consistent with the fable5_scoped_calibration ceiling of 0.5065.

**Final adjudication: faithfulness-as-implemented is the invisible killer inside the pipeline (2–4× the chrome loss), the render chrome is a cheap secondary fix, and the corpus is the silent majority of the gap to 0.4447.**
