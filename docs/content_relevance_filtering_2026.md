# Post-Extraction Content-Relevance Filtering — Frontier Research (2026)

**Strand:** addendum to the fetch/extraction bake-off (#1297). "Keyword-matching crap pollutes findings."
**Scope:** POST-fetch CONTENT-relevance / passage-quality filtering that **DROPS** useless-but-keyword-matching
fetched content — distinct from the RERANKER (which ORDERS) and distinct from boilerplate stripping
(already handled by `clean_fetch_body`, do NOT re-research that).
**Sovereignty:** OSS-deployable + self-hostable for the AI layer. Serper/Zyte allowed as plumbing. **Exa + Tavily BANNED.**
**Date:** 2026-06-24. Author: Claude. Floor read at HEAD of `bot/I-beatboth-011-keystone-cert-enablers`.

---

## 0. TL;DR (the pick / design to beat)

The pipeline already gates **topical relevance** at three points, but **all three are
similarity-based on title+snippet or on the extracted span — none of them is a relevance
JUDGMENT of the full fetched body.** A high embedding-cosine (or a high keyword overlap) is
*exactly* what lets "keyword-matching crap" through: a page that name-drops the query terms but
never answers the question scores high on cosine and survives. That is the gap.

**Provisional design — `passage_relevance_judge` (a new post-extraction DROP layer):** an
instruction-conditioned **cross-encoder judge** that reads `(research_question ∪ sub-queries, fetched
passage)` and emits a calibrated `[0,1]` "does this passage actually answer the question" probability.
Below a fail-open floor → the passage is dropped as **off-topic/non-answering** (the ONE axis §-1.3
permits to filter) with a telemetry ledger entry; never a count cap, never a quality percentile, never a
breadth target. Credibility/tier untouched; faithfulness engine untouched.

- **Deployable pick (sovereign, commercial-clean): `Qwen/Qwen3-Reranker-0.6B`** (or 4B), **Apache-2.0**,
  used in **judge-mode with a custom instruction + a yes/no probability threshold** (it can DROP, not
  just order). Verified: outputs `true_score = exp(true_logit)/(exp(true_logit)+exp(false_logit))`.
- **Design-to-beat blueprint (method, NOT deployable as weights): Provence** (arXiv 2501.16214, Jan 2025) —
  unifies pruning+reranking; SOTA but **CC-BY-NC-4.0 → BANNED for commercial weights** (inspiration only).
- **Maximally-sovereign alternative: an LLM-judge on the existing GLM-5.2 backbone** using the
  **UMBRELA** 0–3 graded-relevance prompt (arXiv 2406.06519, TREC-2024-validated). Zero new model to host.

The honest recommendation (§7) is a **two-stage** design: cheap Qwen3-Reranker-0.6B judge as the always-on
floor, GLM-5.2 UMBRELA-judge as an escalation/audit lane — because precision is the headline metric and a
small cross-encoder is fast enough to run on every fetched passage.

---

## 1. Current floor (what POLARIS does today, with file:line)

Active pipeline = **A** (`scripts/run_honest_sweep_r3.py` → `run_live_retrieval`). The relevant code is
`src/polaris_graph/retrieval/live_retriever.py` + `evidence_selector.py` + `prefetch_offtopic_filter.py`.

### 1.1 EXISTING relevance gates — all PRE-fetch on title+snippet; POST-fetch has NO relevance filter

**Wiring verified at the call site (not the docstring):**

| # | Stage | Mechanism | File:line | What it scores | Wired on active path? | Gap |
|---|---|---|---|---|---|---|
| G1 | **PRE-fetch rerank** | lexical token-overlap, count-cut | `live_retriever.py:3114` `_lexical_relevance_score` + `:3178` `_rerank_and_reserve` | title+snippet only | YES (always) | keyword overlap = the exact junk vector; no body seen |
| G2 | **PRE-fetch semantic gate** (B4) | embedding-cosine ≥ floor threshold | `live_retriever.py:3441` `_relevance_threshold_select`, enabled `:3320` `_relevance_gate_enabled` (`PG_RETRIEVAL_RELEVANCE_GATE`) | title+snippet only | **default OFF** | cosine on snippet; body unseen |
| G3 | **PRE-fetch off-topic filter** | embedding-cosine ≥ 0.25 | `prefetch_offtopic_filter.py:152` `filter_search_results`, invoked `live_retriever.py:3903-3928` (`enable_prefetch_filter`) | snippet | **OFF for the MAIN corpus** (`run_honest_sweep_r3.py:6599` `enable_prefetch_filter=False`); only ON for the agentic+STORM seed lanes (`:7195,7265`) | cosine, snippet-only, and off on the primary path |
| G5 | **POST-fetch content-starvation** | length / PDF-metadata / alpha-ratio / access-denial heuristic | `live_retriever.py:2988` `is_content_starved`, called `:4506` | full body | YES (always) | **NOT a relevance check** — catches empty/binary/captcha bodies, says nothing about whether real prose answers the query |

**Corrected floor (the strengthened gap):** there is **NO post-fetch relevance filter wired on the active
path.** The `PG_OFFTOPIC_THRESHOLD=0.35` "tighter post-fetch" path described in the
`prefetch_offtopic_filter.py:8-23` *docstring* is **not invoked anywhere in `live_retriever.py`** (grep for
`PG_OFFTOPIC_THRESHOLD` / `filter_evidence` / `post.?fetch` in the active retriever returns **nothing** —
only the *pre*-fetch `filter_search_results` exists, and it is OFF for the main corpus). So once a body is
fetched, the **only** post-fetch gate is the **starvation heuristic (G5)** — which is length/format, not
relevance. **Keyword-matching-but-non-answering prose that clears the starvation floor reaches the basket
with no relevance check whatsoever.** This is a wider gap than a precision-weak cosine filter — it is the
*absence* of any answerhood check on the fetched body.

The B1 semantic scorer (`evidence_selector.py:678` `_semantic_relevance_scores`, gated by
`PG_RELEVANCE_SCORER=semantic_v2` `:614`) is the shared embedder used by G2/G3. Under `semantic_v2` the
embedder is the Qwen3-Embedding-8B pick (the strand's named "semantic option"); otherwise MiniLM
(`prefetch_offtopic_filter.py:91` `all-MiniLM-L6-v2`). The relevance floor is `PG_RELEVANCE_FLOOR=0.30`
(`evidence_selector.py:36` `_DEFAULT_RELEVANCE_FLOOR`). Note: G2/G3 score **title+snippet**, never the body.

### 1.2 CRAG is a partial-incumbent **but dead code on the active path**

`src/polaris_graph/retrieval/crag_retriever.py` implements the canonical Corrective-RAG retrieval-evaluator
pattern (GOLD/SILVER/BRONZE + CORRECT/AMBIGUOUS/INCORRECT confidence gate, `crag_retriever.py:10-11,58-64`).
**It is imported ONLY by `graph_v2.py:39` (the FROZEN pipeline-B LangGraph variant), never by
`run_honest_sweep_r3.py`** (which uses `run_live_retrieval` exclusively — verified: 0 CRAG references in
`run_honest_sweep_r3.py`, the only `CRAGRetriever().retrieve(...)` call site is `graph_v2.py:341`). So CRAG
does **not** fire on the active pipeline. And even if wired, its evaluator is **embedding-cosine
GOLD/SILVER/BRONZE** (`crag_retriever.py:560` `model.encode()` on `all-MiniLM-L6-v2`), i.e. the same
similarity-not-judgment limitation as G4 — not an LLM/cross-encoder judge.

### 1.3 The precise gap

> Nothing on the active path reads the **full fetched body** and renders a **relevance JUDGMENT** of the
> form "does this passage actually answer the research question?" The pre-fetch gates (G1 always, G2/G3
> default-OFF or seed-lane-only) score **title+snippet** only and use **similarity** (lexical overlap or
> cosine), never the body. The only **post-fetch** gate is the **starvation** heuristic (G5, length/format
> only) — there is **no post-fetch relevance filter at all.** Keyword-matching-but-non-answering prose clears
> every gate. This strand fills that empty slot.

---

## 2. Why a judge/pruner beats the cosine threshold we already have (the intellectual core)

Embedding cosine and lexical overlap measure **aboutness** (is this text in the same topic neighborhood),
not **answerhood** (does this text contain the answer to *this* question). The two diverge exactly where
junk lives:

- A semaglutide review article that mentions "cardiovascular outcomes" in its intro but reports no CV
  endpoint scores ~high cosine to a "semaglutide CV risk" question and survives G4 — yet it answers nothing.
- A drug-label page that lists the query drug + indication keywords but in a section irrelevant to the asked
  dose/contraindication is high-cosine, zero-answer.

A **cross-encoder / LLM judge** reads query and passage *jointly* and is trained/prompted to output a
relevance grade conditioned on the *question intent*, not topic proximity. That is the only mechanism that
distinguishes "about X" from "answers the question about X." Empirically this is the documented motivation
for CRAG's evaluator (arXiv 2401.15884) and Provence's sequence-labeller (arXiv 2501.16214): both replace a
similarity score with a *judgment*. This layer earns its slot precisely because it catches the failures G4
is structurally blind to.

**Independent 2026 confirmation of the aboutness→answerhood gap (Information Gain Pruning, arXiv 2601.17532,
Jan 2026):** IGP measures directly that **retrieval-relevance metrics (e.g. NDCG) correlate poorly with
downstream QA quality** — i.e. a passage's similarity rank is *not* a good proxy for whether it actually
helps answer the question. This is the strongest recent empirical support for replacing the cosine gate with
an answerhood judgment. **NB on scope (§-1.3):** IGP's own *mechanism* (a generator-aligned utility signal
that "filters weak or harmful passages **before truncation**" under a context-budget interface) is a
budget/redundancy thinner, which is exactly the cap/thinner pattern §-1.3 BANS. We adopt its *finding*
(aboutness ≠ answerhood), **not** its method — POLARIS has no context-budget truncation slot and must not
acquire one through this strand.

---

## 3. Frontier candidates (2025/2026, primary-source-verified)

Every entry verified at the primary source this session (not memory). Banned: Exa, Tavily. Required: date + URL + license.

### 3.1 Provence — sentence-level pruning + reranking (the design-to-beat blueprint)
- **What:** DeBERTa-v3-large cross-encoder that does **sequence labeling** — per-token binary mask, keeps
  relevant sentences, drops the rest — **unified with reranking** in one forward pass. A `threshold`
  param (default 0.1 conservative, 0.5 aggressive) controls pruning. Returns
  `{'reranking_score', 'pruned_context'}`.
- **Date/URL:** arXiv **2501.16214** (Jan 2025, ICLR'25), https://arxiv.org/abs/2501.16214 ;
  model `naver/provence-reranker-debertav3-v1`, https://huggingface.co/naver/provence-reranker-debertav3-v1
- **Size/base:** 430M, base `naver/trecdl22-crossencoder-debertav3`.
- **License:** **CC-BY-NC-4.0 (non-commercial).** ❌ **BANNED for commercial weights** — Telus/Carney is a
  commercial product. Use the **method** (sequence-labelling pruning unified with reranking) as the
  design-to-beat, not the weights.
- **Note vs our axis:** Provence prunes *within* a passage (sentence masks); it does not natively drop a
  whole passage as a unit. For our DROP axis we threshold on its reranking_score, or — more cleanly — adopt
  the *judge* framing (§3.2/§3.4) which natively emits a passage-level keep/drop.

### 3.2 Qwen3-Reranker — instruction-conditioned cross-encoder judge (THE DEPLOYABLE PICK)
- **What:** cross-encoder that, given a custom **instruction** + query + document, emits a **yes/no relevance
  probability** via `true_score = exp(true_logit)/(exp(true_logit)+exp(false_logit))`. Thresholding this
  probability **DROPS** a passage (documented: "documents scoring below a threshold can be excluded rather
  than merely reranked"). Custom instruction lets us phrase the criterion as *"does this passage answer the
  research question?"* (not just topical match).
- **Date/URL:** Qwen3-Embedding/Reranker series, June 2025. Blog
  https://qwenlm.github.io/blog/qwen3-embedding/ ; models
  https://huggingface.co/Qwen/Qwen3-Reranker-0.6B (also 4B, 8B); repo
  https://github.com/QwenLM/Qwen3-Embedding
- **Size:** 0.6B / 4B / 8B; 32K context (fits a full fetched body — a real advantage over snippet-only G2/G3).
- **License:** **Apache-2.0.** ✅ Sovereign, commercial-clean, self-hostable. **SAME family as our chosen
  Qwen3-Embedding-8B retrieval scorer** → one model family, one infra story, shared serving.
- **Why it beats G4:** cross-encoder joint encoding + instruction = answerhood not aboutness; runs on the
  full body, not the snippet; thresholdable to DROP.

### 3.3 CRAG retrieval-evaluator (incumbent PATTERN, not a new candidate)
- **What:** lightweight retrieval evaluator (fine-tuned T5-large) → confidence → {Correct, Incorrect,
  Ambiguous}; "if all documents fall below a lower threshold, mark incorrect and discard." The canonical
  "grade-then-drop" pattern.
- **Date/URL:** arXiv **2401.15884** (Jan 2024), https://arxiv.org/abs/2401.15884 . MIT-style research code.
- **Status in POLARIS:** already present as **dead code** (`crag_retriever.py`, pipeline-B only, §1.2). It is
  the floor's *latent* design but is cosine-based and unwired. Treat as the conceptual incumbent; the Qwen3
  judge is the modern, instruction-conditioned, body-level upgrade of this pattern.
- **Pre-2024 note:** Jan-2024 is just inside the "genuine incumbent floor" carve-out — cited as the
  pattern's origin, not as the 2026 pick.

### 3.4 GLM-5.2 LLM-as-judge with the UMBRELA prompt (maximally-sovereign alternative)
- **What:** prompt the **existing GLM-5.2 backbone** with the **UMBRELA** 0–3 graded-relevance prompt
  (open-source reproduction of Bing's relevance assessor; assesses query-intent alignment + passage
  trustworthiness). Grade < cut → drop. Zero new model to host (GLM is already the pipeline backbone).
- **Date/URL:** UMBRELA arXiv **2406.06519** (2024, validated on the **TREC-2024 RAG track**, 77 runs),
  https://arxiv.org/abs/2406.06519 ; large-scale study SIGIR/ICTIR-2025
  https://dl.acm.org/doi/10.1145/3731120.3744605
- **License:** UMBRELA prompt/code is open (Apache-style, Castorini). GLM-5.2 is the operator-locked backbone.
  ✅ Fully sovereign, nothing new to deploy.
- **Tradeoff:** highest precision/instruction-following but a full generative call per passage — too costly to
  run on every fetched body; right as an **escalation/audit lane** (ambiguous-band passages, or §-1.1 audit),
  not the always-on floor.

### 3.5 Adjacent methods seen (context, not picks)
- **MAIN-RAG** (Multi-Agent Filtering RAG, arXiv 2501.00332, Dec 2024): **training-free** multi-LLM-agent
  filter — several agents independently score each retrieved doc, then **inter-agent consensus** with an
  **adaptive threshold tuned to the score distribution** drops irrelevant docs (reports 2–11% answer-accuracy
  gain + fewer irrelevant docs). Axis = **answerhood/relevance** (the §-1.3-legal axis), so it is a genuine
  *architecture alternative* to a single cross-encoder judge: the GLM-5.2 escalation lane (§3.4 / §6 item 7) is
  effectively a 1-agent slice of this pattern, and a 2–3-agent consensus is the natural precision upgrade for
  the ambiguous band if the single judge proves under-precise on the gold set. Training-free → no new weights
  to host. https://arxiv.org/abs/2501.00332 (Dec-2024 = inside the genuine-incumbent carve-out; cited as a
  consensus-filter pattern, not a 2026 pick.)
- **XProvence** (ECIR-2026, arXiv 2601.18886, `xprovence-reranker-bgem3-v2`): multilingual zero-cost
  Provence; same NC-lineage license concern → inspiration only. https://arxiv.org/abs/2601.18886
- **Prism-Reranker** (arXiv 2604.23734, Apr 2026): Qwen3.5-based reranker (0.8B/2B/4B/9B) that goes *beyond*
  scoring — it emits a contribution statement + a denoised evidence rewrite. **License CC-BY-NC-ND-4.0
  (non-commercial, no-derivatives)** ❌ → **BANNED for commercial weights**, same disposition as Provence;
  the "rewrite to discard noise" framing is a Provence-lineage sibling, inspiration only, never a pick.
  https://arxiv.org/abs/2604.23734
- **RL-tuned rerankers** (e.g. arXiv 2604.02091, 2026, "rerankers via LLM-feedback RL"): a *training method*
  for rerankers, not a deployable filter weight for this slot — out of scope (we are not training a reranker).
- **FILCO** (lexical/statistical passage filter, STRINC/CXMI; ↓hallucination up to 64%): a *lexical* filter —
  same aboutness limitation as G1; not an upgrade over what we have. Noted for completeness.
- **Conformal-prediction context filters** (arXiv 2511.17908, 2025): statistical coverage guarantees on the
  keep-set — interesting for *calibrating the threshold* later, not the judge itself.
- **DIRAS** (arXiv 2406.14162): efficient LLM annotation of document relevance — a way to build the gold set
  (§5) cheaply, not a runtime filter.

### 3.6 Newest same-family sovereign weight checked (the "anything newer?" answer for the PICK)
- **Qwen3-VL-Reranker (2B / 8B)** — arXiv **2601.04720**, released **2026-01-08**, **Apache-2.0**, 32K
  context, https://huggingface.co/Qwen/Qwen3-VL-Reranker-8B . This **is** newer same-family sovereign
  (Apache-2.0) reranker weights than Qwen3-Reranker-0.6B — so the §7 "no newer sovereign weights" claim is
  corrected (see §7). **But it does not displace the pick:** it is **multimodal (text+image/screenshot/video)
  and ships only at 2B/8B — there is no 0.6B text variant.** For an **always-on text-passage** floor that runs
  on *every* fetched body, the multimodal capacity is dead weight and 2B/8B is 3–13× the params of the 0.6B
  text reranker. Disposition: a valid sovereign candidate for the **escalation/audit lane** (or if the corpus
  ever goes multimodal — e.g. screenshot/figure evidence), but the **0.6B text Qwen3-Reranker remains the
  always-on floor**. Verified at the HF primary page this session (license + sizes + modality).

---

## 4. The axis (how we decide the winner) + gold-set sketch

**Axis = junk precision/recall on a labeled relevant-vs-junk passage set. PRECISION IS THE HEADLINE.**
A filter that nukes useful passages is worse than no filter — so the primary metric is **precision of the
DROP decision** (of the passages we dropped, how many were truly non-answering), with recall (of the true
junk, how much we caught) secondary, and an explicit **false-drop rate on gold-useful passages** as a hard
guardrail (must be ~0 on clearly-answering passages).

Metrics, per candidate at a swept threshold:
- **Drop-precision** (headline), **drop-recall**, **F1**, **false-drop-on-useful** (guardrail), ROC-AUC of
  the score vs the gold label, latency/throughput per passage, $ per 1k passages.
- Report the **precision–recall curve over the threshold sweep**, then pick the operating point that holds
  false-drop-on-useful at/near zero (fail-open bias).

**Gold set (REAL data, LAW II — no synthetic):**
- Source: the **banked replay corpora** — `corpus_snapshot.json` fixtures used by the §-1.4 replay harness
  (`scripts/resume_from_corpus_textmode.sh`, `state/iarch007_corpus_checkpoints.json`) and the
  `outputs/audits/b1b10_redesign/replay_fixtures/`. These are real fetched bodies from real runs.
- Labeling: each `(research_question, fetched_passage)` pair labeled **ANSWERS / DOES-NOT-ANSWER** against
  the question. Bootstrap labels with the DIRAS/UMBRELA LLM-annotation approach, then **adjudicate every
  label by hand under §-1.1** (this is clinical-safety-critical — a hand-checked gold set, not an
  LLM-graded one, is the only honest ground truth for a precision claim).
- Include the documented junk archetypes as positive-junk examples: keyword-present-but-non-answering
  intro/landing prose (the G4-blind class), off-section drug-label hits, near-topic review articles with no
  endpoint. Include clearly-answering passages (RCT results sections, label dose tables) as gold-useful.
- Target size: ~300–500 labeled pairs spanning the clinical domains in the banked corpora (enough for a
  stable PR curve; expandable).

---

## 5. Where it slots in the pipeline

```
search → G1/G2/G3 pre-fetch (title+snippet relevance)
       → fetch + clean_fetch_body (boilerplate already stripped — NOT in scope)
       → extraction (statement + direct_quote)
       → is_content_starved  [G5: empty/format/captcha drop — the ONLY post-fetch gate today]  ← keep, orthogonal
       ┌─────────────────────────────────────────────────────────────┐
       │ NEW: passage_relevance_judge  (this strand — fills the       │  ← the DROP-junk layer
       │      currently-EMPTY post-fetch relevance slot)              │
       │  Qwen3-Reranker-0.6B judge-mode, instruction =                │
       │  "does this passage answer the research question?",           │
       │  max-over {question ∪ sub-queries}, score∈[0,1],              │
       │  drop if < PG_PASSAGE_RELEVANCE_FLOOR (fail-open),            │
       │  every drop → relevance-drop ledger (mirror :627)             │
       └─────────────────────────────────────────────────────────────┘
       → baskets / consolidation → strict_verify / 4-role D8 (FAITHFULNESS — untouched)
       → render
```

It sits **after** extraction, in the **currently-empty post-fetch relevance slot** (today only G5 runs there,
and G5 is starvation, not relevance). It is **upstream of** consolidation and **entirely upstream of** the
faithfulness engine — so faithfulness is never relaxed: this layer only changes which passages reach the
basket, exactly like the existing pre-fetch topical relevance gate, but now on the full body.

---

## 6. Provisional design — `passage_relevance_judge` (concrete, §-1.3-safe)

**This is a DESIGN strand element — concrete proposal, not just a survey.**

1. **Model:** `Qwen/Qwen3-Reranker-0.6B` (Apache-2.0), judge-mode. Reuse the Qwen3-family serving already
   stood up for the Qwen3-Embedding-8B retrieval scorer (one family, one infra). 0.6B is fast enough to run
   on **every** fetched passage; 4B is the escalation if 0.6B precision is short.
2. **Instruction (the answerhood criterion, not aboutness):**
   `"Given the research question, judge whether THIS passage contains information that helps ANSWER the
   question. Answer yes only if the passage states a fact, result, or claim responsive to the question;
   answer no if it merely mentions the topic without answering."`
3. **Anchor:** score **max over {research_question} ∪ {sub-queries}** (mirrors `_semantic_relevance_scores`
   `evidence_selector.py:690` so a passage answering one focused facet is not diluted).
4. **Decision:** drop iff `score < PG_PASSAGE_RELEVANCE_FLOOR` (env-driven, LAW VI; default conservative,
   bias to KEEP). **This is the ONE §-1.3-legal axis: topical does-this-answer relevance. It is NOT a count
   cap, NOT a quality percentile, NOT a breadth target, NOT a credibility/tier drop.** No "drop the bottom
   N%" — every drop is an absolute below-floor non-answering verdict.

   **Why this does NOT collide with consolidate-keep-all (§-1.3), stated explicitly (the seam a Codex
   auditor will poke):** §-1.3's carve-out is *off-topic is useless at any weight*; this layer's axis is the
   slightly wider *non-answering* (on-topic-but-mentions-only). The reconciliation is that a **non-answering
   passage carries no claim that can contribute to any basket** — consolidate-keep-all keeps all *corroborating
   sources of a claim*, and a passage that states no fact/result/claim responsive to the question is not a
   corroborator of anything, so keep-all simply does not apply to it. It is exactly the class the operator
   named ("keyword-matching crap pollutes findings"). A passage that DOES state a responsive fact — even a
   weak or low-credibility one — scores as answering and is KEPT (then weighted/consolidated/labelled
   downstream, never dropped here). The judge drops *noise*, never a low-weight *corroborator*.
5. **Fail-open (LAW II):** model unavailable / load failure / scoring exception → **keep all**, log LOUDLY,
   fall back to G4's cosine (never a silent drop-all). Kill-switch `PG_PASSAGE_RELEVANCE_JUDGE` default OFF
   so the legacy path is byte-identical until proven on the gold set.
6. **Telemetry (mirror the existing relevance-drop ledger, `evidence_selector.py:627`
   `_relevance_drop_ledger_enabled`):** every drop records `url`, score, instruction, the winning anchor —
   so the operator can §-1.1 audit exactly what was dropped and why. The recall cost (kept-vs-dropped band)
   is MEASURABLE, never dropped-and-forgotten (same discipline as `RelevanceGateResult`).
7. **Escalation lane (optional):** passages in an ambiguous band `[floor, floor+δ]` → re-judged by the
   GLM-5.2 UMBRELA judge (§3.4) for a higher-precision second opinion before dropping. Keeps the expensive
   generative judge off the hot path while protecting precision on the hard cases.
8. **Behavioral acceptance (§-1.4):** a fail-loud replay test on a banked `corpus_snapshot.json` asserting
   (a) a known keyword-junk passage IS dropped, (b) a known answering passage is NOT dropped, (c) on
   model-unavailable the run keeps-all and logs the fallback. "Green tests + Codex-approve ≠ fired" — the
   harness proves the drop actually happens in the real output.

### 6.1 Explicit scope boundary — what this layer is NOT (the seams a 2026 deep-research system also covers)

This judge filters on **one** axis — *answerhood* — and a §-1.1 reader must not mistake it for the other
post-fetch screens a frontier deep-research system runs. Three are out of scope *by design* and are named
here so the boundary is honest (each is a separate strand, not a relaxation of this one):

- **Adversarial / poisoned content is NOT screened by this layer (the headline unknown-unknown).** A
  relevance/answerhood judge **passes on-topic poison by construction** — crafted text appended to a
  frequently-retrieved page is *highly* answering and scores high, exactly the way injected instructions or
  fabricated "facts" are engineered to (documented for deep-research agents: **arXiv 2605.24245**, *"Deep-
  Research Agents Can Be Poisoned via User-Generated Content,"* May 2026, which finds source-level + relevance
  + output filtering each fail to mitigate without degrading quality). **Existing POLARIS coverage:** (a)
  invariant-7 **delimiter sanitization** neutralizes `<<<evidence:…>>>`-style injection at prompt-wrap time
  (`provenance_generator.py`, `evidence_distiller.py`, `multi_section_generator.py`, et al.); (b) the **tier
  classifier weight-demotes UGC** (reddit/facebook/aol → never T1, `tier_classifier.py:295-302,1267,1360-1370`)
  — a §-1.3 *weight*, not a drop. **Residual gap:** neither screens the *semantic content* of an on-topic
  adversarial passage, and a high answerhood score will actively *promote* it past this judge. → a dedicated
  **content-poisoning / injection-content screen** is a distinct strand; this relevance layer must be
  scope-labelled "NOT an adversarial-content defense" so no one treats it as one.
- **Temporal/vintage relevance is NOT screened here.** A superseded clinical guideline is "answering but
  wrong-vintage"; this judge scores it as answering and keeps it (correctly — recency is a *weight*/disclosure
  concern handled downstream, not an answerhood drop). Named so a reader does not expect staleness filtering
  from this slot.
- **Set-level redundancy / cross-passage conflict is NOT screened here, on purpose.** Each passage is judged
  **independently** against the question; de-duplication and corroboration across passages are
  **consolidation's** job (§-1.3 consolidate-keep-all), never a per-passage drop. This is the explicit line
  against the IGP-style "prune redundant passages before truncation" pattern (§2 NB) that §-1.3 bans.

---

## 7. Honest recommendation + OSS-vs-banned

**Pick (deployable, sovereign, commercial-clean): `Qwen3-Reranker-0.6B` in judge-mode** as the always-on
post-extraction junk-drop, with the **GLM-5.2 UMBRELA judge** as the ambiguous-band escalation/audit lane.
Rationale:
- **Apache-2.0 + self-hostable + same family as the Qwen3-Embedding-8B retrieval scorer** → zero new
  sovereignty/licensing risk, one serving stack.
- **Cross-encoder + instruction = answerhood, not aboutness** → closes the precise G4/G5 gap with the junk
  class the operator named.
- **Precision-first + fail-open + telemetry'd + faithfulness-untouched** → passes our own §-1.1/§-1.3 bar
  (topical does-this-answer is the single legal filter axis; nothing here is a cap/floor-as-target/percentile).

**Design-to-beat:** Provence's unified prune+rerank quality is the bar to clear on the gold set — but its
**CC-BY-NC-4.0 license bars the weights commercially**, so we beat it with Apache-2.0 Qwen3 + the
UMBRELA-judge framing, not by shipping Provence.

**OSS-vs-banned honesty:**
- ✅ Sovereign/OSS: Qwen3-Reranker (Apache-2.0), GLM-5.2 (operator-locked backbone), UMBRELA prompt (open),
  CRAG pattern (open research), MiniLM/Qwen3-Embedding (already in tree).
- ❌ Non-commercial (inspiration only, not weights): Provence (CC-BY-NC-4.0), XProvence (NC lineage).
- ❌ BANNED (Telus competitors, never recommend): **Exa, Tavily.** Neither appears in this design.
- 🔌 Plumbing only (allowed, not AI modules): Serper (search API), Zyte (paywall/Cloudflare bypass).

**Recency check ("anything newer?"):** swept 2026.
- **Newer same-family sovereign weights DO exist** — **Qwen3-VL-Reranker 2B/8B** (Apache-2.0, 2026-01-08,
  §3.6) is newer than Qwen3-Reranker-0.6B. It does **not** supersede the pick for this slot because it is
  multimodal + 2B/8B-only (no 0.6B text variant) → overkill for an always-on **text** floor; it is a valid
  candidate for the escalation lane or a future multimodal corpus. So the precise honest claim is: *no newer
  sovereign weight is a better fit than the 0.6B text reranker for the always-on text-passage floor* — not the
  blanket "nothing newer exists."
- **Newer pruning models are NC-lineage** — XProvence (ECIR-2026) and **Prism-Reranker** (arXiv 2604.23734,
  Apr 2026, Qwen3.5-based, **CC-BY-NC-ND-4.0**) are both barred for commercial weights.
- **Newer methods refine, not replace, the primitive** — IGP (arXiv 2601.17532, Jan 2026; §2/§3.5) and the
  2026 RAG-filtering literature (surveys arXiv 2506.00054, noise-filtering arXiv 2601.01896, dynamic context
  selection arXiv 2512.14313, conformal filters arXiv 2511.17908, TREC-2025 RAG track arXiv 2603.09891) refine
  *thresholding / generator-alignment / calibration* over the **same cross-encoder / LLM-judge primitives**
  picked here; IGP's generator-utility-before-truncation mechanism is §-1.3-banned (finding adopted, method
  not). Conformal calibration is a future threshold-tuning follow-up, not a different judge.

