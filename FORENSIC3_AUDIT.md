# FORENSIC3 — Consolidated line-by-line audit of the four task-72 scored texts

**Consolidator:** OPUS (claude-opus-4-8). **Date:** 2026-07-18.
**Inputs read:** `pack.md` (all four scored texts + confounds), `fable.md`, `codex.md`, `kimi.md`.

## Models that actually returned — READ THIS FIRST

This was briefed as a "3-model" audit. **Only 2 of 3 models returned.**

- **FABLE 5** — returned in full (`fable.md`, MAX-depth). USED.
- **CODEX (gpt-5.6-sol, reasoning=high)** — returned in full (`codex.md`, ~4,900 words; `codex.err` is the reasoning/prompt trace, no crash). USED.
- **KIMI (kimi-k2.6)** — **DID NOT RETURN.** `kimi.md` does not exist on disk; `run_kimi.py` is present but produced no output file. **Nothing is attributed to Kimi below.** (Wry footnote: step3's own Methods block recommends pointing the entailment judge at `moonshotai/kimi-k2.6` — the one model that no-showed this audit.)

So "converge/diverge across models" below means **Fable vs Codex**. They converge almost completely; the two are independent confirmations of the same diagnosis, which raises confidence in the shared findings. Divergences are minor and flagged in §6.

Dimension weights (task-72): **Insight 0.32, Comprehensiveness 0.29, Instruction-Following 0.25, Readability 0.14.**
Scores: **A 0.3992 | B 0.3610 | champ_ourcorpus 0.3671 | step3 0.4291.**

---

## 1. THE VERDICT on A > B: ghost or confound?

**Verdict (both models agree, unanimous): the 0.038 A>B delta is CONFOUNDED, not a clean faithfulness measurement. The faithfulness-cost MECHANISM is confirmed in the text; the MAGNITUDE 0.038 is not attributable to it.**

Codex states it flatly: *"the 0.038 delta is not credibly attributable to 'the faithfulness ghost' as a measured treatment effect. It could contain a faithfulness penalty; it cannot quantify one."* Fable: *"the ghost is real but plausibly worth only part of the delta — somewhere in 0.01–0.03 — with the rest corpus/contract noise. Do not book 0.038 as the price of faithfulness."*

### Why it is confounded (both models enumerate the same list; verified against pack §CONFOUNDS)
A and B differ on **every** axis except the raw-prompt title and D8 banner:
- corpora: **234 vs 302** sources (205 vs 271 citable after masking);
- contracts: **12 vs 8–9** hard terms;
- outlines: **6 vs 9** parallel sections;
- length: **5201 vs 4549** words;
- **source tier: A is 60% T4, B is 74% T4 — B's corpus is measurably worse-tiered**, independent of the gate;
- B's entailment judge was *"UNAVAILABLE for 68 of 212 basket member(s) (32.1%)"*;
- n=1 each. Codex: *"There is one observation per condition."*

Because A's title/banner and B's title/banner are identical, that chrome **cancels** in A−B and cannot explain the gap (both models note this; it is the one thing the comparison *does* control).

### The faithfulness MECHANISM is confirmed in B's text (both models, same scars)
Faithfulness-ON put B under far heavier verification pressure and left visible scars:
1. **~7× more removals.** B: *"147 generated sentence(s) were REMOVED... Support-failed (102)... entailment_failed: 66"* vs A: *"56... Support-failed (15)"* with **zero** entailment failures (faith-OFF never ran entailment).
2. **Stub sections from deletion.** "AI Adoption Rates and Employment Outcomes by Industry" is **two–three sentences**; the Synthesis is three sentences ending off-topic on *"AI development exhibits an inverted U-shaped relationship with urban resilience... threshold value of 0.7383"* — a stranded concept whose context was excised.
3. **Orphaned anaphora = cut-marks** (Fable's sharpest catch, Codex concurs): sections open referencing deleted predecessors — *"The BLS corroborates **this productivity slowdown**..."* (no slowdown stated in that section), *"However, **this process** also involves 'creative destruction'"* (this process = nothing), *"**The consequence** has been a deceleration of wage bill growth..."* (consequence of what?).
4. **Quadruplicated stats from the killed dedup pass** (confound fact: *"fact_dedup proposed 44 rewrites, strict_verify DROPPED all 44"*): the BLS "0.6 percentage points per 10 percentage point" stat appears **four times**; "3.5 to 5.8 trillion USD" **three times**; the 86.2% frontier-tech stat twice. The faithfulness gate vetoing every dedup rewrite is what shipped B with blatant recycling.
5. **Deletion without recovery** is the core failure (Codex's framing): *"A verifier should remove unsupported prose, but the compositor then needs to rebuild a coherent... section from the remaining grounded evidence. B often stops after deletion."*

### Counter-evidence that it's not PURELY the ghost (both models supply it)
- B's long first section is arguably **better prose** than A's — it has **zero** deferral pointers (the pointer disease is A-specific) and contains real narrative (Keynes 1930, Schumpeter, the 1947–1987 decomposition).
- B's corpus is independently worse (74% T4) with 32% of entailment checks unavailable — this degrades B regardless of the gate's design.
- Faith-ON did **not** protect B from relevance/extraction failures: *"Digital technology... robot encounters are helping to train skilled robots and raise their relative wages"* (robots do not earn wages — corruption survived), and its table still shows the shard *"| Source | — | — | bor Market Effects of AI. | — |"*.

**Bottom line:** direction consistent with a deletion-induced ghost; magnitude unidentified and plausibly dominated by corpus/contract/length noise. Honest attribution to the ghost: **~0.01–0.03 of the 0.038**, not the whole thing.

---

## 2. WHY step3 (0.429) BEATS our best A (0.399) — dimension by dimension

**Arithmetic first (both models decomposed identically; rounding-consistent with the 0.0299 gap):**

| dim | raw delta (step3−A) | ×weight | share of gap |
|---|---|---|---|
| Readability | +0.0778 | +0.0109 | **36%** |
| Insight | +0.0300 | +0.0096 | 32% |
| Comprehensiveness | +0.0279 | +0.0081 | 27% |
| Instruction-Following | +0.0073 | +0.0018 | **6%** |

**The single largest contributor is Readability — the lowest-weighted dimension.** IF is essentially TIED (0.4288 vs 0.4361). Codex: *"the result is not 'the champion had a prettier title.'"* The loss is *"our text is much harder to read and somewhat less insightful/complete per word."* Insight+Comp together = ~0.0177 of the ~0.030 gap — a **compositional** deficit, not an instruction-following one.

### 2a. Title
- **A:** `# Research report: Please write a literature review... Ensure the review only cites high-quality, English-language journal articles.` — the raw prompt verbatim. Codex: *"an instruction copied into the deliverable... the output renderer did not distinguish the user request from the report."* Fable: *"the report's own headline is an instruction TO an author, not a title OF a document."*
- **step3:** `# A literature review on the restructuring impact of Artificial Intelligence (AI) on the labor market` — the deliverable's name.
- Both models: title alone explains little (A's IF is only −0.007) but sets the pattern — *A exposes machinery where step3 presents a finished publication.*

### 2b. Opening
- **A's** first prose sentence is grammatically broken — three interrogatives mashed into a declarative with a terminal "?.": *"This report reviews the available evidence on What is the restructuring impact of Artificial Intelligence on the labor market? How does Artificial Intelligence act as a key driver... How does Artificial Intelligence affect various industries...?."* Preceded by the self-indicting D8 banner. Codex: *"The reader reaches the actual subject only after the title, warning banner, pipeline description, heading, and a second pipeline description."*
- **step3** opens with genre-correct scholarly framing (*"The Fourth Industrial Revolution, a term popularized by Klaus Schwab in 2016..."*) and closes the intro with a proper review roadmap (*"These converging trends underscore the need for a comprehensive review... examining how automation displaces and reinstates labor, how industries are differentially affected, and what policy and organizational responses are emerging."*).

### 2c. Structure — orthogonal analytical stages vs overlapping labels
- **step3's** 9 sections are **cumulative and non-overlapping**: task frameworks → occupational exposure → empirical employment evidence → productivity → wage/polarization → policy → cross-study synthesis → conclusions. Codex: *"Each section answers a different question."*
- **A's** 6 sections **overlap** ("...in the Labor Market", "Mechanisms of...", "Cross-Industry Impact of...", "Synthesis of..."), so *"later sections repeatedly point backward rather than advancing the analysis."*

### 2d. THE DEFERRAL-POINTER DISEASE (the finding a superficial read misses — both models flag it as decisive)
A's body is saturated with sentences carrying **zero information** — cross-reference pointers the dedup/carry-up machinery emitted wherever a fact was reused: *"Research on task-level AI adoption effects... is detailed under AI and the Fourth Industrial Revolution in the Labor Market."*, *"Korean firms' shifting skill demands... are covered under Mechanisms..."*, *"Acemoglu and Restrepo's robot diffusion displacement findings are covered under..."*
- Fable's count: **~41 pointer sentences ≈ 800+ words ≈ 15% of body prose** says "the content is elsewhere."
- **The terminal Synthesis section — the Insight section — is ~13 of 16 sentences pure pointers.** A synthesis that synthesizes nothing. Codex: *"That is not synthesis. It does not reconcile methods, distinguish causal from correlational evidence, explain divergent results, or derive an implication."*
- The disease infects **Key Findings**: 3 of 6 "findings" are pointers, e.g. *"**Future Labor Market Trajectories...** Workers' invulnerability bias regarding AI's impact is covered under AI and the Fourth Industrial Revolution in the Labor Market."* — a headline "finding" that is literally a cross-reference.

### 2e. Synthesis vs stat-listing (real Insight)
step3 does three things A never does:
1. **Names and stitches the literature:** *"Complementary research by Autor, using decades of U.S. data from 1940 through 2018, estimates that more than 60 percent of employment in 2018 was found in job titles that did not exist in 1940, **reinforcing the view** that new work is quantitatively important."* Named throughout: Noy et al. (2023), Eloundou et al. (2024), Tomlinson et al. (2025), Cazzaniga (2024), Autor–Dorn–Hanson (2013), Oberfield–Raval (2014), Frank et al. (2026).
2. **Adjudicates between sources:** *"while existing measures have been criticized as poorly validated... Tomlinson et al. (2025) found that AI exposure measures from Eloundou et al. (2024) have very high correlation with Microsoft Copilot usage."* And the counter-attribution: *"a decline in job postings began in 2022, prior to the public release of ChatGPT, corresponding better to the macroeconomic shift of rising interest rates than to the launch of large language models."*
3. **Interprets numbers instead of dropping them:** *"the weighted correlation between self-reported time savings and self-reported output changes is low, **suggesting that workers save time but do not on average produce more.**"*
- **A**, by contrast, machine-guns anonymized stats (*"A study of 671 occupations", "One study", "one analysis"*) and its "Tension" callouts are verbatim copies of body sentences — Fable: *"the pipeline's simulation of insight."* A's "However" between the 671-occupation wage study and the Acemoglu–Restrepo robot study is a false contradiction — Codex: *"these are different technologies, outcomes, units of analysis, and periods. A does not adjudicate those differences."*

### 2f. Broken artifacts in A's scored text (both models catalog these)
- First "Tension" callout truncated mid-sentence: *"**Tension** However, Acemoglu and Restrepo's empirical work using U.S."*
- "Single-source findings" ships raw extraction shards as findings: *"28015, Spain. (single source)"*, *"the-impact-of-new-technologies-on-the-labor-market.pdf). (single source)"*, *"Private domestic final purchases have been solid. (single source)"* (Federal Reserve boilerplate, off-topic), *"Can J Occup Ther 85(4):272–283. \"); Morgan..."*
- ~90 lines of telemetry appendix in the scored text: **astrophysics arXiv categories** as contradiction subjects in a labor review — *"astro-ph / change [not_comparable]... gr-qc / change"* — plus SHA-256 hashes and the same-family-evaluator override disclosure.

### 2g. Conciseness — longer ≠ more Comp credit
A is **5201w vs step3's 3372w** (54% longer) yet loses Comp 0.414 < 0.442. Codex: step3's Comp edge *"despite being 1,829 words shorter"* is because it covers **more distinct analytical dimensions**; A's extra words are *"duplicated findings, routing language, tables, and audit telemetry rather than additional analytical coverage."* Fable: *"Strip that and A's substantive content is comparable in size to step3's — but lower in connective tissue."*

---

## 3. WHY our gate A BEATS champ_ourcorpus (0.367) on the SAME corpus

**A +0.032 overall; won IF (+0.057), Insight (+0.043), Comp (+0.021); lost only Readability (−0.016).** This is the cleanest comparison in the pack — same corpus, so the delta is **composition**, not evidence.

### What our gate does RIGHT (both models converge: topical selection + on-prompt organization)
- **Relentlessly on-question.** A centers the requested mechanism (*"task automation, productivity augmentation, and occupational restructuring"*), supplies opposing evidence (robot displacement vs firm-level +6% employment growth), identifies task granularity (14% fall vs growth), ties disruption to institutions (*"The UK announced a National Retraining Scheme investing £100 million... Amazon's Upskilling 2025... Singapore... Germany's Work 4.0"*), and lands a genuine conclusion: *"neither uniformly destructive nor uniformly beneficial... depends on task characteristics, institutional frameworks, regional adaptability, and policy choices."*
- **The eligibility firewall + 12-hard-term contract keep the composition inside the prompt frame** — that is what drives the IF (+0.057) and Comp (+0.021) wins. Fable: *"the eligibility firewall (29 sources masked) kept the composition inside the prompt's frame."*

### What the champion COMPOSITION produced on OUR corpus (its failures — both models)
The champion pipeline has **no eligibility firewall**, so on our junk corpus it composed the junk:
- **Verbatim back-to-back self-repetition:** *"By 2026, jobs that require social and cognitive skills and are less likely to be automated are expected to be the most common in the job market."* — then the same sentence again with a clause appended. Repeated again in Wage Polarization.
- **Dangling anaphora / phantom references:** *"Between both cases, this implies a difference in better employment of 22%..."* opens a section (which cases?); *"The ADC Framework and its associated propositions (Table 2) contribute... in three main ways"* — references a **nonexistent Table 2** and never states the three ways; opens with *"An R² of 0.9325 indicating that XGBoost captures the majority of variability..."* unexplained.
- **Off-topic bleed:** COVID worker-anxiety (*"14% reported concerns about employment... 24%... 31% (p < 0.001)"* — pandemic, not AI), *"Pre-pandemic inefficiencies... $274 billion"*, *"construction project... value-added-to-cost ratios... 1.03 to 1.54"*. None is AI-labor material.

**Takeaway (both models):** on equal corpus, **our gate beats the champion on the three packaging-independent dimensions (Comp/Insight/IF) and loses only Readability** — because champ_ourcorpus, for all its junk, has the clean title and no telemetry appendix. Codex: *"real evidence of a composition advantage, not merely a corpus advantage."* Fable: *"our gate's firewall+contract is what clawed +0.03 of [the corpus handicap] back."*

**Corollary — champ_ourcorpus (0.367) vs step3 (0.429), same pipeline:** the 0.062 gap is **predominantly corpus** (identical composition/title/preamble, all four dims drop 0.05–0.07, including IF which only moves if content drifts off-prompt — and it did). step3's corpus carried the actual canon (Acemoglu–Restrepo JEP, Autor 1940–2018, Noy–Zhang, Eloundou, ILO, OECD); our corpus confesses *"only 2% of sources classified as T1... 69% are T3 review-tier."* Both models add the honest caveat: the same-corpus A-vs-champ result proves composition can move ~0.032, so **not all** of the 0.062 is corpus. **Our corpus is a ~0.05–0.06 handicap for any composer.**

---

## 4. THE CHROME DRAGS, quantified — does fixing them close the gap?

Both models stress these are **forensic ranges, not causal estimates** (no randomized renderer experiment). Consolidated ranges (Fable's are slightly wider; I take the union and note it):

| Chrome element | Evidence | Plausible overall cost | Notes |
|---|---|---|---|
| **Raw-prompt title** | `# Research report: Please write...` vs `# A literature review...` | **~0.001–0.010** | Mostly IF/Read. A's IF only −0.007 vs step3 → ceiling is small. Cheap to fix. |
| **D8 banner** | *"findings are UNVERIFIED-by-D8... Treat them as UNVERIFIED... pending a re-judge"* | **~0.001–0.015** (Codex allows near-zero) | Instructs the judge to distrust the findings. Cancels in A−B (both carry it). Real possibility of near-zero cost or even a small transparency reward. |
| **Length bloat / anti-content** | ~41 deferral pointers (~800w), junk shards, ~1000w telemetry appendix (astro-ph, SHA-256, evaluator override) | **~0.006–0.020** | The big one. **Mislabeled as "length"** — the drag is that the extra ~1830 words are *anti-content*. Owns most of the −0.078 Read gap (36% of total gap) + a share of Insight (pointer-polluted Synthesis/Key Findings). |

**Does fixing (a)+(b)+(c) close the ~0.030 gap? — Both models: PARTIALLY, likely to ~0.408–0.425, NOT reliably all the way, IF done cosmetically.**

The hard diagnostic (Codex): Read+IF advantages = ~0.0127; **Insight+Comp = ~0.0177 remain even if title/banner/format are perfected.** That residual is compositional — step3 *names authors, connects findings, adjudicates contradictions*; A emits stat-lists and copies body sentences into "Tension" callouts. Fable: chrome fixes plausibly reach **~0.415–0.425**; the residual **~0.005–0.010 (mostly Insight) needs a composer change, not a packaging change.** Codex: *"the winning action is not 'make it shorter'; it is 'replace non-analytical prose with analytical prose.'"*

There is an **optimistic scenario** both models grant: stripping the pointers/shards/telemetry may lift *perceived* Insight density too (not just Read), in which case chrome work approaches the full gap. But that upper case is really synthesis reconstruction, not chrome removal.

---

## 5. RANKED fixes by RACE leverage + the single highest-leverage change

Consolidated from both models (ranges overlap, are NOT additive). Ordered by expected RACE points per unit effort.

1. **Kill the deferral-pointer mechanism** — when dedup relocates a fact, **DELETE** the sentence; never emit "X is covered under Y." Rebuild Key Findings from actual findings (3 of 6 are pointers today); let Synthesis synthesize. **Expected +0.010–0.018 (Read + Insight). Effort: one composer/dedup rule.** *Fable's #1 / highest total leverage — one rule repairs the worst Read text, the hollow Synthesis, and half of Key Findings simultaneously.*
2. **Strip non-report chrome from the SCORED text** — D8 banner, telemetry appendix (contradiction ledgers, astro-ph flags, SHA hashes, evaluator-override disclosure), "Single-source findings" shard block → move to sidecar files; keep only the short Limitations paragraph (champion format). **Expected +0.008–0.018. Effort: near-zero (a presentation flag).** *Best points-per-effort / highest-ROI quick win (both models).*
3. **Regenerate after verification instead of accepting deletion stubs** — the fix for B's two-sentence sections and orphaned anaphora. Rebuild a coherent, scoped section from the surviving grounded evidence. **Expected +0.006–0.018.**
4. **Clean title + fix the framing sentence** — `# A literature review on...`, grammatical scope paragraph, fix the "?." mashup and the truncated "...using U.S." Tension fragment. **Expected +0.002–0.008. Effort: trivial.**
5. **Named-author citation + connective synthesis** — surface author/year ("Acemoglu and Restrepo (2019)", "Noy et al. (2023)"); require each section to contain ≥1 cross-source adjudication sentence. **Expected +0.004–0.010 (Insight).**
6. **Enforce the journal-only source instruction before composition** — remove WEF/McKinsey/speeches/web pages the prompt forbade; directly improves IF and credibility. **Expected +0.006–0.015** (Codex ranks this higher than Fable does — see §6).
7. **Corpus canon retrieval** — the champ_ourcorpus↔step3 delta shows our corpus costs any composer ~0.05; targeted retrieval of the labor-econ canon (JEP, NBER, ILO, OECD) is the largest absolute lever but the most effort.

### THE SINGLE HIGHEST-LEVERAGE CHANGE

**Both models point at the same target — the compositor — but frame it at two altitudes:**

- **Fable (narrow, cheapest):** *eliminate the deferral pointers* (fix 1). One rule change that simultaneously repairs the worst Readability text, the hollow Synthesis, and half the Key Findings block; with the near-free chrome strip (fix 2) it *"plausibly moves A from 0.399 to ~0.42, within noise of the best champion."*
- **Codex (broad, most likely to actually BEAT step3):** *replace the "section = list of verified claims + cross-references" compositor with a **synthesis-first paragraph compositor*** — every paragraph = (1) analytical proposition, (2) evidence from ≥2 studies, (3) agreement/disagreement, (4) why results differ (technology/population/task-granularity/time/method/institution), (5) implication. Expected **+0.015–0.030**. *"That one architectural change attacks the actual score gap: it improves Insight, removes routing bloat, makes sections nonredundant, and preserves faithfulness by reasoning only over grounded claims."*

**OPUS adjudication:** these are the same lever at two zoom levels and they are complementary, not competing. **Do Fable's fix in week 1** (delete pointers + strip chrome = the near-free path to ~0.42, within noise of the champion) — it is the highest points-per-effort and de-risks the whole gap. **Do Codex's synthesis-first compositor to actually clear step3** — it is the only fix that closes the residual ~0.0177 Insight+Comp deficit that packaging cannot touch. If forced to name ONE: **the synthesis-first compositor (Codex)**, because it strictly contains the pointer-deletion (a synthesis-first paragraph has no place to emit a pointer) and is the only change with a path *above* 0.429 rather than merely *up to* it.

---

## 6. Where the two models DISAGREED — and my adjudication

Fable and Codex converge on essentially everything (title, opening, deferral-pointer disease, broken artifacts, telemetry appendix, orphaned-anaphora scars, the "A>B is confounded" verdict, the Readability-dominates-the-gap arithmetic). The disagreements are of degree and framing, not direction:

1. **Magnitude of the ghost in A−B.** Fable puts a number on it — *"somewhere in 0.01–0.03"*; Codex declines to bound it — *"It could contain a faithfulness penalty; it cannot quantify one."* **Adjudication:** Codex is more rigorous (n=1, ≥6 confounds → any point estimate is false precision), but Fable's range is a reasonable *upper-bounded* prior, not a claim of identification. Report as: *ghost real, ≤~0.03, unidentified* — which both are compatible with.

2. **Chrome-cost ranges.** Fable's ranges run higher (banner ~0.005–0.015; title ~0.005–0.010); Codex's run lower (banner ~0.001–0.005 "with a real possibility of near-zero"; title ~0.001–0.003). **Adjudication:** Codex's floor is better-reasoned — the banner cancels in A−B and A still scored IF 0.4288 *with* it, so its isolated cost is probably small and could even be a transparency reward. I report the **union** (~0.001–0.015 banner) and flag the disagreement rather than splitting it.

3. **Highest-leverage framing.** Fable = "delete the pointers" (narrow, cheap, →~0.42). Codex = "synthesis-first compositor" (broad, →potentially >0.429). **Adjudication:** resolved in §5 — same lever, two altitudes, sequence them (Fable first for ROI, Codex to actually win). Not a real conflict.

4. **Ranking of the journal-only-source fix.** Codex elevates *"Enforce the journal-only source instruction before composition"* to its own ranked fix (+0.006–0.015, IF-focused), citing A's own confession (*"T4 materials comprising 60%... T1... only 7%"*) and its citing of *"Speech by Governor Barr"*. Fable folds source quality into the corpus-canon lever (#5) and does not rank a separate IF-source fix. **Adjudication:** Codex is right to surface it — the prompt explicitly demanded *"only... high-quality, English-language journal articles"* and **neither** report complied (Codex is careful to note step3 *also* leans on WEF/PwC/IBM/Deloitte/Gartner and *"does not truly satisfy the restriction either"* — it just *looks* compliant via author-year attribution). So this is partly a real IF lever and partly a *readability-of-provenance* effect. I kept it as ranked fix #6.

5. **Kimi.** Not a disagreement — an **absence**. Any three-way "adjudication" the brief anticipated is a two-way one. I have attributed nothing to Kimi.

---

## Appendix — what a superficial reading of A would have missed (both models, consolidated)
- A's Synthesis section is ~13/16 pointer sentences — looks like a section, contains almost no propositions.
- Half of A's "Key Findings" are not findings (they are cross-references).
- A's first "Tension" callout is truncated mid-sentence at "U.S."
- *"Private domestic final purchases have been solid."* shipped as a single-source **finding** in an AI-labor report.
- astro-ph and gr-qc (astrophysics / general-relativity arXiv categories) appear as contradiction subjects in the scored appendix.
- B's orphaned anaphora (*"The BLS corroborates this productivity slowdown", "However, this process...", "The consequence has been..."*) are the direct textual scars of 147 faithfulness removals.
- B's and step3's summary tables both contain the mid-word shard *"| Source | — | — | bor Market Effects of AI. |"* ("La**bor**" truncated to "bor").
- champ_ourcorpus repeats two sentences verbatim back-to-back (twice) and cites a nonexistent "Table 2" — **champion composition is not magic; on a junk corpus it degrades to grab-bag prose.** The champion's edge is corpus + packaging; our gate already beats it on the packaging-independent dimensions (Comp/Insight/IF) on equal corpus.
