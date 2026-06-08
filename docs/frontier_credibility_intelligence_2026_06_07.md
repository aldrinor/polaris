# FRONTIER INTELLIGENCE: Credibility-Weighted, Both-Sides Deep Research
### State of the art on source diversity, per-source credibility weighting, weighted synthesis, contested-topic handling, echo-chamber detection, and per-claim disclosure — with the POLARIS lead opportunity

---

## 1. Executive Summary — the honest state of the art

There is no deployed system today that does credibility-weighted, both-sides deep research well. The frontier products (OpenAI/Gemini/Perplexity Deep Research) are agentic and broad but treat credibility as prose narration or a clickable link list — never a disclosed weight. The scientific-evidence tools (Elicit, Consensus, scite, Semantic Scholar, Exa, STORM) mostly manufacture "credibility" by **restricting the corpus to peer-reviewed papers** — which is precisely the journal-only filter POLARIS is abandoning — and the ones that touch the open web (Exa, STORM) handle credibility badly. The formal evidence-synthesis frameworks (GRADE, GRADE-CERQual, Cochrane/Campbell, EFSA/OHAT weight-of-evidence, the Maryland SMS) get the *methodology* right — weight, never count — but assume trained human reviewers and curated studies, not an automated pipeline ingesting the whole web. And the credibility-aware RAG literature (RA-RAG, CAG, RAGRank) has working weighted-aggregation algorithms but keeps the weights internal and, critically, mostly **assumes source independence** — the one thing the contested hard case breaks.

Five honest findings frame everything:

1. **None of the three frontier DR products publishes a numeric per-source credibility weight, a per-claim evidence-strength score, or any echo-chamber / source-independence detection.** OpenAI narrates credibility in prose; Gemini and Perplexity give you a link list. That absence is not a gap to paper over — it is the differentiation space for POLARIS's per-sentence, span-bound provenance.

2. **Citation VISIBILITY is inversely related to citation VALIDITY in the current market.** Perplexity is the most citation-forward product yet, per DeepTRACE, grounds almost nothing: 97.5% of its statements are not fully supported by its own listed sources, and 94.5% of the sources it lists are not even needed (source necessity 5.5%). Visible citation chips without span-level verification are theater.

3. **On contested topics all three frontier systems FALSE-CONVERGE to one-sidedness, not false-balance.** They pick a side and under-support it (one-sidedness 54.7%–80.1% across DR agents). None has a published weight-and-disclose policy for the vaccine hard case.

