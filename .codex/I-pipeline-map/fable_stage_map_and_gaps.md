# Full pipeline stage map + isolation-test gap audit — Fable 5 (I-pipeline-map)

Date: 2026-07-10. Author: Fable 5 (architect brain). Traced from the REAL code on the current
checkout (branch `bot/I-deepfix-relaunch` lineage; compose harness on `bot/I-comp-fastloop-001`).

---

## §0. OPERATOR MANDATE — MAXIMUM PARALLELISM GOVERNS EVERY STAGE LOOP (binding)

"Fast fast fast — max it out." The box is NOT the bottleneck: **box2 = 128 CPU cores, 2 TB RAM
(1.8 TB free)**. Every stage-isolation loop below (tier/weight, off-topic, dedup/consolidate,
claim-extract, compose[synthesis→verify→D8→render→eval]) MUST be built to fan out as wide as the
external service allows. TARGET WALL-CLOCK IS MINUTES, not tens of minutes — the operator reads
every line of each loop's output, so the design→build→run→read→fix→pass cycle must turn in minutes.

Four rules bind EVERY loop design:

1. **LLM-based stages fan out 32–64+ concurrent OpenRouter calls.** OpenRouter sustains high
   concurrency; the bound is the provider rate limit, NEVER the box. D8's 4 roles also run
   concurrently with each other. Each loop states its concurrency knob + env var explicitly.
2. **Deterministic / batch stages parallelize across the 128 cores** (pairwise/cluster/scoring
   work in a process or thread pool sized to the cores, not a token-serial loop).
3. **Every loop is crash-resilient: write results INCREMENTALLY + auto-resume the un-processed
   items.** A single hiccup (the crawler EPIPE that killed the first full 921 fetch run) must never
   cost the whole run. Skip already-written ids on restart.
4. **Every loop ships a fast subset mode (`--limit` / `--urls-file` style) AND a full run** over
   all 921 sources / all sections. Subset = the fix cadence; full = the acceptance read.

Each loop design MUST state up front: (1) the parallelism knob + env var, (2) recommended
concurrency, (3) expected wall-clock (minutes).

### Per-stage parallelism spec (real knobs from source — grep `PG_*CONCURREN|WORKERS|PARALLEL|INFLIGHT`)

| Stage | Loop type | REAL knob (env var, file) | Recommended concurrency | Expected wall-clock (921 src / all sections) |
|-------|-----------|---------------------------|-------------------------|----------------------------------------------|
| 1 Fetch junk | deterministic + network | `fetch_corpus_replay.py --parallel` (default **12** — RAISE), `PG_FETCH_CONCURRENCY`, `PG_USE_PARALLEL_FETCH`, `PG_LIVE_RETRIEVER_PER_HOST_CONCURRENT` | `--parallel 48–64` (per-host cap stays polite) | minutes; **NOTE: fetch_corpus_replay writes results.json ONCE at the end (`:214`) — NOT incremental. Add incremental write + resume before the next full run (rule 3).** |
| 2 Tier/weight | LLM (if LLM-tiering) + deterministic scorer | `PG_TIER_LLM_PARALLEL`, `PG_TIER_LLM_WORKERS`; deterministic `authority_score` join over cores | 48–64 LLM; cores for the scorer | minutes (deterministic pass is seconds; fold into the off-topic run) |
| 3 Off-topic | LLM, batched | `PG_SCOPE_TOPIC_BATCH` (default **25** src/call, `topic_relevance_gate.py:180`) × fan out the batches | 25/call × 32–48 batches concurrent | ~1–3 min (921 ÷ 25 ≈ 37 batches, all in flight at once) |
| 4 Dedup/consolidate | deterministic + optional NLI | deterministic clustering across cores; `PG_FINDING_DEDUP_NLI_WORKERS`, `PG_CONSOLIDATION_NLI_WORKERS` for the NLI leg | cores (deterministic); 32–48 NLI workers | seconds–minutes (deterministic core needs no LLM for pass 1) |
| 5 Claim/basket | LLM judges | `PG_CREDIBILITY_JUDGE_CONCURRENCY`, `PG_CREDIBILITY_PASS_MAX_INFLIGHT`, `PG_CREDIBILITY_PASS_SIDE_JUDGE_CONCURRENCY`, wall `PG_CREDIBILITY_JUDGE_POOL_WALL_S` | 48–64 | minutes |
| 6 Synthesis | LLM writers, per-section | `PG_MAX_PARALLEL_SECTIONS` / `PG_PARALLEL_SECTIONS`, `PG_SECTION_WRITE_CONCURRENCY`, `PG_DEPTH_SYNTHESIS_CONCURRENCY` | all sections concurrent (≈14) | minutes — compose harness pool `PG_COMPOSE_HARNESS_MAX_PARALLEL` (default **2** — RAISE for a wide case sweep) |
| 7 Verify + D8 | LLM, per-claim + 4 roles | `PG_VERIFY_CONCURRENCY` / `PG_PARALLEL_VERIFY`; D8 `PG_FOUR_ROLE_ADAPTIVE_CONCURRENCY`, `PG_FOUR_ROLE_CLAIM_WORKERS`, `PG_FOUR_ROLE_JUDGE_CONCURRENCY`, `PG_FOUR_ROLE_SENTINEL_CONCURRENCY` | 48–64 claims; 4 roles concurrent | minutes |
| 8 Render | deterministic | cores (assembly is CPU-only, no LLM) | cores | seconds |
| 9 Eval gates | deterministic + evaluator LLM | evaluator reads once; `PG_LLM_CONCURRENCY` / `PG_MAX_CONCURRENT_LLM` global ceiling | 48–64 | seconds–minutes |

