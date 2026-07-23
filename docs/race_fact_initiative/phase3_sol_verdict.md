/home/polaris/wt/faithoff/docs/race_fact_initiative/SCORING_SPEC.md | lines=245 | FIRST:"# SCORING_SPEC — RACE + FACT — LOSSLESS consolidation of Sol + Fable (Phase 1)" | MID(line 123):"(named-author/journal attribution); verification limited/run-dependent." | LAST:"replication (±0.027 noise, single-call judge)."
/home/polaris/wt/faithoff/docs/race_fact_initiative/phase1_sol_verdict.md | lines=462 | FIRST:"# Phase 1 Investigator Verdict: Definitive Map of DeepResearch Bench RACE + FACT Scoring" | MID(line 231):"### A6.5 Dataset-level leaderboard aggregation" | LAST:"The highest-leverage scoreable surfaces are: **(1)** task-specific Insight—causal/mechanistic analysis, cross-source synthesis, logical integration, uncertainty, and novel implications—because Insight averages 35.2% of RACE weight and reaches 42%; **(2)** Comprehensiveness—complete coverage of every requested dimension/entity/industry/time scope with representative evidence—because it averages 29.2%; **(3)** exact Instruction Following, especially source/type/language/output constraints, because omissions receive separate criteria and can carry up to 45% within that dimension; **(4)** clear structure and synthesis-oriented readability, usually lower-weight but as high as 25% for audience/data-presentation-heavy tasks; and **(5)** FACT’s independent supported-pair surface: inline, extractable, reachable citations attached to atomic claims, with more unique supported statement–URL pairs raising effective citations and unsupported pairs lowering code precision. For task 72, the four largest coefficients are mechanistic labor-market analysis (0.0800), critical cross-industry synthesis (0.0800), restructuring-dimension breadth (0.0725), and industry breadth (0.0725), so fixes that deepen mechanisms and synthesis while closing missing sector/effect coverage have the largest grounded RACE headroom (`criteria.jsonl:72`); citation-count work cannot substitute for those RACE surfaces because FACT is calculated separately (`run_benchmark.sh:35-95`)."
/home/polaris/wt/faithoff/docs/race_fact_initiative/phase1_fable_verdict.md | lines=472 | FIRST:"# Phase 1 Verdict — RACE + FACT scoring map (investigator: Fable)" | MID(line 236):"  criterion; the reported quantity is target/(target+reference) (A.5 step 4-5)." | LAST:"(`stat.py:26-30`)."
/home/polaris/wt/faithoff/docs/race_fact_initiative/COMPETITOR_TEARDOWN.md | lines=424 | FIRST:"# COMPETITOR_TEARDOWN — Phase 2, LOSSLESS consolidation of Sol + Fable" | MID(line 212):"  (":98 'unit labels...not directly comparable' ×7 consecutively, again :148/:152/:170"), empty section bodies (:84-85), citation-" | LAST:"SYNTHESIS with per-paragraph deductions — the exact substance Phase 3 must turn into wired, small-test-proven, generalized fixes."
/home/polaris/wt/faithoff/docs/race_fact_initiative/phase2_sol_verdict.md | lines=1147 | FIRST:"## INGESTION RECEIPT" | MID(line 574):"## 4. Local named competitor outputs" | LAST:"**Definitive Phase-2 conclusion:** the bar is not the reference's word count. The bar is a report whose coverage plan is complete, whose claims are built from faithful evidence baskets, whose reasoning exposes mechanisms and moderators, whose sectors are compared through a shared causal schema, whose disagreements are resolved by level/method/time/institution, whose novel insights are epistemically labeled, whose policy follows from diagnosed levers, and whose paragraphs/tables make every inference inspectable. The frozen reference already does much of this; current cellcog and WhaleCloud sharpen epistemic novelty and comparative matrices; Qianfan and ZTE show how recursive/rubric-guided research produces enormous coverage; and POLARIS's immediate visible gap is converting abundant evidence into readable, source-compliant, matrixed, cross-sector causal synthesis."
/home/polaris/wt/faithoff/docs/race_fact_initiative/phase2_fable_verdict.md | lines=272 | FIRST:"# Phase 2 Verdict — Reference + Top-Scorer Teardown, Per-Sub-Item Win Map (investigator: Fable)" | MID(line 136):"**The decisive read**: winners separate on Insight (Qianfan +11.5 above the 49.9 reference parity; every top-10 legacy system ≥58.5 Insight) and Comp (+7 to +9.5), while Inst (53-54) and Read (53-55) are compressed within ~1.5 points of each other. The scoreboard's dimensional spread independently confirms Phase-1's Strategic Implication #1: Insight is where the bar is beatable; Inst/Read are near-saturated. ZTE's README adds distribution data: "Every single query (100/100) scored above the expert-written reference" (github.com/Adlik/ZTE-Nebula-DeepResearch README.md) — winning is consistent, not variance-lottery." | LAST:"7. **One ranked competitor (NVIDIA, drb1 branch) openly runs a rubric-shaped Opus rewrite pass** (quantify claims, add missing entities, worked examples, named incidents, consolidated tables, micro-mechanisms, ≤20% scaffolding, +50% length cap) — direct evidence that the frontier treats RACE surfaces as an explicit editorial checklist. Our no-post-gen-edit rule means we must achieve the same surfaces pre-generation."
/home/polaris/wt/faithoff/docs/race_fact_initiative/phase2_addendum_fable_verdict.md | lines=335 | FIRST:"# PHASE-2 ADDENDUM — Fable verdict: the SKIPPED above-reference top systems" | MID(line 168):"  the literature from collapsing into either technological pessimism or optimism." Mechanism reuse is present but lighter than" | LAST:"pre-enumerate. Confirms teardown Pattern 5 by counter-example from a 51-point system."

