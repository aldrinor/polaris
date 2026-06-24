# Source-Credibility & Tier-Classification Landscape 2025/2026 — the WEIGHT-not-FILTER DNA (I-cred-001)

**Status:** research deliverable, operator-requested 2026-06-24. Section "SOURCE CREDIBILITY & TIER
CLASSIFICATION" of the standard pipeline-section review
(`docs/standard_process_pipeline_section_review.md`). Sibling of
`docs/retrieval_landscape_2026.md` and `docs/consolidation_landscape_2026.md`; mirrors their structure.
**Method:** deep research — current POLARIS modules grounded against the actual repo (file:line), then
the 2025/2026 OSS frontier for venue ranking / peer-review & retraction detection / ML credibility
scorers, every candidate primary-source-verified (year + arXiv/GitHub/HF URL + license), then a recency
re-check ("is anything NEWER?") and an honest-uncertainty pass.
**Scope guard (the section's job):** how a source earns its **credibility WEIGHT** — a T1–T7 tier and an
`authority_score`. This is the weight-not-filter spine (CLAUDE.md §-1.3): *every relevant source flows
through to composition carrying a weight; we never hard-drop to hit a number.* The tier classifier and
`authority_score` ARE that weighting system. The downstream consolidation/aggregation of those weights
is the consolidation section's job, not this one.

---

## 0. The one-paragraph answer

POLARIS's **live** credibility weighting is `tier_classifier.py` — a deterministic rule cascade over
**~22 hardcoded domain frozensets** (REGULATORY, INDUSTRY_MARKETING, SOCIAL_PLATFORM,
MARKET_RESEARCH, PEER_REVIEWED_JOURNAL, …). It is honest, auditable, fast, and zero-LLM — but it is a
**maintenance treadmill**: 16 documented "passes" (Pass-9 through Pass-16, plus the M-/BUG- series) each
bolted another host onto a frozenset because OpenAlex mis-labelled a law-firm blog or a press-wire as
`article`/`journal`. Every new run finds a host the lists do not cover, defaulting it to UNKNOWN. The
field-agnostic successor — `authority_model.py`, **"ZERO host names in code,"** five data-driven signals
A–E over OpenAlex/ROR/PSL — is built, tested, and **default-OFF** (`PG_USE_AUTHORITY_MODEL=0`); no
downstream gate reads its score. So the floor is *the wired rules path*, with a *half-wired data-driven
successor* sitting behind a flag. The 2025/2026 frontier question is exactly this transition: **replace
the brittle host allowlists with a learned, data-driven venue/source credibility signal — emitted as a
WEIGHT, never a drop.** Four genuine 2025/2026 levers exist for that, and one of them is purpose-built:
**AuthorityBench** (arXiv 2603.25092, Mar 2026) is a labeled domain/entity-authority **gold set + the
LLM-as-authority-judge recipe** — the missing yardstick for an isolation bake-off. The other three are a
**learned questionable-venue scorer** (Science Advances 2025, DOAJ-grounded), **LLM domain-credibility
judges** validated against NewsGuard/MBFC (arXiv 2502.04426), and **clinical study-type/publication-type
classifiers** (PubMedBERT 1.2M-article tagger; StudyTypeTeller LLM) — the data-driven replacement for
the hand-rolled `_PRIMARY_STUDY_TITLE_MARKERS` / `_detect_systematic_review_from_title` regexes. The
signal-source APIs underneath (OpenAlex, Crossref, Retraction Watch, SJR/CORE/DOAJ) are *not dated* —
they are the standard providers the learned scorers layer on top of, the same way rerankers layer on top
of PubMed/arXiv in the retrieval section.

---

## 1. What POLARIS has today (verified in the repo, not assumed)

| Layer | Current POLARIS implementation | Verified location |
|---|---|---|
| **Live tier classifier** | Deterministic rule cascade, T1–T7 + UNKNOWN, first-match-wins, every match logs a reason | `src/polaris_graph/retrieval/tier_classifier.py:1229` `_classify_source_tier_rules` |
| Host knowledge | **~22 hardcoded `frozenset` domain lists** (REGULATORY, NIH_LIT, INDUSTRY_MARKETING, PHYSICIAN_PORTAL, LOW_PROVENANCE, LEGAL_COMMENTARY, SOCIAL_PLATFORM, MARKET_RESEARCH, CLINICAL_REFERENCE, POLICY_THINK_TANK, GOV_AGENCY, STATISTICAL_AGENCY, BUSINESS_NEWS, WEB_GUIDE, VENDOR_BLOG, NEWS_BLOG, PEER_REVIEWED_JOURNAL, LOW_QUALITY_OA, GUIDELINE_AUTHORITY, PREPRINT, STUDENT_JOURNAL, ABSTRACT_ONLY) | `tier_classifier.py:169-851` |
| Venue identity | DOI-prefix allowlist (`PEER_REVIEWED_DOI_PREFIXES`, 24 registrant prefixes) + OpenAlex `source_type`/`venue` resolution | `tier_classifier.py:690-804` |
| Article-type detection | **Hand-rolled title regexes**: `_detect_systematic_review_from_title`, `_detect_primary_study_signal` (`_PRIMARY_STUDY_TITLE_MARKERS`), `_detect_conference_abstract`, guideline/explainer markers | `tier_classifier.py:888-1205` |
| Retraction | OpenAlex `is_retracted` → **Rule 0**, routes to UNKNOWN + "caller should exclude" | `tier_classifier.py:1254-1263` |
| Stub vs venue | `fetch_degraded` carve-out (I-arch-011 B17): a known venue fetched as a <1000-char stub KEEPS venue authority but is labelled degraded, excluded from grounded-content adequacy (no laundering) | `tier_classifier.py:770-805, 1302-1330` |
| **Field-agnostic authority model** | 5 signals: A scholarly-graph, B institutional (ROR/PSL), C structural-junk, D corroboration (independent hosts), E recency; blended `clamp01(Σ w·score)·junk_cap·corroboration`. **"ZERO host names in code,"** data-driven | `src/polaris_graph/authority/authority_model.py:84` `score_source_authority`; signals in `authority/citation_graph.py`, `institutional.py`, `junk_detection.py`, `corroboration.py`, `recency.py` |
| Switch | `PG_USE_AUTHORITY_MODEL` (default `0`) → dispatcher chooses rules vs authority model | `tier_classifier.py:1212-1226` |
| Additive output fields | `authority_score`, `source_class`, `corroboration_count`, `authority_confidence` — **emitted but inert**; no downstream gate reads them in shadow mode | `tier_classifier.py:135-156, 2108-2187` |
| Data backbone | OpenAlex (publication/source type, venue, is_retracted), ROR (institution types), PSL (gov/registrable-domain) | `authority/data_loader.py`; consumed in `live_retriever.py:51` |

**Three corrections to any naive read of the floor, grounded in the repo:**

1. **The live path is the RULES path, not the authority model.** `PG_USE_AUTHORITY_MODEL` defaults to
   `0`; the data-driven model is shadow-only. Any "POLARIS already scores authority data-drivenly" claim
   is false on the live path. The frontier work IS finishing this transition.
2. **The rules path is a maintenance treadmill, and the repo says so.** The frozensets carry 16+ "pass"
   provenance comments (`Pass-9 … Pass-16`, `BUG-M-7/10`, `M-18a/b/c`), each a host added after a live
   run mis-tiered it. This is the brittleness the learned scorers exist to replace — not a bug to patch
   with a 23rd frozenset.
3. **The retraction "exclude" is the ONE near-drop in the floor, and it is honest but worth re-framing.**
   `R0_retracted` → UNKNOWN + "caller should exclude" is the single defensible exclusion. Even it fits
   weight-not-filter better as **lowest-weight-with-disclosure** ("retracted; do not rely") than a silent
   drop — keep the source visible, mark it retracted, let the per-claim verifier see it. Note the tension;
   do not resolve it by hard-dropping.

---

## 2. Why this section matters: the two failure modes a credibility weight must beat

A source-credibility layer exists to beat two measured LLM/RAG failures — both named in the 2025/2026
literature, both directly relevant to a clinical deep-research pipeline:

- **Volume vulnerability** — adopting a consistent-but-false claim from *many* low-credibility sources
  over a *few* high-credibility ones. Measured and labeled in **AuthorityBench** (arXiv 2603.25092). This
  is the vaccine-volume hard case. The defense is *weight beats count* — which is why the credibility
  weight must be real, per-source, and feed aggregation (the consolidation section consumes it).
- **Credibility ignorance** — treating all sources as equal. Also measured in AuthorityBench;
  corroborated by arXiv 2502.04426 finding off-the-shelf LLMs have "limited sensitivity to credibility"
  when merely prompted. The defense is an *explicit, disclosed* weight per source — POLARIS's tier +
  `authority_score`, surfaced per citation.

The floor's rules path addresses these crudely (a hardcoded host either is or isn't a journal). The
frontier upgrade is a *graded, learned, data-driven* weight that generalizes to hosts no frozenset has
seen — without ever hard-dropping (DNA).

