# Adequacy Gate as an Iterative Sufficiency Loop — Design (2026)

Status: DESIGN (no code in this doc). Sovereign clinical pipeline (GLM-5.2 backbone).
Scope: the OUTER adequacy/sufficiency controller only. The sibling search-routing
strand is out of scope here.

Governing DNA: §-1.3 WEIGHT-AND-CONSOLIDATE (never FILTER-AND-CAP), §-1.1 line-by-line
(count/tier-floor proxies are BANNED quality signals), §-1.4 trace-the-path +
behavioral replay-harness. The faithfulness engine (strict_verify / NLI / 4-role /
provenance / span-grounding) is the ONLY hard gate and is NEVER touched by this design.

---

## 0. The one-paragraph thesis

This is **not greenfield**. POLARIS already contains a working gap-targeted
sufficiency loop — `saturation.py` (budget governor + novelty-flatten stop) wired to
`adequacy/plan_sufficiency_gate.py` (per-sub-question coverage) — but it is (a) **OFF
by default** (`PG_USE_RESEARCH_PLANNER=0`), (b) bolted to a SECOND, competing outer
gate (`nodes/corpus_adequacy_gate.py`) whose `expand` branch is a **dead-end** on the
production sweep, and (c) its gap step only **RE-FIRES the existing plan sub-queries**
(`gap_sub_queries`) rather than **synthesizing NEW gap-targeted queries**, and its gap
**detection is structural counting**, not a semantic "what is missing" diagnosis. The
design re-wires these surgically: route `corpus_adequacy`'s `expand` INTO the
saturation orchestrator, demote BOTH gates' count/tier floors (incl.
`plan_sufficiency_gate`'s own `covered_count >= evidence_target`) to advisory WARN, make the
SUFFICIENT determination **required-findings-answered + conflicts-resolved-or-surfaced**
(NOT a count — §3.4, P1-a fix; these set the SUFFICIENT-vs-PARTIAL label and trigger another
round, NEVER block rendering), and upgrade the gap step from "re-fire old queries" to "DETECT
the missing aspect, hand it to FS-Researcher (the #1296 winner; ∨ IterResearch fallback) +
required_entity_retrieval (targeted fetch), re-assess." Reuse saturation's existing
budget/novelty stop machinery for the knows-when-to-stop / no-infinite-loop axis. Budget/novelty exhaustion always
terminates as a **disclosed PARTIAL** (`partial_saturation`) — never as "adequate."

---

## 1. CURRENT FLOOR (grep + read, with file:line)

### 1.1 The named floor — `corpus_adequacy_gate.py` (single-pass, dead `expand`)

`src/polaris_graph/nodes/corpus_adequacy_gate.py`
- `assess_corpus_adequacy(...)` → `CorpusAdequacyReport(decision: "proceed"|"expand"|"abort")`
  (`corpus_adequacy_gate.py:217-341`). The decision is computed from **aggregate
  tier counts vs per-domain thresholds** (`_DEFAULT_DOMAIN_THRESHOLDS`,
  `corpus_adequacy_gate.py:121-186`): `min_total_sources`, `min_t1_count`,
  `min_t1_plus_t2`, `min_evidence_rows`, `max_t7_fraction`, etc.
- Decision rule: any `critical` finding → `abort`; any `warn` finding → `expand`;
  else `proceed` (`corpus_adequacy_gate.py:307-315`).
- The docstring itself names the `expand` branch as "run a second retrieval round
  with broader queries (**caller decides**)" (`corpus_adequacy_gate.py:11-13`).
- **The caller never decides.** In the production sweep
  (`scripts/run_honest_sweep_r3.py`) `assess_corpus_adequacy` is called at
  `:6750`, `:6920`, `:7024`, `:7223`, `:7286`, `:7439` and the only branch that
  changes control flow is `adequacy.decision == "abort"` (`:7618`) and the manifest
  status map at `:11406` (`elif adequacy.decision == "expand":` → it sets a *status
  label*, not a retrieval round). So `expand` is **a label, not a loop**. This is the
  dead branch the task names.
- BUG-20 fix (`corpus_adequacy_gate.py:32-79`): `count_grounded_rows` excludes
  content-less stubs from the grounded count — a real, correct fix; KEEP it. It is the
  one part of this gate that is claim-support-shaped (does the row carry content), not
  a raw count proxy.

### 1.2 The REAL loop that already exists (OFF by default)

`src/polaris_graph/adequacy/plan_sufficiency_gate.py` — `assess_plan_sufficiency(...)`
(`:309-414`). This is the **money-trap fix** and the correct *frame* — but only its SHAPE,
not its numeric threshold, survives P1-a. The right SHAPE: sufficiency is assessed
**per planned sub-question / per mapped facet** (claim-support per facet), NOT by aggregate
source-type counts the way `corpus_adequacy_gate` does. Today the gate computes that frame
as "does the billed corpus cover EVERY planned sub-question to its per-section
`evidence_target`, with EACH mapped facet having ≥ `MIN_PER_FACET` above-floor rows"
(`plan_sufficiency_gate.py:36-41, 368-373`; verdict at `:389-403`) — but
`covered_count ≥ evidence_target` and `≥ MIN_PER_FACET` are themselves **count floors**,
the §-1.1-banned proxy. §3.4 (P1-a) DEMOTES those numeric thresholds to ADVISORY WARN and
makes the SUFFICIENT determination required-findings-answered + conflicts-resolved-or-
surfaced instead. What we KEEP from this gate: the per-facet SHAPE and that relevance is
provenance-first with a content-word overlap fallback shared with the generator's on-mode
assignment via `relevant_section_indices` (`:162-228`) — so a section certified SUFFICIENT
actually RECEIVES its credited rows (no gate/router divergence).

`src/polaris_graph/retrieval/saturation.py` — the orchestrator:
- `run_saturation_loop(...)` (`:294-427`): PURE control flow; the live retrieval round
  is the **injected** `run_round_fn` (constructs no HTTP client, bills no token).
- `gap_sub_queries(sufficiency_report, plan)` (`:104-148`): the gap → query step. It
  fires the **empty-facet** sub-query texts, or (total shortfall) the WHOLE section's
  mapped sub-query texts. **Limitation: it only re-issues EXISTING plan sub-query
  strings** — it never synthesizes a new query for a newly-named missing aspect.
- `saturation_decision(...)` (`:151-184`): the **stop ladder** —
  `proceed→STOP_SUFFICIENT`, `abort→STOP_BUDGET`, rounds-exhausted→`STOP_BUDGET`,
  `round≥1 ∧ novelty<eps→STOP_NOVELTY`, else `CONTINUE`. Budget is checked BEFORE
  novelty.
- `preflight_round_budget(...)` (`:211-246`) + `per_query_discovery_cost(...)`
  (`:189-198`): **PRE-SPEND** worst-case truncation so cumulative discovery calls can
  never exceed `max_discovery_calls` (the budget governor).
- `marginal_novelty(...)` (`:71-101`): fraction of a new round's RAW rows novel by
  canonical URL vs the prior corpus (the flatten stop's signal).

Wiring in `scripts/run_honest_sweep_r3.py`: `_use_research_planner` gate at `:5982-5985`;
the saturation loop block runs only inside `if _use_research_planner:` —
`assess_plan_sufficiency` at `:9006`/`:9210`, `run_saturation_loop` at `:9244`, terminal
decision handling `STOP_SUFFICIENT` / `partial_saturation` at `:9277-9339`. **Default
OFF** ⇒ on the production sweep today the loop does not run; `corpus_adequacy_gate`'s
single-pass proceed/abort is what fires.

### 1.3 Inner loop already present (NOT wired to the outer controller)

`src/polaris_graph/retrieval/fs_researcher_query_gen.py` — `plan_fs_researcher_queries`
(`:79-151`): an `index.md` todo-queue + a **fixed 6-item self-review checklist**
("a question the KB cannot fully answer?", "an aspect with only 1-2 weak sources?")
whose output becomes the next round's deficient todos (`:137-149`). This IS a
gap-detector that synthesizes NEW queries — but it loops on **sub-topics internally**
during the FIRST retrieval pass; it is NOT the re-assessment loop, and its checklist is
not fed by the outer sufficiency verdict. Flag `PG_QGEN_FS_RESEARCHER` (`:39-41`),
bounded by `PG_QGEN_FS_RESEARCHER_MAX_QUERIES` (35) / `MAX_ROUNDS` (6).

**WINNER RECONCILED (added 2026-06-24 — reconciled to live code, supersedes an earlier
inverted note).** The production query-gen winner is **FS-Researcher**, NOT IterResearch.
Live code is authoritative: `scripts/run_honest_sweep_r3.py:6474-6480` and
`docs/standard_process_pipeline_section_review.md:38-44` both record that I-recency-001
(#1296) **FS-Researcher** (`src/polaris_graph/retrieval/fs_researcher_query_gen.py`,
arXiv:2602.01566) **SUPERSEDES IterResearch and takes PRECEDENCE** in the
`if _fs_researcher_enabled() or _iterresearch_enabled():` adaptive-query-gen block. The
re-bake-off was run under a positive-control-validated judge (FS-Researcher: general 0.561 /
clinical 0.351 — 2nd on both axes, never weak). **The earlier provisional IterResearch
"0.386" win did NOT reproduce** under the validated judge (0.000 general / ~0.232 clinical =
near-worst); that win was a harness artifact. IterResearch
(`src/polaris_graph/retrieval/iterresearch_query_gen.py`, I-qgen-002 #1292, arXiv:2510.24701
/ 2511.07327) **remains in-tree only as a FALLBACK** — flag `PG_QGEN_ITERRESEARCH` (`:35-37`),
default OFF, behind FS-Researcher's `PG_QGEN_FS_RESEARCHER`.

Both modules are valid NEW-query synthesizers built on the SAME shared seam: a report-centric
**workspace-RECONSTRUCTION** loop in which each round the GLM-5.2 policy re-derives the NEXT
query from "what is established vs still missing," retrieves through the UNCHANGED
`run_live_retrieval`, and folds the result back (strategic forgetting, O(1) context). Each
carries its own globally-unique `ev_NNN` renumber + sidecar/truncation merge contract
(IterResearch's `merge_retrieval_results` `:115-181`; FS-Researcher's `merge_retrieval_results`).

The honest consequence for §3.3 below: the gap→query lane wires to the **flag-active winner —
FS-Researcher by precedence**, with IterResearch as the fallback only when FS-Researcher is
disabled. The gap step feeds the named missing aspects into whichever path is active
(FS-Researcher's deficient-todos, or IterResearch's evolving report seeded with the gap),
both of which route through the same merge contract.

### 1.4 Gap → targeted FETCH mechanism already present

`src/polaris_graph/retrieval/required_entity_retrieval.py` — `run_required_entity_lane`
(builds targeted queries for a STILL-unsatisfied must-cover entity, fetches the
discovered URLs through the EXISTING `run_live_retrieval` seam, returns ordinary
evidence rows for corpus merge — `required_entity_retrieval.py:1-57`). This is the
"retrieve a specific missing thing" primitive. Faithfulness-safe: rows carry their REAL
fetched URLs, never relabeled to an entity (`:28-49`). Injected `search_fn`/`retrieval_fn`
(testable, no network in-module). Gated by `PG_REQUIRED_ENTITY_RETRIEVAL`.

### 1.5 Other floor pieces

- `crag_retriever.py:783-799` — CRAG gate `CORRECT/AMBIGUOUS/INCORRECT` (Yan et al.
  2024) over embedding-tier counts. A retrieval-confidence signal, not a per-claim
  sufficiency loop; reuse as ONE advisory input, not the controller.
- `agents/searcher.py` `execute_agentic_search` (`:291-292`) +
  `_generate_refinement_queries` (`:1208-1286`): an LLM "what is MISSING → follow-up
  queries" refiner, but it runs INSIDE the search node (benchmark-only), unbounded by
  the sufficiency verdict.

### Floor summary

The machinery for a real iterative sufficiency loop EXISTS and is mostly correct
(`plan_sufficiency_gate` + `saturation`). The three honest gaps: **(G1)** two competing
outer gates, the count-based one is the live default and its `expand` is dead;
**(G2)** gap-DETECTION is structural counting, not a "name the missing aspect"
diagnosis; **(G3)** gap→query only re-fires OLD plan queries, never synthesizes NEW
targeted queries (FS-Researcher [the current #1296 winner, precedence] + IterResearch
[#1292 fallback] + required_entity_retrieval, which DO synthesize, are not wired to the
outer verdict).

---

## 2. FRONTIER (2025/2026) — candidates, methods, dates, URLs, license

Every entry verified at the arXiv primary source this session (FRONTIER mandate).
"Incumbent floor" = pre-2024, kept only as conceptual baseline.

| # | Method | Date | Primary URL | License | What it contributes to THIS loop |
|---|--------|------|-------------|---------|----------------------------------|
| F1 | **A2RAG: Adaptive Agentic Graph Retrieval** | 2026-01-29 | arXiv:2601.21162 | arXiv (paper CC-BY); no repo found | **The twin of our target design.** "adaptive controller that **verifies evidence sufficiency** and triggers **targeted refinement only when necessary**" + an agentic retriever that **progressively escalates** effort with **stage-wise sufficiency checks**. Validates that POLARIS's saturation loop is a current-frontier pattern; donates the "escalate effort by STAGE" idea (cheap re-query → targeted fetch → broader) for the gap step. |
| F2 | **Stop-RAG: Value-Based Retrieval Control** | 2025-10-16 | arXiv:2510.14337 | arXiv; code not stated | Frontier **stopping criterion**: casts iterative RAG as a finite-horizon MDP, learns a **value function** ("value of continuing vs stopping") via Q(λ) targets. Donates the *concept* of a learned stop. **Heavy lift** (requires training a value model) — adopt as a future upgrade, not the v1 stop. |
| F3 | **HiPRAG: Hierarchical Process Rewards** | 2025-10-09 (v1), ICLR-2026 | arXiv:2510.07794 | paper CC-BY-SA-4.0; code not stated | Frontier **over/under-search control**: RL process reward grades EACH search step necessary/redundant; reduced over-searching to 2.3%, lowered under-searching. Donates the **diagnostic frame** (per-step "was this retrieval necessary / is one more needed"). Also training-based → concept, not v1 mechanism. |
| F4 | **SEAL-RAG: Loop-Adaptive RAG with on-the-fly gap localization** | 2025 (OpenReview) | openreview.net/pdf?id=QqjUfdPkkb | OpenReview submission (no OSS license) | The **gap-DETECTION** axis: **localizes the missing fact** and enforces fixed-k replacement; reported to beat Self-RAG by targeting insufficiency rather than just "retrieve more." Donates G2's core: **name the missing aspect, then go get exactly that** (vs our current structural counting). Inspiration only (no usable OSS license / not self-hostable as-is). **DEMOTED:** prefer **F11 FAIR-RAG** for this axis — same idea, an arXiv primary source with a faithfulness frame, no OpenReview-anonymity gap. |
| F5 | **Self-RAG (retrieve / critique / reflect tokens)** | 2023 (ICLR-2024) | arXiv:2310.11511 | MIT (code) | **Incumbent floor** for self-reflective sufficiency. Already embodied in POLARIS via the FS-Researcher 6-item checklist. Kept as the baseline the design must beat on gap-recall. |
| F6 | **CRAG (Corrective RAG)** | 2024-01 | arXiv:2401.15884 | (paper) | **Incumbent floor**, already in tree (`crag_retriever.py`). Its CORRECT/AMBIGUOUS/INCORRECT confidence tier is a usable advisory input, not the controller. |
| F7 | **FS-Researcher** | 2026 (arXiv 2602.01566, in-tree) | arXiv:2602.01566 | (in `fs_researcher_query_gen.py`) | Already the production query-gen winner (I-recency-001 #1296). Its todo-queue + 6-item checklist is the **NEW-query synthesizer** we wire the gap step to. |
| F8 | **IterDRAG / FLARE** | 2024 / 2023 | arXiv:2410.04343 / 2305.06983 | (papers) | **Incumbent floor** for interleaved retrieve-as-you-generate; not adopted (our loop is corpus-level pre-generation, by design — faithfulness verifies the composed report separately). |
| F9 | **ECR: Entropic Claim Resolution** | 2026-03-30 | arXiv:2603.28444 | paper CC-BY-4.0; no repo stated | **NEWER + the SOTA STOP axis the v1 ladder punts on.** Frames sufficiency as a *mathematically-defined* terminal state: stop when the entropy of the competing answer-hypothesis space falls below ε (`H ≤ ε`, "epistemic coherence"), selecting evidence by **Expected Entropy Reduction** ("retrieve what is most *discriminative*, not most *relevant*"). Donates a principled `STOP_SUFFICIENT` upgrade: terminate when added rows stop reducing answer-hypothesis entropy — strictly stronger than novelty-flatten (novelty stops when no NEW URLs arrive; ECR stops when no DISAGREEMENT remains). Method on our slate (no training). Bank as the v1.1 stop upgrade once a per-facet hypothesis-entropy estimator exists. |
| F10 | **AutoSearch: Adaptive Search Depth (RL)** | 2026-04-19 | arXiv:2604.17337 | arXiv distribution; no repo/license stated | **NEWEST on-point (supersedes A2RAG as most-recent).** Learns the **"minimal sufficient search depth"** — the accuracy/efficiency knee, *jointly determined by question complexity and agent capability* — via a self-answering reward that rewards reaching it and **penalizes over-searching**. Donates two ideas: (a) the budget cap should be *question-complexity-adaptive*, not a flat `max_rounds`; (b) a cheap **self-answer probe per round** as an additional `STOP_SUFFICIENT` signal (can the policy already answer the facet?). RL-trained → adopt the self-answer-probe *concept* on the heuristic ladder; defer the learned depth-policy (training lift, like Stop-RAG/HiPRAG). |
| F11 | **FAIR-RAG: Faithful Adaptive Iterative Refinement** | 2025-10-25 | arXiv:2510.22344 | paper; no repo/license stated | **The OSS-paper TWIN of THIS doc's whole G2+G3 design — and it is named *faithful*.** Its **Structured Evidence Assessment (SEA)** decomposes the query into a **checklist of required findings**, examines accumulated evidence to mark confirmed-vs-gap, and that gap signal drives an **Adaptive Query Refinement** agent that synthesizes targeted sub-queries — "repeats until the evidence is **verified as sufficient**." This is a cleaner-licensed, faithfulness-framed alternative to SEAL-RAG (F-prev, OpenReview, no license) for the G2 "name the missing aspect" axis. Donates: the gap diagnosis should emit a **named required-findings checklist** (not just empty-facet indices), and the loop terminus is "checklist verified sufficient." Inspiration/method only. |

**Honest OSS-vs-banned:** none of these are Exa/Tavily-adjacent (those are BANNED AI
search tools). A2RAG/Stop-RAG/HiPRAG/SEAL-RAG are **methods/algorithms**, applied on our
own sovereign GLM-5.2 slate and our own retrieval seam — sovereignty-clean. The only
plumbing remains Serper (raw search-API) + Zyte (paywall bypass), already in-tree and
allowed. No new external AI-search dependency is introduced.

**"Anything newer?" check (recency_check — refreshed 2026-06-24):** an adversarial
re-search of arXiv 2025/2026 for adaptive/agentic-RAG stopping criteria, sufficiency
verification, and gap detection surfaced THREE on-point papers NEWER or
better-licensed than the original table, now added above:
- **AutoSearch** (arXiv:2604.17337, **2026-04-19**) is now the **most-recent**
  directly-on-point paper (supersedes A2RAG's Jan-2026 recency crown). Self-answer
  "minimal sufficient search depth" + an explicit over-search penalty.
- **ECR / Entropic Claim Resolution** (arXiv:2603.28444, **2026-03-30**) gives the
  *mathematically-defined* sufficiency stop (`H ≤ ε`) that this design's §3.4 v1 ladder
  explicitly punts on — the single biggest upgrade target for the stop axis.
- **FAIR-RAG** (arXiv:2510.22344, 2025-10-25) is the *faithful*-framed, arXiv-sourced
  twin of this doc's G2+G3 (its SEA = required-findings checklist gap-detection) and
  should replace the OpenReview-only SEAL-RAG as the G2 reference.
DeepSearchQA (2601.20975, Jan 2026) remains a benchmark axis (gold-set, not a method).
Adjacent-but-out-of-scope: **A-RAG** (2602.03442), **GraphTracer** (2510.10581,
failure-tracing not sufficiency). Re-run this search before BUILD; the frontier moves
monthly and three of the top finds here post-date the doc's original authoring.

---

## 3. THE PROVISIONAL DESIGN TO BEAT (concrete, surgical)

The OUTER controller is the **sufficiency loop**; the active query-gen winner
(FS-Researcher #1296, precedence; ∨ IterResearch #1292 fallback — §1.3) is the INNER
per-todo loop nested inside each retrieval round. Reconcile the two gates; keep saturation's stop
machinery; upgrade only the gap-detect and gap→query hops. (§3.7 surfaces three
unknown-unknown axes — conflict-as-insufficiency, absence-vs-evidence-of-absence,
information-vs-URL novelty — that the original draft was silent on; conflict and
absence-vs-evidence-of-absence are now folded into the §3.4 SUFFICIENT determination,
information-vs-URL novelty is disclosed as a proxy with the entropy stop banked.)

### 3.1 Single outer controller — collapse the two gates

- **Promote `plan_sufficiency_gate`'s per-facet SHAPE to the loop's re-assessment check**
  (claim-support per facet, NOT aggregate source-type counts the way `corpus_adequacy_gate`
  scores). The per-facet SHAPE is the §-1.1/§-1.3-correct frame — but its numeric
  `covered_count ≥ evidence_target` / `≥ MIN_PER_FACET` thresholds are themselves count
  floors and are DEMOTED to advisory WARN (§3.4): the SUFFICIENT determination is
  required-findings-answered + conflicts-resolved-or-surfaced, never a count.
- **Demote `corpus_adequacy_gate` counts/tier-floors to ADVISORY WEIGHTS.** Its raw
  `min_total_sources`/`min_t1_count` floors are the exact metadata-count proxies §-1.1
  bans and that the I-arch-011 autopsy flagged as "avoidable negligence" when a floor
  is described-and-approved. Do NOT let a count threshold ABORT or terminate. Keep two
  honest signals from it: (a) `count_grounded_rows` (content-bearing, not raw count),
  surfaced as a telemetry weight; (b) `max_t7_fraction` stub-ratio as an advisory
  "corpus is mostly junk" WARN, not a hard gate.
- **Resolve the dead `expand` branch:** when `corpus_adequacy` (if still consulted on
  the legacy path) or `plan_sufficiency` returns `expand`, **route into
  `run_saturation_loop`** instead of falling through to a status label. This is the
  literal fix for the task's "the `expand` branch never loops back to query-gen."
- One default-ON flag for the unified path (proposal: `PG_ADEQUACY_LOOP`), so OFF is
  byte-identical to today (anti-regression discipline from every prior in-tree change).

### 3.2 Gap DETECTION — upgrade from counting to "name the missing aspect" (G2)

The re-assessment yields `PlanSufficiencyReport.per_unit` with `empty_facets` and the
ADVISORY `covered_count < evidence_target` WARN. That count is a *structural hint* for WHERE
to look — it points at a thin facet, but it does NOT by itself declare insufficiency (the
SUFFICIENT determination is required-findings + conflict per §3.4, not this count). Add a
**gap diagnosis** layer (FAIR-RAG Structured-Evidence-Assessment / SEAL-RAG-inspired —
emit a NAMED required-findings checklist; run on the GLM-5.2 policy, bounded):

For each under-covered unit, hand the GLM-5.2 critic: the section title, its mapped
sub-query texts, and an `_obs_digest` of the rows currently credited to it
(reuse `fs_researcher_query_gen._obs_digest`, `:69-76`). Ask it to NAME the specific
missing aspect(s) — the concrete entity / sub-claim / population / endpoint absent from
the credited evidence — as short phrases. This is a **diagnosis, not a stop relaxation**:
it only decides what to go fetch; it never decides whether a sentence verifies. (Clinical
care: the diagnosis must be a RETRIEVAL target, never a content suggestion — the gap
phrases are query seeds, the generator still composes only from fetched+verified rows.)

Recall is the axis: a structural-only detector misses an aspect that *is* nominally
"covered" by 1 weak row; the named-aspect critic catches "covered but only by a 2014
secondary source, primary RCT absent." Keep the structural `empty_facets` as the
floor; the critic is additive recall on top.

### 3.3 Gap → QUERY synthesis — wire to the NEW-query generators (G3)

Replace the gap-step's "re-fire old plan strings" with a two-lane gap-targeted
synthesis, mirroring A2RAG's "escalate effort by stage":

1. **Lane A — active query-gen gap queries (general).** Feed the named missing aspects
   (§3.2) into the **flag-active** query-gen winner (see §1.3). Two valid seams, pick the
   active one — **FS-Researcher takes precedence (#1296)**: (i) **FS-Researcher**
   (`plan_fs_researcher_queries`, reusing its "Write ONE search query for this sub-topic"
   prompt, `:121`) — feed the gaps as deficient-todos; (ii) **IterResearch**
   (`plan_iterresearch_queries`, the #1292 fallback) — seed its evolving report with the
   gap so the next derived query targets exactly the missing sub-topic. Either SYNTHESIZES
   new query strings for aspects the plan never had a sub-query for. Bounded by the existing
   `MAX_QUERIES`/`MAX_ROUNDS` (FS-Researcher) / `MAX_ROUNDS` (IterResearch).
2. **Lane B — required_entity_retrieval (clinical authority).** When a missing aspect
   maps to a must-cover safety entity (contraindication, dose limit, boxed warning,
   regulatory status), route it to `run_required_entity_lane` for an authority-biased
   targeted FETCH (DailyMed/FDA/EMA/NICE/Health Canada). This is the clinical-grade
   "go get exactly that label page" lane.
3. Merge both lanes' rows via the EXISTING merge contract (canonical-URL
   dedup + global `ev_NNN` renumber — `fs_researcher_query_gen.merge_retrieval_results`
   OR `iterresearch_query_gen.merge_retrieval_results`, both of which renumber to
   globally-unique `ev_NNN` and carry the sidecar/`corpus_truncated` contract — / the
   saturation gap-round merge). Faithfulness path unchanged.

Crucially: gap queries are issued through the SAME `run_live_retrieval`
(scope-gate → tier-classify → fetch → provenance), so every new row is weighted and
verified identically. No row is admitted by being "the answer to a gap" — it is admitted
only if it fetches real content and its sentences verify. **WEIGHT-AND-CONSOLIDATE: the
loop keeps ALL corroborating rows it finds; it never drops to hit a number** (§-1.3).

### 3.4 Re-assess → STOP (knows-when-to-stop, no infinite loop)

Reuse saturation's stop machinery VERBATIM for the budget/novelty axes
(`preflight_round_budget` + `marginal_novelty`). What CHANGES is the SUFFICIENT
determination feeding `saturation_decision`'s `verdict`.

**SUFFICIENT is NOT a count floor (P1-a fix, §-1.1/§-1.3-binding).** A `covered_count ≥
evidence_target` / "every facet above floor" test is exactly the metadata-count proxy §-1.1
bans and the I-arch-011 autopsy flagged as avoidable negligence when a floor is
described-and-approved. The v1 re-assessment, BEFORE it may declare a unit SUFFICIENT,
requires TWO substantive conditions (NOT a count):

1. **(i) The named REQUIRED-FINDINGS are answered.** Take the §3.2 gap-diagnosis output
   (the FAIR-RAG-SEA-style required-findings checklist for the unit) and confirm each
   named required finding is ANSWERED by ≥1 row whose sentences verify against the
   credited evidence. A unit with an OPEN named required finding is under-covered —
   regardless of how many rows it has.
2. **(ii) UNRESOLVED-CONFLICTS are resolved-or-explicitly-surfaced (§3.7 UU-2).** If the
   unit's basket carries an *unreconciled* contradiction
   (`contradiction_detector` / `semantic_conflict_detector` /
   `qualitative_conflict_detector`), the unit is under-covered until either a
   tie-breaking authority resolves it OR the conflict is explicitly surfaced for
   disclosure ("sources disagree on X: [a] vs [b]"). A facet "covered" by two
   contradicting sources is NOT sufficient.

These two conditions decide the **SUFFICIENT-vs-PARTIAL label** and, when unmet, **route
ANOTHER round** (or a terminal PARTIAL at budget/novelty exhaustion) — they are NEVER a
hard abort and NEVER block rendering. There is **no new binary hard gate here**: the report
always renders (sufficient units as normal prose, still-open units as disclosed-PARTIAL per
the invariant below). This is the §-1.3-safe framing — a smarter STOP decision, never a
higher wall.

**Counts are demoted to ADVISORY WARN only.** `covered_count` vs `evidence_target`,
`corpus_adequacy_gate`'s `min_total_sources` / `min_t1_count` / `min_t1_plus_t2`, and the
per-facet `MIN_PER_FACET` numeric threshold are surfaced as **telemetry WARN signals**
("unit U is thin: 1 row below the advisory target") for the operator and the gap-diagnosis
critic — but a count NEVER on its own makes a unit SUFFICIENT, never makes a unit
under-covered, never ABORTS, and never gates CONTINUE/STOP. The CONTINUE/STOP edge is driven
ONLY by required-findings + conflict (the SUFFICIENT axis) and the budget/novelty terminals;
a thin count alone can neither stop the loop nor force one more round. `plan_sufficiency_gate`'s per-facet structure (claim-support per facet, not
source-type counts) is the right SHAPE and stays; only its numeric `≥ evidence_target`
threshold is demoted from a determinant to an advisory weight.

Map to `saturation_decision`'s `verdict`: a unit is `proceed`-eligible only when (i) AND
(ii) hold for every planned unit; otherwise `expand` (rounds left) / `abort` (rounds
exhausted — which the ladder turns into STOP_BUDGET, a disclosed PARTIAL, never a
render-block). The four terminals are then:

- all units pass (i) AND (ii) → **STOP_SUFFICIENT** (required findings answered, conflicts
  resolved-or-surfaced). Proceed to generation.
- rounds exhausted (`round+1 ≥ max_rounds`) → **STOP_BUDGET**.
- pre-spend budget would exceed `max_discovery_calls` → **STOP_BUDGET** (truncate, then
  stop).
- `round≥1 ∧ novelty < eps` (the new round added <eps novel canonical URLs — the curve
  flattened, the web has no more) → **STOP_NOVELTY**. **NOTE (§3.7 UU-3):** `marginal_novelty`
  is canonical-URL novelty, a PROXY for information-novelty, not the thing itself; the v1
  ladder discloses this proxy status and banks the self-answer / entropy upgrade.

ADD an anti-spin guard for the named-aspect critic: if two consecutive rounds name
the SAME missing required finding AND novelty<eps for it, mark that finding **unfillable**
and stop chasing it — disclose it, do not loop. **CAUTION (§3.7 UU-1):** "unfillable" here
means *not located after N targeted queries across the tried lanes* (absence-of-evidence),
NOT "it does not exist" (evidence-of-absence). The disclosure MUST be worded as the former
and record which lanes were tried — conflating the two is a clinical-lethal fabrication of a
negative. (The conflict condition (ii) above already routes a tie-breaker round via the
required-entity authority lane before any STOP_SUFFICIENT — §3.7 UU-2; an unresolved
conflict is treated as under-covered, never as silently "covered.")

**Terminate-as-PARTIAL invariant (§-1.3, lethal otherwise):** STOP_BUDGET / STOP_NOVELTY
/ unfillable do NOT relabel the corpus "adequate." They emit the existing
`partial_saturation` status: sufficient sections render, under-covered sections
gap-DISCLOSE ("primary RCT evidence for X was not located in reachable sources"). The
loop NEVER reaches "adequate" by lowering the bar — only by actually covering the facets
or by honestly disclosing the residual gap. The faithfulness engine is untouched
throughout.

### 3.5 What is explicitly NOT changed

The faithfulness engine (strict_verify / NLI / 4-role / provenance / span-grounding);
the per-claim verdict; the generator's compose path. This design changes only WHICH
queries are issued and WHEN the retrieval loop stops — the §-1.3 "surgical, not rewrite"
constraint. Stop-RAG/HiPRAG learned controllers are deferred (training lift); the v1
stop is the proven heuristic ladder.

### 3.6 Nesting (the task's "OUTER controller" point, made precise)

```
OUTER: adequacy/sufficiency loop  (loops on OVERALL plan coverage)
  round r:
    run_live_retrieval(queries_r)        # scope→tier→fetch→provenance (UNCHANGED)
      INNER: active query-gen todo-queue  # FS-Researcher (current winner, precedence) or IterResearch (fallback)
                                          # — loops on SUB-TOPICS within the round
    select + merge → corpus_r            # via the existing ev_NNN-renumber merge contract
    reassess(corpus_r)                   # per-facet SHAPE; SUFFICIENT iff required-findings
                                         # ANSWERED + conflicts resolved-or-surfaced (NOT a
                                         # count — counts are advisory WARN; §3.4 P1-a)
    if all_required_findings_answered and all_conflicts_resolved_or_surfaced: STOP_SUFFICIENT
    else:
       gaps = diagnose_missing_aspects(under_covered_units)     # G2 (new; FAIR-RAG SEA / SEAL-style)
       queries_{r+1} = active_qgen(gaps) ∪ required_entity(gaps_clinical)  # G3 (FS-Researcher ∨ IterResearch)
       budget-preflight + novelty → CONTINUE | STOP_BUDGET | STOP_NOVELTY
  terminal != SUFFICIENT → partial_saturation (disclose residual gaps)
```

### 3.7 UNKNOWN-UNKNOWNS — what a 2025/2026 deep-research system handles that this doc never asked (added 2026-06-24)

The completeness critic surfaced THREE axes the original draft was silent on. Each is a
real frontier sufficiency concern, each is clinical-safety-relevant, and none relaxes
faithfulness — they make the STOP decision SMARTER, never the bar LOWER. **UU-1 and UU-2 are
NOW FOLDED into the v1 §3.4 SUFFICIENT determination; UU-3 is folded as a disclosed-proxy in
§3.4 with the information-theoretic stop banked for v1.1/v2.** The bodies below are retained
as the rationale for those folds.

- **UU-1 — absence-of-evidence vs evidence-of-absence (clinical-safety-critical). (NOW
  FOLDED into §3.4 as the unfillable-disclosure invariant.)** DeepSearchQA
  (arXiv:2601.20975) names this explicitly: an agent "must distinguish
  *'I have not found it yet'* from *'it does not exist.'*" A naive `unfillable`
  guard would **conflate the two** — marking an aspect unfillable purely on "2 rounds, same
  gap, novelty<eps," which is an *operational give-up*, not a "this evidence does not
  exist" claim. In clinical context the difference is lethal: disclosing *"no RCT was
  located in reachable sources"* (absence-of-evidence — could exist behind a paywall we
  failed to reach) is HONEST; silently implying *"no RCT exists"* (evidence-of-absence)
  is a fabrication of a negative. **§3.4 now binds this:** the `partial_saturation`
  disclosure for an unfillable aspect MUST be phrased as absence-of-evidence ("not located
  in the sources reached, having issued N targeted queries across M authority lanes"), NEVER
  as evidence-of-absence — and records WHICH lanes were tried (so a Zyte/DailyMed miss is
  visibly a reachability gap, not a non-existence claim). This is a disclosure-wording
  invariant, audited line-by-line per §-1.1.

- **UU-2 — conflicting evidence is a sufficiency signal, not just "covered." (NOW FOLDED
  into §3.4 condition (ii).)** As originally drafted, the design measured sufficiency as
  *"is each facet COVERED above floor"* and did NOT ask *"do the covering sources AGREE."*
  A facet "covered" by two sources that CONTRADICT each other (different dose ceiling,
  opposite contraindication verdict) is NOT sufficient in a clinical brief — it needs an
  ESCALATION round (go find the tie-breaking authority), not a `STOP_SUFFICIENT`. Frontier
  work treats this directly: *RAG with Conflicting Evidence* (arXiv:2504.13079) and
  conflict-resolution fact-checking (arXiv:2505.17762). POLARIS already HAS the detector —
  `retrieval/contradiction_detector.py` + `semantic_conflict_detector.py` +
  `qualitative_conflict_detector.py` — they were simply **not wired as a sufficiency
  input**. **This is now folded into the v1 SUFFICIENT determination as §3.4 condition (ii):**
  a `conflict_unresolved` signal on the per-facet verdict means a facet whose basket carries
  an *unreconciled* contradiction is treated as under-covered (triggers a targeted
  tie-breaker round via the required-entity authority lane), and if still unresolved at
  terminal it gap-DISCLOSES the conflict ("sources disagree on X: [a] vs [b]") rather than
  silently picking one. Consolidate-keep-all (§-1.3) already keeps both sides; this just
  makes the
  loop NOTICE the disagreement. Faithfulness is unchanged — the engine still verifies each
  side's sentence; this only changes WHETHER the loop stops.

- **UU-3 — the stop criterion is "no new URLs," not "no new INFORMATION."** §3.4's
  novelty signal (`marginal_novelty`) is purely **canonical-URL** novelty — a round that
  fetches 10 NEW urls all re-stating the SAME fact reads as "high novelty, keep going,"
  and a round that finds the ONE missing discriminating fact behind an
  already-seen-domain URL can read as "low novelty, stop." Frontier-2026 stop criteria
  are **information-theoretic, not URL-counting**: ECR (arXiv:2603.28444) stops on
  answer-hypothesis ENTROPY (`H ≤ ε` — retrieve what is most *discriminative*); AutoSearch
  (arXiv:2604.17337) uses a self-answer probe ("can I already answer this facet?") as the
  stop signal. **Patch (v1.1, banked):** augment URL-novelty with a per-facet
  discriminative signal — minimally, a cheap GLM-5.2 self-answer probe per under-covered
  facet (AutoSearch-style) as an ADDITIONAL `STOP_SUFFICIENT` gate, and bank ECR's
  entropy stop (`H ≤ ε` over the facet's competing answer hypotheses) as the principled
  v2 upgrade once a per-facet hypothesis-entropy estimator exists. Until then, keep
  URL-novelty as the v1 floor but DISCLOSE that it is a proxy for information-novelty, not
  the thing itself. (Does not touch faithfulness; it only refines the CONTINUE/STOP edge.)

These three are surgical wirings of machinery POLARIS already owns (conflict detectors,
GLM-5.2 policy, the disclosure path) — consistent with §-1.3 "surgical, not rewrite." UU-1
(absence-vs-evidence-of-absence disclosure wording) and UU-2 (conflict-as-insufficiency)
are now FOLDED into the v1 §3.4 SUFFICIENT determination — UU-2 as condition (ii)
(an unresolved conflict makes a facet under-covered, never silently "covered"), UU-1 as the
unfillable-disclosure invariant. UU-3 is partly folded: the v1 ladder keeps URL-novelty but
explicitly DISCLOSES it is a PROXY for information-novelty (§3.4 STOP_NOVELTY note); the
self-answer / entropy stop (`H ≤ ε`) that would stop on "no new INFORMATION" rather than
"no new URL" stays a v1.1/v2 bank (not yet built — LAW II: the proxy is honestly labeled,
not claimed solved).

---

## 4. AXIS + GOLD-SET SKETCH (how we prove it beats the floor)

**Axis (3 sub-metrics):**
1. **Gap-detection recall** — given a corpus with a KNOWN-missing aspect, does the
   detector FLAG that aspect? (structural-only floor vs +named-aspect critic.)
2. **Loop convergence** — once flagged, does an expansion round actually FILL the gap
   (the named required finding becomes ANSWERED, with no unresolved conflict left) within
   `max_rounds`? (Crossing the advisory `evidence_target` count is a WARN signal, NOT the
   convergence criterion — per P1-a/§3.4.)
3. **Knows-when-to-stop** — does the loop reach STOP_SUFFICIENT only when every required
   finding is answered AND every conflict is resolved-or-surfaced (no wasted round, no
   false "adequate" on a thin count), AND terminate at budget/novelty without spinning,
   AND correctly mark unfillable aspects PARTIAL (no infinite loop)?

**Gold-set (offline, no-spend, anchored to banked replay fixtures):**
- Reuse the §-1.4 replay harness: banked `corpus_snapshot.json` +
  `state/iarch007_corpus_checkpoints.json` / the I-arch-011 replay fixtures
  (`outputs/audits/b1b10_redesign/replay_fixtures/`). No re-retrieval — minutes, not
  hours.
- Construct **(corpus, known-missing-required-finding)** pairs by ABLATION: take a banked
  corpus that the audit confirmed sufficient for a section, DELETE the rows answering one
  named required finding → a labeled gap. Detector must flag it (recall); the gap→query
  lane (driven by a STUBBED `run_round_fn` that returns the deleted rows when the right
  query fires) must make the finding ANSWERED within N rounds (convergence); a corpus with
  an UNFILLABLE finding (stub returns nothing) must terminate PARTIAL, not spin (stop).
- Construct a **conflict pair** (UU-2): a corpus where a facet IS count-covered but its two
  rows CONTRADICT (e.g. opposite contraindication verdicts). The loop must treat it as
  under-covered (route a tie-breaker round), and — if still unresolved at terminal —
  gap-DISCLOSE the conflict, NEVER reach STOP_SUFFICIENT on the count alone.
- **Behavioral acceptance (§-1.4, not diff-approval):** a harness that FAILS LOUD
  (non-zero exit) if (a) a labeled gap is not flagged, (b) a fillable gap is not answered
  in ≤ max_rounds, (c) the loop runs > max_rounds (spin), (d) a budget/novelty stop
  mislabels a PARTIAL corpus as `success`, (e) a count-covered-but-conflicted facet reaches
  STOP_SUFFICIENT, or (f) a count-only threshold (advisory) is allowed to ABORT or
  terminate. "Codex-approved + green tests" is NOT acceptance; the effect must APPEAR in the
  replayed output.
- Negative control: with `PG_ADEQUACY_LOOP=0`, the harness must show byte-identical
  single-pass behavior (anti-regression).

**Faithfulness guard in the gold-set:** assert that NO row admitted by the gap loop
bypasses strict_verify, and that a terminal PARTIAL never renders a sentence the
faithfulness engine would drop. Adequacy is NEVER claimed by relaxing faithfulness.

---

## 5. Provisional pick

Build the **unified sufficiency loop** (§3) on the EXISTING `plan_sufficiency_gate` +
`saturation` machinery — promote its per-facet SHAPE to default-ON behind
`PG_ADEQUACY_LOOP`, demote BOTH gates' count floors (`corpus_adequacy_gate`'s tier counts
AND `plan_sufficiency_gate`'s own `covered_count ≥ evidence_target`) to advisory WARN, add
the FAIR-RAG-/SEAL-RAG-style
named-aspect gap diagnosis (G2 — emit a required-findings checklist, FAIR-RAG SEA frame),
and wire the gap step to the **flag-active query-gen winner** (FS-Researcher #1296,
precedence; ∨ IterResearch #1292 fallback) + required_entity_retrieval for NEW-query
synthesis (G3). Make the v1 SUFFICIENT determination required-findings-answered +
conflicts-resolved-or-surfaced (NOT a count floor — §3.4); the count thresholds are
advisory WARN only. Keep saturation's stop ladder as the v1 stopping criterion; bank
Stop-RAG/HiPRAG learned controllers AND
ECR's entropy stop (`H ≤ ε`) + AutoSearch's self-answer-depth probe (§3.7 UU-3) as the
v1.1/v2 stop upgrades. AutoSearch (Apr 2026) / A2RAG (Jan 2026) are the design's external
validation that this stage-wise-sufficiency pattern is 2026-frontier. Wire the existing
conflict detectors as a sufficiency input (§3.7 UU-2) and phrase unfillable-aspect
disclosures as absence-of-evidence, never evidence-of-absence (§3.7 UU-1). This is surgical
re-wiring of proven in-tree modules, not a rewrite, and the faithfulness engine is never
touched.

---

## Appendix — primary sources consulted (this session)

- A2RAG — arXiv:2601.21162 (2026-01-29)
- Stop-RAG — arXiv:2510.14337 (2025-10-16)
- HiPRAG — arXiv:2510.07794 (2025-10-09; ICLR-2026; paper CC-BY-SA-4.0)
- SEAL-RAG — openreview.net/pdf?id=QqjUfdPkkb (2025) — DEMOTED in favour of FAIR-RAG
- DeepSearchQA — arXiv:2601.20975 (2026-01-30, benchmark for stopping-criterion axis)
- Self-RAG — arXiv:2310.11511 (incumbent floor, MIT code)
- CRAG — arXiv:2401.15884 (incumbent floor, in-tree)
- FS-Researcher — arXiv:2602.01566 (in-tree query-gen WINNER, I-recency-001 #1296, precedence)
- Added 2026-06-24 (adversarial completeness re-search, all primary-source verified):
  - **AutoSearch** — arXiv:2604.17337 (2026-04-19, NEWEST on-point; minimal-sufficient-depth + over-search penalty)
  - **ECR / Entropic Claim Resolution** — arXiv:2603.28444 (2026-03-30, CC-BY-4.0; `H ≤ ε` epistemic-sufficiency stop)
  - **FAIR-RAG** — arXiv:2510.22344 (2025-10-25; Structured Evidence Assessment = required-findings checklist, faithful frame)
  - **RAG with Conflicting Evidence** — arXiv:2504.13079 (conflict-as-insufficiency, UU-2)
  - **Conflict-resolution fact-checking** — arXiv:2505.17762 (UU-2)
  - **IterResearch** — arXiv:2510.24701 / 2511.07327 (in-tree query-gen FALLBACK, I-qgen-002 #1292; superseded by FS-Researcher #1296)
- In-tree floor: `nodes/corpus_adequacy_gate.py`, `adequacy/plan_sufficiency_gate.py`,
  `retrieval/saturation.py`, `retrieval/fs_researcher_query_gen.py`,
  `retrieval/iterresearch_query_gen.py` (query-gen FALLBACK, #1292; superseded by FS-Researcher #1296),
  `retrieval/required_entity_retrieval.py`, `retrieval/crag_retriever.py`,
  `retrieval/contradiction_detector.py`, `retrieval/semantic_conflict_detector.py`,
  `retrieval/qualitative_conflict_detector.py`,
  `agents/searcher.py`, `scripts/run_honest_sweep_r3.py`.

---

## Completeness note (critic pass — 2026-06-24)

Independent completeness + unknown-unknowns critic pass against the 2025/2026 frontier.

**Additions (verified at the arXiv primary source this pass; OSS-method / sovereignty-clean,
no Exa/Tavily, applied on our own GLM-5.2 slate):**
- **F9 ECR** (arXiv:2603.28444, 2026-03-30) — the mathematically-defined `H ≤ ε`
  epistemic-sufficiency stop the v1 ladder admits it punts on. The single biggest stop-axis
  upgrade target.
- **F10 AutoSearch** (arXiv:2604.17337, 2026-04-19) — NOW the most-recent on-point paper
  (supersedes A2RAG's recency crown); minimal-sufficient-depth + self-answer probe + an
  explicit over-search penalty.
- **F11 FAIR-RAG** (arXiv:2510.22344, 2025-10-25) — the *faithful*-framed arXiv twin of this
  doc's G2+G3; its Structured Evidence Assessment (required-findings checklist) replaces the
  OpenReview-only SEAL-RAG (F4 DEMOTED) as the G2 reference.

**Winner reconciled to live code:** the production query-gen winner is **FS-Researcher**
(I-recency-001 #1296), which **SUPERSEDES IterResearch and takes PRECEDENCE** —
authoritative per `scripts/run_honest_sweep_r3.py:6474-6480` (FS-Researcher checked first
in the `if _fs_researcher_enabled() or _iterresearch_enabled():` block) and
`docs/standard_process_pipeline_section_review.md:38-44`. IterResearch's earlier provisional
"0.386" win did NOT reproduce under the positive-control-validated judge (0.000 general /
~0.232 clinical = near-worst); it remains in-tree only as a default-OFF FALLBACK
(`PG_QGEN_ITERRESEARCH`). An earlier note in this doc had the direction inverted; §1.3, §3.3,
§3.6, §5 are patched to wire the gap step to the flag-active winner — FS-Researcher by
precedence, IterResearch as the fallback.

**Unknown-unknowns surfaced (§3.7) — axes a 2025/2026 deep-research system handles that the
original draft never asked. UU-1 and UU-2 are NOW FOLDED into the v1 §3.4 SUFFICIENT
determination; UU-3 is folded as a disclosed-proxy with the information-theoretic stop
banked:**
- **UU-1** absence-of-evidence vs evidence-of-absence (DeepSearchQA names it) — a naive
  `unfillable` guard would conflate an operational give-up with a "does-not-exist" claim;
  clinical-lethal if disclosed wrong. NOW FOLDED as §3.4's unfillable-disclosure-wording
  invariant (absence-of-evidence phrasing + which-lanes-tried record).
- **UU-2** conflicting evidence as a sufficiency signal — the original draft scored
  sufficiency as "covered," never "do the sources AGREE"; a facet covered by two
  contradicting sources is NOT sufficient. POLARIS already owns the conflict detectors; they
  were just not wired as a sufficiency input. NOW FOLDED as §3.4 condition (ii).
- **UU-3** the stop is "no new URLs," not "no new INFORMATION" — `marginal_novelty` is
  canonical-URL novelty, not information novelty. The v1 ladder keeps URL-novelty but
  DISCLOSES it as a proxy (§3.4 STOP_NOVELTY note); the ECR/AutoSearch information-theoretic
  stop ("no new INFORMATION") stays a v1.1/v2 bank (not yet built).

All three UUs are surgical wirings of machinery POLARIS already owns and NEVER relax
faithfulness — they make the STOP decision smarter, not the bar lower (§-1.3).

**Rejected / not added:** Stop-RAG, HiPRAG (already present as incumbent/learned-controller
banks — training lift, deferred, not new); A-RAG (2602.03442) and GraphTracer (2510.10581)
adjacent but out of this controller's scope; no Exa/Tavily-adjacent or pre-2024
non-incumbent or non-OSS-method candidate was admitted (LAW II). Re-run the recency search
before BUILD — three of this pass's top finds post-date the doc's original authoring, so the
frontier is provably still moving.