**Net:** the always-on **Qwen3-Reranker-0.6B text judge** remains the right pick as of 2026-06-24; the only
correction is that *newer sovereign reranker weights exist (Qwen3-VL)* but are a worse fit for this specific
always-on-text slot.

---

## 8. Sources (primary, verified this session)
- Provence — arXiv 2501.16214 (Jan 2025); HF `naver/provence-reranker-debertav3-v1` (CC-BY-NC-4.0).
- XProvence — arXiv 2601.18886 (ECIR-2026); HF `xprovence-reranker-bgem3-v2`.
- Qwen3-Reranker — qwenlm.github.io/blog/qwen3-embedding/ ; HF `Qwen/Qwen3-Reranker-0.6B|4B|8B` (Apache-2.0);
  GitHub QwenLM/Qwen3-Embedding.
- Qwen3-VL-Reranker (newest same-family, §3.6) — arXiv 2601.04720 (2026-01-08); HF
  `Qwen/Qwen3-VL-Reranker-8B` (also 2B; Apache-2.0; multimodal, 32K, no 0.6B text variant).
- Prism-Reranker — arXiv 2604.23734 (Apr 2026); Qwen3.5-based 0.8/2/4/9B; **CC-BY-NC-ND-4.0** (NC, no-derivs).
- IGP (Information Gain Pruning) — arXiv 2601.17532 (Jan 2026); finding adopted (aboutness≠QA-quality),
  generator-utility-before-truncation method NOT adopted (§-1.3-banned thinner).
