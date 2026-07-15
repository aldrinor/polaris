# Verdict

POLARIS cannot reach the cellcog profile by rewriting the banked report. It needs:

1. A journal-only, canonical evidence corpus.
2. Source-level evidence cards rather than isolated spans.
3. A dual-lane composer that separates factual claims from premise-linked synthesis.
4. Narrative author/journal attribution that survives cleaning.
5. An outline-first renderer producing roughly 34 claim-first H3s and 12–15k cleaned body words.

My estimated outcome for the complete redesign is **0.53–0.56**, centered near **0.55**. Bodhi parity is credible; 0.5578 is an aggressive but defensible target. Attribution alone will not get close.

## Corrections to the brief

Several premises do not survive inspection.

- **POLARIS does not currently cite 97 journal articles.** It has 105 numbered bibliography rows and approximately 97 canonical sources after duplicates, but many are working papers, institutional reports, news articles, blogs, vendor pages, and mirrors. Examples include WEF, MIT Sloan, NBER, IZA, arXiv, OECD, Harvard Gazette, Substack, Toptal, IMF working papers, Goldman Sachs, vendor statistics, and J.P. Morgan. The report itself says only 6% of its material is T1 primary research. Retrieval depth is therefore not yet journal-literature depth.

- **The cheap attribution transform is conditional.** Narratively attributing the current corpus would expose sources such as WEF, Goldman Sachs, Toptal, and Substack more clearly, potentially lowering “Exclusive Citation of High-Quality Journal Articles.” Corpus filtering must precede—or at least gate—attribution.