# Phase 3 independent verdict — pipeline-to-score audit and pre-generation fix blueprint

## Verdict

POLARIS is not losing task 72 primarily because it lacks evidence or a report skeleton. The `faithoff_t72` run had 1,069 evidence rows, 329 baskets, 12 kept sections, 207 verified sentences, 147 bibliography entries, and no faithfulness-audit failure (`outputs/faithoff_t72/compose_summary.json:21-40`). It loses because the plan does not turn the question into testable analytical obligations, the relationship layer does not build context-aware propositions, and the active composer often receives neither. The result is abundant but unmatrixed evidence: strong local mechanism prose, a sector catalog, a late one-paragraph synthesis, no comparison table, invisible source-selection compliance, and retrieval debris. That diagnosis is visible in the report and matches the Phase-2 handoff (`COMPETITOR_TEARDOWN.md:300-321`).

The production path is:

`compose_agentic_report_s3gear329.py` → prompt/corpus scope → agentic outline → evidence routing and optional obligation/relation packages → either verified-compose or the LLM section writer → unchanged provenance rewrite and strict verification → verified-section assembly → references. The driver forces the facet outline, generic four-role skeleton, and quantitative synthesis directive (`scripts/compose_agentic_report_s3gear329.py:352-361`), but its richer deliverable contract is absent unless a gate artifact is explicitly supplied (`:586-627`). The ordinary call therefore sends no deliverable specification (`:630-648`). The skeleton guarantees an overview, thematic bodies, one combined synthesis/contradiction section, and a conclusion (`multi_section_generator.py:917-950`); it does not guarantee a causal spine, requested-dimension ledger, context comparison, source-selection method, or inference plan.

The protected faithfulness path is not the cause and must remain untouched. `provenance_generator.py:3714-3943` rewrites evidence spans and applies strict verification; `:4637-5252` resolves surviving provenance into citations. `clinical_generator/strict_verify.py:387-574` checks identifiers, spans, numerics, overlap, and entailment. These are claim-admission controls, not score planners. Source eligibility, analytical coverage, paragraph ownership, and comparison design must be solved upstream.

### Score and headroom evidence

The actual RACE result for record 72 is Comp **0.473252**, Insight **0.448947**, Inst **0.445537**, Read **0.398086**, Overall **0.448625** (`/home/polaris/wt/outline_agent/third_party/deep_research_bench/results/race/faithoff_t72/raw_results.jsonl:1`). The smaller `champ_ourcorpus` result is 0.392405/0.341141/0.371741/0.364048, Overall 0.367073 (`.../results/race/champ_ourcorpus/raw_results.jsonl:1`). RACE exposes only dimension scores, not criterion-level scores. I therefore use `effective weight × (1 - observed dimension score)` only as a transparent prioritization proxy, never as a fabricated per-cell result. It gives 0.04408 for each 0.080 Insight cell, 0.03819 for each 0.0725 Comp cell, and 0.03527 for the 0.064 Insight cell—exactly the required first tier.

FACT reports `total_citations: 11`, `total_valid_citations: 11`, `valid_rate: 1.0` (`/home/polaris/wt/outline_agent/third_party/deep_research_bench/results/fact/faithoff_t72_fact/fact_result.txt:1-3`). This is high measured precision but low supported-pair volume relative to 111 distinct in-prose bibliography markers and 147 bibliography entries (`outputs/faithoff_t72/compose_summary.json:30-38`). FACT and RACE are separate (`SCORING_SPEC.md:162-181`); citation volume cannot substitute for the five leading RACE cells.

## Existing levers: measured flat, and why

The replicated same-harness arms named in `scripts/run_race_max_focus.sh:20-30` show:

| arm | Comp mean | Insight mean | Inst mean | Read mean | Overall mean |
|---|---:|---:|---:|---:|---:|
| baseline, three draws | 0.499404 | 0.511538 | 0.493735 | 0.491381 | 0.500912 |
| full, three draws | 0.492177 | 0.504877 | 0.492851 | 0.492464 | 0.496597 |
| max, three draws | 0.490332 | 0.504239 | 0.487291 | 0.483853 | 0.493327 |

The max-minus-baseline changes are −0.00730 Insight, −0.00753 Read, and −0.00759 Overall: all inside the documented ±0.027 single-judge noise (`SCORING_SPEC.md:245`) and not directionally favorable. The individual records are `.../results/race/mf_{baseline,full,max}_draw_{1,2,3}/raw_results.jsonl:1`.

This is not evidence that mechanisms, relations, coverage, or readable structure are bad ideas. It is evidence that the current implementations do not reliably cause those behaviors:

* `coverage_obligations.audit_fulfillment` declares an obligation fulfilled when its bound section merely has any nonempty `verified_text`; it never looks for the obligated concept or proposition (`coverage_obligations.py:139-158`). The max telemetry therefore calls “Effects ... across various industries” fulfilled solely because it was bound to “Economic Consequences...” (`outputs/race_max_focus/mf_max-20260723T114236Z/draw_1/compose_summary.json:11269-11300`).
* Contradiction mining retains only confident, directly comparable conflicts (`contradiction_mining.py:123-183`). It throws away compatible convergence and non-comparability—the two relations most useful for synthesis. All three max runs detected zero contradictions; draw 1 records zero at `compose_summary.json:11410-11411`.
* Relation packs preserve existing section membership and group by a declared proposition identifier or sorted token bag; source attributes cover design, population, measure, basis, and period but not a discovered cross-context schema (`relation_evidence_packs.py:56-85,121-187`). Only a title/focus lexically recognized as synthesis receives the global map (`:190-205`).
* The relation pack and global map enter `_call_section`, but the active verified-compose primary branch constructs `raw` through `_compose_section_per_basket`; `_call_section` is only the `else` branch (`multi_section_generator.py:6630-6728`). Thus a correct prompt addendum can still miss the prose producer.
* Rich structure and paragraph markers compete. `PG_SECTION_STRUCTURE` wins over the default block-preserving path (`multi_section_generator.py:3729-3740`). The max report has `### Guiding Questions...` and several later subheads embedded on physical line 7, directly violating the writer rule that a subheading occupy its own line (`:3581-3585`). Baseline reports had more, shorter prose blocks than full/max; structure was prompted, not preserved as a producer-level object.
* The max arm is not a faithfulness-eligible candidate: its telemetry has strict verification off and entailment off (`compose_summary.json:11401-11407`). I use it only to diagnose wiring and RACE response, never as a proposed production configuration.

## Gap register

Each numbered block below is one complete gap row.

### G1 — A causal mechanism rule exists, but no mechanism obligation exists

**GAP.** The outliner tells itself not to invent mechanisms or comparisons merely because they are analytically interesting; only a concrete aspect explicitly asked by the research question justifies expansion (`outline_agent.py:1324-1331,1447-1458`). The writer's causal rule is conditional—“When the current section concerns a mechanism”—and therefore cannot create a missing mechanism section (`multi_section_generator.py:3532-3540`). In `faithoff_t72` article line 11, the task-based displacement/productivity/reinstatement chain is strong, but the later evidence is not systematically returned to that chain. In `champ_ourcorpus` article line 7, the mechanism spine is only “substitution” versus “complementary effects,” followed by an unrelated model-fit statistic.

**SUB-ITEM LOST.** #7 mechanisms, **0.0800**, the joint-largest task cell; secondarily #9 integration, 0.0480, and #11 implications, 0.0480 (`SCORING_SPEC.md:110-112`). The observed Insight scores—0.448947 and 0.341141—leave material headroom. The issue is not absence of all mechanism prose; it is failure to make mechanism the reusable report architecture.

**WINNER MOVE.** Put the mechanism framework before evidence, specify forces and a net condition, reuse it through the report, and end mechanism paragraphs with a derived implication (`COMPETITOR_TEARDOWN.md:221-224,274-280`).

**FIX (generalized, pre-generation).** Before outlining, compile analytical obligations from the semantic operator in the question. When a question asks how, why, impact, change, or causation, require evidence-backed causal chains with fields for conditions, process, intermediate outcome, final outcome, moderators, and the condition governing the net direction. Attach each chain to the evidence baskets that support its individual links and assign it as a reusable lens to relevant sections. If the evidence supports only part of a chain, plan the boundary rather than completing it. This is general because it reacts to question semantics and evidence relations, not this task, a domain vocabulary, or a fixed section menu.

**SMALL TEST.** Feed the planner a causal fixture, a descriptive fixture, and evidence with one deliberately missing link. Deterministically assert that causal obligations and supported link ownership appear only for the causal fixture, and that the missing link becomes a boundary. Compose short sections from frozen baskets through the active producer; assert that the same mechanism identifiers govern the theory, comparison, and implication plans without leaking identifiers into prose. Then run a same-judge paired RACE probe on a power-selected set of frozen reports; require every paired direction positive and the mean Insight change greater than 0.027.

### G2 — Cross-study synthesis is a late writing request, not a precomputed relation plan

**GAP.** The generic skeleton allocates exactly one combined synthesis-and-contradictions section (`multi_section_generator.py:944-950`). In the real outline, that section received only 17 evidence IDs while “Additional Corroborated Findings” received 433 (`outputs/faithoff_t72/multi_section_outline.json`, section records 10 and 12). `faithoff_t72` article line 43 contains a valuable reconciliation of task/occupation, exposure/realized impact, local-market/firm, and country results, but compresses all of it into one wall paragraph. Contradiction mining detects only direct conflict and returned zero; relation packs do not change membership and can miss verified-compose.

**SUB-ITEM LOST.** #8 critical cross-industry synthesis, **0.0800**; it also depresses #22 sourced synthesis, 0.0210, and #5 literature depth/appraisal, 0.0435 (`SCORING_SPEC.md:108,110-112,116-120`). Measured max Insight was flat relative to baseline, proving the present levers did not contribute beyond noise.

**WINNER MOVE.** State a reconciliation thesis, extract cross-context patterns, and explain disagreement through unit, margin, technology, horizon, method, and institutional setting; do not merely announce conflict (`COMPETITOR_TEARDOWN.md:223-225,277-280`).

**FIX (generalized, pre-generation).** Build an evidence-relation graph before prose. For every potentially related claim basket, represent the proposition, direction, outcome measure, unit of analysis, observation versus projection, method, period, population, and evidence-derived context attributes. Preserve three useful edge types: convergence, qualified divergence, and non-comparability. Generate planned synthesis propositions only when their cited nodes license the relation, including the moderator or measurement difference that explains it. Route these planned propositions and their exact source sets into the active verified-compose producer, not merely an optional writer prompt.

