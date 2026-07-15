Turn 3 should be a controlled rollback: preserve rank10’s coverage, retain journal-only evidence, and replace Turn 2’s destructive composition pipeline. Do not compose another report directly from the 32-paper corpus.

The central error was treating source quality, coverage, prose structure, and faithfulness as one transformation. Citation-graph centrality selected a credible corpus; it did not select a corpus capable of answering the entire rubric.

## 1. Exact Turn 3 changes, in order

| Order | Change | Criterion targeted | Direct acceptance condition |
|---:|---|---|---|
| 1 | Make the 97-source rank10 report the **coverage specification**. Extract its substantive claims, examples, distinctions, and implications before rewriting anything. | Comprehensiveness; instruction-following | Every rank10 substantive unit is either retained, deliberately revised, or marked “unsupported—needs evidence.” Nothing disappears silently. |
| 2 | Convert the judge rubric into a **coverage contract**, especially 4IR grounding, 4IR integration, disruption scale/speed, and actionable foresight. | Comprehensiveness; insight | Every rubric requirement maps to named claims and evidence—not merely to a heading. |
| 3 | Use the 32 journal papers to **re-ground** the rank10 claims. Expand the corpus only through targeted searches for uncovered claims. Stop using citation-graph expansion as the selection objective. | Exclusive high-quality journal citation; comprehensiveness | Every required claim has suitable journal evidence or is explicitly presented as an evidence gap. No required claim is deleted because the initial 32 papers lacked it. |
| 4 | Add a complete, standard reference list and remove questionable venues. | Exclusive high-quality journal citation | Every in-text citation resolves to exactly one journal reference; every reference is cited; journal, year, volume/pages/article number, and DOI are present when available. No books, reports, websites, conferences, or preprints leak in. |
| 5 | Build the article around a **4IR causal spine**, not a sequence of paper summaries. Define 4IR, locate AI within it, explain interconnected infrastructures, then show consequences. | Grounding in 4IR; 4IR Integration; insight | The outline explicitly connects AI with data, cloud/edge compute, networks, sensors/IoT, robotics or cyber-physical systems, and institutional feedback. It also explains why this combination differs from prior automation waves. |
| 6 | Restore a substantial disruption-character-and-scale argument. Cover scale, speed, task versus job effects, sectoral heterogeneity, diffusion constraints, and uncertainty. | Disruption Character and Scale; comprehensiveness | Each of those analytical questions has at least one supported answer. The section cannot pass merely by meeting a word count. |
| 7 | Replace epistemic-label quotas with **analytical obligations**. Each major section must synthesize convergence, disagreement, mechanism, boundary conditions, and implications where the evidence supports them. | Insight | No section is just “paper A says / paper B says.” Each section contains an explicit synthesis that uses multiple sources to reach a bounded conclusion. |
| 8 | Give implications and conclusion their own composition stages and reserved capacity. They must be written from the completed claim ledger, not from whatever tokens remain. | Value and Foresight; Structure | Implications contain actor, action, time horizon, trigger/condition, expected mechanism, trade-off, and measure of success. The conclusion answers the report’s central question and introduces no new claims. |
| 9 | Eliminate the attribution template. Use ordinary author–date citations, naming journals selectively when their identity matters. Put full provenance in the reference list. | Language Clarity; readability | Zero occurrences of “Writing in …” as a stock opener. No repeated attribution opener dominates the prose. Citation exclusivity remains machine-verifiable from the reference list. |
| 10 | Change the faithfulness gate from **drop** to **repair**. Unsupported sentences are narrowed, split, qualified, re-evidenced, or converted into explicit gaps. Deletion is the last action. | Comprehensiveness; insight; factual grounding | The gate reports dispositions. Required claims have zero silent deletions, and the coverage contract is rerun after repair. |
| 11 | Compose section-by-section from section packets, then perform a separate global cohesion pass. | Language Clarity; Structure | Every paragraph has a declared function and a logical relation to the preceding paragraph. Every heading’s promised question is answered before the next heading. |
| 12 | Run a completeness pass after all filtering and editing. | Structure; readability | No fragments, duplicated clauses, empty or vestigial sections, unresolved placeholders, broken citations, or abrupt endings. Generation logs show normal completion rather than output-limit termination. |
| 13 | Keep the final report near the demonstrated saturation region—roughly 8,000 words—but treat that as **capacity**, not a scoring lever. | Prevents truncation-driven coverage loss | All semantic obligations fit. If they do not, reduce redundancy or increase section capacity; do not amputate the final sections. |

Do not optimize H3 count, paragraph length, journal-name count, epistemic-label count, or raw word count. Those are now demonstrated non-levers or actively harmful when pursued mechanically.

## 2. Corpus decision

Transform rank10. Do not keep composing from only the 32-paper corpus.

The correct separation is:

- **Rank10 report:** coverage and argument inventory.
- **Journal corpus:** evidentiary authority.
- **Rubric contract:** completeness test.
- **Turn 3 prose:** newly composed synthesis.

The 32 papers were selected through citation-graph expansion. That favors central, mutually connected literature. It predictably underrepresents peripheral but rubric-critical material: broader 4IR infrastructure, cross-sector diffusion, scale and speed, institutional consequences, and forward-looking policy implications.

