# The verdict

POLARIS can plausibly reach **0.54–0.55**, but not by extending its present fact-conveyor. The winning design is:

> **Verified evidence packets → deterministic comparison graph → bounded adjudications → task-specific assembly**

The current evidence bank plus formatting changes probably tops out around **0.49–0.51**. Reaching 0.54 requires a new, journal-only evidence bank and a synthesis layer that can make assertive cross-source judgments without inventing mechanisms.

My honest forecast for the full plan is **0.535–0.552, centered near 0.545**. A stretch implementation could approach 0.56; it is not a credible guaranteed outcome.

The official task confirms the strict journal-only instruction, and the task-specific rubric assigns 0.32 to insight, 0.29 to comprehensiveness, 0.25 to instruction-following, and 0.14 to readability. [Task prompt](https://github.com/Ayanami0730/deep_research_bench/blob/main/data/prompt_data/query.jsonl), [task-72 criteria](https://raw.githubusercontent.com/Ayanami0730/deep_research_bench/refs/heads/main/data/criteria_data/criteria.jsonl). The published evaluation code also confirms the target/reference normalization. [RACE implementation](https://github.com/Ayanami0730/deep_research_bench/blob/main/deepresearch_bench_race.py)

## Why bodhi wins

Bodhi is shorter because almost every paragraph performs scored work. POLARIS is longer because most paragraphs merely transport facts.

### 1. Bodhi makes compliance visible after cleaning

Bodhi opens by defining:

- Journal-only scope.
- What “restructuring” includes.
- How weakly extractable evidence is handled.

It then names authors and often journals in running prose. After citations and references disappear, the judge can still see scholarly provenance.

POLARIS visibly cites or names WEF, OECD, IMF, Goldman Sachs, BLS, blogs, news, SSRN, arXiv, vendor statistics and unknown-tier material. That directly damages the journal-only criterion, literature-review format, representativeness, and probably the judge’s overall narrative.

### 2. Bodhi uses evidence paragraphs; POLARIS uses evidence queues

A typical bodhi unit contains:

1. Named study or framework.
2. Study finding.
3. Method, scope, or causal status.
4. Limitation.
5. Bounded implication.

POLARIS instead places dozens of unrelated results into a section—ImageNet error rates, AI spending projections, employment forecasts, corporate adoption statistics—without establishing why one result changes the interpretation of another.

### 3. Bodhi has an argument architecture

Its sequence is functional:

> Frameworks → measurement → outcomes → industries → firm/market restructuring → job quality → institutions → convergence/debates/gaps.

POLARIS’s section titles look thematic, but the content repeatedly jumps between levels, technologies, periods, outcomes and source quality. Its “Cross-Study Synthesis” even begins with a sentence fragment.

The H3 and paragraph measurements are symptoms of this distinction. The lever is not “40 H3s”; it is satisfying the rubric’s structure, paragraph-focus and transition requirements.

### 4. Bodhi explicitly reconciles levels of evidence

Examples include:

- Establishment hiring changes alongside undetectable aggregate effects.
- Employment growth at AI-investing firms alongside greater concentration.
- AI wage gains alongside robot/software wage losses.
- Technical exposure distinguished from adoption and realized outcomes.
- Job quantity separated from job quality and control.

POLARIS contains evidence for several of these tensions but concludes that no contradictions were detected and repeatedly calls the literature “inconclusive.” That abandons the two largest insight criteria: mechanisms and critical synthesis.

### 5. Bodhi spends words on evidence quality

Its measurement section repeatedly states strengths and limitations. It distinguishes causal, correlational, survey, postings, exposure and case-study evidence.

POLARIS often reports precise numbers without clarifying whether they are projections, correlations, experiments, administrative estimates or corporate forecasts. Precision without epistemic classification does not become depth.

### 6. Bodhi covers industries as industries

Manufacturing, healthcare, finance, transportation, creative work and professional/public services receive dedicated treatment connecting technology to work reorganization.

POLARIS scatters industry facts throughout general sections. “Various industries” is therefore nominally covered but weakly analyzed.

### 7. Cellcog adds what bodhi only partly supplies

Cellcog’s major advantage is its explicit synthesis protocol:

> Finding A → conflicting finding B → reconciliation → candidate explanations → unresolved question.

It also labels the epistemic status of its original syntheses. That directly targets the rubric’s “emergent themes,” “novel perspectives,” “critical synthesis,” and “future research” criteria.

## The new faithfulness contract

The current contract incorrectly treats all interpretation as prospective factual invention. Replace it with four types.

### FACT

Unchanged:

- Span-verified.
- Byte-identical or mechanically quoted.
- Every number, attribution, entity and empirical mechanism supported.

### STRUCTURE

Unchanged but expanded:

- Headings, ordering, paragraph boundaries and tables assembled from sidecars.
- Source names and journal names may be inserted only from verified bibliographic metadata.

### RELATION

A new deterministic category. It describes a relationship between verified facts without adding an external mechanism.

Allowed relations:

- `CONVERGES_WITH`
- `CONTRASTS_WITH`
- `DIFFERS_IN_SCOPE`
- `DIFFERS_IN_OUTCOME`
- `STRONGER_DESIGN_WITHIN_SCOPE`
- `ESTABLISHES_AT_LEVEL`
- `DOES_NOT_ESTABLISH_AT_LEVEL`
- `REMAINS_UNRESOLVED`

Examples:

- “The reviewed evidence establishes within-firm productivity gains but does not establish economy-wide employment growth.”
- “These results are compatible because one measures task performance and the other measures employment.”
- “The stronger design supports displacement within the studied local markets; it does not settle national effects.”

These are assertive adjudications, not hedges.

### INTERPRETATION

This is the only intentionally cross-source prose. It must:

- Sit beside at least two facts from independent sources.
- Use only entities and mechanisms already present in its evidence packet.
- Introduce no number, attribution, empirical event or uncited mechanism.
- Link to a machine-readable support set.
- Be generated from controlled templates or constrained slots.
- Fail closed if comparable scope, outcome or direction cannot be established.

An explanatory mechanism may appear only when at least one supporting span states that mechanism. Otherwise POLARIS may identify a contrast but not explain its cause.

Replace “may,” “perhaps,” and blanket “inconclusive” with a verdict vocabulary:

> establishes, supports, contradicts, does not establish, is limited to, cannot distinguish, remains unresolved.

That is adjudication without overclaiming.

## Lever plan

Expected points below are estimated changes in final normalized RACE score. They are sequential diagnostic ranges but still overlap; do not add their upper bounds.

| Lever | Rubric criterion moved | Expected | How it fails | Cheap proof before compose |
|---|---|---:|---|---|
| **1. Deterministic structural reflow** | Readability: structure, paragraph cohesion, sourced-information clarity, formatting | **+0.014–0.022** | Produces many headings but leaves fragments, arbitrary clusters or choppy prose | Transform the banked artifact without changing factual sentences. Require one claim-unit per paragraph, roughly 30–45 informative H3s, median 55–95 words and no extreme walls. Verify the FACT-sentence multiset is unchanged; run the official cleaner; score k=5 paired |
| **2. Journal-only source gate plus visible attribution** | Instruction: high-quality journals and English-only; comprehensiveness: representative literature; readability: evidence clarity | **+0.016–0.028** | Filtering destroys coverage; metadata misclassifies a working paper; source identity is still removed by cleaning | Produce an eligibility manifest for every source: journal-article type, English, journal/ISSN, peer-review evidence, canonical version. Zero off-type sources. Prefix anchor findings with verified author/journal metadata and confirm they survive cleaner output. Make a journal-only transform of the banked report and score k=5 |
| **3. Rubric-driven coverage and industry matrix** | Comprehensiveness: restructuring dimensions and industries; instruction: focus and various industries | **+0.010–0.020** | Becomes a checklist of thin sectors or repeats generic findings under several headings | Before search, require coverage for employment, displacement, task change, skills, wages, productivity and job quality; plus at least five industries with two independent journal sources each, one empirical where available. Every industry must contain a task/work reorganization pathway, outcome and limitation |
| **4. Evidence packets with design and limitation** | Comprehensiveness: depth/representativeness; insight: critical evaluation; readability: data clarity | **+0.008–0.016** | Formulaic paragraphs; inferred limitations; equal weight given to forecasts and causal evidence | Each anchor packet must contain verified fields for population, unit, period, technology, industry, outcome, direction, method, causal status and explicitly stated limitation. Missing fields stay missing. Audit a banked transform: at least 80% of central claims expose method or evidentiary status |
| **5. Deterministic adjudication graph** | Insight: mechanisms, critical synthesis, emergent themes; comprehensiveness: balance | **+0.022–0.038** | Invents reconciliation mechanisms or remains so cautious that it merely repeats facts | Run metamorphic tests: remove one supporting source and the verdict must weaken; reverse an outcome and `CONVERGES` must become `CONTRASTS`; add a comparable contradiction and a strong verdict must be blocked. Render 8–12 synthesis nodes into the banked report and score k=5 |
| **6. Make 4IR an explanatory spine** | Comprehensiveness 4IR context; insight 4IR integration; instruction 4IR theme | **+0.006–0.012** | “Fourth Industrial Revolution” appears often but explains nothing | Require every 4IR paragraph to connect verified features—general-purpose diffusion, organizational complements, cyber-physical integration or institutional change—to a labor outcome. Delete any 4IR sentence whose removal would not change the argument |
| **7. Evidence-derived implications and research agenda** | Insight: foresight, implications and future research | **+0.005–0.010** | Generic “more research is needed,” unsupported policy advice or predictions presented as findings | Every research gap must map to a missing cell in the evidence matrix: horizon, outcome, sector, population, level of analysis or identification design. Policy claims require journal evidence; otherwise label them explicitly as normative recommendations |

The combined expectation after overlap is approximately **+0.097 to +0.114**, yielding **0.535–0.552**.

## What to do with the banked artifact first

Do not start with another 65-minute composition.

### Arm A: Reflow only

Apply:

- H3 subdivision by substantive claim.
- Paragraph splitting.
- Removal of fragments.
- Removal of “also mirrored.”
- Collapse duplicate copies of the same paper.
- Reordering within existing thematic sections.

No factual sentence is rewritten.

Expected result: **0.452–0.462**. If the k=5 paired gain is below **+0.0094**, the structural association did not causally transfer to POLARIS; do not generalize from winner statistics.

### Arm B: Reflow plus visible source identity

For verified journal sources only, mechanically replace anonymous openings such as “one study” with verified author/journal lead-ins.

Run through the same cleaner used by RACE. This directly tests whether venue visibility changes the comparative narrative after citation deletion.

### Arm C: Reflow plus controlled synthesis

Use the current bank to construct only the relations it genuinely supports. Task 72 already contains usable contrasts:

- Large within-task productivity effects versus small aggregate effects.
- Freelance displacement versus firm-level complementarity.
- High exposure versus limited adoption.
- Skill compression versus concerns about entry-level job loss.
- Automation exposure versus realized employment outcomes.

If the engine cannot safely generate at least six meaningful adjudications from those, it is not ready for a new compose.

### Arm D: Combined report-only candidate

Combine only promoted transformations. Score k=5, then repeat with five fresh judge calls as confirmation. This estimates the ceiling of the existing bank without generation noise.

I expect that ceiling to be **0.49–0.51**. If it exceeds 0.52, the source-bank problem is smaller than the artifact suggests; if it stays below 0.49, retrieval quality is the dominant residual.

## The new evidence-bank build

The retrieval objective must change from “find more relevant facts” to “fill adjudicable evidence cells.”

For every major question, retrieve:

1. A grounded mechanism or framework.
2. At least two outcome studies.
3. A conflicting or scope-different result where one exists.
4. Study-design information.
5. An explicit limitation.
6. A second level of observation where relevant: worker, task, firm, industry, region or national labor market.

A task-72 stopping matrix should look approximately like this:

| Evidence block | Minimum readiness condition |
|---|---|
| 4IR and theoretical mechanisms | Two or more journal frameworks plus at least one critical alternative |
| Employment and displacement | Multiple levels of observation; both displacement and null/complementarity evidence |
| Skills and task transformation | Exposure evidence plus realized task or hiring evidence |
| Wages, productivity and inequality | Separate outcomes rather than treating productivity as a wage proxy |
| Job quality and control | At least two empirical journal sources |
| Industries | Five strong sectors; two independent sources each |
| Institutional mediation | Cross-country, firm or platform contrasts with explicit institutional evidence |
| Synthesis | At least three genuine convergence/contrast packets |
| Future agenda | At least five gaps derived from the matrix, not generic prose |

Do not compose until this matrix passes.

## Target report shape

A suitable task-72 architecture is:

1. Scope, definitions and journal-selection method.
2. AI and 4IR mechanisms.
3. How exposure, adoption and realized outcomes are measured.
4. Employment, task and skill restructuring.
5. Wages, productivity, inequality and labor share.
6. Industry pathways.
7. Job quality, control and institutional mediation.
8. Critical synthesis: established findings, scope-dependent findings, contested claims and unresolved questions.
9. Implications and research agenda.
10. Compact conclusion.

Use roughly 30–40 H3 subsections as a sanity range, not an optimization target. Each subsection should answer one research question. Most evidence paragraphs should be 50–100 words, but completeness of the evidence unit takes priority.

Likely final length: **5,000–7,000 cleaned words**. That is an outcome, not a gate.

## Content that should disappear

Remove unless a journal article makes it directly necessary:

- AI spending forecasts.
- Vendor market sizes.
- WEF job projections.
- Goldman Sachs forecasts.
- Stock-portfolio performance.
- Resume-industry surveys.
- Content-marketing statistics.
- Foundation-model leaderboard spreads.
- AI literature-review rejection commentary.
- Existential-risk digressions.
- Repeated figures from mirrored versions of one paper.

Padding removal previously scored flat, so pruning is not itself a lever. It is necessary to stop weak material from consuming attention after stronger architecture and synthesis are installed.

## Measurement protocol

### Report-to-report transforms

Because generation noise is zero:

- Use k=5 paired evaluations.
- Pre-register the artifact hashes and transformation.
- Promote only if mean gain is at least **+0.0094**.
- Also require at least four of five paired differences to be positive.
- Confirm the final combined transform with five fresh calls.

### New composition

Prefer deterministic final assembly from a fixed evidence bank. If the composer remains stochastic:

- Generate at least five independent reports.
- Score every report, rather than scoring one report five times.
- Model artifact and judge variance separately.
- Against the fixed baseline, require about **+0.017** before treating the configuration gain as resolved.
- Do not select the best of five; compare configuration means.

### Release gates

Do not ship based only on overall score. Require approximate dimension floors:

| Dimension | Current | Target |
|---|---:|---:|
| Comprehensiveness | 0.4549 | **0.535–0.550** |
| Insight | 0.4238 | **0.535–0.555** |
| Instruction-following | 0.4409 | **0.525–0.545** |
| Readability | 0.3774 | **0.500–0.525** |

Those targets imply roughly **0.54–0.55 overall** under your task-weight decomposition.

Because the detectable effect is ±0.0094 at two sigma, a measured mean of 0.544 does not establish that POLARIS beats bodhi. A defensible “top of task 72” release target is approximately **0.554**, whose two-sigma lower bound is near 0.544.

## What not to optimize

Do not spend another cycle on:

- Word count.
- Executive summaries.
- Bullet density.
- Table count.
- Bibliography formatting for RACE.
- Citation-marker style.
- More hedging.
- More isolated factual depth.
- A universal 40-H3 template across all genres.

The benchmark’s official documentation confirms that RACE evaluates dynamically generated task-specific criteria rather than fixed surface metrics. [Benchmark documentation](https://github.com/Ayanami0730/deep_research_bench#evaluation-framework)

## Ceiling and residual

There are three ceilings:

1. **Reflowed current report: 0.46–0.48.**
2. **Current evidence bank plus controlled synthesis: 0.49–0.51.**
3. **New journal-only bank plus adjudication architecture: 0.535–0.552**, with about **0.56** as a stretch.

If the full system stops near 0.53, the likely residual will not be readability. It will be:

- Insufficient directly grounded mechanisms.
- Too few comparable cross-source evidence packets.
- Weak study-design and limitation extraction.
- Industry coverage that remains descriptive.
- An adjudication renderer that is safe but not intellectually decisive.

The core bet is therefore not “make POLARIS prettier.” It is:

> Preserve the fact verifier, but move reasoning outside the single-span entailment gate into a deterministic, typed relation layer whose only freedom is to adjudicate verified evidence.

That is the path that preserves the moat and attacks the 64% of the score that actually determines whether POLARIS can win.