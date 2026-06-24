# Claim-Basket → Composition Bridge Landscape 2025/2026

**Scope:** the SEAM between retrieval/consolidation and composition — the four coupled
stages `CLAIM EXTRACTION → CROSS-SOURCE BASKETING → WITHIN-BASKET CONSOLIDATION →
BASKET-TO-COMPOSITION`. This is CLAUDE.md §-1.3 "weight-and-consolidate,
basket-faithfulness" DNA made concrete at the layer that is easiest to under-scope.

**Relationship to the existing docs (read first — this EXTENDS, does not duplicate):**
- `docs/consolidation_landscape_2026.md` (I-cons-001 #1295) already maps facets 1–6
  (extraction / clustering / corroboration / contradiction / multi-doc-reduce /
  set-verify). Its candidate tables for stages 1–3 stand. **Its Facet 7
  (deep-research-stack consolidation / the seam) arrived truncated and is explicitly
  empty — "no tool table can be built."** THAT empty Facet 7 is precisely the bridge,
  and is the net-new contribution here.
- `docs/retrieval_landscape_2026.md` is the upstream (retrieval) landscape.

So for stages 1–3 this doc gives the **bridge angle only** — what each stage must
*emit downstream* so composition can cite the whole basket faithfully — and references
the existing candidate tables rather than re-deriving them. The net-new word-count is
spent on **Stage 4 (basket→composition)**, the **handoff data contract**, and the
**clinical gold-set + isolation axis**.

**Frozen-engine rule (governs everything below).** The faithfulness engine —
`strict_verify` / `verify_sentence_provenance`, the NLI entailment check, the 4-role D8
release policy, provenance tokens, span-grounding — is the ONLY hard gate and is NEVER
touched. Every candidate below is an advisory WEIGHT, a CONSOLIDATION, or a LABEL that
feeds that frozen engine. Nothing here relaxes a verify gate. Weight-and-consolidate,
never filter-and-cap.

**License legend:** ✅ OSS-deployable (Apache-2.0 / MIT / BSD — vendorable into the
sovereign binary). ⚠️ CC-BY / CC-BY-NC / paper-only / closed judge — yardstick or
design-reference ONLY (sovereignty constraint: re-implement on the GLM-5.2 / DeepSeek
slate, never link). License must be re-verified at adoption time.

---

## 0. The bridge in one diagram

```
 retrieval pool (weighted, never filtered)
      │
      ▼
 [1] CLAIM EXTRACTION        decompose each source into atomic, checkable claims
      │   emits: AtomicClaim{subject, predicate, value, unit, qualifiers, span, polarity}
      ▼
 [2] CROSS-SOURCE BASKETING  group claims from DIFFERENT sources that share a TARGET
      │   (subject+predicate), stance resolved WITHIN the basket
      │   emits: ClaimBasket{target_key, members[], refuter_refs[], contradiction_flag}
      ▼
 [3] WITHIN-BASKET CONSOLIDATION   keep ALL members; compute support mass,
      │   agreement/contradiction, calibrated confidence
      │   emits: enriched ClaimBasket{weight_mass, calibrated_confidence, per-member span verdict}
      ▼
 [4] BASKET → COMPOSITION    attribution-faithful synthesis: one sentence,
      │   MULTI-CITATION per claim, each citation independently span-verified
      ▼
 strict_verify / NLI / 4-role / provenance  ← THE ONLY HARD GATE (frozen)
      │
      ▼
 report.md + bibliography.json (multi-citation, basket-faithful)
```

The under-scoped failure mode this doc guards against: a pipeline that nails [1]–[3]
but, at [4], collapses a 5-member basket to a single cited span (breadth collapse) OR
synthesizes a sentence whose joint citation set passes while no single member supports
it alone (evidence laundering). The bridge is where breadth and faithfulness are both
won or both lost.

---

## STAGE 1 — CLAIM EXTRACTION

**Bridge role:** turn each fetched source into atomic, checkable claims so [2] can match
them across sources. The atom MUST carry the distinguishing qualifiers (dose, comparator,
population, timepoint) AND a polarity/assertion-status, or [2] cannot safely co-basket
without over-merging distinct clinical claims.

### Current POLARIS floor

| Module | What it actually is | file:line |
|---|---|---|
| `generator/claim_atom_extractor.py` | **Pure-Python regex, NO LLM.** Numeric-anchor + role classifier; only OUTCOME numbers become atoms. Emits frozen `ClaimAtom` (14 fields). | extractor pure-regex note `claim_atom_extractor.py:48-51`; `_NUMBER_ATOM_RE` `:641-648`; `_classify_number` `:772-893` |
| Hardcoded clinical vocab | `_ENDPOINT_VOCAB` (~60 regex: HbA1c, MACE, eGFR…), `_DRUG_RE`, `_TRIAL_RE`, `_STAT_METADATA` (HR/RR/OR) | `:182-302`, `:326-345`, `:347-367`, `:312-319` |
| `retrieval/contradiction_detector.extract_numeric_claims` (consumed by finding_dedup + claim_graph) | clinical-pattern-tuned, **≤1 claim/row**, returns NOTHING for non-clinical numerics; a B9 domain-agnostic path exists but the clinical extractor is primary | residual doc `finding_dedup.py:29-41`; B9 route `finding_dedup.py:660-680` |

**Default:** always-on (pure lib, no flag), but inert on non-clinical / prose-only text.

**#1 gap:** it is a numeric/clinical-pattern extractor, not a general atomic-claim
**decomposer**. Non-clinical numerics and prose-only/qualitative claims get no atom →
they never reach a basket → corroboration under-counted exactly where the DNA needs it.
The hardcoded vocab is the ceiling.

### Top 2025/2026 OSS candidates (bridge angle: a decomposer that emits qualifier-complete, polarity-tagged atoms)

| Candidate | Date | Primary source | License | Why (for the bridge) |
|---|---|---|---|---|
| **Claimify** (Microsoft) | 2025 | [MS Research blog](https://www.microsoft.com/en-us/research/blog/claimify-extracting-high-quality-claims-from-language-model-outputs/) | ⚠️ paper; no official code (unofficial `deshwalmahesh/claimify` = no license) | The selection→disambiguation→decomposition pipeline DROPS a claim when interpretation is ambiguous — exactly the clinical never-fabricate posture. Re-implement on the GLM slate. Its **disambiguation+decontextualization is what lets [2] compare paraphrases without the atom losing its qualifier.** |
| **CORE** | 2024/25 | per `consolidation_landscape_2026.md` §Facet-1 | ✅ MIT (per existing doc) | Entailment-filtered + MILP minimal non-redundant claim set. Sovereign via local NLI/vLLM. Gives [2] a canonical, de-duplicated atom to cluster. |
| **VeriScore** | 2024 | per `consolidation_landscape_2026.md` §Facet-1 | ✅ Apache-2.0 (per existing doc) | Extracts only *verifiable* claims — a pre-filter that drops opinion before [2], so baskets carry checkable atoms only. |
| **MedScore** | 2025-05-24 | [arXiv 2505.18452](https://arxiv.org/abs/2505.18452) ; [github.com/Heyuan9/MedScore](https://github.com/Heyuan9/MedScore) | ⚠️ default decomposition uses **GPT-4o-mini** (closed) — re-implement on the sovereign slate | Domain-adapted decompose-then-verify; extracts ~3× more valid condition-aware clinical claims than FActScore/VeriScore/CORE/DnDScore. Replaces the hardcoded clinical vocab with a learned condition-aware decomposer. |
| **DnDScore (decontextualize + decompose)** | 2024-12 | [arXiv 2412.13175](https://arxiv.org/abs/2412.13175) (EMNLP 2025) | ⚠️ paper | Method: decontextualize each atom so paraphrases compare WITHOUT losing the qualifier (e.g. keep the entity "He" refers to). **Elevate to a hard requirement for [2]** (see §-1.1 over-merge risk). |
| **Distill-and-Align Decomposition** | 2026-02 | [arXiv 2602.21857](https://arxiv.org/abs/2602.21857) | ⚠️ paper | Newest (2026) decomposition-for-verification method; verify whether it adds over Claimify+CORE before adopting. |

> These five are already in `consolidation_landscape_2026.md` §Facet-1; reproduced here
> only to attach the *bridge requirement*: **the extractor's output must be the
> qualifier-complete, polarity-tagged atom that [2] keys on.** Today POLARIS's regex atom
> carries the clinical qualifiers (dose/arm/endpoint) but no polarity field; that polarity
> field is what [2] needs to flag rather than hide a contradiction.

**Provisional frontier pick to beat:** re-implemented **Claimify** (selection +
disambiguation + drop-on-ambiguity) on the sovereign slate, with **CORE** (MIT) as the
canonicalizer, run BESIDE the existing regex extractor (not replacing it) for
out-of-vocab/non-clinical claims. Atom MUST emit an explicit `polarity` /
`assertion_status` for the basketer.

---

## STAGE 2 — CROSS-SOURCE CLAIM BASKETING

**Bridge role (sharpened):** group claims from DIFFERENT sources that share a **claim
TARGET** (subject+predicate / proposition-topic), THEN resolve stance WITHIN the basket.
"X is recommended" and "X is contraindicated"/"not recommended" share the target → they
**co-basket**, and the contradiction is detected and FLAGGED. This is the most
clinical-lethal stage in either direction:
- **split opposites apart** → contradiction silently hidden (the under-count fear);
- **merge opposites as corroboration** → counts an opposite as support (the §-1.1 LETHAL
  direction — a wrong dose/contraindication surviving as "corroborated").

The correct primitive is **bidirectional NLI 3-way over the basket pair**: ENTAILMENT
(paraphrase → co-basket, agree) · CONTRADICTION (opposite → co-basket, FLAG) · NEUTRAL
(different target → separate). Embedding similarity alone cannot distinguish "co-basket
because opposite" from "co-basket because same" — it sees both as "close."

### Current POLARIS floor

| Module | What it actually is | file:line |
|---|---|---|
| `synthesis/claim_graph.build_claim_graph` → `cluster_equivalent_claims` | **Deterministic SHA-1 of a LITERAL normalized-field key; exact-equality only.** Two claims co-basket iff their `normalized_key` tuple is byte-equal. No embedding, no semantic similarity anywhere in the cluster path. | cluster `claim_graph.py:759-777`; id = SHA-1 `:746-756` |
| `build_merge_key` (ON path) | spec-driven **FAIL-CLOSED** key — any unknown discriminator → `__unresolved__` singleton (the A13 residual: blank dose/comparator/effect_measure forces singletons even for genuine same-finding) | key spec `:413-481`; builder `:508-552` (residual doc `:525-535`) |
| **Polarity** | **Opposites do NOT co-basket by design** — opposite `assertion_status` → different key → different cluster; contradiction carried by an EDGE, not co-basketing | `claim_graph.py:264-266` |
| Contradiction EDGES (`build_contradiction_edges`) | 3 sources: deterministic numeric `detect_contradictions`, deterministic qualitative present-vs-absent, and OPTIONAL semantic NLI `detect_semantic_conflicts` — **only when an `nli_judge` is injected**, capped `MAX_PAIRS=60`/`MAX_ROWS=200`, per-pair fail-open | numeric `:899`; qualitative `:914`; NLI `:924-949`; caps `:107-109` |

**Default:** `claim_graph` standalone default-OFF (`PG_SWEEP_CLAIM_GRAPH`); but
`credibility_pass` calls `build_claim_graph` directly under
`PG_SWEEP_CREDIBILITY_REDESIGN` (default **ON**) `credibility_pass.py:118,923`.

**#1 gap:** clustering is **literal-key-equality only**. Paraphrases of the same claim
across sources do NOT co-basket (the entire reason corroboration is under-counted), and
the fail-closed key singletons genuine same-findings whose clinical qualifiers are blank.
Polarity opposites are split (carried by an optional, capped edge) rather than
co-basketed-and-flagged. There is no NLI/embedding *confirm* gate on grouping.

### Top 2025/2026 OSS candidates

| Candidate | Date | Primary source | License | Why (for the bridge) |
|---|---|---|---|---|
| **Bidirectional Entailment Clustering (BEC)** | incumbent floor (orig. 2023; Nature 2024) | [Kuhn et al. semantic entropy, arXiv 2302.09664](https://arxiv.org/abs/2302.09664) | ✅ method (impl on local NLI) | Genuine incumbent floor for the 3-way primitive: classify each basket pair bidirectionally (entail/neutral/contradict) and assign to equivalence classes. **Gives co-basket-by-target + the contradiction label in one pass** — the lever for "co-basket opposites AND flag." |
| **Claim2Vec** | 2026-04-10 (rev 04-14) | [arXiv 2604.09812](https://arxiv.org/abs/2604.09812) | ⚠️ CC-BY-4.0 paper; no confirmed code | **Newest dead-center method.** Contrastive fine-tune of a multilingual encoder for *claim* clustering; "significantly improves clustering across 3 datasets, 14 embedders, 7 algorithms." Says the [2] vectorizer should be a contrastively-tuned claim encoder, NOT stock Qwen3/bge-m3. Re-train on the sovereign slate. |
| **Qwen3-Embedding-8B** | 2025 | [HF Qwen3-Embedding](https://huggingface.co/Qwen/Qwen3-Embedding-8B) | ✅ Apache-2.0 | The basket vectorizer POLARIS already chose in I-arch-009. Reuse as the candidate-generator; confirm with bidirectional NLI. |
| **bge-m3** (BAAI) | 2024 | [HF BAAI/bge-m3](https://huggingface.co/BAAI/bge-m3) | ✅ MIT | MultiClaimNet-winning multilingual embedder; dense+sparse in one model. Strong candidate-generation alternative. |
| **A Straightforward Pipeline for Targeted Entailment & Contradiction Detection** | 2025-08-23 | [arXiv 2508.17127](https://arxiv.org/abs/2508.17127) | ⚠️ CC-BY-4.0 paper | Two-stage attention-saliency → pretrained-NLI entail/contradict. **Intra-document, not cross-source pairwise** — adjacent, pattern-inspiration for the saliency pre-filter, not a drop-in cross-source basketer. |
| **ModernCE-large-nli** | 2025 | [HF dleemiller/ModernCE-large-nli](https://huggingface.co/dleemiller/ModernCE-large-nli) | ✅ MIT | Local always-on NLI cross-encoder, 8192 ctx. Replaces the capped remote GLM judge as the bidirectional-NLI confirm — zero API spend, no socket-hang class. |

> Qwen3 / bge-m3 / ModernCE / MultiClaimNet are in `consolidation_landscape_2026.md`
> §Facet-2; the bridge addition is **BEC as the framing** (3-way, co-basket-by-target)
> and **Claim2Vec as the newest contrastive-tune option** (the existing doc's own
> completeness critic flagged Claim2Vec as the method the main synthesis missed; it
> post-dates and improves on MultiClaimNet — demote MultiClaimNet to "dataset+agglomerative
> baseline," not "the SOTA recipe").

**Provisional frontier pick to beat:** **candidate-generate with Qwen3-Embedding-8B (or
a Claim2Vec-style contrastive fine-tune), then CONFIRM same-target with bidirectional
ModernCE-NLI** before two atoms share a basket. **Hard requirement (NOT a sentence):** a
bidirectional-NLI confirm is REQUIRED before co-basket; a CONTRADICTION verdict
co-baskets-AND-flags (never silently splits, never merges-as-support); DnDScore-style
qualifier preservation gates against over-merging two distinct dose/population claims.
Conservative-singleton holds: when NLI is NEUTRAL/uncertain, keep separate.

---

## STAGE 3 — WITHIN-BASKET CONSOLIDATION

**Bridge role:** keep ALL members (multi-citation, never drop a corroborator); compute
agreement/contradiction, credibility-weighted support mass, and a *calibrated* confidence
the composition layer can surface per claim. Represent the basket so [4] can cite the
WHOLE basket per claim.

### Current POLARIS floor — POLARIS LEADS on keep-all; the frontier is ahead on calibration

| Property | What it actually is | file:line | Verdict |
|---|---|---|---|
| **Keep-all** | `ClaimBasket.supporting_members` keeps ALL sources, never dropped; assembled by iterating every member | `credibility_pass.py:210-233` (keep-all `:227`), assembly `:678-727` | ✅ **POLARIS LEADS** — ahead of public deep-research stacks that dedup at URL level |
| Support mass | `weight_mass.aggregate_weight_mass`: `weight_mass = Σ over independent origins of cluster_mass`, `cluster_mass = authority_score(canonical) ONLY`. **Credibility disclosed-but-NOT-folded** (no-inflation invariant); **copies contribute ZERO** | `weight_mass.py:161-167` (credibility note `:163-166`; copies `:168-172`) | uncalibrated authority sum |
| Strength signal | `verified_support_origin_count` (distinct isolated-verified origins) + `total_clustered_origin_count` (advisory) + `weight_mass` + a 4-value `basket_verdict` LABEL (full/partial/contested/unverified) | `credibility_pass.py:161-164`, `:738-748` | discrete label, no probability |
| **Calibrated confidence** | `calibration_metrics.py` (Brier/ECE/MCE) has **ZERO production importers** (grep-confirmed). NO Beta-Binomial, NO Dawid-Skene, NO crowd-kit anywhere in `src/` | `calibration_metrics.py:1-20` (dead) | ❌ **built but dead** |

**Default:** keep-all + weight_mass run through the credibility chain under
`PG_SWEEP_CREDIBILITY_REDESIGN` (default ON); `calibration_metrics.py` is dead.

**#1 gap:** a basket carries an uncalibrated authority-sum weight + a discrete label, but
**no calibrated probability of correctness** and **no reliability-aware (agreement-weighted)
source weighting**. The calibration machinery is built and untested-in-production.

### Top 2025/2026 OSS candidates

| Candidate | Date | Primary source | License | Why (for the bridge) |
|---|---|---|---|---|
| **crowd-kit** (Dawid-Skene, M-MSR) | 2025 (maint.) | [github.com/Toloka/crowd-kit](https://github.com/Toloka/crowd-kit) | ✅ Apache-2.0 | Reliability-aware truth discovery: a source's weight reflects AGREEMENT with other credible sources, not just venue. Replaces the flat origin count. **HARD FLOOR (DNA): weight > 0 always — a Dawid-Skene estimate can collapse a disagreeing source's weight to ~0 = a disguised DROP. Member stays in the basket, ranked last, never zeroed** (§-1.3). |
| **Beta-Binomial basket posterior** | classical, 2025 tooling | [scikit-learn calibration](https://scikit-learn.org/stable/modules/calibration.html) (BSD-3) backbone | ✅ BSD-3 | Turns a basket's (k verified of n members, weighted) into a CALIBRATED probability + credible interval. Wires the dead `calibration_metrics.py`. Weights members already IN the basket — never adds to a count. |
| **CRED-1** (offline domain reliability) | 2026-02-25 | arXiv 2604.20856 (primary-source-verified in `consolidation_landscape_2026.md` completeness critic) | ⚠️ CC-BY-4.0 (attribution) | Offline negative-signal domain table — DOWN-weight known-bad domains only, NEVER up-weight; absent domain = neutral. Open substitute for closed NewsGuard/MBFC. |
| **Dual-perspective credibility-weighted aggregation** | 2025 | paper (consolidation doc §Facet-6) | ⚠️ paper | Fuses per-member verdicts + corroboration weight + agreement into ONE calibrated basket confidence + an explicit conflict label. |

> crowd-kit / scikit-learn / CRED-1 are in `consolidation_landscape_2026.md` §Facet-3/6;
> the bridge addition is the **positive-weight floor** as a hard requirement (its own
> completeness critic flagged crowd-kit's zero-collapse as a disguised drop), and the
> **basket representation** the next section needs.

**Provisional frontier pick to beat:** **crowd-kit reliability-weighted consensus (with a
hard weight>0 floor) + a Beta-Binomial calibrated basket posterior** on the scikit-learn
backbone, surfaced as a per-basket `calibrated_confidence` + an explicit
`contradiction_flag`. Weight-only, no count inflation, no member ever zeroed/dropped.

---

## STAGE 4 — BASKET → COMPOSITION  *(the net-new core of this doc)*

**Bridge role:** attribution-faithful, multi-document synthesis that emits sentences
carrying **MULTI-CITATION per claim**, faithful to the WHOLE basket — a claim's verdict is
against its whole basket, not one span. The discriminating question for EVERY candidate:
does it preserve **per-member isolated span grounding** (each citation independently
verifiable), or does it do whole-sentence / whole-context **joint** entailment (which
re-opens laundering — a union that passes while a member fails alone)?

### Current POLARIS floor — POLARIS LEADS on quotation-faithfulness; the multi-cite path is gated OFF

| Module | What it actually is | file:line |
|---|---|---|
| `generator/verified_compose.compose_basket_multicited_sentence` | For a basket with ≥2 isolated-`SUPPORTS` members: build ONE single-source clause PER member (each independently passing UNCHANGED `strict_verify` against its OWN span via a 1-member sub-basket), then co-locate into ONE sentence carrying ALL members' `[#ev:...]` citations. **Per-clause verify invariant:** the joined sentence still passes strict_verify PER CLAUSE — each clause keeps its own token inside its own span | `verified_compose.py:669-770+` (sub-basket verify `:684-692`; per-clause invariant `:693-695`) |
| Cross-basket variant `compose_multicited_sentence` | co-locate clauses from N corroborating baskets; returns `None` if <2 baskets yield a clause | `verified_compose.py:543-573` |
| **Faithful-by-construction** | each member falls back to its **verbatim K-span** (`_member_verbatim_clause`); the writer (existing generator-role LLM, NO new model) can only improve phrasing, never license the cite | `verified_compose.py:626-634`, `:697-704` |
| Single-token anti-laundering (the keystone) | isolated per-member verify uses EXACTLY ONE provenance token so the verifier's per-token union loop cannot aggregate spans across members — a member whose own span lacks the claim fails ALONE even if a union would pass | `credibility_pass.py:341-388` |
| Consumption | `multi_section_generator` imports `_compose_section_per_basket`, `_section_baskets_for_compose`; builds reliability header from `credibility_analysis.baskets` | `multi_section_generator.py:57-63`, `:90-122` |
| Breadth-enrichment | surfaces unbound-SUPPORTS members into one extra field-agnostic section (keep-all-sort-below-floor-last, no cap) | `weighted_enrichment.py:51`, `:100-104` |

**Default:** the multi-cited path is **DEFAULT-OFF** (`PG_VERIFIED_COMPOSE_MULTICITED`);
per-basket verified-compose master is `PG_VERIFIED_COMPOSE`; breadth-enrichment
default-OFF (`PG_BREADTH_ENRICHMENT_ENABLED`).

**#1 gap:** the genuine basket→multi-citation synthesis is **implemented but gated OFF by
default**, and it only fires for baskets that already co-clustered under the literal-key
Stage-2 — so paraphrase corroborators (split at [2]) never reach [4]. It is
per-clause-quotation-faithful but does NOT do attributed *abstractive* synthesis across a
basket (no LLMxMapReduce-style attributed reduce); breadth depends entirely on how many
members Stage-2 put in one basket.

### Top 2025/2026 OSS candidates — and the isolation discriminator

| Candidate | Date | Primary source | License | Isolation property (the discriminator) |
|---|---|---|---|---|
| **Attribution/Citation/Quotation survey** | 2025-08 | [arXiv 2508.15396](https://arxiv.org/abs/2508.15396) | ⚠️ survey | Establishes **QUOTATION as the only faithful-BY-CONSTRUCTION form.** POLARIS's verbatim K-span fallback IS this. Frames why [4] should degrade to quotation, not paraphrase, on a failing sentence. **POLARIS already leads.** |
| **LongCite** (THUDM, CoF pipeline) | 2024-09 | [github.com/THUDM/LongCite](https://github.com/THUDM/LongCite) ; [arXiv 2409.02897](https://arxiv.org/abs/2409.02897) | dataset (LongCite-45k) ✅ Apache-2.0; **weights ⚠️ per-variant** — `LongCite-glm4-9b` inherits the GLM-4-9B license, `LongCite-llama3.1-8b` inherits the **Llama-3.1 Community License (restricted, NON-Apache)** — verify per-variant before linking | Fine-grained **sentence-level** citations, SOTA citation quality (beats GPT-4o on LongBench-Cite). BUT citation granularity is sentence-level, NOT per-member-isolated-span — it does not verify each cite ALONE. Strong attributed-generation arm; would need POLARIS's single-token isolation bolted on. |
| **VeriCite** | 2025-10 | [arXiv 2510.11394](https://arxiv.org/abs/2510.11394) | ⚠️ paper | Rigorous per-citation verification in RAG — closest frontier to POLARIS's per-member verify. Pattern reference for the verify-each-cite loop. |
| **Attribute First, then Generate** | 2024-03 | [arXiv 2403.17104](https://arxiv.org/abs/2403.17104) | ⚠️ paper | Locally-attributable generation via **pre-generation span alignment** — the anti-laundering pattern (select the span, THEN write to it). POLARIS already does this (basket-id-bound verbatim fallback). |
| **"Correctness is not Faithfulness in RAG Attributions"** | 2025 | [ACM 10.1145/3731120.3744592](https://dl.acm.org/doi/10.1145/3731120.3744592) | ⚠️ paper | Names the EXACT laundering failure POLARIS's single-token isolation prevents (a cite refers to context used in generation but not containing the statement). The yardstick for "why isolated > joint." |
| **"Are Finer Citations Always Better?"** | 2026 | [arXiv 2604.01432](https://arxiv.org/abs/2604.01432) | ⚠️ paper | Granularity tradeoff — fine-grained constraints can fracture semantic dependencies. Tempers over-fragmenting the per-clause invariant. |
| **sui-1** | 2026-01-13 | [arXiv 2601.08472](https://arxiv.org/abs/2601.08472) ; HF `ellamind/sui-1-24b` | ⚠️ CC-BY-4.0 (weights open, non-Apache) | 24B grounded-summarization model, sentence-level inline cites, 84% LLM-judge faithfulness. **Yardstick only** (CC-BY, sentence-level not per-member). Useful as a competitor to beat on a faithfulness bench. |
| **LLMxMapReduce V1 / CAHM** | 2024/25 | [github.com/thunlp/LLMxMapReduce](https://github.com/thunlp/LLMxMapReduce) ; CAHM (MIT) | ✅ Apache-2.0 / MIT | The attributed *reduce* shape for wide-corpus synthesis (confidence-calibration reduce; recursive re-grounded merge). The bolt-on for abstractive cross-basket synthesis — but the reduce output must re-enter the frozen strict_verify per clause, never resolve conflict in place of it. |

**The honest finding (per the task's "be honest where POLARIS leads"):** every OSS
attribution candidate optimizes **citation precision/recall at sentence granularity** —
NOT per-member ISOLATION. LongCite, sui-1, ALCE-style attributed QA all assign a citation
to a sentence and verify the sentence against its cited set JOINTLY. **POLARIS's
single-token isolated per-member verify + basket-id-bound verbatim fallback is AHEAD of
the published frontier on the anti-laundering property.** The 2025/2026 frontier is ahead
only on (a) abstractive fluency of the attributed synthesis (LongCite/sui-1 read better)
and (b) it is not gated OFF.

**Provisional frontier pick to beat:** **POLARIS's own `compose_basket_multicited_sentence`
turned ON**, with a **LongCite-style writer** as the abstractive phrasing arm — prefer the
`LongCite-glm4-9b` variant (GLM-4-9B license, sovereignty-compatible with the GLM slate;
avoid the Llama-3.1 variant's restricted Community License) — but EVERY emitted citation
routed back through the existing single-token isolated `strict_verify` (the per-clause
invariant), and a verbatim K-span fallback on any clause that fails. Keep the
anti-laundering isolation; borrow only the fluency. The control arm is the current OFF
state (sentence cites a single span).

---

## THE HANDOFF DATA CONTRACT  *(net-new — the seam the existing doc never specified)*

The bridge is only as good as what a `ClaimBasket` CARRIES across the [3]→[4] boundary.
For composition to emit faithful multi-citation, the basket handed to [4] MUST carry:

| Field | Source stage | Why [4] needs it |
|---|---|---|
| `target_key` (subject+predicate / proposition-topic) | [2] | the claim [4] writes a sentence about |
| `members[]` with `{evidence_id, source_url, source_tier, span, direct_quote, span_verdict, member_tier, credibility_weight}` | [2]+[3] | EVERY corroborator + its OWN isolated verdict — so [4] cites all and falls back to a verified member's verbatim span (keep-all multi-citation) |
| `refuter_refs[]` + `contradiction_flag` | [2] | so [4] renders CONTESTED / both-sides, never silently drops the opposite |
| `weight_mass` (authority-only, copy-uninflatable) | [3] | ordering weight (priority of consideration), never a drop |
| `calibrated_confidence` (Beta-Binomial posterior) + `reliability_weights` | [3] (ADD — today missing) | a per-claim confidence [4] can surface honestly |
| `basket_verdict` (full/partial/contested/unverified LABEL) | [3] | display label, never resurrects a dropped sentence |

POLARIS's `ClaimBasket` (`credibility_pass.py:209-233`) already carries `target` (subject/
predicate), `supporting_members[]` with per-member `span_verdict`+`member_tier`,
`refuter_cluster_ids`, `weight_mass`, and `basket_verdict`. **The single missing contract
field is `calibrated_confidence`** — Stage-3's dead calibration machinery is what would
fill it. This is the most concrete, smallest-surface ADD in the whole bridge.

---

## ISOLATION AXIS + CLINICAL GOLD-SET SKETCH  *(net-new — the bake-off design, NO e2e)*

Two isolated axes, neither requiring an end-to-end run. The faithfulness ENGINE stays
frozen; these measure the bridge stages against labeled fixtures.

### Axis A — Basketing accuracy (Stage 2)

A labeled **claim-pair gold set** with **THREE** categories (the 2-category version misses
the lethal direction):

1. **same-assertion paraphrase** — different sources, same claim, same polarity
   → MUST co-basket, agreement label. *(e.g. "tirzepatide lowered HbA1c by 2.1%" /
   "a 2.1 percentage-point HbA1c reduction was seen with tirzepatide")*
2. **polarity-opposite** — same target, opposite stance
   → MUST co-basket AND raise `contradiction_flag`. *(e.g. "drug X is recommended in
   pregnancy" / "drug X is contraindicated in pregnancy")*
3. **same-topic-different-claim** — same subject, DIFFERENT claim (different dose,
   population, endpoint) → MUST NOT co-basket. *(e.g. "5 mg dose" / "10 mg dose"; a T2D
   population vs an obesity population sharing "-2.1%")*

**Metrics:** clustering precision/recall (cat 1 grouped, cat 3 separated);
**contradiction-detection recall** (cat 2 co-basketed-and-flagged, the under-count guard);
and **over-merge rate on cat 3** (the §-1.1 LETHAL-direction guard — an opposite or a
distinct dose merged as corroboration is the clinical fabrication this whole doc exists to
prevent). A basketer that scores high P/R on cats 1+3 but mishandles cat 2 in EITHER
direction FAILS.

### Axis B — Consolidation faithfulness (Stages 3–4)

On a banked `corpus_snapshot.json` basket fixture:
- **multi-citation completeness** = every gold corroborator of a claim SURVIVES as a
  citation in the composed sentence (keep-all check — no dropped corroborator);
- **no-laundering** = a synthesized multi-cite sentence where ONE member's span is
  silently swapped for a non-supporting span must FAIL the per-member isolated verify
  (the single-token isolation must catch it — the joint-entailment laundering test);
- **weight>0 floor** = no member's reliability weight is zeroed (no disguised drop).

**Behavioral acceptance (§-1.4):** each fixture FAILS LOUD (non-zero exit) if the effect
did not fire — `collapsed>0` / multi-source baskets appear / a planted laundering case is
caught / no corroborator dropped — NOT "Codex approved" and NOT "tests green."

### Gold-set construction (sovereign, no closed judge)

Seed from real fetched clinical spans in banked corpora (`state/iarch007_corpus_checkpoints.json`,
the replay corpora). For the three pair categories, draw real same-finding /
opposite-finding / distinct-dose pairs from the corpus and label by hand (clinical, so
human-labeled, not LLM-labeled). Reuse the §-1.1 line-by-line audit discipline as the
labeling standard. Closed-judge benches (DeepTRACE GPT-5, sui-1's LLM-judge) are
**yardstick only** — the gold labels must be human/primary-source, not model-generated.

---

## SUMMARY — per stage: floor · single best 2025/2026 OSS candidate · #1 gap

| Stage | Current POLARIS floor (file:line) | Single best 2025/2026 OSS candidate | #1 gap |
|---|---|---|---|
| **1 Extraction** | pure regex + hardcoded clinical vocab, ≤1 numeric claim/row, no LLM (`claim_atom_extractor.py:48-51,641-648,182-302`) | **Claimify** re-impl + **CORE** (✅ MIT) canonicalizer | no general/LLM atomic decomposition; non-clinical + prose claims unextracted; no polarity field on the atom |
| **2 Basketing** | SHA-1 of LITERAL field key, exact-equality only; opposites SPLIT to an edge; NLI optional+capped (`claim_graph.py:759-777,746-756,264-266,924-949`) | **Bidirectional NLI (BEC) confirm** over Qwen3/Claim2Vec candidates (✅ Qwen3 Apache; ⚠️ Claim2Vec paper) | literal-key only — paraphrases don't co-basket, opposites split not co-basketed-and-flagged; **the biggest real gap** |
| **3 Consolidation** | keep-all ✅ (LEADS); flat authority-sum mass, copies=0, credibility disclosed-not-folded; calibration DEAD (`credibility_pass.py:227`, `weight_mass.py:161-167`, `calibration_metrics.py` 0 callers) | **crowd-kit** reliability (weight>0 floor) + **Beta-Binomial** posterior (✅ Apache/BSD) | no calibrated confidence (machinery built but dead); no reliability weighting |
| **4 Composition** | per-clause verbatim-span multi-citation, single-token isolation (LEADS on anti-laundering); **multi-cite gated OFF** (`verified_compose.py:669-770,693-695`, `credibility_pass.py:341-388`) | **POLARIS's own multi-cite ON** + a **LongCite-glm4-9b** writer (✅ Apache dataset / ⚠️ GLM-licensed weights) behind the frozen isolated verify | real multi-cite synthesis OFF by default; fires only on already-co-clustered baskets; no attributed abstractive reduce |

### Where POLARIS LEADS vs where the 2025/2026 frontier is AHEAD

**POLARIS leads (do not regress):**
- **The keep-all basket primitive** (Stage 3) — ahead of public deep-research stacks that
  dedup at URL level. The genuine crown.
- **Per-member single-token isolated verification + basket-id-bound verbatim fallback**
  (Stage 4) — ahead of the published attribution frontier (LongCite/sui-1/ALCE all verify
  sentence-against-cited-set JOINTLY; POLARIS verifies each member ALONE). This is the
  anti-laundering property the 2025 "Correctness is not Faithfulness" paper says the field
  lacks.

**The frontier is ahead:**
- **Stage 2** — semantic/NLI/contrastive clustering (BEC, Claim2Vec) vs POLARIS's literal
  SHA-1 key. This is the single biggest real gap; it is why corroboration is under-counted
  and why opposites split rather than co-basket-and-flag.
- **Stage 3** — calibrated + reliability-weighted basket confidence (crowd-kit,
  Beta-Binomial) is published practice; POLARIS's machinery is built but DEAD (0 callers).
- **Stage 4 fluency** — LongCite/sui-1 produce more readable attributed prose, and they
  are not gated OFF.

**The one-line bridge verdict:** POLARIS owns the two HARD properties (keep-all,
isolation); it is behind on the two SOFT ones (semantic basketing, calibrated confidence).
Closing Stage-2 (NLI confirm over a contrastive embedder, co-basket-by-target) feeds more
true corroborators into the keep-all primitive POLARIS already leads on — which is exactly
the weight-and-consolidate DNA, with the faithfulness engine never touched.