- MAIN-RAG (multi-agent consensus filter, training-free) — arXiv 2501.00332 (Dec 2024).
- Deep-Research poisoning (adversarial UGC, §6.1 unknown-unknown) — arXiv 2605.24245 (May 2026).
- CRAG — arXiv 2401.15884 (Jan 2024).
- UMBRELA — arXiv 2406.06519 (2024); SIGIR/ICTIR-2025 large-scale study dl.acm.org/doi/10.1145/3731120.3744605.
- FILCO / conformal / DIRAS / 2026 surveys + noise-filtering + dynamic-context-selection / RL-reranker —
  arXiv 2506.00054, 2511.17908, 2406.14162, 2603.09891, 2601.01896, 2512.14313, 2604.02091 (context).
- POLARIS floor — `src/polaris_graph/retrieval/live_retriever.py` (`is_content_starved:2988`,
  `_lexical_relevance_score:3114`, `_rerank_and_reserve:3178`, `_relevance_gate_enabled:3320`,
  `_relevance_threshold_select:3441`); `evidence_selector.py` (`_DEFAULT_RELEVANCE_FLOOR:36`,
  `_semantic_relevance_scores:678`, `_relevance_scorer_mode:614`, `_relevance_drop_ledger_enabled:627`);
  `prefetch_offtopic_filter.py` (`filter_search_results:152`, MiniLM:91, PG_OFFTOPIC_THRESHOLD:21);
  `crag_retriever.py` (dead-code, imported only by `graph_v2.py:39`); invariant-7 delimiter sanitization
  (`provenance_generator.py`, `evidence_distiller.py`, `multi_section_generator.py`); UGC tier-demotion
  (`tier_classifier.py:295-302,1267,1360-1370`).