The 97-source report already demonstrated materially better coverage. Throwing away its semantic inventory to gain source purity was unnecessary. Preserve its claims and examples, then replace or supplement their evidence with high-quality journals. When none of the 32 supports a required claim, conduct a gap-specific search. The final corpus should be as large as the coverage contract requires; “32” has no intrinsic value.

This is not permission to carry all 97 sources into the bibliography. Carry forward their **coverage**, not their source types.

## 3. Prompt, budget, or architecture?

All three contributed, but architecture is the primary failure.

### Repetition: predominantly a prompt/template defect

“Writing in the…” appearing 135 times is direct evidence of a hard-coded realization pattern. The prompt rewarded visible journal attribution without requiring linguistic variation or a global repetition check.

Fix: remove the template entirely. Provenance should normally appear as `(Author, Year)`, with occasional natural formulations such as “A longitudinal study found…” Journal titles belong primarily in the reference list.

### Truncation: architecture first; token budget only if the logs prove it

The symptoms alone do not establish an output-limit failure. Check the generation finish reason and stage artifacts:

- If generation ended because of length, capacity was inadequate.
- If it ended normally but the final sections are incomplete, the prompt or section plan was incomplete.
- If sections were complete before the faithfulness pass and incomplete afterward, the destructive gate caused the truncation.
- If completed sections were lost during assembly, it is an orchestration bug.

Regardless, one-shot composition made the conclusion and implications residual outputs. Section-wise composition with reserved stages removes that vulnerability.

### Incompleteness and fragmentation: architecture defect

The pipeline allowed 74 sentences to be dropped without reopening the affected argument. It optimized sentence-level faithfulness after composition but had no coverage-preservation invariant. That guarantees holes.

Shortening paragraphs and adding headings cannot repair missing argumentative links. Cohesion must be designed at the claim and paragraph-function levels, then checked again after the faithfulness pass.

So the diagnosis is:

- Repetitive prose: **prompt/template**.
- Abrupt ending: **budget if and only if `finish_reason=length`; otherwise architecture**.
- Missing sections and lost coverage: **architecture**.
- Thin insight despite 44 labels: **objective-function error**—labels were substituted for synthesis.

## 4. Cheapest tests before a full compose + judge call

No cheap test can prove the judge score will rise. It can only prove that a specific implementation change actually fired. Claiming otherwise would be another proxy mistake.

Use these direct preflight tests:

1. **Coverage diff — no prose generation required**

   Extract the rank10 semantic units and map them to the Turn 3 outline. Fail if any unit disappears without an explicit disposition. Separately require payloads for the four judge-identified deficits.

2. **Evidence round-trip — no prose generation required**

   For every planned claim, record the supporting paper and exact evidentiary passage. Then reverse the mapping from every reference back to its claims. Fail unresolved claims, orphan references, non-journal sources, and uncertain venue quality.

3. **4IR causal-model test — outline only**

   Ask the outline to answer, in complete propositions: What is 4IR? Where does AI sit in it? Which infrastructures enable it? What feedback loops result? Why is this different from previous waves? Fail if any answer is merely a heading or list of technologies.

4. **Scale-and-speed payload test — outline only**

   Require supported answers for magnitude, rate of diffusion, unit of disruption, sector variation, constraints, and uncertainty. This directly prevents another “extremely brief” subsection; a word minimum alone does not.

5. **Foresight matrix — no prose generation required**

   Populate rows with actor, action, horizon, trigger, mechanism, trade-off, metric, and evidence. Fail incomplete or generic rows such as “policymakers should prepare.”

6. **Faithfulness-gate replay — reuse Turn 2 artifacts**

   Run the revised gate on the 74 sentences that were previously dropped. It must return dispositions such as supported, narrowed, qualified, re-evidenced, explicit gap, or optional deletion. Fail if required claims are simply deleted. This is the cheapest and strongest test of the architecture change.

7. **Attribution pilot — compose only 500–800 words**

   Generate one evidence-dense section. Run exact phrase and sentence-opener counts. Fail any stock “Writing in…” construction, duplicated clause, or source-by-source catalogue. Confirm that all citations still resolve to journal references.

8. **Cohesion pilot — compose three adjacent paragraphs**

   The three paragraphs should perform claim → qualification/contrast → implication. Remove the transition sentences and ask whether the logical relation becomes materially less explicit; if it does not, the supposed transitions were decorative rather than connective.

9. **Completion harness — synthetic dry run**

   Run the production orchestrator with small section packets. Verify that every section is independently completed, survives the gate, is assembled in order, and ends normally. Capture finish reasons and before/after sentence counts. This isolates token-limit, filtering, and assembly failures without paying for the full report.

10. **Final static gate — after composition, before judging**

   Automatically fail fragments, duplicate clauses, unmatched citations, unfulfilled headings, unresolved placeholders, empty conclusions, missing reference entries, and any required claim lost between the plan and final artifact.

The decisive Turn 3 hypothesis is not “more structured prose.” It is:

> Rank10 coverage can be preserved while its heterogeneous evidence is replaced by high-quality journal support, provided that faithfulness repair is coverage-aware and composition is organized around a 4IR argument rather than source attributions.

If that hypothesis fails, the failure will be interpretable. Another 32-paper one-shot composition would merely repeat Turn 2 with cleaner cosmetics.