**SMALL TEST.** Use frozen rows containing a genuine same-measure conflict, compatible findings at different margins, and unrelated findings. Assert the graph produces the correct three relation states; the synthesis plan must cite both sides and name the differentiating attribute, while the unrelated pair produces no claim. Compose a miniature report through verified-compose and assert at least one cross-source proposition survives strict verification. On fixed reports, pair the same judge and require an Insight gain beyond 0.027 without a FACT precision regression.

### G3 — Requested breadth is represented by concepts, not decomposed outcome dimensions

**GAP.** The outliner stops when its current gap ledger is empty and treats only named missing aspects as searchable (`outline_agent.py:1309-1332`). Coverage obligations append a concept to the nearest section focus (`coverage_obligations.py:107-136`) and their audit tests only whether that section contains any text (`:139-158`). The real report covers job creation, displacement, tasks, skills, wages, productivity, inequality, and geography, but has no dimension ledger proving complete coverage or connecting them. The max audit's “missing: []” is therefore not evidence of semantic completion.

**SUB-ITEM LOST.** #2 breadth of restructuring dimensions, **0.0725** (`SCORING_SPEC.md:106-109`). The relevant Comp score is 0.473252; raw length did not secure the cell.

**WINNER MOVE.** Operationalize the requested abstract outcome before writing and keep a coverage ledger in which each evidence-derived dimension has evidence, a home, cross-links, and an honest gap status (`COMPETITOR_TEARDOWN.md:225-227,281-283`).

**FIX (generalized, pre-generation).** Convert each broad requested outcome into evidence-derived dimensions using the task wording, retrieved controlled terms, reported endpoints, and recurring distinctions. Each dimension must have a status: supported with evidence and a planned analytical move, retrieval-needed, or unsupported/disclosed. Fulfillment must be semantic: the planned and emitted proposition must entail the dimension-role pair, not merely occupy a bound section. The rule works for any broad outcome because the dimensions are induced from the question and evidence rather than supplied as a domain list.

**SMALL TEST.** Construct prompts whose broad outcomes decompose differently and a section that is nonempty but omits one required dimension. Assert that the current audit would pass the decoy but the new audit fails it, then passes only after a source-bound proposition covering the dimension is planned and emitted. Use a fixed-report paired Comp probe and require a mean change beyond 0.027.

### G4 — Industries are cataloged, not selected and compared as distinct regimes

**GAP.** `faithoff_t72` article line 35 is one enormous sequence of occupation and sector examples. It has breadth by name but no common fields for mechanism, adoption, outcome, institution, affected party, or evidence strength. The outline assigns 93 evidence IDs to one “Industry and Occupational Case Studies” section and gives it only a generic case-study focus. The max coverage audit binds “various industries” to an economic-consequences section and calls it fulfilled (`compose_summary.json:11292-11300`).

**SUB-ITEM LOST.** #3 industry-specific scope, **0.0725**, and #16 various industries, 0.0375; it is also the context basis of #8 synthesis, 0.0800 (`SCORING_SPEC.md:107,110-115`).

**WINNER MOVE.** Span materially different task and institutional regimes, compare them through a shared schema, and make sector variation an organizing axis rather than a list (`COMPETITOR_TEARDOWN.md:228-240`).

**FIX (generalized, pre-generation).** Infer context attributes from admitted evidence, cluster contexts by materially different mechanisms, institutions, adoption conditions, and outcome margins, and choose coverage for analytical diversity rather than name count. Build a common-schema comparison plan from dimensions genuinely shared by the selected contexts; assign both context-specific findings and a cross-context proposition. This generalizes to regions, populations, jurisdictions, or technologies because “context” and the schema are discovered from evidence metadata and claims.

**SMALL TEST.** Supply baskets from several named contexts, including near-synonyms and genuinely different regimes. Assert that synonym proliferation does not satisfy diversity, every selected context has source support, the common-schema plan contains only shared dimensions, and the synthesis proposition uses evidence from multiple distinct regimes. A same-judge paired probe must improve both Comp and Insight beyond noise.

### G5 — No pre-generation induction and epistemic labeling of emergent themes

**GAP.** The report has no explicit distinction among source-reported findings, cross-source deductions, and hypotheses. `faithoff_t72` article line 43 makes several deductions, but their epistemic status and discriminating test are not labeled. `COMPETITOR_TEARDOWN.md:310-311` records the same defect. Neither contradiction mining nor relation packing induces a new, falsifiable relationship from independent baskets.

**SUB-ITEM LOST.** #10 emergent themes/linkages/novel perspectives, **0.0640** (`SCORING_SPEC.md:111-112`).

**WINNER MOVE.** Derive a new falsifiable relationship from multiple baskets, label its epistemic status, and state the missing observation that would discriminate it (`COMPETITOR_TEARDOWN.md:229-230,295-296`).

**FIX (generalized, pre-generation).** Add an inference planner over the evidence-relation graph. A candidate inference must identify independent supporting baskets, the reasoning operator connecting them, boundary conditions, an epistemic category distinguishing reported from synthesis-derived content, and an observable result that would weaken it. Only the source-supported premises enter strict verification; the inference is calibrated to those premises and planned before writing. This is topic-independent formal reasoning over provenance topology.

**SMALL TEST.** Provide two independent baskets that jointly license a conditional relationship, one basket alone, and a confounded counterexample. Assert that only the joint case creates a synthesis-derived proposition, that it retains both premise citations and a falsifier, and that the confounded case is labeled unresolved. Probe #10 with fixed paired reports and require a change beyond 0.027.

### G6 — The central task concept is introduced, not used as an explanatory variable

