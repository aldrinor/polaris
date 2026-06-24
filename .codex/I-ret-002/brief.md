HARD ITERATION CAP: 5 per document. This is iter 3 of 5.

ITER-2 RESOLUTION (Codex iter-2 = REQUEST_CHANGES, 0 P0, 1 P1 + 2 P2 — all fixed):
- P1 embedder Axis-A keyword labels: EVERY scored POS/NEG row now judge/human-confirmed (two-family + spot
  check); keywords propose rows only, never set the scored label. §7.
- P2 reranker stale drop-threshold: build-handoff note added — the raw-json off-topic-drop facet is
  SUPERSEDED (demote/re-order only) and must be scrubbed at handoff; the brief governs. §6.
- P2 search non-DOI matching: now tied to canonical PAGE/REPORT identity, not registered-domain alone
  (domain necessary-but-not-sufficient, to avoid broad-domain false positives). §1.

ITER-1 RESOLUTION (Codex iter-1 = REQUEST_CHANGES, 0 P0, 2 P1 + 3 P2, all quality_weight/scoped — all fixed):
- P1 quality_weight circular labels: SCORED label now set by a pre-registered OBJECTIVE rubric via two-family
  (Claude+Codex) adjudication + operator sample spot-check; judge proposes only; the LLM-judge candidate is
  scored only against a different family's labels (no self-grading). §4.
- P1 quality_weight GATE-0 impossible: constant/random are now explicit NEGATIVE CONTROLS (expected AUC≈0.5),
  EXEMPT from the semantic-direction liveness canary (which applies only to real classifiers). §4.
- P2 dedup precision floor: pre-registered numeric floor = 0.97, locked before execution. §5.
- P2 search non-DOI sources: source-set schema now supports gov/guideline/agency sources by canonical-URL +
  registered-domain equivalence alongside DOI/PMID. §1.
- P2 external benchmarks: execution plan now states MTEB-R/BEIR/BRIGHT are supplemental axis-specific
  cross-checks, NOT replacements for the per-layer POLARIS/DRB-II metrics (WebMainBench stays primary for
  extraction-general). Execution plan note.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

FRONTIER-TECH MANDATE: every candidate below was date-verified against its primary source in the I-ret-001 recency audit (docs/retrieval_landscape_2026.md §10): 26 frontier 2025/2026 + 13 classic-still-SOTA, 7 dated excluded. Review only against 2025/2026 frontier; reject any grandfathered downgrade.

OUTPUT SCHEMA (this exact schema; loose prose rejected):
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]

# Brief — I-ret-002 (#1294): retrieval per-layer ISOLATION bake-off design

You are reviewing the ACCEPTANCE-CRITERIA CORRECTNESS of a bake-off DESIGN (not code). Full per-candidate
detail (exact HF/pip/API ids, licenses, GPU estimates) is in `.codex/I-ret-002/bakeoff_design_v1_raw.json`;
the critic-driven fixes are in `.codex/I-ret-002/design_must_fix.md`. This brief is the corrected design.

## Goal + non-negotiable frame
Section 2 (retrieval) of `docs/standard_process_pipeline_section_review.md`. Hold the query generator FIXED
at IterResearch/Tongyi (I-qgen-001 winner, `PG_QGEN_ITERRESEARCH`, commit 84bb2d86). Bake off the
recency-verified retrieval methods IN ISOLATION; pick a winner PER LAYER. Combine winners into ONE final
e2e run LATER (not here). Operator decisions (2026-06-23): per-LAYER winner (not one global champion, not
whole-stack A/B); ALL 7 layers built and run in PARALLEL (no sequencing, no layer dropped); cost is not the
constraint, time is; orchestration stacks (GPT-Researcher / Tongyi-DR-30B / MiroThinker) EXCLUDED as e2e.

INVARIANTS (apply to every layer; a violation is at least P1):
- §-1.1: every metric scores REAL output against LABELED ground truth. BANNED: word/citation/source COUNTS
  as quality, pattern-presence, metadata comparison, sample-only audits, string-presence PASS/FAIL.
- §-1.3 weight-not-filter: quality/credibility is a WEIGHT, never a hard drop. Only the obvious-junk
  structural floor may drop. No bake-off metric may reward a new hard filter.
- Faithfulness engine (strict_verify / NLI / 4-role / provenance) is NEVER touched or relaxed by any layer.
- GATE-0 per layer = scorer-math canary (known input → known score) AND per-candidate LIVENESS canary
  (a candidate that returns a stub / empty / load-fail / missing-key result FAILS LOUD, never scores a
  believable-low number). No candidate score is trusted until BOTH canaries are green.
