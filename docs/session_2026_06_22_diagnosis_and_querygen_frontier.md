# Session 2026-06-22 — Beat-Both Disaster Diagnosis + Query-Generation Frontier (re-entry doc)

**Purpose:** single re-entry point after reboot. Captures everything from the 2026-06-22 session:
the beat-both disaster root cause (verified), the benchmark/Telus/search landscapes, and the
triple-verified query-generation frontier with the buildable POLARIS target architecture.
Nothing here is committed yet — it is on disk so it survives the reboot.

---

## 0. Actions already taken (state)
- **All 14 vast.ai instances DESTROYED** (REST API, all `success:true`, 0 remaining). ~$2.1/hr GPU + storage billing stopped. Nothing is running, nothing is billing.
- The beat-both campaign (#1289) is **paused for re-strategy**, not abandoned. No live runs.

## 1. The beat-both disaster — root cause (Claude-ultracode diagnosis + Codex cross-read, both converged)
The drb_72 catastrophe (DRB-II total 0.071 / info_recall 0/57; DeepTRACE 95% unsupported) was
**overdetermined and largely a benchmark-wiring bug, not proof the architecture is worthless.**
Ranked root causes (file:line verified by both arms):
1. **WRONG QUESTION LAUNCHED (foundational).** `scripts/run_honest_sweep_r3.py:4238-4269` hardcodes a
   general "AI / Fourth Industrial Revolution literature review, English journals only" prompt — NOT the
   canonical DRB-II idx-56 prompt ("Generative AI", pre-June-2023, four named sections, 5-col table,
   blocked-reference rule). `corpus_snapshot.json` question = the substituted string. So info_recall 0/57
   is mechanical: the pipeline answered a different question. 0 of 14 rubric studies were ever retrieved.
2. **SPLIT-BRAIN SCORING (Codex catch).** DeepTRACE pack used the CANONICAL question while the report
   answered the SUBSTITUTED one. The report and the grading question are mismatched on both boards.
3. **No question-derived COVERAGE CONTRACT (foundational, missing organ #1).** `completeness_checker.py`
   keys on a domain keyword checklist; it read 8/8 covered while recall was 0/57. `required_entity_ledger.py`
   is advisory/default-OFF/post-strict_verify. Coverage is accidental.
4. **DeepTRACE harness artifacts.** `pack_deeptrace.py` 10-source greedy cap uncites 55% of statements
   BEFORE judging (the 0.5 cites/statement); `run_deeptrace.py:181` `scrape_ok` accepts `Title:`-only Jina
   stubs, so 9/10 paywalled PDFs feed the GPT-5 judge no body.
5. **Residual real faithfulness signal (do NOT exonerate).** Sources that DID return content were still
   judged "none". Not pure artifact.
6. **Corpus-shaped sections from config + ordering (NOT span-grounding).** `config/scope_templates/workforce.yaml:167-357`
   hand-authors one-paper-per-section; `multi_section_generator.py:6968-6973` places contract plans FIRST and
   demotes the (enabled) STORM scaffold to "enrichment". Also `workforce.yaml` hard-wires 2024/2025 sources
   violating the "before June 2023" rule.
7. **No cross-source synthesis producer (missing organ #2).** `relational_quantifier_guard.py` is strip-always
   by design; `verified_compose.py` multi-cite path double default-OFF. (Underdetermined on that run: only 2 of
   366 clusters were multi-source.)
- **Truncation was a non-issue** (answer body ends ~char 94.6K, inside the 150K judge budget).
- **The faithfulness engine is the crown jewel and was found CORRECT (zero fabrications).** Untouchable.

## 2. Benchmark landscape (Claude + Codex online, verified)
- **DeepTRACE (arXiv 2509.04499)** = citation-faithfulness audit of long-form deep-research REPORTS. GPT-5 judge.
- **DeepResearch Bench II (arXiv 2601.08536, Feb 2026)** = coverage, 132 tasks / 9430 binary rubrics, Gemini judge.
- **Original DeepResearch Bench (Du/Mao, arXiv 2506.11763)** = RACE+FACT, the **most-recognized** report board
  (only one with a live public multi-vendor leaderboard). Splits RACE (coverage) and FACT (citation accuracy).
- **BrowseComp / GAIA / HLE are NOT deep-research-report benchmarks** — web-agent QA (short answer) / closed-book exam.
  Labs cite them for their DR *products*, which causes the conflation.
- Note: two different "Deep Research Bench" papers — Du/Mao (reports) vs FutureSearch 2506.06287 (RetroSearch, QA).

## 3. Telus buyer analysis (grounded, Telus AI posture verified)
- **Lead benchmark: DeepResearch Bench FACT (citation accuracy), backed by DeepTRACE for competitor-gap numbers**
  (GPT-5 Deep Research 79%, Perplexity 58% / 97.5% unsupported). It maps to a regulated buyer's real fear.
- **A benchmark only gets you shortlisted.** What closes: a live POC on Telus's own data with one-click per-claim
  traceability + audit trail; certs (SOC2 Type II + ISO 27001 baseline, ISO 42001 + NIST AI RMF rising);
  independent attestation.
- **Two Telus buyers:** Telus Health (BAA before PHI, SOC2, external clinical validation) vs Telus enterprise.
- **THE FLAG: sovereignty is Telus's #1 enterprise lever** (Sovereign AI Factory, Rimouski; US CLOUD Act avoidance).
  POLARIS recently pivoted to **all-GLM via OpenRouter (US)** and uses **Serper (US Google)** — both misaligned
  with the Telus sovereign pitch. **The sovereignty decision needs reopening if Telus is the buyer.**

## 4. Search-tool landscape (code-audit + web, verified)
- **Wired + always-on:** Serper (Google SERP proxy — dumb pipe, no AI), Semantic Scholar (S2), OpenAlex.
- **Wired + by-topic:** arXiv/GitHub (tech), Europe PMC (clinical), SEC EDGAR (due diligence).
- **Fetch chain:** Crawl4AI (local) + Jina (+ Zyte/Firecrawl if keys), Unpaywall OA-upgrade, CORE, PMC BioC.
- **Wired but DEFAULT-OFF:** the whole agentic loop — Exa (neural), DuckDuckGo (fallback), Serper-Scholar,
  citation-snowball, STORM. Flipping it on is the biggest breadth change but risks silent no-op.
- **Not wired (sovereignty path):** Brave Search API (own index), Mojeek, **SearXNG** (already in docker-compose
  sovereign profile, zero code consumers — the main sovereignty action item).
- **Not wired (clinical gaps):** ClinicalTrials.gov v2 (403) + openFDA (allowlist) — the two patient-safety APIs.

## 5. QUERY-GENERATION FRONTIER (the main deliverable — triple-verified: Claude survey -> Claude adversarial verify -> Codex online)
### 5a. POLARIS's actual state
- **POLARIS does NOT run STORM live.** STORM is wired but default-OFF (`PG_STORM_ENABLED_IN_BENCHMARK=0`).
  The live query generation is the **template/planner "amplified facets"** (anchor question + facets from the
  scope template/contract, or the research planner). These are **WEAKER than STORM** on coverage.
- Ladder: **frontier (closed-loop) > STORM (open-loop, 2024) > POLARIS today (template facets).** Two steps behind.
- Query generation is the **highest-leverage stage** — it decides coverage; everything downstream is capped by it.

### 5b. The frontier (one idea)
**Open-loop -> closed-loop.** Stop planning queries once/freezing; keep re-deciding what to search from what was
found; reshape the outline as evidence arrives. **Coverage (InfoRecall) is the bottleneck** — even leaders 40-60%.
Codex correction: **faithfulness is ALSO unsolved across the field** (WebWeaver's whole point is getting cite-acc to
93%), so POLARIS's faithfulness lead is on an uncontested problem.

### 5c. The verified reference set (2025 spine + 2026 patterns)
**2025 spine (verified mechanisms):**
- WebWeaver (arXiv 2509.13312) — dynamic outline interleaved with evidence + memory bank; **93.37% citation accuracy**.
- Tongyi DeepResearch / IterResearch (2510.24701 + 2511.07327) — **open-weight** closed-loop; workspace
  reconstruction fixes context collapse; scales 3.5%->42.5%.
- ConvergeWriter (2509.12811) — **open weights**, cluster-to-section; coverage **80.14% vs STORM 24.91%**.
- TTD-DR (2507.16075, Google) — draft-conditioned retrieval; ablation 39.4%->69.1%; 69-74% win over OpenAI DR. (closed)
**2026 patterns to fold in (verified; NO 2026 system beats 2025 on both axes on open weights):**
- AgentCPM-Report / WARP (2602.06540) — **open-weight 8B** writing-as-reasoning, dynamic outline during writing.
- DuMate (2606.07299) — auditable multi-agent + rubric-grounded coverage (fits POLARIS audit identity; DRB-II recall #1).
- FS-Researcher (2602.01566, ACL 2026) — durable file-system memory (scale past context window). RACE 53.94 but
  proprietary backbone + 76.17% cite-acc (< WebWeaver 93.37%).
- ScaffoldAgent (2606.20122) — utility-guided outline ops (Expansion/Contraction/Revision). RACE 44.70-48.27 (< 50.58).

### 5d. POLARIS TARGET ARCHITECTURE (closed-loop coverage front-end; faithfulness engine UNTOUCHED)
1. **Coverage contract per question** — decompose the question into an evidence-tree of required sub-points (gap map).
   = the missing organ #1 from the diagnosis.
2. **Un-freeze the outline** — WebWeaver-style dynamic outline; each node linked to its basket of corroborators.
   (Also fixes the corpus-shaped-report defect.)
3. **Gap-driven re-query + workspace reconstruction** — IterResearch loop: find thin/empty baskets, fire targeted
   follow-up queries, rebuild a clean workspace each round, stop when the contract is satisfied (honest stopping rule).
4. **Cluster-to-section composition** — ConvergeWriter-style; clusters of corroborating sources become sections (fits baskets).
5. **Faithfulness fence (load-bearing)** — every new span -> basket -> verify layer, NEVER prose directly.
   strict_verify / span-grounding / 4-role run UNCHANGED each round. The loop only ADDS retrieval; never relaxes a gate.
- This is WEIGHT-AND-CONSOLIDATE (§-1.3) + a closed-loop coverage front end. Coverage EMERGES; never forced with a cap.

## 6. NEXT STEP (recommended)
Draft the **Step-1 build brief** (Claude Codex Workflow), faithfulness untouched, frontier-tech mandate block on top:
- The **coverage-contract generator** (question -> required-points evidence-tree).
- The **gap-detector** keyed on the existing baskets (`finding_dedup`): which sub-points have thin/empty baskets.
- The **gap-driven re-query loop** wrapping the existing `live_retriever`.
- A **behavioral replay harness** measuring required-points-satisfied before/after on a banked `corpus_snapshot.json`.
- Acceptance = the loop demonstrably fires and lifts basket-coverage in the REAL output (not green tests, not a diff approval),
  and every new source passes the unchanged faithfulness gate. Re-scan the frontier at build-start (field moves monthly).

## 7. Open strategic decisions still on the table (operator's call)
- **Targets:** keep beat-both (DeepResearch Bench FACT + DeepTRACE), and which board(s) for market recognition.
- **Sovereignty:** reopen the Serper (US Google) + OpenRouter (US) dependency vs the Telus sovereign pitch
  (SearXNG + Brave + open-weights path already partly available).
- **Build scope:** Step-1 surgical (coverage loop) first to get a clean baseline, then scope the full structural rebuild.

---

## 8. BENCHMARK SET — rigorous relevance/impact filter (added 2026-06-22, all 16 scored vs POLARIS criteria)
Prior `state/beatboth_campaign/BENCHMARKS_STUDY.md` studied only the 2 pinned (assumed, not filtered). This filter
scored all ~16 verified deep-research-report benchmarks against POLARIS criteria (axis / runnable-judge / recognition /
rewards-our-faithfulness-edge / winnable-headroom / mission-fit / cost). Result: the pinned two are validated (both 9/10),
each has ONE weakness, and 3 primaries patch them.

**PRIMARY (5) — the set to run:**
1. **DeepTRACE (9, arXiv 2509.04499)** — faithfulness anchor (POLARIS home axis; competitors 40-80% cite-acc).
   WEAKNESS: NO public leaderboard + scoring HARNESS NOT RELEASED -> we reimplement the 8 metrics (~1-2 days) = a self-run
   audit, not a ranking we top. Weak metric = One-Sided/Overconfident (must render pro+con from contradiction edges).
2. **DeepResearch Bench II / DRB-II (9, arXiv 2601.08536)** — coverage anchor; LIVE public board (agentresearchlab,
   AI21 #1 ~64.38%, top pack 59-64%); official harness runnable (run_evaluation.py, Gemini-2.5-pro judge). Coverage win
   needs the synthesis layer (facts retrieved != facts composed).
3. **DEER (8)** — runnable, text-native, low-cost per-claim faithfulness harness; checks linked evidence supports each
   claim + back-tracks uncited claims. Fills DeepTRACE's missing released harness. (Surfaced by the completeness critic.)
4. **DeepScholar-Bench (8)** — LIVE monthly public board, sentence-level verifiability (mirrors strict_verify); top
   system only ~31% (far from saturated). Fills DeepTRACE's no-public-board gap = a faithfulness ranking we can point at.
   Caveat: weak clinical fit (academic related-work synthesis).
5. **DRACO (8)** — Perplexity real-usage benchmark; 26 expert validators incl. medical/legal/financial; Law+Medicine
   domains + Objectivity axis. The regulated-buyer (Telus) trophy. Caveat: top bar ~70.5% (high) — sales asset, not guaranteed #1.

**SECONDARY (3) — insurance/recognition, not headline:**
6. DeepResearch Bench v1 / Du-Mao (6, arXiv 2506.11763) — most-recognized established public HF leaderboard (RACE+FACT,
   judge now GPT-5.5); carry for the recognized headline number only; superseded by DRB-II on coverage.
7. ReportBench (8 score / secondary role, arXiv 2508.15804) — two-axis (cited-lit quality + per-claim statement
   faithfulness), .env-swappable judge; internal regression check.
8. ResearchRubrics (7, arXiv 2511.07685, Scale AI + ICLR 2026) — strongest third-party CREDENTIAL for buyer conversations;
   overlaps DRB-II on coverage, under-rewards per-claim citation.

**SKIP:** MMDeepResearch-Bench (multimodal penalizes text-only POLARIS), DeepResearchEval (citation-FREE — neutralizes our
edge), Dr.Bench/Rigorous (rewards source-URL not span-support), MDPI Paged-RAG (no competitor board), FINDER (overlaps DRB-II).

**Operative metric for the query-gen bake-off:** coverage (DRB-II info_recall + DeepResearch Bench RACE) while watching
faithfulness (DEER + DeepTRACE + DeepScholar-Bench sentence-verifiability) so coverage never costs faithfulness.

**Key operational insight:** DeepTRACE alone is NOT a winnable public ranking (no board + unreleased harness) — DEER makes
faithfulness RUNNABLE, DeepScholar-Bench makes it RANKABLE (public board), DRACO makes it BUYER-LEGIBLE to Telus. Faithfulness
gates stay fixed; never relaxed to chase a coverage score.

---

## 9. STANDARD PROCESS + first instance (added 2026-06-22, GH #1291)
**Operator-locked:** every pipeline section is now reviewed by a **systematic Claude Codex bake-off in VM** against the locked benchmark set — data-driven, GLM-5.2, Codex the only gate. Standard process doc: `docs/standard_process_pipeline_section_review.md`.
- **GitHub:** Issue **#1291** (I-qgen-001) — "Standard process: systematic pipeline-section review via Claude Codex bake-off (first instance: query generation)".
- **Brief (Codex-gated):** `.codex/I-qgen-001/brief.md` → verdict `.codex/I-qgen-001/codex_brief_verdict.txt`.
- **First instance = query generation.** Candidates: AgentCPM-Report/WARP, DuMate, FS-Researcher, ScaffoldAgent + REQUIRED baselines (IterResearch/WebWeaver/ConvergeWriter + current POLARIS template-facets floor). Metric: coverage primary (DRB-II info_recall + DeepResearch Bench RACE), faithfulness watched (DEER/DeepTRACE/DeepScholar) — regress faithfulness = lose.
- **GATE 0 (hard precondition):** fix + sanity-canary the benchmark harness (wrong-question/split-brain/Title-stub) BEFORE any scoring run. No valid bake-off until the canary passes.
- **Honest scope:** the 4 methods are NOT POLARIS modules — standalone bake-off SELECTS the mechanism; the winner is then ported into POLARIS (integrated run + §-1.1 audit = the real decision). Only runnable open candidates are tested.
- **Execution status:** plan authored + Codex-gating in progress. Execution (harness fix → VM bake-off) is the multi-day program the gated plan defines; ALL VMs were destroyed this session, so it needs re-provisioning. Faithfulness engine untouched throughout.

### 9a. Brief gate APPROVED (2026-06-22)
`.codex/I-qgen-001/brief.md` is Codex-APPROVED (iter 3; convergence 6 P1 -> 4 P1 -> 0 P1). The bake-off plan is execution-ready: hash-chained artifact lineage + 3 negative canaries on GATE 0; SCREEN (advisory) + DECIDE (POLARIS-controlled isolation with a deterministic per-query retrieval snapshot + a fixed adapter API for closed-loop candidates + common-code basket build); decision-grade stats (paired bootstrap + Holm/FDR + min-effect + finalist reruns); hard faithfulness non-regression gates; subcomponent candidate taxonomy (trained-weights vs portable scaffold). EXECUTION NEXT (multi-day, needs VM re-provision): GATE 0 harness fix + canary -> frontier rescan file + classify + runnability -> VM bake-off (SCREEN then DECIDE) -> §-1.1 audit of winner -> port (Codex diff-gate) -> integrated POLARIS replay + §-1.1 = SECURE.

### 9b. Brief gate FINAL APPROVE (scoreboard-only, 2026-06-22)
Operator directive: the bake-off decision is SCOREBOARD-ONLY (no human gate); §-1.1 per-claim audit is performed mechanically by the faithfulness scoreboards (DEER/DeepTRACE/DeepScholar). Brief re-gated: iter4 REQUEST_CHANGES (1 P1: GATE 0 must prove the scoreboards catch SEMANTIC unsupportedness, not just reachability) -> iter5 APPROVE after adding a 4th GATE-0 negative canary (reachable-but-contradicted claim must fail-loud on all 3 faithfulness scoreboards). Final verdict trajectory: RC(6P1) -> RC(4P1) -> APPROVE -> [scoreboard change] -> RC(1P1) -> APPROVE. `.codex/I-qgen-001/brief.md` is the locked, execution-ready plan. DECISION RULE: faithfulness-eligible (>= floor-tolerance on DEER/DeepTRACE/DeepScholar) then highest coverage (DRB-II info_recall + DeepResearch Bench RACE), significance-confirmed; no human read.
