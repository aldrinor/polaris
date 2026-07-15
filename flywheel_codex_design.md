# Executive decision

The strongest path is not “route more” or “require eight sources per section.” It is:

1. Enforce a work-level allowlist for high-quality, English-language journal articles.
2. Build an evidence-backed claim graph before outlining.
3. Select sources by marginal claim utility under a fixed word budget.
4. Draft claim-centered synthesis, then critique and rewrite against the claim graph.
5. Add quantitative synthesis only within explicitly compatible evidence sets.

`PG_ROUTE_ALL_BASKETS` should be off for candidate reports and retained only as a recall-audit tool. The observed 37-source peak is a useful operating prior, not a target or a proven causal optimum.

I relied only on the inline findings and excerpts.

# 1. Corrections to the findings brief

## 1. “The planner sees the full corpus” is only conditionally true

In the large-pool branch, the planner receives:

- The entire `evidence` list only when `_outline_redesign` is true.
- Otherwise `evidence[:_outline_max_ev]`.
- Only `ev_id`, tier, and title—no statement text—in either large-pool case.

The optional basket digest can replace this with claim-bearing digests, but only when `PG_OUTLINE_BASKET_DIGEST` is on and `finding_clusters` exists. Therefore “full corpus visibility” may mean visibility of 995 titles, not visibility of 995 pieces of usable evidence. That is still semantically title-starved. See Excerpt 2, `_call_outline` around 3100–3170.

Consequence: log the effective outline branch, prompt hash, row count shown, and whether statements or claim digests were actually visible.

## 2. The no-floor diagnosis is not established for task 72

The visible clinical `OUTLINE_SYSTEM_PROMPT` has no `ev_ids` floor. However, the comment immediately before `OUTLINE_SYSTEM_PROMPT_GENERIC` says that the generic version includes “`>=8 ev_ids each`”; the actual relevant portion of that generic prompt is omitted from the excerpt.

Task 72 is nonclinical, so it should probably use the generic prompt, but the excerpts do not prove which prompt was selected at runtime. See Excerpt 1.

Consequence: do not patch a presumed missing floor until the run logs `prompt_kind`, prompt hash, and effective rules. In any case, a blanket eight-ID floor is the wrong control: central-claim coverage and independent corroboration are better controls.

## 3. “95% dropped at outline selection” mixes incompatible units

The comparison uses approximately 39 `ev_ids` against approximately 840 distinct works. Those are not the same unit:

- Several evidence rows can represent one work.
- One evidence ID can appear in multiple sections.
- Baskets can expose additional members.
- Weighted enrichment, route-all, and debate augmentation operate after initial outline selection.
- Final citations are distinct report sources, not evidence-row assignments.

The exact funnel should use a stable `work_id`:

`raw rows → distinct works → eligible works → independent study families → compose baskets → selected works → cited works`.

The funnel is clearly severe, but “95% dropped here” is not yet a defensible exact attribution.

## 4. The section boundary is not fully hard

The base `_section_baskets_for_compose` does select baskets through an intersection with section-assigned `ev_ids`. However:

- Route-all mutates the section’s `ev_ids`, deliberately piercing that boundary.
- Debate consolidation explicitly adds con-baskets even when their evidence was not assigned to the section.

See Excerpt 4 around 3280–3340 and Excerpts 3/5.

The accurate statement is: direct basket selection is section-bound, but several downstream augmentation paths can enlarge it.

## 5. Route-all does not cover the whole validated pool

It covers:

- Orphan baskets present in `credibility_analysis.baskets`.
- Unassigned singleton candidates only when their tier is T1, T2, or T3.
- Only when `credibility_analysis` is non-`None`.

It does not automatically reach standalone T4 works or lower-tier rows. It also withholds confirmed all-off-topic candidates. See Excerpt 3 around 10565–10620 and Excerpt 5 around 3720–3840.

Conversely, the brief’s statement that it requires actual baskets is too strong: Excerpt 5 expressly permits routing when the basket list is empty but `singleton_candidates` is nonempty.

## 6. The route-all defaults are not contradictory

`route_all_baskets_enabled()` defaults off at the library level. A compose script can set the environment variable on by default for a particular run profile. Both statements can be true. See Excerpt 5 and the cited compose-script configuration.

The run must log the resolved value, not infer it from either default.

## 7. “Demoted off-topic” is not necessarily “deletable off-topic”

The caller uses `is_row_deletable_offtopic()`, described as requiring an affirmative off-subject disposition with relevance vetoes and fail-open uncertainty. A generic `DEMOTED(kept, disclosed)` status may not enter `_off_topic_ev_ids`.

Moreover:

- A mixed basket survives if at least one member is not confirmed off-topic.
- The compose screen is separately feature-gated.
- An already assigned row may bypass orphan-routing deletion.

This explains how obviously medical rows can survive despite a nominal off-topic mechanism. Excerpts 3–5 support the distinction.

## 8. “Keep T1–T4 in the writer menu” would violate the task

Tier is not task eligibility:

- T3 includes government/regulatory documents, which are not journal articles.
- T4 explicitly includes conference proceedings.
- T2 can contain nonjournal guidelines.
- A mislabeled or non-English T1 can still violate the task.
- Conversely, a genuinely strong peer-reviewed journal review could be usable despite a coarse T4 label.

The writer menu must be driven by a bibliographically verified task allowlist, with tier retained only as a quality prior.

## 9. Strict verification does not enforce the source restriction

Sentence-level entailment can establish that a source supports a sentence. It does not establish that the source is:

- A journal article.
- English-language.
- Peer-reviewed.
- High quality.
- On-task.
- Independent of another cited paper.
- Semantically compatible with other numbers in a calculation.

The source-eligibility firewall and numeric compatibility compiler must be separate hard gates before strict verification.

## 10. The 37-source inverted-U is not yet causal

The compared reports differ in more than source count, and the scorer itself moved one report from 0.4447 to 0.4291. Therefore the data show an empirical operating region, not a proven source-count response curve.

