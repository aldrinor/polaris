# POLARIS Credibility-Weighted Sourcing Redesign — Complete Implementation Plan

**Document class:** Architecture plan, operator-approval-gated (no code is written until the operator signs off on this document).
**Author:** Claude (lead architect). **Date:** 2026-06-07.
**Primary input:** `docs/frontier_credibility_intelligence_2026_06_07.md` (read in full — §3 honest gap, §4 six layers, and §6 the binding completeness addendum).
**Grounding note (honesty):** the task referenced "six subsystem maps." Only **two** structured JSON maps were supplied (Evidence-selection/adequacy, and Conflict-detection/disclosure). The remaining four subsystems were grounded by reading the actual source files directly (`authority_model.py`, `corroboration.py`, `finding_dedup.py`, `tier_classifier.py`, `provenance_generator.py`, `corpus_approval_gate.py`, `plan_sufficiency_gate.py`, `journal_only_filter.py`, `evidence_selector.py`). Every file:line reference below was verified against the working tree **or the supplied subsystem maps** (the `semantic_conflict_detector.py:346` family-segregation anchor came from a JSON map; the `evidence_selector.py` diversity anchor was map-sourced and Codex iter-1 P2-5 corrected it to `:532-704` + `:1513-1542` — fixed inline; all other anchors were read/grepped and spot-verified).

**Revision log — Codex plan-gate iter-1 (REQUEST_CHANGES) addressed inline:** P1-1 added the §6b competitor systems (Claude Research/Anthropic Citations API, MS Copilot Researcher, Grok); P1-2 specified the **origin-cluster weight-mass invariant** (copied rows cannot inflate claim-side mass); P1-3 **wired the clinical source-type veto** to the clinical adequacy floor (not a slogan); P2-4 made the drb_72 fixture audit-conditional; P2-5 corrected the `evidence_selector` anchor; P2-6 named the voter/arbiter integration point. **Iter-2 (REQUEST_CHANGES) addressed:** P1-2-continuing — replaced the row-level/averaging formula with the EXECUTABLE origin-cluster invariant (one `max(authority_score)` per `origin_cluster_id`, summed once per cluster; L3 emits `origin_cluster_id`); P2 — Phase 1 bibliography keys render only when the flag is ON (OFF byte-identical); P2 — split the clinical-veto test (Phase 6 = veto fires / not weight-adequate; Phase 7 = ABSTAIN/fringe rendering). **Iter-3 (REQUEST_CHANGES) addressed:** P1-2 made mathematically closed — `cluster_mass = authority(canonical origin)`, copies excluded, so a higher-authority copier joining a cluster cannot raise mass (+ copy-invariance fixture); Phase 4a emitted-contract made explicit (`origin_cluster_id` + canonical designation + copy flag, with a P6-groupability test); drb_72 Verification bullet made audit-conditional; Phase 6 clinical-veto bullet emits a signal (rendering moved to Phase 7); Phase 10 adds the `SENTINEL_ORIGINS` (`plan_sufficiency_gate.py`) update + fallback test. **Iter-4 (REQUEST_CHANGES) addressed:** replaced every remaining normative `max(authority_score)` with `authority_score(canonical_origin)` (§3 L3/L5 rows + Phase 4a scope) so the formula is consistent everywhere; tightened the clinical-veto wording (Phase 6 owns the `clinical_source_type_veto` emission, Phase 7 only renders); removed the duplicate `Files:` bullets in Phase 4a + Phase 7. **Iter-5: APPROVE** (Codex binding plan-gate, 0 P0 / 0 P1, convergence=accept_remaining). One P2 residual — keep the per-claim clinical source-type veto distinct from the corpus clinical adequacy floor — noted inline in Phase 6 for the implementation brief.

**Binding acceptance gate (READ FIRST).** The source doc does not stop at §4's six layers. Its §6 ends with:
> `proceed_to_plan: yes, CONDITIONAL on the plan incorporating 6a (no overstatement), 6b (added systems/benchmarks), and ALL of 6c (the 8 required layers).`
§6 is **authoritative over §4** where they differ. This plan therefore delivers against **all 8 of §6c**, honors §6a (no overstatement), and pulls §6b's systems/benchmarks into the test strategy. A clean six-layer plan that ignores §6c would *feel* complete and still fail this gate.

---

## 1. GOAL + NON-NEGOTIABLES

### 1.1 Goal

Turn POLARIS from a **count-and-tier-threshold** sourcing pipeline into a **credibility-WEIGHTED, independence-aware, per-claim-disclosed** one — the union that no deployed system offers (§3): a disclosed credibility weight that (a) is domain-conditional, (b) discounts non-independent corroboration *before* aggregation, and (c) actually drives composition and is shown per claim. We extend POLARIS's existing hard substrate — per-sentence `[#ev:id:start-end]` tokens + `strict_verify` + zero-verified-abort — from *provenance disclosure* to *provenance + weight + independent-origin-count + certainty disclosure*.

### 1.2 Non-negotiables (these override every design choice below)

1. **Faithfulness gates are preserved, never weakened.** The four gates stay intact and any verifier work is **additive-only**:
   - **strict_verify** (`provenance_generator.py:1156` `verify_sentence_provenance`) — six per-sentence checks (evidence-pool membership, span bounds, numeric match, ≥2 content-word overlap, trial-name, entailment). New work *adds* checks on top (§6c-7); it never relaxes one of the six.
   - **4-role / two-family segregation** (`check_family_segregation`, enforced e.g. `semantic_conflict_detector.py:346`) — untouched. Generator and evaluator stay cross-lineage.
   - **provenance token grammar** `[#ev:id:start-end]` — unchanged. New fields are *side-outputs* on `SentenceVerification`, never inputs to the verdict.
   - **corpus_approval_gate** (`corpus_approval_gate.py`, FX-05) — stays an **independent downstream backstop**. Weight-based adequacy does NOT bypass it; both gates run sequentially.
