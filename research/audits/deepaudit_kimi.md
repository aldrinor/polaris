# Kimi K3 deep audit (usage {'prompt_tokens': 13332, 'completion_tokens': 28862, 'total_tokens': 42194, 'cost': 0.472926, 'is_byok': False, 'prompt_tokens_details': {'cached_tokens': 0, 'cache_write_tokens': 0, 'audio_tokens': 0, 'video_tokens': 0}, 'cost_details': {'upstream_inference_cost': 0.472926, 'upstream_inference_prompt_cost': 0.039996, 'upstream_inference_completions_cost': 0.43293}, 'completion_tokens_details': {'reasoning_tokens': 23739, 'image_tokens': 0, 'audio_tokens': 0}})

# FORENSIC VERDICT (up front)

The operator is **right about the killer and wrong about the sufficiency of the fix**. The measured, causal loss inside the pipeline is `strict_verify`: A(faith OFF) 0.3992 − B(faith ON) 0.3610 = **−0.0382**, same corpus, same render. The render chrome is real but bounded at **≤0.0061** (champ_ourcorpus 0.3671 − B 0.3610). And both are dwarfed by the corpus wall: champion 0.4447 − champ_ourcorpus 0.3671 = **0.0776** that no post-generation fix can touch. The prior audit's "deferral-pointer disease" is doubly non-existent, and dedup is innocent — its own docstring convicts the real ghost.

---

## Q1 — The 34 drops: GOOD content, wrongly killed. Quantified cost.

**Classification of the 34 shown:**

**(a) Unique, true, insight-bearing content — killed (~8 sentences, the real wound):**
- DROP 8: *"Acemoglu and Restrepo's task-based framework identifies a displacement effect… and a reinstatement effect, whereby new technologies generate new labor-demanding tasks"* — killed because *"The span mentions 'new task generation' but does not explicitly mention the 'rei[nstatement effect]'"*. This is the **organizing framework of the entire review**. Its survivor in the final is an amputated fragment: *"A task-based framework developed by Acemoglu and Restrepo describes a displacement effect, whereby capital takes over tasks previously performed by labor, and new task generation."* The champion builds a whole section on exactly this: *"Countervailing the displacement effect is the reinstatement effect, which is the polar opposite of displacement…"*
- DROP 9/21: *"displacement accelerated to 0.7 percent per year while reinstatement slowed to 0.35 percent per year"* — the headline later-period decomposition. `missing=['0.35','0.7','1.3']`. Gone from the final (only the orphan *"deceleration of wage bill growth to 1.33 percent"* survives, mechanism deleted).
- DROP 22: *"college-educated workers nearly doubling from 20 percent in 1979 to 39 percent in 2018, and the experience premium rising from roughly 67 percent in 1980 to 91 percent in 2018"* — `missing=['67','91']`. The entire SBTC/college-premium line of argument is **extinct** in the final.
- DROP 2/10/24/30: McKinsey *"75 to 375 million workers by 2030"* — `missing=['375']` **four separate times**. Four instances entered the gate; zero survived. The range is wholly absent from the final (only *"800 million jobs"* remains).
- DROP 1 (Industry 4.0 definitional framing, *"2011 Hannover Fair… cyber-physical systems…"*), DROP 11 (*"declined by 850,000 jobs"*), DROP 20 (section topic sentence, `no_provenance_token`).

**(b) Duplicates whose fact survived but whose INSIGHT was shaved (~17):** DROP 12 kept the bare STEM numbers but the NEUTRAL reason shows the gate's true target: *"The SENTENCE adds the explanation 'reflecting rising demand for new technical sk[ills]'"*. Same pattern in DROP 16 (*"underscoring the urgency…"*), DROP 25 (*"vary significantly by occupation and regional context"*), DROP 13 (*"adds the specific timeframe 'through 2034'"*). The NLI judge is executing **interpretive clauses**, not falsehoods.