To establish causality, create nested 30/34/37/40/44-source sets from one ranked selection, hold the claim plan, writer, word budget, and model settings fixed, and score repeatedly.

## 11. The top-24 cap cannot yet be dismissed

If route-all produces 52–103 rows per section and a downstream path retains only 24, that cap can become an accidental, order-sensitive selector even if it did not bind in the lean run.

Log cap input IDs, retained IDs, and dropped IDs. Under the new selector, any selected evidence silently lost to a downstream cap is a hard gate failure.

## 12. The dump flag is not shown to stop composition

The findings say `PG_DUMP_ROUTED_OUTLINE` dumps before compose. Nothing in the excerpts shows an early exit. Therefore it is instrumentation, not yet a cheap outline-only execution mode.

Add a separate `PG_STOP_AFTER_ROUTED_OUTLINE=1` flag that exits successfully after validation and artifact emission.

## 13. “Never delete” needs a corpus-versus-composition distinction

The router documentation uses “DELETED” for confirmed off-topic material. To preserve §-1.3 cleanly:

- Never remove the original row from the audit corpus.
- Mark it `WITHHELD_FROM_COMPOSE`.
- Record a reason and observed evidence.
- Exclude it from outline, writer, calculations, citations, and bibliography.

That preserves disclosure without contaminating the report.

# 2. Target architecture

```text
Immutable raw corpus
├── Audit ledger: every row retained with disposition and reason
└── Work identity/deduplication
    └── Task eligibility: relevant + English + journal + peer-reviewed + quality
        └── Compose allowlist
            └── Eligible basket views + independent study/sample families
                └── Claim-evidence graph
                    ├── Targeted gap retrieval for uncovered central claims
                    └── Marginal-utility source selector
                        └── Claim-based section plan
                            └── Compatible numeric packets
                                └── Claim-centered draft
                                    └── Strict verification
                                        └── Coverage/redundancy critique
                                            └── Constrained rewrite
                                                └── Strict verification + final allowlist check
```

The key architectural change is that sections contain `claim_ids`; raw evidence allocation becomes a deterministic selection-manifest operation rather than an LLM routing-everything operation.

# 3. Ranked fix plan

## Rank 0 — Lock the experiment and expose the actual funnel

This is a prerequisite rather than a direct score lever.

**What.** Create one task-72 run policy containing:

- Corpus hash and work-identity version.
- Model IDs and generation settings.
- Effective prompt name/hash.
- Every relevant feature flag.
- Task source policy.
- Word budget.
- Selector and claim-graph versions.
- Numeric compiler version.

Emit the full funnel in distinct works and independent study families, not just rows and `ev_ids`.

**Where.**

- `compose_agentic_report_s3gear329.py:190` and 231–246: task profile and resolved flags.
- `multi_section_generator.py`, `_call_outline` around Excerpt 2: effective prompt/input path.
- Route call around 10565–10620.
- `verified_compose.py`, `_section_baskets_for_compose` around 3280–3340.

**Why it moves RACE.** It prevents spending 45 minutes on false comparisons and reveals whether failure occurs in eligibility, selection, cap truncation, verification, or final citation use.

**Faithfulness risk.** None if logging is read-only and sensitive raw reasoning is not required.

**Trap.** Instrumentation alone is not progress. Land it first, then immediately test a content hypothesis.

---

## Rank 1 — Add a task-specific source and topic firewall

**What.** Build a work-level `TaskSourcePolicy` and immutable `compose_allowlist`. A work passes only if all hard dimensions pass:

- Positively relevant to AI and labor-market restructuring.
- English-language article.
- Published in a journal.
- Peer-reviewed scholarly article.
- Allowed article role: original research, systematic review/meta-analysis, strong scholarly review, or relevant theory.
- No retraction or invalid bibliographic identity.
- High-quality verdict under a design-appropriate rubric.

Unknown is not deleted, but it is held for review and cannot compose.

Tier remains metadata, not the decision. Low-tier and ineligible material is disclosed in the run artifact, not cited or discussed in the final report.

**High-quality rubric.**

- Empirical work: transparent data, sample, method/estimand, outcome definition, and limitations.
- Reviews: explicit and credible synthesis method if used for quantitative/consensus claims.
- Theory/conceptual work: direct relevance and recognized peer-reviewed contribution.
- Venue prestige can support the judgment but cannot be the sole criterion.
- Duplicate publications and multiple reports from the same study receive one `study_family_id`.

**Mixed baskets.** Do not merely remove ineligible citations from a basket whose canonical claim may have been derived from them. Create an `EligibleBasketView` and revalidate or regenerate the canonical claim against eligible members only.

**Where.**

- New proposed module: `src/polaris_graph/generator/task_source_eligibility.py`.
- Invoke after topic adjudication and before `build_outline_digest` in the flow anchored by Excerpt 2.
- `topic_relevance_gate.py`: add `RELEVANT`, `OFF_SUBJECT`, and `UNCERTAIN_REVIEW` composition dispositions.
- Route caller around 10565–10620: pass the allowlist, not merely `_off_topic_ev_ids`.
- `_section_baskets_for_compose` around 3280–3340: return eligible member views.
- Final citation renderer: reject any `work_id` outside the allowlist.

Every augmentation path—theme floor, weighted enrichment, singleton routing, route-all, and debate-con consolidation—must pass the same central predicate.

**Why it moves RACE.** It simultaneously satisfies the explicit instruction and removes the medical, press-release, regulatory-document, and derivative-source contamination that consumes words without answering the question.

**Faithfulness risk.** False negatives from incomplete language/type metadata.

**Control.** Preserve all rows, route unknowns to a review queue, and manually resolve the final approximately 35–40 selected works. Never fail open into composition for a hard source restriction.

**Trap verdict.** A T1–T4 filter, publisher-domain heuristic, or impact-factor cutoff is a trap.

**Exit criterion.** Zero selected or cited works with `topic`, `language`, `journal`, `peer_review`, or `quality` status other than `PASS`.

