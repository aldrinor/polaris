# Search Orchestration Landscape 2026 — turning queries into candidate URLs

**Scope:** the SEARCH-ORCHESTRATION layer of the POLARIS sovereign clinical
pipeline — the stage that turns a research question into candidate URLs. Three
problems: (1) kill Exa/Tavily (Telus-competitor AI-search) and replace their
role with sovereign self-hosted OSS meta-search; (2) a concrete QUERY→ENGINE
routing design across ~8 engines; (3) direct sovereign querying of clinical
registries (ClinicalTrials.gov, openFDA, EMA, NICE) instead of relying on paid
web to surface them.

**Axis:** source/URL recall + routing accuracy + clinical-source coverage.

**Frontier-tech mandate:** every external candidate carries a year + primary-source
URL + license; pre-2024 tech appears only as a genuine incumbent floor (called
out explicitly). Sovereignty: the AI/analysis layer must be OSS + self-hostable.
Serper (raw search API) + Zyte (paywall/Cloudflare bypass) are ALLOWED as
plumbing. **Exa + Tavily are BANNED** (competitor AI-search). This doc is a
landscape + design; **no e2e, no run-spend.**

---

## 0. Honest framing up front (read this first)

Two honesty points that govern the whole doc:

1. **Exa ≠ SearXNG. They are different capability classes — this is NOT a 1:1 swap.**
   Exa is a *neural / embedding* search engine (it has its own semantic index
   and neural ranker). SearXNG is a *metasearch aggregator*: it has **no index
   of its own** and **no neural ranking** — it fans a query out to existing
   engines (Google, Bing, DuckDuckGo, Brave, plus science engines like PubMed,
   arXiv, Semantic Scholar, CrossRef) and merges their results. So removing Exa
   **loses** the neural-semantic web-retrieval capability; SearXNG **adds**
   sovereign multi-engine breadth, not neural recall. The sovereign replacement
   for the *semantic* capability is the in-house embedding retriever
   (Qwen3-Embedding-8B over the fetched corpus, I-arch-009 #1266) re-ranking
   candidates after fetch — not SearXNG. The doc keeps these two roles distinct.

2. **An evidence-need router already exists in POLARIS.** The planner emits a
   field-agnostic `evidence_needs` list, and `need_type_router.py` +
   `source_adapter_registry.py` already map each need → a set of discovery
   adapters (data-driven, no `if domain ==` on the live path). The routing
   proposal in §2 is an **extension** of that existing machinery (surgical, per
   the WEIGHT-AND-CONSOLIDATE DNA / §-1.3), **not** a greenfield router. Claiming
   a brand-new router would be both dishonest and a violation of surgical-not-
   rewrite.

---

## 1. Current floor (grep + read, with file:line)

### 1.1 Two retrieval entrypoints — both reachable

There are **two** parallel search-orchestration paths in the tree, and the Exa
removal + routing redesign must account for both:

| Path | Entry | Callers | Contains Exa? | Routing today |
|---|---|---|---|---|
| **A — agentic / STORM searcher** | `src/polaris_graph/agents/searcher.py::execute_searches` (line 274) | `graph.py:128`, `graph_v2.py:180`, `graph_v3.py:198` | **YES** (Exa is wired here) | static fan-out: Serper web + OpenAlex/S2 academic + Exa, all queries to all engines |
| **B — live_retriever (the rebuild path)** | `src/polaris_graph/retrieval/live_retriever.py` (calls `run_need_type_backends` at line 3832-3834) | the honest-rebuild live clinical path (docstring line 16: *"the live alternative to the pre-rebuild searcher.py path"*) | no Exa | **need-type routed**: `need_type_router.route_needs_to_adapters(frame)` → `source_adapter_registry` |

The clinical sweep runs through path B's need-type router, which already has the
right shape for the §2 routing design. Path A still carries Exa and the
all-engines-fan-out, so the Exa kill (§1.3 below) and any routing improvements
must be applied to BOTH or path A silently keeps the banned tool.

### 1.2 Engines/backends in the floor

**Path A — `searcher.py`:**
- `_run_web_searches` (line 438) — Serper web via `src/agents/search_agent.py::web_search`.
- `_run_academic_searches` (line 654) — OpenAlex primary (`_search_openalex`, line 166) + Semantic Scholar parallel.
- `_run_serper_scholar` (line 913) — Google Scholar via Serper.
- `_run_exa_searches` (line 957) — **Exa neural search. BANNED — to remove.**
- `_run_ddg_fallback_for_zeros` (line 797) — DuckDuckGo zero-result fallback.
- `_adaptive_web_search` (line 1289) / agentic loop (`execute_agentic_search`) — LLM-refined multi-round; agentic loop fires Exa at lines 1698/1759 via `analysis.exa_queries[:PG_AGENTIC_EXA_PER_ROUND]`.

**Path B — `domain_backends.py` (need-keyed adapters):**
- `arxiv_search` (line 127) — arXiv Atom API, keyless.
- `policy_targeted_serper` (line 164) / `site_scoped_serper` (line 218) — `site:`-scoped Serper from `jurisdiction_scopes.yaml`.
- `sec_edgar_search` (line 286) — SEC EDGAR full-text, keyless.
- `github_search_repos` (line 351) — GitHub repo search, keyless.
- `europe_pmc_search` (line 404) — Europe PMC primary literature, **keyless/free** (the one clinical-primary backend that already exists).
- `openalex_search` (line 509) — OpenAlex `/works` keyword discovery, keyless.

**Router/registry (path B):**
- `need_type_router.py::route_needs_to_adapters` (line 53) — validates `evidence_needs` + jurisdiction shape, returns the deduped adapter union; empty needs → safe `{primary_literature, open_web}` fallback (line 32).
- `source_adapter_registry.py::SourceAdapterRegistry.adapters_for_need` (line 266) — the per-need→adapter map (hardcoded `if need ==` branches, lines 277-319).
- `EVIDENCE_NEEDS` enum (`research_planner.py:97`): `primary_literature, regulatory, legal, statistical, standards, datasets, news_press, company_filings, code, open_web` (10 needs).
- `config/discovery/jurisdiction_scopes.yaml` (`VERSION: jurisdiction_scopes_v1`) — the `site:` host data; today carries `fda.gov` (line 55), `nice.org.uk` (line 105), `ema.europa.eu` (line 125) as *web hosts to `site:`-scope a Serper query*, **NOT** as direct API adapters.

### 1.3 Exa removal — the precise blast radius

Exa appears in **130 lines** of `searcher.py` plus call sites elsewhere. The
banned-tool removal is mechanical but must be complete:

- `searcher.py`: delete `_run_exa_searches` (957), `_exa_check_budget` (895), `reset_exa_budget` (101), the `_exa_session_*` module globals (97-98), the `exa_task` in the parallel gather (line 362), and the agentic-loop Exa block (1698/1759, `analysis.exa_queries`). Remove `_run_serper_scholar` only if it is Exa-coupled (it is independent — it stays; it is Serper plumbing).
- `graph.py:1414-1415`: delete the `reset_exa_budget()` call.
- `state.py:184-204`: delete the `PG_EXA_*` config block (~20 vars) and `PG_AGENTIC_EXA_PER_ROUND` (line 230). Drop `EXA_API_KEY` from `.env`/deploy.
- **Honest OSS-vs-banned:** Exa's role was (a) neural-semantic web recall and (b) a `research paper` category filter. (a) is replaced by SearXNG breadth + the in-house Qwen3 embedding re-rank (sovereign); (b) is replaced by SearXNG's `categories=science` engines (PubMed/arXiv/CrossRef/S2). **Tavily** is not currently wired in `searcher.py`/`domain_backends.py` (grep-clean) — it stays banned and must never be added.

---

## 2. DESIGN PROBLEM #1 — QUERY → ENGINE ROUTING

This is the core design strand. The task: with ~8 engines (arXiv, OpenAlex, S2,
PubMed, Europe PMC, CORE, SEC EDGAR, GitHub + SearXNG + the new clinical
registries), decide WHICH query hits WHICH engine(s). Today path A fans every
query to every web/academic engine (wasteful + noisy); path B routes by
`evidence_needs` but with hardcoded `if need ==` branches and no learned/LLM
signal at the *query* granularity.

### 2.1 What the 2025/2026 literature says (primary sources)

| Method | Year | Primary source | License | What it contributes |
|---|---|---|---|---|
| **RAGRouter** (query routing for RAG) | 2025-05 | arXiv 2505.23052 (title verbatim: *"RAGRouter: Learning to Route Queries to Multiple Retrieval-Augmented Language Models"*) | code public | Learned router using document + RAG-capability embeddings with contrastive learning; routes a query to the retrieval-augmented **LLM** most likely to answer it (+3.61% over best individual LLM); score-threshold knob for latency. **The "design to beat" for a learned recall optimizer** — note it routes to RAG-augmented *models*, so transferring it to *engine* selection is the adaptation we name, not a drop-in. |
| **DeepRetrieval** | 2025-02 (rev 2025-04) | arXiv 2503.00223 · github.com/pat-jj/DeepRetrieval | CC BY 4.0 | RL (PPO/GRPO) policy that generates queries rewarded directly on recall/relevance against **real** search engines — a 3B model beat GPT-4o/Claude-3.5 on 11/13 datasets. **Clinical-relevant headline:** 63.18% recall on *trial search* (vs 32.11% prior) + 65.07% on *publication search* (vs 24.68%) — the exact RL recipe to learn per-engine query rewriting for CT.gov/PubMed. |
| **RouteLLM** | 2024-06 | arXiv 2406.18665 · github.com/lm-sys/RouteLLM | Apache-2.0 | BERT-scale preference-trained router; the proven "cheap classifier routes to the right backend" pattern (built for model routing; the mechanism transfers to *engine* routing). Incumbent-floor-adjacent (2024) but actively used. |
| **Search-R1 / agentic-RL-search family** | 2025-02→03 (Search-R1 open-sourced 2025-02) | arXiv 2503.09516 · github.com/PeterGriffinJin/Search-R1 | Apache-2.0 | RL framework (built on veRL, extends DeepSeek-R1) that trains an LLM to **interleave reasoning with live search-engine calls** — the agentic-loop analogue to path-A's `execute_agentic_search`. Sibling 2025 work (ZeroSearch, R1-Searcher, DeepResearcher) confirms the consensus that **live-web-trained** agents beat static/simulated ones — relevant if POLARIS ever RL-trains its agentic search loop. Pattern-inspiration on our own GLM-5.2 slate (frontier mandate); not a runtime adoption. |
| **SAGE** (retrieval benchmark for deep-research agents) | 2026-02 | arXiv 2602.05975 | benchmark | 1,200 queries / 4 scientific domains / 200K-paper corpus; finding: *all six tested deep-research agents struggle with reasoning-intensive retrieval* — informs the §2.5 gold-set design and sets the frontier bar. |

Honest read: there is **no off-the-shelf OSS engine-router** we can drop in. The
literature gives (a) the *learned-router pattern* (RAGRouter/RouteLLM — both route
to *models/RAG-paths*, not to engines, so adaptation is required), (b) the *RL
query-rewriting pattern* (DeepRetrieval — proven on trial/publication search), and
(c) the *agentic-RL-search pattern* (Search-R1 family — interleaves reasoning with
live search calls). All three need training data / RL infra we do not yet have.
So the **provisional pick is a 2-tier deterministic + sovereign-LLM router now**,
with the learned recall-optimizer as the named design-to-beat once the gold set
exists. **Is anything newer (2026)?** No off-the-shelf sovereign OSS *engine*-router
has appeared; the 2026 movement is on benchmarks (SAGE) and richer agentic-RL-search
loops, not a drop-in router — re-check before build.

### 2.2 Proposed routing design (concrete — extends the existing registry)

**Tier 1 — deterministic query-type → engine map (the backbone, clinical-first).**
A static table the router consults first. It is *additive* to the existing
`evidence_needs` routing: the planner's `evidence_needs` stay the coarse signal;
this table adds **query-granularity engine selection** and the new clinical
adapters. Plug-in point: `source_adapter_registry.adapters_for_need` (the same
`if need ==` site, extended), so the change is surgical.

| Query class (detected) | Primary engines (fire always) | Secondary (fire on thin recall) | Rationale |
|---|---|---|---|
| Clinical intervention / drug / trial | **ClinicalTrials.gov v2, EU CTIS, Health Canada CTD, openFDA, Europe PMC, PubMed-via-SearXNG** | OpenAlex, S2, EMA, NICE, Health Canada DPD | registries are the gold source; web is corroboration (CT.gov + CTIS + HC CTD jointly cover US+EU+CA trials) |
| Drug regulatory / label / safety | **openFDA, DailyMed, EMA ePI, Health Canada DPD, NICE syndication** | Serper `site:` (fda.gov/ema.europa.eu/nice.org.uk/cda-amc.ca), SearXNG | primary regulatory docs first; US+EU+UK+CA jurisdictions covered directly |
| Systematic-review / guideline synthesis | **Europe PMC, PubMed, OpenAlex, NICE (UK), CDA-AMC `site:` (CA)** | SearXNG science, Serper scholar | guideline/HTA bodies named per jurisdiction (NICE=UK, CDA-AMC=CA); Cochrane is access-gated (§3) → reach CENTRAL-class trials via Europe PMC/PubMed |
| Mechanism / preprint / methods | **arXiv, medRxiv/bioRxiv, OpenAlex, S2** | SearXNG science | preprint-heavy; medRxiv is the clinical-preprint venue (date-scan feed, §3) |
| Company / market / due-diligence | **SEC EDGAR**, Serper `site:` issuer | SearXNG general | filings of record |
| Code / tooling | **GitHub** | SearXNG IT | — |
| General / news / open-web | **SearXNG (general+news)** | Serper (paid Google), Zyte for blocked | sovereign default; Serper is the *paid fallback*, not the default |

**Engine-of-last-resort + plumbing precedence (sovereignty ordering):**
`SearXNG (sovereign, self-hosted, default)` → `Serper (paid Google, fallback when
SearXNG recall is thin)` → `Zyte (paywall/Cloudflare unblock on a chosen URL)`.
This makes SearXNG the sovereign default and demotes the paid raw-search API to a
recall backstop — the honest sovereign posture.

**Tier 2 — sovereign LLM query classifier (the router, zero training data).**
A single structured call on the **in-house GLM-5.2 backbone** (sovereign; the same
model the pipeline already runs) classifies each sub-query into {query class,
evidence_needs, jurisdictions, must-hit-registry?} and emits a confidence. This
is exactly the `evidence_needs` the planner already produces — so Tier 2 is a
*finer-grained, per-sub-query* version of the existing planner frame, reusing
`validate_evidence_needs` / `validate_jurisdiction_shapes`. On low confidence,
fall back to Tier 1's deterministic map (fail-safe, never empty). No new model,
no training, fully sovereign.

**Tier 3 — learned recall-optimizer (the design to beat, future).** Once the §2.5
gold set is labeled, train a RAGRouter/RouteLLM-style BERT-scale classifier (or a
DeepRetrieval-style query-rewriter) on `(query → engines that actually returned
the must-find URL)`. This replaces Tier 2's heuristic confidence with a
recall-calibrated score. It is *named now, built later* — Tier 1+2 ship first and
are the baseline the learned router must beat on source recall.

**Cross-ref (adequacy / when-to-stop loop):** retrieval adequacy — deciding when
enough sources have been gathered to stop searching — is a sibling section's
concern, not this orchestration layer's. The only hook here is that the Tier-2
GLM-5.2 classifier emits a per-sub-query confidence + the router records
per-engine recall, both of which feed the adequacy loop's stop decision; the loop
itself is out of scope for this doc.

### 2.3 Why this design fits the DNA

- **WEIGHT-AND-CONSOLIDATE, not filter-and-cap (§-1.3):** routing changes *which
  engines fire*, never drops a returned source. Every candidate still flows
  through the unchanged tier classifier (weight) + `finding_dedup` (consolidate)
  + faithfulness engine (the only hard gate). The router widens recall; it never
  caps breadth.
- **Surgical, not rewrite (§-1.3):** Tier 1 extends `adapters_for_need`; Tier 2
  reuses the planner's validated frame; new engines are `SearchCandidate`-
  returning adapters registered in `SourceAdapterRegistry`. No engine class is
  rewritten, the faithfulness engine is untouched.
- **Fail-loud / fail-open per the existing contract:** new adapters fail-open
  (return `[]` + log) like every backend in `domain_backends.py`; a malformed
  frame still raises `MalformedPlanError` up front.

### 2.4 The unowned hop: cross-engine candidate fusion (UNKNOWN-UNKNOWN, surfaced 2026-06-24)

The doc above decides *which* engines fire; §0 notes SearXNG itself "merges" its
upstreams. But once POLARIS fans a query across **SearXNG + the direct registry
adapters (§3) + Serper + academic backends**, *something* must merge those
parallel candidate-URL lists into one ranked, de-duplicated set **before fetch** —
and the doc never says what. This is a genuine in-scope gap (it is candidate-URL
**fusion**, distinct from the fetched-corpus reranking owned by
`retrieval_landscape_2026.md` and from claim-level `fact_dedup` owned by
`consolidation_landscape_2026.md` — the retrieval doc itself flags that URL
near-dup is *not* `fact_dedup`, i.e. unowned). Today path A's parallel `gather`
just concatenates; there is no cross-engine rank-aggregation or URL-canonical dedup.

**2025/2026 primary sources for the fusion method (frontier crown is a 2025 weighted/learned method, NOT 2009 RRF):**

| Method | Year | Primary source | License | Contribution |
|---|---|---|---|---|
| **Weighted Reciprocal Rank Fusion (WRRF)** *(the PICK — 2025 frontier crown)* | **2025-03 (SIGIR 2025)** | arXiv 2503.20698 (MMMORRF, Samuel et al., Stanford/JHU/Georgetown) · github.com/hltcoe/video-retrieval-demo | OSS (public code) | The 2025 **weighted** generalization of RRF: `WRRF(m) = Σ_i w_i / (k + r_i(m))` — each list `i` carries a **weight `w_i`** so a more-trusted ranking counts more, instead of RRF's "all lists equal." **Honest scope of the primary source:** MMMORRF formalizes WRRF for *video* retrieval, where the weight is a per-document modality-trust prior `α_d` (computed offline from how news-like a video is) fusing the OCR/ASR/visual streams of one corpus — it proves WRRF beats flat RRF *there*, not on heterogeneous search engines. **The adaptation we name (not a drop-in, exactly like the RAGRouter row):** carry WRRF's formula across to *cross-engine* fusion by setting `w_i` = the **per-engine tier/authority weight** POLARIS already computes (§-1.3 WEIGHT-AND-CONSOLIDATE) — a credible registry/gov engine's ranking then counts more than general web, with zero training data. This is the DNA-correct pick: WRRF wires the existing credibility weight into the merge. Still rank-only (operates on candidate-URL ranks **pre-fetch**, no document text), so it stays the correct hop (not the fetched-corpus reranker owned by `retrieval_landscape_2026.md`). |
| **Exp4Fuse** *(2025 LLM-driven fusion variant)* | **2025-06 (ACL 2025 Findings)** | arXiv 2506.04760 (Liu & Zhang) · github.com/liuliuyuan6/Exp4Fuse | CC BY 4.0 | The **LLM-augmented** 2025 fusion route: fans the same retriever across the *original* query and an *LLM-expanded* query, producing two ranked lists, then fuses them with a **modified RRF** — SOTA on MS MARCO + 7 low-resource sets. Relevant to POLARIS because the §2 Tier-2 GLM-5.2 classifier already produces query variants; Exp4Fuse is the recipe for fusing the multi-variant ranked lists with an LLM signal (vs WRRF's source-weighted merge of multi-*engine* lists). Named as a second frontier option once gold-set tuning exists. |
| **Reciprocal Rank Fusion (RRF)** *(2009 — INCUMBENT BASELINE / FLOOR, not the crown)* | 2009 | Cormack et al., SIGIR 2009 · widely re-implemented (Azure AI Search, Elastic, Weaviate all ship it 2024-2026) | algorithm, public | The parameter-light, label-free **floor** for merging ranked lists from heterogeneous engines whose scores are not comparable. Still the deployed zero-shot default across every major 2026 search stack (e.g. TREC iKAT 2025: RRF lifted nDCG@10 0.4218→0.4425), so it is the honest **baseline POLARIS ships behind the WRRF weight wiring** — RRF is the `w_i ≡ 1` special case of WRRF. **Demoted from "the pick" to incumbent floor** per the frontier-tech mandate: a 2009 algorithm is not a frontier crown; it is the deterministic safety net the weighted/learned methods must beat. |

**Recommendation (DNA-aligned) — the HOW of the merge, step by step:** insert a single
deterministic **cross-engine fusion step** between the multi-engine `gather` and fetch.
It does NOT decide which engines fire (that is §2 routing) — it merges the parallel
candidate-URL lists each engine/adapter returned into one ranked, de-duplicated set.
Concrete ordering:

1. **Collect** every engine's ranked `list[SearchCandidate]` from the parallel `gather`
   (SearXNG + direct registry adapters §3 + Serper + academic backends) — keep the
   per-engine rank position `r_i(url)` for each candidate.
2. **Canonicalize each URL** before any dedup, so the same page from two engines collapses
   to one node: lowercase scheme+host, force `https`, strip the trailing slash, strip
   tracking/query cruft (`utm_*`, `gclid`, `fbclid`, `ref`, session ids), strip URL
   fragments (`#…`), apply known host aliases (e.g. `dx.doi.org`→`doi.org`,
   `www.`-stripping, `clinicaltrials.gov/ct2/show/<NCT>`→`/study/<NCT>`). The canonical
   form is the dedup key.
3. **DEDUP by canonical URL, consolidate-not-drop (§-1.3):** group all engine hits for one
   canonical URL into a single candidate; **keep every contributing engine + its rank**
   on that candidate (the corroboration set), never discard the duplicate — multi-engine
   agreement is signal the fusion score below rewards.
4. **Score with WRRF:** `score(url) = Σ_i w_i / (k + r_i(url))` over the engines that
   returned it, `k≈60` (RRF default), `w_i` = the engine's **existing tier/authority
   weight** (registries/gov > academic > general web; SearXNG science-category > general).
   With `w_i ≡ 1` this degrades exactly to plain RRF (the floor) — so the floor ships even
   before weights are tuned.
5. **Rank, never cap:** sort by `score` descending and pass the WHOLE ranked, de-duplicated
   set to fetch. This is a CONSOLIDATE step — it merges + orders, it does not drop or cap
   (§-1.3), so it is faithfulness-neutral and surgical (a new `fuse_candidates(...)` util
   called once after `gather`, ahead of the unchanged fetch/tier/verify chokepoint).

**Is anything newer than 2009 RRF (re-checked 2026-06-24)?** Yes — and that is exactly the
P1 correction here: the crown is **WRRF (2503.20698, 2025)** with the per-source weight wired
from POLARIS's tier classifier; **Exp4Fuse (2506.04760, 2025)** is the LLM-driven sibling;
plain **RRF (2009) is demoted to the incumbent floor / `w_i≡1` special case**, not the pick.
The fully-learned variant (train `w_i` per query class on the §5 gold set, or a learned
convex score-combination) is the gold-set-gated next step, exactly like the Tier-3 router.

---

## 3. DESIGN PROBLEM #3 — DIRECT CLINICAL-REGISTRY QUERYING

Today the pipeline recognizes FDA/EMA/NICE/Cochrane/trials as high-tier but
relies on paid web (`site:`-scoped Serper) to surface them. That is fragile (web
ranking, paywalls) and not sovereign. The fix: add **direct API adapters** that
return `SearchCandidate` objects, registered against the right `evidence_needs`,
so registries are queried first-class. **The clinical-registry reality is uneven
— this section is honest about which are sovereign-queryable and which are not.**

### 3.1 The registries (primary sources + honest access status)

| Registry | API / endpoint | Key? | Format | Status for a sovereign adapter | Primary source |
|---|---|---|---|---|---|
| **ClinicalTrials.gov v2** | `https://clinicaltrials.gov/api/v2/studies` (params `query.term`, `query.cond`, `query.intr`, `filter.*`, `pageSize`, `format=json`) | **No key** | JSON REST (OpenAPI 3.0) | **GO** — keyless, paginated, clean query syntax. Classic API retired 2024-06; v2 is the supported path. | clinicaltrials.gov/data-api/api · NLM Technical Bulletin 2024 Mar-Apr |
| **openFDA** | `https://api.fda.gov/[noun]/[category].json` (e.g. `drug/label.json`, `drug/event.json`; params `search=`, `limit=`, `skip=`) | **Optional** (keyless with documented per-IP rate limits; an optional free key raises them — confirm exact limits at open.fda.gov before build) | JSON (`meta`+`results`) | **GO** — keyless, Elasticsearch-style `search=field:term`. Drug label + adverse-event + enforcement. **Note the openFDA-vs-DailyMed relationship:** openFDA `drug/label` is a *derived, re-indexed* view of the same DailyMed SPLs (Structured Product Labeling) — so openFDA is best for its Elasticsearch query surface + the adverse-event/enforcement nouns it adds, while **DailyMed (row below) is the more direct source for the verbatim label text itself**. Register both (they complement, not duplicate). | open.fda.gov/apis/ |
| **EMA ePI (Consuming API)** | EMA electronic Product Information API | **No key/subscription** for the public ePI consuming API | JSON (FHIR-based) | **GO (cautious)** — keyless public ePI; broader EMA open-data is partly portal/FHIR (Write-PMS guide v1.2.0 UAT 2025-08). Start with ePI consuming endpoints; treat the rest as portal data. | ema.europa.eu open data · EMA Write-PMS API Implementation Guide v1.2.0 (2025-08) |
| **NICE syndication API** | REST; requires `API-Key` header + `Accept` media-type header | **Yes — free key by application** | XML/HTML/JSON per `Accept` | **GO after key** — apply for the free syndication key; covers NICE guidance + quality standards. Operator-gated step (key request). | nice.org.uk/reusing-our-content/nice-syndication-api · corporate/ecd10 |
| **Cochrane Library / CDSR** | Review-Document API exists but is **access-gated** | **Gated** — "contact Wiley for permission to access full-text/metadata/API" | JSON (where granted) | **NO direct sovereign adapter.** Cochrane is NOT freely API-queryable. **Honest fallback:** reach systematic-review + CENTRAL-class RCT coverage via **Europe PMC + PubMed** (already wired) and OpenAlex; do not promise a Cochrane API adapter. | cochranelibrary.com/help/access · documentation.cochrane.org/display/API |
| **PubMed / E-utilities** | `eutils.ncbi.nlm.nih.gov/entrez/eutils/` (`esearch`/`efetch`) | Optional key (higher rate) | XML/JSON | **GO** — the canonical clinical-literature index; complements Europe PMC. | (NCBI E-utilities, incumbent) |
| **DailyMed v2** *(ADDED 2026-06-24)* | `https://dailymed.nlm.nih.gov/dailymed/services/v2/spls.json` (params `drug_name`, `ndc`, `rxcui`, `setid`, `dea_schedule_code`, `marketing_category_code`, `boxed_warning`, `published_date`; `pagesize`≤100) | **No key** | JSON/XML (`spls.json`/`spls.xml`) | **GO** — keyless NLM SPL (Structured Product Labeling) index; the **most direct US drug-label source**, complementary to openFDA `drug/label` (which is a *derived* index of the same SPLs). Register under `regulatory` alongside `openfda_search`. | dailymed.nlm.nih.gov/dailymed/webservices-help/v2/spls_api.cfm (WebFetch-verified 2026-06-24) |
| **Health Canada DPD** *(ADDED 2026-06-24)* | `https://health-products.canada.ca/api/drug/` (sub-resources `drugproduct`, `activeingredient`, `company`, `status`, `schedule`, `therapeuticclass`; filters `din`, `brandname`, `status`, `lang=en/fr`, `type=json`) | **No key** | JSON/XML | **GO** — keyless, nightly-updated, ~47K Canadian-approved products. **Part of closing the doc's Canada jurisdiction gap (US/EU/UK were covered, Canada was not — and POLARIS is a Canadian clinical company)** — DPD is the *drug-product* arm; the trial + guideline arms are the two rows below. Register under `regulatory` (CA jurisdiction). | health-products.canada.ca/api/documentation/dpd-documentation-en.html (WebFetch-verified 2026-06-24) |
| **Health Canada Clinical Trials Database (CTD)** *(ADDED 2026-06-24 — Canada trial arm)* | `https://health-products.canada.ca/api/clinical-trial/` (sub-resources for sponsor, medical condition, drug product, protocol, status, study population; `lang=en/fr`, `type=json`) + portal `health-products.canada.ca/ctdb-bdec` | **No key** | JSON/XML | **GO (caveat: listing, not a full registry)** — keyless REST API under the same Open Government Licence as DPD; lists Canadian phase I/II/III drug-trial records. **This is the Canadian *trial-registry* coverage the doc lacked** (the §2.2 clinical row named CT.gov + CTIS for US+EU but no CA trials). Honest limitation Health Canada states itself: the CTD is a *listing*, not a comprehensive registry, so pair it with CT.gov/CTIS for full protocol detail. A new HC search portal is phasing in to replace it — re-check the endpoint before build. Register under `{primary_literature, regulatory}` (CA). | health-products.canada.ca/api/clinical-trial/ · canada.ca Health-Canada-Clinical-Trials-Database · open.canada.ca CTD dataset (Open Government Licence, WebFetch-verified 2026-06-24) |
| **CDA-AMC (Canada's Drug Agency, formerly CADTH)** *(ADDED 2026-06-24 — Canada guideline/HTA arm)* | `https://www.cda-amc.ca/` guidance + HTA reports (methods guides, reimbursement reviews, deliberative framework Feb-2025); **no clean public API** — reach via `site:cda-amc.ca` Serper scope, like the NICE-host pattern | n/a (no API) | HTML/PDF | **GO via `site:` scope (no native API, like NICE before its syndication key)** — CDA-AMC is the Canadian HTA + clinical-guideline body (CADTH rebranded to Canada's Drug Agency in 2024 after its federal mandate expansion). **This is the Canadian *guideline/HTA* coverage the doc lacked** — the §2.2 guideline-synthesis row named NICE (UK) but no Canadian HTA. No keyless query API exists, so add `cda-amc.ca` to `jurisdiction_scopes.yaml` as a CA `site:`-scoped Serper host (mirrors how `nice.org.uk` is handled today), not a direct adapter. Register the host under `{standards, regulatory}` (CA). | cda-amc.ca/methods-and-guidelines (web-search-confirmed 2026-06-24; direct WebFetch returned HTTP 402, so confirmed via search results + the corroborated 2024 CADTH→CDA-AMC rebrand, not a page fetch) |
| **EU CTIS (Clinical Trials Information System)** *(ADDED 2026-06-24)* | `POST https://euclinicaltrials.eu/ctis-public-api/search` (public API feeding the EU trials register) | **No key** (public API) | JSON | **GO (cautious — POST + evolving schema)** — the live EU clinical-trials DB that replaced EudraCT/EUCTR; migration to CTIS completed 2025-01-31; **designated a WHO ICTRP Primary Registry 2025-04**. Register under `{primary_literature, regulatory}` (EU). The honest caveat: it is a POST-body search API (not a clean GET), schema still maturing — wrap defensively, fail-open. | who.int/news/item/03-04-2025-…(CTIS WHO primary registry) · ema.europa.eu CTIS · euclinicaltrials.eu public API |
| **WHO ICTRP** *(ADDED 2026-06-24 — honest NO)* | ICTRP search portal (the global trial-registry aggregator over CT.gov/CTIS/ISRCTN/etc.) | n/a | flat-file export / portal | **NO direct sovereign adapter (like Cochrane).** As of 2025 the **ICTRP crawling/programmatic service is unavailable** (survey-gated); ICTRP is portal + bulk-export, not a live query API. **Honest fallback:** query the member registries directly (CT.gov v2 + CTIS) — they ARE the ICTRP feeders — rather than fake an aggregator API. | who.int/tools/clinical-trials-registry-platform (status verified 2026-06-24) |
| **bioRxiv / medRxiv** *(ADDED 2026-06-24 — GO with caveat)* | `https://api.biorxiv.org/details/<server>/<interval>/<cursor>/json` (server=`medrxiv`/`biorxiv`; interval=date-range `YYYY-MM-DD/YYYY-MM-DD` or recent-N) | **No key** | JSON (+ XML OAI-PMH, CSV) | **GO with caveat** — keyless clinical/biomedical **preprint** feed; closes a real recall gap (§2.2 mechanism/preprint row names arXiv but omits clinical preprints, where medRxiv is the gold venue). **Honest limitation: the API is date-range/DOI scan, NOT keyword search** — use it as a recency/snowball feed filtered post-fetch by the embedding re-rank, not a `query.term` engine. Register under `primary_literature`. | api.biorxiv.org (WebFetch-verified 2026-06-24) |

### 3.2 Concrete adapter plan (surgical)

Add new keyless adapters in `domain_backends.py` mirroring the existing
`europe_pmc_search` shape (`(query, limit) -> list[SearchCandidate]`, fail-open):

- `clinicaltrials_search` → `GET /api/v2/studies?query.term=…&pageSize=…&format=json`; emit the canonical study URL (`https://clinicaltrials.gov/study/<NCTId>`) + title + brief-summary snippet. Register under `evidence_needs ∈ {primary_literature, regulatory}` and *always* for clinical query class (§2.2).
- `openfda_search` → `GET /drug/label.json?search=<term>&limit=…` (+ `/drug/event.json` for safety queries); emit the label/SPL URL + snippet. Register under `regulatory`.
- `dailymed_search` → `GET /dailymed/services/v2/spls.json?drug_name=<term>&pagesize=…`; emit the SPL setid URL + title. Register under `regulatory` (US). **More direct than openFDA for the label text itself** (openFDA derives from these same SPLs).
- `health_canada_dpd_search` → `GET /api/drug/drugproduct/?brandname=<term>&type=json`; emit the DPD product URL + DIN + status. Register under `regulatory` (CA jurisdiction) — **the Canada drug-product coverage the doc previously lacked**.
- `health_canada_ctd_search` → `GET /api/clinical-trial/<resource>/?...&type=json` (sponsor / medical-condition / drug-product / protocol / status sub-resources); emit the HC CTD trial record URL + sponsor + condition + status. Register under `{primary_literature, regulatory}` (CA jurisdiction) — **the Canada trial-registry coverage the doc previously lacked**. Honest caveat: HC calls it a *listing*, not a full registry, so corroborate protocol detail via CT.gov/CTIS; a replacement HC search portal is phasing in — re-check the endpoint before build.
- CDA-AMC (Canada's Drug Agency, formerly CADTH) has **no keyless query API**, so it is NOT a direct adapter — add `cda-amc.ca` to `jurisdiction_scopes.yaml` as a CA `site:`-scoped Serper host (identical to the existing `nice.org.uk` host handling, via `site_scoped_serper`); register the host under `{standards, regulatory}` (CA) for the §2.2 guideline-synthesis class. **The Canada guideline/HTA coverage the doc previously lacked.**
- `ema_epi_search` → EMA ePI consuming endpoints; emit medicine/EPAR URLs. Register under `regulatory` (EU jurisdiction).
- `ctis_search` → `POST /ctis-public-api/search` with a JSON body filtering the EU trials register; emit the CTIS trial URL. Register under `{primary_literature, regulatory}` (EU). **POST + maturing schema — wrap defensively, fail-open.**
- `nice_syndication_search` → REST with `API-Key` header (operator provides the free key via `.env`, like ZYTE/SERPER); register under `{regulatory, standards}` (UK jurisdiction). **Gated on the key — fail-open and skip if absent**, identical to the SERPER_API_KEY guard.
- `medrxiv_recent` → `GET api.biorxiv.org/details/medrxiv/<date-range>/<cursor>/json` as a **recency/snowball feed** (not keyword search) for clinical preprints; filter post-fetch by the embedding re-rank. Register under `primary_literature`.

Then extend `SourceAdapterRegistry`: add a `clinical_registry` virtual grouping
(or wire the new adapters into `primary_literature` + `regulatory` need
branches) so the §2.2 clinical query class fires them first-class. **No change to
the tier classifier or faithfulness engine** — registry candidates flow through
the same fetch/tier/strict_verify chokepoint as every other source (no tier
laundering), exactly as `europe_pmc_search` already does (domain_backends.py:411).

### 3.3 Sovereignty note

CT.gov, openFDA, **DailyMed, Health Canada DPD, Health Canada CTD, EU CTIS**, EMA ePI,
PubMed, **bioRxiv/medRxiv** are public-government/keyless = fully sovereign direct queries
(no third-party AI vendor). NICE needs a free key (still sovereign — it is the
registry's own API, not an AI-search reseller). **Full Canada coverage now spans all three
arms** for a Canadian clinical company: drug-product (DPD API), trials (CTD API), and
guideline/HTA (CDA-AMC via `site:` scope — no API exists, so it is reached the same
sovereign way NICE-host content was before the key, not faked as a direct adapter). **Two
honest gaps, both routed around rather than faked:** (1) **Cochrane** (access-gated) → reach
systematic-review/CENTRAL coverage via Europe PMC/PubMed; (2) **WHO ICTRP**
(crawling service unavailable in 2025, portal/bulk-export only) → query its
member registries directly (CT.gov v2 + CTIS + HC CTD), which are the ICTRP feeders. The
medRxiv adapter is keyless but date-scan-only (no `query.term`), so it is a
recency/snowball feed, not a first-class query engine — disclosed, not over-promised.

---

## 4. SOVEREIGN META-SEARCH — replacing Exa's web role

### 4.1 Candidates (2025/2026, primary sources)

| Candidate | Role | Year/recency | Primary source | License | Why / why not |
|---|---|---|---|---|---|
| **SearXNG** *(the pick)* | self-hosted metasearch aggregator over 70+ engines incl. `science` category (PubMed/arXiv/CrossRef/S2) | **calendar-versioned (YYYY.M.D), actively maintained** — docs carry a current 2026 build stamp | github.com/searxng/searxng · docs.searxng.org | **AGPL-3.0** (WebFetch-confirmed at the repo) | Sovereign, Docker-deployable, JSON API, fine-grained `engines=`/`categories=` control → directly drivable by the §2 router. Fork lineage predates 2024 but it is a live **incumbent floor** the mandate explicitly allows (active 2026 maintenance). |
| **Perplexica** | agentic search UI/layer *over* SearXNG | 2024→active 2025 | github.com/ItzCrazyKns/Perplexica | MIT | Pattern inspiration only — it is an agentic front-end on SearXNG; we already have our own agentic loop. Not a meta-search engine itself. |
| **OpenDeepSearch** | OSS deep-search agent over SearXNG/serp backends | 2025 | github.com/sentient-agi/OpenDeepSearch | Apache-2.0 | Reference for the agentic-over-SearXNG pattern; runtime not adopted (frontier-mandate: pattern-inspiration only on our own slate). |
| **Whoogle / 4get** | lighter self-hosted metasearch | active | github.com/benbusby/whoogle-search · 4get.ca | AGPL / various | Single-source-ish (Whoogle ≈ Google proxy); less breadth than SearXNG's multi-engine + `science` category. Backup only. |

**Exa + Tavily:** BANNED (Telus-competitor AI-search). Not adopted, never to be
added. Their neural-recall role is covered by SearXNG breadth + the in-house
Qwen3 embedding re-rank (sovereign), per §0.

### 4.2 SearXNG integration (concrete)

- **Deploy:** official SearXNG Docker image + Redis (rate-limit), private network,
  on the same VM as the pipeline → sovereign, no external AI vendor. Enable JSON
  by adding `json` to `search.formats` in `settings.yml` (default ships HTML only).
- **Query:** `GET /search?q=<query>&format=json&categories=<science|general|news>&engines=<csv>&time_range=<year>`. The §2 router sets `categories`/`engines` per query class (e.g. clinical → `categories=science`, pin `engines=pubmed,crossref,semantic scholar,arxiv`).
- **Adapter:** a `searxng_search(query, *, categories, engines, limit) -> list[SearchCandidate]` in `domain_backends.py`, fail-open, registered as the `open_web` adapter (replacing the demoted Serper-as-default) and as a science-engine source for `primary_literature`. Serper stays as the paid fallback adapter; Zyte stays as the per-URL unblock in `live_retriever`/`access_bypass` (unchanged).

---

## 5. The axis + gold-set sketch (how we measure “better”)

Per §-1.1, the evaluation must be claim/source-level, not metadata counts. Three
sub-axes, each with a labeled gold set (no e2e in this task — this is the sketch
the bake-off harness will implement):

1. **Source/URL recall@k.** Build **N≈30 clinical questions**, each hand-labeled
   with its *must-find authoritative URLs* (the specific CT.gov NCT records,
   openFDA labels, EMA EPARs, NICE guidance, pivotal-trial DOIs a domain expert
   would cite). Metric: fraction of must-find URLs the orchestration surfaces as
   candidates @k (k=20/50). This is the breadth headline (§monitoring memory).
   *Without labeled must-find URLs it is not an axis — count-of-sources is §-1.1-banned.*
2. **Routing precision.** For each query, did the *right* engine fire (did the
   clinical query hit CT.gov/openFDA, not just generic web)? Metric: per-query
   precision = (engines that returned ≥1 must-find URL) / (engines fired). Catches
   the path-A "fan everything everywhere" waste and confirms the §2 map.
3. **Clinical-source coverage.** Of the must-find set, what fraction came from a
   *direct registry adapter* vs paid web? Target: registries surface their own
   records directly (CT.gov/openFDA/EMA/NICE/DailyMed/DPD/CTIS), web is
   corroboration only. Proves §3 is wired and not laundered through Serper.

**Public benchmark anchors for the gold set (ADDED 2026-06-24 — don't reinvent the methodology):**
the hand-labeled clinical gold set above is POLARIS-specific, but it should be
*calibrated against* published retrieval benchmarks so the labeling protocol and the
recall@k bar are not invented in a vacuum:

| Benchmark | Year | Primary source | Use here |
|---|---|---|---|
| **SAGE** | 2026-02 | arXiv 2602.05975 | Frontier deep-research-agent *retrieval* benchmark (1,200 queries / 4 sci domains / 200K corpus); its query-construction + recall protocol is the template for our §5.1 recall@k. |
| **MIRAGE + MedRAG toolkit** | 2024-02 (incumbent floor) | arXiv 2402.13178 · github MedRAG | The medical-RAG retrieval benchmark (7,663 biomedical-QA questions, 5 corpora incl. PubMed); the closest public analogue to our clinical gold set — borrow its corpus/retriever split, not its (non-sovereign) judge. |
| **BRIGHT** | 2024-07 (incumbent floor) | arXiv 2407.12883 | Reasoning-intensive retrieval (1,398 queries; SOTA drops 59.0→18.0 nDCG@10) — the honest reminder that clinical "must-find" queries are reasoning-hard, so a thin recall@k bar is misleading. Pre-2024-adjacent but the canonical reasoning-retrieval floor. |

These are *anchors*, not substitutes: none is sovereign-clinical-Canadian, so the
labeled POLARIS gold set still has to be built — but its methodology is grounded in
published practice, not improvised.

**Baseline-to-beat:** current path-A fan-out (Serper+OpenAlex+S2+Exa) and path-B
need-routing on the SAME gold set, Exa removed. The §2 Tier-1+2 router + §3
registry adapters + §4 SearXNG must beat that baseline on all three sub-axes
before the Tier-3 learned router is even attempted. Faithfulness gates are
untouched throughout — recall goes up, the hard gate does not move.

---

## 6. Provisional pick / design to beat (summary)

- **Meta-search:** **SearXNG** (AGPL-3.0, self-hosted Docker+Redis, JSON API,
  `science` category) replaces Exa's web role as the sovereign default; Serper
  demoted to paid fallback; Zyte unchanged. Exa/Tavily stay banned.
- **Routing:** **Tier-1 deterministic query-type→engine map (clinical-first) +
  Tier-2 sovereign GLM-5.2 per-sub-query classifier**, both extending the
  existing `need_type_router`/`source_adapter_registry` (surgical). **Tier-3
  learned recall-optimizer (RAGRouter 2505.23052 / DeepRetrieval 2503.00223
  pattern) is the design to beat**, built only after the gold set exists.
- **Cross-engine fusion (§2.4):** a **Weighted Reciprocal Rank Fusion (WRRF, arXiv
  2503.20698, 2025)** merge + canonical-URL dedup between the multi-engine `gather`
  and fetch (the previously-unowned hop), with the per-engine weight `w_i` wired from
  POLARIS's existing tier/authority classifier (§-1.3 WEIGHT-AND-CONSOLIDATE). Plain
  **RRF (2009)** is the `w_i≡1` incumbent floor it ships behind; **Exp4Fuse (arXiv
  2506.04760, 2025)** is the LLM-driven variant; a fully-learned `w_i`/score-combination
  is the gold-set-gated design-to-beat. The fusion DEDUPs by canonical URL and keeps
  ALL contributing engines per candidate (consolidate-not-drop), never caps breadth.
- **Clinical registries:** **direct keyless adapters for CT.gov v2, EU CTIS,
  Health Canada CTD (CA trials), openFDA, DailyMed, Health Canada DPD (CA drug
  products), EMA ePI; keyed adapter for NICE; CDA-AMC (CA guideline/HTA) via
  `site:` scope since it has no API; medRxiv as a date-scan feed; route around
  access-gated Cochrane + portal-only WHO ICTRP via the member registries / Europe
  PMC / PubMed.** Full Canada coverage now spans drug-products + trials + guideline/HTA.
  All as `SearchCandidate`-returning fail-open adapters through the unchanged
  fetch/tier/verify chokepoint.

**Recency check:** all external methods are 2025/2026 with primary-source URLs
(RAGRouter 2505.23052 · DeepRetrieval 2503.00223 · Search-R1 2503.09516 · SAGE
2602.05975 · **WRRF/MMMORRF 2503.20698 (2025) · Exp4Fuse 2506.04760 (2025)** · CT.gov
v2 2024+ · EU CTIS 2025 · openFDA · DailyMed v2 · Health Canada DPD + **Clinical
Trials Database** · **CDA-AMC/CADTH guidelines 2025** · EMA ePI 2025 · NICE ecd10 ·
bioRxiv/medRxiv API). 2024-and-earlier incumbent floors are named as such: SearXNG
(2026 release tag, actively maintained), **RRF 2009 (now demoted from the fusion crown
to the `w_i≡1` floor behind WRRF)**, BRIGHT/MIRAGE (eval anchors). **Is anything newer
(re-checked 2026-06-24)?** No off-the-shelf sovereign OSS *engine-router* beats the
Tier-1+2 design; **SearXNG is still the only widely-adopted OSS metasearch** (no 2026
challenger surfaced); for fusion, the 2025 crown is **WRRF (weighted RRF, 2503.20698)**
with Exp4Fuse (2506.04760) as the LLM-driven sibling — plain RRF is the floor, not the
pick. The 2026 movement is on benchmarks (SAGE) and agentic-RL-search loops (Search-R1
family), both captured. Re-check arXiv query-routing + rank-fusion + the SearXNG release
feed + the registry API docs (esp. the still-maturing CTIS POST schema) before build.

**Honest OSS-vs-banned:** every adopted component is OSS + self-hostable (SearXNG
AGPL; GLM-5.2 in-house; registries are public-government APIs). Serper + Zyte are
allowed plumbing, not AI modules, and are demoted/retained as raw-search /
unblock only. Exa + Tavily are removed and stay banned. **Two honest capability
gaps, routed around not faked:** Cochrane (access-gated, no sovereign API) and WHO
ICTRP (crawling service unavailable, portal/bulk-export only) — both reached via
their member registries / Europe PMC / PubMed.

---

## 7. Completeness note (independent critic pass, 2026-06-24)

This doc was put through an independent completeness + unknown-unknowns critic on
**2026-06-24** (frontier-tech mandate; every candidate primary-source-verified via
WebFetch; pre-2024/non-OSS/Exa/Tavily rejected). Floor claims re-grounded against
the live repo (Exa = 130 lines in `searcher.py` confirmed; path-B adapters in
`domain_backends.py` confirmed; `need_type_router.py` + `source_adapter_registry.py`
relocated to `src/polaris_graph/discovery/`).

**Additions (all primary-source verified):**
- **Clinical registries the original doc never listed:** DailyMed v2 (keyless SPL labels), **the full Canada trio for a Canadian clinical company — Health Canada DPD (keyless drug-product API), Health Canada CTD (keyless clinical-trial API), and CDA-AMC/CADTH (Canadian guideline/HTA, no API → `site:` scope like NICE)**, EU CTIS (keyless public POST API, now a WHO primary registry), bioRxiv/medRxiv (keyless preprint date-scan feed). Honest NOs added: WHO ICTRP (crawling service unavailable in 2025 — portal/export only).
- **§2.4 cross-engine candidate fusion + the HOW of canonical-URL dedup** — a genuine in-scope UNKNOWN-UNKNOWN: the doc decided *which* engines fire but never *how* the parallel candidate lists merge + de-duplicate before fetch. Now specified end-to-end as a 5-step merge (collect → canonicalize-URL → dedup-consolidate-keep-all → WRRF-score → rank-never-cap), with the **2025 frontier crown = WRRF / weighted RRF (arXiv 2503.20698)** wiring POLARIS's existing tier weight into the merge, **Exp4Fuse (arXiv 2506.04760)** the LLM-driven sibling, and **plain RRF (2009) demoted to the `w_i≡1` incumbent floor** — correcting the prior draft that crowned 2009 RRF (a frontier-tech-mandate violation).
- **Agentic-RL-search family** (Search-R1 2503.09516, Apache-2.0, + ZeroSearch/DeepResearcher siblings) added to the §2 router literature as a richer design-to-beat.
- **§5 public benchmark anchors** (SAGE 2026 / MIRAGE 2024 / BRIGHT 2024) so the clinical gold-set methodology is grounded, not improvised.

**Corrections:**
- **Frontier-mandate fix — the fusion crown (§2.4):** the prior draft crowned **2009 RRF** as "the honest pick for POLARIS's cross-engine merge now," a frontier-tech-mandate violation (a 2009 algorithm cannot be the crown). Corrected: the crown is **WRRF / weighted RRF (arXiv 2503.20698, SIGIR 2025, primary-source-verified)** — the per-source weight maps directly onto POLARIS's existing tier/authority classifier (§-1.3) — with **Exp4Fuse (arXiv 2506.04760, ACL 2025 Findings, CC BY 4.0)** as the LLM-driven sibling; **plain RRF (2009) is demoted to the explicit `w_i≡1` incumbent baseline/floor** the weighted/learned methods must beat. The vague "learned/normalized score-combination (survey literature 2025)" hand-wave was replaced with these named, primary-source-verified methods.
- **Fixed a mis-cite:** §2.1 cited arXiv **2505.23052 twice** (once as "RAGRouter", once as a "survey/taxonomy"). It is a single paper (RAGRouter); the phantom survey row was removed and the RAGRouter row corrected (it routes to *RAG-augmented LLMs*, not engines — adaptation, not drop-in).
- DeepRetrieval row corrected: arXiv **2503.00223**, github.com/pat-jj/DeepRetrieval, **CC BY 4.0**, with its verified clinical-trial recall headline (63.18%).

**Unknown-unknowns surfaced (what a 2026 clinical deep-research system does here that the doc never asked):**
1. **Cross-engine result fusion / canonical-URL dedup** (now §2.4) — the strongest in-scope miss.
2. **Jurisdiction completeness** — the doc had US/EU/UK but no **Canada**, despite POLARIS being a Canadian clinical company. Now covered across all three arms: **drug products (DPD API), trials (CTD API), guideline/HTA (CDA-AMC via `site:` scope)** — DPD alone was insufficient (it is only the drug-product arm; the critic asked for Canadian *guideline + trial* registries too).
3. **DailyMed vs openFDA distinction** — openFDA `drug/label` is a *derived* index of DailyMed SPLs; the doc treated openFDA as the only US-label source.
4. **Clinical preprints** — medRxiv is the gold clinical-preprint venue and the §2.2 preprint row omitted it (arXiv only).
5. **Eval-methodology grounding** — the §5 gold set was self-invented; published retrieval benchmarks (SAGE/MIRAGE/BRIGHT) anchor it.

**Rejected / not added (LAW II honesty):**
- **Exa, Tavily, Perplexity-API, Google paid-AI search** — banned/non-sovereign; never added.
- **OpenDeepSearch / Perplexica as runtime** — already in §4 as pattern-inspiration-only; not promoted to adoption (frontier mandate: external runtimes are inspiration on our own slate).
- **WHO ICTRP as a query adapter** — verified *unavailable* (crawling service down 2025); recorded as an honest NO, not a capability.
- **medRxiv as a keyword engine** — its API is date-scan only; recorded with that explicit limitation, not over-promised.
- **A brand-new greenfield router** — would violate surgical-not-rewrite; the design stays an extension of the existing `need_type_router`.

**Residual / re-check-before-build:** the CTIS POST schema is still maturing (wrap defensively); openFDA exact rate limits to confirm at open.fda.gov; the learned-fusion + Tier-3-router both remain gold-set-gated. No e2e / run-spend in this pass.