2. **No silent downgrade (LAW II + operator directive 2026-06-04).** Every new layer ships behind a flag, **default-OFF byte-identical**, fail-loud when its inputs are missing. Capability caps are surfaced and per-cap approved, never silently applied.
3. **Domain-aware, not a global hierarchy (§4 ISSUE 4 — "there is no universal evidence hierarchy").** Clinical weights RCT+peer-review+RoB; econ/policy weights design-validity over venue (the Nobel-validated shift — a strong NBER natural experiment must not rank below a weak peer-reviewed cross-section); qualitative weights coherence/adequacy. Domain is detected off the existing `scope_templates`.
4. **Sovereign + capture-resistant.** `authority_model.py` is already host-name-free, data-driven (LAW VI — "ZERO host names in code"). The credibility prior stays **multi-signal, self-computed, and OVERRIDABLE by the claim-level verifier** — no single external rater (NewsGuard/MBFC/Ad Fontes) hardwired as ground truth (the FTC-capture risk in §4 ISSUE 3).
5. **Clinical-safety weighting invariant (task §6 + §6c-8).** Web/news *volume* must never outweigh the **absence of clinical evidence**; medical/health misinformation is disclosed as **low-weight / fringe**, explicitly NOT normalized as an equal "side." Honest failure mode is **ABSTAIN** ("contested; no independent consensus"), never a fabricated balanced verdict.
6. **Weight beats count, and independence is collapsed before the vote** — the through-line of the whole source doc.

---

## 2. TARGET ARCHITECTURE — the 8 layers mapped onto our concrete files

The source doc frames a six-stage flow `retrieve → score → independence-collapse → aggregate → compose → disclose`. §6c **extends** this with three net-new layers (temporal/supersession, claim-graph-before-voting, retrieval dissent-recall) and four cross-cutting strengtheners (article+claim scoring, independence-beyond-TFIDF, calibration/audit, additive verifier). The table below is the full §6c-aware target; **REUSE** = existing code we re-wire, **BUILD** = genuinely new.

| # | Layer (flow stage) | What it does | REUSE (existing file:anchor) | BUILD (new) |
|---|---|---|---|---|
| L0 | **Retrieve broadly + dissent-recall** (§6c-6) | All-source-type retrieval; *actively seek* the best minority-side / contrary evidence; stratify by source-type | `live_retriever.py` retrieval lanes; subquery-reserve diversity pass `evidence_selector.py:552-660` (`_reserve_subqueries:602`); domain soft-cap `:661-704` (`_apply_domain_cap`); selection-time passes `:1513-1542` | dissent-recall sub-query expansion + source-type stratification quota (net-new, upstream of scoring) |
| L1 | **Score — two-axis, domain-conditional, article+claim** (§4 L1 + §6c-1) | Reliability × Relevance, primary axis chosen by domain; article-level (author/venue/method/funding/date/corrections) AND claim-specific relevance, not just host prior | `authority_model.py` signals A–E (scalar blend); `tier_classifier.py:135-142` additive fields `authority_score`/`corroboration_count`/`authority_confidence`; `scope_templates/` for domain | second **relevance** axis; domain-conditional rubric selector; article-level + claim-level decomposition (real BUILD — current blend is one field-agnostic scalar) |
| L2 | **Temporal / supersession** (§6c-2) | Downgrade stale-but-authoritative evidence (old guidelines, superseded regs/datasets, retracted/corrected) even when the source is high-authority | Signal E recency `recency.py` / `authority_model.py:138-145`; `is_retracted` in journal sidecar `journal_only_filter.py:237` | supersession rules (guideline/reg/dataset version), retraction → **hard** penalty surfaced per claim |
| L3 | **Independence-collapse — beyond near-duplicate** (§4 L2 + §6c-4) | Collapse content-copying / syndication / common-ownership / common-funding / shared-authorship / citation-chain / paraphrase clusters to ~1 origin BEFORE any weighted vote | `corroboration.py` eTLD+1 PSL host-collapse (`count_independent_hosts`, `registrable_domain`); `finding_dedup.py` already clusters by finding + counts independent registrable-domains (`dedup_by_finding`, host-based) | TF-IDF cosine ≥0.85 **content-copy detector** + ownership/funding/authorship signals on top of the host primitive (real BUILD — current collapse is host-based only) |
| L4 | **Claim-graph BEFORE aggregation** (§6c-3, NEW sub-layer) | atomic-claim extraction → normalization → stance clustering → contradiction/refutation detection → span entailment, so equivalent claims are clustered before any vote | `finding_dedup.py` numeric-finding clustering (seed, clinical-numeric only); `semantic_conflict_detector.py` + `qualitative_conflict_detector.py` + numeric `contradiction_detector.py` (stance/contradiction seeds); entailment path in `verify_sentence_provenance` | field-agnostic atomic-claim extractor + normalization + stance-cluster graph (real BUILD — finding_dedup is numeric-only and inert on non-clinical) |
| L5 | **Aggregate by weight, auditable non-averaging** (§4 L3) | Weighted Majority Voting over post-collapse independent origins; inverse-variance for quantitative; GRADE "lowest-among-critical" for multi-part certainty | `plan_sufficiency_gate.py` already uses `authority_score` as a numeric GATE (`:50`, `:301`) | replace COUNT aggregation (`plan_sufficiency_gate.py:313` `covered_count >= target`; journal `DEFAULT_MIN_DISTINCT_JOURNALS=12` `journal_only_filter.py:531`) with **origin-cluster weight-mass** (one weight per independent-origin cluster; copied rows cannot inflate mass — Phase 6 invariant) |
| L6 | **Contested-topic composition — weight-and-disclose-with-forewarning** (§4 L4 + §6c-8 multi-position) | Consensus side at high weight AND minority **attributed** at low weight, with explicit **forewarning** (the N=887 finding: forewarning works, outnumbering does not). Multi-position, not binary. Medical misinfo = low-weight/fringe. ABSTAIN over fabricated balance | cross-lineage multi-judge agreement via the EXISTING 4-role adjudication — integration point `roles/role_pipeline.py` + `honest_sweep_integration.py` (REUSE, do NOT build a parallel adjudication path); existing refuse/unresolved behavior; retraction flag | forewarning composition rule + multi-position (>2 side) disclosure policy + clinical-fringe down-weight |
| L7 | **Per-claim disclosure** (§4 L5 + §6c-1 claim-level) | Each verified sentence carries {span-verdict, credibility_weight, independent_origin_count, certainty_label}; rendered in bibliography; "Proof Replay" SUPPORTS-not-EXISTS UX | `SentenceVerification` additive-field precedent (`soft_warnings` `:427`, `judge_error` `:433`); `resolve_provenance_to_citations` `:1881` render point | four optional fields + bibliography render + certainty-label scoring fn |
| L8 | **Additive verifier strengthening** (§6c-7) | NLI/QA entailment + unit/table/quantity checks + contradiction-sensitive verification **ON TOP of** strict_verify's six (never weakening) | existing NLI advisory path; `semantic_conflict_detector.py`; numeric checks in `verify_sentence_provenance` | wire the advisory NLI/contradiction checks as additive fail-closed gates (flag-gated, ON-mode only) |
| Lx | **Calibration + audit** (§6c-5) + **adversarial benchmark** (§4 L6) | Brier/ECE reliability curves on the weights; blinded per-claim faithfulness eval; ablations per layer; SourceBench/DeepTRACE/ReportBench suites | existing manifest telemetry; `outputs/audits/` §-1.1 harness | calibration metric script + adversarial vax fixture + benchmark harness (test infra, not pipeline) |

