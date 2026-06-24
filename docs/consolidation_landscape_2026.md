# Consolidation/Baskets Landscape 2025/2026 (I-cons-001 #1295)

Serial deep-research, 7 facets, primary-source verified, grounded against POLARIS fact_dedup/finding_dedup/weighted_enrichment.

All gaps closed. Facet-4 confirmed: `MAX_PAIRS=60`, `MAX_ROWS=200`, default judge `z-ai/glm-5.2`, default-OFF. Facet-5 confirmed: `PG_SECTION_DISTILL` gate, `contradiction_key` string field used for conflict clustering. `claim_graph` confirmed default-OFF (`PG_SWEEP_CLAIM_GRAPH`, empty default). 

The facet-7 input (deepresearch_stack_consolidation) is truncated in my input — it ends mid-sentence at `weighted_enrichment.select_unbo` with no `best_practice_2025_2026`, `bakeoff_candidates`, or `license_flags`. I'll flag that honestly per LAW II. Now writing the report as my final message.

---

# POLARIS Basket-Pipeline Landscape Report — I-cons-001 (#1295)

## Section 0 — How this report is grounded

This report synthesizes 7 facet researches into one map of the 2025/2026 best practice for the consolidation-and-baskets layer of POLARIS, and what to keep, add, or fix.

Two honesty notes up front, per LAW II.

First, I verified every load-bearing claim about the current POLARIS code against the repo myself. I read the actual files. The verified files are: `claim_atom_extractor.py`, `finding_dedup.py`, `credibility_pass.py`, `weighted_enrichment.py`, `weight_mass.py`, `calibration_metrics.py`, `semantic_conflict_detector.py`, `claim_graph.py`, `evidence_distiller.py`, `both_sides.py`, `atomic_decomposer.py`, and `live_retriever.py`. One facet path was wrong in the input and I corrected it: the semantic NLI conflict detector lives at `src/polaris_graph/retrieval/semantic_conflict_detector.py`, not under `synthesis/`. The defaults it claims (60 judged pairs, 200 rows, GLM-5.2 judge, default-off) are correct.

Second, the seventh facet input — deepresearch_stack_consolidation — arrived truncated. It ends mid-sentence inside its current-POLARIS description and carries no best-practice list, no bake-off candidates, and no license flags. So this report covers that facet only for the current-POLARIS state it did describe (claim-level and work-level keep-all baskets ahead of public STORM and GPT-Researcher, which dedup only at the URL level). Sections 1 and 4 mark it as input-incomplete rather than inventing entries.

The frozen-engine rule governs everything below. The faithfulness engine — strict_verify, the NLI entailment check, the 4-role D8 release policy, provenance, span-grounding — is the only hard gate and is never touched. Every item in this report is an advisory weight, a consolidation, or a label that feeds that frozen engine. Nothing here relaxes a verify gate. This is the weight-and-consolidate DNA, not filter-and-cap.

---

## Section 1 — Per-facet best-practice recipe table (2025/2026)

One named tool per row. License and role in short cells.

### Facet 1 — Atomic claim extraction

| Tool | License | Role |
|---|---|---|
| Claimify (Microsoft) | Paper CC-BY-4.0; no official code | Method: 4-stage LLM extraction that drops a claim when ambiguity cannot be resolved. Re-implement in-house. |
| CORE (zipJiang) | MIT | OSS pick: entailment filter plus MILP dedup to a minimal non-redundant claim set. Sovereign via local NLI or vLLM. |
| MedScore | License unconfirmed | Clinical-domain decomposer. Replaces the hardcoded clinical regex vocabulary. Verify license first. |
| VeriScore | Apache-2.0 | OSS pick: open-weight extractor that keeps only verifiable claims. Pre-filters opinion before decomposition. |
| DnDScore | Paper open | Method: decontextualize each atom so paraphrases compare, without losing the qualifier. |

### Facet 2 — Same-claim clustering and basketing