- Honest scope: only runnable candidates tested; no_key / needs_gpu / needs_fixture marked honestly, never
  faked. Exact HF/pip ids pinned for determinism.

## The 7 layers (corrected design)

### 1. search_discovery
- Candidates: Serper (baseline/current), Exa, Semantic Scholar /paper/search, Firecrawl search, SearXNG
  (self-host). no_key (noted, not faked): Tavily, Parallel, Brave. Hold IterResearch queries + everything
  downstream fixed; score the RANKED URL list pre-fetch.
- Metric (CORRECTED): per-required-finding gold-SOURCE-SET recall@k. gold(f) = a SET matched by IDENTITY, not
  exact URL — fixes the §-1.3 basket-faithfulness inversion (a valid alternate source must score positive).
  The source-set schema supports BOTH (a) DOI/PMID-identified sources (matched by canonical identifier) AND
  (b) non-DOI/PMID authoritative sources — gov agency / guideline body / agency report — matched by canonical
  PAGE/REPORT IDENTITY (the specific report URL/title), NOT registered-domain alone: registered-domain
  equivalence is necessary but NOT sufficient (it must be tied to the specific page/report identity to avoid
  broad-domain false positives, e.g. any fda.gov page counting). Claim-level resolution: idx findings without a quoted title
  are judge-mapped to their supporting source (fixes idx66 where only 3/48 carry a title). Blocked DRB-II
  source excluded before scoring. Every required finding scored (no sampling).
- Ground truth: BUILD `drb_gold_sources.jsonl` — claim→source-set for idx 56/62/66/72 via Crossref+OpenAlex
  title/claim resolution + judge, DOI verified to resolve. Build a real DOI/identifier matcher (the prior
  "reuse _normalize_url+DOI-canon" claim was false).
- GATE-0: positive/negative/normalization/lineage scorer canaries + per-candidate liveness (assert each
  backend returns a real non-empty ranked list; assert keys present; Exa use_autoprompt=False so it cannot
  rewrite the held-fixed query).

### 2. fetch_crawl
- Candidates: crawl4ai (baseline), Zyte, Firecrawl fetch, Playwright. On a FROZEN URL set.
- Metric: per-URL recovery verdict {RECOVERED / WALLED / SOFT_STUB / FETCH_FAIL} + main-content
  reference-recall vs a labeled reference body. Never a length floor.
- Ground truth: BUILD `fetch_crawl_refbody_fixture` (~60–100 URLs, stratified OA/paywalled/gov/news/social),
  main-content span + recovery class hand/judge-labeled (WebMainBench protocol).
- GATE-0: two-extreme scorer canary + per-ENGINE liveness (assert ZYTE_API_KEY + PG_ZYTE* present and a
  known-fetchable URL returns a real body; a keyless Zyte must fail loud, not score low).

### 3. content_extraction
- Candidates: Trafilatura 2.x (baseline), MinerU-HTML, Resiliparse, jusText, readability (fallback
  baseline), union(traf+resi+just). Yardstick (never content-of-record): ReaderLM-v2 (generative — flag as
  fabrication risk, never auto-crowned).
- Metric: gold-referenced extraction precision/recall + WebMainBench OFFICIAL ROUGE-N F1 (general) + TEDS
  table-fidelity (clinical subset). DETERMINISTIC extractors only as content-of-record.
- Ground truth: REUSE WebMainBench (7,809 labeled pages + gold Markdown + OFFICIAL scorer) for general axis +
  GATE-0 anchor. BUILD a small clinical page fixture (~50–100: journal HTML / FDA label / EMA SmPC /
  ClinicalTrials.gov / guideline) with gold body + table trees.
- GATE-0: positive deterministic canary (gold body in → ~1.0) + reproduce WebMainBench PUBLISHED per-extractor
  numbers — VALID ONLY IF the official scorer is confirmed runnable first (else re-derive blind; do not make
  it circular). Per-candidate liveness (extractor loads + returns non-empty on a known page). FAITHFULNESS:
  assert every extractor output span is a verbatim substring of the fetched HTML text (catches the union /
  any non-extractive path).

### 4. quality_weight  (output is a WEIGHT, never a drop)
- Candidates (must pass semantic-direction liveness): DCLM fastText, Ultra-FineWeb fastText, Essential-Web
  EAI-Distill-0.5b, FineWeb-Edu, Nemotron-CC ensemble; baseline POLARIS heuristic score_content_quality;
  yardstick GLM-5.2 LLM-judge. NEGATIVE CONTROLS (NOT candidates; exempt from the liveness canary):
  constant(0.5) and random — expected AUC ≈ 0.5; the harness asserts they land near 0.5 as a scorer sanity
  check, and a candidate that cannot beat them is reported as no-signal.
