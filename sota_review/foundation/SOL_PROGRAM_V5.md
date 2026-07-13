## Verdict

Do not run the current composer with the new quantitative extractor yet. It cannot currently certify the non-negotiable attribution contract:

- The writer receives the LLM-authored `claim`, not the verbatim span, in `_fmt_cards()` ([cellcog_composer.py:404](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:404)).
- Extraction verifies only that the first 60 normalized characters of the proposed span occur in the source ([cellcog_composer.py:182](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:182)).
- The attributed-sentence gate checks against `span + claim`, allowing an extractor hallucination in `claim` to validate itself ([cellcog_composer.py:517](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:517)).
- The allegedly fabrication-proof table prints that same LLM-authored claim ([cellcog_composer.py:638](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:638)).
- Source binding is inferred from surnames, not carried structurally from generation; same-author/multiple-paper cases are ambiguous ([cellcog_composer.py:452](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:452)).
- The abstract is hardcoded after all gates and makes substantive claims without passing either lane ([cellcog_composer.py:705](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:705)).

This does not prove that the artifact contains fabrication. It proves that “span-verified” and “fabrication structurally impossible” are presently unjustified. Flooding this path with numbers would magnify the risk.

For score estimates below, I use the local conversion around turn 3:

\[
\Delta score \approx 0.036 \times \sum_i w_i\Delta criterion_i
\]

These are direct score units, not raw criterion points. They exclude speculative reference-drag benefits and are deliberately non-additive where fixes overlap.

## One integrated execution plan

Build all components this round, but release them through a cumulative replay ladder over one frozen corpus. That prevents another turn-2 confound while still delivering one final stacked arm.

### 0. Close the evidence-laundering path — mandatory prerequisite

**Mechanism**

Replace prose-level source guessing with a structured sentence IR:

```text
{
  voice: "attributed" | "owned",
  text: "...",
  source_clauses: [{card_id, clause_text}],
  premise_card_ids: [...]
}
```

For attributed clauses:

- Verify the entire verbatim span against the full source with stored byte offsets.
- Check the clause against that span alone—never against `claim`.
- Require exact number/token boundaries plus semantic entailment.
- Bind source by `card_id`; author, year, and journal are rendered metadata, not used to rediscover the source.
- Gate each clause separately in comparative sentences.

For owned sentences:

- Require an explicit marker such as `**[Our synthesis]** We infer...`.
- Permit non-entailment, exactly as your invariant requires.
- Forbid source names, figures, and new particulars.
- Screen for contradiction with the selected premises; do not require premises to entail the conclusion.

Generate the abstract and conclusion last from admitted sentence objects and pass them through the same contract.

Acceptance attacks must include: span-prefix spoofing, claim self-validation, same surname/different papers, wrong-paper mechanism binding, decimal substring leakage, mixed-source clauses, journal-only attribution, and ungated abstract claims.

**Criteria and score**

Direct benchmark effect: **−0.002 to +0.002**. Its purpose is validity, not points.

**Failure risk**

It may delete attractive but unsupported prose and temporarily lower the score. That is the correct result. An arm failing this gate is burned regardless of score.

**Stacking**

Must precede every other intervention. Nothing quantitative or synthetic is safe to stack before it.

---

### 1. Replace the extractor’s 28,000-character head sample with full-document evidence mining

The current extractor exposes only 539,222 of 1,688,418 full-text characters—31.9%. It mostly sees introductions, exactly where generic claims and literature framing dominate ([cellcog_composer.py:160](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:160)).

**Mechanism**

- Parse full text into section-aware overlapping chunks.
- Run deterministic candidate harvesting first: sentences containing effects, percentages, coefficients, confidence intervals, sample sizes, dates/periods, and comparative quantities.
- Run semantic extraction across all Results, Methods, tables, appendices, abstract, and conclusion chunks.
- Cards must carry:
  - verbatim span and offsets;
  - effect and unit;
  - denominator/comparator;
  - population/sample/geography/period;
  - technology;
  - industry;
  - outcome;
  - unit of analysis;
  - method/design;
  - uncertainty/significance;
  - source version.
