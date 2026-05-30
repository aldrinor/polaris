# I-safety-002 — DR Eval Gold-Standard + Top-Tier Benchmark + Claude/Codex Optimize-Harness Loop

**Status**: SYNTHESIZED PLAN (Claude research `claude_dr_research.md` + Codex research `codex_dr_research.txt`, both 2026-05-27/28). Pending Codex §-1.1 plan review, then build.
**GitHub**: #923. **Constraint**: human-free (#922), top-tier models only, only budget = API fees, §-1.1 claim-by-claim scoring.

---

## §1. The gold-standard method = a BATTERY (Claude+Codex agree), not one number

Four layers. Each is a recognized public method; together they establish credibility AND showcase the POLARIS differentiator.

| Layer | Method (gold standard) | Measures | Current top-tier (the bar) |
|---|---|---|---|
| **A. Objective web-research** | **FutureSearch DRB / RetroSearch** (arXiv 2506.06287; frozen snapshots = reproducible) | answer accuracy on real research tasks, no live-web drift | Claude 4.6 Opus 55.0%, GPT-5 49.6%, Gemini 3 Flash 49.9% |
| **B. Report quality** | **DeepResearch Bench RACE** (arXiv 2506.11763) | comprehensiveness/depth/instruction-following/readability (reference-based adaptive rubric) | Gemini-2.5-Pro DR **48.88** |
| **C. Citation/claim faithfulness (PRIMARY for POLARIS)** | **FACT** + **SAFE/LongFact** (2403.18802) + **ALCE** (2305.14627) + FActScore (2305.14251) | per-claim support/refute/insufficient; unsupported-claim rate; citation precision/recall/coverage; effective supported claims | Perplexity DR **90.24% citation accuracy** |
| **D. Clinical fabrication (DIFFERENTIATOR)** | **MedHallu-style mechanical injection** (= our human-free oracle #922) + FActBench | fabrication-catch rate on deterministically-injected clinical fakes | frontier best **F1 ≈ 0.625** on hard medical hallucinations |
| Retriever isolation (debug only) | **BrowseComp-Plus** (fixed corpus) | retriever vs agent | GPT-5+Qwen3-Embed 70.1% |

**Positioning (Codex; honesty per P2 — hypothesis until sealed-test data exists)**: POLARIS *aims to demonstrate* leadership on **"claim-faithful clinical deep research,"** NOT generic DR. Layers A/B = credibility; layers C/D = where native per-claim provenance + the fabrication contract are *hypothesized to* exceed the public gold standard. No leadership claim is made until sealed-test results back it.

## §2. The PRIMARY POLARIS score: per-claim citation faithfulness

Pipeline (SAFE/FACT-style):
1. Atomize every report sentence into atomic claims.
2. Map each claim to cited source span(s) — applied UNIFORMLY to ALL tools' visible output+citations (POLARIS already emits `[#ev:<id>:<start>-<end>]`; competitors scored on their visible citations).
3. Judge each: SUPPORTED / REFUTED / INSUFFICIENT (cross-family judge panel for the judgment; mechanical where a decimal/entity/date is deterministically checkable per strict_verify).
4. Report: **unsupported-claim rate**, citation precision, citation coverage/recall (importance-aware, 2604.03141), effective supported claims, **critical-clinical-claim failure rate**.

**FAIR-SCORING RULE (Codex P1)**: the benchmark score is computed on EACH tool's VISIBLE output+citations, scored identically. POLARIS's native per-claim provenance is NOT scored as a benchmark advantage — it is reported as a SEPARATE **product-capability dimension** ("native verifiable provenance," which competitors lack). Do NOT claim "native provenance → higher benchmark score"; that conflates a feature with a metric. FACT is citation accuracy/effective-citations, not a clinical truth oracle.

**Anti-gaming (Codex P2)**: unsupported-claim rate is gameable by terse/refusal-heavy reports. ALWAYS pair it with importance-aware recall + answer completeness + abstention QUALITY + effective-supported-clinical-claims, so a tool can't win by saying little.

**Provenance upgrade (Codex rec, product side)**: convert per-SENTENCE → per-ATOMIC-CLAIM provenance, each carrying source span + date/version + evidence tier + the hard unsupported-claim contract. (A product improvement, reported as a capability — not a benchmark-scoring trick.)

## §3. Reconciling the no-human constraint with the clinical-credibility caveat (HONEST — Codex P1 corrected)

Codex flagged: clinical-safety claims *ideally* want a blinded clinician audit + judges calibrated to human labels. Under the operator's no-hire HARD CONSTRAINT (#922) we reconcile — but WITHOUT overstating what the oracle proves:

- **What the mechanical oracle ACTUALLY establishes** (and ONLY this): deterministic ground truth for **synthetic-perturbation detection** — "did the verifier catch a fabrication we DELIBERATELY PLANTED?" It does NOT establish real-world clinical claim correctness, real-world severity, source adequacy, or judge calibration against ground clinical truth. MedHallu = controlled synthetic hallucination detection, NOT clinical validation.
- It therefore does NOT "replace human calibration" in general — it replaces human labeling ONLY for the synthetic-fake STATUS dimension (where it is genuinely superior: we know the answer because we injected it).
- **SEVERITY**: a judgment call; no human → cross-family LLM judge panel + deterministic hazard scaffold (#922), disclosed as machine-adjudicated.
- **Claim license (binding)**: clinical results = a **bench safety stress test on synthetic perturbations, NOT expert/clinically validated** (amendment §6, locked). The credibility gap where a clinician audit would add value is REAL and DISCLOSED, not papered over.
- Layers A/B/C non-clinical: fully human-free + credible. Layer D clinical: human-free, scoped to synthetic-perturbation detection, down-licensed exactly there.

## §4. Head-to-head protocol — TWO protocols, never mixed (Codex P1: no frozen-vs-live trap)

Running POLARIS on frozen snapshots while competitors hit the live web is apples-to-oranges. Split:

### Protocol 1 — LIVE-PRODUCT head-to-head (layers B report-quality + C citation-faithfulness + D clinical)
- ALL tools run as their LIVE products: POLARIS, ChatGPT DR, Gemini DR, Perplexity DR.
- Identical prompts, **same date window**, paid top tier, NO manual steering, clarification → "You decide", require final markdown + citations.
- **Evidence archived AT RUN TIME**: snapshot every cited page/source the moment each tool runs, so scoring is reproducible without giving any tool a frozen-corpus edge. Tools that can't emit claim tables → post-hoc atomization of their visible output.
- This is the fair real-world comparison.

### Protocol 2 — FROZEN-CORPUS apples-to-apples (layer A objective accuracy + retriever isolation)
- ALL agents use the SAME fixed corpus / RetroSearch-like interface (FutureSearch DRB for objective accuracy; BrowseComp-Plus for retriever-vs-agent isolation when DEBUGGING POLARIS retrieval).
- Only run a competitor here if it can consume the same fixed corpus; otherwise this layer is POLARIS-internal diagnostics, reported as such (NOT a head-to-head claim).

### Prompt set (100–120, across both protocols)
30 FutureSearch objective (P2) + 30 DeepResearch Bench long-report (P1) + 20 BrowseComp-Plus retriever-isolation (P2) + 20–40 SEALED clinical tasks (P1) from PubMed / FDA labels+reviews / ClinicalTrials.gov / guidelines / systematic reviews. (Buckets sum to 100–120.)

### Scoring (automatable; FAIR per §2 — visible output scored identically across tools)
objective accuracy (A), RACE report score (B, judge panel), FACT/SAFE claim support + ALCE precision/recall (C), mechanical synthetic-fabrication-catch (D), source diversity, evidence-tier coverage, importance-aware recall + completeness + abstention quality (anti-terse), latency, cost. Report a comparison table per dimension + **failures/abstentions, not just successes**.

### Clinical layer D — stratify injected errors (Codex P2)
9 strata = the #922 7-type taxonomy + 2 clinical-specific: quantitative(dosage) · qualitative_negation · relation_direction(comparator) · temporal(date/version) · scope_overreach(inclusion-criteria) · citation_swap(fabricated-citation) · entity_swap [7 base] + endpoint · evidence-tier-mismatch [2 clinical]. Per-stratum catch rate, not a lumped number.

**Injection substrate for the LIVE head-to-head (Codex P2 — same substrate visible to EVERY tool)**: the perturbation must be presented identically to all competitors. Lock one of: (a) **prompt false premise** (the question embeds the planted error); (b) **uploaded doctored source** (a source doc with the mutation, given to every tool that accepts uploads); (c) **candidate-report perturbation** (post-hoc: mutate a true claim in a tool's own report and test its self-verification). Pick per task type; record which substrate each task uses so no tool gets an asymmetric input.

## §5. The harness loop (the operator's requested loop, hardened)

**The loop runs on the PRIVATE VALIDATION split — NEVER the sealed test (Codex P1: no sealed-set leak).**

```
①  TEST       run POLARIS on the PRIVATE VALIDATION slice
②  REVIEW     score §-1.1 claim-by-claim: A/B/C/D + cross-family judge panel (blinded, order-randomized)
③  BENCHMARK  same prompts → live competitors (Protocol 1) → comparison table per dimension
④  CODEX      Codex root-causes losses/wins on VALIDATION + deep-researches the fix
⑤  CLAUDE     Claude implements the targeted fix (prompt / retrieval / verifier) — Codex gate-reviews the diff
⑥  RE-TEST    on a FRESH VALIDATION draw + a FROZEN regression slice → back to ①
```

**Sealed test is touched ONCE per release/report** — to produce the headline "where POLARIS stands vs top-tier" number. NO optimization is ever driven by sealed-test failures (if it were, it would silently become a validation set). Codex root-causing (④) and Claude optimizing (⑤) see ONLY dev + validation, never sealed.

**Anti-overfitting / anti-gaming guardrails (Claude+Codex)**:
- **3 splits, strict roles**: public/dev (tune freely) · **private validation (the loop lives here)** · **sealed test (report-only, never tuned on, never root-caused from)**.
- Freeze source snapshots (RetroSearch-style) for reproducibility; rotate sealed clinical tasks quarterly; include post-cutoff docs; run contamination scans.
- **Canary design (Codex P2)**: canaries are contamination probes / hidden leak sentinels — placed where a model CANNOT legitimately cite them as evidence (so a canary appearing = leakage, not valid retrieval).
- Lock model/tool versions before each run; preregister scoring; fixed N replicates; bootstrap confidence intervals; blind judge inputs; randomize pairwise order; cross-family judges; calibrate judges against the MECHANICAL ORACLE (synthetic STATUS only, per §3) — NOT a substitute for human clinical calibration, which we honestly forgo.
- Report dev↔validation↔(occasional)sealed gap (overfit detector).

## §6. Build order (to FIRST real numbers fast)

1. **Harness scaffold** (`scripts/dr_benchmark/`): prompt-set loader, multi-tool runner (POLARIS + top-tier via API), run-time evidence archiver (Protocol 1), atomizer, claim→span mapper, SAFE/FACT scorer (judge panel), ALCE citation scorer, mechanical clinical-injection scorer (reuse #922 oracle), comparison-table emitter, split manager.
2. **Scorer-fixture validation FIRST, before any paid run (Codex P2)**: atomizer goldens, citation-span goldens, deterministic strict-checks, cross-family judge-agreement check, and a set of KNOWN good/bad reports the scorer must grade correctly. A scorer that misgrades fixtures invalidates every downstream number — validate it before spending a dollar on top-tier API calls.
3. **Smoke run**: 10–20 prompts across layers → FIRST real POLARIS-vs-top-tier comparison data (Protocol 1 live).
4. **Scale** to the full 80–120 battery.
5. Enter the §5 loop (on validation; sealed test report-only).

## §6.5 Version-pinning before any external/published number (Codex P2)

Every "current top-tier" figure in §1 (Gemini 48.88 RACE, Perplexity 90.24% citation accuracy, FutureSearch standings, etc.) is a leaderboard snapshot. Before ANY external/published comparison, pin: exact benchmark source version + leaderboard date + the competitor model/tool versions + the date window of our run. The §1 numbers here are dated 2026-05-27/28 and are for INTERNAL targeting only until re-pinned at publication.

## §7. Definition of done

Battery method locked (A/B/C/D); per-claim-faithfulness primary score + provenance upgrade; no-human reconciliation + claim license; head-to-head protocol; harness loop + anti-overfit guardrails; build order. Codex §-1.1 plan APPROVE. Then build scaffold → smoke → first data.

## Sources
Claude: `claude_dr_research.md`. Codex: `codex_dr_research.txt`. Key: DeepResearch Bench 2506.11763; FutureSearch DRB 2506.06287 + futuresearch.ai/effort-scaling; SAFE 2403.18802; FActScore 2305.14251; ALCE 2305.14627; BrowseComp-Plus 2508.06600; MedHallu 2502.14302; importance-aware recall 2604.03141.
