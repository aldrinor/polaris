# OPERATOR FIXES — corrections neither Sol nor Fable found. These are NOT optional.
# Every one of these came from the operator, and every one was right. They are the reason the two plans
# above are insufficient as written.

## FIX 1 — **THE RECENCY FIX. THIS DISSOLVES THE BIGGEST RISK IN BOTH PLANS.**
Both plans bet 2024-2026 coverage on FORWARD CITATION TRAVERSAL. Sol rates its failure a **35% chance of
sinking the entire plan** ("a 2026 review of AI and the labor market with no generative-AI-era journal
evidence is structurally stale"). Fable verified our corpus has **ZERO papers after 2023**.
Both are correct that forward traversal is DEAD on this box (OpenAlex 429s our IP; Semantic Scholar 404s).

**NEITHER OF THEM THOUGHT TO JUST SEARCH BY DATE.**

MEASURED, WORKING, TODAY:
```
crossref /works?query.bibliographic=...&filter=type:journal-article,from-pub-date:2024-01-01
  -> 344,623 journal articles, 2024-2026
  -> e.g. Babina & Fedyk (2024), Journal of Financial Economics, "Artificial intelligence, firm growth..."
```
**We do not need forward traversal to reach recent papers. We can ASK FOR THEM BY DATE.**
Forward traversal becomes a BONUS, not a dependency. Sol's 35% risk is retired.

**BUT — AND THIS IS THE REAL LESSON:** that same query also returns scGPT, convolutional neural networks,
vision-language models and medical image segmentation. **Date-filtering gets us RECENT papers; it does not get
us RELEVANT ones.** Which means:

## FIX 2 — **SELECT IS THE BROKEN STAGE, NOT RETRIEVAL.**
Our corpus: 997 rows, 919 URLs, 206 DOIs — and after enrichment only **17 of 120 journal works are ON-TOPIC**.
It contains **ResNet, the BMJ PRISMA checklist, and a 1974 Cognitive Psychology paper on reading automaticity.**
Prestigious. Peer-reviewed. Utterly irrelevant.

**RETRIEVAL WAS NEVER SHALLOW. IT WAS AIMED WRONG.** More search with the same broken SELECT just yields more
junk — and now, *recent* junk. SELECT must be an **LLM relevance judge against the actual research question**,
never a regex, never a venue-prestige score. (`topic_relevance_gate` already exists in the codebase.)
Prestige is not relevance. Tier is a WEIGHT, never a FILTER.

## FIX 3 — **SCOPE MUST BE DERIVED FROM THE PROMPT, AND ENFORCED AS A GATE.**
Not a weighting bonus (which is all Sol has: "recency-bonus for >=2023"). A **hard admission gate**, derived at
runtime from the question itself:
  - **topic** (what is this actually about?)
  - **recency window** (a 2026 AI question needs 2024+; a French-Revolution question does not)
  - **venue class** ("only cites high-quality journal articles" => journals only; other prompts differ)
  - **language**
Out-of-scope evidence NEVER enters the citable corpus. WEIGHT then ranks *within* scope.
**This is what makes it a system rather than a hack: the same code answers a clinical question, a financial one,
a historical one — because the scope is derived, not typed in by an engineer.**

## FIX 4 — **WE ARE OVERFITTING, AND BOTH PLANS DO IT.**
Sol and Fable both hardcode, to AI-and-labour:
  - 15 hand-named anchor papers (Autor-Levy-Murnane, Frey & Osborne, Acemoglu-Restrepo...)
  - a 10-section outline
  - an 8-dimension x 10-industry coverage matrix, read off task 72's rubric BY HAND
  - a topic regex
**That is not a research system. It is an expensive way to answer one question.** The benchmark has 100 tasks;
a system that can only do one of them is a demo.

**EVERY ONE OF THOSE CONSTANTS MUST BE DERIVED FROM THE PROMPT AT RUNTIME:**
  - **The coverage matrix**: RACE's OWN JUDGE GENERATES ITS 25 GRADING CRITERIA FROM THE TASK PROMPT
    (`third_party/deep_research_bench/prompt/criteria_prompt_en.py` — the generator is handed only the task text).
    **We can generate our coverage matrix the same way, from the same prompt.** This is the keystone insight.
  - **The anchors**: do not hand-name them. Run a first search, take the most-cited on-topic works, use THOSE as
    the seeds for citation-graph expansion. The method finds the canon for ANY field.
    (Citation-graph expansion is essential and general: keyword search PROVABLY cannot find Autor-Levy-Murnane,
    whose title contains neither "AI" nor "labor market" — but it is the field's most-cited paper.)
  - **The outline**: derived from the matrix, not written by an engineer.
  - **The stopping condition**: the matrix is full, not "100 papers".

## FIX 5 — **FAITHFULNESS: THE OPERATOR HAS AUTHORISED RELAXING IT. GET THE LINE RIGHT.**
Our gate blocks BOTH fabrication AND legitimate scholarly inference. The #1 system asserts original mechanisms
CONSTANTLY (71% of its sentences carry no citation) and stays honest by **LABELLING them, not by refusing to think**.

- **FABRICATION = putting words in a source's mouth.** Inventing a number, a study, a finding, an attribution.
  **This is fraud and must remain impossible. A 0.60 obtained by fabricating is a 0.00.**
- **SCHOLARSHIP = the reviewer's own reasoning, marked as such.** "We propose, as analytical synthesis, that..."
  is not fabrication. It is what every literature review in existence does.
- **The moat is NOT "every sentence must be span-grounded". The moat is "no sentence may put words in a source's
  mouth."** Those are different rules and we have been enforcing the wrong one.

**FABLE'S REFINEMENTS ON THIS ARE CORRECT AND MUST BE KEPT (they beat the operator's first formulation):**
  - The mechanism pool is **the union of the SENTENCE'S OWN CITED CARDS**, not the whole corpus. A corpus-wide
    pool degenerates into "does the sentence contain a word the field uses" — and **flips our own adversarial
    test ATTACK #1 from REJECT to PASS.** (bodhi never needed the widening: its bridge sentence already cites
    the mechanism's paper.)
  - **Hedge + tag alone is COSTUME, never a license.** An analytical synthesis must be a CONDITIONAL over >=2
    ADMITTED premises, carrying premise_ids, so the no-new-number and no-new-entity gates STILL RUN.
  - **Gap declarations must be CORPUS-SCOPED.** cellcog writes "No peer-reviewed study has yet measured X" —
    which is a **false universal** (you cannot know that). Write instead: "Within the 137 journal articles
    retrieved for this review, none measures X" — **true by construction, same scoring payoff.**

## FIX 6 — **THE LOAD-BEARING UNKNOWN (Fable's own words, and it is the honest crux):**
> "Everything measured so far is about what SURVIVES the cleaner — feature **VISIBILITY** — not about what the
> judge PAYS for those features — feature **VALUE**. We have never composed one full report in this architecture
> and scored it k=5. The visibility-to-value conversion rate is the plan's load-bearing unknown."

**Design the CHEAPEST experiment that measures visibility-to-value FIRST, before building everything.**
If the judge does not pay for visible scholarship at the magnitude the arithmetic requires, the whole plan is
wrong, and we should learn that in one compose rather than three weeks.

## FIX 7 — THREE REAL BUGS IN THE CODE WE ALREADY WROTE (found by Sol, all on the critical path)
1. `scripts/synthesis_contract.py` `validate()` is **imported at `cellcog_composer.py:49` and NEVER CALLED.**
   The safety contract is not on the critical path. The only thing between LLM prose and the page is a regex.
   **This is the exact failure pattern that wasted a whole night: a mechanism that looks armed and never fires.**
2. `cellcog_composer.py:167` copies the `mechanisms` field **straight from LLM output with no span check**, while
   `claim` and `span` next to it ARE checked. **A hallucinated mechanism string becomes a global citation
   license — two-hop laundering.** Every mechanism must carry its own verbatim span.
3. `journal_corpus_fetch.py` accepted a **548-word Oxford landing page** ("CONTACT Name Email... We welcome
   feedback") as FULL TEXT for Frey & Osborne. The full-text detector is a lying measurement. Real quotable
   full text is ~10 papers, not 12.