- Consolidate duplicate cards by finding—not by paper—and retain all corroborating sources.
- Treat `claim` as a display cache derived after verification, never as evidence.

The quantitative target is not “202 numbers.” Cellcog’s count includes years, samples, and exposure estimates. The target is interpretable evidence texture: effect + unit + population + design + scope.

**Criteria and score**

Moves D1, analytical depth, disruptive scale, literature depth, and P1 because the judge can see what studies found and how firmly.

Expected marginal effect: **+0.005 to +0.009**.

**Failure risk**

Count-chasing can produce contextless figures, incomparable estimates, and tables full of sample sizes rather than findings. Require complete estimate tuples and reject orphan numbers.

**Stacking**

Safe after item 0. It supplies items 3–8.

---

### 2. Build a query-derived coverage matrix and expand the sectoral corpus against it

This is the largest of the original seven levers. The current outline promises four sectoral subsections while its corpus cannot substantiate them; the artifact visibly substitutes Frey–Osborne occupational exposure for healthcare and education evidence ([report.md:207](/home/polaris/wt/flywheel/outputs/cellcog_arm/report.md:207)).

**Mechanism**

Compile every question into a research contract:

```text
requested source constraints
core concepts
outcome dimensions
industries/subpopulations
geographies
time horizons
method/design diversity
required contrasts
output genre
```

For task 72, use a matrix covering at least manufacturing, finance/professional services, healthcare, education, transport/logistics, retail, agriculture, creative work/platforms, crossed with employment, wages, tasks, skills, productivity, autonomy/control, and labor share.

A cell closes when it has:

- two groundable, relevant journal works where literature exists;
- at least one credible quantitative or direct qualitative result;
- methodological contrast where material;
- or an explicit, corpus-scoped evidence gap.

Retrieve through citation graphs plus targeted semantic search. Apply journal/English/source constraints before composition and semantic relevance before admission.

A working paper may serve as a content mirror for a published journal article only when title/authors/version provenance establishes that relationship. “The working paper is the paper” is not sufficient for source binding: journal and working-paper versions can differ.

**Criteria and score**

Mainly:

- Industry scope, 5.76 → approximately 8–8.5.
- Various industries, 5.82 → approximately 8–8.5.
- Breadth, disruption scale, critical synthesis, and balance also benefit.

Expected marginal effect: **+0.010 to +0.015**.

**Failure risk**

Keyword retrieval has already admitted ResNet, medical papers, job listings, and irrelevant high-tier articles. Coverage quotas can also incentivize weak papers. Selection needs semantic relevance and cell-level gap disclosure, not forced filling.

**Stacking**

Safe with items 1 and 3 because they share the same research contract. Unsafe as a blind “add more papers” pass after writing.

---

### 3. Make extraction facet-aware, including 4IR, rather than adding a hardcoded 4IR extractor

Seven papers allegedly discuss 4IR, but lexical card selection cannot find what extraction never represented. The current `_select()` uses subsection-word overlap against claims and sparse metadata ([cellcog_composer.py:392](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:392)).

**Mechanism**

- Generate extraction facets from the research contract.
- Extract evidence separately for each requested facet.
- Store facet tags and explicit relations such as:
  - AI ↔ cyber-physical/Industry 4.0 infrastructure;
  - AI ↔ organizational redesign;
  - convergence and systemic scope;
  - technological-determinism critiques;
  - how 4IR framing changes interpretation of labor evidence.
- Require a 4IR claim to connect to labor restructuring; generic “AI is part of 4IR” passages do not close the cell.
- Use the 4IR lens again in empirical synthesis and implications, not just the introduction.

This remains general: another question will produce different facet extractors.

**Criteria and score**

Targets the three 4IR criteria with combined weight 0.1145.

Expected marginal effect: **+0.005 to +0.008**.

**Failure risk**

It can generate repeated background definitions without analytical use. Require every 4IR card or owned synthesis to connect to a later empirical or institutional argument.