Global LLM ceiling knobs that cap ALL of the above: `PG_LLM_CONCURRENCY`, `PG_MAX_CONCURRENT_LLM`,
`PG_SIDE_JUDGE_MAX_CONCURRENCY`. Set these HIGH (≥64) so no per-stage knob is silently throttled
below its own setting. The compose harness `PG_COMPOSE_HARNESS_MAX_PARALLEL` default 2 and the fetch
replay `--parallel 12` are the two known under-set defaults — RAISE both.

Every gap recommendation in §"Ranked gap list" below inherits these four rules and the row above it.

---

Scope: the production flow from `corpus_snapshot.json` (post-retrieval selected evidence) to the
rendered `report.md`, as executed by `run_one_query` in `scripts/run_honest_sweep_r3.py:8816`
(launched via `scripts/dr_benchmark/run_gate_b.py:5585 run_gate_b_query` → `--only <slug> --resume`).
Every stage below cites the real entrypoint. "Compose-covers" = the end-to-end compose fastloop
harness (`scripts/compose_fastloop_harness.py`, #1378, branch `bot/I-comp-fastloop-001`, 47 tests
green, Codex gate r3) exercises the stage because it subprocesses this exact resume path and reads
the produced report.

---

## Correction to the assumed picture (matters for the decision)

**Tier classification does NOT run in the corpus_snapshot → report window.** The T1–T7 tier and
`authority_score` are stamped on each evidence row at RETRIEVAL time
(`src/polaris_graph/retrieval/tier_classifier.py`, 2,443 lines) and are FROZEN inside
`corpus_snapshot.json`. On `--resume`, selection is SKIPPED and the snapshot's billed rows reload
as-is (`run_honest_sweep_r3.py:12928`, `:13164`). What DOES run at compose time is the
tier→authority JOIN + weighting display (`credibility_pass.py:266 _join_tier_authority_prior`,
B17 deterministic weights) and the tier-mix disclosure (`run_honest_sweep_r3.py:2120
_tier_mix_disclosure_summary`, weighted-corpus gate `:12282-12354`). So a WRONG TIER is a
retrieval-time defect already banked in the snapshot — no compose-window loop can catch it; it
needs its own read of the banked assignments.

---

## The ordered stage table