- Metric: ROC-AUC of the scalar weight vs binary label (authoritative=1 / on-topic-SEO-spam=0), paired
  WITHIN-topic AND WITHIN-source-type (fixes the "source-type = better" proxy). Credibility labels INDEPENDENT
  of POLARIS's own tier metadata. Weight is NOT used as a hard filter in the test.
- Ground truth (CORRECTED per Codex P1 — labels must match the human-ground-truth metric, not be judge taste):
  BUILD `clinical_quality_weight_fixture.jsonl` (~300–500 sources, ≥150 authoritative + ≥150 on-topic-spam,
  ~15–25 topics) from banked corpus_snapshot bodies. The SCORED label is set by a PRE-REGISTERED OBJECTIVE
  rubric (verifiable signals: peer-reviewed venue / gov-agency / guideline-body vs known SEO-spam/marketing
  domain — NOT "reads high-quality"), produced by an independent TWO-FAMILY adjudication (Claude + Codex, the
  two-family principle) with an operator spot-check on a stratified sample for a kappa target. A GLM/LLM judge
  may PRE-LABEL/propose only; it never sets the scored label. The GLM-5.2 LLM-judge CANDIDATE is scored ONLY
  against labels produced by a different model family (no self-grading / no circularity). This is a small
  component-selection eval fixture, distinct from the product's human-free validation program (no collision).
- GATE-0: AUC scorer canary (perfect→1.0, inverted→0.0, random→~0.5) + per-candidate liveness applied ONLY to
  the real classifiers (each loads + scores a known authoritative-vs-garbage pair in the correct direction).
  The constant/random NEGATIVE CONTROLS are exempt from semantic-direction liveness (they are expected ≈0.5).

### 5. dedup  (near-dup collapse BEFORE basket weight; never drops a distinct claim)
- Candidates: POLARIS ContentDeduplicator (baseline), SimHash (baseline), datasketch MinHashLSH (+threshold
  sweep), SemHash+Model2Vec.
- Metric: pairwise collapse precision/recall vs per-pair gold {syndicated_copy / distinct}; recall maximized
  subject to a PRE-REGISTERED numeric precision FLOOR = **0.97** (locked before execution, not post-hoc):
  false-merge of distinct independent sources is the cardinal sin — it deletes a real corroborator, a §-1.3
  violation. A candidate below the 0.97 precision floor is disqualified regardless of recall.
- Ground truth: BUILD a labeled near-dup PAIR fixture from the 6 banked snapshots. CORRECTED SCALE: exhaustive
  C(N,2) only at N≈50–80 (≤3,160 pairs) — the "500 bodies exhaustive" claim was arithmetically impossible;
  larger needs stratified pair sampling with a stated bound. Hard-negative pairs human/Codex-adjudicated
  (clinical safety).
- GATE-0: bidirectional canary (byte-identical→merge, distinct→no-merge, over-merge precision floor) +
  per-candidate liveness on the two byte-identical controls.

### 6. reranker  (re-ORDER only; never a new hard drop)
- Candidates: POLARIS lexical rerank (baseline), BGE-reranker-v2-m3 (dated baseline), gte-reranker-modernbert-base
  (lead), mxbai-rerank-base-v2, zerank-1-small, Qwen3-Reranker-4B, Qwen3-Reranker-8B; yardstick
  llama-nemotron-rerank-1b-v2.
- Metric (CORRECTED): credibility-graded NDCG@K + required-source recall@K guard. The "off-topic-DROP
  precision" facet is REMOVED — it rewarded a new hard filter (§-1.3 breach; the incumbent only count-cuts).
  Off-topic items get gain 0 (demoted), never removed. PROD INVARIANT (state explicitly): a ported reranker
  may only RE-ORDER; it may not remove a non-junk source upstream of strict_verify.
- Ground truth: relevance via DRB-II info_recall (claim-level), credibility via an INDEPENDENT judge
  annotation over the pre-rerank pool (~3.4k candidates — budgeted as a parallel judge job with Codex/human
  sample audit; labels independent of POLARIS tier metadata).
- GATE-0: lineage (gate0_lineage.py idx binding) + hand-computed NDCG canary (ideal=1.0) + per-candidate
  model-wiring liveness (each loaded reranker ranks an obviously-relevant doc above an obvious junk doc).