---

## Rank 2 — Build the judge-aligned claim-evidence architecture

**What.** Introduce a `ClaimNode` layer between evidence consolidation and section planning:

```text
claim_id
canonical_question_or_claim
priority: P0 / P1 / P2
concept_family
claim_type
required_evidence_role
quantitative_slot
word_budget
supporting_baskets
independent_study_families
qualifiers
contradictions
status: supported / singleton / retrieval_gap / omit
```

Task-72 concept families should include, as questions to answer rather than conclusions to force:

- AI, automation, robotics, and generative-AI distinctions.
- Task exposure versus adoption versus observed outcomes.
- Task displacement, complementarity, productivity/scale effects, and new-task creation.
- Employment, wages, hours, vacancies, productivity, occupational transitions, and task content.
- Short-run versus long-run adjustment.
- Variation by occupation, skill, industry, firm, geography, and demographic group.
- Causal studies versus exposure indices, projections, and laboratory productivity studies.
- Organizational and institutional mediators.
- Consequential contradictions and methodological limitations.

Assign `P0` only to concepts that directly answer the research question. Unsupported concepts remain gap nodes; they do not become prose claims.

**Where.**

- New proposed module: `src/polaris_graph/generator/claim_architecture.py`.
- Build it from eligible claim digests before `_call_outline`, whose current input construction is shown in Excerpt 2.
- Pass it to `outline_agent.py` for gap analysis.
- Change section-plan output to carry `claim_ids`, thesis, and word budget, with evidence IDs included only as a resolved audit view.

**Why it moves RACE.** The present system optimizes which sources reach sections, not whether the report answers the reference concepts coherently. A claim graph directly measures omission, centrality, triangulation, contradiction resolution, and evidence-to-word efficiency.

**Faithfulness risk.** The planner may invent an attractive architecture unsupported by evidence.

**Control.** Separate concept questions from asserted claims. Only evidence-backed claim nodes can enter prose. A missing concept triggers targeted retrieval or explicit omission, not fabricated coverage.

**Trap verdict.** Copying a hidden benchmark answer or mechanically forcing every ontology node is a trap. Use the research question, a general literature-review rubric, and the eligible corpus. Reference-answer concepts should be used only when evaluation policy permits them, preferably as a post-hoc diagnostic.

**Exit criterion.**

- 100% of P0 concepts addressed.
- At least 90% weighted P0/P1 concept coverage.
- Every detected material contradiction either resolved in the plan or explicitly marked for treatment.
- No unsupported concept silently converted to a claim.

---

## Rank 3 — Replace route-all with a marginal-utility selector

**What.** Select works and baskets deliberately rather than routing every orphan.

Each selected work must have at least one explicit role:

- Anchor for an uncovered central claim.
- Independent corroborator.
- Consequential contradictor.
- Methodological qualifier.
- Contributor to a compatible numeric set.
- Distinct population/design needed for a central heterogeneity claim.

A deterministic greedy-add-and-swap process is sufficient initially:

1. Add the strongest eligible anchor for each P0 claim.
2. Add an independent corroborator where the claim warrants synthesis.
3. Add material contradictory evidence.
4. Add evidence needed for compatible quantitative comparison.
5. Prefer replacement of a weaker source over appending.
6. Stop when no candidate has positive marginal utility under the word budget.
7. Run leave-one-source-out ablation and remove zero-utility works.

Track source counts by distinct `work_id`, and triangulation by `study_family_id`.

**Where.**

- New proposed module: `src/polaris_graph/generator/quality_selective_selector.py`.
- At the route call around 10565–10620:

  - If selective mode is on, assert that route-all is off.
  - Route selected claim packets by `claim_id`.
  - Do not append a residual section.
  - Unselected material remains an audit backlog.

- In `_section_baskets_for_compose` around 3280–3340:

  - Accept a selection manifest containing exact `basket_id` and eligible member IDs.
  - Do not include an entire basket merely because one arbitrary member intersects the section.
  - Pass debate con-baskets through the same selector and eligibility checks.

- Log and reject downstream top-24 truncation of selected material.

**Why it moves RACE.** It aims directly at the observed sweet spot: authoritative, nonredundant synthesis at a fixed word budget. It recovers useful evidence without producing a one-sentence-per-basket encyclopedia.

**Faithfulness risk.** A selector can suppress a minority result or overvalue venue/tier.

**Control.** Give contradictions explicit positive utility, retain the full rejection ledger, and require observed claim spans for every source-selection decision.

**Trap verdict.** Route-all, the residual “Additional Corroborated Findings” section, and a universal per-section evidence floor are traps.

**Source-count policy.**

- Treat approximately 34–40 eligible works as a green experimental band because 37 currently performs well.
- Do not encode 37 into the objective.
- A source above 37 must add a central claim, independent triangulation, material contradiction, or quantitative contribution.
- Any report above 37 must beat its nested 37-source subset on synthesis density and claim coverage at the same word budget before full scoring.

**Exit criterion.**

- Zero selected sources with zero marginal utility.
- Zero residual routes.
- Zero selected sources dropped by a downstream cap.
- Every selected source maps to an explicit claim role.
- Projected word count no more than 5% above the champion’s word budget.

---

## Rank 4 — Compose claims, not baskets, and revise against the graph

**What.** Replace the implicit “one basket, one sentence” rendering pattern with claim packets containing:

- The claim or analytical question.
- Two to four selected independent sources where warranted.
- Exact supporting spans.
- Contradictory or qualifying source spans.
- Design, population, technology, outcome, and horizon distinctions.
- Numeric packet IDs.
- A paragraph word budget.

A strong paragraph should usually do four things:

1. State the bounded synthesis.
2. Compare or triangulate evidence.
3. Explain a consequential difference or contradiction.
4. State the implication for labor-market restructuring without exceeding the evidence.

After the first draft:

1. Run strict verification.
2. Recalculate claim coverage from surviving sentences.
3. Critique for concept omissions, source-by-source narration, redundancy, causal overstatement, unresolved contradiction, and numeric misuse.
4. Rewrite only the affected paragraph using the same allowlisted evidence.
5. Run strict verification again.
6. Remove any selected source that is no longer cited or useful.

The critic must not introduce new evidence IDs or facts.

**Where.**

- Add a proposed `claim_compose.py` at the compose boundary anchored by `_section_baskets_for_compose` in Excerpt 4.
- Thread claim packets through the existing strict-verification path.
- Run the critique after the first verified draft, not merely on the pre-verification draft; otherwise it evaluates sentences that may later disappear.

**Why it moves RACE.** RACE rewards analytical synthesis and coverage, not a bibliography rendered as isolated summaries. This is the primary prose-side improvement.

**Faithfulness risk.** Multi-source sentences can accidentally attribute one source’s detail to another; unconstrained revision can hallucinate.

**Control.** Keep clause-level citation mapping, immutable evidence packets, and unchanged strict verification after every rewrite.

**Trap verdict.** Citation spraying, adding prose without additional analysis, and repeated whole-report rewrites are traps.

**Exit criterion.**

- All final factual clauses pass the existing verifier.
- No P0 claim is lost when failed sentences are removed.
- Multi-source synthesis density is at least 15% higher than the champion per 1,000 words.
- Final selected-work set equals final cited-work set.

---

## Rank 5 — Add narrow, manifest-bound quantitative synthesis

**What.** Build a typed numeric manifest before any calculation. Add the brief’s fields plus work and dependence identity:

```text
numeric_id
ev_id
work_id
verbatim_numeric_span
span_hash
locator
population
geography
technology_or_exposure
design
estimand
outcome_definition
unit_and_scale
sign_convention
comparator
horizon
estimate
uncertainty
N
study_family_id
sample_dependence_id
quality_status
transformation
compatibility_key
```

A compatibility key should normally agree on:

- Construct and estimand.
- Outcome definition.
- Unit/scale and sign.
- Technology/exposure definition.
- Population frame and geography.
- Comparator.
- Time horizon.
- Design class.
- Independent sample family.

**Safe first-release operations.**

- Algebraically valid unit normalization.
- CI/SE conversions when all inputs are available.
- A reported-estimate range within a strictly compatible set.
- Reproduction of a published journal meta-analysis’s pooled estimate.
- Side-by-side quantitative contrasts when studies are incompatible, explicitly labeled as nonpoolable.

**Initially forbidden.**

- Pooling percentages with percentage points or log changes.
- Combining exposure scores, productivity experiments, job projections, and realized employment effects.
- Combining different horizons or technologies.
- Vote-counting directions as if it were a meta-analysis.
- Pooling duplicate samples.
- LLM-authored broad meta-analysis because arithmetic happens to be possible.

Use registered deterministic calculation functions. Bind `[#calc:<hash>]` to canonicalized manifest inputs, inclusion/exclusion rules, function code/version, output, and rounding. Any change invalidates the hash.

**Where.**

- New proposed module: `src/polaris_graph/generator/numeric_manifest.py`.
- Integrate with the existing `execute_python` dispatch associated with `outline_agent.py:105/162`.
- Enforce the hash in the existing `[#calc:]` renderer; its exact location was not supplied, so a line number should not be invented.

**Why it moves RACE.** It adds numerical specificity and methodological insight while distinguishing studies that measure very different labor-market phenomena.

**Faithfulness risk.** Semantic incompatibility and hidden sample dependence are much more dangerous than arithmetic errors.

**Trap verdict.** Broad pooling is a major trap. The narrow compatibility compiler is worth building.

**Exit criterion.**

- Every computed number has a valid manifest hash.
- Every manifest input is from the composition allowlist.
- Zero calculations over an incompatible or dependence-unknown set.
- Every P0 quantitative node has either a safe quantitative packet or an explicit, evidence-backed noncomparability treatment.

---

## Rank 6 — Make gap retrieval claim-specific and interruptible

**What.** Split cognition gaps into three types:

- `SUBSTANTIVE_CLAIM_GAP`: may trigger literature retrieval.
- `BIBLIOGRAPHIC_VERIFICATION_GAP`: metadata lookup only.
- `SOURCE_POLICY_GAP`: handled by the eligibility filter, never used as a topical search query.

Every substantive search action must include:

```text
gap_claim_id
observed_support_refs
missing_relation
target_article_role
AI_or_automation_anchor
labor_outcome_anchor
population_or_method_anchor
query
expected_gain
stop_condition
```

Bad query:

> methodological restriction to high-quality English-language journals

Good structure:

> AI/automation term + labor outcome term + the missing claim’s method, population, or mechanism

Journal/language restrictions should be metadata filters and eligibility checks, not the query’s substantive topic.

Fetch in batches of 10 and topic/eligibility-screen each batch before continuing. A candidate cannot be auto-assigned unless it is positively relevant and composition-eligible.

**Where.**

- `outline_agent.py`, the `search_more_evidence` action handler and ReAct dispatch.
- `topic_relevance_gate.py`, before select/weight/route.
- The auto-routing stage that sent demoted rows to Introduction.

**Why it moves RACE.** Retrieval becomes a response to missing central claims instead of an undirected increase in corpus volume.

**Faithfulness risk.** Overly rigid lexical anchors can miss relevant terminology.

**Control.** Permit exact-title/DOI searches and semantic exceptions, but require a claim ID and human-readable rationale.

**Trap verdict.** “More retrieval” without graph utility is a trap.

**Exit criterion.**

- Every query points to an uncovered P0/P1 claim.
- No source-policy-only query executes.
- No fetched row reaches selection without positive topic and source eligibility.
- Two consecutive zero-utility queries terminate that gap branch.

---

## Rank 7 — Repair the effective outline prompt and menu

**What.**