**GAP.** The report defines the Fourth Industrial Revolution in article line 7, then mostly uses it as framing. Coverage spine is default-off (`config_defaults.py:920`), and the max obligation binds “AI as a key driver...” to the conclusion rather than enforcing explanatory roles across the report (`compose_summary.json:11278-11284`). The generic skeleton cannot distinguish a required central concept from ordinary background.

**SUB-ITEM LOST.** #1 4IR grounding, 0.0290; #9 4IR integration, 0.0480; #14 4IR-driver theme, 0.0375 (`SCORING_SPEC.md:106,111-115`).

**WINNER MOVE.** Define and historically contrast the central concept, then use its supported properties to explain pace, breadth, redesign, and institutional pressure (`COMPETITOR_TEARDOWN.md:232-243`).

**FIX (generalized, pre-generation).** For every concept the prompt designates as a driver, lens, or organizing theme, create a concept-role spine: definition, contrast, mechanism role, context-variation role, and implication role, but instantiate only roles supported by evidence. An intro mention cannot fulfill downstream roles. This is general because roles come from the semantic relation between prompt concepts, not from any named concept.

**SMALL TEST.** Use a task with a designated driver and one with a merely mentioned background term. Assert that only the driver receives a role spine and that an intro-only report fails the semantic audit. Compose frozen evidence and verify that non-intro planned propositions use the concept as an explanatory variable, then run a paired RACE probe.

### G7 — Exposure, adoption, productivity, and realized outcomes are not governed by a shared measurement ontology

**GAP.** The writer does ask for scope disambiguation (`multi_section_generator.py:3529-3530,3562-3568`), and `faithoff_t72` article line 43 does distinguish some measures. But there is no report-wide pre-generation ontology preventing an exposure score, an experiment, a forecast, a firm association, and a labor-market outcome from being treated as one disruption scale. Benefits and harms are also scattered rather than conditioned on stakeholder and horizon.

**SUB-ITEM LOST.** #4 disruptive character and scale, 0.0435; #6 balanced impacts, 0.0290; #15 significant disruption, 0.0375 (`SCORING_SPEC.md:107-115`).

**WINNER MOVE.** Treat exposure, observed task productivity, diffusion, and realized employment/wage outcomes as different quantities; balance effects by affected party and time horizon (`COMPETITOR_TEARDOWN.md:235-242`).

**FIX (generalized, pre-generation).** Induce a measurement ontology from evidence fields and claim text: construct, unit, observed/modelled/forecast status, margin, population, period, and affected party. Permit aggregation or net-direction claims only for compatible measurements. Build an effect ledger that preserves benefits, harms, distribution, horizon, and uncertainty without forcing artificial balance where evidence is one-sided.

**SMALL TEST.** Mix exposure percentages, experimental productivity effects, forecasts, and observed employment changes. Assert that the planner refuses a common aggregate, preserves labels and units, and produces stakeholder/horizon comparisons only where licensed. A negative fixture with one-sided evidence must disclose asymmetry, not invent a counterclaim.

### G8 — Implications are recommendations appended to evidence, not consequences of diagnosed levers

**GAP.** `faithoff_t72` article line 39 contains substantive policy material, but much of it serially inventories institutions and programs. `champ_ourcorpus` article line 35 offers generic investment/collaboration prescriptions. No plan object links an implication to a specific mechanism, context, trade-off, evidence strength, and observable result.

**SUB-ITEM LOST.** #11 implications and future agendas, 0.0480 (`SCORING_SPEC.md:111-112`).

**WINNER MOVE.** Every recommendation identifies the mechanism changed, population, trade-off, evidence strength, and testable outcome (`COMPETITOR_TEARDOWN.md:233-234`).

**FIX (generalized, pre-generation).** Derive implication objects from already planned mechanism and synthesis propositions. Each must point to the diagnosed lever, affected context or population, expected direction, trade-off, evidence grade, and observation that would test it. Reject generic recommendations with no upstream proposition. This applies to policy, practice, and research agendas in any field.

**SMALL TEST.** Give the planner evidence-backed and generic recommendation candidates. Assert that only the former is admitted and every implication has valid upstream proposition IDs plus a predicted observable outcome. Compose a short conclusion and test #11 with paired fixed reports beyond the noise band.

### G9 — Exclusive source constraints are only partially enforced and are invisible in judged prose

**GAP.** The driver writes source-selection telemetry to `methods.md`, explicitly “NOT part of the judged report” (`compose_agentic_report_s3gear329.py:776-810`). RACE strips the bibliography, so #17/#18 require in-prose evidence (`SCORING_SPEC.md:121-123`). The base report's article line 55 self-discloses only 4% T1, 1% T2, and 25% unknown, while lines 7-51 cite working papers, organizational reports, websites, and pasted pages. The max report explicitly names an NBER working paper, journalism, grey literature, and an IEEE conference paper on article line 7; its references include arXiv, ResearchGate, industry, and institutional material (`outputs/race_max_focus/.../draw_1/report.md:7,69-98`).

The scope contract correctly excludes definitive wrong type and unresolved type under an explicit exclusive constraint (`scope_contract.py:152-177`), but its admission function consumes source types and languages only (`:223-262`). Extracted `quality_attributes` are not checked there. In the base compose summary, the prebuilt corpus was not scope-evaluated and compliance is null (`outputs/faithoff_t72/compose_summary.json:41-42`).