**Reuse vs build, in one honest sentence each:**
- **`authority_model.py`** blends A–E into ONE field-agnostic scalar — the second (relevance) axis + domain conditioning is a real BUILD, not a rewire.
- **`finding_dedup.py` / `corroboration.py`** give us the independent-origin PRIMITIVE, but **host-based** only; §6c-4 content-copy detection is a BUILD on top.
- **`SentenceVerification` + `resolve_provenance_to_citations`** are the disclosure substrate — additive fields, lowest-risk first phase.
- **`plan_sufficiency_gate.py`** already treats `authority_score` as a numeric gate — converting its COUNT aggregation to WEIGHT-MASS is a small, surgical re-wire.

---

## 3. GAP TABLE — per layer: HAVE vs NEEDED vs the file:line change

| Layer | HAVE | NEEDED | Specific change (file:line) |
|---|---|---|---|
| L0 dissent-recall | breadth retrieval + diversity passes (`evidence_selector.py:532-704` subquery-reserve+domain-cap, `:1513-1542`) | active minority-side retrieval + source-type stratification | new sub-query expansion lane in `live_retriever.py` retrieval orchestration; a `dissent_seed` origin (mirror the existing `agentic_seed`/`deepener_seed` sentinel lanes in `plan_sufficiency_gate.py:53-59`) |
| L1 two-axis score | scalar `authority_score` blend A–E (`authority_model.py:159-170`); domain in `scope_templates` | **relevance** axis + domain-conditional rubric + article/claim decomposition | add `relevance_score` to `AuthorityResult` (`source_class.py:75`); new `credibility_prior.py` selecting rubric off detected domain; emit on rows in `tier_classifier.py:2035-2038` |
| L2 temporal/supersession | Signal E recency; `is_retracted` (`journal_only_filter.py:237`) | supersession downgrade + retraction hard penalty per claim | new `supersession.py` rule module; consume in L1 score as a multiplier; surface as a `soft_warning` + certainty downgrade |
| L3 independence-collapse | host eTLD+1 collapse (`corroboration.py:58-64`); finding-clustering (`finding_dedup.py:121`) | **content-copy** TF-IDF ≥0.85 + ownership/funding/authorship | new `independence_collapse.py`; emits a stable `origin_cluster_id` + membership per row (NOT just `independent_origin_count`); runs BEFORE L5 (which takes `authority_score(canonical_origin)` once per origin cluster; derivative copies contribute zero) |
| L4 claim-graph | numeric finding clusters (`finding_dedup.py`); conflict detectors | field-agnostic atomic-claim graph + stance clustering | new `claim_graph.py`; reuses conflict detectors for the contradiction/refutation edges; gates L5 (vote only over clustered-equivalent claims) |
| L5 weighted aggregate | COUNT thresholds (`plan_sufficiency_gate.py:313`); journal COUNT floor (`journal_only_filter.py:531,596`) | origin-cluster weight-mass = Σ over origin clusters of `authority_score(canonical_origin)` (one mass per `origin_cluster_id` = its canonical origin's authority; derivative copies contribute zero; NO row-level term, NO max-over-copies — Phase 6 invariant) | replace `covered_count >= target` with `weight_mass >= weight_target` (`plan_sufficiency_gate.py:312-317`); add `assess_journal_only_adequacy` weight path (`journal_only_filter.py:543-607`); consumes L3 `origin_cluster_id` |
| L6 forewarning compose | refuse/unresolved; 4-role agreement | weight-and-disclose-with-forewarning; multi-position; clinical-fringe | new composition rule in the generator's contested-claim path; forewarning string injected via `soft_warnings` channel |
| L7 per-claim disclose | `SentenceVerification` fields; bibliography render | 4 new optional fields + render | add `span_verdict`/`credibility_weight`/`independent_origin_count`/`certainty_label` to `SentenceVerification` (`provenance_generator.py:419-433`); extend bibliography dict (`:1897-1903`) |
| L8 additive verifier | strict_verify six checks; advisory NLI | NLI/unit/contradiction as additive fail-closed gates | new `additive_verifiers.py` invoked AFTER the six checks in `verify_sentence_provenance`; ON-mode flag-gated, never relaxes the six |
| Lx calibration/bench | manifest telemetry; §-1.1 harness | Brier/ECE + ablations + vax fixture + suites | new `tests/fixtures/credibility/` + `scripts/credibility_calibration.py`; benchmark harness for §6b suites |

**§6a corrections honored (no overstatement):** AuthorityBench is cited only as an authority-PERCEPTION benchmark, NOT a volume-vulnerability benchmark. DeepTRACE Perplexity numbers are framed "low minimum-cover / weak grounding," not "94.5% decorative." RA-RAG is the aggregation primitive AFTER independence-collapse, not a solution to it. The "79%→17% tool-call collapse" stat is replaced by the supportable "39–77% factual accuracy / ~42% average fact-check drop." CAG is EMNLP 2024 and its labels are relevance/timeliness, not source authority. RAGRank is inspiration (CTI PoC), not a validated web echo detector. Community-Notes/Elicit stats are flagged as needing their own primary citations before being treated as settled.

---

## 4. PHASED DELIVERY

**Phasing spine (the codebase's own proven pattern).** Every new layer ships behind a flag, **default-OFF byte-identical**, activated only in the Gate-B slate — exactly how `journal_only_active(protocol)`, `judge_error`, and `quantified_models=None` already behave. This single discipline yields: ≤200-LOC self-contained Codex-gated phases, "no silent downgrade," AND a trivially-true faithfulness-safety argument per phase (OFF ⇒ byte-identical output + identical rendered artifacts). The disclosure SCHEMA ships first as inert plumbing; independence-collapse populates it later (per the JSON map's own warning: do not deploy *populated* per-claim disclosure until independence-collapse exists).

Each phase below = one GitHub Issue, one brief → Codex APPROVE → one diff → Codex APPROVE on the Red-Team checklist (the standard §3.0 triple). Phases are ordered by dependency and risk; the claim-graph (L4) and two-axis rescore (L1) are explicitly decomposed because neither fits in a single ≤200-LOC unit.

> **Honest sizing note:** L4 claim-graph and L1 two-axis are NOT one ≤200-LOC phase each. They are split (P4a/P4b, P2a/P2b). Where a phase legitimately exceeds 200 LOC, it requests a documented §3.0 LOC exemption in the brief rather than being split into incoherent halves.

### Phase 1 — Disclosure schema (inert plumbing). [L7, lowest risk]
- **Scope:** Add four optional fields to `SentenceVerification` (dataclass-only inert plumbing). The bibliography render is NOT changed here — the four keys are emitted ONLY when the credibility-disclosure flag is ON (Phase 8), so OFF stays byte-identical (Codex iter-2 P2: extra empty keys would break byte-identity). NO population yet (defaults: `span_verdict=""`, `credibility_weight=None`, `independent_origin_count=None`, `certainty_label=""`).
- **Files:** `provenance_generator.py:419-433` (dataclass only). The bibliography dict (`:1897-1903`) is touched in Phase 8 (flag-gated render), NOT here.
- **Change:** add the four fields with safe defaults; NO bibliography-render change (preserves OFF byte-identity); token grammar + `is_verified` untouched.
- **Offline tests:** backward-compat (old callers read new objects); OFF byte-identity of rendered report + bibliography; the six strict_verify checks unchanged.
- **Verification:** diff shows only additive fields; smoke run produces byte-identical `report.md` with empty new fields.
- **Faithfulness-safety:** new fields are side-outputs, never inputs to the verdict. OFF = byte-identical. Trivially safe.

### Phase 2a — Relevance axis + domain rubric selector (score, part 1). [L1]
- **Scope:** Add a second `relevance_score` axis to `AuthorityResult`; a `credibility_prior.py` that selects the primary axis off the detected domain (clinical/econ-policy/qualitative) from `scope_templates`. Flag-gated; OFF ⇒ legacy scalar unchanged.
- **Files:** `source_class.py:75` (AuthorityResult), new `authority/credibility_prior.py`, `tier_classifier.py:2035-2038` (emit).
- **Change:** compute relevance (directness-to-question) and conditionally select the reliability rubric; emit both axes additively.
- **Offline tests:** econ natural-experiment (NBER) must out-score a weak peer-reviewed cross-section **only when the flag is ON**; OFF byte-identity; thin-signal → honest LOW confidence (never fabricated HIGH).
- **Verification:** diff is additive-fields-only; OFF smoke produces byte-identical `report.md` + manifest; the two-axis selection-flip is reproducible on the unit fixture.
- **Faithfulness-safety:** SELECTION-side only — `verify_sentence_provenance` and the six checks are untouched; scoring changes WHICH rows are billed, not how a claim verifies its span; corpus_approval backstop still runs. OFF = byte-identical.

### Phase 2b — Article-level + claim-level decomposition (score, part 2). [L1 + §6c-1]
- **Scope:** Decompose the prior into author/venue/method/funding/date/corrections (article) AND claim-specific relevance, disclosed sub-criteria NewsGuard-style; overridable by the verifier.
- **Files:** `credibility_prior.py`, `authority_model.py` signal plumbing.
- **Offline tests:** decomposed sub-scores sum/compose correctly; a high-venue but stale/retracted article scores lower than a fresh direct one; capture-resistance test (no single external rater can flip a verdict alone).
- **Verification:** additive-fields diff; OFF byte-identity smoke; decomposition unit fixture reproduces the sub-scores.
- **Faithfulness-safety:** SELECTION-side only — verifier and the six checks untouched; the decomposed prior is overridable by the claim-level verifier (capture defense); corpus_approval still runs. OFF = byte-identical.

### Phase 3 — Temporal / supersession + retraction hard penalty. [L2, §6c-2]
- **Scope:** `supersession.py` downgrade rules for superseded guidelines/regs/datasets; retraction → hard penalty + per-claim surfacing.
- **Files:** new `authority/supersession.py`; consume in `credibility_prior.py`; surface via `soft_warnings` + certainty downgrade.
- **Offline tests:** an old-guideline source is downgraded vs the current one; a retracted source is hard-penalized and the penalty surfaces per claim.
- **Verification:** additive-fields diff; OFF byte-identity smoke; supersession + retraction rules reproduce on the unit fixture.
- **Faithfulness-safety:** SELECTION/disclosure-side only — verifier and the six checks untouched; downgrade surfaces as a `soft_warning` (additive channel, existing precedent), never drops a verified span. OFF = byte-identical.

### Phase 4a — Content-copy / syndication detector (independence, part 1). [L3, §6c-4]
- **Scope:** `independence_collapse.py` — TF-IDF cosine ≥0.85 near-duplicate clustering over the retrieved corpus, layered on the existing host-collapse primitive. Curated acceptable-mirror handling (arXiv/SSRN/PMC) to bound false positives. **Emits a stable `origin_cluster_id` + canonical-origin designation + cluster membership per row** (L5 takes one `authority_score(canonical_origin)` mass per cluster — derivative copies contribute zero — Codex iter-3), not merely a scalar `independent_origin_count`.
- **Files:** new `synthesis/independence_collapse.py`; reuse `corroboration.py:58-64` + `finding_dedup.py` host primitive.
- **Offline tests:** 50 near-verbatim copies of one press release collapse to `independent_origin_count≈1`; legitimate parallel reporting / arXiv mirror does NOT over-collapse (false-positive bound).
- **Verification:** new-module diff (no edits to verifier or selection paths yet). **Phase 4a MUST emit, per row: a stable `origin_cluster_id`, the canonical-origin designation + cluster membership, a copy/derivative flag, AND `independent_origin_count`** — with a test asserting P6 can group by `(claim_cluster_id, origin_cluster_id)` and that copies are flagged (so P6's origin-cluster mass is computable); OFF byte-identity smoke; collapse + false-positive fixtures reproduce.
- **Faithfulness-safety:** pure scoring side-output; touches no faithfulness gate; collapse NEVER drops a source, only de-weights duplicated corroboration. OFF = byte-identical.

### Phase 4b — Ownership / funding / authorship / citation-chain signals (independence, part 2). [L3, §6c-4]
- **Scope:** Extend the collapse beyond content-copy to common-ownership/funding/shared-authorship/citation-chain/paraphrase clusters.
- **Files:** `synthesis/independence_collapse.py`.
- **Offline tests:** common-owner network collapses even without verbatim copy; independent same-finding sources keep `independent_origin_count > 1`.
- **Verification:** additive-signal diff; OFF byte-identity smoke; ownership/funding fixtures reproduce.
- **Faithfulness-safety:** pure scoring side-output; no faithfulness gate touched; never drops a source. OFF = byte-identical.

### Phase 5a — Atomic-claim extractor + normalization (claim-graph, part 1). [L4, §6c-3]
- **Scope:** Field-agnostic atomic-claim extraction + normalization (generalizes `finding_dedup.py`'s clinical-numeric-only extractor, which is inert on non-clinical numerics).
- **Files:** new `synthesis/claim_graph.py`; reuse `contradiction_detector.extract_numeric_claims` as one extractor among several.
- **Offline tests:** non-clinical numerics (GDP, emissions) now produce claims (current `finding_dedup` returns nothing); conservative-singleton safety preserved (never over-merge distinct claims).
- **Verification:** new-module diff; OFF byte-identity smoke; the conservative-singleton safety rule (never over-merge distinct claims) reproduces on the `finding_dedup` clinical fixtures.
- **Faithfulness-safety:** pre-aggregation analysis side-output; touches no faithfulness gate; default on ambiguity is "keep separate" (no distinct-claim loss). OFF = byte-identical.

### Phase 5b — Stance clustering + contradiction edges (claim-graph, part 2). [L4, §6c-3]
- **Scope:** Stance clustering + contradiction/refutation/entailment edges over the normalized claims, reusing the three conflict detectors.
- **Files:** `synthesis/claim_graph.py`; reuse `semantic_conflict_detector.py`/`qualitative_conflict_detector.py`/`contradiction_detector.py`.
- **Offline tests:** equivalent claims cluster; contradictory claims form an edge (recall-first on the refutes class per §4 L4 — over-detect, fail loud); the graph gates L5 (vote only over clustered-equivalents).
- **Verification:** new-edge-builder diff; OFF byte-identity smoke; stance + contradiction fixtures reproduce; the three detectors' existing fail-open/recall-first behavior is unchanged.
- **Faithfulness-safety:** analysis side-output; the conflict detectors keep their existing safety contracts (semantic fail-open never fabricates a conflict; qualitative escalates-to-review never silent-drops). OFF = byte-identical.

### Phase 6 — Weighted aggregation (replace count with weight-mass). [L5]
- **Scope:** Replace COUNT aggregation with **origin-cluster weight-mass**, computed by this EXECUTABLE invariant (Codex iter-2 P1-2): group every supporting row by `(claim_cluster_id, origin_cluster_id)`; for each origin cluster L3 designates exactly ONE **canonical origin** (the syndication root / earliest independent publication; the other members are derivative copies — genuinely-INDEPENDENT corroboration has different content and forms its OWN cluster, it does not join an existing one). `cluster_mass = authority_score(canonical origin)`; copy/derivative members are attributed for disclosure ("N copies → 1 origin") but contribute ZERO to the mass. The claim-side weight-mass = Σ of `cluster_mass`, once per origin cluster within the claim cluster. **No row-level term, no averaging, no max-over-copies.** A row joins an existing `origin_cluster_id` only because L3 flagged it a copy of that cluster's canonical origin — so it adds NOTHING to the mass **even if its own `authority_score` is higher than the canonical origin's** (a high-authority verbatim republisher is still derivative; only its own *independent* content would form a new cluster). **Binding invariant (mathematically closed, Codex iter-3):** `weight_mass(rows + copied_row) == weight_mass(rows)` for ANY authority of the copier, whenever the added row joins an existing origin cluster. This requires **L3 to emit a stable `origin_cluster_id`, the canonical-origin designation, and membership** (NOT merely an `independent_origin_count` scalar) and L4 to emit `claim_cluster_id`, both BEFORE L5. Without it, copied rows re-inflate the false majority and the vax test fails. Applies in plan-sufficiency AND journal-only adequacy. Per-facet weighting preserved.
- **Files:** `plan_sufficiency_gate.py:312-317` (verdict math), `journal_only_filter.py:543-607` (`assess_journal_only_adequacy` weight path; demote `DEFAULT_MIN_DISTINCT_JOURNALS=12` count-floor to a weight-floor when journal-only is NOT protocol-pinned).
- **Clinical source-type veto (Codex iter-1 P1-3 — wired, not a slogan):** a clinical-domain claim requires ≥1 **independent clinical-tier source (T1/T2 clinical)** in its origin-clustered support; if absent, Phase 6 emits a **`not_weight_adequate` / `clinical_source_type_veto`** signal REGARDLESS of news/commercial weight-mass; **Phase 7 (L6) consumes that signal to render ABSTAIN/fringe** (the rendering is Phase 7, not here). Wired to the existing clinical adequacy floor (`corpus_adequacy_gate.py` `_DEFAULT_DOMAIN_THRESHOLDS['clinical']`: `min_t1_count=3`, `min_t1_plus_t2=5`) The source-type veto is OWNED and EMITTED at Phase 6 (the `clinical_source_type_veto` signal); web/news/commercial weight can NEVER substitute for the clinical-tier floor; Phase 7 only RENDERS the resulting ABSTAIN/fringe. **Brief-time note (Codex iter-5 P2):** the per-claim source-type VETO (a claim needs ≥1 independent clinical-tier source) is DISTINCT from the corpus-level clinical adequacy FLOOR (`min_t1_count=3`, `min_t1_plus_t2=5`) — the Phase-6 implementation brief must keep them separate (the veto is a per-claim absence-check; the floor is a corpus threshold). They are not the same gate and must not be conflated.
- **Offline tests:** **the vax adversarial test** (N independent-LOOKING-but-copied low-cred sources vs few high-cred — naive count flips to the false majority, weight+collapse picks the high-cred side); **copy-invariance fixture (Codex iter-3): a copier whose own `authority_score` is HIGHER than the cluster's canonical origin joins that origin cluster → `weight_mass` is UNCHANGED (the copier is derivative, excluded from the cluster mass)**; drb_72 regression **(CONDITIONAL on the journal-only audit, Decision #4)** — assert weight-floor passage for drb_72 ONLY if the audit confirms journal-only was an implementation choice, not a protocol requirement; otherwise assert on a non-protocol-pinned fixture (a protocol-pinned `source_restriction: journal_only` keeps its hard T1+T2 filter); corpus_approval still blocks material-deviation auto-approve even when weight-adequate (AuthorizedSweep still required); **clinical veto test (adequacy-level, Codex iter-2)** — a clinical claim with only news/commercial support is **NOT weight-adequate** / the clinical source-type veto fires (the T1/T2 clinical-tier floor is empty), even at high weight-mass. The ABSTAIN/fringe *rendering* is asserted in Phase 7 (L6 composition), not here.
- **Verification:** the count→weight flip is reproducible on the vax fixture (naive count picks the false majority; weight-mass + independence-collapse does not); drb_72 regression **(CONDITIONAL on Decision #4 / the journal-only audit)** passes adequacy at the weight-floor ONLY if the audit confirms journal-only was implementation-only (else assert on a non-protocol-pinned fixture); OFF byte-identity smoke confirms the legacy count path is unchanged with the flag off; corpus_approval still fires on the material-deviation fixture.
- **Faithfulness-safety:** **both gates run sequentially** — weight-based adequacy + the independent corpus_approval tier-distribution backstop. A single high-authority source OR a news pile-up cannot clear the bar alone (independence multiplier + tier-distribution range). corpus_approval is untouched.

### Phase 7 — Forewarning composition + multi-position policy. [L6, §6c-8]
- **Scope:** Contested-claim composition rule: consensus at high weight + minority attributed at low weight + explicit forewarning; multi-position (>2 sides); medical-misinfo low-weight/fringe; ABSTAIN over fabricated balance.
- **Files:** generator contested-claim path; forewarning via `soft_warnings`.
- **Offline tests:** vax case emits forewarning + attributed minority (not 50/50, not censored); a 3-position dispute is not forced binary; a medical-misinfo claim is disclosed fringe, never equal-side; a clinical claim that failed the Phase-6 clinical source-type veto renders as ABSTAIN/fringe (the rendering half of the split test); no-independent-consensus → ABSTAIN.
- **Verification:** OFF byte-identity smoke; ON-mode the vax/multi-position/fringe/abstain fixtures reproduce; the forewarning text appears in the rendered report only on the ON path.
- **Faithfulness-safety:** composition/disclosure-side only — verifier and the six checks untouched; forewarning rides the additive `soft_warnings` channel; ABSTAIN reuses existing refuse/unresolved behavior (never fabricates a verdict). OFF = byte-identical.

### Phase 8 — Per-claim disclosure population. [L7, depends on P4/P5/P6]
- **Scope:** Populate the four Phase-1 fields from the upstream layers; turn on the "SUPPORTS-not-EXISTS" Proof-Replay render.
- **Files:** `provenance_generator.py` (population call sites for the Phase-1 fields), `resolve_provenance_to_citations`.
- **Offline tests:** end-to-end populates `credibility_weight` + `independent_origin_count` ("N sources → M origins") + `certainty_label` + `span_verdict`; bibliography renders all four; OFF byte-identity retained.
- **Verification:** OFF byte-identity smoke (empty fields); ON-mode end-to-end fixture shows all four populated + rendered; `is_verified` and the rendered prose body are byte-identical between OFF and ON (only the metadata sidecar differs).
- **Faithfulness-safety:** the four fields remain SIDE-OUTPUTS — never inputs to `is_verified` or the six checks; population reads upstream layer outputs, writes only the disclosure sidecar. OFF = byte-identical.

### Phase 9 — Additive verifier strengthening. [L8, §6c-7] — **HIGHEST FAITHFULNESS RISK; the only phase that edits `verify_sentence_provenance`.**
- **Scope:** Wire NLI/QA entailment + unit/table/quantity + contradiction-sensitive checks as **additive fail-closed gates** invoked AFTER the six strict_verify checks. ON-mode flag-gated.
- **Files:** new `generator/additive_verifiers.py`; a single call site appended AFTER the six checks in `verify_sentence_provenance` (`provenance_generator.py:1156`).
- **Offline tests:** the six checks are byte-identical with the flag OFF; ON-mode a span that passes the six but fails NLI is dropped (fail-closed); a sentence that PASSES the six is NEVER relaxed into a fail by the off path; the existing `judge_error` fail-closed contract is preserved.
- **Verification:** the six-check regression suite passes byte-identical with the flag OFF (this is the gating assertion); ON-mode adds drops, never adds passes; CI runs the full faithfulness-guard suite (the 113-test guard) against this diff.
- **Faithfulness-safety:** **flagged as the single highest-risk phase** — it is the only diff that touches the faithfulness-critical `verify_sentence_provenance`. The new checks are STRICTLY ADDITIVE and fail-closed (they can only DROP a sentence, never admit one the six rejected, and never relax one the six accepted). Warrants the hardest Codex scrutiny and its own explicit operator sign-off line in the brief; recommend it ship LAST among the verifier-adjacent phases. OFF ⇒ the six checks are byte-identical.

### Phase 10 — Dissent-recall retrieval + source-type stratification. [L0, §6c-6]
- **Scope:** Active minority-side retrieval + source-type stratification quota upstream of scoring.
- **Files:** `live_retriever.py` orchestration; new `dissent_seed` sentinel lane; **update `SENTINEL_ORIGINS` in `plan_sufficiency_gate.py`** so `dissent_seed` rows are fallback-creditable (mirrors `agentic_seed`/`deepener_seed`), with a unit test proving the fallback credit.
- **Offline tests:** a contested query retrieves the strongest contrary evidence (recall metric on a labeled fixture); stratification quota fills under-represented source types.
- **Verification:** OFF byte-identity smoke (no extra retrieval calls billed); ON-mode the dissent-recall fixture shows the contrary evidence retrieved; the new `dissent_seed` origin is fallback-eligible in plan-sufficiency exactly like the existing seed lanes.
- **Faithfulness-safety:** retrieval-side only — broadens the corpus, does not touch verification; more source-types STRENGTHEN corpus_approval's tier-distribution check. Spend-bearing on the ON path → gated behind the live-run authorization, never silently. OFF = byte-identical.

### Phase 11 — Calibration + adversarial benchmark harness. [Lx, §6c-5 + §4 L6 + §6b]
- **Scope:** Brier/ECE reliability curves on the weights; per-layer ablations (retrieve/score/collapse/aggregate); the vax fixture promoted to a CI benchmark; §6b suites (SourceBench, DeepResearch Bench, DRBench, BrowseComp-Plus, ResearchRubrics) + DeepTRACE/ReportBench wired as offline eval targets.
- **Files:** `scripts/credibility_calibration.py`; `tests/fixtures/credibility/`.
- **Offline tests:** calibration runs and emits a reliability curve; ablation shows each layer's marginal contribution; weight-beats-count is proven on the vax fixture.
- **Verification:** the harness is test/script infra only (no pipeline edit) — its presence is byte-neutral to the production path; the vax-fixture assertion (count flips, weight+collapse does not) is the load-bearing pass/fail.
- **Faithfulness-safety:** offline measurement infrastructure; touches no production faithfulness gate. Any live eval steps are spend-gated behind `PG_AUTHORIZED_SWEEP_APPROVAL`.

**Dependency order:** P1 (schema) → P2a/P2b (score) → P3 (temporal) → P4a/P4b (independence) → P5a/P5b (claim-graph) → P6 (aggregate) → P7 (compose) → P8 (populate disclosure) → P9 (verifier) → P10 (retrieval) → P11 (calibration). P10 is upstream conceptually but ships late because it depends on the scoring/collapse machinery to evaluate dissent-recall quality; P1 ships first as inert plumbing.

---

## 5. TEST + VERIFY STRATEGY

1. **Unit (per phase):** every new module is a PURE function with fixtures in `tests/fixtures/credibility/` (LAW VI — no live data in unit tests). Backward-compat + OFF byte-identity asserted on every phase.
2. **Integration:** end-to-end smoke that the layers compose (score → collapse → claim-graph → aggregate → compose → disclose) and that **corpus_approval still gates** when weight-adequate.
3. **The adversarial vax fixture (the load-bearing test, §4 L6):** a labeled `tests/fixtures/credibility/vax_volume_vs_weight.json` — N independent-LOOKING-but-content-copied low-credibility sources vs a few high-credibility independent ones. **Assert:** naive count picks the false majority; weight + independence-collapse picks the high-credibility side; per-claim disclosure shows the forewarning. This is the concrete proof that **weight beats count** and **independence-collapse works**.
4. **Blinded per-claim faithfulness eval (§4 L6):** POLARIS's own blinded eval (not self-graded LLM scores — the Exa circular-eval / Co-STORM marketing-gap risk). Run claim-by-claim vs the cited span per §-1.1, against Scholar QA / OpenScholar as the honest BEAT-BOTH baseline.
5. **AuthorityBench-style adversarial benchmark + §6b suite:** wire SourceBench, DeepResearch Bench, DRBench, BrowseComp-Plus, ResearchRubrics, DeepTRACE, ReportBench as offline eval targets. **Per §6a, AuthorityBench is used as an authority-PERCEPTION benchmark only**, not a volume-vulnerability one. **Competitor head-to-head (Codex iter-1 P1-1)** must cover the added §6b deployed systems — OpenAI / Gemini / Perplexity Deep Research PLUS Claude Research (+ Anthropic Citations API), Microsoft 365 Copilot Researcher, and Grok DeepSearch — none of which discloses a credibility weight; POLARIS is scored against all on per-claim faithfulness + the weight/origin-count/certainty disclosure they lack.
6. **Calibration (§6c-5):** Brier score / ECE / reliability curves on the credibility weights; ablations isolating retrieve/score/collapse/aggregate so we can show each layer's marginal contribution.
7. **Proving independence-collapse:** the vax fixture + a false-positive bound test (legitimate parallel reporting and arXiv/PMC mirrors must NOT over-collapse).

---

## 6. RISKS + MITIGATIONS

| Risk | Mitigation |
|---|---|
| **Single-source authority capture** (low weight_target lets one high-authority source clear the bar) | corpus_approval tier-distribution backstop runs independently AFTER weight-adequacy; `independent_origin_count` multiplier requires multiple independent origins, not just a high scalar. Both gates sequential. |
| **Capture-resistance / single external rater hardwired** | The prior is multi-signal, self-computed (`authority_model.py` is host-name-free, LAW VI), and **overridable by the claim-level verifier**. No NewsGuard/MBFC/Ad Fontes verdict is ground truth (the FTC-capture risk, §4 ISSUE 3). |
| **Echo-collapse false positives** (legitimate parallel reporting / CDN / arXiv mirrors collapsed as "same origin") | Curated acceptable-mirror handling; TF-IDF ≥0.85 + a short time-window; a dedicated false-positive bound test; collapse never *drops* a source, only de-weights duplicated corroboration. |
| **Clinical safety — news outweighs absence of clinical evidence** | Hard weighting-policy invariant (§1.2.5): web/news volume cannot outweigh missing clinical evidence; medical misinfo disclosed low-weight/fringe, never equal-side; ABSTAIN over fabricated balance. Recall-first on the refutes class (a missed refutation is the lethal error). |
| **Thin-signal honesty** (sparse OpenAlex / non-English venues) | `authority_confidence` defaults to LOW on thin signals (existing Phase-0a contract); certainty_label inherits it — never a fabricated HIGH. |
| **Two-axis weight tuning** (no published numeric thresholds; our blend is not inverse-variance) | weight_target/weight_per_facet are config (LAW VI), domain-calibrated; left as an OPEN DECISION (§8) for operator policy; calibration harness (P11) validates against the vax fixture before any spend. |
| **Journal-only softening regresses protocol intent** | When a protocol declares `source_restriction: journal_only`, the hard T1+T2 filter stays (protocol fidelity). Softening to a credibility prior applies ONLY when journal-only is NOT protocol-pinned. Audit all drb_72-like protocols before flipping. |
| **Faithfulness-gate regression** | Every phase is flag-gated default-OFF byte-identical; the six strict_verify checks are never relaxed (§6c-7 is additive-only); corpus_approval/4-role/two-family untouched. CI byte-identity test per phase. |

---

## 7. ITERATION-TO-APPROVAL

- **Per phase:** standard §3.0 triple — Claude authors `.codex/<issue_id>/brief.md` (opening with the verbatim §8.3.1 cap directive) → Codex APPROVE on the brief → Claude writes `codex_diff.patch` → Codex APPROVE on the Red-Team checklist. **5-iteration cap** per gate (§8.3.1); iter-5 REQUEST_CHANGES → force-APPROVE on remaining non-P0/P1 + residuals captured as follow-up Issues. Codex is the only gate.
- **Resource discipline (§8.4):** parallel codex allowed rate-controlled (2-3, AIMD back-off on 429), PID-scoped child cleanup, no heavy ML/CUDA in the autonomous loop (the TF-IDF/NLI heavy paths run only on operator-authorized smoke, not in the Codex loop).
- **Overall acceptance bar:**
  1. **Beat-both on the 5 golden questions** (DRB-EN #72/#75/#76/#78/#90) — the citation-faithfulness stress slice, clinical-3 + overall-5 reported separately; head-to-head vs the full §6b competitor set (OpenAI/Gemini/Perplexity/Claude Research/Copilot Researcher/Grok).
  2. **§-1.1 line-by-line audit** of every user-visible claim against the cited span (PRISMA/AMSTAR-2/GRADE per claim) — the ONLY acceptable evaluation; no metadata/pattern/count audit.
  3. The vax fixture proves weight beats count + independence-collapse works.
  4. All phases default-OFF byte-identical; faithfulness gates verified intact.

---

## 8. OPEN DECISIONS FOR THE OPERATOR

1. **Domain weighting policy.** Confirm the three primary-axis rubrics: clinical → RCT+peer-review+RoB; econ/policy → design-validity over venue (NBER natural experiment can be near-apex); qualitative → CERQual coherence/adequacy. Are there additional domains (regulatory, legal) that need their own rubric? And the numeric `weight_target` / `weight_per_facet` defaults — set by operator policy + P11 calibration, or deferred to a calibration-driven default?
2. **Default dissent visibility.** On a contested claim, is the minority side shown **by default** with forewarning, or only on an "expand dissent" affordance? (The N=887 finding favors always-visible forewarning; confirm for the demo UX.)
3. **Where to start.** Recommended: **Phase 1 (disclosure schema, inert plumbing)** — lowest risk, ships the substrate every later layer populates, zero faithfulness exposure. Alternative if you want the headline capability first: Phase 4a (independence-collapse) is the single biggest lead opportunity but depends on nothing schema-side and can run in parallel with P1. Confirm the starting phase.
4. **Journal-only audit scope.** Before P6 softens the journal-only count-floor, do you want a full audit of all drb_72-like protocols to confirm journal-only was a *protocol requirement* vs an *implementation choice*? (Default: yes, audit first.)
5. **Spend gating.** P11 calibration + the blinded faithfulness eval + the beat-both run are the only spend-bearing steps; everything else is offline. Confirm these stay behind `PG_AUTHORIZED_SWEEP_APPROVAL` + operator-set budget, as today.