- Assert that task 72 uses the generic prompt.
- Log the effective prompt text hash.
- Replace raw source-count floors with claim-coverage rules.
- Require at least two independent sources for a central synthesis claim when such evidence exists; otherwise mark it singleton or a retrieval gap.
- Make claim/basket digests mandatory in the candidate profile.
- Include claim text, exact span availability, journal, article type, year, quality verdict, study family, and quantitative availability.
- Do not send 995 title-only rows as the primary semantic menu.
- Make digest fallback a cheap-gate failure in the task-72 profile rather than silently reverting to title-only planning.
- Apply theme recovery only to eligible claim nodes, never to the raw corpus.
- Treat seminal works as “must receive a selection decision,” not “must be assigned.”

**Where.**

- `OUTLINE_SYSTEM_PROMPT_GENERIC`, beginning around the second half of Excerpt 1.
- `_call_outline`, Excerpt 2 around 3100–3170.
- `outline_digest.py`.
- Existing theme-floor hook around the cited routed-outline stage.

**Why it moves RACE.** It removes title starvation and prompt ambiguity while preventing a universal density floor from recreating the bloat failure.

**Faithfulness risk.** Prompt-only controls are brittle and can be ignored.

**Trap verdict.** Treating a better prompt as a substitute for deterministic eligibility, selection, and coverage validation is a trap.

---

## Rank 8 — Establish the selection-versus-synthesis ceiling experimentally

Run a controlled 2×2 at the same word budget:

| | Current composer | Claim composer + revision |
|---|---:|---:|
| Current/automatic selected set | A | C |
| Oracle-curated eligible set from the existing corpus | B | D |

Interpretation:

- `B − A`: evidence selection ceiling.
- `C − A`: claim architecture/composition gain.
- `D − C`: remaining selection loss.
- `D − B`: composition gain under good evidence.
- If D remains weak, test an external gold journal set to determine whether the existing corpus itself is the ceiling.

Then test nested source sets—30, 34, 37, 40, and 44—from the same marginal-utility ranking.

**Why it moves RACE.** It prevents investing months in retrieval if prose architecture is the bottleneck, or vice versa.

**Faithfulness risk.** None, provided the oracle uses the same source policy.

**Trap verdict.** Optimizing to one noisy RACE result is a trap.

# 4. Cheap outline-first flywheel

## Candidate outline-only profile

```text
PG_DUMP_ROUTED_OUTLINE=1
PG_STOP_AFTER_ROUTED_OUTLINE=1          # proposed
PG_ROUTE_ALL_BASKETS=0
PG_QUALITY_SELECTIVE_ROUTE=1            # proposed
PG_TASK_SOURCE_POLICY=journal_en_hq      # proposed
PG_OUTLINE_BASKET_DIGEST=1
PG_OUTLINE_THEME_FLOOR=0                 # initially, to isolate effects
PG_COMPOSE_OFFTOPIC_BASKET_SCREEN=1      # defense in depth
```

The route-all profile can run separately to produce a recall backlog, but its output must never feed candidate prose automatically.

## Per-iteration loop

1. **Quick fix:** change one hypothesis-bearing component only.
2. **Quick test:** run through routed-outline dump and stop.
3. **Quick read:** inspect every selected work’s metadata, claim mapping, and supporting span.
4. **Quick investigate:** compare the first divergent logged decision against the baseline.
5. **Promote:** run the approximately 45-minute compose only after every outline gate passes.
6. **Verify and score:** deterministic checks, source ablation, then repeated RACE scoring.
7. **Archive:** preserve config, prompt, selection, report, verifier, and score hashes.

## Exact gates

| Gate | Pass signal | Failure action |
|---|---|---|
| G0 Configuration | Expected corpus hash, model locks, generic prompt, candidate flags, and word budget; no silent fallback | Stop before outline |
| G1 Eligibility | 100% of selected works are relevant, English, verified journal articles, peer-reviewed, and quality-pass; zero unknowns | Review or replace source |
| G2 Retrieval | Every executed query cites a real P0/P1 gap; no source-policy-only query; no invalid candidate auto-routed | Cancel/rewrite query |
| G3 Claim graph | P0 coverage 100%; weighted P0/P1 coverage ≥90%; every detected material contradiction planned | Targeted retrieval or replan |
| G4 Selection | Zero zero-utility works, residual routes, or downstream cap drops; every work has a role | Swap/remove sources |
| G5 Synthesis projection | At least 70% of P0/P1 analytical claims have ≥2 independent study families where available; projected multi-source synthesis density ≥1.15× champion | Reallocate claim packets |
| G6 Word efficiency | Projected words ≤1.05× champion; claim coverage per 1,000 words ≥ champion | Replace rather than append |
| G7 Read gate | Reviewer reads 100% of selected source entries; each has bibliographic proof, a usable span, and correct claim mapping; no title-only support | Reject the source/route |
| G8 Numeric | All calculations compatible, manifest-bound, and allowlisted; unresolved P0 quantitative nodes explicitly tracked | Block calculation or retrieve |
| G9 Final compose | Every final factual clause verifies; no P0 claim lost; zero ineligible citations; selected works equal cited works | Targeted paragraph rewrite |
| G10 RACE | At least five paired rescoring runs; mean gain ≥0.02 and 95% paired interval above zero | Treat as noise/near miss |

The 34–40 source band is a dashboard signal, not a pass condition. A report outside it can proceed if it passes utility and word-efficiency gates. A report above 37 must also outperform its nested 37-source version.

Do not claim SOTA merely at 0.46. SOTA is established only when the candidate’s lower confidence bound exceeds the best comparison score under the same evaluator and settings.

## Fast diagnosis from the funnel

- Eligible evidence exists for a missing claim but was not selected: selector/router defect.
- Evidence was selected but absent from the section input: cap or augmentation defect.
- Evidence reached the writer but the claim disappeared after verification: composition/grounding defect.
- Oracle evidence helps the current writer: selection ceiling.
- New writer helps the current evidence set: synthesis ceiling.
- Oracle plus new writer remains weak: concept architecture, word allocation, corpus, or evaluator mismatch.
- More sources increase count but not weighted claim coverage: bloat; revert and replace.