**(c) Cross-reference pointers (~9: drops 6,17,18,19,26,27,28,29,34):** *"…are detailed under AI and the Fourth Industrial Revolution: Context for Labor Market Transformation"*. Low value — but note: Evidence 3 contains **zero** "detailed under" sentences. The gate already filtered them. They never reached the scored text, so they cannot explain the score. The prior audit's "disease" does not exist **in the artifact that gets scored**, and the pointed-to sections demonstrably exist (Evidence 2 lists exactly those titles). Doubly non-existent.

**Truth check:** every substantive dropped figure is canonical literature (McKinsey 75–375M; Acemoglu-Restrepo 0.7/0.35; BLS 47%/16pp; college hours 20→39%; experience premium 67→91). Pack confirms: **"Only 2 CONTRADICTED in the whole report."** The gate killed 147 sentences to remove 2 lies — a **98.6% false-positive rate on truth**.

**Ledger reconciliation (a superficial audit misses this):** drop_reason_counts sum to 131 (66+21+15+11+9+8+1), not 147. The missing 16 ≈ 14 `no_provenance_token` (DROP 20's class) + 2 contradicted. Also: 147 dropped + 55 verified = **202 verdicts** against "~145 sentences" — the verifier segmented ~202 sentences (5823 words / 202 ≈ 28.8 w/s, which reconciles exactly).

**Quantified cost:**
- Words: −1274 net (−22%). But gross: 147 × ~28.8 ≈ **~4,230 findings-words removed**; 55 survivors ≈ ~1,590 words. Render then added ~2,960 apparatus words (5823 − 4230 + 2960 ≈ 4549 ✓). **The scored document is ~35% surviving findings, ~65% render apparatus.** The raw draft was 100% findings.
- RACE: the clean A/B arm measures the whole 147-drop set at **−0.0382**. Split estimate from the drop mix: the 45 number-bearing drops + citation-set collapse load mostly on Comp/Coverage (~0.02–0.025); the 66 NEUTRAL clause-executions + topic-sentence loss + span-verbatim fragment style load on Insight (~0.013–0.018).
- **Second-order (the invisible part):** every dropped sentence takes its `[N]` citations with it. The code admits the coupling: *"the body ``[N]`` markers live in strict_verify-PASSED prose"* (`s2_cited_bibliography_records`). Fewer surviving sentences → smaller `cited_reference_numbers(body)` → required-entity coverage credit collapses → *"a fail-safe UNDER-credit"* fires. The gate doesn't just delete prose; **it starves the Completeness/Coverage dimension through the bibliography path.**

## Q2 — The number-mismatch class (45 drops): SELF-INFlicted wound, with quoted proof.

45 drops = `no_integer_overlap` 21 + `percent_not_in_cited_span` 15 + `number_not_in_any_cited_span` 9. Three fingerprints prove it's a matcher/window failure, not hallucination detection:

1. **The sign-regex bug.** DROP 6: `missing=['-1987']`. The sentence says *"post-1987"*. The extractor glued the hyphen to the year (`-?\d+`), then searched the span for the literal string "-1987", which exists in no document on earth. The number 1987 is in the evidence; the *token* "-1987" is not. A cosmetic reading ("number not found ⇒ hallucination") misclassifies a tokenizer bug as a lie.
2. **Window truncation.** DROP 2/30: `missing=['375']` — note **75 was found** in `ev_225:2700-3500`, only 375 is "missing." The real McKinsey span contains both endpoints of the range; the generator-asserted 800-byte window cut between them. Same in DROP 22: 20 and 39 found, 67 and 91 "missing." The verifier is auditing the *citation offsets*, not the *evidence*.
3. **Same-document, wrong-window.** DROP 9 cites `ev_165:0-800`+`ev_001:0-800` and dies for 0.7/0.35/1.3 — while the **early-period** decomposition from the same documents (0.48/0.47/2.4/2.5) verified and sits in the final. The later-period numbers live deeper in the same evidence docs; the generator cited the right document at the wrong offset.

Verdict: the class has a legitimate *core* (a number found nowhere in the corpus is a hallucination signal), but it is implemented against the wrong index (cited byte-window instead of full evidence doc → corpus) with the wrong action (drop instead of re-bind). **45 drops, zero demonstrated fabrications in the shown sample. It is a citation-window linter masquerading as a lie detector.**

## Q3 — What verify+render did, line by line. Chrome confirmed render-injected.

**VERIFY did:**
- Segmented ~202 sentences; kept 55 (27%); killed 147 (73%).
- Killed **non-deterministically w.r.t. content, deterministically w.r.t. span-window luck**: the 47% figure dies in DROP 5/14 yet the final keeps *"Workers in the most AI-exposed professions earn 47 percent more on average…"*; the 0.6pp BLS claim dies in DROP 4/13/32 yet appears **three times** in the final (Skill Demand, Adoption Rates, Polarization). The gate kept triplicates and killed singletons — the final is simultaneously **redundant and impoverished**.
- Forced the span-verbatim style the final advertises — *"each cited claim is carried verbatim from a source span"* — producing the amputated *"…and new task generation."* fragment.
- Stripped/omitted inline citations in the scored body: Evidence 3's prose carries **no `[N]` and no `[#ev:]` markers**. If that holds full-length, `cited_reference_numbers(body)` returns ∅ and `s2_cited_bibliography_records` hits its quoted fail-safe: *"When the body is empty/unreadable this returns [] — a fail-safe UNDER-credit"* — consistent with the telemetry fingerprint *"Completeness checklist: 0/0."*

**RENDER injected (absent from Evidence 2's raw draft, present in Evidence 3 — confirmed not-LLM):**
- **Title:** `# Research report: Please write a literature review on… Ensure the review only cites high-quality, English-language journal articles.` Code: `f"# Research report: {_strip_injected_instruction_appendix(research_question)}\n\n"`. Note the helper's name promises to strip the injected instruction appendix — **it failed**: the instruction sentence *"Ensure the review only cites…"* leaked into the H1. (The shown code is the zero-survivor abort body, but the identical `head` string in B's final proves the title-builder is shared.)
- **Banner:** `> **STRONGEST VERIFIER (four-role D8) DID NOT RUN… findings are UNVERIFIED-by-D8.**` — a three-line self-deprecation as the first thing a scorer reads. Its own text admits the disclosure already lives off-body: *"See `manifest.json` (`release_disclosure`)"*.
- **Boilerplate:** *"This report reviews the available evidence on How is Artificial Intelligence restructuring…?"* + *"Scope: this review is bounded to the question of…"* — raw questions dumped twice more.
- **Tension callouts:** `**Tension** Schumpeter's innovation theory captures this duality…` and `**Tension** However, contradictions around labor replacement…` — **verbatim duplicates of sentences already in the body**. Render's idea of synthesis is copy-and-label.
- **Appendix/telemetry:** `_CORPUS_LEDGER_HEADER = "## Corpus ledger (audit appendix — not cited references)"` + *"Completeness checklist: 0/0"*.

## Q4 — FINAL B vs TRUE CHAMPION: corpus first, gate second, chrome third.

**What the champion has that we lost:**
- **Study-attributed specificity:** *"Noy et al. assigned occupation-specific writing tasks to 453 college-educated professionals… average time taken decreased by 40% and output quality rose by 18%"*; *"elasticity of substitution… is 0.8, based on Oberfield and Raval's work"*; *"Autor, using decades of U.S. data from 1940 through 2018, estimates that more than 60 percent of employment in 2018 was found in job titles that did not exist in 1940"*; named Tomlinson, Frank, Cazzaniga, Bonney, Eloundou. Our final attributes almost nothing to anyone.
- **The displacement–reinstatement framework intact** (our DROP 8 amputation), plus WEF/PwC forecasts (85M/97M, 75M/133M, *"$15.7 trillion"*), LLM-exposure estimates (*"1.8%… jumps to just over 46%"*), Korean firm survey, platform wages (*"$2 to $3 per hour… federal minimum wage of $7.25"*).
- **Real synthesis:** a *"Cross-Study Synthesis and Contradictions"* section (*"reveals a field still in its earliest stages"*), Conclusions/Gaps, and a Limitations section that reads the corpus itself (*"only 6% of sources classified as T1 primary studies and 21% falling into T6"*). We have two verbatim-duplicating Tension callouts.
- **Clean chrome:** derived title (*"# A literature review on the restructuring impact of…"*), and the entire honesty disclosure compressed into one clause — *"claims that could not be verified against the underlying evidence were removed rather than paraphrased"* — versus our three-line UNVERIFIED banner. **Note: the champion also verify-and-drops. Verify-drop is compatible with 0.4447 when the corpus is rich and retained mass is large. Our gate retains 27%.**

**Adjudication by the pack's own numbers:**
- **Corpus: 0.4447 − 0.3671 = 0.0776.** The champion's approach re-anchored to our corpus loses three-quarters of its score. Dominant factor.
- **Gate: 0.3992 − 0.3610 = 0.0382.** Second.
- **Composition/chrome residual: 0.3671 − 0.3610 = 0.0061.** Third, small.
- **The decisive, easily-missed fact: A (0.3992) > champ_ourcorpus (0.3671).** Our own raw draft, unmangled, **out-scores the champion's text on our corpus by 0.0321**. The draft was never the problem — which is exactly the operator's core premise. (fable5's 0.5065 is a scoped calibration run, not a head-to-head; it marks the scorer's dynamic range, not the target.)

## Q5 — ROOT CAUSE functions and ROOT FIX, ranked by RACE leverage.

**ROOT CAUSE — three errors stacked inside `strict_verify`, plus one coupling, plus render chrome:**

1. **Category error:** `entailment_failed(NEUTRAL)` (66 drops, 45%) is collapsed with CONTRADICTION into the same action. The quoted reasons show the judge working as designed — *"introduces specific details like the 2011 Hannover Fair"*, *"adds the specific timeframe 'through 2034'"* — and the **policy** executing true sentences for it. Genuine faithfulness forbids contradiction and requires corpus-grounding; it does not require byte-entailment from one 800-byte window.
2. **Window error:** number/percent checks (45 drops) search only generator-asserted cited spans that drift and truncate (Q2), compounded by the `-1987` sign-regex bug and no digit/word/percent/magnitude normalization and no derived-number tolerance (*"a reduction of 25%"* is arithmetic on 7.5→5.7, not a citable byte).
3. **Policy error:** the only action is DROP. `binding_qualifier_dropped` (8) should re-attach the qualifier; `no_provenance_token` (~14) should auto-ground or regenerate; NEUTRAL should regenerate; number-mismatch should re-locate and re-bind.
4. **The coverage coupling (the invisible multiplier):** `s2_cited_bibliography_records` keys required-entity credit on `cited_reference_numbers(body)`, and the docstring states *"the body ``[N]`` markers live in strict_verify-PASSED prose"* — so each of the 147 drops can de-cite a source, demote it to the ledger, and strip entity-coverage credit. This is why the faithfulness failure **surfaces as a Completeness/Coverage weakness** — invisible to anyone reading the score by dimension.
5. **Render chrome:** title built from the raw prompt with a strip-helper that doesn't strip; D8 banner and *"0/0"* telemetry injected into the scored body; Tension callouts duplicating body sentences.
6. **EXONERATED — dedup.** The prior suspect is innocent on its own docstring: *"KEEP-ALL: every input row is returned… the output list has the SAME length as the input"*, *"MERGE-NOTHING"*, *"GROUNDING-UNTOUCHED: the annotation… never feeds or relaxes strict_verify"*. W9 drops nothing.

**ROOT FIX — ranked by measured RACE leverage:**

**#1 — Verdict-gradation + relocate-not-drop + regenerate-not-drop in strict_verify (leverage: the full A−B delta, +0.0382, PLUS the s2 coverage recovery).**
- CONTRADICTION → drop (all 2 of them; genuine faithfulness preserved).
- NEUTRAL → re-ground against the **full evidence document, then the corpus**; if grounded, re-bind the citation and KEEP; if not, route to a **repair pass**: dropped sentence + best-matching span(s) + "rewrite using only these spans, keep the citation." Deletion is the last resort, not the default.
- Number-mismatch → search cited spans → full doc → corpus, with normalization (words/digits, `%`/`percent`, magnitudes like `375 million`, en-dash ranges `1947–1987`, sign fix so `post-1987` tokenizes as 1987) and a tolerance band for derived statistics; on hit, **re-bind offsets and keep**; on true absence everywhere, regenerate or drop — that is the only case that is actually a hallucination.
- `binding_qualifier_dropped` → re-insert the qualifier (*"projected," "an estimated"*); `no_provenance_token` → auto-ground framing sentences or regenerate with a token.
- This keeps the gate's guarantee (every surviving claim traces to a corpus span — identical to today's guarantee, and identical to the champion's stated method) while recovering the 22% of mass and the citation set.

**#2 — Retrieval/corpus enrichment to champion grade (leverage: 0.0455–0.0776; the ONLY path past ~0.40).** Even with the gate perfect, our corpus caps at A = 0.3992, still 0.0455 short of 0.4447. Retrieve the study-grade sources the champion cites: Noy et al., ILO generative-AI brief, WEF Future of Jobs (85M/97M; 75M/133M), PwC ($15.7T), Eloundou (1.8%→46%), Autor 1940–2018, OECD exposure, the Korean firm survey, platform-wage studies, Oberfield-Raval. Highest absolute ceiling; it is a retrieval fix, not a mangling fix — and the operator's thesis does not cover it.

**#3 — Decouple coverage credit from verify survival (part of #1's second-order, but an independent one-function fix).** Compute `cited_reference_numbers` on the pre-strip body, or map `[#ev:ev_N]` → bibliography `[N]` before citation stripping, so a dropped sentence never silently demotes a cited source into the ledger and the S2 *"fail-safe UNDER-credit"* stops firing on a healthy report.

**#4 — Strip render chrome from the SCORED text (leverage ≤0.006, but ~zero cost).** Derive a champion-style title; fix `_strip_injected_instruction_appendix` to actually remove instruction clauses; relocate the D8 banner and telemetry to `manifest.json` — where the banner itself says the disclosure already lives. **Honesty is preserved by relocation, not suppression**; do not fake a D8 run. Dedupe or delete the verbatim Tension callouts.

**Do NOT (cosmetic retreats):** prompt-engineer away "pointer" sentences (they never reach the scored text — the disease doesn't exist there); strip the banner while leaving the gate (recovers ≤0.006); or turn faithfulness fully OFF (arm A re-admits the 2 contradictions and forfeits the anti-hallucination property the product exists for — the fix is verdict gradation, not gate removal).

## Q6 — Adjudication: the operator is right about the killer, incomplete about the war.

**Faithfulness gate vs render chrome, with numbers:**
- Gate: **−0.0382**, directly measured by the only clean post-generation arm in the pack (A vs B, same corpus, same render). Mechanism: 147 drops at 98.6% false-positive-on-truth, −22% words, amputated framework, extinct claim-lines (McKinsey range, SBTC premium, 0.7/0.35 decomposition), **plus** the invisible coverage-credit starvation through `cited_reference_numbers`/`s2_cited_bibliography_records`.
- Chrome: present in both A and B, so no arm isolates it; its hard upper bound is the same-corpus composition residual **0.0061** (0.3671 − 0.3610). The gate is **≥6× the chrome**, before counting the coverage coupling.

**So: yes, the faithfulness verifier is the invisible killer — and now we can say precisely why it was invisible.** It does not look like a faithfulness failure anywhere: the report it produces is *more* honest-looking (span-verbatim, "*findings that survived span-level verification*"), its damage surfaces under Completeness/Coverage and Insight, its citation starvation fires a *fail-safe* that reads as prudence (*"a fail-safe UNDER-credit… never suppresses a gap"*), and its most visible byproduct — the pointer sentences in the drop log — baited the prior audit into inventing a disease in the LLM that never survives to the scored artifact.

**But the operator's thesis stops one layer short.** Killing the ghost AND the chrome caps us at ~0.40 (A = 0.3992, plus ≤0.006). The champion's remaining edge is not composition we lost — on our corpus our own raw draft already beats the champion's text (0.3992 > 0.3671) — it is **the corpus itself** (0.0776 of the 0.0837 gap). The full root stack, ranked: **corpus (0.0776) > strict_verify gate (0.0382, +coverage coupling) > render chrome (≤0.006)**. Fix the gate to earn back our own draft; fix retrieval to earn the champion's.