- **RACE cleaning is model-driven, not deterministic.** The cleaner sends each article or chunk to an LLM with instructions to remove citation marks, links, bibliographies, and footnotes. The observed local result may indeed contain zero markers, but that is an empirical output, not a regex guarantee. [The cleaner prompt says exactly this](https://github.com/Ayanami0730/deep_research_bench/blob/main/prompt/clean_prompt.py).

- **“The judge sees no sources at all” is too strong.** It loses the numbered markers and reference list, but retains existing narrative references. POLARIS already names Acemoglu, Restrepo, Autor, Frey, Osborne, Felten, Raj, Seamans, Brynjolfsson, and several others. It also names at least *Journal of Economic Perspectives*, *Strategic Management Journal*, and *Science*. The sourcing signal is very weak, not literally zero.

- **The table’s “10 authors / 1 journal” labels are not reproducible literally.** The raw POLARIS text contains more than twenty distinct author surnames and at least three journal venues. Those numbers may come from a narrower attribution-pattern regex, but then the metric needs that definition.

- **The marker counts are reconcilable:** approximately 240 body occurrences plus 105 bibliography labels gives the reported 345 items entering cleaning.

- **“No credit for being a better 7” is false as written.** Scores are continuous. A 7.8 beats a 7.0. Crossing 8 may be especially salient to the judge, but it is not a hard threshold. The bands are guidance, not quantization. [The scoring prompt explicitly uses continuous 0–10 scores](https://github.com/Ayanami0730/deep_research_bench/blob/main/prompt/score_prompt_en.py).

- **Cellcog’s synthesis is not entirely fact-free.** “The task-based framework subsumes…” and “the earlier frameworks did not anticipate…” are theoretical assertions. They can be faithful when derived from already grounded premises, but they are more than stylistic glue. The safe target is not “unverified prose with no numbers”; it is **typed, premise-linked adjudication**.

- Cellcog has exactly **31 H3 headings** by direct heading enumeration. POLARIS has zero. Cellcog’s bibliography contains about 104 rows; “98 distinct sources” appears to mean distinct body-cited works, not bibliography entries.

The grader facts do check out: task 72 has 25 criteria—6 comprehensiveness, 5 insight, 7 instruction-following, and 7 readability—with weights 0.29/0.32/0.25/0.14. The complete task-specific rubric is in [criteria.jsonl](https://github.com/Ayanami0730/deep_research_bench/blob/main/data/criteria_data/criteria.jsonl). Both articles and all criteria are presented to one comparative scoring call, and the final calculation is target/(target+reference), as implemented in [deepresearch_bench_race.py](https://github.com/Ayanami0730/deep_research_bench/blob/main/deepresearch_bench_race.py).

## The required architecture

```text
retrieval
  ↓
canonical journal-only corpus
  ↓
verified source cards: study + setting + method + result + limitation
  ↓
rubric/coverage matrix
  ↓
34 claim-first H3 plans, each with premises and an adjudication question
  ↓
dual-lane generation
  ├─ EVIDENCE sentence → existing single/multi-span provenance gate
  └─ SYNTHESIS sentence → new premise-operation contract
  ↓
75-word paragraph renderer + narrative attribution
  ↓
cleaner-survival audit
  ↓
report + machine-readable sentence ledger
```

### Code placement

I would make these changes:

- `provenance_generator.py`, at the existing `verify_sentence_provenance` definition reported near line 2098:
  - Keep the current zero-failure behavior for `sentence_kind="evidence"`.
  - Dispatch `sentence_kind="synthesis"` to a separate validator.
  - Update every caller of `verify_sentence_provenance`; do not silently infer the sentence kind.

- `entailment_judge.py`, around the NEUTRAL rule reported near line 588:
  - **Do not weaken this rule.**
  - Its refusal of unsupported facts, entities, and mechanisms is correct for evidence sentences.
  - A global relaxation would sell the faithfulness moat.

- Add `evidence_cards.py:1`:
  - Canonical DOI/source deduplication.
  - Journal/language/peer-review verification.
  - Source-card construction and coverage-matrix generation.

- Add `synthesis_contract.py:1`:
  - Typed synthesis operations, premise validation, entity/number checks, and an adversarial test suite.

- Add `narrative_attribution.py:1`:
  - Deterministic rendering from validated `authors`, `year`, and `venue`.
  - First-mention and later-mention policies.
  - Cleaner-survival auditing.

- Add `cellcog_composer.py:1`:
  - Outline-first section planning, paragraph budgeting, source allocation, and typed sentence generation.
  - This replaces the current report-to-report composition path; it should not post-edit `rank10_sections_compose/report.md`.

Because the managed shell failed before command execution, I could not independently verify the two private-code line numbers supplied in the brief or locate the current compose-prompt line. I therefore use exact symbol anchors and new-file line 1 rather than inventing line numbers. Locate integration sites with:

```bash
rg -n "def verify_sentence_provenance|verify_sentence_provenance\\(" /home/polaris/polaris_project
rg -n "len\\(failures\\).*0|NEUTRAL" /home/polaris/polaris_project
rg -n "This report synthesizes|Cross-Study Synthesis|Additional Corroborated" /home/polaris/polaris_project
```

## Lever 1: Repair the corpus before composing

The existing source count is a false strength. Build a **90–105 source corpus of canonical, verified English journal articles**, not 97 heterogeneous web records.

Positive admission should require:

- Canonical DOI or publisher record.
- Publication type verified as journal article.
- English-language title/full text or explicit language metadata.
- Named journal and authors.
- Peer-review status or reputable journal/index evidence.
- At least one usable full-context evidence span.
- No canonical duplicate by DOI/title.

Reject reports, working papers, proceedings, books, news, explainers, consultancy forecasts, blogs, repositories, mirrors, and vendor pages from the evidence used in the review. They may be stored as excluded context, but never cited or used as factual premises.

Each admitted article needs a card such as:

```json
{
  "source_id": "...",
  "authors": ["..."],
  "year": 2025,
  "journal": "...",
  "doi": "...",
  "study_type": "field experiment",
  "level": "worker",
  "industry": "customer service",
  "geography": "United States",
  "horizon": "...",
  "outcomes": ["productivity", "attrition"],
  "verified_claim_ids": ["..."],
  "limitations": ["..."],
  "metadata_receipts": ["..."]
}
```

“Study type,” “level,” “outcomes,” and “limitations” must themselves be span-supported.

| Rubric moved | Expected raw movement |
|---|---:|
| “Depth and Representativeness of Literature Synthesized” | +0.6 to +1.2 |
| “Exclusive Citation of ‘High-Quality Journal Articles’” | +1.5 to +2.5 |
| “Exclusive Citation of ‘English-Language’ Journal Articles” | +0.2 to +0.5 |
| “Critical Synthesis and Nuanced Evaluation…” | +0.3 to +0.7 |

Failure mode: treating the existing tier label as proof of journal quality. The current data already labels some explainer pages implausibly highly.

Cheap pre-compose test: produce a corpus audit CSV. Release requires:

- 100% admitted sources with positive journal and English evidence.
- Zero nonjournal types.
- Zero DOI/title duplicates.
- At least 80 sources with usable method/result/limitation cards.
- Coverage of at least six industries and all six required restructuring outcomes.

## Lever 2: Narrative attribution that survives RACE

Do not simply replace `[1]` with `(Acemoglu & Restrepo, 2019)`. The cleaner is instructed to remove complex citation formats too. Use grammatical attribution:

> In their 2019 *Journal of Economic Perspectives* article, Acemoglu and Restrepo distinguish displacement from reinstatement.

Rules:

- First use: year + journal + all surnames up to four.
- Later use: surnames + year, unless the cleaner test shows the year is removed.
- Multiple sources: integrate them as actors in a comparison, not as a parenthetical block.
- Preserve `[n]` markers and the bibliography for provenance/FACT; narrative attribution is an additional RACE-surviving channel.
- Only attribute sources admitted by the journal firewall.
- Every surname, year, and venue must match the canonical metadata record.
- Missing author or venue means “do not render,” not “guess.”

| Rubric moved | Expected raw movement |
|---|---:|
| “Depth and Representativeness of Literature Synthesized” | +0.3 to +0.7 |
| “Exclusive Citation of ‘High-Quality Journal Articles’” | +0.5 to +1.0 |
| “P1: Clarity and Synthesis in Presenting Sourced Information” | +0.3 to +0.6 |
| “L1: Language Clarity, Precision, and Academic Tone” | +0.2 to +0.5 |

Failure mode: repetitive “X found…” prose that remains a catalogue, or attribution that exposes bad sources.

Cheap test: make a 20-sentence fixture with five forms—numbered markers, parenthetical author-year, possessive attribution, “writing in Journal” attribution, and lexical year/journal attribution. Clean it five times with the production cleaner. Choose the form with:

- 100% author and journal survival.
- No changed factual text.
- No orphaned grammatical fragments.

Then apply journal-only narrative attribution to the banked report and score the exact before/after pair five times. Require at least **+0.0094 overall** before treating it as a scored lever.

## Lever 3: Add a premise-linked synthesis lane

The central change is not “allow NEUTRAL sentences.” It is to give synthesis a different proof obligation.

Every generated sentence must declare one kind:

### Evidence

A factual statement about a study, entity, number, mechanism, finding, or method. It continues through the current provenance gate and ships only with zero failures.

### Synthesis

A relationship over already admitted premises. It must declare:

```json
{
  "sentence_kind": "synthesis",
  "operation": "CONTRAST_LEVEL",
  "premise_ids": ["claim_17", "claim_42"],
  "draft": "Firm-level expansion can coexist with worker-level losses because the two estimates observe different adjustment margins."
}
```

Allowed operations:

- `CONJUNCTION`
- `COMPARE_DIRECTION`
- `CONTRAST_LEVEL`
- `CONTRAST_HORIZON`
- `BOUNDARY_CONDITION`
- `RANK_EVIDENCE`
- `CONSENSUS_OR_DISAGREEMENT`
- `COVERAGE_GAP`
- `CONDITIONAL_IMPLICATION`

Validation rules:

1. Every named entity and numeral must occur in a premise or canonical metadata.
2. Causal language is forbidden unless a premise contains the mechanism and supports causal interpretation.
3. Evidence ranking may use only declared fields such as design, level, horizon, sample, and directness.
4. A coverage gap must correspond to an empty or underpopulated coverage-matrix cell.
5. A conditional implication may recommend investigation or policy attention but cannot predict an unobserved effect.
6. “May reflect X” fails if X is not a supported mechanism.
7. The rendered sentence is rechecked against its structured plan; divergence deletes it.

This permits:

> The frameworks are complementary because one organizes relative skill demand while the other explains endogenous task allocation.

It does not permit:

> The difference probably reflects slower regional adoption.

unless adoption speed is an explicit, grounded premise.

| Rubric moved | Expected raw movement |
|---|---:|
| “Analytical Depth in Characterizing…Mechanisms” | +1.5 to +2.5 |
| “Critical Synthesis and Nuanced Evaluation…” | +1.5 to +2.5 |
| “Identification…of Emergent Themes, Theoretical Linkages, or Novel Perspectives” | +1.5 to +2.5 |
| “Insightful Integration…within the 4IR Context” | +0.7 to +1.4 |
| “Value and Foresight…Future Research Agendas” | +0.8 to +1.5 |

Failure mode: laundering a novel causal story as “analysis,” or allowing a multi-span NLI model to approve something merely plausible.

Cheap test: create an adversarial suite from 50 existing source-card pairs:

- 100 valid conjunctions/contrasts/rankings/gaps.
- 100 invalid examples that introduce mechanisms, causalize correlations, generalize local results nationally, change time horizons, or introduce entities/numbers.

Release requires **zero false admissions** on the invalid set and at least 90% acceptance of the valid set, followed by manual review of every accepted example.

## Lever 4: Replace section composition with claim modules

The report should be planned as approximately 34 H3 modules:

- 3: scope, method, and 4IR framing.
- 5: theoretical mechanisms.
- 8: technology eras and measurement.
- 6: industry comparisons.
- 6: wages, employment, labor share, skills, inequality, autonomy, and institutions.
- 4: cross-source adjudications and policy implications.
- 2: limitations/frontier agenda and conclusion.

Every H3 title should make a proposition:

- “Within-firm augmentation and platform displacement are institutionally compatible”
- “Exposure measures disagree because they encode different theories of susceptibility”
- “Employment stability can conceal labor-share and autonomy losses”

Each module receives:

- 3–6 source cards.
- At least two perspectives where the literature permits.
- One declared adjudication question.
- 350–450 cleaned words.
- Four to six paragraphs of roughly 60–100 words.
- An evidence → comparison → boundary → implication progression.

Target the **cleaned artifact**, not raw Markdown:

- 12,500–14,500 body words.
- 32–36 H3 headings.
- Median paragraph 70–95 words.
- 90–105 canonical journal sources.
- 7–10 surviving narrative author attributions per 1,000 words.
- 55–65% internally tagged synthesis/adjudication sentences.

Those are activation constraints, not score proxies. Only repeated RACE evaluation establishes benefit.

| Rubric moved | Expected raw movement |
|---|---:|
| “Scope of Industry-Specific Analysis” | +0.8 to +1.5 |
| “Breadth of Labor Market Restructuring Dimensions Covered” | +0.4 to +0.9 |
| “S1: Overall Structure and Logical Organization” | +1.5 to +2.5 |
| “S2: Paragraph Cohesion and Transitions” | +2.0 to +3.0 |
| “P1: Clarity and Synthesis…” | +1.0 to +2.0 |
| “F1: Formatting, Layout, and Visual Consistency” | +1.0 to +2.0 |

Failure mode: manufacturing 34 headings that simply subdivide the existing fact conveyor. A module without an adjudication question and premise-linked synthesis should fail planning.

Cheap test: generate the outline and module plans without prose. The linter must prove:

- Every rubric concept has assigned modules.
- Every H3 contains an explicit claim.
- Every source card has a planned use.
- No module consists entirely of single-source exposition.
- Every proposed synthesis sentence already has premise IDs and an allowed operation.

## Lever 5: Source-level deduplication and evidence adjudication

The existing report repeats mirrors of the same study and even emits “(also mirrored).” Canonicalize before planning, then compare studies on meaningful dimensions:

- Worker, firm, platform, regional, or national level.
- Experimental, quasi-experimental, observational, qualitative, or meta-analytic design.
- Exposure versus realized outcome.
- Short versus longer horizon.
- Employment, wages, productivity, labor share, skills, or autonomy.
- Institutional setting and industry.

This is how POLARIS can explain apparent contradictions without inventing a mechanism. For example, firm growth and worker losses are not automatically contradictory when they use different observational levels. The safe analytical statement is about estimands and scope; a causal institutional explanation needs a grounded source.

| Rubric moved | Expected raw movement |
|---|---:|
| “Balanced Discussion of AI’s Labor Market Impacts” | +0.5 to +1.0 |
| “Critical Synthesis and Nuanced Evaluation…” | +1.0 to +1.8 |
| “D1: Clarity of Data/Evidence Referenced or Summarized” | +0.6 to +1.2 |
| “P1: Clarity and Synthesis…” | +0.8 to +1.5 |

Failure mode: ranking evidence solely by journal prestige or pipeline tier rather than study design and fit to the claim.

Cheap test: select five apparent contradictions already in the bank. The system must produce a comparison grid and a bounded adjudication for each, with no new entity, number, or causal mechanism.

## Rollout and measurement

Do not spend a full compose until all mechanism tests pass.

1. **Corpus audit**
   - Canonicalize and classify all 105 existing rows.
   - This will reveal the real retrieval deficit.

2. **Cleaner-survival experiment**
   - Five cleaner runs per attribution form.
   - Then five paired RACE runs on the journal-only attribution retrofit.

3. **Synthesis-gate adversarial suite**
   - No full prose generation.
   - Zero unsupported admissions is a release requirement.

4. **Outline and two-module micro-compose**
   - One theory module and one cross-industry contradiction module.
   - Inspect the sentence ledger, not just the prose.

5. **Full compose**
   - Run three independent compositions.
   - Score each artifact five times.
   - With generation SD ≈0.016, three composes reduce generation SE to about 0.0092; five judges reduce the per-artifact judge SE to about 0.0033. Combined uncertainty is roughly 0.010, so a two-sigma detectable integrated effect is around 0.02.

6. **Release threshold**
   - Mean ≥0.5441 across independent compositions.
   - No composition below 0.52.
   - Zero faithfulness violations in sentence-ledger audit.
   - Cleaner-survival and corpus-admission checks remain hard gates.

## Expected ceiling

My non-additive estimate is:

| Configuration | Expected RACE |
|---|---:|
| Journal-safe narrative attribution on banked prose | 0.45–0.48 |
| Journal corpus repair + current fact-conveyor composer | 0.47–0.51 |
| New dual-lane composer without complete corpus repair | 0.50–0.53 |
| Full corpus + cards + synthesis contract + profile renderer | **0.53–0.56** |
| Excellent execution with stable cleaner survival | **0.55–0.58** |

The full redesign plausibly reaches bodhi and can reach cellcog, but 0.5578 is not guaranteed by matching paragraph length, heading count, or author density. The decisive mechanism is:

> **Verified journal evidence made visible in prose, organized into bounded cross-source adjudications that the current single-span gate cannot express.**

That is the path that preserves faithfulness while removing the actual reasoning bottleneck.