Every diagnosis must cite specific source, claim, route, or verifier log records—not only aggregate counts.

# 5. Real-time cognition monitor

## Monitor action boundaries, not private chain-of-thought

Raw model reasoning may be incomplete, unavailable, or unsuitable as a correctness dependency. The stable unit to stream and assess should be a structured decision beat emitted before every tool action:

```text
turn_id
state_hash
observed_refs
gap_claim_id
short_reasoning_summary
proposed_action
expected_claim_graph_delta
risk
stop_condition
```

Hook this around the GLM ReAct dispatch in `outline_agent.py` near the cognition model configuration/calls cited at 104 and 156.

At each beat:

1. Validate deterministic requirements.
2. Send the beat and referenced evidence records to the Sol assessor.
3. Receive `ALLOW`, `PAUSE_REPLAN`, or `ABORT_BRANCH`.
4. Dispatch the action only after `ALLOW`.
5. Stream tool results in batches.
6. Reassess after topic and eligibility dispositions.
7. Update the claim graph.

The Sol assessor should not be allowed to override hard source, calculation, or faithfulness gates. If it is unavailable, deterministic preflight may continue, but the run is marked degraded and cannot skip the outline read gate.

## Pause/replan triggers

| Trigger | Required response |
|---|---|
| `observed_refs` empty or unresolved | Block action and ask GLM to ground its decision |
| Gap is merely “find high-quality English journals” | Convert to source-policy filtering; do not search |
| Query lacks both an AI/automation anchor and labor outcome anchor, unless exact-title/DOI search | Reject before fetch |
| At least 3 of the first 10 results are confirmed off-subject | Pause and rewrite query |
| Zero relevant, eligible unique works in the first batch of 10 | Pause; allow one rewritten attempt |
| Fewer than 2 useful eligible works after 20 results, with no contradiction or unique anchor found | Stop that query |
| Two consecutive queries create no P0/P1 coverage, triangulation, contradiction, or numeric-set gain | End retrieval for that gap |
| Any `OFF_SUBJECT`, `UNKNOWN`, or source-ineligible work enters selection | Hard-stop outline and rebuild |
| Any empirical outcome claim is dumped into Introduction without an Introduction-specific claim role | Replan section mapping |
| Any selected basket routes by zero-overlap residual | Replan; residual section forbidden |
| Added source has nonpositive marginal utility | Replace or remove it |
| Downstream cap drops a selected source | Hard-stop; selection and writer inputs disagree |
| Mixed units, outcomes, horizons, or dependence-unknown samples enter a calculation | Block calculation |
| A material contradiction is detected but only one side reaches the plan | Reopen selection |
| Digest construction silently falls back to titles | Fail the candidate outline gate |
| Candidate profile resolves `PG_ROUTE_ALL_BASKETS=1` | Stop before compose |

A failed query should abort only that branch. Two failed replans for the same violation should mark the gap unresolved and move on; persistent hard contamination should invalidate the whole outline.

# 6. Is claim architecture the missing SOTA lever?

Yes—probably. The evidence favors a synthesis/selection bottleneck:

- The corpus is already large.
- The gap-search loop does retrieve and update the corpus.
- Lean selection underuses relevant material.
- Route-all overuses it and lowers RACE.
- The best report uses a moderate number of synthesized sources.
- Current instrumentation measures source counts and tiers more directly than concept recall, centrality, contradiction resolution, or evidence efficiency.

The uncertainty is whether the eligible journal-only subset contains the right works. That is why the source-eligibility audit and 2×2 oracle experiment come first.

The claim layer should slot after eligibility/consolidation and before the final outline:

```text
eligible evidence
→ claim graph
→ gap analysis
→ updated claim graph
→ source optimization
→ section plan
→ draft
→ verified-draft critique
→ constrained rewrite
```

It should not be an extra prose-planning prompt pasted after the existing outline. It must become the shared contract for retrieval, selection, word allocation, writing, criticism, and evaluation.

The most judge-relevant metrics are:

- Weighted central-concept recall.
- Marginal claim coverage per added work.
- Independent multi-source synthesis claims per 1,000 words.
- Contradiction-resolution rate.
- Quantitative-slot resolution.
- Unsupported-claim rate.
- Redundancy rate.
- Evidence-to-word efficiency.
- Final eligible-source compliance.

# 7. Line-by-line monitoring specification

The excerpts provide only one exact existing free-form activation line:

```text
[activation] debate_con_basket_consolidation: consolidated=%d
```

Per Excerpt 4, `consolidated=0` is valid and must not be treated as failure. The excerpt mentions a distinct unavailable/fail-open marker but does not provide its exact complete string, so it would be dishonest to invent it.

Add the following JSONL contract. Every line has `run_id`, `iteration_id`, `seq`, and `ts`. Repeated records are emitted once per work, candidate, claim, basket, route, or sentence.