**SUB-ITEM LOST.** #17 only high-quality journals, 0.0375; #18 English-only, 0.0250; #5 representative literature depth, 0.0435; #12 literature-review form, 0.0250 (`SCORING_SPEC.md:108,113-115`). The reports are English and I found no confirmed non-English article, so #18 is an unproven visibility/compliance risk, not a claimed observed violation. #17 is directly violated.

**WINNER MOVE.** Enforce source type at retrieval, carry an auditable selection method, and state source policy, named author/year/journal, and exclusions in prose because bibliography prestige is invisible to RACE (`COMPETITOR_TEARDOWN.md:236-245,286-287`).

**FIX (generalized, pre-generation).** Compile every exclusive source, language, date, and quality constraint into an admission contract before outlining. A load-bearing row must have definitive eligible type and language plus evidence-based quality status (publication provenance, peer-review status, correction/retraction state where available, venue identity, and design transparency); unknown eligibility becomes a retrieval target or disclosed evidence gap, never body evidence. Generate a reader-facing selection statement from the actual admission ledger and plan it into the introduction/method section. No venue whitelist or domain literal is required.

**SMALL TEST.** Use a mixed-metadata corpus with eligible, wrong-type, wrong-language, unknown, retracted, and unverified-quality rows. Deterministically assert partition completeness, no inadmissible row in any section plan, and explicit exercise of the quality rule. Compose a miniature review and assert that the cleaned body truthfully names its selection policy and contains no inadmissible load-bearing attribution. Pair the Inst judge and require a gain beyond 0.027.

### G10 — Paragraph and heading structure is advisory text that the active producer does not preserve

**GAP.** `faithoff_t72` has 14 prose paragraphs with 608.5-word median and 838-word maximum according to the Phase-2 forensic measurement (`COMPETITOR_TEARDOWN.md:301-307`). Article lines 11, 35, and 43 each contain multiple analytical moves in one wall. Article lines 27 and 47 begin mid-word, and line 51 begins with a pasted page header (`:308-310`). The current writer asks for paragraphs of about 3–6 sentences (`multi_section_generator.py:3581-3585`) and the marker path materializes writer-authored breaks (`:3670-3707,6748-6750`), but verified-compose constructs units separately and joins them; rich structure can put subheads inline. The full/max Read arms were flat or worse.

**SUB-ITEM LOST.** #19 language 0.0280, #20 structure 0.0280, #21 cohesion 0.0210, #22 synthesis clarity 0.0210, #24 layout 0.0140, and #25 audience 0.0140 (`SCORING_SPEC.md:116-120`).

**WINNER MOVE.** One inferential move per paragraph; transitions encode the actual relation; stable heading depth; definition → intuition/example → limitation; no raw retrieval fragments (`COMPETITOR_TEARDOWN.md:242-251`).

**FIX (generalized, pre-generation).** Make paragraph blocks first-class plan objects. Each block owns one reader question and one analytical movement—claim, evidence/appraisal, relation or implication—with an explicit transition relation to adjacent blocks. The active producer emits verified sentences into those block containers, and the renderer preserves container boundaries and heading nodes exactly. This is not a post-generation edit: structure exists before generation and is carried through verification. Add pre-composition input sanitation that prevents navigation text, cut fragments, and page boilerplate from becoming evidence spans.

**SMALL TEST.** Create a section plan with multiple analytical moves and unique block IDs. Assert one-to-one survival of block boundaries through compose, provenance rewrite, strict verification, and render; assert headings occupy their own physical lines and no input-fragment sentinel appears. Compare deterministic block/heading metrics before and after, then use same-judge paired Read reports with a mean change beyond 0.027.

### G11 — Tables are post-hoc or writer-optional, not evidence-shaped plans

**GAP.** Both task-72 reports contain no Markdown table (`COMPETITOR_TEARDOWN.md:303-308,317`). The base writer permits a table only conditionally (`multi_section_generator.py:3597-3602`), while `PG_SUMMARY_TABLE_COMPOSE` inserts a table after the verified report is assembled (`compose_agentic_report_s3gear329.py:746-761`), which is forbidden by this initiative's pre-generation-only rule. The max table at `report.md:41-44` merely repeats two facts and values; it is not the shared sector/mechanism/evidence-strength matrix needed for #8.

**SUB-ITEM LOST.** #23 data/evidence clarity, 0.0140, #24 layout, 0.0140; materially supports #3 industry breadth and #8 synthesis (`SCORING_SPEC.md:107,110-120`).

**WINNER MOVE.** Use a table only for genuinely shared dimensions and follow it with interpretation; include methods/limitations where analytically useful (`COMPETITOR_TEARDOWN.md:248-250,285-286`).

**FIX (generalized, pre-generation).** When the relation planner finds multiple contexts or studies sharing meaningful dimensions, create a table plan before writing: row entities, shared columns, cell-level source ownership, units, missingness, and the interpretive proposition the table supports. If dimensions are not comparable, plan prose instead. Generate and verify each cell as an ordinary evidence-bound unit. The present post-assembly table constructor is not reusable as-is.

**SMALL TEST.** Provide comparable and non-comparable evidence fixtures. Assert a table plan only for the former, exact column consistency, source ownership for every factual cell, preserved units, and a planned interpretation block after the table. Run it through the ordinary verifier and renderer; no post-generation insertion is allowed.

### G12 — Route-all creates a miscellaneous evidence dump and allows low-contribution text into the body

**GAP.** The base outline's last section is literally “Additional Corroborated Findings” with 433 evidence IDs and the same phrase as its focus (`outputs/faithoff_t72/compose_summary.json:18-20`; `multi_section_outline.json`, section 12). This contradicts the current composition rule “Do not create an additional, miscellaneous, residual, or corroborated-findings section” (`multi_section_generator.py:3593-3595`), showing that prompt advice cannot repair upstream routing. Article line 31 contains raw blog phrasing; lines 47 and 51 contain broken retrieval artifacts. More evidence became more prose without a marginal-contribution test.