| Tool | License | Role |
|---|---|---|
| Qwen3-Embedding-8B | Apache-2.0 | OSS pick: the basket vectorizer. POLARIS already chose this in I-arch-009 for the quality gate. Reuse it. |
| bge-m3 (BAAI) | MIT | OSS pick: the MultiClaimNet-winning multilingual embedder. Dense plus sparse in one model. |
| sentence-transformers | Apache-2.0 | OSS engine: community-detection and agglomerative clustering, keep-all members. The exact SOTA recipe. |
| MultiClaimNet | Dataset, verify Zenodo | Method: embed then agglomerative cluster is the 2025 same-claim SOTA (0.574 ARI). |

### Facet 3 — Multi-source corroboration and weighting

| Tool | License | Role |
|---|---|---|
| crowd-kit | Apache-2.0 | OSS pick: reliability-aware truth discovery (Dawid-Skene, M-MSR). Replaces the flat origin count. |
| scikit-learn | BSD-3 | OSS engine: calibration backbone to wire the dead `calibration_metrics.py`. |
| CRED-1 | CC-BY-4.0 | OSS pick: offline negative-signal domain table. Down-weights known-bad domains only. Never up-weights. |
| Vinod and Erk uncertainty-gated fact-checking | Paper CC-BY-4.0 | Method, native clinical domain: corroborate only when basket confidence is low; abstain rather than override. |

### Facet 4 — Contradiction, stance, conflict

| Tool | License | Role |
|---|---|---|
| ModernCE-large-nli | MIT | OSS pick: local always-on NLI cross-encoder. 8192 context, 1.8GB. Replaces the capped remote GLM judge. |
| MoritzLaurer deberta-v3-large-zeroshot-v2.0-c | MIT base, c-variant data clean | OSS pick: zero-shot stance via hypothesis templates, sovereign-safe. |
| ConflictRAG | No license declared | Method: cheap-classifier-first then LLM-only-on-hard-pairs; credibility-weighted arbitration. Pattern only. |
| NegEx / ConText | Public-domain method | Already in POLARIS: deterministic present/absent assertion polarity. The no-LLM contraindication detector. |

### Facet 5 — Multi-doc consolidate, distill, map-reduce

| Tool | License | Role |
|---|---|---|
| LLMxMapReduce V1 | Apache-2.0 | OSS pick: structured-information protocol plus in-context confidence calibration at reduce time. |
| LLMxMapReduce-V2 | Apache-2.0 | OSS pick: hierarchical entropy-driven scaling for wide-corpus long-form grounded reports. |
| CAHM | MIT | OSS pick: bottom-up recursive merge with re-grounding at each level. Lightest to port. Closest to POLARIS span-grounded ethos. |
| LangGraph map-reduce | MIT | Parity baseline: POLARIS asyncio fan-out already equals this. Not a gap-closer. |

### Facet 6 — Set-based claim verification

| Tool | License | Role |
|---|---|---|
| MiniCheck (Flan-T5 / DeBERTa) | Apache lib, open weights | OSS pick: per-member entailment primitive feeding a set aggregator. Not a gate. 7B variant is non-commercial — avoid it. |
| RAGChecker | Apache-2.0 | OSS pick: claim-versus-context-set entailment, judge swappable. Offline replay scorer. |
| Dual-perspective credibility-weighted aggregation | Paper CC-BY-4.0 | Method: combine per-member verdicts into one calibrated basket confidence plus a conflict label. |
| MedRAGChecker | Repo TBD; students open | Method, clinical-native: calibrated set-support score over the whole set, plus a safety-error rate. |

### Facet 7 — Deep-research stack consolidation

Input incomplete. The facet text was truncated and carried no best-practice list. The only grounded fact it gave: POLARIS already consolidates at claim level and work level, ahead of the public STORM and GPT-Researcher stacks, which dedup only at the URL level. No tool table can be built from the input as received.

---

## Section 2 — THE BASKET PIPELINE: the ordered chain

This is the spine. Six steps, in order. For each step: the 2025/2026 SOTA method, the open-source pick, and the POLARIS plug-point.

### Step 1 — Atomic claims (from prose to checkable atoms)