---

## 3. The signal sources (NOT dated — the standard providers the scorers layer on top of)

These are corpus-/metadata-ACCESS providers, the credibility analog of PubMed/arXiv/OpenAlex in the
retrieval section. A provider being old ≠ dated if it is still the standard. Apply the retrieval-doc
rule: *signal-source API old ≠ dated; ML scorer pre-2024 = reject unless incumbent floor.*

| Provider | What it gives the weight | Status | License / access |
|---|---|---|---|
| **OpenAlex** | publication_type, source_type, venue, host_organization, is_retracted, citation counts; ISSN-L join to SJR (90.0% match) | Standard scholarly graph; **already wired** in POLARIS. *Caveat:* as of Feb 2026 OpenAlex moved to a freemium model — an API key is now required at volume (verify the run env carries one) | CC0 data; free API w/ key |
| **Crossref REST API** | DOI registrant → publisher, type, license, **Retraction Watch retractions/corrections** (merged into the production schema **Jan 2025**; the Labs annotation path is deprecated) | Standard DOI metadata; the canonical retraction feed | Open; CSV mirror at `gitlab.com/crossref/retraction-watch-data` |
| **Retraction Watch DB** | human-verified retraction list, daily updated; **more complete than OpenAlex `is_retracted`** (arXiv 2403.13339: OpenAlex's flag misses retractions Retraction Watch catches — cross-reference both) | Standard; Crossref-owned since 2023 | CC-BY; free |
| **SJR (Scimago)** | journal-rank quartile (Q1–Q4), SJR score (prestige-weighted citations) | Standard venue prestige; joinable to OpenAlex by ISSN-L (90.0% coverage) | Free to browse; bulk under terms |
| **CORE Rankings** | conference/venue rank (A*/A/B/C) — the venue-prestige signal for CS/eng corpora | Standard for non-journal venues | Free |
| **DOAJ** | OA-journal whitelist + transparency criteria; the *gold-label source* for "questionable vs legitimate" classifiers (§4) | Standard OA whitelist. *Caveat:* sponsor-funded (Springer/Wiley/T&F) → not a neutral oracle; ~44% "suspected predatory" found in a Mar-2025 replication. Use as one signal, never hardwired ground truth | Open metadata; CC-BY |
| **Semantic Scholar (S2)** | venue normalization + `influentialCitationCount` (4-class influence classifier — a quality-weighted alternative to raw citation count) | Standard scholarly graph (enumerated in the task). **Largely redundant with OpenAlex** for POLARIS's purpose — OpenAlex is already the wired backbone and covers venue/source_type/citations; influence is biased toward already-highly-cited papers (influence ≠ correctness). Add only if a venue not in OpenAlex needs resolving | Open API (key) |

**Why none is "the answer":** every one is a *prior over the venue/publisher*, not a *per-claim* signal,
and several are gameable or captured (DOAJ sponsorship; SJR self-citation inflation). The 2025/2026
*method* frontier is the learned scorer that **fuses** these into a graded weight and generalizes to
unseen hosts — and the verifier that overrides the prior per claim. POLARIS's existing
`authority_model.py` already fuses OpenAlex+ROR+PSL; the upgrade is the learned head + the missing
gold-set yardstick.

---

## 4. The 2025/2026 method frontier — the learned credibility scorers (the genuine ADD)

Open-source-first; license-flagged for sovereignty. These are the methods that REPLACE the hardcoded
frozensets with a data-driven weight.

### 4.1 AuthorityBench — the labeled gold set + the LLM-as-authority-judge recipe (THE yardstick)
- **arXiv 2603.25092**, Yao, Zhang & Bi, **2026-03-26**. Paper license: arXiv nonexclusive-distrib; the
  paper states **"Code and benchmark are available"** — but the WebFetch confirmed only the *paper*
  license, **not the repo code license**. Treat the **benchmark data as usable as a gold set** regardless;
  **verify the actual code-repo license before vendoring** the judge implementation. Primary:
  https://arxiv.org/abs/2603.25092
- Three datasets, all directly usable as POLARIS's isolation gold set:
  **DomainAuth** (10K web domains, **PageRank-based** authority labels — same primitive as RAGRank /
  AuthorityBench's lineage), **EntityAuth** (22K entities, popularity-based), **RAGAuth** (120 queries
  with documents of varying authority for downstream RAG eval).
- Recipe: LLM scores authority via **PointJudge / PairJudge / ListJudge**; **ListJudge and PairJudge with
  a PointScore output correlate best with ground-truth authority; ListJudge is the cost-optimal**.
  **Authority-guided filtering improved downstream RAG answer accuracy** — i.e. the weight is load-bearing.
- **Critical finding for our verifier-first DNA:** "incorporating webpage text consistently DEGRADES
  judgment performance — authority is distinct from textual style." So a credibility prior should be
  computed from **metadata/graph signals, not the page body** — which is exactly what `authority_model.py`
  does (signals A/B/D are graph/institution/corroboration; the body only feeds the junk signal C).
- **Why it's the headline:** it is the only fetched candidate that is *both* a benchmark POLARIS can bake
  off against *and* a method (LLM-judge) that drops onto the sovereign GLM/DeepSeek slate, no host lists.

### 4.2 Learned questionable-venue scorer — DOAJ-operationalized (the clinical-corpus guard)
- **Science Advances, Aug 2025**, Zhuang, Liang & Acuna — "Estimating the predictability of questionable
  open-access journals." Primary: https://pmc.ncbi.nlm.nih.gov/articles/PMC12383260/ /
  https://www.science.org/doi/10.1126/sciadv.adt2792
- Operationalizes **DOAJ criteria** into ML features across three families: **website content** (aims/scope
  readability, editorial-board affiliations, ethics/copyright policy), **website design** (HTML TF-IDF +
  ResNet homepage-screenshot embeddings), **bibliometrics** (citation patterns, author h-indices,
  self-citation rate, institutional diversity).
- Gold set: **12,869 legitimate + 2,536 questionable** journals (DOAJ whitelist/unwhitelist; no
  proprietary Cabells). Performance: combined model **PRC-AUC 0.79 (±0.03)** (bibliometrics-only 0.64);
  at a 50% threshold on Unpaywall it flagged **1,437 titles at precision 0.757 / recall 0.376** (~24% FP).
- **License: CC-BY-NC** (non-commercial) and no released repo. → **yardstick / feature-recipe inspiration
  only**, not vendorable. But the *feature families* are directly portable to a sovereign re-implementation
  on top of OpenAlex bibliometrics, and the **DOAJ gold set is a usable label source** for the isolation
  bake-off.
- **Honest limit it documents (quote the operator should hear):** recall 0.376 means **~1,782 problematic
  journals stay undetected** at that threshold. A questionable-venue score is a *down-weight*, never a
  drop — exactly the DNA. Use it to demote, never to gate.

### 4.3 LLM domain-credibility judges — validated against NewsGuard/MBFC (the news/web half)
- **arXiv 2502.04426**, Loru et al., **2025**, "Decoding AI Judgment: How LLMs Assess News Credibility and
  Bias." Primary: https://arxiv.org/html/2502.04426v2
- 2,286 news domains, ground truth = **NewsGuard + MBFC**; six LLMs (DeepSeek-V3, Gemini-1.5-Flash,
  GPT-4o-mini, Llama-3.1-405B, Llama-4-Maverick, Mistral-Large-2). **Unreliable-source detection
  agreement 85–97%**; **reliable** domains are the hard class (GPT-4o-mini / Llama-4-Maverick misclassify
  32% / 35%). URL-only F1 0.78 vs full-HTML 0.86.
- **Two findings that bind our design:** (1) **right-leaning outlets are systematically misclassified as
  unreliable** — a measured political bias → an LLM credibility judge must be **audited for skew and never
  be a single hardwired oracle** (matches the §-1.3 capture-resistance rule and the NewsGuard/Ad-Fontes
  FTC-capture caution in the June-7 prior art). (2) The robust direction is *spotting the unreliable*
  (down-weight), not certifying the reliable — again, demote-don't-certify.
- **License:** method/finding (paper); the open substitute for the proprietary NewsGuard/MBFC labels is
  **CRED-1** (CC-BY-4.0, offline domain-credibility table — already named in the consolidation section as
  the down-weight-only overlay). Use a sovereign LLM judge + CRED-1, never the proprietary APIs.

### 4.4 Clinical study-type / publication-type classifiers (the data-driven replacement for the title regexes)
- **Publication-Type Tagging w/ Transformer Models** — medRxiv 2025
  (`10.1101/2025.03.06.25323516`): **PubMedBERT** multi-label tagger trained on **>1.2M** human-curated
  PubMed articles (title+abstract) for publication types AND study designs; full-text-feature variant at
  `10.1101/2025.04.23.25326300`. Primary:
  https://www.medrxiv.org/content/10.1101/2025.03.06.25323516.full.pdf
- **StudyTypeTeller** — PMC12657658, Doneva et al. 2025 (fetched): classifier into **14 study types** (RCT,
  cohort, case report, animal, …) on a **2,645-sample** human-annotated corpus, for SR screening. Tested 7
  BERT models + GPT-3.5/4. **Key sovereignty fact: the fine-tuned encoder beats the generative LLM** —
  SciBERT **F1 0.839** vs GPT-4 **0.645** vs GPT-3.5 0.540 → a small local BERT is both more accurate AND
  cheaper than an LLM judge for this task. **Code + data are public (GitHub) — OSS.**
- **GRT/IRGT/SWGRT trial-design classifier** — Aghaarabi & Murray, **JMIR Medical Informatics 2025**, vol 13,
  e63267, published **2025-05-09** (fetched). Primary: https://medinform.jmir.org/2025/1/e63267. Fine-tuned
  **BioMedBERT** to detect *trial-DESIGN* specificity beyond publication-type — **group-randomized (GRT),
  individually-randomized group-treatment (IRGT), and stepped-wedge group-randomized (SWGRT)** designs.
  Sensitivity/specificity: GRT 0.94/0.90, IRGT 0.81/0.97, SWGRT 0.96/0.99, negatives 0.95/0.93. **License:
  CC-BY-4.0 open-access** (confirm any released model/data repo license before deploy). **Why it matters
  here:** it is a 2025 *third* clinical-tagger candidate for the isolation bake-off alongside PubMedBERT
  (publication-type) and StudyTypeTeller (14 study-types) — it captures the cluster-randomization structure
  the other two do not, which is load-bearing for correctly tiering cluster-trial evidence (a GRT/SWGRT is
  not the same risk-of-bias profile as an individually-randomized RCT) feeding the T1/T2/T4 ladder.
- **Why this matters here:** POLARIS's T1-vs-T2-vs-T4 split currently rests on **hand-rolled title
  regexes** (`_PRIMARY_STUDY_TITLE_MARKERS`, `_detect_systematic_review_from_title`,
  `_GUIDELINE_*` markers) — 16 passes of whack-a-mole. PubMedBERT publication-type tagging is the
  data-driven, EBM-grounded replacement that maps cleanly onto the clinical tier ladder
  (RCT/cohort→T1, SR/MA→T2, guideline/consensus→T2, narrative/case→T4). **License: verify** (PubMedBERT
  base is MIT; the fine-tuned weights/release license is under-specified in the preprint — verify before
  deploy). This is the clinical slice of the isolation axis.

### 4.5 Independence-aware authority — PageRank/RAGRank lineage (cross-ref, lives in consolidation)
- Trust-propagation over a citation/link graph (RAGRank PageRank-style; AuthorityBench's DomainAuth labels
  are literally PageRank). A source cited 100× by one origin scores LOWER than one cited 10× by 10 distinct
  origins — the echo-chamber defense. **POLARIS's Signal D (corroboration over independent registrable
  hosts, `corroboration.py`) is the seed of this.** The independence-COLLAPSE machinery (origin clusters,
  copy-invariance) is the **consolidation** section's job; here it matters only as the *authority* input
  (PageRank authority of the canonical origin). Cross-ref `docs/consolidation_landscape_2026.md` §3.