**Stacking**

Safe within items 1–2. Do not implement it as task-72-only prompt text.

---

### 4. Add a fact-use ledger, but do not enforce “one card, one section”

The current 28 subsection jobs consume 222 card slots from only 82 cards. One finding is selected eight times; several canonical claims recur four times verbatim. The report contains at least 41 exact normalized repetitions.

**Mechanism**

Create stable `finding_id` and `work_id` identifiers. The document planner records:

- primary section;
- analytical role;
- attributed uses;
- owned syntheses using it;
- whether a later use adds a new comparison, boundary, method, or implication.

Rules:

- A finding is narrated fully once.
- Later sections may use it only for a new analytical role.
- Otherwise use an owned backward reference without restating the fact.
- Corroborating sources remain in the basket; consolidation does not delete them.
- Each section receives a deliberately different evidence bundle.

**Criteria and score**

Incrementally improves breadth, focus, S2, P1, and evidence density.

Expected marginal effect: **+0.001 to +0.003**.

**Failure risk**

A hard one-use rule would starve theory and synthesis sections and contradict the consolidate-don’t-drop architecture. The ledger governs rhetorical reuse, not evidence retention.

**Stacking**

Safe and helpful before synthesis. Deleting duplicates after writing without replacing them is expected to be score-neutral, as the earlier repetition-guard result showed.

---

### 5. Replace isolated subsection composition with a document-level comparison planner

This is the highest-value writing change. Currently all 28 subsections are generated independently in six threads with no shared argument state ([cellcog_composer.py:676](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:676)). A later cohesion pass cannot manufacture comparisons the planner never selected.

**Mechanism**

Before prose generation, construct comparison bundles keyed by:

```text
technology × outcome × industry × unit × method × horizon × geography × direction
```

The planner then assigns each subsection:

- a claim-first thesis;
- two or more attributed evidence clauses;
- the exact comparison being made;
- methodological comparability or non-comparability;
- an owned verdict;
- a boundary/unresolved question;
- a bridge to the next subsection.

Generate attributed evidence objects first. Then generate explicit owned sentences such as:

> **[Our synthesis]** We read these results as compatible rather than contradictory because they observe different units of analysis.

This sentence may be non-entailed; it must not masquerade as either source’s claim.

The dedicated critical-synthesis section should contain several named syntheses spanning industries and methods, not a few residual paragraphs. The current section is almost empty and largely recycles Frey–Osborne ([report.md:223](/home/polaris/wt/flywheel/outputs/cellcog_arm/report.md:223)).

**Criteria and score**

Primary effects:

- Critical synthesis.
- Analytical depth.
- Emergent themes.
- Balance.
- P1.
- Industry analysis through cross-sector comparison.

Expected marginal effect: **+0.010 to +0.016**.

**Failure risk**

Incorrect method/horizon tags could manufacture a false reconciliation. Those fields must be verified against article spans or explicit metadata. Owned sentences must never silently inherit an author attribution.

**Stacking**

Safe after items 0–4. This is where the industry, numeric, and 4IR evidence becomes an argument.

---

### 6. Add a dedicated implications and research-agenda generator

**Mechanism**

Run after the factual and synthesis ledger is complete. Produce three classes:

- implications directly attributed to policy/organizational evidence;
- owned implications derived from established boundary conditions;
- research gaps derived from empty or conflicting coverage-matrix cells.

Each implication object must name:

```text
premises
affected actor
level
time horizon
boundary condition
evidence status
```

Avoid predictions. “More longitudinal evidence is needed to distinguish temporary adoption effects from durable employment change” is valid when the ledger shows only short horizons. A new policy prescription such as UBI, robot taxation, or retraining requires its own evidence cards.

**Criteria and score**

Mainly Value/Foresight, plus emergent themes and focus.

Expected marginal effect: **+0.004 to +0.006**.

**Failure risk**

Implications are the easiest place to smuggle in new actors, mechanisms, or forecasts. New particulars require attributed premises; otherwise the implication stays abstract and owned.