- SOTA method: Claimify four stages — split, select only verifiable propositions, disambiguate and drop when ambiguity cannot be resolved, decompose into self-contained atoms. The drop-on-ambiguity rule matches the clinical never-fabricate posture.
- OSS pick: VeriScore (Apache-2.0) as a pre-filter for verifiable-versus-not, then CORE (MIT) for entailment-filtered atoms.
- POLARIS plug-point: `claim_atom_extractor.py`. Confirmed live — imported by `multi_section_generator.py`, `evidence_distiller.py`, `sentinel_contract.py`, and `atom_refusal_validator.py`. It is pure regex with a hardcoded clinical vocabulary and no LLM. The plug-in adds a span-faithful LLM decomposer beside it for out-of-vocabulary and non-clinical claims.

### Step 2 — Clustering into baskets (group same-claim sources)

- SOTA method: embed each decontextualized claim, then agglomerative or community-detection clustering at a distance threshold, keep-all members. MultiClaimNet recipe.
- OSS pick: Qwen3-Embedding-8B (Apache-2.0, already in-tree) plus sentence-transformers community detection. A hybrid lexical-plus-dense candidate generation, then an NLI same-claim confirm, to preserve the conservative never-over-merge rule.
- POLARIS plug-point: `finding_dedup.py` and `fact_dedup.py` group by literal numeric keys or exact content-word Jaccard. `claim_graph.py` is the field-agnostic upgrade already in-tree but default-off (`PG_SWEEP_CLAIM_GRAPH`, confirmed empty default). Swap its SHA-1 literal-key grouping for embedding-plus-NLI grouping.

### Step 3 — Corroboration and weighting (decide basket strength)

- SOTA method: reliability-aware truth discovery — a source's weight reflects its agreement with other credible sources, not just its venue. Plus a negative-signal domain down-weight.
- OSS pick: crowd-kit Dawid-Skene or M-MSR (Apache-2.0) for reliability-weighted consensus; CRED-1 (CC-BY-4.0) as a down-weight-only overlay for known-bad domains.
- POLARIS plug-point: `weight_mass.py` sums authority over independent origins, copies count zero — confirmed, and confirmed default-off with no production caller. `corroboration.py` counts independent registrable domains. The plug-in upgrades the flat count to a reliability-weighted consensus, weight-only, never adding to any count.

### Step 4 — Conflict detection (find disagreement inside a basket)

- SOTA method: run NLI over every basket pair to catch prose-only directional disagreement with no number and no assertion cue, then arbitrate by credibility weight.
- OSS pick: ModernCE-large-nli (MIT, local, 8192 context). Always-on, zero API spend, no socket-hang class.
- POLARIS plug-point: `semantic_conflict_detector.py` (under `retrieval/`, confirmed). It is a remote GLM-5.2 judge, default-off, hard-capped to 60 judged pairs and 200 rows. The frozen-engine constraint holds: this detector is advisory, it feeds labels and the both-sides composer, it never gates a sentence. ModernCE makes the capped optional pass an always-on local basket attribute.

### Step 5 — Set verification (does the whole basket support the claim?)

- SOTA method: a calibrated set-level support score that fuses per-member verdicts plus corroboration weight plus agreement into one probability, with an explicit conflicting or cherry-picking label.
- OSS pick: MiniCheck as the per-member primitive feeding a set aggregator; the dual-perspective credibility-weighted aggregation pattern for the calibrated confidence.
- POLARIS plug-point: `credibility_pass.py`, the `_verify_member_in_isolation` path. Critical constraint, verified at line 369: each member is verified alone, against its own span, with exactly one provenance token so the verifier cannot aggregate spans across members. This is the anti-laundering invariant. No frontier set-verifier may concatenate basket spans into a joint-entailment gate — that re-opens evidence laundering. The set layer is admissible only as an advisory confidence over already-isolated per-member verdicts.

### Step 6 — Synthesis and reduce (compose one grounded answer)

- SOTA method: hierarchical or iterative merge that preserves cross-source structure as the corpus grows, with conflict resolved at reduce time by confidence calibration. Not a flat single pass.
- OSS pick: CAHM (MIT) for the recursive re-grounded merge shape; LLMxMapReduce V1 (Apache-2.0) for the confidence-calibration reduce.
- POLARIS plug-point: `evidence_distiller.py`, gated by `PG_SECTION_DISTILL` (confirmed). The map step is per-source and fail-closed today. The reduce is a single-pass per-section compose, and conflict clustering uses exact-string `contradiction_key` equality (confirmed). Upgrade only the reduce shape and the conflict protocol. The reduce still feeds the frozen strict_verify; it never resolves conflict in place of it.