| # | Stage | Module + entrypoint (file:line) | What it breaks in the final report if wrong | Isolation test that reads its decisions line-by-line? | Compose end-to-end covers it? |
|---|-------|-------------------------------|---------------------------------------------|------------------------------------------------------|-------------------------------|
| 0 | Resume load | `src/polaris_graph/generator/corpus_snapshot.py` `load_corpus_snapshot`; seam `run_honest_sweep_r3.py:9090-9148` | Corrupt/stale snapshot → wrong evidence pool; stale `OFF_SUBJECT` stamps from an earlier run (guarded: fresh-verdict-only deletion `:13256`, `junk_deletion_gate.py:95`) | Fail-loud on corrupt (`:9148`); no dedicated loop | YES — it is the compose harness's entry seam |
| 1 | Fetch/clean + junk screen (A15 + refetch seams) | `_screen_junk_evidence` def `run_honest_sweep_r3.py:1248`, calls `:11754` (retrieval-side), `:13569`, `:13681`, `:14260` (refetch/L5 seams); chrome strip in fetch stack (`strip_markdown_nav_chrome`, `frame_fetcher._is_fetch_shell`) | Chrome/bot-wall/cookie text becomes cited evidence → chrome-as-claim bullets, truncated numbers, junk quotes in prose | **YES — RUNNING.** `scripts/fetch_corpus_replay.py` (256 lines) over the 921-source corpus; gate tests `tests/polaris_graph/test_fetch_junk_gate.py`; I-fetchclean-001 rounds 1–2 merged | YES (leg-B chrome/shell/truncated-number oracle) |
| 2 | Tier/credibility weighting | Classifier (retrieval-time, FROZEN in snapshot): `src/polaris_graph/retrieval/tier_classifier.py`. Compose-time join/weight: `src/polaris_graph/synthesis/credibility_pass.py:266 _join_tier_authority_prior`, `:210 institutional_tier_floor_enabled`; weighted gate + disclosure `run_honest_sweep_r3.py:12282-12354`, `:2120` | Junk/predatory source displayed at high weight; credible institution under-weighted; corroboration blocks + Methods tier-mix percentages wrong → reader trusts the wrong sources | **GAP.** I-cred-001 produced a research doc (`docs/credibility_tier_landscape_2026.md:1`) + disclosure-schema unit tests (`test_credibility_disclosure_schema_icred001.py`, `test_bug771_tier_authority_and_oa_ceiling.py`) — no loop reads the 921 (url → tier, authority) assignments | PARTIAL — weights are DISPLAYED per citation in the rendered report, but a wrong tier reads as plausible prose; only a per-source check catches it |
| 3 | Topic-relevance gate + junk deletion | `src/polaris_graph/retrieval/topic_relevance_gate.py:481 classify_topic_relevance` (called `run_honest_sweep_r3.py:13230/:13329`); deletion `src/polaris_graph/generator/junk_deletion_gate.py:205 partition_rows` (called `:14988`); disclosure write `:15033` | Off-topic sources kept → off-topic prose sections; good sources deleted (over-deletion) → coverage loss; both were diagnosed defects | **DESIGNED.** `.codex/I-offtopic-loop-001/fable_offtopic_loop_design.md` — real judge over 921 sources, read every ON/OFF_ASPECT/OFF_SUBJECT verdict + over-deletion guard | PARTIAL — off-topic prose is visible, but a wrongly-DELETED good source is invisible in prose |
| 4 | Dedup/consolidation | Pre-gen selection cap: `run_honest_sweep_r3.py:5399 _capped_finding_dedup_selection` (call `:13207`). Consolidation: `src/polaris_graph/synthesis/finding_dedup.py:624 consolidate_same_work`, `dedup_by_finding` (call `run_honest_sweep_r3.py:14650-14687`); claim key `_finding_key` `finding_dedup.py:535`, `__unknown__` sentinel `:570` (RC-D area); syndication `src/polaris_graph/synthesis/content_dedup_consolidate.py` (generator call `multi_section_generator.py:~9246`) | Under-consolidate → the diagnosed REPETITION defect (same claim restated many times). Over-consolidate → §-1.3 violation: corroborating sources silently dropped, breadth loss. `__unknown__` key collapse → per-row singleton baskets → no corroboration counts, shallow "quote-dump" synthesis | **GAP (partial).** Unit tests (`test_fact_dedup.py`, `test_content_dedup_consolidate.py`) + `scripts/iarch011_b11_compose_repetition_harness.py` (banked drb_72 behavioral replay, 4 checks — but pinned to the OLD banked run, not a per-corpus read loop). No loop reads every (claim_key → basket members) grouping over the current corpus | PARTIAL — repetition IS visible in prose (compose leg reads it); silently-dropped corroboration and split baskets are INVISIBLE (report just reads thinner) |
| 5 | Claim/basket build (credibility pass) | `src/polaris_graph/synthesis/credibility_pass.py:1564 run_credibility_analysis`; `ClaimBasket` `:760`, `BasketMember` `:714`; awaited inside generator `multi_section_generator.py:~9464` (advisory, walled) | Wrong basket membership → wrong corroboration counts rendered; depth synthesis compares across wrong members → fabricated-FEELING cross-source claims; judge-unavailable → `credibility_unscored` disclosed gap | **GAP (partial).** Unit tests (`test_credibility_pass_*`, `test_basket_confirmed_offtopic_missing_member_p1_3.py`, `test_compose_offtopic_basket_screen.py`); no basket-by-basket read over the real corpus | PARTIAL — corroboration blocks + depth prose appear and are read; wrong-but-plausible member grouping doesn't announce itself |
| 6 | Composition/synthesis | `src/polaris_graph/generator/multi_section_generator.py:8845 generate_multi_section_report` (call `run_honest_sweep_r3.py:15169`): outline → per-section `_run_section` (provenance-token drafts) → `generator/fact_dedup.py dedup_pass` (`multi_section_generator.py:~10036`, rewrites re-verified) → `_apply_cross_section_repetition_guard` (`:~10634`) → limitations → `generator/analyst_synthesis.py generate_analyst_synthesis` (`:~10825`) → trial table. Then sweep-level `generator/depth_synthesis.py depth_synthesis_pre_pass` + D8 gate (`run_honest_sweep_r3.py:16556-16604`) | Quote-dump/shallow prose (diagnosed defect), missing cross-source synthesis, wrong analyst commentary, marketing preamble | **YES — BUILT.** `scripts/compose_fastloop_harness.py` (#1378, branch `bot/I-comp-fastloop-001`): subset snapshot → `run_gate_b.py --only --resume` → read the prose (leg B clean-room oracle + operator §-1.1 read) | YES — this stage is the harness's primary target |
| 7 | Faithfulness verify | `src/polaris_graph/generator/provenance_generator.py strict_verify` (per sentence, inside `_run_section` + post-dedup re-verify + depth `verify_fn=strict_verify` `run_honest_sweep_r3.py:16563/16590`); NLI entailment layer (`PG_STRICT_VERIFY_ENTAILMENT=enforce`); `src/polaris_graph/synthesis/synthesis_entailment_verify.py`; 4-role D8 `src/polaris_graph/roles/sweep_integration.py:1157 run_four_role_seam` (seam `run_honest_sweep_r3.py:18190-18700`); demotion/redaction `:3212 _apply_corroboration_d8_demotion_post_gate` (call `:18633`), body-withhold `:18661`, redaction `:18879-19252`; advisory post-release NLI `:19668` | THE clinical-lethal stage: fabricated claim survives, OR over-drop → empty/held report | Frozen incumbent (memory: faithfulness engine FROZEN 2026-06-25) + dense unit tests + D8 fixture/throughput harnesses (`scripts/dr_benchmark/build_d8_fixture_large.py`, `d8_adaptive_sweep.py`, `d8_sentinel_throughput_isolation.py`). No verdict-QUALITY read loop over real claims | YES — compose leg A reads `manifest.verification`, `synthesis_entailment_verified`, release status; the engine re-runs in full on every compose case |
| 8 | Render/assembly | `run_honest_sweep_r3.py:5230 assemble_report_md` (call `:16884`, fail-soft `:16893`); reliability header `:6237/:6336`; corroboration blocks `:3277`; bibliography `:3999`; chrome screens `:2627/:2745/:2926`; primary `report.md` write `:17275`; post-D8 rewrites; chrome canary `generator/weighted_enrichment.py evaluate_render_chrome_canary` (`:20312-20356`, enforce = status flip); D8 banner `:20373`; `generator/render_repetition_dedup.py dedup_rendered_report_markdown` (`:20405-20420`) | Chrome as claims, garbled headers, doubled disclosure blocks, verbatim-duplicate paragraphs, broken/placeholder bibliography | PARTIAL-YES — production chrome canary (self-check) + independent render harnesses: `scripts/rendered_report_acceptance_harness.py`, `scripts/iwire013_fast_render_audit.py`, `scripts/iwire012_render_canary_replay_harness.py`, `scripts/harness_render_boundary_screen.py` | YES — compose leg B is an INDEPENDENT clean-room read of the final markdown (zero production predicate imported) |
| 9 | Eval gates | `src/polaris_graph/evaluator/external_evaluator.py:960 run_external_evaluation` (call `run_honest_sweep_r3.py:17648`); `evaluator_rule_checks.json` PT11/PT13 write `:17690`; run-validity gate `scripts/dr_benchmark/run_validity_gate.py enforce_render_validity` (`run_gate_b.py:5992`, → `abort_run_validity_gate`); honest scorecard `roles/release_policy.apply_honest_scorecard_to_manifest` (`:~20440`) | Gate false-PASSes a defect (uncited numeric ships) or false-aborts a good run (drb_72 fresh run tripped exactly this — summary table absent) | Compose leg A binds any FAILED rule check to FAIL with the detail quoted (r2-P1 fix, commits `39988683`/`dbe76771`) — the gate's own output is read, both artifacts | YES |

---

## Ranked gap list + recommendation per gap

Anchor: the diagnostic report's known defects map as — chrome (stage 1, covered), repetition
(stage 4), quote-dump/shallow (stage 6, covered), off-topic kept + good deleted (stage 3,
designed), truncated number (stages 1/8, covered). So the proven-risky uncovered middle is
**stage 4/5 (dedup + baskets)**, and stage 2 (tier) is the one stage whose defects are frozen
upstream of every existing loop.

### GAP 1 — Dedup/consolidation + claim-key/basket build (stages 4+5). HIGHEST RISK. Build a dedicated loop.
- Why highest: (a) repetition was a DIAGNOSED defect of this stage; (b) the failure modes the
  compose read CANNOT see are exactly this stage's worst ones — a silently-dropped corroborating
  source (§-1.3 violation) or a wrongly-SPLIT basket makes the report quietly thinner, never
  visibly wrong; (c) the `__unknown__` claim-key sentinel (`finding_dedup.py:570`, RC-D) degrades
  to singleton baskets = the R=0.0 floor — the report still renders, just shallow.
- Recommendation: ONE fast loop, same shape as fetch/off-topic. Deterministic core is OFFLINE
  (no LLM needed for the first pass): run `consolidate_same_work` + `dedup_by_finding` +
  the basket grouping over the real 921-row snapshot; dump every
  `(claim_key → [members: ev_id, url, tier, span-head])` grouping + the `__unknown__` fraction +
  every collapsed row with its surviving sibling; operator reads every grouping for wrong-merge /
  wrong-split. Reuse `iarch011_b11_compose_repetition_harness.py`'s footprint-preservation checks
  (its CHECK 2/3 are exactly the over-collapse guard) but pointed at the CURRENT corpus, not the
  banked June run.
- **Parallelism (mandate §0): (1) knob = a process pool sized to `os.cpu_count()` (128) for the
  pairwise/cluster grouping — deterministic, no LLM for pass 1; the optional NLI consolidation leg
  uses `PG_FINDING_DEDUP_NLI_WORKERS` / `PG_CONSOLIDATION_NLI_WORKERS` fanned to 32–48. (2)
  recommended = 128-way cores for clustering, 48 NLI workers if the NLI leg is on. (3) wall-clock =
  seconds for the deterministic dump over 921 rows; single-digit minutes with the NLI leg.**
  Crash-resilient: write the per-cluster JSONL incrementally, resume by skipping written cluster
  ids. Subset mode: `--limit N` rows / `--section <name>`; full = all 921.

### GAP 2 — Tier/credibility weighting (stage 2). MODERATE RISK. Cheap loop, fold into the off-topic run.
- Why: tiers are frozen in the snapshot BEFORE every existing loop's window; a junk source stamped
  T2 sails through fetch (content is clean), topic (it is on-topic), and compose (weight is
  displayed, not validated). Defect class = wrong emphasis, not fabrication — real but not lethal.
- Recommendation: do NOT build a separate harness. The off-topic loop already iterates the same
  921 snapshot rows; add one dump column per source — `(url, title, tier, authority_score,
  institutional-floor hit?)` — and read the assignments in the same sitting. That IS the I-cred-001
  isolation read, at near-zero extra build cost. Escalate to a dedicated bake-off only if the read
  finds systematic misclassification.
- **Parallelism (mandate §0): the deterministic `authority_score` + tier join is a cores-parallel
  pass (seconds over 921 rows, no LLM). If the LLM tiering path is exercised, knob = `PG_TIER_LLM_PARALLEL`
  / `PG_TIER_LLM_WORKERS` fanned to 48–64. Because this rides the off-topic loop, it inherits that
  loop's incremental-write + resume + `--limit`/`--urls-file` subset mode for free.**

### GAP 3 — D8/4-role verdict QUALITY (stage 7). LOW residual. Rely on compose; no new loop.
- The engine is the frozen incumbent, per-claim unit-tested, with dedicated fixture + throughput
  harnesses; compose re-runs it in full and leg A reads its verdicts. The uncovered sliver is
  "is the judge's VERDICT right per claim" — a verdict-quality audit loop. Given frozen status and
  the cost of hand-adjudicating claims, rely on the compose read: isolate only if the prose read
  surfaces a claim the D8 verdict got wrong.

### Non-gaps (explicitly checked, no action)
- Stage 0 resume: fail-loud + compose harness entry seam. Stale-stamp deletion is fresh-verdict-only.
- Stage 8 render: 4 independent harnesses + compose leg B clean-room read + production canary.
- Stage 9 eval gates: compose leg A binds failed checks with the detail quoted, dual-artifact.
- I-comp-002 (iso composition bake-off): source `.py` NOT in git (only a `.pyc`); its gate-0 canary
  pattern is already re-implemented inside the compose fastloop harness. I-render-001: research
  deliverable only (`docs/render_landscape_2026.md:1`); render is locked deterministic
  (`state/section_winner_board.md:22`). I-cred-001: research doc + schema tests, NOT a harness —
  that is GAP 2.

---

## Bottom line on sequence completeness

fetch → off-topic → compose is NOT complete as a middle coverage plan. Insert ONE stage:

**fetch → off-topic (+tier columns) → DEDUP/BASKET loop → compose.**

The dedup/basket loop is the single missing dedicated harness; the tier read piggybacks on the
off-topic loop; everything else is either already isolated, frozen-and-tested, or genuinely
revealed by the compose end-to-end read.

Every one of these loops is built to the §0 mandate: fan out to the provider limit (32–64+ LLM
calls) or across the 128 cores, write incrementally + auto-resume, ship a subset mode, and turn in
MINUTES. Two existing loops need a parallelism upgrade to meet it: `fetch_corpus_replay.py`
(`--parallel 12` → 48–64, and add incremental write + resume — it currently writes results.json
once at the very end, exactly the single-point-of-failure that the EPIPE crash exposed), and the
compose harness (`PG_COMPOSE_HARNESS_MAX_PARALLEL` default 2 → higher for a wide case sweep).