- BUILD-HANDOFF NOTE (Codex P2): the raw design json (`bakeoff_design_v1_raw.json`) still carries a stale
  "calibrated off-topic-drop threshold" facet — it is SUPERSEDED by this brief (demote-only, re-order-only,
  no hard drop) and MUST be scrubbed from the harness at build handoff. The brief governs, not the raw json.

### 7. embedder_late_interaction  (single-vector vs token-level late-interaction MaxSim)
- Candidates: all-MiniLM-L6-v2 (current FLOOR), Qwen3-Embedding-8B (I-arch-009 pick to confirm),
  gte-modernbert-embed, Granite-Embedding-R2; yardstick EmbeddingGemma; late-interaction (NEW first-class):
  GTE-ModernColBERT-v1 (Apache lead), Reason-ModernColBERT (CC-BY-NC ceiling probe) via PyLate.
- Metric: dual-axis — (A) AUC(on-topic > off-topic) separation; (B) reasoning-retrieval recall@k on
  non-lexical evidence (the late-interaction edge). Hold all else fixed.
- Ground truth (CORRECTED per Codex iter-2 P1): Axis A SEEDS candidate rows from
  `scripts/relevance_scorer_bakeoff.py` LABEL_SETS keywords, but the keywords PROPOSE rows only — EVERY
  scored POS/NEG row's relevance label must be judge/human-confirmed (two-family Claude+Codex adjudication +
  operator sample spot-check), never set by string-pattern. Otherwise AUC rewards agreement with a keyword
  pattern, not true on/off-topic relevance. Axis B BUILD hand/judge-verified (rubric-claim →
  non-lexically-overlapping supporting source) pairs from banked snapshots, same two-family adjudication.
- GATE-0: known-correct AUC/MaxSim canary + per-candidate liveness (each embedder/ColBERT loads + scores a
  known on>off pair in the correct direction; assert loaded model id == requested id, no silent MiniLM
  fallback — the I-arch-009 Gate-B lesson).

## Execution plan (ALL 7 in PARALLEL — operator-mandated, cost-no-object)
NOTE on external benchmarks (Codex P2): MTEB-R / BEIR / BRIGHT are SUPPLEMENTAL, axis-specific external
yardsticks (general-domain relevance and reasoning-retrieval) — they are NOT replacements for the
layer-specific POLARIS/DRB-II metrics defined per layer above. The per-layer WINNER is decided by the
POLARIS/DRB-II metric on POLARIS data; the external benchmark is a cross-check that the winner is not a
domain-overfit. WebMainBench IS a primary metric for the extraction general axis (it is the published gold
for that exact job) + the GATE-0 anchor.
1. Build all 7 fixtures in parallel: REUSE published benchmarks for their axes (WebMainBench primary for
   extraction-general; MTEB-R/BEIR/BRIGHT supplemental cross-checks) + parallel judge-PROPOSED,
   two-family-adjudicated annotation for the POLARIS-specific fixtures (search gold, quality, dedup pairs,
   reranker credibility, embedder Axis-B), scored labels human/two-family-adjudicated with operator sample
   spot-check.
2. Build all 7 harnesses in parallel (each: scorer-math canary + per-candidate liveness canary; stub-tested
   offline before any paid run).
3. GPU VM (multi-GPU, cost-no-object): deploy, GATE-0 green per layer, then run all candidates × all layers
   concurrently. Identical held-fixed budget/snapshot per candidate within a layer; finalists rerun ≥3×.
4. Per-layer winner from REAL isolation output + a §-1.1 read of the winning layer's output. Faithfulness
   gates NEVER relaxed to lift a score.

## What to check (your call — Codex is the gate)
- Is any per-layer metric still a banned count/pattern/metadata proxy in disguise (§-1.1)?
- Does any layer reward a new hard filter or relax faithfulness (§-1.3 / faithfulness invariant)? (Esp.
  reranker drop removal + dedup false-merge floor + quality weight-not-filter.)
- Is each GATE-0 strong enough to catch a stubbed/keyless/load-failed candidate (per-candidate liveness),
  not just scorer math? This is the drb_72 anti-pattern — the highest-priority check.
- Ground-truth soundness: gold source-SET (not single URL); claim-level resolution for untitled findings;
  within-source-type pairing for quality; credibility labels independent of POLARIS tier; dedup pair-count
  arithmetic; WebMainBench official-scorer-exists precondition.
- Any candidate mis-classified (a dated method as frontier), wrong HF id, or license/sovereignty error
  (CC-BY-NC crowned as deployable rather than yardstick).
- Any NEW P0/P1 that makes a layer's "winner" untrustworthy.