---

## Section 3 — KEEP vs ADD vs FIX against current POLARIS

Honest, weight-and-consolidate DNA, faithfulness engine frozen.

### KEEP — POLARIS is genuinely ahead here

- The keep-all basket primitive. `ClaimBasket` keeps every supporting member, never drops. This is ahead of the public deep-research stacks, which dedup only at URL level.
- Claim-level and work-level consolidation. `finding_dedup.py` keeps all same-claim rows as a basket under the redesign flag and de-pads same-work duplicates so N URLs of one paper count as one origin.
- The anti-laundering single-token isolation in `credibility_pass.py`. This is a correct, deliberate defense. Do not let any set-verifier override it.
- The frozen faithfulness engine. Untouched by everything in this report.
- The breadth-surfacing rule in `weighted_enrichment.py`: full ordered list, keep-all, sort-below-floor-last, no cap.

### ADD — the real gaps, advisory only

- Semantic and paraphrase clustering. This is the single biggest real gap. Today grouping is literal — numeric signatures or exact Jaccard. Two paraphrases of one clinical claim, for example "not recommended" versus "should be avoided" versus "contraindicated", never land in one basket, so corroboration is under-counted exactly where the DNA needs it. Add embedding-plus-NLI clustering.
- Calibrated basket confidence. Today a basket carries a 4-value label and an uncalibrated weight. Add a Beta-Binomial or logistic-fused posterior that turns a basket into a calibrated probability, weighting members already in the basket, never adding to a count.
- Reliability-aware weighting. Today source weight is a fixed authority prior. Add a reliability-weighted consensus so weight reflects agreement with other credible sources.
- A surfaced conflict label. Today disagreement is implied by the both-sides block. Add an explicit conflicting or cherry-picking attribute on the basket.

### FIX — verified, repo-grounded, highest confidence, do these first

- The flag split-brain. Verified directly: `credibility_pass.py:118` reads `getenv(PG_SWEEP_CREDIBILITY_REDESIGN, "on")` — default ON in synthesis. `live_retriever.py:379` reads the same flag with an empty default and an in-set test — default OFF in retrieval. So on an unset run, the down-weight-don't-drop redesign is live in synthesis but the retriever still hard-drops content-starved rows. This is the same funnel class as the I-arch-007 collapse. Make the retriever default match synthesis.
- Wire the dead modules. All verified as default-off or no-production-caller: `calibration_metrics.py` (Brier, ECE, MCE — pure offline, zero callers), `both_sides.py` (`PG_SWEEP_BOTHSIDES_DISCLOSURE`, no caller), `weight_mass.py` (`PG_SWEEP_WEIGHT_MASS`, no caller), `claim_graph.py` (`PG_SWEEP_CLAIM_GRAPH`, default-off). The machinery exists; it is built but not rendered into the report path.
- Remove or flag `atomic_decomposer.py`. Verified: its `initialize()` falls back to `GeminiClient` at lines 133-134, a sovereignty violation. It is dead on the live path — only `auditor_agent.py` (pipeline-C) and `schemas.py` reference it. Flag it for removal.

---

## Section 4 — Bake-off candidate list per facet

Open-source first. Behavioral acceptance, not vendor score. Every acceptance below means the effect appears in the real rendered output on a banked corpus and fails loud if it does not.