---

## 9. Completeness note (independent critic pass, 2026-06-24)

An independent completeness + unknown-unknowns critic re-swept this strand against the 2025/2026 OSS frontier
(adversarial fresh-search, primary-source-verified, §-1.1/LAW-II). **Verdict: the original pick and design
hold; six additions + one corrected crown + three scope-boundary unknown-unknowns were patched in.**

**Additions (verified at primary source this session):**
- **Qwen3-VL-Reranker 2B/8B** (Apache-2.0, 2026-01-08, arXiv 2601.04720) — §3.6. The newest *same-family
  sovereign* reranker; corrects the §7 "no newer sovereign weights" overclaim. Not the pick (multimodal,
  2B/8B-only, no 0.6B text variant → overkill for an always-on text floor); valid escalation/multimodal-future
  candidate.
- **IGP / Information Gain Pruning** (arXiv 2601.17532, Jan 2026) — §2 + §3.5. Empirical *finding* adopted
  (retrieval-relevance correlates poorly with QA quality = independent support for answerhood over aboutness);
  its generator-utility-**before-truncation** *method* explicitly flagged as the §-1.3-banned cap/thinner
  pattern and NOT adopted.
- **MAIN-RAG** (arXiv 2501.00332, Dec 2024) — §3.5. Training-free multi-agent consensus filter on the legal
  answerhood axis; the natural precision upgrade for the §6 item-7 escalation lane (multi-agent vote vs single
  judge).