4. **The "credibility" of the evidence tools is mostly corpus restriction.** Their per-claim signal *mechanics* are transferable (scite's support/contrast classification, Elicit's span-linked extraction, GRADE's certainty label); their corpus-restriction *strategy* is exactly what POLARIS rejects and must not inherit.

5. **Source independence / echo-chamber detection is the single hardest unsolved problem** — and it is detectable. Content-copying network features alone hit ~0.80–0.84 accuracy at spotting unreliable sources and catch exactly the echo-chamber cases that text models miss. RA-RAG, the best 2025 weighted-aggregation method, explicitly assumes independence and breaks when many sources copy one claim. This is the vaccine-volume hard case, and it is POLARIS's clearest place to lead.

The through-line: **quality is WEIGHT, not COUNT, and the weight must (a) actually drive synthesis, (b) discount non-independent corroboration, and (c) be disclosed per claim.** No deployed system does all three. POLARIS's existing per-sentence `[#ev:id:start-end]` provenance + `strict_verify` is the right substrate; the missing layers are a disclosed credibility prior, an independence/echo-chamber collapse, and a per-claim weight-and-disclose UX.

A methodological caution that the report itself observes: one widely-circulated "Perplexity 37% citation-hallucination" figure does **not** trace to either primary hallucination paper and is excluded. A hallucinated statistic inside a report about citation hallucination would be self-refuting.

---

## 2. Per-Issue Findings

Each issue below covers the seven POLARIS dimensions: (a) source diversity vs filtering, (b) per-source credibility weighting + signals, (c) composition/synthesis weighted by credibility, (d) contested-topic both-sides handling (the vax case), (e) volume-vs-weight + source-independence/echo-chamber detection, (f) per-claim credibility disclosure. For each, what the frontier DOES, the SOTA best practice, and the OUTCOME (how well, known failures).

---

### ISSUE 1 — Frontier closed/agentic Deep Research products (OpenAI, Gemini, Perplexity)

**(a) Source diversity vs filtering.** All three are breadth-first open-web agents with no categorical source-type filter by default. OpenAI uniquely adds an *opt-in* trusted-sites allowlist plus authenticated/paid connectors (FactSet, PitchBook, Drive/SharePoint) as of Feb 2026. Gemini defaults to Google Search + optional Workspace content and markets reach to "academic journals, government databases, reputable news" — but "reputable" is marketing framing, not a documented filter. Perplexity is open-web agentic RAG. **Diversity is high; filtering is essentially absent or user-manual.** This validates POLARIS's all-source-type direction — but none of them adds a credibility layer on top of the breadth.

**(b) Per-source credibility weighting.** *No published numeric weight in any of the three.* OpenAI's marketing claim that the agent "actively evaluates the credibility of sources" and "explains why each source was chosen" resolves on inspection to **prose narration in the reasoning trace** — not a score, not a signal set, not an auditable weight. The only real OpenAI lever is the manual allowlist. Gemini's own docs are silent on credibility weighting (confirmed by fetch); the Sources panel is a manual visual scan. Perplexity markets "credibility as the primary filter" but every concrete description (five-stage gauntlet, L1–L3 rerankers) is **third-party SEO/GEO blog reverse-engineering, not vendor documentation** — and Perplexity's official Deep Research blog was 403 during research, so its internals could not be primary-verified. **SOTA best practice here is, frankly, the absence — there is no frontier best practice to copy.**

**(c) Composition weighted by credibility.** Not documented by any of the three. Inferred behavior from ReportBench: OpenAI DR does heavy citation *post-processing* — 88.2 vs 16.16 cited statements per query vs the bare o3 model, and the highest citation precision (~0.385 vs Gemini ~0.145). So composition optimizes for **citation density and coverage, not credibility-weighted synthesis.** Gemini "generates excessive citations without proportional improvement in coverage" — volume-heavy, not weight-disciplined.

**(d) Contested-topic / the vax case.** **All three FALSE-CONVERGE to one-sidedness, not false-balance.** DeepTRACE one-sidedness on debate queries: GPT-5(DR) 54.67% (best/lowest, yet still a majority), Perplexity(DR) 63.1%, Gemini(DR) 80.1% (second-worst). None has a documented weight-and-disclose policy for the vaccine-vs-antivaccine more-sources-but-lower-credibility case. Behavior is emergent from model training, not a transparent both-sides policy. **The failure mode is silent side-picking + under-support, which is arguably more dangerous than naive 50/50 because it is invisible.**

**(e) Volume-vs-weight + independence.** No volume-vs-weight distinction and **zero echo-chamber / source-independence detection** in any of the three. DeepTRACE source necessity (fraction of listed sources actually used to support statements): OpenAI 87.5% (good citation hygiene), Gemini 33.1%, **Perplexity 5.5%** — i.e., ~94% of Perplexity's links are decorative. DeepTRACE's structural finding: "more citations per query do not mean fewer errors per citation," and DR agents "that list many links often leave them uncited." None detects many sites copying one origin claim.

**(f) Per-claim credibility disclosure.** All three provide inline per-claim citations (click-through to source). **None shows per-claim evidence strength or source-quality score, and none shows whether the cited span actually supports the claim** — verification is left to the reader. Perplexity's numbered chips are the signature UX yet are "largely decorative given the 97.5% unsupported-statement rate."

**OUTCOME / known failures (empirical, primary-sourced):**
- ReportBench citation-MATCH rate (does cited content semantically support the statement): OpenAI DR **78.87%** (best), Gemini DR **72.94%** — even the best leaves ~1 in 5 cited statements unsupported.
- DeepTRACE: OpenAI unsupported 12.5% / citation-acc 79.1% (best); Gemini unsupported 53.6% / citation-acc 50.3% (worst DR); **Perplexity unsupported 97.5%** (worst of ALL systems) / citation-acc 58.0%.
- URL fabrication ("Detecting and Correcting Reference Hallucinations," arXiv 2604.03173, DRBench): **Gemini 13.3%** (highest measured) vs OpenAI 3.5% vs Claude ~3%.
- Content-misrepresentation ("Cited but Not Verified," arXiv 2605.06635): frontier models keep >94% working links and >80% topical relevance but only **39–77% fact-check accuracy** — live, real, on-topic URLs that misrepresent their content. This is the more dangerous failure mode.
- **Search-depth degradation:** GPT-5.4 fact-check accuracy collapsed **79% → 17% as tool calls scaled 2 → 150**, while link validity stayed >92%. Deeper agentic research produced MORE misrepresentation, masked by surface metrics.

**Relevance to POLARIS:** OpenAI DR is the closest competitor on citation hygiene and the system to beat on faithfulness. Its "explains why each source was chosen" is prose, not an auditable weight — exactly what POLARIS's disclosed credibility prior + span-bound provenance token out-rigors. The 21% unsupported-citation rate and the 79%→17% degradation curve are the concrete failure modes `strict_verify` (numeric match + content-word span overlap) is built to catch. **Perplexity is the strongest single argument FOR the POLARIS thesis:** most citation-visible product, grounds almost nothing — proof that visible citations without span verification are theater.

---

### ISSUE 2 — Scientific-evidence tools (Elicit, Consensus, scite, Semantic Scholar, Exa, STORM)

Three cross-cutting findings frame this entire issue and must not be lost:

- **SPLIT mechanics from corpus strategy.** With one exception (Exa), every tool here manufactures credibility by *restricting the corpus* to academic/peer-reviewed papers (OpenAlex, Semantic Scholar, ~125–280M scholarly works). That corpus restriction IS the journal-only filter POLARIS is abandoning. Adopt the **claim-support mechanics**; reject the **corpus-restriction strategy**.
- **None solves the vax hard case — they AVOID it by construction.** Anti-vax/forum/commercial content is simply not in their academic corpus, so the weak-side-has-more-sources problem never arises. POLARIS, ingesting all source types, cannot inherit this avoidance and must build the machinery these tools never needed.
- **Most "consensus"/"support" signals here are VOTE-COUNTING and are themselves echo-chamber-vulnerable.** A popular-but-wrong paper accrues "supporting" citations; a widely-repeated claim scores high regardless of independence. None detects source independence. This is a transferable *warning*, not a feature to copy.

**(a) Source diversity vs filtering.** scite (~280M scholarly works, ~1.4B citation statements), Consensus (OpenAlex + Semantic Scholar ~150–200M), Elicit (~125M+), Semantic Scholar (~200M papers / 2.4B citation links) are all corpus-restricted to academia. **Exa is THE exception** — a general neural web-search engine over tens of billions of pages, explicitly not SEO-influenced (paid per query), the closest model to POLARIS's all-source ingestion. STORM is open-web but *outsources* credibility to an upstream search engine (You.com/Bing "trusted sources") and never evaluates trust itself.

**(b) Per-source credibility weighting + signals — what's transferable:**
- **scite (HIGH transferable):** Does NOT assign a source credibility weight; its signal is orthogonal and more interesting — per-citation-STATEMENT intent classification (supporting / contrasting-disputing / mentioning) via a SciBERT classifier with a confidence %, plus retraction/editorial-notice flags. "Credibility" here = *downstream reception* (how later papers treated the claim), span-anchored and disclosed.
- **Consensus (MEDIUM):** Surfaces study-design tags (RCT/meta-analysis/SR, LLM-extracted), journal-rank percentiles (SJR/SciScore), citation count, year — and these ARE disclosed as chips. **But the weighting formula is opaque and, critically, these signals do NOT feed the headline Consensus Meter.**
- **Elicit (HIGH):** No global weight; user-defined extraction columns (design, n, effect size, funding) turn quality into inspectable cells, each hyperlinked to the exact source passage.
- **Semantic Scholar (MEDIUM-HIGH as infrastructure):** "influentialCitationCount" from a 4-class classifier (highly-influential / background / method / results) — a quality-weighted alternative to raw count, but biased toward already-highly-cited papers. Influence ≠ correctness.
- **Exa (LOW as credibility model):** Internal LLM-grader "result_quality = authority/accuracy/trustworthiness," used to tune ranking but **never surfaced to the user.**

**(c) Composition weighted by credibility.** Mostly vote-counting. Consensus classifies the top 5–20 results into Yes/No/Possibly/Mixed and visualizes the distribution — quality tags shown alongside but **do not re-weight the tally.** scite aggregates N-supporting vs N-contrasting counts. Elicit composes a span-hyperlinked matrix (no auto prominence-by-credibility). STORM synthesizes by *perspective coverage*, not credibility weight — the most synthesis-heavy tool and the one whose credibility handling is weakest.

**(d) Contested-topic / vax case.** Uniformly avoided-by-construction (academic corpus). scite is best-in-slice at *surfacing* disagreement (a contrasting citation = "someone refuted this") but does not adjudicate or weight it. **Consensus is weakest-by-design** — its own guardrails doc states: *"Research quality is not part of the analysis — currently, each claim counts the same on the roll-up interface regardless if it comes from a meta-analysis or an n = 1 case report."* On open-web inputs, STORM's perspective-balancing-without-weighting is **a recipe for false balance** — "source bias transfer" is a named, unsolved STORM failure.

**(e) Volume-vs-weight + independence.** **This is the dominant anti-pattern across the slice.** Consensus explicitly conflates volume with weight ("a small study n=50 counts the same as n=5,000"). scite partitions citations into support/contrast (better than raw count) but the tallies are still counts, echo-chamber-vulnerable. Semantic Scholar's influence ≈ citation count, biased toward the prominent. **None of the six detects source independence.** Exa, being embedding-relevance-based, can actively *amplify* echo chambers (near-duplicate pages all match well).

**(f) Per-claim disclosure.** scite (citation-statement intent + confidence + surrounding span) and Elicit (every extracted cell hyperlinked to the exact passage) are the **two most POLARIS-aligned features in the slice** — claim → span, inspectable. Both disclose the source location/intent, neither discloses a quality *score* per claim.

**OUTCOME / known failures:**
- **scite:** Own QSS/MIT paper: disputing/contrasting F-score 58.97%, precision 85.19%, all production classes precision >80% (precision-favoring). **Independent eval (Hsiao & Schneider, n=98): F-measures 0.0–0.58 and systematic COLLAPSE of supporting AND contrasting into "mentioning"** (labeled 2 supporting / 96 mentioning where humans found 42 / 39 / 17). The rare-but-critical "contrasting" class is the hardest and least reliable — high precision, low recall. **In clinical use a missed "contrasting" = a silently-unchallenged claim.**
- **Consensus:** Publication-bias blindness, journal-quality fallacy, biomedicine-tuned SciScore travels poorly, non-reproducible rankings, heterogeneity blindness. Vote-counting is the core indictment (Tay 2025).
- **Elicit:** ~81.4% extraction accuracy (vs 86.7% human, n.s.); high-accuracy mode ~91%. **~6% hallucinations — fabricated control groups, invented participant counts, numbers fabricated when the true value was absent.** Crucially, **when Elicit and a human AGREED, the value was correct 100% of the time** (agreement = validity proxy).
- **STORM:** Vendor Co-STORM "~99% factual" vs peer-reviewed STORM **~85% citation precision/recall** — a marketing-vs-eval gap that is itself a credibility signal. Named open problems: source-bias transfer, over-speculation, non-neutral tone.
- **Semantic Scholar:** Influence classifier biased toward highly-cited papers; impact is multi-dimensional; no single refined measure exists.

**Relevance to POLARIS:** Adopt the mechanics — scite's span-anchored support/contrast intent, scite's retraction flag as a *hard* penalty, Elicit's span-hyperlinked extraction + agreement-as-validity (supports multi-voter architecture), Consensus's disclosed quality chips. Reject the corpus restriction. Encode two warnings: **(1) favor RECALL on the refutes/contrasting class** (opposite of scite's precision-favoring tune — a missed refutation is the lethal error); **(2) DISCLOSED-BUT-NOT-WEIGHTED is the trap** (Consensus shows quality chips but excludes them from the verdict). The POLARIS weight must FEED composition and the user must see THAT it did.

---

### ISSUE 3 — Source-credibility scoring orgs + credibility-aware RAG + independence detection (NewsGuard, MBFC, Ad Fontes, RA-RAG, CAG, RAGRank, content-sharing networks, Community Notes, weight-of-evidence/MEDRS)

This issue holds the actual building blocks for POLARIS's contested-topic redesign, organized as a layered pipeline.

**(a) Source diversity vs filtering.** The three rating orgs are *source-level priors*, not searchers — they rate websites/publishers, not claims. The RAG methods (RA-RAG, CAG, RAGRank) search broadly and down-rank/tag rather than journal-filter. Community Notes operates on individual posts. The weight-of-evidence frameworks (WP:MEDRS, denialism literature) are normative editorial rules.

**(b) Per-source credibility weighting + signals:**
- **NewsGuard:** 0–100 per-source score from **nine weighted, disclosed, PRACTICE-based criteria** (does not repeatedly publish false content 22 pts, gathers responsibly 18, corrects errors 12.5, separates news/opinion 12.5, deceptive headlines 10; transparency cluster ~35.5). Signals are journalistic practice, NOT impact factor — fully auditable. Good model for a *decomposed, disclosed* prior.
- **MBFC:** 10-point scale, Factual-Reporting-first then Bias then Traffic/Longevity. **Letting Traffic leak into the score is the wrong direction** — popularity contaminating evidential weight.
- **Ad Fontes:** Reliability (Veracity + Expression + Headline) and Bias, scored by a **politically-balanced 3-person pod (one left, one center, one right)** — reduces single-rater skew *by construction.* The most transferable idea for contested-topic handling.
- **RA-RAG (the weighted-aggregation blueprint):** Estimates per-source reliability **without labels** via Dawid-Skene/EM cross-source agreement, then **Weighted Majority Voting** — the answer with the most reliability-weight wins, so a few high-credibility sources override a larger low-credibility bloc. Estimated reliabilities correlated with ground truth at PCC 0.991 / SRCC 0.992.
- **CAG ("Not All Contexts Are Equal"):** Attaches credibility tags (high/med/low) to each context and **fine-tunes the synthesizer to weight by them** — because off-the-shelf LLMs show "limited sensitivity to credibility" when merely prompted. Survives ~80% noise (~91.7% accuracy vs baselines ~78%).
- **RAGRank:** PageRank-style trust propagation over a citation graph — **an independence-aware prior.** A source cited 100× by one origin scores LOWER than one cited 10× by 10 distinct origins. Detects closed loops and single-origin clusters.

**(c) Composition weighted by credibility.** RA-RAG's Weighted Majority Voting and CAG's credibility-deference are the two cleanest operationalizations of "credibility governs which claim wins a conflict." RAGRank filters low-trust sources pre-retrieval. The rating orgs are external priors consumed downstream.

**(d) Contested-topic / vax case — the actual playbook lives here:**
- **Community Notes bridging:** Surfaces a note ONLY if raters who *usually disagree* both rate it helpful — explicitly NOT majority rule. **The cleanest deployed answer to "avoid both false balance AND censorship":** a minority-but-correct correction can surface if it earns cross-viewpoint assent; a high-volume one-sided pile-on does not surface for being numerous. Honest failure mode: **it ABSTAINS** (<12.5% of submitted notes ever display) rather than mislabel.
- **Weight-of-evidence + WP:MEDRS:** Tier claim weight by evidence/source quality (consensus > significant minority > fringe); **a large public following does NOT upgrade a fringe medical claim.** Three operationalizations: weight-of-evidence (proportional emphasis), outnumbering (more consensus voices), forewarning/inoculation (warn about the false-balance effect before exposure).
- **The empirical kicker (PMC7528676, N=887, 3 experiments — single study line, treat as that study's finding):** OUTNUMBERING (even 5:1 consensus:deniers) showed **NO significant protective effect** on vaccine attitudes; **FOREWARNING consistently DID** reduce denialism's impact (attitude p=.006, intention p<.001, confidence p=.001). **Implication: piling up more consensus citations does not move minds — labeling/forewarning the false-balance trap does.** This makes per-claim *disclosure* not merely transparency but the empirically-supported anti-false-balance mechanism — POLARIS's exact strength.

**(e) Volume-vs-weight + independence — the load-bearing layer:**
- **RA-RAG's load-bearing blind spot (verified at full-text after a fast-model summary claimed the opposite):** RA-RAG **ASSUMES SOURCE INDEPENDENCE.** Its adversary-robustness results assume adversaries act independently; **a coordinated bloc of copies is counted as many independent reliable-looking votes and can win the weighted vote.** This is precisely the vaccine-volume hard case.
- **RAGRank fills it:** PageRank weights independence, not frequency — echo loops do not accumulate independent trust. (Caveat: PageRank-popularity can drift toward "establishment = trusted" and bury a well-evidenced minority — must be paired with a claim-level verifier.)
- **Content-Sharing Veracity Networks ("Tell Me Who Your Friends Are," arXiv 2101.10973) — the strongest concrete numbers:** detect unreliable sources from *copying behavior alone.* Build a directed graph (near-verbatim copies, TF-IDF cosine ≥0.85 within 5-day windows, directed by timestamp). **Network features ALONE beat text-only models: Node2Vec 0.802 accuracy (F1 0.813) vs NELA text 0.689; combined FastText+Node2Vec 0.836 (F1 0.820), up to +14.7%.** And they excel exactly where text fails: text models make 68% of their errors on unreliable sources, the network models only 37%. Temporally stable (0.75→0.70 over 10 months vs text 0.61→0.50).
- **Wikipedia circular-reporting / WP:Independent-sources doctrine** = the cleanest statement of the COUNTING rule: syndicated copies of one wire story count as ONE source; collapse apparently-independent sources that trace to a single origin **before tallying support.**

**(f) Per-claim disclosure.** The entire rating-org industry is **source-level, not per-claim** — NewsGuard says so explicitly ("rates entire websites, not individual articles or claims"). RA-RAG and CAG keep weights internal (CAG's annotations stay in the *input*; the answer never surfaces which sources it prioritized). Community Notes is the closest to claim-level (per-post note + sources) but discloses a status, not a graded weight. **Per-claim credibility disclosure is essentially unsolved across this entire issue — confirming it is POLARIS's whitespace.**

**OUTCOME / known failures:**
- **RA-RAG:** Holds 0.558 accuracy under 7 adversaries + 2 reliable sources where plain majority voting collapses to 0.327 and vanilla RAG to 0.294 — survives the vax-shaped adversarial mix *as long as sources are independent.* Fails in homogeneous/correlated environments (acknowledged). Reliability is global-per-source, not per-domain.
- **AuthorityBench (arXiv 2603.25092):** Independently shows current LLMs suffer **"volume vulnerability"** (adopt consistent-but-false claims from many low-credibility sources over few high-credibility) and **"credibility ignorance"** (treat all sources as equal) — a measured, labeled benchmark of exactly the failure POLARIS must beat.
- **Community Notes:** PNAS 2025 + X A/B test show 25–34% reduction in misinformation spread *when notes display* — but <12.5% display, so the hardest posts stay unlabeled (abstain, not mislabel).
- **Rating orgs — capture risk:** NewsGuard and Ad Fontes both drew 2025 FTC civil-investigative demands and "censorship cartel" accusations (NewsGuard probe closed April 2026). **A single opaque human-rated allowlist is a political-capture and single-point-of-failure risk** — do not hardwire one vendor's verdict as ground truth.

**Relevance to POLARIS:** This issue gives the four-layer recipe for the vax case (see §4). The headline: **RA-RAG is the best weighted-aggregation blueprint but has a fatal independence blind spot; the content-copying network + RAGRank + Wikipedia counting doctrine are the antidote; Community Notes bridging + Ad Fontes balanced panels are the cross-viewpoint analog; weight-of-evidence/MEDRS + the forewarning finding are the epistemic spec.**

---

### ISSUE 4 — Formal evidence-weighting methodologies (GRADE, GRADE-CERQual, Cochrane/Campbell, EFSA/OHAT WoE, Maryland SMS, RA-RAG/AuthorityBench as the code anchor)

These are the *gold-standard methodologies*, mapped to a computable pipeline. Outcome claims are about trained-reviewer application plus where they break.

**(a) Source diversity vs filtering.** Critically, these frameworks do NOT journal-only-filter at search. Cochrane/Campbell run exhaustive protocol-driven searches **including grey literature** (trial registries, theses, government/agency reports, conference abstracts) specifically to fight publication bias; they filter on *eligibility + risk-of-bias*, not venue prestige. EFSA/OHAT WoE is purpose-built for the **all-source-types heterogeneous-stream** problem (human + animal + in-vitro + mechanistic + monitoring + grey literature). The Maryland SMS / What Works clearinghouses admit working papers (NBER) and government evaluations, weighted by design not by peer-review status.

**(b) Per-source credibility weighting + signals:**
- **GRADE:** Weight per BODY-OF-EVIDENCE-per-outcome (not per source), design-anchored then adjusted. RCT bodies start High, observational start Low; moved by 5 downgrade domains (risk of bias, inconsistency, indirectness, imprecision, publication bias) and 3 upgrade domains. Output: High/Moderate/Low/Very-Low, **fully disclosed with per-domain rationale in a Summary-of-Findings table.**
- **GRADE-CERQual (qualitative):** Different four components — methodological limitations, coherence, adequacy, relevance — proving **the same meta-framework needs DIFFERENT domains for different evidence types.**
- **EFSA/OHAT WoE:** Three explicit steps — ASSEMBLE → WEIGH (on RELIABILITY × RELEVANCE, at least semi-quantitative and documented) → INTEGRATE (+ characterise uncertainty). This is the **two-axis weight** POLARIS currently conflates into one tier.
- **Maryland SMS:** 5-point design-validity scale (1=correlation … 5=RCT), quasi-experiments (diff-in-diff, RD, IV) in the strong middle. Per the economics "credibility revolution" (Card/Angrist/Imbens 2021 Nobel), **a strong natural experiment can be near-top evidence — RCTs are NOT automatically the apex outside clinical efficacy.**

**(c) Composition weighted by credibility — concrete, auditable primitives:**
- **GRADE "overall = LOWEST certainty among the critical outcomes"** (PMID 22542023; ACIP Handbook Ch.10) — explicitly NOT an average and NOT a count. A deterministic, non-averaging aggregation primitive directly portable to a pipeline.
- **Inverse-variance weighting** (Cochrane/Campbell meta-analysis) — literally weight by precision; a precise large study dominates many imprecise ones. The cleanest quantitative "weight not count."
- **RA-RAG Weighted Majority Voting** — the computable analog for discrete factual claims.

**(d) Contested-topic / vax case.** GRADE handles disagreement via the **inconsistency domain** — unexplained heterogeneity *downgrades certainty* rather than being averaged away or hidden; it does not false-balance (the higher-quality body's estimate is reported with its certainty and the conflict is stated) and does not censor the minority finding. WoE is *literally built to adjudicate competing hypotheses across discordant streams* — weigh by reliability×relevance, state the balance, report disagreement as characterised uncertainty. **This is the formal vax playbook: weight-and-disclose, never 50/50, never suppress.**

**(e) Volume-vs-weight + independence.** **Unanimous: quality = WEIGHT, not COUNT.** GRADE explicitly rejects vote-counting (many small biased studies → still Low; one large low-RoB trial → High). Inverse-variance weighting and risk-of-bias weighting formally separate strength from count. **Independence gap:** these frameworks model duplicate/overlapping reports of the same trial (de-duplication at SR stage — the nearest formal cousin to echo-chamber detection) but have no native web-source independence mechanism because they never leave the curated-study world. RA-RAG (the code anchor) has the same blind spot; **AuthorityBench measures it.**

**(f) Per-claim disclosure.** GRADE's Summary-of-Findings table, CERQual's Summary-of-Qualitative-Findings, EFSA's weighing table, WWC's evidence tiers — **every formal framework treats the weighting RATIONALE as a required, disclosed, per-claim deliverable.** GRADE = per-claim CERTAINTY disclosure; POLARIS already does per-claim PROVENANCE disclosure. **The gap is wiring a GRADE-style certainty label onto each verified sentence.**

**OUTCOME / known failures:** Field standard (Cochrane, WHO, NICE, CDC ACIP, BMJ mandate GRADE). Failures: substantial inter-rater variability (GRADE is acknowledged "subjective" — reproducible only as *structured judgement*, not a deterministic formula); frequent misapplication in published SRs (PMC12900191); CERQual's coherence/adequacy are even harder to operationalize computationally. Cochrane's RCT-apex under-values real-world evidence; Campbell's flexible hierarchy is criticized for admitting weaker designs; SMS has a documented "anti-social bias"; clearinghouses can be so strict they manufacture a "nothing works" artefact. The cost of doing this RIGHT is high — an automated pipeline buys speed at the price of approximation, **which must be disclosed.**

**Relevance to POLARIS:** The single most important design claim in the entire report comes from here: **there is no universal evidence hierarchy.** The same meta-framework (confidence via explicit domains) must use different hierarchies and different *primary credibility axes* per domain — clinical weights RCTs + peer-review; **economics/policy weights design-validity over venue** (a Nobel-validated shift); qualitative weights coherence/adequacy. **POLARIS's current journal-allowlist `tier_classifier` would mis-rank a strong NBER working-paper natural experiment (routed to policy/think-tank T4) below a weak peer-reviewed cross-sectional study.** A global journal-only filter is methodologically wrong outside clinical efficacy questions. Adopt: separate SOURCE-credibility prior from EVIDENCE-certainty posterior; reliability×relevance two-axis weight; "lowest-among-critical" + inverse-variance as auditable non-averaging primitives; domain-conditional rubrics driven off the existing `scope_templates`; grey literature as first-class weighted by design.

---

### ISSUE 5 — Faithfulness & dissent UX synthesis (SourceCheckup, Wallat, OpenScholar/Scholar QA, plus the 9-system roll-up)

This issue is a compact cross-system synthesis (the JSON's item0 is the substantive one; items "b"/"c" are placeholder stubs with no content and carry no findings).

**(a) Source diversity vs filtering.** Evals audit deployed LLMs; OpenScholar grounds *only* in retrieved papers; the engines search the open web. Spread mirrors Issues 1–2.

**(b) Per-source weighting.** Confirms the report-wide finding: **no system discloses a per-source weight; Consensus counts studies equally.**

**(c) Composition.** Per-statement support checking, ablation, Citation-F1, scite support/contrast/mention, Consensus proportion meter — all *measurement* of support, none *weighting-by-credibility.*

**(d) Contested-topic / vax.** Equal-weighting false-balances the vaccine case; the prescribed answer is **present weighted convergence**, not a count ledger.

**(e) Volume-vs-weight.** "Citation count is not evidential strength; consilience is independent lines" — i.e., the right signal is **independent corroborating lines of evidence**, not citation volume.

**(f) Per-claim disclosure.** The sharpest framing in the whole report: **"Perplexity chips say SOURCE EXISTS, not SUPPORTS."** The UX target is **span-linked verdict badges** — does the cited span support this exact sentence — not existence chips.

**OUTCOME / known failures (the faithfulness numbers that anchor the BEAT-BOTH case):**
- 50–90% of statements not fully supported across systems.
- **Up to 57% of CORRECT citations are unfaithful** (the citation is real and on-topic but does not support the claim).
- GPT-4o hallucinated >90% of cited papers in the relevant eval.
- **Perplexity ~94% of citations are "source-exists," not "source-supports."**
- scite 2023 reproducibility F 0.0–0.58 (consistent with Issue 2's independent eval).

**Relevance to POLARIS:** Validates verify-against-span as the core differentiator — the exact failure a chip misses. **The gap none fill is: disclose weight per claim.** Ai2's Scholar QA / OpenScholar is named as the BEAT-BOTH faithfulness baseline (it grounds strictly in retrieved papers — the most honest competitor to measure against). Techniques: verify each claim against its cited span; weighted-and-disclosed balance ledger plus consilience; calibrated framing + abstain; **split-view "Proof Replay"** as the disclosure UX.

---

## 3. THE HONEST GAP — the ideal vs where the field actually is

**The ideal outcome.** For any research question, in any domain, ingesting all source types: (1) retrieve broadly without a venue filter; (2) assign each source a *decomposed, disclosed* credibility prior on the correct domain-conditional axis (design-validity for econ/policy, peer-review+RoB for clinical, coherence/adequacy for qualitative); (3) **collapse non-independent sources to independent origins** so 50 sites copying one press release count as ~1; (4) aggregate by reliability-WEIGHT not count, using auditable non-averaging primitives; (5) on contested topics, present the consensus side at its high weight AND the minority side attributed at its (low) weight with an explicit forewarning that the minority has more-but-weaker sources — never censor, never false-balance; (6) attach to every sentence a span-bound provenance token, a certainty label, a credibility weight, and an independent-origin count — and let the user replay the proof.

**Where the field actually is.** Each of the six elements exists *somewhere*, but no system assembles them, and three are barely solved anywhere:

- **Disclosed per-claim credibility weight: unsolved everywhere.** Frontier products narrate or list; rating orgs are source-level only; RA-RAG and CAG keep weights internal. This is open whitespace.
- **Source independence / echo-chamber detection: unsolved in every deployed product and in the best RAG method.** RA-RAG explicitly assumes independence. The signal is *detectable* (content-copying networks at 0.80–0.84, RAGRank PageRank, Wikipedia counting doctrine) but **nobody has wired independence-collapse into a deployed deep-research pipeline.** This is the single biggest lead opportunity.
- **The contested low-credibility-majority (vax) hard case: unsolved.** Academic tools avoid it by corpus restriction; open-web tools (Exa, STORM) handle it badly (echo-amplification or false balance); frontier products silently pick one side and under-support it. The *normative* answer (weight-of-evidence + forewarning + bridging) is known and even empirically tested, but **no automated system implements weight-and-disclose-with-forewarning.**

Three additional honest truths the field would rather not state:
- **Citation visibility is inversely correlated with citation validity** (Perplexity). The market optimizes the wrong metric.
- **Deeper agentic research can REDUCE faithfulness** (79%→17% as tool calls scaled), with surface metrics masking it. "More sources" is a risk multiplier, not a quality signal.
- **The popular trust authorities are capture-prone** (FTC demands on NewsGuard/Ad Fontes). A sovereign pipeline must not hardwire any one external rater as ground truth.

**Where POLARIS could LEAD, given per-claim provenance.** POLARIS already has the hardest substrate — per-sentence `[#ev:id:start-end]` tokens + `strict_verify` (numeric match + ≥2 content-word span overlap) + zero-verified-abort. That is the verify-against-span layer the entire faithfulness literature says is missing and the layer a citation chip cannot provide. The lead is to extend that substrate from *provenance disclosure* to **provenance + credibility-weight + independent-origin-count + certainty disclosure per claim** — the union that no competitor offers — and to make the credibility weight (a) domain-conditional, (b) independence-aware, and (c) actually drive composition (not sit beside it as a decoration like Consensus's chips).

---

## 4. Concrete best-practice techniques POLARIS should adopt

Tied to the pipeline `retrieve → score → independence-collapse → aggregate → compose → disclose`. Several map directly onto POLARIS's existing `tier_classifier`, `authority_score[0,1]`, `corroboration_count`, `AuthorityConfidence`, and `scope_templates`.

**Layer 0 — Retrieve broadly, validated by Exa.** Keep all-source-type semantic retrieval (Exa proves a non-journal-filtered retriever is viable). Treat retrieval as ingest; add the credibility/independence/disclosure layers Exa stops short of.

**Layer 1 — Domain-conditional, two-axis, decomposed credibility prior (replace the single-tier conflation).**
- Detect the question's domain off the existing `scope_templates`, then select the *primary credibility axis*: clinical → RCT-apex + peer-review + RoB proxy; **economics/policy → design-validity (SMS-style), NOT venue** (a strong NBER natural experiment outranks a weak peer-reviewed cross-section); qualitative → CERQual coherence/adequacy/relevance.
- Score each source on **two axes — RELIABILITY (internal validity/method) × RELEVANCE (directness to this question)** per EFSA WoE, instead of one venue tier (fixes the indirect-but-prestigious vs direct-but-weak confusion).
- Decompose and **disclose** the prior NewsGuard-style (auditable sub-criteria), but **never hardwire a single external vendor's verdict** — transparent, multi-signal, overridable by the claim-level verifier (capture defense).
- Admit grey literature (gov data, working papers, registries) as first-class, weighted by **design, not peer-review status.**
- Keep `AuthorityConfidence` honest: thin signals → LOW confidence, never a fabricated HIGH (GRADE Very-Low / EFSA uncertainty-characterisation are the formal precedent).

**Layer 2 — Source-independence collapse (the lead capability; nobody deploys it).**
- Build a near-duplicate / syndication detector over the retrieved corpus (content-copying graph: TF-IDF cosine ≥0.85 in a short time window; ~0.80–0.84 accuracy in the literature, catching exactly the cases text misses).
- Turn `corroboration_count` into an **independent-origin count** — distinct hosts/owners/funding — and **collapse correlated copies to ~1 BEFORE any weighted vote** (Wikipedia circular-reporting doctrine: 50 sites copying one press release = 1 piece of evidence).
- Optionally layer a RAGRank PageRank-style independence prior, but **pair it with the claim-level verifier so a genuinely well-evidenced minority is not buried** (PageRank's establishment-bias caveat).

**Layer 3 — Aggregate by weight, with auditable non-averaging primitives.**
- For discrete factual claims: RA-RAG-style **Weighted Majority Voting over the post-collapse independent origins** — a few high-credibility sources override a larger low-credibility bloc.
- For quantitative claims with reported uncertainty: **inverse-variance weighting** (weight by precision).
- For overall certainty of a multi-part claim: GRADE's **"lowest certainty among critical sub-claims"** (deterministic, non-averaging) — prefer these auditable formulas over an LLM "just weigh it" step.
- Earn reliability from cross-source agreement (RA-RAG Dawid-Skene/EM) where labels are absent, but **always after independence-collapse** — never feed correlated votes into the EM.

**Layer 4 — Contested-topic composition: weight-and-disclose-with-forewarning (the vax case).**
- Report the consensus side at its high weight AND the minority side **attributed** at its low weight, with an **explicit forewarning** that the minority has more-but-weaker / non-independent sources. The N=887 finding: forewarning works, outnumbering does not — so disclosure is the mechanism, not citation flooding.
- Use **cross-lineage multi-judge agreement** (POLARIS's existing voter/arbiter architecture) as the bridging/balanced-panel analog — weight a contested claim by agreement across *independent/diverse* judges, not by volume.
- **Honest failure mode = ABSTAIN** ("contested; no independent consensus") rather than fabricate a balanced verdict — maps onto POLARIS's existing refuse/unresolved behavior and Community Notes' abstention.
- Carry scite's **retraction/editorial-notice flag as a hard credibility penalty**, and **favor RECALL on the refutes/contrasting class** (over-detect potential contradiction, fail loud / route to human — a missed refutation is the lethal clinical error; this is the *opposite* of scite's precision-favoring tune).

**Layer 5 — Per-claim disclosure (extend provenance to weight + origins + certainty).**
- Extend the per-sentence `[#ev:id:start-end]` token so each verified sentence carries **{span-verdict, credibility weight, independent-origin count "N sources → M origins", certainty label}** — the union of Elicit's traceability + scite's intent signal + GRADE's certainty + a weight none of them show.
- Ship the **split-view "Proof Replay"** UX (verdict badges that say SUPPORTS, not just EXISTS — the explicit answer to the Perplexity-chip illusion).
- **Make the weight FEED composition AND show that it did** (avoid Consensus's disclosed-but-not-weighted trap).

**Layer 6 — Validate adversarially, publish blinded.**
- Benchmark against **AuthorityBench** (volume-vulnerability + credibility-ignorance) and RA-RAG's Adversary-Hammer prior — labeled tests where naive volume-based synthesis flips to the false majority — to *prove* weight beats count on the vax-shaped case.
- Re-verify per claim at every depth increment (the 79%→17% degradation curve: treat more sources/tool-calls as a risk multiplier to be checked, not a quality signal — consistent with POLARIS's existing ban on source-count as a quality metric).
- Publish POLARIS's **own blinded per-claim faithfulness eval** rather than self-graded LLM scores (the Exa circular-eval risk; the Co-STORM 99%-vs-85% marketing gap). Scholar QA / OpenScholar is the honest BEAT-BOTH baseline.

---

## 5. Consolidated Source List

**Independent evals — frontier DR faithfulness/bias (T1):**
- DeepTRACE — https://arxiv.org/abs/2509.04499 ; https://arxiv.org/html/2509.04499v1
- ReportBench — https://arxiv.org/abs/2508.15804 ; https://arxiv.org/html/2508.15804v1
- "Cited but Not Verified" — https://arxiv.org/html/2605.06635v1
- "Detecting and Correcting Reference Hallucinations" — https://arxiv.org/html/2604.03173v1
- AI-search struggle coverage — https://www.digitalinformationworld.com/2025/09/study-finds-ai-search-tools-struggle.html
- https://www.techrxiv.org/doi/full/10.36227/techrxiv.172107441.12283354/v1 ; https://arxiv.org/pdf/2504.06436

**Vendor docs (T2 — stated claims, not verified behavior):**
- https://openai.com/index/introducing-deep-research/ ; https://chatgpt.com/features/deep-research/
- https://gemini.google/overview/deep-research/ ; https://ai.google.dev/gemini-api/docs/interactions/deep-research

**Scientific-evidence tools:**
- scite independent eval (Hsiao & Schneider) — https://journals.indianapolis.iu.edu/index.php/hypothesis/article/view/26528
- scite QSS/MIT paper — https://www.biorxiv.org/content/10.1101/2021.03.15.435418v1.full.pdf ; https://direct.mit.edu/qss/article/2/3/882/102990
- scite features/Reference Check — https://scite.ai/features ; https://scite.ai/blog/how-do-i-use-the-scite-reference-check
- Consensus deep-dive (Tay 2025) — https://aarontay.substack.com/p/a-2025-deep-dive-of-consensus-promises
- Consensus Meter / guardrails — https://help.consensus.app/en/articles/10069920-the-consensus-meter
- Consensus PMC review — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC12318603/
- Elicit vs human (Cochrane / Bianchi 2025) — https://onlinelibrary.wiley.com/doi/full/10.1002/cesm.70033 ; https://pmc.ncbi.nlm.nih.gov/articles/PMC12462964/
- Elicit 2nd-reviewer (Hilkenmeier 2025) — https://journals.sagepub.com/doi/10.1177/08944393251404052
- Exa evals — https://exa.ai/blog/evals-at-exa
- STORM paper — https://arxiv.org/pdf/2402.14207 ; https://storm-project.stanford.edu/research/storm/
- Co-STORM "99%" vendor claim — https://www.edtechinnovationhub.com/news/pn7fo3f7xehe5gfj24mcjuntt7ormz
- Semantic Scholar — https://www.semanticscholar.org/faq/influential-citations ; https://www.semanticscholar.org/product/api
- Impact-measure critique — https://www.mdpi.com/2304-6775/11/1/5 ; https://arxiv.org/html/2405.15739v3

**Credibility scoring + credibility-aware RAG + independence detection:**
- NewsGuard — https://www.newsguardtech.com/ratings/rating-process-criteria/ ; https://en.wikipedia.org/wiki/NewsGuard ; https://csh.ac.at/news/newsguard-study-finds-no-bias-against-conservative-news-outlets/
- NewsGuard FTC coverage — https://www.techpolicy.press/considering-the-federal-trade-commissions-double-standard-on-media-bias/ ; https://www.courthousenews.com/media-watchdog-fires-back-at-ftc-over-retaliatory-probe/ ; https://www.washingtontimes.com/news/2026/apr/17/federal-trade-commission-shuts-investigation-newsguard/
- MBFC — https://mediabiasfactcheck.com/methodology/ ; https://en.wikipedia.org/wiki/Media_Bias/Fact_Check ; https://arxiv.org/pdf/2506.12552
- Ad Fontes — https://adfontesmedia.com/methodology/ ; https://adfontesmedia.com/methodology-white-paper/ ; https://en.wikipedia.org/wiki/Ad_Fontes_Media
- RA-RAG — https://arxiv.org/abs/2410.22954 ; https://arxiv.org/html/2410.22954 ; https://arxiv.org/html/2410.22954v4 ; https://aclanthology.org/2025.emnlp-main.1738/ ; https://learnprompting.org/docs/retrieval_augmented_generation/reliability-aware-rag
- CAG — https://arxiv.org/abs/2404.06809 ; https://arxiv.org/html/2404.06809v3
- RAGRank — https://arxiv.org/pdf/2510.20768
- Content-sharing veracity networks — https://ar5iv.labs.arxiv.org/abs/2101.10973 ; https://arxiv.org/pdf/2101.10973
- Wikipedia doctrine — https://en.wikipedia.org/wiki/Wikipedia:Independent_sources ; https://en.wikipedia.org/wiki/Wikipedia:MEDRS ; https://en.wikipedia.org/wiki/Wikipedia:Identifying_reliable_sources_(medicine)/FAQ
- Community Notes — https://en.wikipedia.org/wiki/Community_Notes ; https://www.pnas.org/doi/10.1073/pnas.2503413122 ; https://arxiv.org/pdf/2510.09585 ; https://arxiv.org/pdf/2601.14002
- Weight-of-evidence / forewarning — https://www.ncbi.nlm.nih.gov/pmc/articles/PMC7528676/ ; https://journalofcognition.org/articles/10.5334/joc.125 ; https://www.voicesforvaccines.org/toolkits/false-balance-in-media/ ; https://healthjournalism.org/glossary-terms/false-balance-false-equivalence/
- AI health-misinfo context — https://almcorp.com/blog/google-ai-overviews-health-misinformation-investigation-2026/ ; https://www.ersnet.org/news-and-features/news/ai-models-produce-inaccurate-and-potentially-harmful-health-information-reports-find/
- AuthorityBench — https://arxiv.org/pdf/2603.25092
- Trustworthy-RAG index — https://github.com/Arstanley/Awesome-Trustworthy-RAG

**Formal evidence-synthesis methodologies:**
- GRADE — https://www.cdc.gov/acip-grade-handbook/hcp/chapter-7-grade-criteria-determining-certainty-of-evidence/index.html ; https://www.cdc.gov/acip-grade-handbook/hcp/chapter-10-overall-certainty-of-evidence/index.html ; https://pubmed.ncbi.nlm.nih.gov/22542023/ ; https://academic.oup.com/aje/article/194/6/1681/7746729 ; https://pmc.ncbi.nlm.nih.gov/articles/PMC12900191/
- Cochrane handbook Ch.14 — https://www.cochrane.org/authors/handbooks-and-manuals/handbook/current/chapter-14
- GRADE-CERQual — https://www.cerqual.org/ ; https://journals.plos.org/plosmedicine/article?id=10.1371/journal.pmed.1001895 ; https://pmc.ncbi.nlm.nih.gov/articles/PMC5791047/
- Campbell — https://www.campbellcollaboration.org/ ; https://en.wikipedia.org/wiki/Campbell_Collaboration
- EFSA / OHAT WoE — https://www.efsa.europa.eu/en/efsajournal/pub/4971 ; https://academy.europa.eu/courses/efsa-s-weight-of-evidence-approach ; https://health.ec.europa.eu/document/download/cfa0d186-1c5d-4c01-aea5-6a9f856ff46a_en ; https://pmc.ncbi.nlm.nih.gov/articles/PMC7551547/
- Maryland SMS / What Works — https://whatworksgrowth.org/resources/the-scientific-maryland-scale/ ; https://whatworksgrowth.org/wp-content/uploads/16-06-28_Scoring_Guide.pdf ; https://arxiv.org/pdf/2405.20604
- Economics credibility revolution — https://www.nber.org/papers/w15794 ; https://papers.ssrn.com/sol3/papers.cfm?abstract_id=4567672 ; https://pmc.ncbi.nlm.nih.gov/articles/PMC6680130/

**Faithfulness & dissent UX (Issue 5):**
- https://www.nature.com/articles/s41467-025-58551-6 ; https://arxiv.org/abs/2412.18004 ; https://www.cjr.org/

---

**Two integrity flags carried from the research, retained on purpose:** (1) the "Perplexity 37% citation-hallucination" figure does not trace to either primary hallucination paper and is excluded as SEO-blog conflation; (2) Perplexity's Deep Research internals could not be primary-verified (official blog 403; all "five-stage gauntlet / L1–L3 reranker" detail is third-party speculation, treated as low-confidence). One correction recorded during research: a fast-model summary wrongly claimed RA-RAG detects correlated/copied sources; the full text shows it *assumes* independence — the opposite — which is exactly why the independence layer is POLARIS's lead opportunity.

---

## 6. CODEX COMPLETENESS ADDENDUM (mandatory corrections + REQUIRED additional layers)

The Codex research-completeness gate returned NEEDS_ADDITIONS. The corrections below SUPERSEDE any overstatement in sections 1-5, and the "required additional layers" are MANDATORY in the implementation plan. Treat this section as authoritative where it conflicts with text above.

### 6a. Factual corrections (do NOT overstate these in the plan)
- AuthorityBench evaluates AUTHORITY PERCEPTION (DomainAuth / EntityAuth / RAGAuth), NOT echo-chamber/volume. Do not cite it as a volume-vulnerability benchmark. (arxiv 2603.25092)
- DeepTRACE: Perplexity(DR) ~97.5% unsupported statements + 5.5% source necessity are correct, BUT "94.5% decorative links" is overstated -- source necessity is a minimum-cover metric, and DeepTRACE uses LLM-judge support labels with only moderate human correlation. Frame as "low minimum-cover / weak grounding," not "decorative." (arxiv 2509.04499)
- RA-RAG: iterative reliability estimation + weighted majority voting; it is NOT clearly Dawid-Skene/EM, and it does NOT solve copied-source dependence -- its benchmark constructs sources independently. So RA-RAG is the aggregation primitive AFTER independence-collapse, not a solution to it. (arxiv 2410.22954)
- The "GPT 79%->17% as tool calls 2->150" faithfulness-collapse stat is UNVERIFIED. Use the supportable figure: 39-77% factual accuracy with ~42% average fact-check drop across two frontier models. The directional claim ("more tool calls can reduce faithfulness") stands; the dramatic number does not. (arxiv 2605.06635)
- CAG is EMNLP 2024 (not 2025); its "credibility" labels are largely relevance/timeliness/noise, not source authority; 0.917 is exact-match on EvolvingTempQA at noise 0.8. (arxiv 2404.06809)
- RAGRank is a CTI PageRank poisoning-defense proof-of-concept, NOT a validated general web echo-chamber/independence detector. Use only as inspiration. (arxiv 2510.20768)
- Community Notes ("<12.5% display", "25-34%") and Elicit ("6% hallucinations / fabricated control groups") claims need their OWN primary citations before being treated as settled.
- "Citation visibility is inversely related to citation validity" is too broad: state Perplexity as a strong COUNTEREXAMPLE to citation-chip trust, not a proven general market law.
- GRADE/CERQual descriptions are sound; minor: distinguish classic GRADE upgrade domains from newer Core GRADE (which narrows rating-up reasons).

### 6b. Missed systems/benchmarks to incorporate
- Competitor mapping (add): Claude Research + Claude web search + Anthropic Citations API; Microsoft 365 Copilot Researcher/Analyst (wraps OpenAI deep research); Grok DeepSearch/DeeperSearch. (None appear to disclose a credibility WEIGHT -- consistent with the whitespace thesis -- but the "frontier products" claim is incomplete without them.)
- Validation/benchmark suite (promote into the plan, section 5/Layer 6): SourceBench (2026; cited web-source quality across 100 queries / 3,996 sources -- arxiv 2602.16942), DeepResearch Bench, DRBench, BrowseComp-Plus, ResearchRubrics, plus DeepTRACE / ReportBench / AuthorityBench.

### 6c. REQUIRED additional architecture layers (MANDATORY in the plan; these extend the 6-layer flow)
1. ARTICLE-LEVEL + CLAIM-LEVEL quality scoring, not just a source/host-level prior: author, venue, method/design, funding & conflicts, date, corrections/retractions, AND claim-specific relevance. Source-level priors alone are insufficient.
2. TEMPORAL / SUPERSESSION logic: downgrade stale-but-authoritative evidence (old guidelines, superseded datasets/regulations, retracted or corrected claims) even when the source is high-authority.
3. CLAIM-GRAPH layer BEFORE weighted voting (this is a new sub-layer between independence-collapse and aggregate): atomic-claim extraction -> claim normalization -> stance clustering -> contradiction/refutation detection -> span entailment. Weighted majority voting is only valid AFTER equivalent claims are clustered.
4. INDEPENDENCE-COLLAPSE must go beyond near-duplicate TF-IDF: syndication, press-release origin, common ownership, common funding, shared authorship, citation chains, semantic paraphrase, and generated-copy clusters.
5. CALIBRATION + AUDIT metrics: Brier/ECE or reliability curves for the credibility weights, blinded human audits, and ablations for retrieve/score/collapse/aggregate -- plus the SourceBench/DeepTRACE/ReportBench/AuthorityBench suites.
6. RETRIEVAL source-type stratification + DISSENT RECALL: scoring cannot fix a pipeline that never retrieves the strongest contrary evidence or the best evidence for a minority view. Retrieval must actively seek the best minority-side evidence.
7. FINAL VERIFIER strengthening (ADDITIVE only, never weakening): strict_verify (numeric match + >=2 content-word overlap) is too weak as the FINAL gate -- ADD NLI/QA entailment, unit/table/quantity checks, and contradiction-sensitive verification on top. (POLARIS already has an NLI advisory path + qualitative/semantic conflict detectors to build on.)
8. BOTH-SIDES UX policy for MULTI-position disputes (not just binary pro/con): medical/health misinformation must be disclosed as low-weight / fringe evidence, explicitly NOT normalized as an equal "side."

proceed_to_plan: yes, CONDITIONAL on the plan incorporating 6a (no overstatement), 6b (added systems/benchmarks), and ALL of 6c (the 8 required layers).