- **RAGRank — the named primary-source candidate for citation-graph authority weighting.** arXiv 2510.20768
  (Jia, Ramesh, Shamsi, Zhang & Liu), **2025-10-23** (v1; v2 2025-12-15), ACSAC-2025 poster. Primary:
  https://arxiv.org/abs/2510.20768. Applies **PageRank as a source-credibility algorithm over the corpus
  citation graph to counter RAG poisoning** — assigns a LOWER authority score to malicious/poisoned
  documents while promoting trusted content; the poisoning/echo-chamber defense is exactly Signal D's job.
  **License: CC-BY-SA-4.0** (paper); **no public code repo found** on the arXiv page → method/pattern
  reference, not a vendorable implementation (the PageRank primitive is re-implementable sovereignly over
  the OpenAlex citation graph). This is the concrete OSS-pattern candidate the doc previously under-specified
  as "RAGRank lineage"; verify any released repo's license before vendoring.

### 4.6 Clinical health-source authority framework — the domain-specific authority axis
- **"Authority Signals in AI Cited Health Sources: A Framework for Evaluating Source Credibility in ChatGPT
  Responses"** — Jacques, Datuowei, Jones, Basch, Vanderpool, Udeozo & Chapa, arXiv 2601.17109,
  **2026-01-23**. Primary: https://arxiv.org/abs/2601.17109. **License: CC-BY-4.0**; research materials
  released on Zenodo (clean to reference).