**Stacking**

Safe after item 5 and before the final cohesion pass.

---

### 7. Run a restricted sequential cohesion pass

**Mechanism**

Do not let a final model rewrite the whole report. Freeze every attributed clause byte-for-byte. The pass may only:

- add or revise owned topic sentences;
- add owned backward/forward transitions;
- reorder already admitted paragraph objects within their section;
- remove redundant owned sentences;
- repair grammar without altering factual clauses.

Give it the prior paragraph summary, current paragraph role, and next paragraph role. Require transitions to express analytical movement—level, method, horizon, sector—not generic “Turning now to...”.

**Criteria and score**

Targets S2 directly, with secondary gains in L1, P1, S1, and audience adaptation.

Expected marginal effect: **+0.004 to +0.007**.

**Failure risk**

A conventional rewrite pass can alter numbers, swap bindings, or add causal explanations. Immutability of attributed objects is the safety boundary. Excess transition prose can also create a smoother but slower report.

**Stacking**

Safe only in this restricted form. A free-form sequential rewrite is not safe to stack.

---

### 8. Resolve the reference-list/table contradiction with two separate artifacts

The cleaner explicitly removes reference lists ([clean_prompt.py:24](/home/polaris/wt/flywheel/third_party/deep_research_bench/prompt/clean_prompt.py:24)). Restoring an ordinary bibliography is therefore not a credible scoring lever.

**Mechanism**

- Keep a complete formal bibliography in the delivered artifact for scholarly integrity and human verification.
- Expect **zero benchmark gain** from it.
- In the body, render analytical study tables whose rows contain substantive evidence:
  - study/authors;
  - journal and year in prose;
  - design/sample;
  - technology/sector;
  - quantitative result;
  - boundary/interpretation.
- Include one cross-study outcome table and one compact sectoral table.
- Generate cells from verified card fields, not LLM-authored claims.
- Run both tables through the production cleaner five times before final scoring. If a “source register” caption causes deletion, describe it as an evidence-synthesis table instead.

The judge’s “no reference list” criticism is best understood as a proxy for poor visible verifiability. In-prose attribution plus an analytical study table addresses what the judge can actually see.

**Criteria and score**

Incremental effects on D1, F1, P1, and possibly journal-source verification.

Expected visible-table effect: **+0.001 to +0.003**.  
Expected ordinary-bibliography effect: **0.000**.

**Failure risk**

A table formatted like bibliography entries may be deleted. A table with truncated claim text can also strip necessary denominators or caveats.

**Stacking**

Safe after item 1; cleaner survival is a hard gate.

---

### 9. Parameterize the composer and run the generality gate

The current architecture is literally a task-72 machine: the extraction question, outline, title, abstract, sectors, and rubric interpretation are hardcoded ([cellcog_composer.py:103](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:103), [cellcog_composer.py:255](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:255)).

**Mechanism**

Replace hardcoded constants with a query compiler that produces the research contract, coverage matrix, outline, evidence schema, and answer genre. Then freeze the code and evaluate:

- task 72;
- one unrelated scientific literature review;
- one legal/comparative question;
- one practical public-facing question;
- one adversarially thin-evidence question.

Use current successful artifacts only; do not score historical aborted runs. Run k=5 paired and inspect criterion-level written feedback.

**Criteria and score**

Immediate task-72 delta: **0.000**.

Mission value: decisive. Without this test, “general system” is an unsupported claim.

**Failure risk**

Five tasks are still a small sample, and benchmark questions may need different answer genres. That is precisely what this test is intended to reveal.

**Stacking**

Read-only and safe. It must not influence task-72 prompts after the freeze.

## One-round execution and measurement order

Build everything, but produce these cumulative banked artifacts:

1. **A0 — Integrity replay:** new source-bound IR, old corpus/content. It must preserve supported claims and kill all adversarial attacks.
2. **A1 — Evidence arm:** expanded coverage matrix + full-document numeric/facet extraction + verified analytical tables.
3. **A2 — Argument arm:** fact-use ledger + comparison planner + native attributed/owned synthesis.
4. **A3 — Final arm:** implications + restricted cohesion + final abstract/conclusion + body tables and bibliography.