**SUB-ITEM LOST.** #13 on-topic focus, 0.0500; #19 language, 0.0280; #22 synthesis rather than serial summary, 0.0210; #24 layout, 0.0140 (`SCORING_SPEC.md:113-120`).

**WINNER MOVE.** Every added section adds a new analytical layer; off-topic evidence is removed at retrieval and composition, and repeated/corroborating sources are synthesized in the owning claim rather than dumped (`COMPETITOR_TEARDOWN.md:231-232,289-298`).

**FIX (generalized, pre-generation).** Before body routing, require each basket to declare a marginal contribution to a supported coverage obligation, relation, method appraisal, limitation, or implication. Merge corroboration into its owning proposition. Evidence without a body contribution remains archived for bibliography/audit and can trigger a gap, but does not force prose. Sanitize candidate spans for fragment boundaries and page-navigation signatures before they become admissible claims. This is a general ownership rule, not evidence deletion or a topic-specific filter.

**SMALL TEST.** Use duplicate, corroborating, off-topic, boilerplate, and novel baskets. Assert every emitted block has one valid analytical owner, corroborators join the existing proposition, the novel basket adds a planned move, and the rest stays out of body while remaining archived. The report must contain no residual-section role.

### G13 — FACT precision is strong, but the claim-to-URL plan yields too few extractable supported pairs

**GAP.** FACT finds only 11 supported pairs despite 111 distinct prose markers and 147 bibliography entries. The benchmark extracts four inline forms, returns nothing for bibliography-only sources, deduplicates by URL, and counts supported statement–URL pairs (`SCORING_SPEC.md:168-181`). The current pipeline optimizes strict internal provenance, but does not preflight the external extractor's complete proposition, canonical URL, inline location, and dedup identity as one plan object. Two AEA destinations in the validated artifact were unavailable to scraping and excluded as unknown, illustrating URL volatility.

**SUB-ITEM LOST.** FACT #40–#52: immediate atomic citation, extractable form, complete fact frame, reachable URL, exact support, avoidance of unsupported and duplicate pairs, supported-pair volume, multi-source/multi-fact behavior, and separation from RACE (`COMPETITOR_TEARDOWN.md:253-271`). The direct observed signal is E.Cit=11 with C.Acc micro=1.0.

**WINNER MOVE.** Attach a reachable real URL immediately after the smallest complete proposition, keep each source-specific proposition atomic, and widen unique supported pairs without sacrificing precision (`COMPETITOR_TEARDOWN.md:256-268`).

**FIX (generalized, pre-generation).** Extend the claim plan—not strict verification—with an external-citation contract: atomic proposition frame, exact supporting span, canonical reachable URL, inline marker mapping, and expected dedup key. A multi-source sentence is allowed only when each source supports the same complete atomic proposition; distinct source-specific facts become distinct planned units. Preflight reachability and extractor compatibility before generation, while retaining the stricter internal faithfulness gate.

**SMALL TEST.** Generate a small report from frozen evidence and its pre-generation claim plan, then run the benchmark extractor/deduper/support validator locally. Assert every planned eligible pair is extracted once, every extracted proposition is complete, E.Cit rises materially above the present 11-pair baseline on the same evidence subset, and the lower confidence bound for C.Acc is non-inferior to 1.0 within evaluator resolution. No existing report is rewritten.

## Complete scored-surface disposition

| scored surface | observed disposition | controlling gap |
|---|---|---|
| Comp #1 4IR grounding .0290 | definition present; historical/explanatory reuse incomplete | G6 |
| Comp #2 restructuring breadth .0725 | many dimensions present; no semantic ledger or completeness proof | G3 |
| Comp #3 industry scope .0725 | many names; no regime diversity or common schema | G4 |
| Comp #4 disruption scale .0435 | unlike measures are discussed but not governed report-wide | G7 |
| Comp #5 literature depth .0435 | large corpus; methods/source quality not reader-visible or compliant | G2, G9 |
| Comp #6 balanced impacts .0290 | both signs present; no stakeholder/horizon effect ledger | G7 |
| Insight #7 mechanisms .0800 | strong isolated base-run section; not a reusable plan spine | G1 |
| Insight #8 cross-industry synthesis .0800 | late/compressed paragraph; no context-aware relation graph | G2, G4 |
| Insight #9 4IR integration .0480 | framing label more than explanatory variable | G6 |
| Insight #10 emergent themes .0640 | deductions not epistemically labeled or falsified | G5 |
| Insight #11 implications .0480 | recommendations not linked to diagnosed levers/tests | G8 |
| Inst #12 literature-review form .0250 | thematic shell present; selection method absent from judged body | G9 |
| Inst #13 focus .0500 | residual dump and retrieval artifacts violate focus | G12 |
| Inst #14 driver theme .0375 | named centrally but not role-audited | G6 |
| Inst #15 significant disruption .0375 | scale categories insufficiently separated | G7 |
| Inst #16 various industries .0375 | names present; analytical variation weak | G4 |
| Inst #17 journal-only .0375 | directly failed by non-journal load-bearing sources | G9 |
| Inst #18 English-only .0250 | no observed language breach; compliance statement invisible | G9 |
| Read #19 language .0280 | fragments, boilerplate, walls | G10, G12 |
| Read #20 structure .0280 | macro skeleton good; internal heading/block preservation broken | G10 |
| Read #21 cohesion .0210 | transitions hidden within long multi-move paragraphs | G10 |
| Read #22 sourced synthesis .0210 | relation plan and ownership insufficient | G2, G10, G12 |
| Read #23 data/table clarity .0140 | absent in base; max table is not comparative | G11 |
| Read #24 layout .0140 | no base tables; inline headings in max | G10, G11 |
| Read #25 audience .0140 | scholarly tone present; definitions/intuition/limits not block-planned | G10 |
| FACT #40–#52 | 11/11 supported, but low effective volume and URL/extractor fragility | G13 |

