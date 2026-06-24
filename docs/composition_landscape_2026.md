# Composition & Long-Form Generation Landscape 2025/2026 (I-comp-001)

**Status:** research deliverable, operator-requested 2026-06-23. Section "composition" of the standard
pipeline-section review (`docs/standard_process_pipeline_section_review.md`), joining the retrieval
(`docs/retrieval_landscape_2026.md`) and consolidation (`docs/consolidation_landscape_2026.md`) docs.
**Method:** deep research — frontier searches fanned out across STORM/Co-STORM, OmniThink, WriteHERE,
LongCite/LongWriter, GenerationPrograms, Deep-Reporter, AgentCPM-Report; every candidate primary-source
verified (year + arXiv/GitHub URL + license); then a "is anything newer?" recency re-check; then every
current-stack claim grounded against the actual POLARIS repo (files read, not assumed).
**Scope (precise):** the outline scaffold + multi-section synthesis + citation INSERTION — where verified
evidence becomes the rendered report. The faithfulness ENGINE (strict_verify / NLI entailment / 4-role D8 /
provenance / span-grounding) is FROZEN and OUT of scope; citation/claim VERIFICATION is frozen, only
citation INSERTION/FORMATTING is in scope.

---

## 0. The one-paragraph answer

The composition frontier cleaves cleanly into two classes, and which class a method belongs to decides
whether POLARIS can adopt it at all. **Class A — generate-then-attribute:** the LLM writes free prose first,
then citations are bolted on after (STORM's article stage, OmniThink, WriteHERE, LongWriter, the whole
ALCE/LongCite citation-insertion line). **Class B — verify-then-organize:** the writer is only allowed to
ORGANIZE and PHRASE already-verified source spans; a fabrication cannot survive because it is checked against
the span it claims, and on failure the text degrades to a verbatim quotation. POLARIS is a Class-B pipeline
by construction (`verified_compose.py`: the writer organizes verified spans, fails back to the basket's own
verbatim K-span, never empty), and on the COMPOSE step it is genuinely **ahead** of the public Class-A stacks
— the same pattern the consolidation doc found (keep-all baskets ahead of URL-dedup). So the governing
question for every candidate is one line: **does its value survive being clamped to "organize verified spans
only," or does its quality come precisely from the free generation POLARIS structurally forbids?** STORM's
OUTLINE stage survives (already adopted, structure-only, `PG_STORM_OUTLINE_SECTIONS`). STORM's ARTICLE stage
does not. The single highest-value, lowest-risk adoptable from the 2025/2026 frontier is **GenerationPrograms**
(2506.14580): it builds text from explicit modular source-grounded operations (paraphrase / compress / fuse)
so attribution is inherent to generation rather than retroactive — the same Class-B DNA as POLARIS, and the
right pattern to upgrade the verified-compose WRITER without touching the frozen gate. The biggest genuine
gap is the one the repo already documents and CUT: **cross-claim author-summary synthesis** (the abstract/
conclusion that asserts a NEW relation assembled from the body's own atoms) is ADD-only-if it ships an
entailment grounding gate; bag-of-atoms checking provably cannot catch atom-recombination, so today
POLARIS ships the safe verbatim-only subset. Every abstractive frontier method steps on that exact landmine.

---

## 1. What POLARIS has today (verified in the repo, not assumed)

The canonical FLOW (`.codex/I-arch-011/composition_design_plan.md` §THE FLOW, I-arch-011 #1268):
`user query → STORM outline (section scaffold) → retrieve+verify → K claims → CONSOLIDATE by claim (Argus
pattern baskets) → ROUTE each basket to its outline section → COMPOSE each section (prose per basket +
provenance tokens → deterministic strict_verify each sentence → fall back to verbatim K-span on failure,
never empty) → THEN draft abstract/exec-summary (front) + conclusion (end), LAST, from already-verified body.`

| Composition stage | Current POLARIS implementation | Verified location |
|---|---|---|
| Outline scaffold | STORM-outline section-scaffold adapter — STRUCTURE-ONLY (titles + order + archetype), asserts NO facts, carries NO STORM-authored prose. DEFAULT-OFF (`PG_STORM_OUTLINE_SECTIONS`) | `generator/multi_section_generator.py:1795-1944` (`_build_storm_outline_section_plans`, `_storm_outline_sections_enabled`) |
| Outline parse / fallback | LLM outline call (`_call_outline`) + deterministic fallback outline + archetype fallback when the LLM outline is unusable | `multi_section_generator.py:1174 (_parse_outline), :1387 (_build_deterministic_fallback_outline), :1984 (_call_outline)` |
| Evidence→section routing | `_assign_evidence_to_planned_outline` maps each verified basket to its outline section | `multi_section_generator.py:1593` |
| Per-basket verified compose | The abstractive WRITER (existing generator-role LLM, NO new model) drafts prose w/ `[#ev:id:a-b]` tokens; each sentence re-checked by UNCHANGED strict_verify against a BASKET-SCOPED pool; a failing sentence FALLS BACK to that basket's own verbatim K-span; never empty. DEFAULT-OFF (`PG_VERIFIED_COMPOSE`) | `generator/verified_compose.py:1-130` |
| Multi-cited synthesis | Co-locate per-member-verified clauses from N corroborating baskets into ONE multi-cited sentence; per-CLAUSE (not whole-sentence) verify invariant. DEFAULT-OFF (`PG_VERIFIED_COMPOSE_MULTICITED`) | `verified_compose.py:44 (compose_multicited_sentence)`; `relational_quantifier_guard.py` |
| Same-span dedup | Collapse degenerate same-span restatements to one rendering per resolved-span footprint, keep-first; a sentence that introduces a NEW number survives (`PG` B11 fix) | `verified_compose.py:84 (dedup_same_span_sentences)` |
| Contract section runner | Slot-bound M-58 prose for entities with a FrameRow; multi-entity slots render N blocks each with own `[bound_ev_id]`; gap rows skip the LLM via `compose_gap_payload` | `generator/contract_section_runner.py:1-55` |
| Abstract / conclusion | Drafted LAST from already-verified body sentences ONLY; VERBATIM re-presentation, faithful BY IDENTITY (byte-equal to a body sentence that already passed strict_verify); empty body → disclosed insufficient-evidence line, never filler | `generator/abstract_conclusion.py:1-50` |
| Key findings | Sibling extractive-summary module the abstract/conclusion reuses (gap-marker filter, citation-preserving sentence regex) | `generator/key_findings.py` |
| Citation insertion | `[#ev:<evidence_id>:<start>-<end>]` provenance tokens at compose time → rendered `[N]` citations; resolved-span identity (ev_id+offsets) is stable under both the stub and the real writer | `verified_compose.py:47-66`; `provenance_generator.py` |
| Other section composers | `abstractive_writer.py`, `analyst_synthesis.py`, `cross_trial_synthesis.py`, `regulatory_synthesizer.py`, `cross_jurisdiction_synthesizer.py`, `quantified_analysis.py` (domain-specific section bodies) | `generator/*.py` |

**The crown-jewel constraint, verified.** The verified-compose WRITER "only ORGANIZES + PHRASES already-verified
spans; it can never license an unsupported claim — a fabrication fails strict_verify and degrades to the verbatim
K-span (QUOTATION is the only faithful-BY-CONSTRUCTION form — survey arXiv:2508.15396)" (`verified_compose.py:14-25`).
strict_verify / NLI / 4-role / provenance are UNCHANGED; the compose module adds NO gate, relaxes none. This is
the Class-B invariant and it is what makes POLARIS's compose step different from every Class-A long-form generator.

**Three corrections to the naive "just adopt STORM end-to-end" framing, grounded in the repo:**

1. **STORM is already adopted — but only its outline stage, deliberately.** POLARIS uses STORM for the section
   SCAFFOLD (structure-only). STORM's article-WRITING stage is Class-A free generation and is structurally
   incompatible with the provenance gate. The repo made exactly this split on purpose (PR-a #1268).
2. **The compose WRITER is the only new LLM call, and it is the EXISTING generator role.** No new model, no new
   slug, no new resolver — governed by `polaris_runtime_lock.yaml` §9.1.8 exactly like every other generation.
   A frontier method is adoptable only as a PATTERN that reshapes how that one existing call is prompted/structured.
3. **Cross-claim synthesis was DESIGNED then CUT** because a bag-of-atoms grounding gate cannot catch
   atom-recombination ("X causes Y" assembled from separate X, Y, and "causes" — every atom present by
   construction). This is the single most important repo lesson for evaluating abstractive frontier methods (§4).

---

## 2. The two faithfulness classes (this is the crux)

Every composition method belongs to one of two classes, and the class — not the benchmark score — decides
adoptability for a provenance-gated clinical pipeline.

- **Class A — generate-then-attribute.** Free prose first; citations attached after (post-hoc attribution, or
  trained-in citation generation). Quality comes from the model's unconstrained writing. **Adoptable by POLARIS
  only as: (i) an OUTLINE/structuring device that asserts no facts, or (ii) a YARDSTICK to beat — never as the
  body writer**, because the free-generation step is precisely what the provenance gate forbids. STORM (article
  stage), OmniThink, WriteHERE, LongWriter, AgentCPM-Report, and the ALCE/LongCite citation line are Class A.

- **Class B — verify-then-organize.** The writer composes from already-verified source spans using
  source-grounded operations; attribution is inherent to construction; a fabrication is caught or degrades to a
  verbatim quote. **This is POLARIS, and it is adoptable directly** because it preserves the gate by construction.
  GenerationPrograms (executable text-operation programs) is the cleanest Class-B frontier method; the
  deterministic-quoting / extractive floor (survey 2508.15396) is the Class-B faithfulness anchor.

The composition isolation axis (§5) tests Class-B-preserving quality on a FIXED verified set; a Class-A method
can only ever enter the bake-off as a yardstick or as an outline/structure contributor.

---

## 3. The 2025/2026 composition frontier (primary-source verified)

Open-source-first (sovereignty). Year + URL + license per candidate. **C = faithfulness class.**

### Outline scaffold (structure-only — Class-A methods admissible here because they assert no facts)

| Method | Year | Primary source | License | Class | Role / why |
|---|---|---|---|---|---|
| **STORM** | 2024-02 | arXiv:2402.14207; github.com/stanford-oval/storm | code MIT (verify LICENSE file); FreshWiki data CC-BY-SA | A (outline used) | **Incumbent FLOOR, partly adopted.** Perspective-guided question-asking → hierarchical outline. POLARIS uses the OUTLINE stage only (`PG_STORM_OUTLINE_SECTIONS`). Article stage = Class-A, NOT adopted. |
| **Co-STORM** | 2024-08 | arXiv:2408.15232; same repo | same as STORM | A (mind-map) | Collaborative discourse + dynamic mind-map (hierarchical concept structure). The mind-map is a structuring idea worth studying for outline organization; the human-in-loop discourse is out of scope for an autonomous pipeline. |
| **AgentCPM-Report (WARP)** | 2026-02 | arXiv:2602.06540 | CC-BY-4.0 (paper); code/weights NOT confirmed | A | **Dynamic outline EVOLUTION** — "Writing As Reasoning Policy" interleaves Evidence-Based Drafting + Reasoning-Driven Deepening, revising the outline as it writes rather than committing upfront. Pattern of interest: a *revisable* scaffold vs POLARIS's fixed STORM scaffold. Writing step is Class-A; only the outline-revision pattern is admissible. |
| **UniCreative** | 2026-04 | arXiv:2604.05517 | arXiv nonexclusive-distrib (paper); code on GitHub (verify) | A | **Adaptive plan-vs-direct SWITCHING** (Findings ACL 2026). Reference-free RL (AC-GenRM adaptive constraint-aware reward + ACPO) where the model learns to autonomously pick rigorous planning vs direct generation per task. Pattern of interest: treating the outline/plan as a *callable, mode-switched* resource — a third revisable-scaffold contender alongside AgentCPM-Report (WARP). Writing step is Class-A free generation; only the adaptive-scaffold pattern is admissible. |

### Citation insertion / attribution (in scope — INSERTION only, NOT verification)

| Method | Year | Primary source | License | Class | Role / why |
|---|---|---|---|---|---|
| **GenerationPrograms** | 2025-06 | arXiv:2506.14580 | arXiv standard; code on GitHub (verify license) | **B** | **LEAD adoptable.** Two-stage: build an executable PROGRAM of modular text operations (paraphrase / compress / fuse) over source passages, then EXECUTE → text whose attribution is inherent, not retroactive. Each operation keeps provenance to its source. This is POLARIS's verify-then-organize DNA expressed as a generation framework — the right pattern to upgrade the verified-compose writer. |
| **LongCite** | 2024-09 | arXiv:2409.02897; github.com/THUDM/LongCite | open weights (LongCite-glm4-9b, -llama3.1-8b); verify model card license | A (trained-in) | Sentence-level fine-grained citations in long-context QA; LongCite-45k dataset. The model GENERATES citations (Class A), so not a body-writer for POLARIS, but the **sentence-level granularity target + CoF (coarse-to-fine) data recipe** are a yardstick for citation density/precision, and the GLM-4-9B base is sovereign-relevant. |
| **FullCite** (Structured Inline Citation Generation) | 2026-06 | arXiv:2606.07130 | verify | A/B hybrid | **Most-recent on-point citation-insertion method.** Generates structured inline citations linking each claim to source doc + supporting evidence via three strategies: prompt-based, **constrained decoding over a citation GRAMMAR**, and post-hoc span alignment. The constrained-decoding-over-grammar strategy is directly relevant to POLARIS's `[#ev:id:start-end]` token grammar — a way to make the writer emit only well-formed, span-anchored citations by construction. Pattern-inspiration for citation insertion. |
| **TROVE** | 2025-03 | arXiv:2503.15289 | CC-BY-4.0 (paper); dataset released | A (benchmark) | **Fine-grained text-provenance benchmark.** Traces each target sentence to its SOURCE sentences AND annotates the relationship (quotation / compression / inference / others) across 11 scenarios, multi- and long-document (0–10k+ tokens). Yardstick + relationship-taxonomy for citation-INSERTION correctness — the taxonomy refines §5c's "the span actually supports the sentence" check beyond a binary, and pairs with ALCE/LongCite as a metric def. Not a method/body-writer. |
| **Citation Grounding (legal)** | 2026-05 | arXiv:2606.00898 | CC-BY-4.0 (paper); code to verify | A (benchmark) | **Newest domain-specific citation-correctness eval** (legal, Ukrainian-court citation graph). Three grounding axes — citation precision (does the cited provision EXIST), relevance (contextually appropriate), temporality (valid at the relevant date). The three-axis decomposition maps onto POLARIS's `[#ev:...]` insertion-correctness check (ev_id exists / span supports / span is the right version). Domain is legal, not clinical, so metric-def/yardstick only — not a method. |
| **ALCE** | 2023-05 | arXiv:2305.14627; github.com/princeton-nlp/ALCE | code on GitHub (EMNLP 2023) | A (benchmark) | **2023 FLOOR / yardstick only — do NOT crown.** First citation-generation benchmark (fluency / correctness / citation quality on ASQA/QAMPARI/ELI5). Useful as the citation-quality metric definition, not a method. |

### Multi-section synthesis / long-form report writers (mostly Class A — yardsticks)

| Method | Year | Primary source | License | Class | Role / why |
|---|---|---|---|---|---|
| **OmniThink** | 2025-01 | arXiv:2501.09751 | arXiv standard; code on GitHub | A | "Slow-thinking" machine writing — iterative expand+reflect to deepen knowledge before writing. **Its value is in the RETRIEVAL/knowledge-curation loop, not composition** (do not let it pull into the retrieval section's turf). The writing step is Class-A free generation. Yardstick for content depth/novelty. |
| **WriteHERE** | 2025-03 | arXiv:2503.08275 (EMNLP 2025 oral); github.com/principia-ai/WriteHERE | arXiv standard; code+prompts released | A | Heterogeneous recursive planning — interleaves recursive task decomposition + execution across retrieve/reason/compose; "beyond outlining" (no fixed outline). Strong on adaptive structure; the COMPOSE leaf is Class-A free generation. Pattern of interest: recursive decomposition of a section into sub-tasks; yardstick for organization. |
| **LongWriter** | 2024-08 | arXiv:2408.07055 (ICLR 2025); github.com/THUDM/LongWriter | open weights; verify license | A | 10,000+ word generation from long context (AgentWrite + LongWriter-6k). Pure length-scaling of free generation — Class A, faithfulness-orthogonal. Yardstick for long-output coherence only; the length is not POLARIS's bottleneck (breadth/coverage is). |
| **Deep-Reporter** | 2026-04 | arXiv:2604.10741; github.com/fangda-ye/Deep-Report | code on GitHub (verify license) | A (grounded) | Grounded MULTIMODAL long-form: agentic search + **checklist-guided incremental synthesis** ("optimal citation placement") + recurrent context management. The **checklist-guided incremental synthesis + citation-placement** idea is the most on-point composition pattern of the 2026 cohort. Multimodal scope is out; the checklist-incremental compose pattern is a yardstick worth a hard look. |
| **ADORE** (Trustworthy Enterprise RAG) | 2026-01 | arXiv:2601.18267 | verify | A | Outline-draft → iterative retrieve → **reflection audits evidence against the outline** (missing sections / weak support) → revise outline. The reflect-against-outline loop is a coverage/completeness pattern; pairs naturally with POLARIS's STORM scaffold + the I-arch-007 breadth funnel. |
| **DeepWriter** | 2025-07 | arXiv:2507.14189 | verify | A (grounded) | Fact-grounded multimodal writing over an OFFLINE knowledge base — close to POLARIS's "compose from a fixed verified corpus" setting. Yardstick for offline-corpus grounded synthesis. |
| **RAPID** | 2025-03 | arXiv:2503.00751; github.com/USTC-StarTeam/RaPID | arXiv nonexclusive-distrib; code on GitHub (verify) | A | Retrieval-augmented long-text generation: retrieval-augmented preliminary OUTLINE + attribute-constrained search + plan-guided article generation (ACL 2025, FreshWiki-2024). The outline+plan-then-write loop is on the composition+retrieval seam; POLARIS's corpus is fixed (not re-retrieving at compose), so the COMPOSE leaf is Class-A free generation — yardstick for retrieval-augmented outline planning, not a body writer. |
| **Disco-RAG** | 2026-01 | arXiv:2601.04377 | CC-BY-4.0 (paper); code to verify | A | **Discourse-aware RAG.** Builds intra-chunk discourse trees (local hierarchy) + inter-chunk rhetorical graphs (cross-passage coherence), folded into a planning blueprint that conditions generation. The rhetorical-structure-conditioned planning is relevant to outline scaffold + section routing (§1); compose leaf is Class-A. Yardstick/pattern for discourse-coherent section organization. |
| **Story2Proposal** | 2026-03 | arXiv:2603.27065; github.com/AgentAlphaAGI/Idea2Paper | arXiv nonexclusive-distrib; code on GitHub (verify) | A | Contract-governed multi-agent scientific-manuscript writer (architect / writer / refiner / renderer + a generate-evaluate-adapt loop under a persistent shared *visual contract*). The document-level structural-CONTRACT pattern (a tracked section/element state the agents may not violate) rhymes with POLARIS's slot-bound contract section runner — pattern of interest for structural-contract composition safety. Class-A write step; pattern only. |
| **Writer-R1** | 2026-03 | arXiv:2603.15061; code on GitHub (verify) | A | Memory-augmented Replay Policy Optimization (MRPO): self-reflection + RL with auto-constructed evaluative criteria as reward, no human annotation. Class-A free generation with reflection — a recent frontier method alongside OmniThink/WriteHERE; yardstick for self-reflective writing quality, not an adoptable. |
| **sui-1** | 2026-01 | arXiv:2601.08472; ellamind/sui-1-24b (HuggingFace) | paper CC-BY-4.0; open weights (24B, verify model-card license) | B-adjacent (grounded) | **Open-weights grounded, verifiable long-form summarization with inline citations** — synthetic CoT + multi-stage-verification data (22k examples, 5 languages); every claim traceable to a source sentence; task-specific training beats scale. The closest public model to POLARIS's citation-grounded compose DNA. BUT POLARIS's hard constraint is "the only new LLM call is the EXISTING generator role, no new model/slug" (§1) — so sui-1 enters as a Class-B *example + yardstick* for citation-grounded summarization, NOT a runtime adoptable and NOT a new crown (GenerationPrograms remains the lead Class-B adoptable, as a PATTERN on the existing writer). |

### Faithfulness-by-construction anchors + cautions

| Item | Year | Primary source | Role |
|---|---|---|---|
| Quotation = only faithful-by-construction form | 2025-08 | arXiv:2508.15396 (faithfulness survey) | The taxonomy anchor POLARIS's verbatim K-span fallback is built on. Confirms the extractive floor is the principled Class-B safety net. |
| "Deep Research Agents are Unreliable at Multi-turn Report" | 2026-01 | arXiv:2601.13217 | **Caution.** Multi-turn report agents lose faithfulness across turns — argues FOR POLARIS's single-pass, verify-each-sentence compose over agentic multi-turn rewriting. |
| TTD-DR (diffusion-style report gen) | 2025 | Google (no open weights) | YARDSTICK only — closed, non-sovereign. |

---

## 4. The cross-claim-synthesis trap (the repo already proved this — do NOT re-add a bag-of-atoms gate)

The single most important composition lesson is repo-grounded and load-bearing for every abstractive
frontier method. `abstract_conclusion.py:17-29` documents that a LABELED cross-claim author-summary
("reuses the body's entities + numbers but asserts a NEW relation / comparative / causal / safety
conclusion") was **DESIGNED then CUT, 2026-06-18**:

> "a first build added a `check_claim_atom_grounding` bag-of-atoms gate, but the PR-d replay harness proved
> it UNSOUND for exactly that class: a recombination of the body's own atoms ('X causes Y' when the body
> separately contains X, Y, and the word 'causes') has every atom present BY CONSTRUCTION, so
> presence-checking can never reject it. Catching atom-RECOMBINATION requires entailment of the synthesis
> sentence against the SPECIFIC cited claim — a judge call... Rather than ship a green harness over a gate
> that cannot do its job (a future landmine...), PR-d ships the safe subset that already renders — verbatim
> re-presentation, faithful by identity — and the unsound synthesis machinery is REMOVED."

This is the exact landmine **every** Class-A abstractive method steps on: OmniThink's reflective synthesis,
WriteHERE's recursive compose leaf, Deep-Reporter's incremental synthesis, AgentCPM-Report's deepening, any
"synthesize across sources" step. They all produce sentences that recombine source atoms into new relations,
and bag-of-atoms / presence checking cannot catch the fabrication. **Binding conclusion: abstractive
cross-source synthesis is ADD-only-if it ships an ENTAILMENT grounding gate** (the synthesis sentence
entailed against the specific cited claim, not its atoms). Absent that gate, abstractive synthesis is a
yardstick, not an adoptable — and the verbatim-re-presentation subset POLARIS ships is the correct floor.
GenerationPrograms is attractive precisely because its operations (paraphrase / compress / fuse over a
specific source) avoid free recombination — but a `fuse` across two sources is exactly the recombination
case, so even GenerationPrograms' fuse operation must be gated by per-clause entailment (which POLARIS's
multi-cited compose already does at the CLAUSE level, `verified_compose.py:44`).

This entry is an application of the standing rule (`feedback_avoidable_vs_structural_review_miss`): **a
recommendation that re-adds a described-but-unsound grounding gate is auto-reject** until it ships the
entailment check the repo already proved is required.

---

## 5. The isolation axis (composition QUALITY on a FIXED verified-evidence set — NOT e2e)

**Hold retrieval + consolidation + the faithfulness engine FIXED.** Bank a `corpus_snapshot.json` of N
already-verified baskets (the output of consolidation), and run each composition scaffold on the SAME input.
This isolates composition: it does NOT re-retrieve, NOT re-rank, NOT re-verify. Measure:

- **(a) Evidence coverage = how many of the N verified baskets the report actually RENDERS / cites.** This is
  the composition-controlled slice of breadth. Critical discipline: breadth-loss is *partly* consolidation's
  problem (other section); the part attributable to composition is strictly "given N baskets in, how many come
  out cited." Do NOT re-litigate retrieval/consolidation breadth here. (Ties to the I-arch-007 funnel:
  many baskets in, few rendered = a COMPOSE-stage funnel.)
- **(b) Organization** — section structure follows the outline; baskets routed to the right section;
  no orphaned / duplicated content; logical flow.
- **(c) Citation density + correctness** — every sentence carries a resolvable `[#ev:...]` → `[N]`; no
  uncited claim; no citation pointing to a span that does not support the sentence (insertion correctness,
  NOT re-running the verifier). ALCE citation-quality + LongCite sentence-level granularity are the metric defs.
- **(d) Faithfulness-preservation** — strict_verify pass-rate UNCHANGED vs the floor, ZERO new fabrications,
  the verbatim K-span fallback fires correctly on induced failures, no empty section. This is a fail-LOUD gate,
  not a score: a candidate that lifts coverage by relaxing faithfulness is disqualified (§-1.3).

**Clinical slice (structured clinical report sections).** On a banked clinical corpus_snapshot, the report
must render structured sections (efficacy / safety / dosing / contraindications / mechanism / regulatory) with:
NO safety-critical basket dropped at compose (a contraindication basket that exists in the input MUST appear
in the output); section structure preserved; the contraindication/negation polarity preserved verbatim
(no paraphrase that flips "not recommended" → "recommended"). A dropped safety basket or a flipped polarity is
an automatic fail regardless of (a)–(c).

**Behavioral acceptance (§-1.4):** the effect must APPEAR in the real rendered output on the banked corpus and
FAIL LOUD if it does not — not "green tests," not "Codex approved the diff." The standalone bake-off SELECTS
the mechanism; the integrated POLARIS run DECIDES; a §-1.1 line-by-line audit of the winning output is required
before any LOCK (per `standard_process_pipeline_section_review.md` step 6).

**Secondary measurement references (metric-def yardsticks for the isolation axis — NONE is a body writer):**
- **LongWeave** (2025-10, arXiv:2510.24345, CC0) — long-form benchmark with **Constraint-Verifier Evaluation
  (CoV-Eval)**: define verifiable targets, synthesize queries/materials/constraints, score against them
  (up to 64K/8K tokens, 23 models). The CoV-Eval *construction pattern* (objective, verifiable targets rather
  than a reference) is the right way to make §5(b)/(c) organization+citation checks objective; it reports even
  strong models cap well below ceiling on 8K outputs — a sober yardstick.
- **LongEval** (2025-02, arXiv:2502.19103) — long-text benchmark evaluating BOTH direct and plan-based
  paradigms (content quality, structural coherence, information density). The dual direct-vs-plan design is
  methodologically on-point for the §5 composition bake-off (free-but-verified prose vs program/plan-based
  compose).
- **Lost in Stories** (2026-03, arXiv:2603.05890) — **ConStory-Bench** consistency-error taxonomy (2,000
  prompts; 5 categories / 19 subtypes: factual, temporal, character, world-rule, causal) + ConStory-Checker
  (contradiction detection grounded in textual evidence). Narrative-domain, but the factual/temporal/causal
  inconsistency taxonomy is exactly what §5(d) faithfulness-preservation must watch for when a compose step
  recombines source atoms (§4) — a checklist of failure modes for the bake-off, not a clinical fixture.

---

## 6. KEEP vs ADD vs FIX against current POLARIS

**The compose step is genuinely ahead of the public stacks. Gaps are concentrated, not architectural.**

### KEEP (verified present and correct — Class-B, faithfulness-preserving)
- **STORM outline as structure-only scaffold** (`PG_STORM_OUTLINE_SECTIONS`). Correct, deliberate, principled.
  Keep; consider widening (ADD-1).
- **Per-basket verified-compose + verbatim K-span fallback** (`verified_compose.py`). The Class-B crown of the
  composition layer; never empty, fabrication degrades to quotation. Keep untouched in contract.
- **Abstract/conclusion verbatim re-presentation** (`abstract_conclusion.py`). Faithful-by-identity. Keep as
  the floor; do NOT re-add the unsound synthesis gate (§4).
- **Multi-cited per-clause compose** (`PG_VERIFIED_COMPOSE_MULTICITED`, `relational_quantifier_guard.py`). The
  clause-level (not whole-sentence) verify is the right granularity; it is the lever for safe `fuse`.
- **Same-span dedup keep-first with number-survival** (`dedup_same_span_sentences`). The B11 fix; keep.
- **Contract section runner slot-bound prose** (`contract_section_runner.py`). The clinical structured-section
  machinery; keep.
- **`[#ev:id:start-end]` provenance-token citation insertion**. The resolved-span identity is the right
  insertion primitive; keep.

### ADD / FIX (priority order — all advisory, the frozen gate is never relaxed)
1. **GenerationPrograms-pattern executable-operation compose (the biggest genuine ADD).** Reshape the
   verified-compose WRITER prompt so it emits an explicit PROGRAM of source-grounded operations
   (`quote(span)`, `paraphrase(span)`, `compress(span)`, `fuse(span_a, span_b)`) instead of free prose, then
   execute deterministically. Attribution becomes inherent; `quote` is the existing verbatim floor; `fuse` is
   gated by the existing per-clause entailment (`compose_multicited_sentence`). Uses the EXISTING generator
   role only — no new model. Flag-gated; behavioral acceptance = the program structure appears in the real
   output and faithfulness pass-rate is unchanged. *(Primary: arXiv:2506.14580.)*
2. **Verify the STORM-outline scaffold actually FIRES on the live run (wiring, not flag).** It is DEFAULT-OFF
   (`PG_STORM_OUTLINE_SECTIONS`) and the design doc flags the open wiring question ("is the STORM outline
   already threaded to the generation stage as the section scaffold?"). Confirm behaviorally that rendered
   sections == the STORM outline on a real corpus_snapshot before any coverage claim — this is the same
   "committed ≠ wired" class as I-arch-007 (`state/iarch_wiring_acceptance_checklist.md`).
3. **Coverage-funnel instrument at the compose stage (ties ADORE reflect-against-outline + I-arch-007).** Emit,
   per run, "N baskets in → M baskets rendered/cited" so a compose-stage breadth funnel is visible. ADORE's
   reflect-audit-against-outline (2601.18267) is the pattern: after compose, audit which outline sections /
   baskets got no rendered content and disclose them (already partly done as the empty-section disclosure).
4. **Cross-claim author-summary synthesis — ADD-only-if it ships the entailment gate (§4).** Do NOT re-add the
   bag-of-atoms gate. If labeled author-summary synthesis is wanted, build the per-claim entailment check first
   (the synthesis sentence entailed against the specific cited claim), reusing the existing entailment slate
   off the hot path. Until then, keep the verbatim-only subset.
5. **Checklist-guided incremental synthesis (Deep-Reporter pattern) as a coverage aid.** A per-section
   checklist of required baskets/entities, filled incrementally, with citation placement at fill time. Pairs
   with the contract section runner's slot model. Pattern-inspiration only (Deep-Reporter is multimodal/Class-A).

### DO NOT add
- **Any Class-A free-generation body writer** (STORM article stage, OmniThink/WriteHERE/LongWriter compose
  leaf, AgentCPM-Report deepening) as the section body — violates the provenance gate by construction.
- **Multi-turn agentic report rewriting** — 2601.13217 shows it loses faithfulness across turns; POLARIS's
  single-pass verify-each-sentence is the safer design.
- **A re-added bag-of-atoms grounding gate** for cross-claim synthesis — provably unsound (§4).
- **Any external Argus/eTracer/GenerationPrograms RUNTIME or new model slate** — patterns only; the only new
  LLM call stays the existing generator role (`polaris_runtime_lock.yaml` §9.1.8).

---

## 7. The composition bake-off candidate list (the next step)

Open-source-first (sovereignty). **Acceptance is behavioral (§5), not a vendor score:** run each candidate
on the banked `corpus_snapshot.json`, hold retrieval+consolidation+faithfulness FIXED, measure coverage /
organization / citation / faithfulness-preservation + the clinical slice. The standalone number selects; the
integrated POLARIS run decides; a §-1.1 audit gates the LOCK.

**Floor (the control arm):** current POLARIS verified-compose + STORM outline + abstract/conclusion-last.
Always in the bake-off — never bake-off only the new candidates.

**Compose-writer mechanism (Class-B, the real adoptable contest):**
- GenerationPrograms-pattern executable-operation writer (arXiv:2506.14580) — **lead candidate**
- Current free-but-verified prose writer (the floor)
- Multi-cited per-clause `fuse` variant (existing `PG_VERIFIED_COMPOSE_MULTICITED`, expanded)

**Outline scaffold (structure-only):**
- STORM outline (incumbent, `PG_STORM_OUTLINE_SECTIONS`) — floor
- AgentCPM-Report WARP revisable-outline pattern (arXiv:2602.06540) — does dynamic revision beat a fixed
  scaffold on coverage without hurting faithfulness?
- Co-STORM mind-map hierarchical organization (arXiv:2408.15232) — structure-organization contender

**Citation insertion / density (INSERTION only):**
- Current `[#ev:...]` token insertion (floor)
- FullCite constrained-decoding-over-citation-grammar (arXiv:2606.07130) — emit only well-formed
  span-anchored `[#ev:...]` tokens by construction
- LongCite sentence-level granularity target (arXiv:2409.02897) as the density/precision yardstick
- ALCE citation-quality metric (arXiv:2305.14627) as the metric definition

**Coverage / completeness pattern:**
- ADORE reflect-against-outline audit (arXiv:2601.18267)
- Deep-Reporter checklist-guided incremental synthesis (arXiv:2604.10741)

**Yardsticks-to-beat (Class-A / closed — NOT adoptable as body writer):**
- OmniThink (2501.09751), WriteHERE (2503.08275), LongWriter (2408.07055), DeepWriter (2507.14189),
  TTD-DR (closed). Bench POLARIS's output quality against these; never adopt their free-generation compose.

**Benchmarks (per `standard_process_pipeline_section_review.md`):** composition primarily drives BOTH axes but
is watched hardest on FAITHFULNESS (DeepTRACE) while not regressing COVERAGE (DeepResearch Bench II);
DeepScholar-Bench (live public faithfulness board) and ReportBench (2-axis regression) as secondary.

---

## 8. Honest uncertainty + license flags (verify before adoption)

### Uncertainty
- **Benchmark numbers are vendor/self-reported and not cross-comparable** (WriteHERE "outperforms SOTA on all
  metrics," LongCite citation F1, etc. are author-aligned). None is an independent head-to-head — hence the
  behavioral bake-off requirement (§5).
- **GenerationPrograms is the strongest adoptable on PATTERN grounds, but it has not been run on POLARIS's
  slate.** Frontier-tech rule: it is pattern-inspiration only until proven on GLM-5.2 on a banked corpus. The
  `fuse` operation specifically must be entailment-gated (§4) — do not assume the program structure alone
  guarantees faithfulness across two sources.
- **The clinical composition frontier is thin for TEXT deep-research.** Most 2025/2026 clinical report-gen is
  radiology/image-grounded (2510.00428, 2602.16006, 2603.16876) — not directly transferable. The convergent
  transferable pattern is "exclude unsupported findings / trace every reported finding to a deterministic
  feature," which POLARIS already enforces via strict_verify. The structured-section discipline is the
  transferable part, not the image models.
- **The multimodal text-chart frontier is orthogonal and OUT of scope.** Multimodal DeepResearcher
  (arXiv:2506.02454, June **2025** per arXiv — the gap-file "2026" label was wrong) generates text-chart
  interleaved reports from an agentic framework (research → exemplar textualization → plan → multimodal
  generation; "Formal Description of Visualization"). The structural pattern (agentic plan → execute across text
  AND chart blocks) is transferable in principle, but POLARIS's scope is TEXT composition (§Scope) and the
  multimodal slice is out — same orthogonality already noted for Deep-Reporter's multimodal scope (§3). Listed
  for completeness of the frontier snapshot, not as an adoptable.

### License flags
- **STORM / Co-STORM** (stanford-oval/storm): README states only the FreshWiki DATA license (CC-BY-SA). The
  CODE license must be read from the repo LICENSE file before any code reuse — **verify-before-adopt** (commonly
  MIT, but confirm). POLARIS uses the outline PATTERN, not the code, so this is low-risk as currently used.
- **AgentCPM-Report** (2602.06540): paper CC-BY-4.0; code/weights NOT confirmed available. Pattern-inspiration
  only.
- **GenerationPrograms** (2506.14580): code on GitHub, license not surfaced in the abstract — **verify before
  any code reuse.** Adopt as PATTERN regardless.
- **LongCite / LongWriter** (THUDM): open weights (LongCite-glm4-9b / -llama3.1-8b; LongWriter-glm4-9b) —
  verify each model-card license (THUDM weights are frequently under custom/Apache-mixed terms). Used as
  yardstick/metric, not a body writer, so low-risk.
- **OmniThink / WriteHERE / Deep-Reporter / ADORE / DeepWriter**: code released; arXiv-standard paper license;
  per-repo code license must be verified before any reuse. All used as PATTERN/yardstick, not runtime.
- **ALCE** (princeton-nlp/ALCE): EMNLP 2023, code on GitHub — used as metric definition only.
- **Clean to use as PATTERN/yardstick (no code/weights pulled into the sovereign binary):** all of the above.
  The ONLY new LLM call in composition stays the existing generator role under `polaris_runtime_lock.yaml`.

Verified current-POLARIS files: `multi_section_generator.py`, `verified_compose.py`,
`contract_section_runner.py`, `abstract_conclusion.py`, `key_findings.py`, `provenance_generator.py`,
`relational_quantifier_guard.py`, `abstractive_writer.py`, `analyst_synthesis.py`; design doc
`.codex/I-arch-011/composition_design_plan.md` (the canonical FLOW).

---

## 9. Recency audit (2026-06-24) — is this 2025/2026 frontier, or did old methods sneak in?

Operator challenge: "Are these the 2025/2026 best way, not old old methods?" Re-checked at research time;
every method date-verified against its primary source; reject pre-2024 unless it is the genuine incumbent floor.

**Verdict: frontier-current.** The only pre-2025 methods present are the genuine incumbent FLOOR (STORM 2024-02,
adopted outline-only) and explicit YARDSTICKS/metric-defs (ALCE 2023-05, LongCite/LongWriter 2024) — each
labeled as such, none crowned as the current adoptable. The adoptable contest is led by **GenerationPrograms
(2025-06)**, and the 2026 cohort (AgentCPM-Report 2026-02, ADORE 2026-01, Deep-Reporter 2026-04, the
2601.13217 multi-turn caution) is folded in.

**Recency-COMPLETE (2026-06-24, I-recency-001 #1296).** A completeness-critic pass surfaced 12 further
2025/2026 candidates the first draft missed; each was primary-source verified (exact title + date + license at
its arXiv page) and folded in above. **None displaces GenerationPrograms as the lead Class-B adoptable** and
**no dated-crown correction was warranted** (the gap audit flagged none, and the only open-weights Class-B
candidate — sui-1, a NEW 24B model — cannot be a runtime adoptable under the "only the existing generator role,
no new model" constraint, so it enters as an example/yardstick). The additions, by slot:
- **Outline-revision patterns (Class-A write step, scaffold pattern only):** UniCreative (2026-04, adaptive
  plan-vs-direct switching) — joins AgentCPM-Report/WARP.
- **Citation-correctness metric-defs (yardsticks, not methods):** TROVE (2025-03, fine-grained provenance +
  relationship taxonomy), Citation Grounding (2026-05, legal precision/relevance/temporality).
- **Multi-section synthesis (Class-A yardsticks/patterns; one Class-B EXAMPLE):** RAPID (2025-03, retrieval-aug
  outline+plan), Disco-RAG (2026-01, discourse-aware planning), Story2Proposal (2026-03, structural-contract
  multi-agent), Writer-R1 (2026-03, MRPO RL writing), **sui-1 (2026-01, open-weights 24B citation-grounded —
  example/yardstick only, NOT a new model adopted)**.
- **Isolation-axis measurement references (§5 metric-defs):** LongWeave (2025-10, CoV-Eval), LongEval
  (2025-02, direct-vs-plan), Lost in Stories (2026-03, ConStory consistency-error taxonomy).
- **§8 out-of-scope completeness note:** Multimodal DeepResearcher (date CORRECTED to 2025-06 per arXiv; the
  gap file's "2026" was wrong) — multimodal text-chart, orthogonal to text composition.
- Also reconciled FullCite (2026-06, already in §3/§7) into the §9 table + §10 list for table coherence.

| Method | Year | Status in this report |
|---|---|---|
| STORM | 2024-02 | Incumbent FLOOR; outline stage adopted (structure-only); article stage NOT adopted (Class A) |
| ALCE | 2023-05 | YARDSTICK / metric-definition only — not crowned |
| LongCite / LongWriter | 2024-09 / 2024-08 | YARDSTICK (citation granularity / long-output) — not a body writer |
| OmniThink | 2025-01 | Class-A yardstick; value is retrieval-loop, not composition |
| LongEval | 2025-02 | Benchmark (direct-vs-plan paradigms) — §5 metric-def yardstick |
| RAPID | 2025-03 | Class-A yardstick (retrieval-augmented outline + plan-then-write) |
| WriteHERE | 2025-03 | Class-A yardstick (recursive decomposition pattern) |
| TROVE | 2025-03 | Benchmark (fine-grained text provenance + relationship taxonomy) — citation-correctness metric def |
| GenerationPrograms | 2025-06 | **LEAD adoptable** (Class B; executable-operation compose) |
| Multimodal DeepResearcher | 2025-06 | OUT of scope (multimodal text-chart) — §8 completeness note |
| DeepWriter | 2025-07 | Class-A yardstick (offline-corpus grounded synthesis) |
| LongWeave | 2025-10 | Benchmark (CoV-Eval constraint-verifier) — §5 metric-def yardstick |
| ADORE | 2026-01 | Coverage pattern (reflect-against-outline) |
| Disco-RAG | 2026-01 | Class-A yardstick/pattern (discourse-aware RAG planning) |
| sui-1 | 2026-01 | Class-B-adjacent EXAMPLE/yardstick (open-weights 24B citation-grounded summarizer; no new model adopted) |
| AgentCPM-Report | 2026-02 | Outline-revision pattern (WARP); Class-A write step |
| Lost in Stories | 2026-03 | Benchmark (ConStory consistency-error taxonomy) — §5(d) failure-mode checklist |
| Story2Proposal | 2026-03 | Class-A pattern (structural-contract multi-agent manuscript writer) |
| Writer-R1 | 2026-03 | Class-A yardstick (memory-augmented RL writing, MRPO) |
| UniCreative | 2026-04 | Outline-revision pattern (adaptive plan-vs-direct switching); Class-A write step |
| Deep-Reporter | 2026-04 | Checklist-incremental-synthesis pattern (multimodal/Class A) |
| Citation Grounding (legal) | 2026-05 | Benchmark (citation precision/relevance/temporality) — citation-correctness metric def |
| FullCite | 2026-06 | Citation-insertion pattern (constrained decoding over citation grammar) |
| "Unreliable multi-turn report" | 2026-01 | Caution — argues for single-pass verify-each-sentence |

**What the recency pass says we should keep watching (the field moves monthly):** the 2026 long-form cohort
is converging on *revisable outlines* (WARP) + *reflect-against-outline coverage audits* (ADORE) +
*checklist-incremental synthesis* (Deep-Reporter). None is a Class-B body writer, so none displaces
GenerationPrograms as the adoptable; but all three are coverage/organization patterns worth a hard look in the
bake-off, and a fresh "is anything newer?" search should run again at bake-off time.

---

## 10. Primary sources (2025/2026)
- STORM — arXiv:2402.14207 ; github.com/stanford-oval/storm (incumbent outline floor)
- Co-STORM — arXiv:2408.15232 (mind-map structuring)
- GenerationPrograms — arXiv:2506.14580 (executable-operation attribution; LEAD adoptable, Class B)
- OmniThink — arXiv:2501.09751 (slow-thinking machine writing)
- WriteHERE / Beyond Outlining — arXiv:2503.08275 ; github.com/principia-ai/WriteHERE (recursive planning, EMNLP 2025)
- LongCite — arXiv:2409.02897 ; github.com/THUDM/LongCite (sentence-level citations)
- LongWriter — arXiv:2408.07055 ; github.com/THUDM/LongWriter (long-output, ICLR 2025)
- Deep-Reporter — arXiv:2604.10741 ; github.com/fangda-ye/Deep-Report (checklist-incremental synthesis, 2026)
- AgentCPM-Report — arXiv:2602.06540 (WARP revisable outline, 2026)
- ADORE / Trustworthy Enterprise RAG — arXiv:2601.18267 (reflect-against-outline, 2026)
- DeepWriter — arXiv:2507.14189 (offline-corpus grounded multimodal writing, 2025)
- "Deep Research Agents are Unreliable at Multi-turn Report" — arXiv:2601.13217 (multi-turn caution, 2026)
- ALCE — arXiv:2305.14627 ; github.com/princeton-nlp/ALCE (citation-eval benchmark, 2023 floor)
- Faithfulness survey (quotation = faithful-by-construction) — arXiv:2508.15396 (2025)
- FullCite (structured inline citation generation) — arXiv:2606.07130 (constrained-decoding citation grammar, 2026)
- RAPID — arXiv:2503.00751 ; github.com/USTC-StarTeam/RaPID (retrieval-augmented outline + plan-then-write, ACL 2025)
- LongWeave — arXiv:2510.24345 (CoV-Eval constraint-verifier long-form benchmark, 2025, CC0)
- LongEval — arXiv:2502.19103 (direct-vs-plan long-text benchmark, 2025)
- TROVE — arXiv:2503.15289 (fine-grained text-provenance benchmark + relationship taxonomy, 2025, CC-BY-4.0)
- Disco-RAG — arXiv:2601.04377 (discourse-aware RAG planning, 2026, CC-BY-4.0)
- sui-1 — arXiv:2601.08472 ; ellamind/sui-1-24b (open-weights citation-grounded summarizer, EXAMPLE/yardstick only, 2026, CC-BY-4.0)
- Story2Proposal — arXiv:2603.27065 ; github.com/AgentAlphaAGI/Idea2Paper (structural-contract multi-agent manuscript writer, 2026)
- Writer-R1 — arXiv:2603.15061 (memory-augmented RL writing / MRPO, 2026)
- Lost in Stories / ConStory-Bench — arXiv:2603.05890 (long-form consistency-error taxonomy, 2026)
- UniCreative — arXiv:2604.05517 (adaptive plan-vs-direct RL writing, Findings ACL 2026)
- Citation Grounding (legal) — arXiv:2606.00898 (citation precision/relevance/temporality, 2026, CC-BY-4.0)
- Multimodal DeepResearcher — arXiv:2506.02454 (text-chart interleaved reports, OUT of scope/multimodal, 2025)
- Cross-ref: consolidation (Argus/eTracer patterns) — `docs/consolidation_landscape_2026.md`