- Facet 1, atomic claims: re-implemented Claimify on the sovereign GLM or DeepSeek slate, versus the live regex extractor; plus CORE (MIT) as the semantic canonicalizer versus current lexical Jaccard. Accept on extraction coverage and span-faithfulness, and on how many equivalent-phrasing atoms collapse into one basket without over-merging distinct clinical claims.
- Facet 2, clustering: bge-m3 plus agglomerative versus Qwen3-Embedding-8B plus community detection, both keep-all; plus the hybrid lexical-then-NLI confirm; plus activating `claim_graph.py` with embedding-plus-NLI grouping. Accept on paraphrase claims correctly landing in one basket while conservative-singleton holds.
- Facet 3, corroboration: crowd-kit Dawid-Skene or M-MSR for reliability-weighted consensus; Beta-Binomial basket confidence on the scikit-learn backbone; CRED-1 down-weight overlay. Accept on a more discriminative, calibrated strength signal in the real output, weight-only, no count inflation, and on the split-brain fix making retrieval coherent.
- Facet 4, conflict: ModernCE-large-nli (MIT) as the primary local always-on NLI, versus the incumbent capped GLM-5.2; the c-variant zero-shot DeBERTa as contender; ConflictRAG two-stage cheap-then-LLM pattern. Accept on contradiction-pair recall and precision, cost, and latency.
- Facet 5, reduce: LLMxMapReduce V1 confidence-calibration reduce; LLMxMapReduce-V2 hierarchical scaling for wide corpora; CAHM recursive re-grounded merge as the lightest port; control arm keeps current consolidation and bolts the chosen reduce on top. Accept on cross-source coverage in the real wide-corpus output. Exclude XpandA — no verified OSS license.
- Facet 6, set verification: MedRAGChecker calibrated set-support as an advisory head; dual-perspective credibility-weighted aggregation with a conflict label; MiniCheck as the per-member primitive; RAGChecker and Ev2R as offline replay scorers. Accept only as advisory layers over isolated per-member verdicts — no span concatenation, no inline gate.
- Facet 7, deep-research stack: input incomplete, no candidates can be listed. Re-run the facet research to populate this row.

---

## Section 5 — Honest uncertainty and license flags

### Uncertainty

- Facet 7 is incomplete in the input. Sections 1 and 4 mark it so. Re-run it before any bake-off.
- One facet path was wrong in the input (the semantic conflict detector). I corrected and re-verified it. Treat any other in-input path as needing a repo check.
- The frontier methods Claimify, ConflictRAG, MedRAGChecker, and the dual-perspective and uncertainty-gated papers have no confirmed open code release or a license-TBD repo. They are design references, not vendorable code.
- Several SOTA reference implementations use closed judges — DeepTRACE uses GPT-5, MedRAGChecker trains from GPT-4. The metric is reusable; the judge must be swapped to the sovereign open-weight slate.

### License flags — must verify before adoption

- `atomic_decomposer.py` in-tree falls back to Gemini, closed and non-sovereign. Dead on the live path. Remove or flag.
- deshwalmahesh/claimify: no license declared, all-rights-reserved. Do not vendor. Re-implement from the paper.
- MedScore: repo license not surfaced; default config uses a closed model though sovereign backends exist. Verify and swap the default.
- NV-Embed-v2: CC-BY-NC, non-commercial, non-sovereign. Do not use. Prefer Qwen3-Embedding Apache-2.0 or bge-m3 MIT.
- sileod deberta-v3-large-tasksource-nli: license not stated. Verify before sovereign use.
- MoritzLaurer zeroshot non-c weights: trained on research-only NLI data. Use the c-variant for commercial sovereign use.
- HerO and Bespoke-MiniCheck-7B: CC-BY-NC, non-commercial. Design reference only. Use the Apache MiniCheck library with the open Flan-T5 or DeBERTa variants instead.
- RobotReviewer and Trialstreamer: GPL-3.0 copyleft. Pattern reference only — do not link into the sovereign binary.
- NewsGuard and MBFC: proprietary closed APIs. Avoid. CRED-1 (CC-BY-4.0, offline) is the open substitute, and it is down-weight-only — absent domain means neutral, never reliable.
- ConflictRAG and SeCon-RAG: no license declared. Pattern only. SeCon-RAG also drops conflicting evidence, which is anti-DNA — adopt its reasoning rubric, never its filtering.
- XpandA: no verified OSS license. Trade-off evidence only, not adoptable code.
- Clean and safe to vendor, sovereign-OK: crowd-kit (Apache-2.0), scikit-learn (BSD-3), Qwen3-Embedding (Apache-2.0), bge-m3 (MIT), sentence-transformers (Apache-2.0), ModernCE-large-nli (MIT), LLMxMapReduce V1/V2/V3 (Apache-2.0), CAHM (MIT), LangGraph (MIT), CORE (MIT), VeriScore (Apache-2.0), RAGChecker (Apache-2.0), MiniCheck library (Apache-2.0), CRED-1 (CC-BY-4.0, attribution required).

