# THE OPUS SYNTHESIS — v1, UNATTACKED (its attack phase died to rate limits)

## STATUS: three of its claims are VERIFIED ON DISK by Opus-4.8 (the 0.263 system score,
## the polaris_vm_t* files, WHEEL_PROGRESS.md:411). Its 'document shape is worthless' claim
## CONTRADICTS the judge's own written critique and is NOT yet verified.


## THESIS
Our problem is not that we write badly — it is that we have a demo, not a system, and that the demo answers a question nobody asked. Verified tonight: our end-to-end system scores 0.263 across five real tasks while our hand-iterated task-72 artifact scores 0.4396, so the hand-tuning gap (0.187) is LARGER than the gap to SOTA (0.105); and across 898 real (article, score) pairs already on disk, every document-shape lever that all six designs are built on — section count, word count, paragraph length, tables, citation format — collapses to a coefficient of ~0.000 once you remove system identity with two-way fixed effects. So the plan is: derive from the prompt WHAT KIND OF DOCUMENT IS BEING ASKED FOR, retrieve evidence that is actually ABOUT the question, reason to something true and non-obvious, and treat every structural/cosmetic lever as a free afternoon booked at ZERO expected points.


## THE_PLAN
## PART 0 — THE THREE FINDINGS THAT REFRAME THE MISSION (I ran all three tonight; none is quoted from the brief)

**F1. THE SYSTEM SCORES 0.263. THE ARTIFACT SCORES 0.4396. THE MISSION IS THE SYSTEM.**
`third_party/deep_research_bench/results/race/polaris_vm_t{72,75,76,78,90}` — our pipeline run end-to-end on five real benchmark tasks:
```
t72 0.2530 | t75 0.2839 | t76 0.2646 | t78 0.2107 | t90 0.3026   MEAN 0.263
```
Our task-72 artifact (`noise_r10_1..5`, k=5) = 0.4397/0.4330/0.4334/0.4405/0.4512 → **mean 0.4396, SD 0.0074** (exact; the headline 0.4382 is not reproducible from the stored runs).
**The distance between our system and our artifact is 0.187. The distance from our artifact to bodhi is 0.105.** Every plan on the table — Sol's, Fable's, and all six architects' — optimizes the artifact. The mission says "beat SOTA on ANY question." On any question we score 0.263. `WHEEL_PROGRESS.md:411` already says "2ND-DRB-TASK GENERALITY GATE — BLOCKED" and nobody built on it.

**F2. DOCUMENT SHAPE IS WORTH APPROXIMATELY ZERO. THIS KILLS A LEVER FAMILY IN ALL SIX DESIGNS, INCLUDING THE ONE I WAS ABOUT TO BUILD.**
We hold **898 scored (article, score) pairs** — 9 systems × 100 tasks, articles in `drb_corpus/gpt55_board/*.jsonl`, scores in `scores/*/raw_results.jsonl`. This is the cheapest experiment in the project: **$0, zero judge calls.** Nobody ran it.

Within-task (reference fixed → pure target effect), the correlations look like a mandate:
```
H3 count    r = +0.519   (and r = +0.538 with INSIGHT, the heaviest dimension)
tables      r = +0.466
H2 count    r = +0.451
words       r = +0.417
[n] markers r = +0.226   (POSITIVE — the thing both plans delete)
in-prose attribution r = +0.129   (WEAK — the brief's crown-jewel lever)
median paragraph     r = +0.010   (ZERO — the "highest-confidence move in the whole plan")
```
Then add **two-way (task × system) fixed effects** — the specification that removes "which system wrote this":
```
                     within-task   within-system   TWO-WAY FE
log(words)  per +1SD   +0.0267        +0.0039        +0.0069
sections    per +1SD   +0.0211        -0.0003        +0.00000
R^2                     0.614          0.021          0.086
```
**Section count's effect is exactly zero. Length's is +0.0069/SD — below the k=5 resolvable effect of +0.0094.** The entire within-task correlation was system identity: good systems section well AND score well; sectioning is not why they score well. Confirmed by the system table — the top systems span **2,035 (dalpha, 0.5309) to 6,259 (lunon, 0.5347) median words**, a 3× length range with a 0.004 score spread. Sol's 13,500–16,500-word target and Fable's 15,000–16,000 are read off the one artifact we happened to open.

*The one honest caveat, and I will not hide it:* our 677-word median paragraph sits at the **99.7th percentile of all 898 articles** (only 3 of 898 exceed 400w). The regression's null on paragraph length is estimated over a range (p5–p95 = 0–125 words) that contains no point anywhere near us. **The observational null does not extrapolate to our operating point.** So we fix the paragraphs — it costs an afternoon — and we book ZERO for it, and Experiment E4 settles it by intervention. Section count *does* have support near us (58 of 898 articles have zero sections; we have 11, the 25th percentile), and there the zero is real.