```json
{"event":"RUN_CONFIG","run_id":"<id>","iteration_id":"<id>","seq":1,"task_id":72,"corpus_sha256":"<hash>","models":{"cognition":"z-ai/glm-5.2","executor":"deepseek/deepseek-v4-pro","writer":"z-ai/glm-5.2","assessor":"openai/gpt-5.6-sol"},"flags":{"PG_ROUTE_ALL_BASKETS":false,"PG_OUTLINE_BASKET_DIGEST":true,"PG_OUTLINE_THEME_FLOOR":false,"PG_COMPOSE_OFFTOPIC_BASKET_SCREEN":true,"PG_DUMP_ROUTED_OUTLINE":true,"PG_STOP_AFTER_ROUTED_OUTLINE":true},"word_budget":<n>}

{"event":"PROMPT_EFFECTIVE","seq":2,"prompt_kind":"GENERIC","prompt_sha256":"<hash>","outline_path":"LARGE_DIGEST","outline_redesign":true,"outline_max_ev":150,"rows_available":995,"works_available":840,"rows_shown":<n>,"statements_visible":true,"digest_status":"OK","digest_clusters":<n>}

{"event":"FUNNEL_SNAPSHOT","seq":3,"stage":"POST_ELIGIBILITY","raw_rows":995,"distinct_works":<n>,"study_families":<n>,"topic_relevant_works":<n>,"english_journal_works":<n>,"quality_pass_works":<n>,"compose_allowlist_works":<n>,"baskets_raw":<n>,"baskets_eligible":<n>,"members_artifact_sha256":"<hash>"}

{"event":"SOURCE_ELIGIBILITY","seq":<n>,"work_id":"<stable-id>","ev_ids":["<ev-id>"],"title":"<title>","doi_or_stable_id":"<id>","journal":"<journal>","year":<year>,"tier":"<tier>","topic_status":"RELEVANT","language_status":"PASS","container_status":"JOURNAL","peer_review_status":"PASS","quality_status":"PASS","retraction_status":"CLEAR","compose_status":"PASS","study_family_id":"<id>","reason_codes":[],"observed_refs":[{"ev_id":"<id>","locator":"<metadata-or-span>","span_sha256":"<hash>"}]}

{"event":"DECISION_BEAT","seq":<n>,"turn":<n>,"state_sha256":"<hash>","gap_claim_id":"<claim-id>","short_reasoning_summary":"<bounded-summary>","proposed_action":"SEARCH_MORE_EVIDENCE","expected_delta":{"coverage":[],"triangulation":[],"contradiction":[],"numeric_set":[]},"stop_condition":"<condition>","observed_refs":[{"seq":<claim-record-seq>},{"ev_id":"<id>","locator":"<locator>","span_sha256":"<hash>"}]}

{"event":"ASSESSOR_VERDICT","seq":<n>,"decision_seq":<n>,"verdict":"ALLOW|PAUSE_REPLAN|ABORT_BRANCH","violations":[],"required_changes":[],"observed_refs":[{"seq":<n>}]}

{"event":"QUERY_PREFLIGHT","seq":<n>,"query_id":"<id>","gap_claim_id":"<id>","query":"<query>","ai_anchors":["<term>"],"labor_anchors":["<term>"],"method_or_population_anchors":["<term>"],"target_article_role":"<role>","source_filters":{"language":"en","container":"journal"},"status":"PASS|REJECT","reason_codes":[],"observed_refs":[{"seq":<claim-record-seq>}]}

{"event":"FETCH_BATCH","seq":<n>,"query_id":"<id>","batch":1,"candidate_ids":["<id>"],"fetched":10,"duplicates":<n>,"confirmed_offtopic":<n>,"topic_uncertain":<n>,"relevant_eligible":<n>,"continue":true,"observed_refs":[{"seq":<candidate-disposition-seq>}]}

{"event":"CANDIDATE_DISPOSITION","seq":<n>,"query_id":"<id>","candidate_id":"<id>","ev_id":"<id>","work_id":"<id>","topic_status":"RELEVANT|OFF_SUBJECT|UNCERTAIN_REVIEW","source_status":"PASS|FAIL|UNKNOWN","corpus_action":"KEEP_AUDIT","compose_action":"ALLOW|WITHHOLD|REVIEW","claim_ids":["<id>"],"reason_codes":[],"observed_refs":[{"ev_id":"<id>","locator":"<title-or-abstract>","span_sha256":"<hash>"}]}

{"event":"CLAIM_NODE","seq":<n>,"claim_id":"<id>","priority":"P0|P1|P2","concept_family":"<family>","claim_type":"<type>","status":"SUPPORTED|SINGLETON|RETRIEVAL_GAP|OMIT","supporting_basket_ids":["<id>"],"independent_study_families":["<id>"],"contradiction_ids":["<id>"],"quantitative_slot":"NONE|OPEN|READY|INCOMPATIBLE","word_budget":<n>,"observed_refs":[{"seq":<source-seq>}]}

{"event":"BASKET_ELIGIBLE_VIEW","seq":<n>,"basket_id":"<id>","canonical_claim":"<claim>","raw_member_ev_ids":["<id>"],"eligible_member_ev_ids":["<id>"],"withheld_member_ev_ids":["<id>"],"canonical_claim_reverified":true,"study_family_ids":["<id>"],"observed_refs":[{"seq":<source-seq>}]}

{"event":"SELECTION_DECISION","seq":<n>,"work_id":"<id>","basket_id":"<id>","claim_ids":["<id>"],"decision":"SELECT|REJECT|REPLACE","roles":["ANCHOR|CORROBORATOR|CONTRADICTOR|QUALIFIER|QUANT"],"replaced_work_id":null,"marginal_utility":{"claim_coverage":<n>,"triangulation":<n>,"contradiction":<n>,"quantitative":<n>,"design_diversity":<n>,"redundancy_cost":<n>,"word_cost":<n>,"total":<n>},"observed_refs":[{"seq":<claim-seq>},{"seq":<source-seq>}]}

{"event":"ROUTE_DECISION","seq":<n>,"basket_id":"<id>","claim_id":"<id>","section_id":"<id>","method":"CLAIM_MANIFEST|LEGACY_LEXICAL_OVERLAP","overlap_score":null,"status":"ROUTED|WITHHELD|REPLAN","residual":false,"eligible_member_ev_ids":["<id>"],"observed_refs":[{"seq":<selection-seq>},{"seq":<claim-seq>}]}

{"event":"AUGMENTATION","seq":<n>,"name":"THEME_FLOOR|WEIGHTED_ENRICHMENT|ROUTE_ALL|DEBATE_CON","enabled":true,"status":"OK|OFF|UNAVAILABLE_FAILOPEN","added_basket_ids":[],"added_work_ids":[],"rejected_work_ids":[],"observed_refs":[{"seq":<n>}]}

{"event":"OUTLINE_SECTION","seq":<n>,"section_id":"<id>","title":"<title>","thesis":"<thesis>","claim_ids":["<id>"],"work_ids":["<id>"],"study_family_ids":["<id>"],"estimated_words":<n>,"p0_claims":<n>,"p1_claims":<n>,"independent_multi_source_claims":<n>,"contradictions_planned":<n>,"numeric_packets":["<id>"],"observed_refs":[{"seq":<claim-seq>},{"seq":<route-seq>}]}

{"event":"CAP_APPLICATION","seq":<n>,"cap_name":"TOP_24_WRITER","input_work_ids":["<id>"],"kept_work_ids":["<id>"],"dropped_work_ids":[],"selected_work_dropped":false,"status":"PASS","observed_refs":[{"seq":<selection-seq>}]}

{"event":"OUTLINE_GATE","seq":<n>,"verdict":"PASS|FAIL","metrics":{"p0_coverage":1.0,"weighted_p0_p1_coverage":<n>,"selected_works":<n>,"selected_study_families":<n>,"zero_utility_works":0,"residual_routes":0,"ineligible_selected":0,"unknown_selected":0,"projected_words":<n>,"synthesis_density":<n>,"redundancy_rate":<n>},"failed_invariants":[],"observed_refs":[{"seq":<offending-or-supporting-seq>}]}

{"event":"NUMERIC_SET","seq":<n>,"numeric_set_id":"<id>","claim_id":"<id>","compatibility_key":"<canonical-key>","input_numeric_ids":["<id>"],"excluded_numeric_ids":["<id>"],"exclusion_reasons":{"<id>":"<reason>"},"independence_status":"PASS|FAIL|UNKNOWN","operation":"RANGE|NORMALIZE|PUBLISHED_META|NO_POOL","status":"READY|INCOMPATIBLE","manifest_sha256":"<hash>","observed_refs":[{"ev_id":"<id>","locator":"<locator>","span_sha256":"<hash>"}]}

{"event":"CALC_RESULT","seq":<n>,"calc_hash":"<hash>","numeric_set_id":"<id>","formula_id":"<id>","formula_version":"<version>","code_sha256":"<hash>","input_manifest_sha256":"<hash>","raw_result":"<value>","rounded_result":"<value>","rounding_rule":"<rule>","status":"PASS|INVALID","observed_refs":[{"seq":<numeric-set-seq>}]}

{"event":"SENTENCE_VERIFY","seq":<n>,"sentence_id":"<id>","section_id":"<id>","claim_ids":["<id>"],"cited_work_ids":["<id>"],"calc_hashes":["<hash>"],"allowlist_status":"PASS","strict_verify_status":"PASS|FAIL","nli_status":"PASS|FAIL","failure_reasons":[],"observed_refs":[{"ev_id":"<id>","locator":"<locator>","span_sha256":"<hash>"}]}

{"event":"CRITIQUE_ISSUE","seq":<n>,"issue_id":"<id>","severity":"BLOCKER|MAJOR|MINOR","type":"OMISSION|REDUNDANCY|CAUSAL_OVERCLAIM|CONTRADICTION|NUMERIC_MISUSE|SOURCE_VIOLATION|WORD_INEFFICIENCY","section_id":"<id>","claim_ids":["<id>"],"sentence_ids":["<id>"],"required_action":"REWRITE|REMOVE|RESELECT|RETRIEVE","observed_refs":[{"seq":<n>}]}

{"event":"REPORT_FUNNEL","seq":<n>,"report_sha256":"<hash>","draft_sentences":<n>,"verified_sentences":<n>,"dropped_sentences":<n>,"final_words":<n>,"selected_works":<n>,"cited_works":<n>,"eligible_cited_works":<n>,"study_families_cited":<n>,"p0_coverage_final":<n>,"weighted_coverage_final":<n>,"synthesis_density_final":<n>,"unsupported_claim_rate":0,"source_violation_count":0}

{"event":"SOURCE_ABLATION","seq":<n>,"work_id":"<id>","report_or_plan_sha256":"<hash>","coverage_loss":<n>,"triangulation_loss":<n>,"contradiction_loss":<n>,"numeric_loss":<n>,"word_saving":<n>,"decision":"KEEP|REMOVE","observed_refs":[{"seq":<selection-seq>}]}

{"event":"RACE_EVAL","seq":<n>,"report_sha256":"<hash>","judge_id":"<id>","judge_version":"<version>","repeat":<n>,"seed_or_sample_id":"<id>","race_score":<n>,"paired_baseline_report_sha256":"<hash>","paired_delta":<n>}

{"event":"ITERATION_DECISION","seq":<n>,"verdict":"REPLAN|FULL_COMPOSE|PROMOTE|REJECT","finding":"<specific finding>","single_change_next":"<one change>","observed_refs":[{"seq":<real-record-seq>},{"ev_id":"<id>","locator":"<locator>","span_sha256":"<hash>"}]}
```