## Limits: what cannot be fixed by pre-generation content design

* RACE judge stochasticity, cleaner behavior, and the target/reference ratio are evaluator properties. They can be controlled only with same-judge pairing, frozen reports, and replication; they cannot be authored away.
* FACT page availability, Jina scraping, paywalls, and validator “unknown” exclusions are external at scoring time. Preflight and canonical URL choice reduce exposure but cannot guarantee future reachability.
* If retrieval finds no eligible evidence for a required source/type/language constraint or analytical dimension, generation cannot repair it. The pre-generation action is targeted retrieval/deepening followed by an explicit gap if evidence remains absent.
* Strict verification may remove a planned sentence whose support is inadequate. The lawful response is stronger evidence ownership or regeneration from the plan, never weakening the faithfulness engine or editing the finished report.
* Bibliography stripping is fixed RACE behavior. Compliance therefore must be truthfully stated in prose from the admission ledger; render-only bibliography changes cannot earn #17/#18.

## Prioritized Phase-4 fix list

Priority uses effective weight, the observed dimension headroom proxy stated above, demonstrated artifact severity, and cross-cell leverage.

1. **G1 mechanism obligation compiler — #7 .0800, proxy 0.04408.** Fix: derive supported causal chains from question semantics and route them as a reusable pre-outline spine. Test: causal/noncausal/missing-link fixtures plus active-producer structural assertions and paired Insight gain >0.027.
2. **G2 context-aware evidence-relation graph — #8 .0800, proxy 0.04408.** Fix: precompute convergence, qualified divergence, and non-comparability propositions and feed them to verified-compose. Test: three-relation fixture, strict-verified cross-source proposition, paired Insight gain >0.027.
3. **G3 semantic outcome-dimension ledger — #2 .0725, proxy 0.03819.** Fix: induce requested dimensions from task plus evidence and audit emitted propositions, not section existence. Test: nonempty-decoy section must fail until the missing dimension is actually emitted; paired Comp gain >0.027.
4. **G4 analytical context-diversity and comparison plan — #3 .0725, proxy 0.03819.** Fix: select materially different regimes and compare them through evidence-derived shared fields. Test: synonyms do not satisfy diversity; multi-regime proposition and paired Comp/Insight gains clear noise.
5. **G5 epistemically labeled inference planner — #10 .0640, proxy 0.03527.** Fix: induce multi-basket, bounded, falsifiable synthesis propositions before writing. Test: joint-premise positive, single-premise/confounded negatives, paired #10 gain >0.027.
6. **G6 designated-concept role spine — #9 .0480 plus #1/#14.** Fix: require supported definition, contrast, mechanism, variation, and implication roles for prompt-designated drivers. Test: intro-only mention fails; non-intro explanatory propositions pass.
7. **G8 implication derivation — #11 .0480.** Fix: admit only implications linked to a mechanism, affected context, trade-off, evidence strength, and observable outcome. Test: generic recommendation rejected; every emitted implication resolves upstream.
8. **G9 full source-eligibility contract and judged-body method — #5 .0435 plus #17/#18/#12.** Fix: enforce type, language, and evidence-based quality before routing and generate a truthful in-prose selection statement. Test: mixed eligibility partition, zero inadmissible body rows, paired Inst gain >0.027.
9. **G7 measurement/effect ontology — #4 .0435 plus #6/#15.** Fix: separate construct, margin, observation status, stakeholder, and horizon before comparison or net claims. Test: incompatible metrics cannot aggregate; one-sided evidence stays one-sided.
10. **G12 marginal-contribution routing and input sanitation — #13 .0500 plus Read.** Fix: body-route only baskets that add a supported analytical move; archive the rest and exclude fragments/boilerplate pre-compose. Test: ownership completeness, no residual section, no fragment sentinel.
11. **G10 first-class paragraph/heading blocks — Read #19/#20 and #21/#22.** Fix: plan analytical blocks and preserve them through the active producer, verification, and render. Test: one-to-one block survival, headings on their own lines, paired Read gain >0.027.
12. **G11 evidence-shaped table planning — Read #23/#24 plus #3/#8.** Fix: create cell-level cited comparison schemas before generation only when evidence shares meaningful dimensions. Test: comparable fixture yields a verified table plus interpretation; non-comparable fixture yields prose.
13. **G13 external FACT claim contract — FACT #40–#52.** Fix: plan atomic complete propositions with exact spans, reachable canonical URLs, inline mappings, and dedup identities before prose. Test: miniature end-to-end FACT extraction raises supported-pair volume above 11 while preserving measured precision; strict verification remains unchanged.

The Phase-4 architectural center should therefore be one pre-generation analytical contract shared by outline, retrieval admission, relation planning, active composition, and semantic acceptance. Adding more advisory prompt prose or more independent flags will repeat the measured-flat failure unless the contract changes evidence ownership and is consumed by the producer that actually emits verified sentences.