- Operationalizes a **four-domain authority framework** for HEALTH-domain sources: **Author Credentials**
  ("who wrote it"), **Institutional Affiliation** ("who published it"), **Quality Assurance** ("how was it
  vetted"), **Digital Authority** ("how does AI find it"). Built from a study of **615 sources cited across
  100 HealthSearchQA questions** entered into ChatGPT 5.2 Pro; **>75% of cited sources were established
  institutional hosts** (Mayo Clinic, Cleveland Clinic, NHS, PubMed, Wikipedia).
- **Why it matters here:** it is a 2026 domain-specific instantiation of source-credibility weighting,
  complementary to AuthorityBench's generic domain/entity authority (§4.1) — it names the clinical authority
  axes (clinician credentials, institutional vetting) that a generic web-PageRank prior cannot see. Directly
  relevant to the §5 CLINICAL SLICE and the §2 credibility-ignorance failure mode: it is a *down-weight /
  weight* recipe, never a gate, and it confirms the doc's DNA that authority is a disclosed per-source signal.
  Use as a **feature-recipe / gold-label inspiration** for the clinical health-source authority axis; the
  framework itself is descriptive (no released scorer model), so it is yardstick + axis-definition, not a
  drop-in classifier.

---

## 5. The isolation axis — how to bake this section off WITHOUT an e2e run

**Metric the section CONTROLS:** *tier-assignment / authority-weight ACCURACY against a labeled
venue/credibility gold set* — precision/recall per tier, plus rank-correlation of the continuous
`authority_score` against graded authority labels. **NOT** an end-to-end report quality run (that
confounds retrieval, consolidation, generation, verify). The classifier takes a `ClassificationSignals`
in and emits a `ClassificationResult` (tier + score) out; the bake-off is a pure input→label comparison
on banked rows.

**Gold sets (concrete, named — not a slogan):**
1. **Venue→tier labels** from SJR quartile + CORE rank + DOAJ membership (map Q1/A*→high-tier,
   questionable→low). Measure per-tier P/R of the rules path vs the authority model vs an LLM-judge.
2. **Retraction labels** from Retraction Watch / Crossref → measure `R0_retracted` recall (and the
   OpenAlex-only blind spot from arXiv 2403.13339: cross-referencing Retraction Watch should lift recall).
3. **Questionable-venue labels** from the DOAJ 12,869/2,536 gold set (§4.2) → measure down-weight
   precision/recall; report the recall ceiling honestly (≤~0.38 at useful precision).
4. **Graded-authority correlation** from **AuthorityBench DomainAuth (10K) + RAGAuth (120)** → rank-correlate
   the continuous `authority_score` against PageRank ground truth (the AuthorityBench native metric);
   this is the cleanest isolation test because it grades the *weight*, not just the tier bucket.
5. **CLINICAL SLICE (mandatory):** a labeled clinical-venue/study-type set — PubMed publication-type
   ground truth (RCT / SR-MA / guideline / narrative / case report) from the PubMedBERT 1.2M corpus or
   the StudyTypeTeller 2,645-abstract corpus, plus the **GRT/IRGT/SWGRT trial-design labels** (JMIR Med
   Inform 2025, §4.4) for cluster-randomization structure → measure whether the tier ladder puts
   **RCT/cohort at T1, SR/MA/guideline at T2, narrative/case at T4** (and does not laund a cluster-trial's
   weaker design into the individually-randomized-RCT bucket). The **clinical health-source authority
   axes** (author credentials / institutional vetting / quality-assurance, §4.6) are the domain-specific
   weight to grade alongside the tier bucket. This is the §-1.1 clinical-safety control: a mis-tiered
   contraindication-bearing case report laundered to T1 is the lethal failure this axis exists to catch.

**Acceptance is behavioral (§-1.4), weight-not-filter (§-1.3):** a candidate wins on (a) higher per-tier
P/R and higher score-vs-label correlation on the gold sets above, AND (b) **no source is ever
hard-dropped** — a "low" verdict is a low weight that still flows to composition, fail-loud if any
candidate silently zeroes/drops a row. No candidate is crowned on a vendor/self-reported number; the
labeled gold-set comparison decides.

---

## 6. KEEP vs ADD (against the current rules-path + shadow authority-model floor)

### KEEP (verified present and correct)
- **The deterministic rules path as the auditable backstop.** Zero-LLM, reason-logged, fast. Keep it as
  the explainable floor and the regression oracle — do NOT delete it when the learned scorer lands.
- **`authority_model.py` 5-signal data-driven design.** "ZERO host names in code" is the right north
  star; signals A/B/D being graph/institution/corroboration (not body text) matches AuthorityBench's
  "authority is distinct from textual style." Keep and **wire it** (see ADD-1).
- **The `fetch_degraded` venue/stub separation** (I-arch-011 B17). It already does the right
  weight-and-label thing — venue authority kept, grounded-content adequacy separate, no laundering. Keep.
- **OpenAlex + Crossref/Retraction-Watch + ROR + PSL data backbone.** Standard providers; keep. Add the
  Retraction-Watch cross-reference (ADD-4).

### ADD / FIX (priority order)
1. **Flip on and wire `PG_USE_AUTHORITY_MODEL`, with a downstream consumer.** The biggest genuine gap is
   that the data-driven score is *shadow-only*. Stand up a behavioral bake-off (§5) proving the authority
   model's per-tier P/R ≥ the rules path on the gold sets, then make a downstream gate read `authority_score`
   as the disclosed weight. This converts the host-treadmill into a data-driven weight without deleting the
   rules backstop.
2. **Add an AuthorityBench-style LLM-as-authority judge on the sovereign slate (the learned head).** A
   ListJudge/PairJudge authority scorer over **metadata signals (not body text)**, calibrated against the
   AuthorityBench gold set, emitting a graded weight for hosts no frozenset has seen. Flag-gated;
   down-weight-only.
3. **Replace the clinical title regexes with a PubMedBERT publication-type / study-design tagger.** The
   single highest-value clinical fix: data-driven RCT/SR/guideline/narrative tagging feeding the T1/T2/T4
   ladder, retiring the 16-pass regex treadmill (`_PRIMARY_STUDY_TITLE_MARKERS` et al.). Verify the
   fine-tuned-weight license first.
4. **Cross-reference Retraction Watch against OpenAlex `is_retracted`.** arXiv 2403.13339 shows OpenAlex
   misses retractions; pull the Crossref/Retraction-Watch CSV and union it into Rule 0's input to lift
   retraction recall. And re-frame the retracted verdict as **lowest-weight-with-disclosure**, not a
   silent drop (DNA).
5. **Optional: a learned questionable-venue down-weight** (sovereign re-implementation of the Science
   Advances feature recipe over OpenAlex bibliometrics + the DOAJ gold labels). Down-weight only; honest
   about the ≤~0.38 recall ceiling. Never a gate.

### DO NOT add
- **Any hardwired single external rater as ground truth** (NewsGuard / MBFC / DOAJ / a single LLM judge).
  Capture + political-skew risk is measured (arXiv 2502.04426 right-lean misclassification; the 2025 FTC
  demands on NewsGuard/Ad-Fontes). Multi-signal, self-computed, verifier-overridable — per §-1.3.
- **Any hard-drop credibility classifier.** Violates weight-not-filter. A questionable/unreliable verdict
  is a LOW WEIGHT, not a removal. The only quasi-exclusion (retracted) is re-framed as lowest-weight +
  disclosure.
- **Body-text-based authority scoring as the primary signal.** AuthorityBench: page text *degrades*
  authority judgment. Keep authority on metadata/graph signals; the body feeds junk-detection only.
- **CC-BY-NC / closed components in the sovereign binary** — Science Advances questionable-venue model
  (CC-BY-NC), NewsGuard/MBFC APIs (proprietary). Yardstick / feature-recipe inspiration only.

---

## 7. The bake-off candidate list (the next step)

Open-source-first (sovereignty). Behavioral acceptance on the §5 gold sets; no candidate crowned on a
vendor number. Every candidate flows weight-not-filter — fail loud if any drops a row.

**Authority/credibility scorer (the weight):**
- `authority_model.py` 5-signal data-driven model (incumbent successor, default-OFF) — the model to wire
- AuthorityBench LLM-judge (ListJudge/PairJudge, metadata-only) on sovereign GLM/DeepSeek — arXiv
  2603.25092, open; the learned head
- Rules path (`tier_classifier.py`) — the explainable backstop / regression oracle (KEEP, not replaced)

**Venue prestige prior (joins, not models):**
- OpenAlex venue + SJR (ISSN-L join, 90.0% coverage) + CORE rank — standard providers
- DOAJ membership as a binary OA-legitimacy signal (one signal, not an oracle)

**Questionable-venue down-weight (CC-BY-NC → re-implement, don't vendor):**
- Science Advances 2025 feature recipe (bibliometrics + design + content) over OpenAlex — yardstick +
  re-implementable; DOAJ 12,869/2,536 gold labels

**Clinical study-type / publication-type tagger (replace the regexes):**
- PubMedBERT publication-type + study-design multi-label tagger (medRxiv 2025, 1.2M corpus) — verify weight license
- StudyTypeTeller LLM (PMC12657658, 14 study types) — contender on the sovereign slate

**Retraction / integrity:**
- Crossref REST + Retraction Watch CSV (`gitlab.com/crossref/retraction-watch-data`) unioned with OpenAlex
  `is_retracted` — close the arXiv-2403.13339 OpenAlex blind spot

**News/web domain credibility (down-weight overlay):**
- CRED-1 (CC-BY-4.0, offline) + a sovereign LLM judge (arXiv 2502.04426 recipe) — never NewsGuard/MBFC live

**Independence/echo authority (cross-ref consolidation):**
- Signal D corroboration (`corroboration.py`) → PageRank/RAGRank canonical-origin authority — the input to
  the consolidation section's independence-collapse; not re-baked-off here

---

## 8. Honest uncertainty + license flags

### Uncertainty
- **Benchmark numbers are not cross-comparable.** AuthorityBench correlation, the Science-Advances PRC-AUC
  0.79, the news-domain F1 0.86, and the clinical tagger F1s use different gold sets and metrics. None is a
  head-to-head on POLARIS rows — hence the §5 in-house gold-set bake-off is mandatory before any adoption.
- **The "flip the authority model on" recommendation needs the §5 proof first.** It is shadow-only for a
  reason (no downstream consumer validated it). Do not wire it to a gate until the per-tier P/R proof lands
  — that is the behavioral-acceptance discipline (§-1.4), not a paper claim.
- **Questionable-venue detection is genuinely immature** — recall ≤~0.38 at useful precision (Science
  Advances 2025). Treat as a low-confidence down-weight, never a gate.
- **LLM credibility judges carry measured political skew** (right-lean misclassification, arXiv 2502.04426).
  Any LLM-judge addition must be skew-audited and ensembled, never a single oracle.
- **OpenAlex freemium shift (Feb 2026):** an API key is now required at volume. Verify the run env carries
  a key, else the authority model's OpenAlex signals silently thin (a fail-loud check is warranted).
- **Emerging code-first venue-credibility trend (forward-looking, not adoptable).** "Review the Code, Not
  the Story: A Vision and Protocol for Code-First Peer Review" (Chen, arXiv 2606.07683, **2026-06-03**,
  https://arxiv.org/abs/2606.07683) proposes shifting peer-review credibility from author-controlled
  manuscripts to **venue-controlled execution of code + minimal claim manifests** (reproducibility layer,
  code-audit layer, credibility safeguards). It is explicitly a **vision/protocol paper, no released
  implementation** (license: arXiv non-exclusive) → not a candidate, but it signals that *venue credibility
  is starting to move from text/metadata authority toward reproducibility/code-audit signals.* It
  reinforces the doc's "never hardwire a single external rater as ground truth" principle (§6 DO NOT add):
  a future credibility weight may incorporate a reproducibility signal, but that is over the horizon and
  out of scope for the current metadata/graph-based authority weight. Watch-only.

### License flags — verify before adoption
- **AuthorityBench** (arXiv 2603.25092): code+benchmark "available," arXiv nonexclusive-distrib license —
  confirm the repo's actual code license before vendoring; the *benchmark data* is usable as a gold set
  regardless.
- **Science Advances questionable-venue model** (`sciadv.adt2792`): **CC-BY-NC**, no released repo →
  **yardstick / feature-recipe inspiration only**, re-implement sovereignly. Do not vendor.
- **NewsGuard / MBFC**: proprietary closed APIs → avoid in the sovereign binary. **CRED-1 (CC-BY-4.0,
  offline)** is the open down-weight substitute.
- **DOAJ**: open metadata (CC-BY) but sponsor-funded → one signal, never hardwired ground truth.
- **PubMedBERT publication-type tagger** (medRxiv 2025): base PubMedBERT is MIT; **fine-tuned-weight /
  dataset release license under-specified** — verify before deploy.
- **StudyTypeTeller** (PMC12657658): generative-LLM method; confirm any released model/data license.
- **GRT/IRGT/SWGRT trial-design classifier** (JMIR Med Inform 2025, e63267): paper **CC-BY-4.0** open-access
  (clean to reference); confirm any released BioMedBERT fine-tune weights/data repo license before deploy.
- **RAGRank** (arXiv 2510.20768): paper **CC-BY-SA-4.0**; **no public code repo found** → PageRank pattern
  is re-implementable sovereignly over the OpenAlex citation graph; verify any later-released repo license.
- **Authority Signals in AI Cited Health Sources** (arXiv 2601.17109): **CC-BY-4.0**; materials on Zenodo —
  descriptive framework (no scorer model), so axis-definition / gold-label inspiration only.
- **Code-first peer review** (arXiv 2606.07683): arXiv non-exclusive license; **vision paper, no code** —
  watch-only trend, not adoptable.
- **Retraction Watch / Crossref** CSV: open (CC-BY) — clean to vendor.
- **crowd-kit** (Apache-2.0), **scikit-learn** (BSD-3): clean if a learned head needs a reliability/agg
  backbone (cross-ref consolidation §5).
- **Clean + sovereign-OK to build on:** OpenAlex (CC0), Crossref (open), ROR (CC0), PSL (MPL-2.0), the
  in-tree `authority_model.py` + rules path.

### Verified-current POLARIS files
`src/polaris_graph/retrieval/tier_classifier.py`, `src/polaris_graph/authority/authority_model.py`,
`authority/citation_graph.py`, `authority/institutional.py`, `authority/junk_detection.py`,
`authority/corroboration.py`, `authority/recency.py`, `authority/source_class.py`,
`authority/data_loader.py`, `authority/supersession.py`, `retrieval/evidence_selector.py`,
`retrieval/source_registry.py`, `nodes/journal_only_filter.py`,
`docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md` (Codex APPROVE iter-5),
`docs/frontier_credibility_intelligence_2026_06_07.md`.

---

## 9. Recency audit (2026-06-24) — is this 2025/2026 frontier, or did old methods sneak in?

Per the FRONTIER-TECH MANDATE: explicit "is anything NEWER?" re-check at research time; reject pre-2024
unless it is the genuine incumbent floor. Every candidate above was date-checked against its primary
source during this research (not from training memory).

**Verdict: frontier-current.** The *methods* are all 2025/2026 and primary-source-dated:

| Candidate | Date | Primary source | Frontier? |
|---|---|---|---|
| AuthorityBench | 2026-03-26 | arXiv 2603.25092 | Genuine 2026 frontier — the headline yardstick |
| Questionable-venue ML scorer | 2025-08 | Science Advances `sciadv.adt2792` | Genuine 2025 frontier (CC-BY-NC, re-implement) |
| LLM domain-credibility judge | 2025 | arXiv 2502.04426 | Genuine 2025 frontier |
| PubMedBERT pub-type tagger | 2025-03/04 | medRxiv 2025.03.06.25323516 | Genuine 2025 frontier (clinical slice) |
| StudyTypeTeller | 2025 | PMC12657658 | Genuine 2025 frontier |
| GRT/IRGT/SWGRT trial-design classifier | 2025-05-09 | JMIR Med Inform e63267 | Genuine 2025 frontier (clinical slice, §4.4) — CC-BY-4.0 |
| RAGRank (PageRank anti-poisoning authority) | 2025-10-23 | arXiv 2510.20768 | Genuine 2025 frontier (§4.5) — CC-BY-SA-4.0, no repo |
| Authority Signals in AI Cited Health Sources | 2026-01-23 | arXiv 2601.17109 | Genuine 2026 frontier (§4.6 clinical authority axis) — CC-BY-4.0 |
| Code-first peer review (vision) | 2026-06-03 | arXiv 2606.07683 | Genuine 2026 frontier TREND (§8 watch-only, no code) |
| OpenAlex `is_retracted` blind-spot study | 2024 (rev) | arXiv 2403.13339 | Recent; the data finding still holds 2026 |

**The signal-source providers (NOT crowned as "methods," correctly classified as classic-but-still-SOTA),
web-verified still-current:** OpenAlex / Crossref / Retraction-Watch / SJR / CORE / DOAJ are the standard
2025/2026 providers (Retraction Watch merged into Crossref's *production* schema Jan 2025; OpenAlex+SJR
ISSN-L join is the documented 2025 method) — they are corpus-ACCESS APIs the learned scorers layer on top
of, exactly as PubMed/arXiv are in the retrieval section. Crowning any of them as "the frontier method"
would be the dated-crown error; rejecting them as "pre-2024" would be the opposite error. Both avoided.

**The genuinely-dated thing in this section is POLARIS's OWN live path** — the 22-frozenset hardcoded host
treadmill and the hand-rolled title regexes. That is the floor we are replacing, not a candidate we are
recommending. The data-driven `authority_model.py` already exists as the successor; the frontier work is
finishing the wire-up and adding the learned head + the clinical study-type tagger.

**What a re-check surfaced as adjacent (fold into the bake-off, lower materiality):**
- **SciPred** (SciBERT predatory-journal classifier) and the AJPC blacklist/whitelist system — pre-2024
  lineage, superseded by the Science-Advances 2025 DOAJ-operationalized scorer; reference only.
- **Kai-Cheng Yang & Menczer (2025)** LLM news-credibility-rating accuracy+bias study — corroborates the
  arXiv 2502.04426 skew finding; second independent confirmation that LLM judges need skew-audit.
- **Wikipedia source-reliability / WP:RSP** as a crowd-curated domain-credibility label source — an open,
  non-captured alternative label set worth adding to the §5 gold mix.

**Recency-COMPLETE as of 2026-06-24 (ref I-recency-001 #1296).** A completeness-critic re-scan surfaced four
2025/2026 candidates missing from the first pass; all four were primary-source-verified (date + URL +
license) and inserted:
1. **RAGRank** (arXiv 2510.20768, 2025-10-23, CC-BY-SA-4.0, no repo) → §4.5 as the named citation-graph /
   PageRank anti-poisoning authority candidate (previously under-specified as "RAGRank lineage").
2. **GRT/IRGT/SWGRT trial-design classifier** (JMIR Med Inform e63267, 2025-05-09, CC-BY-4.0) → §4.4 + §5
   as the third clinical-tagger candidate, adding cluster-randomization structure beyond publication-type.
3. **Authority Signals in AI Cited Health Sources** (arXiv 2601.17109, 2026-01-23, CC-BY-4.0) → new §4.6 +
   §5 clinical slice as the domain-specific clinical health-source authority axis.
4. **Code-first peer review** (arXiv 2606.07683, 2026-06-03, vision paper, no code) → §8 as a watch-only
   venue-credibility trend (reproducibility/code-audit), reinforcing the §6 "no single hardwired rater".

No gap candidate was rejected — all four cleared the frontier-tech mandate (2025/2026, primary-verified,
genuinely relevant; licenses range CC-BY-4.0/CC-BY-SA-4.0 OSS-referenceable to vision-paper watch-only).

---

## 10. Primary sources (2025/2026)
- AuthorityBench — arXiv 2603.25092 (2026-03-26), https://arxiv.org/abs/2603.25092 — labeled
  domain/entity authority gold set + LLM-as-authority-judge; "authority distinct from textual style"
- Estimating the predictability of questionable open-access journals — Science Advances 2025-08,
  https://www.science.org/doi/10.1126/sciadv.adt2792 / PMC12383260 — DOAJ-operationalized ML scorer,
  PRC-AUC 0.79, CC-BY-NC
- Decoding AI Judgment: How LLMs Assess News Credibility and Bias — arXiv 2502.04426 (2025),
  https://arxiv.org/html/2502.04426v2 — LLM domain-credibility judges vs NewsGuard/MBFC, political skew
- Publication-Type Tagging using Transformer Models — medRxiv 2025.03.06.25323516,
  https://www.medrxiv.org/content/10.1101/2025.03.06.25323516.full.pdf — PubMedBERT 1.2M-article tagger
- StudyTypeTeller — PMC12657658 (2025) — LLM study-type classifier, 14 study types
- GRT/IRGT/SWGRT trial-design classifier — Aghaarabi & Murray, JMIR Med Inform 2025 (2025-05-09),
  https://medinform.jmir.org/2025/1/e63267 — fine-tuned BioMedBERT for cluster-randomization trial designs;
  CC-BY-4.0
- RAGRank: PageRank to counter poisoning in CTI RAG pipelines — arXiv 2510.20768 (2025-10-23),
  https://arxiv.org/abs/2510.20768 — PageRank source-credibility over the citation graph; CC-BY-SA-4.0,
  no code repo found
- Authority Signals in AI Cited Health Sources — arXiv 2601.17109 (2026-01-23),
  https://arxiv.org/abs/2601.17109 — four-domain clinical health-source authority framework; CC-BY-4.0
- Review the Code, Not the Story (code-first peer review, vision) — arXiv 2606.07683 (2026-06-03),
  https://arxiv.org/abs/2606.07683 — venue-controlled reproducibility/code-audit credibility trend; vision
  paper, no code (watch-only)
- (Non-)retracted papers in OpenAlex — arXiv 2403.13339 — OpenAlex `is_retracted` incompleteness vs
  Retraction Watch
- Retraction Watch in the Crossref API (production schema Jan 2025) —
  https://www.crossref.org/documentation/retrieve-metadata/retraction-watch/ ;
  CSV mirror https://gitlab.com/crossref/retraction-watch-data
- OpenAlex × SJR ISSN-L join (90.0% coverage) — OpenAlex developer docs https://developers.openalex.org/
- POLARIS prior art (June 2026): `docs/frontier_credibility_intelligence_2026_06_07.md`,
  `docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md` (Codex APPROVE iter-5)