## Monitoring invariants

- Every decision-bearing line must have nonempty, resolvable `observed_refs`.
- A summary count must point to a hashed member artifact and representative offending records.
- No work can appear in `SELECTION_DECISION: SELECT` without a passing `SOURCE_ELIGIBILITY`.
- No basket can route without a selected claim.
- No augmentation can add a work outside the allowlist.
- No selected work can disappear through a cap.
- No computed number can render without a matching `CALC_RESULT: PASS`.
- No final citation can fall outside the allowlist.
- The monitor must read final post-verification claim coverage, not assume that the pre-draft outline survived.
- An iteration conclusion based only on “39 selected,” “106 demoted,” or a RACE count is invalid unless it cites the corresponding source/claim records.

# Recommended first three experiments

1. **Hygiene-only candidate:** route-all off, hard journal-English-quality allowlist, demoted/unknown auto-routing blocked, basket digest on. Run outline-only.
2. **Claim-selector candidate:** same eligible pool, add claim graph and marginal-utility selection. Compare its outline against the hygiene-only result.
3. **2×2 synthesis test:** automatic versus oracle-curated eligible evidence crossed with old versus claim-centered composer.

Only after those pass should the compatible-set numeric layer be added. That sequencing isolates the actual unlock while avoiding the two largest traps: indiscriminate coverage and semantically invalid arithmetic.