Use one frozen A1 evidence snapshot for A2 and A3. This removes corpus noise from the writing comparison. Run cleaner-survival canaries on each artifact. Score A0–A3 k=5 paired, but make the release decision from criterion-level movement as well as the scalar. The final submission is A3 only if no faithfulness canary regresses.

## Ranking

### Entire program, by expected task-72 score impact

1. Document-level comparison planner and native owned synthesis: **+0.010 to +0.016**
2. Coverage-matrix industry expansion: **+0.010 to +0.015**
3. Full-document quantitative/evidence extraction: **+0.005 to +0.009**
4. Generic 4IR/facet extraction and integration: **+0.005 to +0.008**
5. Restricted sequential cohesion: **+0.004 to +0.007**
6. Dedicated implications/research agenda: **+0.004 to +0.006**
7. Analytical tables/source register: **+0.001 to +0.003**
8. Fact-use ledger: **+0.001 to +0.003**
9. Integrity repair: approximately score-neutral, but mandatory
10. Generality measurement: zero task-72 points, mission-critical

### The original seven planned fixes

1. **#3 Industry corpus expansion** — highest value.
2. **#4 4IR extraction** — keep only as generic facet-aware extraction.
3. **#1 Cohesion pass** — keep only as an owned-lane, attribution-immutable pass.
4. **#2 Implications pass** — worthwhile and independently targeted.
5. **#6 Card-partition ledger** — replace with a fact-use ledger; hard partitioning is low-value and risky.
6. **#7 Measure generality** — no immediate score, but non-negotiable for the stated mission.
7. **#5 Formal reference list** — zero expected benchmark effect as a standalone lever.

## What should be dropped

Drop these exact formulations:

- **Standalone traditional reference-list restoration as a scoring fix.** Keep the bibliography for integrity, but do not assign it score delta.
- **Hard “one card, one section” partitioning.** It can starve synthesis. Use rhetorical fact-use accounting instead.
- **A free-form post-hoc cohesion rewrite.** It can break source bindings. Permit only owned transitions and reordering of immutable attributed objects.
- **A task-72-specific 4IR extractor.** Replace it with query-derived facet extraction.
- **“Reach 202 quantitative claims” as an objective.** Optimize complete, interpretable evidence tuples and comparative use.
- **Treating working-paper text as automatically entailing the later journal version.** Require version provenance.

## Is 0.5603 reachable?

Not with the current architecture, and not credibly in this single round.

The integrated program has a plausible marginal gain of roughly **+0.040 to +0.067**, with substantial overlap. From 0.4603, the most credible landing range is approximately **0.50–0.53**; **~0.54 is an upside case** if comparison effects drag the reference down strongly. Banking on 0.5603 would be cheerleading.

The reason is structural. Cellcog’s weighted criterion mean is about 9.4. The present report is 6.857. These fixes can plausibly move it into the mid-to-high eights, but not produce near-ceiling performance on almost every criterion simultaneously. Cellcog is not winning through one exploit; it has deep multidisciplinary evidence, native report-level argument, direct quantitative texture, sectoral comparisons, coherent implications, and fluent document control.

Reaching 0.5603 requires replacing this subsection composer with a general research architecture:

```text
question/genre compiler
    → adaptive rubric and coverage matrix
    → recursive retrieval until evidence cells close
    → source-bound evidence graph
    → contradiction/comparison bundles
    → report-level argument planner
    → attributed-clause + explicit-owned-synthesis generation
    → implications/abstract generated from admitted body
    → independent faithfulness and contradiction audit
    → criterion-specific revision
    → unseen-question evaluation
```

That is more than adding seven passes. It is a new composer built around the attributed/owned invariant. The current `cellcog_composer.py` is a useful task-72 experiment, but as written it is neither general nor safe enough to serve as the winning architecture.