**F3. NO SUBSET OF CRITERIA CLOSES THE GAP. THE OBJECTIVE IS NOT ADDITIVE.**
`deepresearch_bench_race.py:155-160`: `overall = target_total / (target_total + reference_total)` against a FIXED reference (`data/test_data/cleaned_data/reference.jsonl`, 100 articles; task-72's is 9,029 words, **but the corpus median is 3,660 and the min is 297**). Sol's ratio arithmetic is right and I re-derived it: T/R must go **0.784 → 1.252, ×1.60**. On the judge's own scale (`score_prompt_en.py`: 0–10 continuous; *4–6 = "average, basically meets"*; *8–10 = "excellent, fully meets or exceeds"*), if the reference scores R≈7/10 then our weighted mean across all 25 criteria must move **from 5.5/10 to 8.8/10**. That is a band jump on the *mean of everything*.
**Take task 72's single heaviest criterion (w=0.080, "Critical Synthesis and Nuanced Evaluation") from 5.5 to a PERFECT 10. It buys +0.016. We need +0.117.**
Every plan that lists five levers and sums their deltas — Sol's 0.563, Fable's 0.572 — is mis-modelling the instrument.

**PUT F2 AND F3 TOGETHER AND THE PLAN WRITES ITSELF.** The only thing that can move all 25 criteria at once is whether the document *answers the question that was actually asked, from evidence that is actually about it, and says something true and non-obvious.* That is CONTENT. And content is precisely where our system is catastrophic: it admitted ResNet, the BMJ PRISMA checklist and a 1974 paper on reading automaticity into an AI-and-labour corpus, and it scored **0.2107 on task 78** — a Parkinson's family-advisory question — because it wrote a literature review nobody asked for.

---

## PART 1 — THE SYSTEM. SIX STAGES. ZERO DOMAIN CONSTANTS.

### STAGE 0 — THE COMPILER: prompt → `brief.json` (new: `scripts/compile_brief.py`)
Input: **the task prompt. Nothing else.** This is the whole anti-overfit keystone and it is the fix for the 0.263.

**0a. THE RUBRIC.** Run RACE's own generators verbatim from `third_party/deep_research_bench/prompt/criteria_prompt_{en,zh}.py` (I confirmed: five generator prompts, each handed only `{task_prompt}`). k=3, take the **union** — single-sample derivation silently drops criteria and the drops concentrate in INSIGHT. Emit ~25 weighted criteria + 4 dimension weights, schema-identical to `data/criteria_data/criteria.jsonl`.
Apply one measured, domain-free correction: **+0.03 to the insight weight** (derived insight was below stored in 7/7 tasks in the derivation architect's run). Insight's true mean weight across all 100 tasks is **0.352 — it is the heaviest dimension on the benchmark, on average**, and its range is 0.11–0.42, so "insight is 0.32" is a task-72 fact, not a system fact.

**0b. THE ANSWER SHAPE — my central addition, and it is the direct fix for the 0.263.**
The instruction-following criteria are the judge's most literal restatement of what the prompt demands. Read them and you get the *document type*. Ground truth I pulled tonight from `criteria.jsonl`:
- **Task 78 (Parkinson's):** three of the top six criteria are literally *"Response to Query on Warning Signs by Disease Stage"*, *"Response to Query on Post-DBS Adjustments and Support"*, *"Response to Query on Intervention Signs for Family Members."* Readability weight **0.20** (43% above task 72's). This wants a **staged, family-facing advisory.** We scored **0.2107** — our worst — because we shipped a literature review.
- **Task 90 (ADAS liability):** insight **0.38**; top criteria *"Sophistication in Synthesizing Technical, Legal, and Case Law Perspectives"* (0.095) and *"Originality, Feasibility, and Justification of Proposed Regulatory Guidelines"* (0.076). This wants an **argued proposal.**
- **Task 75 (metal ions / CVD):** insight 0.35; *"Critical Appraisal of Clinical Evidence for Efficacy"* (0.0875). This wants a **critical appraisal that reaches a verdict.**
- **Task 72:** a peer-reviewed literature review.
`brief.answer_shape` = `{deliverables: [one required output per instruction criterion], stance: verdict|survey|proposal|advisory, audience: expert|practitioner|layperson, must_answer: [sub-questions lifted verbatim from the prompt]}`. **The outline is generated from this, not from a checked-in skeleton.** One system, four documents.

**0c. SCOPE (operator FIX 3), all derived:** `topic_statement` (the SELECT yardstick) · `venue_class` — **derived from the prompt's own words**: task 72 says *"only cites high-quality, English-language journal articles"* → hard journal gate; *"what caused the 2008 financial crisis"* says no such thing → **the FCIC Report, BIS papers and Gorton are admissible, and Sol's blanket journal-only rule would delete them** · `recency_window` — a 2026 AI question needs 2024+; a 2008-crisis question needs 2007–2012 primary + retrospectives and **a recency bonus there is actively wrong** · `language` · `entity_types`.

**0d. THE COVERAGE MATRIX.** For each derived criterion, one call: *"enumerate what a report must contain for an expert to score this 10/10."* Rows = criteria, columns = facets. A cell is FILLED when ≥2 admitted cards support it. **This replaces Sol's hand-built 8×10 matrix and Fable's 9×6 — both read off task 72's rubric by hand.**

**0e. LENGTH BUDGET.** Derived from facet count, with a **floor at ~2,500 words** (below that every system on the board fails: grok at 500w scores 0.412, perplexity at 781w scores 0.431) and **no target ceiling.** We do not pad. Padding to a word count is exactly what routed 104 off-topic medical papers into our Introduction.

**THIS STAGE IS FALSIFIABLE BEFORE WE WRITE ANOTHER LINE.** The benchmark ships the judge's real criteria for all 100 tasks. Run the compiler on all 100 prompts, measure weighted rubric-mass recall + dimension-weight L1. **That is the anti-obvious proof of generality and it is executable in a day.**

### STAGE 1 — RETRIEVAL, AIMED BY THE RUBRIC (operator FIX 1, FIX 2)
- **Anchors are DISCOVERED, never named.** Delete Sol's 15 and Fable's 5. Broad search → **LLM topic gate against `scope.topic_statement`** → rank by citation count **WITHIN the relevance-gated pool.** This ordering is not cosmetic: Crossref `sort=is-referenced-by-count` on an AI-and-labour query returns **Faster R-CNN (33,962 cites)**; on a 2008-crisis query it returns **SHELX crystallography (79,867 cites)**. **Citation-sort is topic-blind, and it is the deterministic generator of the ResNet/PRISMA junk in our corpus.** That kills Sol's `log(citations)` ranker and Fable's `citation-percentile × venue tier` ranker as *primary* keys.
- **PROPOSE-THEN-RESOLVE for the canon.** Keyword search provably cannot find Autor-Levy-Murnane (its title contains neither "AI" nor "labor market"). So: the LLM *proposes* canonical works; **Crossref/PubMed is the sole authority on whether they exist**; unresolved proposals are silently dropped. Fabricated papers become structurally impossible. **Guard the false-negative side too** — the derivation architect's own resolver silently deleted MajesTEC-1, KarMMa, CARTITUDE-4 and MagnetisMM-3 on a 0.6-Jaccard title gate (a 57% FNR in one domain), and it printed a green tick. FNR is measured and published every run.
- **Recency by date-filtered search, not forward traversal** (operator FIX 1: Crossref `filter=type:journal-article,from-pub-date:2024-01-01` → 344,623 hits). **Sol's blocking Gate 0 is deleted and his 35%-chance-of-sinking-the-plan risk is retired.** OpenCitations COCI forward traversal (verified live, 1,772 citing DOIs for AR2020) becomes a bonus lane.
- **SELECT is the broken stage and it becomes a HARD GATE on the CITABLE corpus.** `retrieval/topic_relevance_gate.py:98-110` already exists, already fires, already correctly labels ResNet off-topic — and then **keeps it**, because `PG_SCOPE_TOPIC_GATE_HARD_DROP` defaults to 0 under an old "weight, don't filter" instruction. Resolution: scope stays a WEIGHT on the *research* pool and becomes a HARD GATE on the *citable* pool. Both instructions were right, at different stages.
- **Queries are DEFICIT-DRIVEN.** Round 1 aims at unfilled facets. Round N aims at **the judge's own written complaint** (Stage 5). **STOP when the matrix is full**, not at a paper count. Delete "110–160 DOIs" and "120–150 named."

### STAGE 2 — EVIDENCE: extractive cards (Fable's rule, kept verbatim)
**The LLM may SELECT character offsets. It may never COMPOSE spans.** Every field that licenses a claim (`finding`, `N`, `design`, `mechanism`) is a verbatim quote with a char offset into fetched text, **or NULL**. Missing texture is *narrated* as missing, never filled — a required output field with an absent input is the canonical invention condition.
Three bugs, all confirmed live tonight:
1. `cellcog_composer.py:167` copies `'mechanisms': f.get('mechanisms') or []` **straight from LLM output with no span check**, while `claim`/`span` beside it ARE checked. Two-hop laundering. **Every mechanism carries its own verbatim offset or is dropped.**
2. `journal_corpus_fetch.py` accepted a **548-word Oxford landing page** as FULLTEXT. Guard: ≥1500 words AND title-in-body AND no landing-page chrome.
3. Three tiers, all three counts always published: QUOTABLE / ABSTRACT-CITABLE / NAMED. **An abstract may never license a mechanism.**
**The card's declared dimensions are DERIVED per domain, not the checked-in enum.** `synthesis_contract.py` currently hardcodes `level ∈ {task, worker, firm, region, economy}` and puts `'AI', 'Artificial'` in `SAFE_CAPS` — **the safety gate itself is overfit to AI-and-labour.** Any dimension with <0.75 dual-extraction agreement is disqualified from carrying analytical weight, and the exclusion rate is published.

### STAGE 3 — REASONING: the contradiction index and the corpus census
Fable's CONTRADICTION INDEX is the best constructive idea in either foundation plan and it survives. Pairs of cards whose *extractive* findings diverge on the same question, labelled with the declared dimensions on which they differ.
**THE CORPUS CENSUS is the thesis, and it is true by construction:**
> *"Across the 41 divergent pairs among the 137 works retrieved for this review, 29 divide along the unit at which outcomes are measured."*
This is a **measurement of our own evidence base** — computed in code, printable as a table, checkable by anyone. It is the reviewer's own reasoning, marked as such (operator FIX 5), and it is **strictly more honest than cellcog**, which asserts the same class of claim with no count behind it. No system on the board has this.
I am **demoting the tension lattice from "the organ" to "one insight generator"** — its own author names the killer risk (the sorting statistic is only as good as LLM-extracted card dimensions) and it has nothing to say on a corpus with no contradictions. First-class fallbacks: GRADIENT (the field converges, here is the shape), FRONTIER (here is where the evidence stops), NULL (say so honestly).

### STAGE 4 — COMPOSITION: shape-matched, evidence-dense, and cosmetically correct at zero booked value
The outline comes from `brief.answer_shape` × the coverage matrix. Every derived criterion gets a home; criterion text is passed **verbatim** to the section writer.
Cosmetics — **do them all in one afternoon, book ZERO, never cite them as progress:** ~100w paragraphs; 30+ subsections; a summary table; a structured abstract; the graded epistemic taxonomy (six types, not one); cellcog's *measured* citation form `Author(s) (YYYY), in the *Journal*, find that...` (**not Sol's Format-D — Fable measured that 160 of cellcog's 177 year-parens are narrative form with the author already in prose, and that survives the cleaner**); internal cross-references; the organizing-puzzle ring; kill the meta-opener and the 240 `[n]` markers. **F2 says all of this together is worth ~0.00–0.02 and I refuse to book it.**
What we book instead: **the document answers every `must_answer` sub-question, in the demanded stance, at the demanded audience level, from evidence that passed SELECT.**

### STAGE 5 — MEASUREMENT: stop deleting the grader's own answer
`deepresearch_bench_race.py` builds `llm_output_json` — for all 25 criteria: our raw 0–10, **the reference's raw 0–10**, and the judge's **written comparative analysis** — and then `final_result` keeps five floats and throws the rest away. **Patch it. Six lines.** Every score run now emits the deficit ledger, the reference's raw total R (which fixes the analytic ceiling at `10/(10+R)`), and the grader telling us in its own words why we lost. That text feeds Stage 1's next query round and Stage 4's revision.
**But per-criterion scores are NOT a lever-scoring instrument until their noise is measured** — the judge scores all 25 in one call, so they are halo-correlated. Re-score the 5 banked `noise_r10_*` artifacts through the patched harness ($0.55) to get the per-criterion SD matrix. **No criterion is a "deficit" until its own SD is known.** Skipping this is how this repo produced commits 947d2b5, 225b323 and b3acb72 — and it would reproduce them at 25× resolution.


## DERIVATION_LAYER
**THE KEYSTONE, AND THE ONLY COMPONENT IN THE SYSTEM WHOSE GENERALITY CAN BE *MEASURED* RATHER THAN ARGUED.**

RACE's judge generates its own 25 criteria and its own 4 dimension weights from the task prompt alone — I confirmed the mechanism in `prompt/criteria_prompt_en.py` (five generators, each handed only `{task_prompt}`), and the benchmark ships the answers for all 100 tasks in `data/criteria_data/criteria.jsonl`. **We can run the same generators on the same prompt. And because the ground truth is on disk, we can grade our own derivation on 100 tasks across every domain in the benchmark — before we build anything downstream.**

**WHAT IS DERIVED (everything):** the criteria · the dimension weights · the ANSWER SHAPE · `scope.topic` · `scope.venue_class` · `scope.recency` · `scope.language` · the coverage axes · the cells · the anchor set · the outline · the section budgets · the length target · the card schema's declared dimensions · the epistemic tags · the gap claims · the stopping condition.

**WHAT IS HARDCODED — four things, and I claim each is domain-free:** (1) RACE's five generator prompts, imported verbatim from `third_party/` — they contain no domain; (2) the relation vocabulary (CONVERGES / CONTRASTS / REMAINS_UNRESOLVED / COVERAGE_GAP) — these name relations *between evidence*, not topics; (3) the +0.03 insight-weight correction, estimated across 7 domains; (4) the rule that Crossref/PubMed, not the LLM, decides what exists. **A CI grep bans domain nouns from every file outside `brief.json`.**

**THAT CI GREP IS NOT THEORETICAL — THE CODEBASE IS RIDDLED.** `src/polaris_graph/generator/summary_table.py:270` holds `_DOMAIN_PHRASES` — 119 hand-written AI-and-labour phrases ("deskilling", "reskilling", "radiologist", "paralegal", "call centre") — and `:307` holds `_RISK_PHRASES`. They populate the *cells* of the live summary matrix. I grepped further and found domain vocabulary in **10+ live source files**: `decomposer.py`, `claim_atom_extractor.py`, `scope_classifier_llm.py`, `template_classifier.py`, `evidence_value_extractor.py`, `domain_signal.py` (a GLP-1-flavoured clinical term list). **The overfit is not in the plans. It is checked into the system that scores 0.263.**

---
### WALKTHROUGH A — CLINICAL: *"CAR-T versus bispecific antibodies in relapsed/refractory multiple myeloma — which should be preferred, and for which patients?"*
- **RUBRIC — derived.** The benchmark's real clinical tasks show exactly the shape this produces: task 75's criteria are *"Critical Appraisal of Clinical Evidence for Efficacy"* (0.0875), *"Thoroughness of Clinical Evidence on Feasibility and Safety"*, *"Breadth of Proposed Intervention Modalities"*; task 78's are *"Response to Query on Warning Signs by Disease Stage."* Nothing resembling "industries" or "4IR" can appear, because the generator never sees them.
- **WEIGHTS — derived.** Task 75's real weights are C .29 / **I .35** / IF .22 / R .14. Insight *rises*; instruction-following *falls* (this prompt imposes few constraints). A pipeline tuned to task 72's .29/.32/.25/.14 mis-allocates its whole budget.
- **ANSWER SHAPE — derived: COMPARATIVE VERDICT.** The instruction criteria will read *"Responsiveness to the question of which therapy should be preferred"* and *"Explicit patient-specific recommendations"* — i.e. **half the instruction weight is a VERDICT.** Sol's and Fable's composers, which emit a literature review no matter what, service none of it.
- **VENUE CLASS — derived: NOT journal-only**, because this prompt does not say so. Pivotal trials, guidelines, registries, and conference readouts (ASH/ASCO — where myeloma's newest pivotal data lands before journals) are admissible. **Sol's blanket journal gate, read off task 72's prompt text, would delete the evidence base.**
- **RECENCY — derived: 2019+**, from the technology clock (first BCMA CAR-T approvals), not from a constant.
- **ANCHORS — discovered.** Broad search → topic gate → citation rank *within the gated pool* → KarMMa, CARTITUDE, MajesTEC, MonumenTAL surface as seeds. Nobody typed them. (And the resolver's FNR gate fires here: this is the exact domain where a naive title-match verifier silently deleted four of them.)
- **REASONING — the same code path.** The contradiction index finds CARTITUDE's ORR diverging from real-world registry outcomes; the resolving dimension computes out as *trial-eligible vs. frail/real-world population* — the identical mechanism as cellcog's firm-vs-worker resolution, with no new code.

### WALKTHROUGH B — HISTORICAL: *"What caused the 2008 financial crisis?"*
- **VENUE CLASS — derived: NOT journal-only.** The **FCIC Report, BIS working papers, Gorton's book** are the primary literature. Sol's rule deletes them; ours admits them because the prompt never asked for journals.
- **RECENCY — derived: 2007–2012 primary + later retrospectives.** **Sol's "recency-bonus for ≥2023" is not merely useless here — it is actively wrong**, and it would promote 2024 commentary over the FCIC Report.
- **ANCHORS — discovered.** Citation-sort *alone* returns SHELX crystallography (79,867 cites). Topic-gate *then* citation-sort returns Mian-Sufi, Gorton, Reinhart-Rogoff, Brunnermeier. **This single reordering is the difference between a corpus and a junk pile, and it is the mechanism that put ResNet in ours.**
- **ANSWER SHAPE — derived: CAUSAL-EXPLANATORY with contested attribution.** Not a verdict, not an advisory. The insight criteria will pay for adjudicating *between* causal accounts (global savings glut vs. regulatory failure vs. securitisation incentives vs. monetary policy), which is exactly what the contradiction index + corpus census produce.
- **THE CENSUS FIRES UNCHANGED:** *"Across the 34 divergent pairs among the 112 works retrieved, 22 divide along whether the account is monetary or micro-institutional."* Same code. Same struct. No domain noun anywhere.

**IF THE COMPILER'S RUBRIC-MASS RECALL IS BELOW ~80% ON THE 100-TASK GROUND TRUTH, THE KEYSTONE IS WEAK AND I WILL SAY SO** — and we fall back to the static rubric at `score_prompt_en.py:104-194` as a floor, downgrading the generality claim to "we derive scope and shape, not the full rubric." That is a one-day finding, not a one-month one.


## RETRIEVAL
**RETRIEVAL WAS NEVER SHALLOW. IT WAS AIMED WRONG — AND I FOUND THE EXACT MECHANISM.**

Crossref `sort=is-referenced-by-count` is **topic-blind**: on *"artificial intelligence automation impact on labor market"* it returns Faster R-CNN, SMOTE, DeepLab; on *"causes of the 2008 financial crisis"* it returns SHELX crystallography and GLOBOCAN cancer statistics. Default relevance sort is the opposite failure — on-topic but quality-blind (2026 papers with 0 citations in near-predatory venues). **ResNet, the BMJ PRISMA checklist and a 1974 paper on reading automaticity are not accidents in our corpus. They are the deterministic output of ranking a keyword query by citation count.** That single fact kills Sol's `log(citations)` ranker and Fable's `citation-percentile × venue tier` primary key at the root.

**THE CHAIN, END TO END:**
1. **QUERY-GEN** — from `brief`: one query family per unfilled matrix cell, plus the prompt's own `must_answer` sub-questions. Round N ≥ 2 generates from the judge's written complaint (Stage 5's ledger). *No topic regex anywhere.*
2. **SEARCH** — Crossref (relevance sort + **date-filtered** for the derived recency window; operator FIX 1: `from-pub-date` returns 344,623 journal articles 2024-26, which **retires Sol's blocking Gate 0 and the 35% risk he priced against it**), plus PubMed / domain registries when `scope.venue_class` admits them. OpenCitations COCI forward traversal is a **bonus lane, not a dependency** (verified live: 1,772 citing DOIs for AR2020). OpenAlex list endpoints and the Semantic Scholar fallbacks at `deep_fetch.py:78-88` are **deleted** — they 429/404 and silently inflate the perceived fetch budget.
3. **PROPOSE-THEN-RESOLVE** for the canon that keyword search structurally cannot reach. LLM proposes; **Crossref/PubMed is the authority on existence**; unresolved → dropped. Fabricated papers become impossible *upstream of the writer*, which is stronger than any prose gate. **And we measure the FALSE-NEGATIVE rate every run** — a strict title-match verifier deleted four landmark myeloma trials in one domain and printed a green tick; in a field nobody on this team knows, that failure is invisible.
4. **SELECT — the broken stage, and now a HARD GATE.** An LLM relevance judge against `scope.topic_statement`. `topic_relevance_gate.py` already exists, already fires, already gets the right answer, and **already keeps ResNet** because `PG_SCOPE_TOPIC_GATE_HARD_DROP` defaults to 0. Resolution: **scope is a WEIGHT on the research pool and a HARD GATE on the citable pool.** Out-of-scope evidence may inform; it may never be cited.
5. **WEIGHT** — within scope only: relevance × venue standing × citations × recency-fit-to-derived-window × groundability. **Tier is a weight, never a filter. Prestige is not relevance.**
6. **DEDUP** — canonical DOI + title-similarity clustering to merge working-paper/journal version pairs into ONE work carrying the journal identity and the WP text. Sol's working-paper TEXT lane survives (cite the journal, quote the WP PDF, never quote a number from a WP), because Unpaywall genuinely cannot reach the econ canon.
7. **STOP** — when the coverage matrix is full, or two consecutive rounds add <3 cells. **Not at a paper count.**

**HOW MANY PAPERS? THE HONEST ANSWER IS: WE DO NOT KNOW, AND IT IS THE WRONG QUESTION.** F2 says evidence *volume* is confounded with system quality; F3 says the two criteria the entire journal-corpus apparatus serves ("Depth and Representativeness", 0.0435; "Exclusive Citation of High-Quality Journal Articles", 0.0375) total **8.1% of task 72's score** — driving both from 5.5 to a near-perfect 9.5 buys **+0.0142** against a 0.116 gap. **Retrieval is not the gate. Retrieval is the thing that makes the other 92% of the rubric answerable at all** — you cannot critically synthesise evidence you do not have, and you cannot say anything true about AI and labour from a corpus containing the PRISMA checklist. That is why retrieval is rebuilt: not for the 8.1%, but because it is the input to everything.


## REASONING_AND_FAITHFULNESS
## THE LINE: **YOU MAY REASON FREELY. YOU MAY NEVER NAME FREELY.**

Fabrication is always the introduction of a **PARTICULAR** — a number, an entity, a study, a date, an attribution — or the **binding of a proposition to a source that does not assert it.** It is never the assertion of a **RELATION**. Everything the judge pays for lives in relations; everything fraud consists of lives in particulars. Separating those two is the whole system.

### WHAT I MEASURED, AND IT IS DAMNING
I ran our own gates from `scripts/synthesis_contract.py` against cellcog's own task-72 prose:
```
cellcog body sentences:                    509
reviewer-voice (uncited):                  368  = 72% of the document
  DELETED by NO_VERDICT_VOCAB              340
  DELETED by UNIVERSAL                       7
  DELETED by CAUSAL_IMPORT                   6
  DELETED by FORECAST                        5
>>> TOTAL DELETED BY OUR CONTRACT:     341/368 = 93%
```
**`VERDICT_VOCAB` — a 17-item hardcoded English idiom list — does 93% of the damage by itself. It is not a faithfulness gate. It is a style gate calibrated against nothing.** And the collateral is exact:
- `UNIVERSAL` bans the word **"none"** — which makes `COVERAGE_GAP`, *an operation the contract itself defines at line 67*, permanently unpassable, **and rejects the operator's own prescribed FIX-5 sentence** (*"Within the 137 journal articles retrieved for this review, **none** measures X"*).
- `FORECAST` bans the word **"will"** — which makes the insight rubric's own criterion *"Value and Foresight in Delineating Implications and Future Research Agendas"* (w=0.048 on task 72) **literally unwritable.**
- **Rule 10** demands ≥2 shared content-lemmas with the premise text — it *punishes abstraction*, the exact thing insight pays for.
- `SAFE_CAPS` contains `'AI', 'Artificial'` and `CONTRASTS_LEVEL` hardcodes `{task, worker, firm, region, economy}`. **The safety gate is itself overfit to AI-and-labour and cannot even be evaluated on a clinical question.**

**We built a gate that deletes the rubric. And it has never once fired** — `validate()` is imported at `cellcog_composer.py:49` and grep shows it is **called nowhere.** The only thing between LLM prose and the page is a regex `_clean()`.

### WHAT REPLACES IT — THREE PROPERTIES, AND THE THIRD IS THE ONE EVERY DESIGN MISSED

**1. REFERENTIAL CLOSURE (deterministic; no LLM in the loop).** Every particular in the shipped prose — every number, proper noun, study, venue, year, person, organisation — must resolve to a registered entry in the evidence ledger (card id + character offset) or to the prompt's own lexicon. Pure set membership. **This makes fabricating a FACT structurally impossible, and it cannot silently fail the way an LLM gate can.**

**2. ATTRIBUTION INTEGRITY.** Any sentence attributing a proposition to a named source must be ENTAILED by that source's own extractive span. `entailment_judge.py`'s NEUTRAL clause **stays, unchanged, in the evidence lane.** Every author surname and journal name in prose must string-match a card the sentence cites; an off-by-one binding is a false claim about a named real person and it never ships.

**3. SYNTHESIS ENTAILMENT — THE GATE THAT ALL SIX DESIGNS OMIT, AND WITHOUT IT "DELETE THE GATES" IS GENUINELY UNSAFE.**
The attack on the composer design proved it with executable code: referential closure alone **admits mechanism transplant, misattribution, and sign inversion** — all *false relations over true particulars*, which a set-membership check is blind to by construction. So: a reviewer-voice synthesis sentence gets a **second, cheap entailment call where SPAN = the concatenated claim texts of exactly its own cited premises.** NEUTRAL if it asserts a relation, direction, or attribution those premises do not support. Premises are short; this costs almost nothing. **This is the single most important correction I am making to the "referential closure" thesis, and I take it from the attack, not from the design.**
Three sub-rules that fall out:
- **Named attribution is BANNED in the synthesis lane.** A synthesis relates already-attributed premises; it must not itself name a source. That kills the Autor-for-Babina swap by construction.
- **Causal language requires an explicit `mechanism_premise_id`**, and the effect it attaches to must be *that premise's own claim* — not any other cited card's. Fable's per-sentence mechanism pool is necessary and **not sufficient**: one card declaring one mechanism currently licenses causal language about a *different* card's finding.
- **`COVERAGE_GAP` becomes a first-class operation**, exempt from UNIVERSAL/NUMERIC/anchoring, with **the count computed in code from `len(corpus)`, never emitted by the LLM**, in a fixed scope template. The honest gap claim becomes admissible; the false universal (*"No peer-reviewed study has ever..."* — a claim about 10⁴ papers made from a 140-item convenience sample) stays banned.

### WHAT SURVIVES FROM FABLE, UNCHANGED — she got these right and they beat the operator's first formulation
Extractive-only card fields (**the LLM may SELECT offsets, never COMPOSE spans**) · the mechanism pool is the union of the **sentence's OWN cited cards**, never the corpus (a corpus-wide pool over 140 cards degenerates gate #6 into *"does this sentence contain a word the field uses"* and **flips our own ATTACK #1 from REJECT to PASS**) · **hedge + tag alone is COSTUME, never a licence** — a synthesis must be a conditional over ≥2 admitted premises carrying `premise_ids`, so the no-new-number and no-new-entity gates STILL RUN · corpus-scoped gap claims · the ISSN allowlist, so *"SSRN Electronic Journal"* can never be rendered as a journal.

### THE THING THAT MUST BE BUILT FIRST, BEFORE ANY RELAXATION SHIPS
**We are proposing to relax faithfulness rules while relying on gates with a documented history of looking armed and never firing.** `validate()` has been imported-and-never-called through at least two shipped "fixes" (commits 225b323, b3acb72). So **before one gate is loosened**: a CI test that feeds a **poisoned card** through the real composer and asserts **zero poisoned sentences on the page** — a test that FAILS if the gate is bypassed, not one that passes because the gate returned True in isolation. Plus the adversarial suite extended with the three new attacks (transplant, misattribution, sign inversion) and the corpus-scoped gap claim as a **MUST-ADMIT** case. **Zero false admissions AND zero false rejections, green on every commit.** If that test is not the first thing built and kept green, this is not scholarship — it is an unlocked door.

**And the hard abort stands: one fabricated particular on a shipped page burns the artifact regardless of score. A 0.60 obtained by fabricating is a 0.00.**


## COMPOSER
**THE COMPOSER'S JOB IS TO ANSWER THE QUESTION THAT WAS ASKED. EVERYTHING ELSE IS TABLE STAKES BOOKED AT ZERO.**

F2 is the discipline here. Across 898 real scored articles, under two-way fixed effects, **section count buys +0.00000 and log-words buys +0.0069/SD (below the k=5 resolvable effect).** The top systems span **2,035 to 6,259 median words** with a 0.004 score spread. So:

**WHAT THE COMPOSER IS BUILT AROUND (the things that can move all 25 criteria at once):**
1. **THE ANSWER SHAPE.** The outline is generated from `brief.answer_shape` — deliverables, stance, audience, `must_answer` sub-questions — crossed with the coverage matrix. A verdict question gets a verdict. An advisory question gets staged, family-facing guidance (task 78's readability weight is **0.20**, and three of its top six criteria are literally *"Response to Query on..."*). A proposal question gets an argued proposal (task 90's insight weight is **0.38**). **We scored 0.2107 on task 78 because we shipped a literature review. That is the 0.263, and this is its fix.**
2. **EVERY DERIVED CRITERION GETS A HOME, AND ITS TEXT IS PASSED VERBATIM TO THE SECTION WRITER.** This is how the 4IR criteria get serviced *without* Sol's 4IR spine — Fable's decode proves cellcog compares AI to prior revolutions in **one sentence** and then explicitly demotes the frame, while the system that builds the four-revolution comparison table is WhaleCloud at 0.5396. **The criteria are real; the prescribed content was wrong.** Generalised: *critique-and-subordinate the frame the prompt names.*
3. **THE THESIS, COMPUTED.** The corpus census — *"Across the 41 divergent pairs among the 137 works retrieved, 29 divide along the unit of observation"* — with GRADIENT / FRONTIER / NULL fallbacks when the corpus has no contradictions. Insight sold in **named, counted units** with first-person ownership and a graded epistemic tag. The organizing-puzzle ring: stake a real evidentiary tension in the opening, resolve it in the close, because those are the two passages the judge reads hardest.
4. **EVIDENCE DENSITY AT THE PARAGRAPH LEVEL.** evidence → evidence → punchline. Methods texture (N, design, identification) emitted **only** where the card carries the extractive field; absence narrated, never filled.

**THE AFTERNOON OF COSMETICS (all of it, once, then never mentioned again as progress):**
~100w paragraphs (we are at **677 — the 99.7th percentile of 898 articles; only 3 of 898 exceed 400w**, so we are off the distribution and the observational null does not cover us) · 30+ subsections (we have **zero H3**) · a summary table · a structured abstract · six-type epistemic tags · **cellcog's measured citation form** `Author(s) (YYYY), in the *Journal*, find that...` — **NOT Sol's Format-D**, which nobody on the board uses and which Fable's measurement refutes (160 of cellcog's 177 year-parens are narrative form, author already in prose, and they survive) · internal cross-references · delete the 240 `[n]` markers · delete the meta-opener (*"This report synthesizes the retrieved research evidence on the question above"* — there is no question above) · **delete the hardcoded abstract at `cellcog_composer.py:400-414`**, which asserts *"draws exclusively on peer-reviewed... journal articles identified through citation-graph expansion"* regardless of the actual corpus — **a fabricated compliance claim aimed squarely at the instruction-following grader, and the most dishonest line we currently ship.**

**LENGTH IS DERIVED, FLOORED, AND NEVER PADDED.** Floor ~2,500 words (below which every board system fails). No ceiling target. **We do not write 16,000 words because cellcog did** — the reference median is 3,660 words, bodhi wins task 72 at 4,361, and dalpha scores 0.5309 at a 2,035-word median. Padding to a word count is how 104 off-topic medical papers got routed into our Introduction.


## MEASUREMENT
## THE CHEAPEST FALSIFYING EXPERIMENT COST $0, IT RAN FIRST, AND IT ALREADY FIRED.

**E0 — THE 898-ARTICLE FIXED-EFFECTS REGRESSION. $0. ZERO JUDGE CALLS. ALREADY DONE (above).**
We have held 898 scored (article, score) pairs on disk this entire time — 9 systems × 100 tasks, articles in `drb_corpus/gpt55_board/*.jsonl`, scores in `scores/*/raw_results.jsonl`. Nobody looked. **Result: every document-shape lever collapses to ~0 under task × system fixed effects.** This falsified a lever family that Sol, Fable, and four of the five architects all depend on — *and that I was about to build myself, until I ran the FE spec.* It is the single highest-value hour in the project and it cost nothing.

## DAY 0 — EVERYTHING ELSE THAT CAN CHANGE THE PLAN. ~$11 TOTAL, ~2 DAYS, ALL IN PARALLEL, BEFORE ONE LINE OF PIPELINE IS WRITTEN.

**E1 — THE LEDGER PATCH. $0, six lines.** `deepresearch_bench_race.py` builds `llm_output_json` (25 criteria × {our raw, reference raw, the judge's written comparative analysis}) and then `final_result` keeps five floats and discards it. Add `criteria_scores`, `target_total`, `reference_total`. Free, permanent, task-agnostic, no overfit surface. Ship first regardless of everything else.

**E2 — R, AND THE ANALYTIC CEILING. $0.11 (one call, from E1).** Read `reference_total`. Max achievable = `10/(10+R)`:
```
R = 6.0 -> ceiling 0.625   R = 7.0 -> ceiling 0.588   R = 7.5 -> ceiling 0.571
```
**If R ≈ 7.5, the ceiling is 0.571, cellcog at ~0.556 already sits at 97% of the theoretical maximum, and BOTH foundation plans' release gates (Sol 0.5670, Fable 0.5672) are unreachable regardless of how good the report is.** This is the most sobering possibility in the project, nobody has considered it, and it is one judge call away.

**E3 — SCORE cellcog's TASK 72, k=5. $0.55.** `cellcog-max.jsonl` is the **only** board system with no `raw_results.jsonl`; its article is on disk in the harness's exact `{id, prompt, article}` format. **The number both foundation plans argue about for pages, and set their gates from a regression on, costs fifty-five cents to measure.** It may come back *below* bodhi's 0.5441 — in which case both plans spent their entire ceiling analysis chasing a phantom.

**E4 — THE SHAPE INTERVENTION. $2.20 (k=10 paired).** E0 is observational and has **no support at our operating point** (677w paragraphs = 99.7th percentile). So intervene: take our own artifact, hold the content and word count fixed, split paragraphs to ~100w, add 30 subsections, add a table. Score k=10 paired. **This settles by intervention what E0 can only bound by observation — and it settles it on OUR document, at OUR score, not on a champion at 0.556 where the gradient may be entirely different.**

**E5 — THE FABRICATION / QUALITY SWAP. $2.20 (k=10).** Byte-identical prose, three arms: **A** = our artifact, real citations (already banked at k=5, free). **B** = every citation replaced with a plausible *fabricated* reference. **C** = every citation replaced with a *real but low-quality non-journal* source. Same words, same structure, same argument, same 25 criteria — **the length/fluency confound is zero by construction.**
- If **B ≈ A**: the judge cannot detect fabrication. Our faithfulness contract buys **zero score** and must be justified on product-trust grounds alone. **We keep it anyway, and we say out loud that it costs us.** (Arm B is quarantined, marked, and never leaves the test directory.)
- If **C ≈ A**: *"Exclusive Citation of High-Quality Journal Articles"* is graded on FORM, and the entire journal-corpus program buys nothing.
- If **B and C both crater**: the judge-value assumption **survives**, retrieval is priced, and only then have we earned the right to build it.
**This is the experiment that answers operator FIX 6 — the load-bearing unknown — and it is the only one that isolates feature VALUE from feature VISIBILITY.**

**E6 — PER-CRITERION NOISE MATRIX. $0.55.** Re-score the 5 banked `noise_r10_*` artifacts through the patched harness. Gives the run-to-run SD of each of the 25 raw scores. **No criterion may be called a deficit until its own SD is known.** Without this, the per-criterion ledger is a noise amplifier and it recreates commits 947d2b5 / 225b323 / b3acb72 at 25× resolution.

**E7 — RUBRIC RECALL ON ALL 100 TASKS. ~$5.** Run RACE's own generators (k=3, union) on all 100 prompts; score weighted rubric-mass recall + dimension-weight L1 against `criteria.jsonl`. **This is the anti-overfit proof, it is executable before anything is built, and it is the only generality claim in this plan that is a measurement rather than an argument.**

## WHY I AM DROPPING THE SIX-ARM CHAMPION ABLATION
The k=5 two-arm MDE at SD=0.0074 is **0.0131** (0.0163 with Bonferroni across 6 arms). Ablating the *entire* journal-corpus program (w=0.081, a generous 5-raw-point swing) moves overall by **0.0113**. **The maximal ablation of the whole retrieval apparatus lands BELOW the detection floor of the instrument built to price it.** The experiment returns null for nearly every lever it exists to measure, and this repo's history says null gets read as "worthless." Properly powering it needs k≈20–34/arm — the whole budget for one contrast. **E4 and E5 buy the same knowledge, properly powered, at our own operating point.**

## THE STANDING MEASUREMENT REGIME
- **k=5 minimum. Never n=1.** Judge SD 0.0074 (rank10); note it is heteroscedastic (ctrl SD 0.0021), so 0.0074 is the conservative figure.
- **THE HEADLINE METRIC IS A 3-TASK PANEL MEAN, NOT TASK 72.** One academic, one clinical, one non-academic/advisory. A lever that lifts task 72 and does nothing on 78 and 90 **is an overfit and gets reverted.** Full 8-task panel at every checkpoint. This triples judge spend, it is the right call, and **it must be a hard CI gate rather than a convention — because under time pressure it is the first thing that will get quietly dropped, and that is exactly how we ship the 0.263 system.**
- **Every lever ships a post-cleaner MECHANISM COUNTER.** A score run is inadmissible as evidence about a lever whose counter did not move. This is Sol's best idea and it is the only defence against this repo's signature failure.
- The judge's **written comparative analysis** (not the floats) feeds Stage 1's next query round and Stage 4's revision. It is qualitative, so it is not subject to the per-criterion noise problem.
- **HARD BOUNDARY: the composer never reads `reference.jsonl`.** Reading the judge's output is one step from writing to one specific opponent. That is a code boundary, not a discipline — but it will be under pressure every time the score stalls, and I am naming it now.


## PHASING
## DAY 0 (ALREADY DONE): **E0, THE $0 FALSIFIER.** 898-article two-way fixed-effects regression. **It fired.** Document shape ≈ 0. A lever family in all six designs is dead. This is the fastest, cheapest experiment in the project and it required zero judge calls and zero new code.

## DAYS 1–2 — THE INSTRUMENT AND THE FALSIFIERS. ~$11. ALL IN PARALLEL. NO PIPELINE CODE IS WRITTEN.
Six things run at once, and **every one of them can change the plan**:
- **E1 the ledger patch** (6 lines, $0) — ships regardless of every other outcome.
- **E2 read R → the analytic ceiling** ($0.11). *If R ≈ 7.5 the ceiling is 0.571 and cellcog already sits at 97% of it — and the honest response is to change the plan, not the narrative.*
- **E3 score cellcog task 72, k=5** ($0.55). The number both plans argue about and neither measured.
- **E4 THE SHAPE INTERVENTION** (k=10 paired, $2.20). Our own artifact, content held fixed, restructured. Settles by *intervention* what E0 bounds by *observation*, at the operating point where observation has no support.
- **E5 THE FABRICATION SWAP** (k=10, $2.20). **The experiment that could prove the whole thesis wrong.** Same prose, fake refs / junk refs. Answers operator FIX 6 — does the judge PAY for scholarship, or only for its costume?
- **E6 per-criterion noise matrix** ($0.55) + **E7 rubric recall on all 100 tasks** (~$5) — the anti-overfit proof.

**HARD GO/NO-GO GATE. Nothing downstream is built until these read out.**

## DAYS 2–5 — TWO TRACKS, FULLY PARALLEL
**TRACK A — THE DERIVATION LAYER (`compile_brief.py`).** Rubric (k=3 union) → dimension weights (+0.03 insight correction) → **ANSWER SHAPE** → scope (topic/venue/recency/language) → coverage matrix → outline → length budget. Validated continuously against `criteria.jsonl` on all 100 tasks. **This is the keystone and the fix for the 0.263.**
**TRACK B — THE INTEGRITY FLOOR.** The **poisoned-card CI test that fails if `validate()` is bypassed** (it has been imported-and-never-called through two shipped "fixes" — we do not relax one gate until this is green). Adversarial suite extended: mechanism transplant, misattribution, sign inversion as MUST-REJECT; the corpus-scoped gap claim as MUST-ADMIT. Zero false admissions AND zero false rejections. **In parallel: rip the checked-in domain vocabulary out of `src/` and add the CI grep that bans domain nouns outside `brief.json`.**

## DAYS 5–8 — RETRIEVAL + EVIDENCE (rebuilt at the root), IN PARALLEL WITH THE COMPOSER
The composer does **not** wait for new retrieval — we already hold a corpus, and the composer's real job (answer shape, thesis, criterion homes) can be built and tested against it immediately. Retrieval's rebuild (topic-gate-then-citation-rank; propose-then-resolve with a published FNR; date-filtered recency; SELECT as a hard gate on the citable pool) runs alongside.

## DAY 8 — **THE FIRST REAL k=5 SCORE OF THE NEW SYSTEM, ON A 3-TASK PANEL.**
One academic (72), one clinical (78 — where we score 0.2107), one non-academic/proposal (90). **The headline number is the PANEL MEAN.** A lever that lifts 72 and not 78/90 is an overfit and gets reverted.

*(Fastest path to a real k=5 score overall: Day 1. E3, E4 and E5 all produce real k=5/k=10 numbers within 48 hours, on artifacts we already hold.)*

## DAYS 8+ — THE WHEEL, AIMED AT WHOLE-DOCUMENT QUALITY
FIX → COMPOSE (3-task panel) → INTEGRITY GATES → SCORE k=5 → **READ THE JUDGE'S OWN WRITTEN ANALYSIS** → FIX. Not one lever per turn — F3 proves no single lever can clear the kill threshold. Each turn targets **a whole-document property** (does it answer every `must_answer`? does the evidence actually bear on the question? is the thesis true and non-obvious?), with the mechanism counter proving the change fired before the score is admissible as evidence about it.


## EXPECTED
**I will give you four numbers, and only one of them is good.**

**1. ON TASK 72, THE ARTIFACT: this plan probably does NOT beat cellcog, and has a coin-flip chance against bodhi.**
From 0.4396 we need +0.117 — a ×1.60 in the judge's points, which by F3 means the weighted mean of **all 25 criteria** moving from the 4–6 "average" band into the 8–10 "excellent" band. The single heaviest criterion on the task, taken to a perfect 10, buys **+0.016**. I do not have a proven band-jump mechanism. I have a hypothesis: *answer the question that was asked, from evidence that is actually about it, and say something true and non-obvious.* I believe it, and I cannot price it.
- **P(k=5 mean > bodhi's measured 0.5441) ≈ 40–50%.**
- **P(k=5 mean > cellcog's estimated ~0.556) ≈ 25–30%.**
Both foundation plans project 0.563 and 0.572 by summing lever deltas. **F3 says that arithmetic is invalid, and E0 says a large share of those deltas are worth zero.** I will not repeat it.

**2. ON THE SYSTEM (the actual mission — an unseen question): this plan is a large, honest win, and it still does not reach SOTA on the first cycle.**
We are at **0.263**. The failures are catastrophic, not marginal: ResNet in an AI-labour corpus; a literature review shipped to a family asking about Parkinson's warning signs (0.2107). Fixing SELECT and deriving the answer shape addresses failures of that magnitude. **Honest projection: 0.35–0.45 on a first pass over the 3-task panel. P(the SYSTEM beats 0.5441 on an unseen task in cycle one) ≈ 15%.** But the trajectory matters more than the level: for the first time we would have a system whose score is a function of the prompt rather than of an engineer's afternoon.

**3. CORPUS-WIDE, ACROSS THE 100-TASK BENCHMARK: WE DO NOT BEAT 0.5578, AND I WANT THIS SAID LOUDLY. 50 OF THE 100 TASKS ARE IN CHINESE.**
I verified it by character scan of `criteria.jsonl`. cellcog's 0.5578 is a **100-task mean that includes all 50 of them**, graded by `criteria_prompt_zh.py`, against Chinese references (some as short as 297 words). **Nothing in this project — not one plan, not one of the six designs, not one line of code — composes in Chinese, and nobody has mentioned it.** **P(beat 0.5578 corpus-wide) < 10%.** The only defensible corpus-wide claim available to us is on the **50 English tasks**, and every number we report must be scoped that way or it is a units error of exactly the kind that has already burned this project once.

**4. THE CEILING MAY ALREADY BE NEARLY CLOSED, AND WE ARE ONE JUDGE CALL FROM KNOWING.**
Max achievable = `10/(10+R)`. If the reference scores R ≈ 7.5, the ceiling is **0.571** — cellcog at ~0.556 would sit at 97% of the theoretical maximum, and both foundation plans' gates (0.5670, 0.5672) would be **unreachable no matter how good the report is.** That is E2. It costs eleven cents. **If it is true, the honest response is to change the plan, not the narrative.**

**WHAT I AM CONFIDENT ABOUT:** this plan is the first one that builds a *system* instead of polishing an *artifact*; its generality is a measurement (rubric recall against 100 tasks of ground truth) rather than an argument; it retires the biggest lie in our codebase (a safety gate that has never fired while deleting 93% of the #1 system's prose); and its first experiment cost zero dollars and already killed a lever family that every other plan on this table depends on.


## KILL_RULES
**DECLARED BEFORE THE FIRST COMPOSE. EVERY ONE OF THESE WOULD ACTUALLY STOP US.**

**K0 — THE INSTRUMENT GATE (Day 2).** If **E4 (shape intervention) AND E5 (fabrication swap) both come back null** — restructuring buys nothing, and the judge cannot tell real citations from fabricated ones — then **we do not know what the judge grades, and no plan on this table deserves funding.** STOP. Find out what it grades before building anything. This is the single most important gate and it fires in 48 hours.

**K1 — THE CEILING GATE (Day 1, $0.11).** If `reference_total` comes back at R ≥ 7.5, the analytic ceiling is ≤ 0.571 and cellcog sits at ~97% of the theoretical maximum. **Then Sol's 0.5670 and Fable's 0.5672 are unreachable by construction, and we re-target honestly rather than re-narrate.** The plan changes; the story does not get rewritten.

**K2 — THE KEYSTONE GATE (Day 2).** If the compiler's weighted rubric-mass recall against the 100-task ground truth is **< 80%**, the derivation layer is the sand under the whole edifice. Fall back to the static rubric at `score_prompt_en.py:104-194` and **downgrade the generality claim in writing** to "we derive scope and answer-shape, not the full rubric." The failure mode here is silent and seductive — a plausible-looking wrong rubric would send retrieval, composition and the wheel confidently in the wrong direction.

**K3 — THE SENSOR GATE (Day 1, $0.55).** If the per-criterion noise matrix shows per-criterion SD ≥ the deficits we intend to chase, **the deficit map is a noise map and we do not steer by it.** We steer by the aggregate and by the judge's written analysis. No criterion is called a deficit until its own SD is known — skipping this is precisely how commits 947d2b5, 225b323 and b3acb72 happened.

**K4 — THE GENERALITY GATE (every turn, non-negotiable).** The headline metric is the **3-task panel mean**, never task 72 alone. **A lever that lifts task 72 and moves nothing on the clinical and non-academic tasks is an overfit and is REVERTED, not tweaked.** This is a hard CI gate, not a convention, because our system already scores 0.263 while our artifact scores 0.4396 and that is exactly the failure this gate exists to prevent.

**K5 — THE MECHANISM GATE (every lever).** Every lever ships a post-cleaner mechanism counter. **A score run is INADMISSIBLE as evidence about a lever whose counter did not move.** This repo's entire commit history is a graveyard of metrics that moved while the mechanism never fired.

**K6 — THE INTEGRITY FLOOR (any time, absolute).**
- **`validate()` must be provably on the critical path** — demonstrated by a poisoned-card CI test that FAILS when the gate is bypassed. It has been imported-and-never-called through two shipped "fixes." **No faithfulness rule is relaxed until that test is green.** We are opening a door; the lock gets installed first.
- The adversarial suite must be green with **zero false admissions AND zero false rejections**, including the three new attacks (mechanism transplant, misattribution, sign inversion) and the corpus-scoped gap claim as a MUST-ADMIT case.
- **ONE fabricated number, entity, study, or attribution on a shipped page BURNS THE ARTIFACT REGARDLESS OF SCORE.** A 0.60 obtained by fabricating is a 0.00. This holds even if E5 proves the judge cannot detect it — *especially* then.
- The composer never reads `reference.jsonl`. Code boundary, enforced in CI.

**K7 — THE RUN KILL.** If two consecutive wheel turns gain < +0.0094 on the **panel mean** while the panel sits below target, **STOP and report MISSED** with the per-dimension gaps and the named closers. No re-targeting, no fallback success state, no "we beat every measured score" consolation sentence. **A plan that ships with a fallback hits the fallback.**

**K8 — THE HONESTY KILL.** Any claim comparing us to cellcog's 0.5578 must be scoped to the **50 English tasks** or it is a units error. Any corpus-wide claim that silently includes the 50 Chinese tasks we cannot compose for is retracted on sight.


## WHAT IT DROPS

- **ALL DOCUMENT-SHAPE LEVERS AS SCORED LEVERS: Sol's 13,500-16,500 word target (+booked value), Fable's 15,000-16,000, Sol's readability lever (+0.021, 'the highest-confidence move in the whole plan'), Fable's 'readability is fully mechanical, attack to 0.54', Fable's 'SCALE ITSELF' finding, and the composer architect's 'only evidenced length x density moves all 25 criteria'.**
  - MEASURED on 898 real (article, score) pairs already on disk, $0, zero judge calls. Within-task the correlations are seductive (H3 r=+0.519 with score, +0.538 with INSIGHT). Under two-way task x system fixed effects: section count beta = +0.00000, log-words beta = +0.0069/SD -- BELOW the k=5 resolvable effect of +0.0094. The entire correlation was system identity. Top systems span 2,035 (dalpha, 0.5309) to 6,259 (lunon, 0.5347) median words -- a 3x length range with a 0.004 score spread. WE STILL DO THE COSMETICS (one afternoon, they are free) BUT WE BOOK ZERO AND NEVER CITE THEM AS PROGRESS.

- **OPTIMISING THE TASK-72 ARTIFACT AS THE PRIMARY OBJECTIVE (every plan on the table, including all six designs).**
  - Our SYSTEM scores 0.263 across five real tasks (polaris_vm_t72/75/76/78/90 = .2530/.2839/.2646/.2107/.3026). Our hand-iterated task-72 ARTIFACT scores 0.4396. The hand-tuning gap (0.187) is LARGER than the gap to bodhi (0.105). The mission is 'beat SOTA on ANY question.' On any question we score 0.263. WHEEL_PROGRESS.md:411 already flagged this and nobody built on it.

- **The 'keep a lever iff paired overall delta >= +0.0094' kill rule (BOTH foundation plans), and one-lever-at-a-time.**
  - overall = T/(T+R) demands the weighted MEAN of all 25 criteria move from ~5.5/10 ('average, basically meets') to ~8.8/10 ('excellent, exceeds'). Task 72's SINGLE HEAVIEST criterion (w=0.080), taken from 5.5 to a perfect 10, buys +0.016 against a 0.117 gap. No subset of criteria closes it. The two plans mandate one-lever-at-a-time AND a kill rule that no single lever can clear -- they would have killed every good lever they built.

- **The six-arm champion ablation (composer architect's centrepiece).**
  - k=5 two-arm MDE is 0.0131 (0.0163 with Bonferroni across 6 arms). Ablating the ENTIRE journal-corpus program moves overall by at most 0.0113. The maximal ablation lands BELOW the detection floor of the instrument built to measure it. It returns null for nearly every lever and this repo reads null as 'worthless.' Replaced by E4 (shape intervention) and E5 (fabrication swap), both properly powered at k=10, both at OUR operating point rather than the champion's.

- **VERDICT_VOCAB (synthesis_contract.py:71/:214, 'no_verdict_vocabulary (this is a vibe, not an adjudication)').**
  - MEASURED by running the real gate: it alone deletes 340 of cellcog's 368 reviewer-voice sentences. Total contract deletion: 341/368 = 93% of the #1 system's own prose. It is a 17-item hardcoded English idiom list. It is not a faithfulness gate, it is a style gate calibrated against nothing, and it is the single largest cost in our codebase.

- **The UNIVERSAL regex (synthesis_contract.py:87) and the FORECAST regex (:84).**
  - UNIVERSAL bans the word 'none' -- making COVERAGE_GAP, an operation the contract itself DEFINES at line 67, permanently unpassable, and rejecting the operator's own FIX-5 prescribed sentence ('Within the 137 journal articles retrieved for this review, NONE measures X'). FORECAST bans the word 'will' -- making the insight rubric's own criterion 'Value and Foresight in Delineating Implications and Future Research Agendas' (w=0.048) literally unwritable. Both verified by execution. We built a gate that deletes the rubric.

- **Rule 10, lexical premise-anchoring (synthesis_contract.py:228-230), and the domain-specific innards of the safety gate (SAFE_CAPS contains 'AI'/'Artificial'; CONTRASTS_LEVEL hardcodes level in {task, worker, firm, region, economy}).**
  - Rule 10 demands >=2 shared content-lemmas with the premises -- it punishes abstraction, which is exactly what INSIGHT (the heaviest dimension, mean weight 0.352) pays for. And the gate's own vocabulary is overfit to AI-and-labour, so it cannot even be EVALUATED on the clinical question we use to argue generality.

- **entailment_judge.py:588's NEUTRAL delete-clause AS APPLIED TO THE SYNTHESIS LANE ('the SENTENCE introduces a fact, entity, mechanism, or specificity NOT present in the SPAN').**
  - It bans every cross-source inference by construction, on the heaviest-weighted dimension on the benchmark. It STAYS, unchanged, in the EVIDENCE lane. It is REPLACED in the synthesis lane by a scoped entailment call against the sentence's own cited premises -- NOT by nothing. Deleting it without that replacement admits mechanism transplant, misattribution and sign inversion, all of which are false relations over true particulars.

- **Rank-by-citation-count as a PRIMARY retrieval sort key (Sol's log(citations); Fable's citation-percentile x venue tier).**
  - MEASURED: Crossref sort=is-referenced-by-count returns Faster R-CNN (33,962 cites) for an AI-and-labour query and SHELX crystallography (79,867 cites) for a 2008-crisis query. Citation-sort is TOPIC-BLIND. This is the deterministic mechanism that put ResNet, the BMJ PRISMA checklist and Cognitive Psychology 1974 into our corpus. Citations may rank only WITHIN a relevance-gated pool.

- **Sol's 15 hand-named anchor papers, Fable's 5, Sol's 8x10 coverage matrix, Fable's 9x6, the 10-section OUTLINE at cellcog_composer.py:220, the topic regex, 'recency-bonus for >=2023', and 'insight is 0.32'.**
  - Operator FIX 4. Verified: insight's weight across the 100 tasks ranges 0.11-0.42 (mean 0.352); instruction_following 0.13-0.35 (median 0.20, so task 72's 0.25 is atypical); readability up to 0.25. And the overfit is not just in the plans -- _DOMAIN_PHRASES (119 AI-labour phrases) is CHECKED INTO src/polaris_graph/generator/summary_table.py:270, with domain vocabulary found in 10+ more live source files.

- **Sol's blanket journal-only corpus admission, and 'recency-bonus for >=2023' as a constant.**
  - Both are read off task 72's prompt text and baked into the engine. Journal-only would delete the FCIC Report from a 2008-crisis review and conference readouts from a myeloma review. A recency bonus is ACTIVELY WRONG on any historical question -- it would promote 2024 commentary over primary 2008-2012 evidence. Venue class and recency window are DERIVED scope parameters.

- **Sol's blocking GATE 0 (forward-citation preflight), which he prices at a 35% chance of sinking the entire plan.**
  - Retired by operator FIX 1: date-filtered Crossref (from-pub-date) returns 344,623 journal articles 2024-2026 today. Forward traversal (OpenCitations COCI, verified live) becomes a BONUS lane, not a single point of failure. Also delete the dead Semantic Scholar fallbacks at deep_fetch.py:78-88 and all OpenAlex list/filter endpoints -- they 404/429 and silently inflate the perceived fetch budget.

- **THE 4IR ORGANISING SPINE (Sol, priced at ~11.5% of score; also Fable's composer item 8).**
  - Fable's own decode refutes it verbatim: cellcog compares AI to prior industrial revolutions in ONE sentence, never mentions steam or electrification, and explicitly demotes 4IR to 'a periodization it declines to adopt uncritically.' The system that DOES build the four-revolution comparison table is WhaleCloud, at 0.5396. The 4IR criteria are real and heavy; the prescribed CONTENT is wrong. Fixed generally by passing every derived criterion's text VERBATIM to the section writer, and by the rule: critique-and-subordinate the frame the prompt names.

- **Sol's Format-D attribution ('Writing in the American Economic Review in 2020, Acemoglu and Restrepo find...'), and the '>=110 attributions / 12-16 tags / 10-12 named syntheses' count targets.**
  - Format D is a contorted variant nobody on the board uses; Fable measured that 160 of cellcog's 177 year-parens are NARRATIVE form ('Acemoglu and Restrepo's (2020)') with the author already in prose, and those survive the cleaner. And in-prose attribution's within-task correlation with score is only r=+0.129 -- the WEAKEST feature I measured, before fixed effects erase it. The entire cleaner-survival investigation -- the brief's crown jewel -- is aimed at a lever worth ~0.13 correlation. Real, but small. Copied count targets are fine as sanity floors and fatal as targets.

- **The hardcoded abstract at cellcog_composer.py:400-414; the 240 [n] markers in prose; the 15-sources-per-section floor; the meta-commentary opener.**
  - The abstract asserts 'draws exclusively on peer-reviewed, English-language journal articles identified through citation-graph expansion' regardless of what the corpus actually contains -- a FABRICATED COMPLIANCE CLAIM aimed squarely at the instruction-following grader, and the most dishonest line we ship. It dies first. The 15-source floor is unsatisfiable and silently padded (it routed 104 off-topic medical papers into the Introduction). The opener says 'the question above' when there is no question above, in the position the judge reads most carefully. (Note: [n] markers actually correlate POSITIVELY with score, r=+0.226 -- they are a symptom of citation density, not a cause of loss. Delete them for prose quality, not because they are costing points.)

- **BOTH foundation plans' release gates (Sol 0.5670, Fable 0.5672) and their per-dimension expected-total arithmetic.**
  - Both require T/R = 1.31 -- higher than any system has posted on ANY dimension of this task -- and both are stacked on a REGRESSION ESTIMATE of cellcog's task-72 score whose residual SD (0.0094) equals the effect being resolved. cellcog's article is on disk in the harness's exact input format and scoring it k=5 costs $0.55. Two plans disagreeing by 0.0002 about an unmeasured number is the argument for measuring it.


## ITS OWN HONEST UNKNOWNS

- I DO NOT KNOW WHAT PRODUCES A BAND JUMP, AND NEITHER DOES ANYONE ELSE ON THIS TABLE. F3 proves we need the weighted mean of ALL 25 criteria to move from ~5.5/10 to ~8.8/10 in a single comparative call. Every plan, including mine, is a sum of increments. Increments do not obviously produce band jumps. My answer -- 'answer the actual question, with real evidence, and say something true' -- is a hypothesis, not a priced lever. It is the thing that would make us miss.

- E0 IS OBSERVATIONAL AND HAS NO SUPPORT AT OUR OPERATING POINT. Our 677-word median paragraph is the 99.7th percentile of 898 real articles (only 3 of 898 exceed 400w). The fixed-effects null on paragraph length is estimated over a range (p5-p95 = 0-125 words) containing no point anywhere near us. I cannot claim paragraph size matters and I cannot claim it does not. E4 settles it by intervention; until then I fix it for free and book zero.

- TWO-WAY FIXED EFFECTS MAY BE A BAD CONTROL. If a system's quality IS partly its ability to structure a document, then removing the system mean removes the very thing I am trying to measure. I think the null is real (sections should still correlate positively under FE if they mattered -- a system writes more sections when it has more to say -- and beta is exactly 0.00000), but this is the strongest objection to my central finding and I cannot fully rebut it with observational data.

- THE PER-CRITERION LEDGER MAY BE A NOISE MAP. The judge scores all 25 criteria in ONE call, so they are halo-correlated. If per-criterion SD is large relative to the deficits, steering by the deficit map is steering by noise -- and it would look exactly like progress. E6 measures it first. If it fails I need a different sensor and I do not currently have one.

- THE COMPILER'S ~5% RUBRIC MISS CONCENTRATES IN INSIGHT -- the heaviest dimension (mean weight 0.352). The k=3 union demonstrably recovers the misses on task 72, but that was measured on ONE task. If the union does not close the gap in other domains, we are silently zeroing ~5% of the score on exactly the dimension we most need.

- PROPOSE-THEN-RESOLVE INHERITS THE MODEL'S TRAINING CUTOFF AND ITS PRESTIGE/LANGUAGE BIASES. It cannot propose a paper it has never seen, and it will preferentially propose the anglophone high-prestige canon -- carrying the model's own field biases into a document that claims to survey the literature. Date-filtered search fixes the recency half. NOTHING in this design fixes the prestige/language half, and I will not pretend otherwise.

- 50 OF THE 100 BENCHMARK TASKS ARE CHINESE AND NOTHING WE HAVE EVER BUILT COMPOSES IN CHINESE. No plan and none of the six designs mentions this. Every corpus-wide comparison anyone has made in this project -- including cellcog's 0.5578 -- silently includes them. This is the third units error waiting to happen.

- REFERENTIAL CLOSURE GUARANTEES INTEGRITY, NOT QUALITY. It cannot stop a FALSE RELATION among TRUE PARTICULARS. The synthesis-entailment gate catches the mechanical cases (transplant, sign inversion, misattribution), but there is no deterministic gate for 'is this argument any good.' A judge could rate our reviewer-voice prose as confident waffle and score it BELOW cellcog's. I have no gate for that and I am not going to invent one.

- IF E5 SHOWS THE JUDGE CANNOT DETECT FABRICATION, we will have measured precisely what our integrity costs us in score -- and someone will be tempted to spend it, at 3am, 0.008 short of the gate. That is a governance risk, not a technical one, and it is the one I trust least. The hard abort has to hold.

- I HAVE NOT COSTED THE 3-TASK PANEL AT SCALE. Every lever now needs 3 composes plus k=5 judging. Composing is the real cost, not scoring. Under time pressure the panel is the first thing that will get quietly relaxed -- and that is exactly how we ship the 0.263 system while believing we shipped the 0.44 one.