Verified current-POLARIS files: `claim_atom_extractor.py`, `finding_dedup.py`, `credibility_pass.py`, `weighted_enrichment.py`, `weight_mass.py`, `calibration_metrics.py`, `retrieval/semantic_conflict_detector.py`, `claim_graph.py`, `evidence_distiller.py`, `both_sides.py`, `atomic_decomposer.py`, `live_retriever.py`.

---

## Completeness critic

All three papers exist and resolve correctly. Key finding: **Claim2Vec (2604.09812, April 2026)** is a genuine, newer, dead-center facet-2 method that the synthesis MISSES — and it beats the MultiClaimNet (March 2025) recipe the synthesis crowns as "the 2025 same-claim SOTA." This is both a missing-method gap (a) and a dated-crown gap (d). The CRED-1 date inconsistency in the facet (2604=April but text says Feb) resolves to **Feb 25, 2026** — the arXiv ID prefix is just non-chronological; CRED-1 is real. Vinod & Erk is real.

I have what I need. The synthesis is durable (it's already my input, not something I need to persist). Let me write the final gap list, severity-ordered.

# COMPLETENESS-CRITIC GAP LIST — I-cons-001 (#1295)

Severity-ordered. Every repo claim and every flagged paper below was verified by me (file reads + arXiv primary-source fetches). Bottom line: the synthesis is largely sound and its repo claims hold, but it has **one material missing method that is also a dated-crown error**, plus three DNA-hardening gaps in its ADD recommendations that must be named as hard requirements, not gestured at.

---

## P1 — MATERIAL MISSING METHOD that is ALSO a dated-method crown (gaps a + d)

**1. Claim2Vec (arXiv 2604.09812, Panchendrarajan & Zubiaga, submitted 2026-04-10, rev 2026-04-14) is absent, and it post-dates and beats the method the synthesis crowns as facet-2 SOTA.**
- The synthesis (Facet 2 table + Section 1) crowns **MultiClaimNet (2503.22280, March 2025)** as "the 2025 same-claim SOTA (0.574 ARI)" via "embed then agglomerative cluster." Claim2Vec is the **April-2026** follow-on: it fine-tunes the multilingual encoder with **contrastive learning on similar-claim pairs** and reports it "significantly improves clustering performance across 3 datasets, 14 embedding models, and 7 clustering algorithms" — i.e. the embedder POLARIS would plug into Step 2 should be a contrastively-tuned one, not a stock Qwen3/bge-m3. Crowning a March-2025 dataset paper as the current clustering recipe while a 2026 method that improves the exact same task exists is a dated-crown miss per the operator's "no dated method as current" rule.
- Primary source: https://arxiv.org/abs/2604.09812
- Fix: add Claim2Vec to the Facet-2 table and the Step-2 bake-off as the contrastive-fine-tune option layered on the Qwen3/bge-m3 vectorizer; demote MultiClaimNet to "the dataset + agglomerative baseline," not "the SOTA recipe."

---

## P2 — DNA-violation risk in the ADD recommendations (gap c) — name them as hard floors, not mentions

**2. crowd-kit reliability weighting can drive a source weight to ZERO = a disguised drop.** Section 1/3/4 recommend crowd-kit Dawid-Skene / M-MSR to replace the "flat origin count" with a reliability-weighted consensus. A Dawid-Skene reliability estimate can legitimately collapse a disagreeing source's weight to ~0, which is an **effective drop** — exactly the FILTER-AND-CAP the weight-and-consolidate DNA forbids (§-1.3: "Social media STAYS at low weight... Do NOT hard-drop a source to hit a number"). The synthesis never states a positive-weight floor. Fix: any reliability-weighting recommendation must carry an explicit **weight > 0 floor** (the member stays in the basket, ranked last, never removed and never zeroed). Primary source for the DNA constraint is internal (CLAUDE.md §-1.3); the method is https://github.com/Toloka/crowd-kit.

**3. embedding+NLI basket clustering carries clinical-lethal over-merge risk that is mentioned but not made a hard requirement.** The single biggest ADD (Section 3, "semantic and paraphrase clustering") would merge "not recommended" / "should be avoided" / "contraindicated" into one basket. The synthesis lists this as the *benefit* but only "gestures at conservative-singleton." Over-merge in the wrong direction (collapsing "contraindicated" with "recommended", or two distinct dose claims) is the §-1.1 lethal direction. Fix: make **never-over-merge / conservative-singleton a named hard acceptance gate** on the Step-2 bake-off (bidirectional-NLI-entailment confirm REQUIRED before two atoms share a basket; a precision floor on the same-claim judge), not a sentence. The synthesis's own DnDScore citation (preserve the distinguishing qualifier) is the lever — elevate it to a gate.

---

## P3 — Scope / honesty gaps (gap a, lower severity)

**4. Facet 7 (deepresearch_stack_consolidation) is truncated in the synthesis input and yields no method table.** The synthesis honestly flags this (Section 1 Facet 7, Section 5). I confirm the input is genuinely incomplete — it ends mid-sentence with no best-practice list. This is a real completeness hole, not a synthesis error: re-run that facet before any bake-off. No fix to the synthesis text needed beyond what it already says; flagged here so the operator sees the landscape is one-facet-short.

**5. Two adjacent 2025/2026 methods surfaced by my own searches are absent but LOWER materiality — confirm-or-discard, don't auto-add.**
- **JointCQ (2510.19310, Oct 2025)** — joint claim + query generation for hallucination detection. Touches Step 1 (extraction) but its native task is detection, not basket consolidation; likely out-of-scope, but the synthesis should state why it was excluded rather than silently omit.
- **Distill-and-Align Decomposition (2602.21857, Feb 2026)** — decomposition for claim verification; overlaps Step 1/Step 5. Verify whether it adds over Claimify+CORE before listing.
- These are not blockers; they are "enumerate-and-justify-exclusion" items so the landscape is demonstrably complete.

---

## NOT GAPS — verified clean (so the operator can trust these)

- **Every load-bearing repo claim in the synthesis holds.** I read the files. Confirmed: `credibility_pass.py:118` defaults `"on"`; `live_retriever.py:379` defaults OFF (the split-brain funnel is real and correctly flagged); `weighted_enrichment.py:222-265` is genuine keep-all-sort-below-floor-last with no cap; `weight_mass.py:161-172` carries credibility as disclosed-not-folded and copy_count with copies contributing zero mass; `credibility_pass.py:341-388` single-token anti-laundering isolation is real; `both_sides.py` / `weight_mass.py` / `claim_graph.py` are default-OFF with "no production caller"; `calibration_metrics.py` has **zero importers** (grep-confirmed); `atomic_decomposer.py:133` Gemini fallback is real and it is dead on the live path.
- **The contested judge default is correct against the LIVE code.** The synthesis says the semantic conflict detector defaults to `z-ai/glm-5.2` — verified at `semantic_conflict_detector.py:69` (env-overridable via `PG_ENTAILMENT_MODEL` at :623), with `MAX_PAIRS=60` / `MAX_ROWS=200` at :63-64. The module's own **docstring at line 30 is STALE** ("Gemma-4-31B by default") but the code default was migrated to GLM-5.2 (#1249/#1252/#1285), so the synthesis matched the code, not the stale comment. This is a one-line repo-hygiene nit (fix the docstring), NOT a synthesis error.
- **All three high-risk future-dated papers exist and resolve correctly** (no hallucinated primary source): Vinod & Erk 2604.11036 (real, biomedical uncertainty-gated fact-checking, 2026-04-13); CRED-1 2604.20856 (real, 2026-02-25 — the facet's internal "2604 vs Feb-2026" inconsistency resolves to Feb-25-2026; the arXiv ID prefix is simply non-chronological, CRED-1 is genuine and CC-BY-4.0).
- **The frozen-faithfulness-engine rule is respected throughout.** No recommendation touches strict_verify / NLI entailment / 4-role D8 / provenance / span-grounding; every ADD is an advisory weight/label/consolidation. The synthesis correctly rejects SeCon-RAG's drop behavior and preserves the single-token isolation invariant. No "cap/drop/thin dressed up" survived except the two latent risks named in P2 above.