- **Prism-Reranker** (arXiv 2604.23734, Apr 2026) — §3.5. CC-BY-NC-ND → BANNED commercial weights; Provence-
  lineage inspiration only.
- **RL-tuned rerankers** (arXiv 2604.02091) — §3.5. Training method, out of scope (we don't train a reranker).
- 2026 context literature (noise-filtering 2601.01896, dynamic-context-selection 2512.14313) folded into §7.

**Unknown-unknowns surfaced (§6.1 — things a 2026 deep-research system screens that the original doc never
asked about):**
1. **Adversarial / poisoned on-topic content (headline).** A relevance/answerhood judge *passes on-topic
   poison by construction* (arXiv 2605.24245). Existing POLARIS coverage = invariant-7 delimiter sanitization
   + UGC tier-demotion (verified in code); residual gap = no *semantic* screen of on-topic adversarial prose,
   and a high answerhood score actively promotes it. → scope-labelled "NOT an adversarial-content defense;
   separate strand," not redesigned here.
2. **Temporal / vintage relevance** (superseded guideline = answering-but-wrong-vintage) — out of scope for an
   answerhood judge; named as a downstream weight/disclosure concern.
3. **Set-level redundancy / cross-passage conflict** — out of scope by design; that is consolidation's job
   (§-1.3 consolidate-keep-all), explicitly the line against IGP-style redundancy pruning.

**Rejected / logged (LAW II):** Exa, Tavily (banned, absent); Provence/XProvence/Prism-Reranker weights
(NC/ND license → commercial-barred, inspiration only); IGP method (§-1.3-banned truncation thinner — finding
kept, method rejected). No pre-2024, non-OSS, or unverifiable entry was promoted to a pick. "Anything newer?"
answer: newer sovereign reranker weights exist (Qwen3-VL) but are a worse fit for the always-on text slot —
**Qwen3-Reranker-0.6B text judge remains the right pick as of 2026-06-24.**
