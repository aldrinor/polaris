# POLARIS Champion Pipeline — FULL BODY (query → report → score) — FINAL / RECONCILED

**Champion identity:** `run_id = SWEEP_workforce_drb_72_ai_labor_1783476454`, slug `drb_72_ai_labor`, domain `workforce`, DRB-II task 72 (canonical gold idx 56).
**Champion score:** RACE Overall **0.4447** (Comp 0.4569 / Insight 0.4293 / IF 0.4587 / Read 0.4310), FACT valid_rate **0.9032** (84/93).
**Repo of record:** `/home/polaris/wt/outline_agent` (git worktree of `/workspace/POLARIS`), HEAD `df4118a` on branch `bot/outline-agent-box`.
**Secured deliverable:** `/home/polaris/polaris_project/SECURED_0.44_champion/champion_0.4447_report.md` (3,875 words, 37 `[N]` markers + 37 References).

> **Reconciliation provenance.** This FINAL merges the draft with (a) an adversarial Opus verifier that re-checked every file:line, handoff line number, and headline figure against on-disk state and by executing `utils.stat` (VERDICT: high-fidelity, one major flaw + minor nits), and (b) an independent **Codex-terra (gpt-5.6-terra)** audit. Terra's own read-only sandbox failed on this kernel (`bwrap: No permissions to create a new namespace`), so the in-repo run produced nothing; it was **re-run text-fed** (final doc + full/excerpted source packet piped to terra, no shell execution) and DID produce a substantial second-engine audit. Terra found **5 WRONG and ~6 MISSING items the single Opus engine missed**; the two most consequential were then **re-verified against the live code by the main session** and are tagged **[TERRA+CODE-VERIFIED]**. Terra's packet-limited items (things it could not see in the excerpt packet) are tagged **[TERRA, packet-limited]**. See §0.5. Where a claim is real but unverifiable from any committed artifact it is tagged **[GAP]**.

---

## 0.5 SECOND-ENGINE (CODEX TERRA) RECONCILIATION — corrections Opus missed

Terra (text-fed) independently audited the doc against the source packet. Items below CHANGE claims elsewhere in this document and take precedence over any conflicting inline text.

### WRONG (terra) — corrections to apply
- **[TERRA+CODE-VERIFIED — MAJOR] Stage F was NOT corpus-frozen as the champion actually ran it.** `outline_agent.py:212` returns `_env_flag("PG_OUTLINE_WEB_SEARCH", default_on=True)`; `:209` comments *"Default ON (champion path)."* The compose driver (`compose_agentic_report_s3gear329.py`) sets `PG_OUTLINE_AGENT=1` but **never sets `PG_OUTLINE_WEB_SEARCH=0`** (verified absent from its setdefault list). So the outline agent's live-web tool `search_more_evidence` was AVAILABLE during the champion compose — cp4 + OpenRouter alone is **not** a guaranteed frozen replay. **To freeze the replay you MUST add `PG_OUTLINE_WEB_SEARCH=0`** to the Stage-F command. (Whether the agent actually *elected* to search on the champion run is a separate open question — see §0.5 note.)
- **[TERRA+CODE-VERIFIED] Model ledger is a MIX, not "all glm-5.2."** The outline *agent* model defaults to `z-ai/glm-5.2`, but the outliner *code* model and the generator/writer default to `deepseek/deepseek-v4-pro` across many modules (`analyst_synthesis.py:647`, `sentence_repair.py`, `llm/__init__.py`, `external_evaluator.py`, etc.). Any "all glm-5.2" statement in this doc is incomplete — correct to "glm-5.2 outline agent + deepseek-v4-pro code/generator (subject to `OPENROUTER_DEFAULT_MODEL`)."
- **[TERRA] Final "hard audit" does not check numeric grounding.** `faithful = (audit["leaked_cite_ev_tokens"] == 0 and not audit["unresolved_markers"])` — only `[CITE:...]` leaks + unresolved bibliography markers. The report is also NOT assembled solely from `verified_text`: the driver emits a static introduction and optional `multi.limitations_text`. Correct the Stage-F assembly claim accordingly.
- **[TERRA] Stage G is not a fresh FACT rerun.** `deepresearch_bench_race.py` is the RACE scorer; `utils/stat.py` only *aggregates* an existing `validated.jsonl`. So "FACT 84/93 reproduced by execution" means the **stat aggregation** was reproduced — NOT the full extract→scrape→validate chain. A fresh FACT rerun needs its own entrypoint + validator model + Jina scrape (see MISSING).
- **[TERRA — downgrade] P0-item-1 overstates external cp2 as a Stage-E single point of failure.** `cp3_to_cp4_corpus.py` falls back to the durable pool snapshot (`elif pool_snapshot_path.exists(): pool = snap["evidence_pool"]`), so external cp2 is **not required** for cp3→cp4 when `data/cp2_evidence_pool_snapshot.json` exists. External cp2 still matters for canonical provenance / rebuilding the durable pool, but demote it from "absolute SPOF."

### MISSING (terra) — add to the minimal closure / recipe
- **[TERRA+CODE-VERIFIED] `PG_OUTLINE_WEB_SEARCH=0`** is mandatory for a frozen Stage-F replay (see above).
- **[TERRA, packet-limited] Enablement flags for the verified-compose/basket-digest lane** are NOT set by the driver: `PG_VERIFIED_COMPOSE=1` (default off) and `PG_OUTLINE_BASKET_DIGEST=1` (default off gating the cited `:3168` digest path). Confirm whether the champion depended on these; if so they must be in the recipe.
- **[TERRA+CODE-VERIFIED] Section parallelism is the CLI arg `--max-parallel 3`** (driver `:128`, passed as `max_parallel_sections` `:258`), not (only) the env `PG_PARALLEL_SECTIONS`. Recipe should pass `--max-parallel 3`.
- **[TERRA] Stage-F prompt data file** `third_party/deep_research_bench/data/prompt_data/query.jsonl` is required by `--rq-drb-task 72` and is omitted from the minimal set.
- **[TERRA] report→benchmark bridge missing.** No command serializes a NEW timestamped `report.md` into `data/test_data/raw_data/polaris_step3_control.jsonl`; the existing JSONL only re-scores the OLD report.
- **[TERRA] agentic-outline dependency surface underlisted:** `tool_registry.py`, `analysis_notebook.py`, `react_agent.py`, `outline_checkpoint.py` (named by `outline_agent.py`); live-outline mode additionally pulls `run_live_retrieval`.

### CONFIRMED by BOTH engines (now two-engine consensus)
- `outline_digest.py` and `verified_compose.py` live under `src/polaris_graph/generator/` (correct paths).
- Stage-C keep-all under redesign (`kept = list(scored)`).
- The quant-directive trap (`setdefault(PG_SYNTHESIS_QUANT_DIRECTIVE, "1")`) → explicit `=0` override required.
- cp3→cp4 fail-closed + durable-pool fallback; non-deterministic `created_utc` timestamp makes byte output vary run-to-run.
- RACE target-vs-reference formula; `utils/stat.py` supported/non-unknown ratio.

> **RESOLVED — the champion is NOT frozen-corpus reproducible (proven from the mechanism artifact).** The byte-identical champion artifact was located: `outputs/step3_control/report.md` (md5 `4f57c31b83edb892be7ef795d6ef8d05` == `SECURED_0.44_champion/champion_0.4447_report.md`), with sidecars `bibliography.json` + `compose_summary.json` and the compose log `outputs/step3_control_compose.log`.
> - **Live search fired during compose:** the outline agent's `live_retriever` ran **9 SERPER + 10 Semantic-Scholar rounds** and folded in **107 new rows** via `auto-assign: routed N new ev_id(s)`. `997 (cp4) + 107 = 1104` = `compose_summary.evidence_rows` exactly.
> - **Citations:** of the 37 rendered references, **14 are in cp4, 23 are NOT** (every absent id is `ev_1271+`, above cp4's `ev_1270` ceiling). The 23 include all 4IR-framing sources (weforum, wikipedia, tomorrow.city) and headline-stat sources (Morgan Stanley, ILO brief, IZA dp17554, NU blog); ~17 are works cp4 cannot supply at all, ~6 are live-fetched duplicates of works cp4 holds.
> - **Consequences:** (1) **cp4 alone cannot reproduce the champion** — the real reproduction corpus is the **1104-row post-live-fold pool** (cp4 997 + 107 live rows), whose preservation status must be established. (2) The "open-weight / frozen 997-corpus" framing is **false** for this champion — ~62% of citations came from live SERPER/S2. (3) Even with `PG_OUTLINE_WEB_SEARCH=0`, the champion does not regenerate; a frozen re-run is a *different* report. Full evidence: `citation_verify.md`.

---

## 0. PRESERVATION PUNCH-LIST (merged, de-duplicated, severity-ordered)

Merged from the draft punch-list + Opus verifier `missing_for_full_body` + terra second-engine items (§0.5). Each item is concrete: what file/artifact to snapshot or what code to restore.

### P0 — external single-points-of-failure (copy into repo + commit)
1. **Copy the external canonical cp2** `/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json` (13.2 MB, sha256 `e6c77bcff2…`) into `data/` and commit. It is the TRUE Stage-D input and the default `--cp2` for Stage E; currently external-only.
2. **Copy the raw Stage-A pool** `/workspace/POLARIS/outputs/paid_drb72_deep/workforce/drb_72_ai_labor/corpus_snapshot.json` (13.4 MB) + `live_corpus_dump.json` + `protocol.json` + `run_log.txt` + `sweep_summary.json` into a committed `champion_stageA/`. **This same file already contains `retrieval.evidence_rows` (1106 rows) — the Stage-C selector INPUT pool — and the per-source origin distribution (serper / serper_statistical_agency / s2 / frame).** Copying it therefore closes THREE gaps at once: the crashed-harvest record, the Stage-C pre-selection pool, and the source-origin breakdown that the durable pool drops. (Opus: this is why old punch-list #9 was wrong to say the pool "isn't saved.")
3. ~~**Extract and commit the cp3 `s3_consolidate` checkpoint serializer** — "NO repo code can produce the cp3 schema."~~ **[OVERTURNED by main-session verification]** This was a grep artifact: `s3_consolidate` is a stage-*label string*, not a function. The cp3 checkpoint serializer IS in the repo — `src/polaris_graph/generator/generation_snapshot.py:407` and `src/polaris_graph/generator/outline_checkpoint.py:100` emit the exact schema (`faithfulness_invariant`/`flag_slate`/`payload`), driven by `scripts/run_honest_sweep_r3.py:6883/6919/7045`, with `tests/polaris_graph/test_outline_checkpoint.py` asserting the key order. **No action needed — the producer is on-lineage.** (Both the Opus finder and terra missed this via literal `grep s3_consolidate`.)
4. **Pin the FACT score chain inside SECURED.** Copy `results/fact/polaris_step3_control/{extracted,deduplicated,scraped,validated}.jsonl` + a regenerated `fact_result.txt` into `SECURED_0.44_champion/`. FACT 90.3% (84/93) is reproducible by execution TODAY but lives only in the **uncommitted** working tree `third_party/deep_research_bench/results/fact/` — a real single-point-of-loss (Opus reaffirmed).

### P1 — integrity + article pinning
5. **Add a checked-in hash manifest** tying the four durable `data/` artifacts (cp2 pool, cp3, cp4) and the report to the external cp2/Stage-A snapshots by sha256. No committed checksums exist today, so silent drift of the committed corpus would go undetected (Opus).
6. **Snapshot `data/test_data/raw_data/polaris_step3_control.jsonl`** (article 29240 chars) alongside the report and assert `article == champion_0.4447_report.md` in a checked-in check.

### P2 — branch-divergent + config surface
7. **Vendor `src/polaris_graph/retrieval/line_screen.py` + `scripts/s2_select_replay.py`** (branch `bot/sec-s2-select`, commit `d3864ea`, NOT an ancestor of HEAD `df4118a`) into a documented `stageB_line_screen/` so the stamp producer is on-lineage, even though default-OFF.
8. **Write `CHAMPION_ENV.lock`** capturing the full force-applied slate from `run_gate_b.py:main()` + the compose `setdefault` list, with `PG_SYNTHESIS_QUANT_DIRECTIVE=0` flagged as the mandatory override (the flag trap).
9. **Resolve the `.env` symlink risk:** document `.env → /workspace/POLARIS/.env` and store a redacted `.env.template` listing every required key (OPENROUTER, SERPER, S2, Zyte, JINA).
10. **Annotate the Stage-F repro command:** `git checkout df4118a` **detaches HEAD to the same commit** HEAD already points at (branch `bot/outline-agent-box`). Harmless but should be documented so a reproducer is not surprised by a detached-HEAD state (Opus).

### P3 — lift stages toward `code`
11. **Build a standalone Stage-C replay harness** that feeds the saved `retrieval.evidence_rows` pool (already present inside the P0-item-2 `corpus_snapshot.json` — 1106 rows) + frozen protocol/anchors into `select_evidence_for_generation` under the Gate-B slate. **Correction vs draft:** the pool is NOT unsaved; the fix is *copy it into `data/` and write the harness*, not *first preserve a pool that does not exist*.
12. **Add a golden-file assertion for Stage E** (`cp3_to_cp4_corpus.py`) so the deterministic join is guarded beyond its fail-closed raise.
13. **Enable a non-zero `retrieval_trace.jsonl` writer** on any future harvest to record the FS-Researcher sub-query sequence (champion's is 0 bytes).

**Reconciliation flags to resolve (do not silently drop):** "~856 sources" (deduped-unique, not stored) vs on-disk `classified_sources=1061`; "84 verified citations" (prior anchor) vs 37 `[N]`/37 refs in the scored report; `evidence_id` rename `ev_{i:03d}` → v30 entity ids (992/997) where the renaming layer was not traced; per-source origin distribution present only in the external `corpus_snapshot.json`, dropped from the committed durable pool.

---

## 1. EXECUTIVE MAP — the end-to-end DAG

All 8 stage entrypoints and all 6 critical-path handoff line numbers below were re-verified EXACT against on-disk state by the Opus verifier. [CONFIRMED]

| # | Stage | Entrypoint (file:line) | One-line purpose | Input artifact → Output artifact |
|---|-------|------------------------|------------------|----------------------------------|
| A | QUERY INTAKE + SUB-QUERY PLANNING + RAW RETRIEVAL | `scripts/dr_benchmark/run_gate_b.py:6295` (`main()`) | Bind official task-72 question, force benchmark slate, live-harvest the web into a raw source pool | DRB-II idx-56 question + SWEEP_QUERIES seed queries → `corpus_snapshot.json` (classified_sources=1061, evidence_for_gen=999) |
| B | FETCH/SCRAPE → FULLTEXT → SPAN EXTRACTION → EVIDENCE ROWS | `src/polaris_graph/retrieval/live_retriever.py:5405` (`run_live_retrieval()`) | Fetch/scrape candidates, extract fulltext, mint one grounded evidence row per surviving source | live network + query → `cp2_corpus_snapshot.json` / `data/cp2_evidence_pool_snapshot.json` (997 rows) |
| C | EVIDENCE SELECTION ("mining") | `src/polaris_graph/retrieval/evidence_selector.py:2796` (`select_evidence_for_generation()`) | Relevance-floor / tier weighting from span pool to `evidence_for_gen` (≈997); WEIGHT-not-drop under redesign | `retrieval.evidence_rows` (1106) → `evidence_for_gen` (≈996 + 1 referenced-only) |
| D | CONSOLIDATION & CLUSTERING | `src/polaris_graph/synthesis/finding_dedup.py:1946` (`dedup_by_finding()`) | Same-work fold + numeric/qualitative basketing + 3 NLI union passes → cp3 basket artifact | cp2 `evidence_for_gen` → `data/cp3_s3gear_329basket_snapshot.json` (baskets=329, same_work=55 multi-member) |
| E | cp3→cp4 JOIN | `scripts/cp3_to_cp4_corpus.py:103` (`build_cp4_corpus()`) | Resolve basket member ids→pool indices, fail-closed, emit the compose corpus | cp3 snapshot + cp2 pool → `data/cp4_corpus_s3gear_329.json` (evidence=997, clusters=329) |
| F | COMPOSE + MULTI-SECTION GENERATION | `scripts/compose_agentic_report_s3gear329.py:124` (`main()`) → `src/polaris_graph/generator/multi_section_generator.py:9584` | Agentic outline → credibility pass → route baskets → per-section verified compose → `report.md` | `cp4_corpus_s3gear_329.json` + DRB task-72 prompt → `outputs/agentic_report_<TS>/report.md` |
| G | SCORING (RACE + FACT) | `third_party/deep_research_bench/deepresearch_bench_race.py:326` (`main()`) | Judge report vs human reference (RACE win-rate) + citation validation (FACT) | `report.md` serialized as `polaris_step3_control.jsonl` → `race_result.txt` (0.4447) + `validated.jsonl` (84/93) |

**Critical path handoffs (proven, all line numbers EXACT [CONFIRMED]):**
`run_gate_b.py:main()` → `run_gate_b_query()` (`:5588`) → `scripts.run_honest_sweep_r3.run_one_query()` (`:8816`) → `live_retriever.run_live_retrieval()` (called `:10457`) → `_save_corpus_snapshot()` (`:15065`) → evidence_selector (`:13167`) → `dedup_by_finding()` (`:14667`) → cp3 checkpoint (external) → `cp3_to_cp4_corpus.py` → `compose_agentic_report_s3gear329.py` → DRB RACE/FACT.

---

## 2. PER-STAGE DETAIL

### STAGE A — Query intake / sub-query planning / raw retrieval
**Command (snapshot_only — live re-harvest, not exact repro):**
```
cd /home/polaris/wt/outline_agent && python -m scripts.dr_benchmark.run_gate_b --only drb_72_ai_labor --official-question --out-root outputs/stageA_rerun
```
Benchmark slate is force-applied **inside `main()`**, not via env: `PG_QGEN_FS_RESEARCHER=1` (`run_gate_b.py:1526`), `PG_SWEEP_QUERY_DECOMPOSE=0`, `PG_USE_RESEARCH_PLANNER=0` (default), `PG_SWEEP_FETCH_CAP=740`, `PG_SWEEP_MAX_SERPER=100`, `PG_SWEEP_MAX_S2=100`, `PG_QGEN_PARALLEL_QUERIES=8`, `PG_SWEEP_CREDIBILITY_REDESIGN=1`, `PG_BENCHMARK_OFFICIAL_QUESTION=1`, budget cap ~$300.

Sub-query generation is a **hybrid**: (1) intent_frame clean-question substitution (`run_one_query` ~9297-9481); (2) 19 hand-authored `amplified` site:-journal seed queries baked into `SWEEP_QUERIES['drb_72_ai_labor']` (`run_honest_sweep_r3.py:7714` [CONFIRMED]); (3) FS-Researcher adaptive GLM-5.2 query rounds (`fs_researcher_query_gen.run_fs_researcher_retrieval()` `:10293`). `query_decomposer` (`:9975`) and `research_planner` (`:9794`) are present but OFF.

**Load-bearing modules:** `run_gate_b.py`, `gate0_lineage.py` (idx-56 binding, `:39`; `drb_72_ai_labor`→56 [CONFIRMED]), `run_honest_sweep_r3.py` (`run_one_query`), `live_retriever.py` (serper `:821` / s2 `:924` / openalex `:1483` / domain_backends+WRRF `:1780`), `fs_researcher_query_gen.py`, `corpus_snapshot.py` (F04), `access_bypass.py`.

**On-disk artifacts:**
- `/workspace/POLARIS/outputs/paid_drb72_deep/workforce/drb_72_ai_labor/corpus_snapshot.json` (13.4 MB — THE champion Stage-A raw pool; **also contains `retrieval.evidence_rows`=1106 (the Stage-C selector input) + per-source origin fields**) [CONFIRMED external-only]
- `.../live_corpus_dump.json` (690 KB), `.../protocol.json`, `.../run_log.txt` (84 KB)
- `/workspace/POLARIS/outputs/paid_drb72_deep/sweep_summary.json` (overall_rc=1 — crashed at run_validity_gate AFTER snapshot [CONFIRMED])
- `/workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json` (13.2 MB — S2 re-snapshot)
- `/home/polaris/wt/outline_agent/data/cp2_evidence_pool_snapshot.json` (5.7 MB — durable 997-row pool)

### STAGE B — Fetch/scrape → fulltext → span → evidence rows
**Command:** No one-command regen. Invoked as `run_live_retrieval(research_question=..., amplified_queries=..., fetch_cap=...)` inside the sweep; requires live Serper/S2/OpenAlex + keys, non-deterministic. line_screen stamp path (`PG_LINE_SCREEN=1 python scripts/s2_select_replay.py`) exists **only on branch `bot/sec-s2-select` (commit d3864ea)**, not an ancestor of champion HEAD [CONFIRMED].

Row build: `live_retriever.py:7570` mints `_row = {evidence_id: ev_{i:03d}, source_url, statement, direct_quote, tier, ...}` [CONFIRMED]; `direct_quote` from `_build_provenance_quote()` (`:4750`, head cap 1500 / window 500). Fetch-shell reject at `:7554`.

- **Source distribution** (serper 761, serper_statistical_agency 220, s2 11, frame/prepend 5): **[GAP]** — present ONLY in the external `corpus_snapshot`/`cp2_corpus_snapshot` files; the committed durable `cp2_evidence_pool_snapshot.json` carries NO source-origin field (keys: authors, direct_quote, doi, evidence_id, journal, line_screen, pmid, provenance_class, source_url, statement, tier, title, v30_entity_id, v30_frame_row, year). Not proven wrong — dropped on worktree detach. See punch-list P0-item-2.
- **997 rows over 919 unique URLs** — **corrected from draft's "920"**: the durable `cp2_evidence_pool_snapshot.json` has 919 distinct `source_url` values (Opus, off-by-one against committed artifact) [CONFIRMED, corrected]. **No span-explosion** — one provenance span per source.

**Env flags:** `PG_OUTLINE_AGENT=1`, `PG_LINE_SCREEN` (default OFF, module absent on HEAD), `PG_SWEEP_CREDIBILITY_REDESIGN=on`, fetch caps.
**Load-bearing modules:** `live_retriever.py`, `corpus_snapshot.py` (save `:90` / load `:147`), `fetch_snapshot.py` (`:102`), `line_screen.py` (BRANCH-ONLY), `cp3_to_cp4_corpus.py` (`_carry_stamps`).
**On-disk artifacts:** `data/cp2_evidence_pool_snapshot.json` (5.7 MB, 997 rows), `data/cp3_s3gear_329basket_snapshot.json`, `data/cp4_corpus_s3gear_329.json`.

### STAGE C — Evidence selection ("mining")
**Command (live-harvest, not re-run in champion repro):** `run_gate_b.py` drives `run_honest_sweep_r3.py` with the certification slate over live retrieval; requires Qwen3-Embedding-8B relevance embedder + network. The champion **reproduction** (`compose_agentic_report_s3gear329.py:202`) never calls evidence_selector — it reads 997 rows raw [CONFIRMED].

**Key nuance:** under `PG_SWEEP_CREDIBILITY_REDESIGN=on` this stage is **NOT lossy**. `_relevance_floor_selection` (guard `if _redesign_on:` at `:2455`) executes `kept = list(scored)` at **`:2459`** (keep-all) — **corrected from draft's `:2455`**; the guard is at ~:2455, the assignment at :2459 (Opus, semantics unchanged) [CONFIRMED, corrected]. The 0.30 floor + semantic_v2 cosine only drive the sort key. `PG_LIVE_MAX_EV_TO_GEN=1500` is **dormant** (floor branch has no max_rows cap; `PG_CAPPED_FINDING_DEDUP=0` skips re-cap).

**Selector INPUT pool — MAJOR correction vs draft.** The draft claimed "No on-disk artifact of the selector INPUT (`retrieval.evidence_rows` pre-selection pool)" and that it must be "first preserved." **This is false.** `retrieval.evidence_rows` = **1106 rows** already lives inside the external `corpus_snapshot.json` listed above under Stage A. The pre-selection pool therefore EXISTS (externally); it does not need to be preserved — it needs to be COPIED into the repo (punch-list P0-item-2), after which a standalone replay harness can be fed the saved 1106-row pool today (punch-list P3-item-11) [CONFIRMED — Opus, verified against the very file the draft itself lists].

**Env slate (`run_gate_b.py`):** `PG_RELEVANCE_FLOOR=0.30` (`:920`), `PG_LIVE_MAX_EV_TO_GEN=1500` (`:791`), `PG_USE_FINDING_DEDUP=1` (`:903`), `PG_CAPPED_FINDING_DEDUP=0` (`:919`), `PG_SELECT_SUBQUERY_FLOOR=1` (`:941`), `PG_RELEVANCE_SCORER=semantic_v2` (`:949`), `PG_SWEEP_CREDIBILITY_REDESIGN=1` (`:951`).
**Load-bearing modules:** `evidence_selector.py` (whole stage), `prefetch_offtopic_filter.py`, `constraint_enforcement.py`, `primary_trial_expander.py`, `run_honest_sweep_r3.py` (~:12786-13177), `run_gate_b.py`.
**On-disk artifacts:** `data/cp4_corpus_s3gear_329.json` (evidence=997), `data/cp2_evidence_pool_snapshot.json`, `data/cp3_s3gear_329basket_snapshot.json`, `SECURED_0.44_champion/RECIPE.md`.

### STAGE D — Consolidation & clustering
**Command:** No in-repo command writes the cp3 `s3_consolidate` schema (the serializer is external) [CONFIRMED — `grep s3_consolidate` → 0 repo producers]. Consolidation logic re-runs via `python scripts/breadth_replay_harness.py --corpus <cp2 corpus_snapshot.json> --domain workforce --baskets --no-verify` — this harness EXISTS, accepts `--baskets`/`--no-verify`, and invokes the REAL `dedup_by_finding` (so the command is valid as **logic only**; it emits a verification report, NOT the cp3 payload) [CONFIRMED].

**Funnel (from cp3 `consolidation_summary`):** raw_row_count=687 → basket_total=329 (320 numeric distinct + 9 qualitative) [CONFIRMED cp4 basket_total=329]. collapsed_row_count=6, nli_merge_count=11, rep_invariant_merge_count=3. same_work: 582 groups, 55 multi-member [CONFIRMED same_work_groups=55], 2 CAPTCHA + 4 prefix dropped. Multi-member baskets dist 1:291, 2:22, 3:14, 4:2.

Three NLI pair caps (all default 20000, all fail to UNDER-merge keep-all): `PG_CONSOLIDATION_NLI_MAX_PAIRS` (`consolidation_nli.py:208`; n_texts=226→25425 pairs scored fully via W04 sub-bucketing, edges=71), `PG_FINDING_DEDUP_NLI_MAX_PAIRS` (`finding_dedup.py:1110`), `PG_FINDING_DEDUP_QUALITATIVE_NOMINATE_MAX_PAIRS` (`finding_dedup.py:1381`).

**Env flags:** `PG_SWEEP_CREDIBILITY_REDESIGN=1`, `PG_FINDING_DEDUP_QUALITATIVE=1`, `PG_CONSOLIDATION_NLI=1`, `PG_FINDING_DEDUP_NLI=1` (default-OFF, slate-ON), `PG_BASKET_CONSUME_FINDING_DEDUP=1`, wall 180s.
**Load-bearing modules:** `finding_dedup.py`, `consolidation_nli.py`, `credibility_pass.py` (`_assemble_baskets`), `fact_dedup.py`, `domain_signal.py`, `cp3_to_cp4_corpus.py`.
**On-disk artifacts:** `data/cp3_s3gear_329basket_snapshot.json` (300080 bytes), `data/cp2_evidence_pool_snapshot.json`, `data/cp4_corpus_s3gear_329.json`.

### STAGE E — cp3→cp4 join
**Command (fully reproducible):**
```
python scripts/cp3_to_cp4_corpus.py
# defaults: --cp3 data/cp3_s3gear_329basket_snapshot.json
#           --cp2 /workspace/POLARIS/outputs/s2_hamster_i1/cp2_corpus_snapshot.json   # EXTERNAL — see punch-list P0-item-1
#           --out data/cp4_corpus_s3gear_329.json
#           --pool-snapshot data/cp2_evidence_pool_snapshot.json
```
Join (`build_cp4_corpus:103` [CONFIRMED]): `id2idx` first-occurrence-wins over pool; per basket member ids→positional indices (`:123-124`); clusters keep only `{representative_index, member_indices, corroboration_count, member_hosts, claim_group_id}`; `same_work_groups` pass-through (`:139`). Fail-closed at `:114-119`, `:172-176`, `:190-194`. `referenced_ids=425` distinct (of 997 pool; 572 attached-unreferenced), all resolve → write succeeds. cp4 top keys: `research_question, domain, evidence[997], finding_clusters[329], same_work_groups[55], basket_total=329, _provenance` [CONFIRMED headline keys/counts on disk].
**Env flags:** none. **Module:** `scripts/cp3_to_cp4_corpus.py` (single commit e3b1664). Default `--cp2` points at the external `s2_hamster_i1` path [CONFIRMED].
**On-disk artifacts:** `data/cp4_corpus_s3gear_329.json` (5.8 MB), cp3 + cp2 inputs, external `s2_hamster_i1/cp2_corpus_snapshot.json`.

### STAGE F — Compose + multi-section generation → report.md
**Command (reproducible to ~0.43-0.45, stochastic):**
```
cd /home/polaris/wt/outline_agent && git checkout df4118a && set -a && . ./.env && set +a && \
PG_OUTLINE_AGENT=1 PG_SYNTHESIS_QUANT_DIRECTIVE=0 \
python scripts/compose_agentic_report_s3gear329.py --corpus data/cp4_corpus_s3gear_329.json --rq-drb-task 72
```
> **NOTE (Opus):** HEAD is already `df4118a` (branch `bot/outline-agent-box`), so `git checkout df4118a` **detaches HEAD to the same commit** — it changes no files but leaves you in a detached-HEAD state. Documented so a reproducer is not surprised.

**FLAG TRAP:** the driver `setdefault`s `PG_SYNTHESIS_QUANT_DIRECTIVE=1` (`:181` [CONFIRMED]), but the champion config is quant-directive **OFF** (RECIPE.md). You MUST export `PG_SYNTHESIS_QUANT_DIRECTIVE=0` — the single most error-prone repro detail.

Flow inside `generate_multi_section_report` (`:9584` [CONFIRMED]): outline via `run_outline_agent_or_legacy` (`:9909`, glm-5.2, digest from `build_outline_digest` `:3168`) → credibility pass priors-only (judge=None, `PG_ALWAYS_RELEASE` ON → guard returns 'run', `:10278`) → `route_orphan_baskets_to_section_plans` (`:10615`, all 329 baskets) → per-section writer + `strict_verify` (`provenance_generator.py:3598` [CONFIRMED], drops any clause whose `[CITE:ev_xxx]` fails span match) → driver assembles `report.md` from verified_text only (`:300-316`) + `_audit_citations` tripwire (`:348-354`).
Models: writer/outliner/generator all `z-ai/glm-5.2` (`openrouter_client.py:579/:64`; default `z-ai/glm-5.2` at `:64` [CONFIRMED]). section_temp=0.3, outline_temp=0.2.

**Env flags:** `PG_OUTLINE_AGENT=1`, `PG_SYNTHESIS_QUANT_DIRECTIVE=0` (explicit), `PG_COMPOSE_BASKET_WORKERS=1`, `PG_PARALLEL_SECTIONS=3`, `PG_ROUTE_ALL_BASKETS=1`, `PG_EV_BUDGET_TRACKS_PAYLOAD=1`, `PG_SWEEP_CREDIBILITY_REDESIGN=on`, `PG_ALWAYS_RELEASE=on`, `OPENROUTER_API_KEY` (required, `.env` symlink → `/workspace/POLARIS/.env`).
**Load-bearing modules:** `compose_agentic_report_s3gear329.py`, `multi_section_generator.py`, `outline_agent.py`, `outline_digest.py`, `credibility_pass.py`, `verified_compose.py`, `provenance_generator.py`, `openrouter_client.py`, `release_policy.py`, `data_loader.py`.
**On-disk artifacts:** `SECURED_0.44_champion/champion_0.4447_report.md` (3,875 words, 37 unique `[N]` markers, 37 References [CONFIRMED]), `RECIPE.md`, `champion_0.4447_score.txt`, `data/cp4_corpus_s3gear_329.json`.

### STAGE G — Scoring reproduction (RACE + FACT)
**RACE (exact champion invocation from scorelog):**
```
cd /home/polaris/wt/outline_agent/third_party/deep_research_bench && \
LLM_BACKEND=openrouter OPENROUTER_API_KEY=*** RACE_MODEL=openai/gpt-5.5 \
/opt/conda/bin/python -u deepresearch_bench_race.py polaris_step3_control \
  --raw_data_dir data/test_data/raw_data --cleaned_data_dir data/test_data/cleaned_data \
  --query_file data/prompt_data/query_task72.jsonl --output_dir results/race/polaris_step3_control \
  --max_workers 4 --only_en --force
```
**FACT valid_rate deterministically from preserved artifact:**
```
python -u -m utils.stat --input_path results/fact/polaris_step3_control/validated.jsonl \
  --output_path results/fact/polaris_step3_control/fact_result.txt   # -> 0.9032 = 84/93
```
RACE math (`:155-170`): `overall = target_total/(target_total+reference_total)` — pairwise win-rate vs human reference (0.4447 = just below reference on task 72). Judge `openai/gpt-5.5` (reasoning medium). FACT math (`utils/stat.py:22-40`): count `result=='supported'` (84) over `result!='unknown'` (93). **FACT 84/93 = 0.9032 REPRODUCED BY EXECUTION** of `utils.stat` against the preserved `validated.jsonl` (total_citations 93.0, valid 84.0) [CONFIRMED — Opus ran it]. Validator `openai/gpt-5.4-mini`, Jina scrape.
**Env flags:** `LLM_BACKEND=openrouter`, `OPENROUTER_API_KEY`, `RACE_MODEL=openai/gpt-5.5`, `FACT_MODEL=openai/gpt-5.4-mini`, `JINA_API_KEY` (FACT scrape only).
**Load-bearing modules:** `deepresearch_bench_race.py`, `utils/api.py`, `utils/score_calculator.py`, `prompt/score_prompt_en.py`, `utils/{extract,deduplicate,scrape,validate,stat}.py`, `utils/clean_article.py`.
**On-disk artifacts:** `SECURED_0.44_champion/champion_0.4447_score.txt` + `champion_0.4447_scorelog.log`, `results/race/polaris_step3_control/{race_result.txt,raw_results.jsonl}`, `data/test_data/raw_data/polaris_step3_control.jsonl` (article 29240 chars [CONFIRMED]), `reference.jsonl`, `criteria.jsonl`, `query_task72.jsonl`, `results/fact/polaris_step3_control/{extracted,deduplicated,scraped,validated}.jsonl` (**uncommitted — see punch-list P0-item-4**).

---

## 3. REPRODUCIBILITY LEDGER (every claim tagged)

Tag key: **[CONFIRMED]** = Opus-verified against on-disk state or by execution (terra could not provide a second engine — see provenance note). **[GAP]** = claim is real but not verifiable from any committed artifact / preservation gap. **[DISPUTED]** = genuine inter-auditor conflict (NONE exist: terra produced no findings).

| Stage | reproducible_today | Repro command | Key gaps (tagged) |
|-------|--------------------|---------------|----------------------|
| A — Query/plan/retrieval | **snapshot_only** [CONFIRMED] | `python -m scripts.dr_benchmark.run_gate_b --only drb_72_ai_labor --official-question --out-root outputs/stageA_rerun` | Live web + adaptive GLM query-gen → non-deterministic [CONFIRMED]; exact source pool exists ONLY as external `corpus_snapshot.json` [CONFIRMED]. Run itself CRASHED (`overall_rc=1`) after the F04 checkpoint [CONFIRMED]. `retrieval_trace.jsonl` is 0 bytes [CONFIRMED] so exact sub-query sequence only partially recoverable. Needs paid keys + ~$300. |
| B — Fetch→span→rows | **snapshot_only** [CONFIRMED] | none (invoked as `run_live_retrieval(...)` inside sweep) | 856-source RAW FETCH layer not preserved (no `fetch_snapshot.json`) [GAP]. `line_screen` producer only on branch d3864ea, not ancestor of HEAD, default-OFF [CONFIRMED]. Canonical cp2 external; only durable pool re-snapshot survives (key `evidence_pool`) [CONFIRMED]. 997 rows over **919** unique URLs [CONFIRMED, corrected from 920]. Source-origin distribution not in any committed artifact [GAP]. |
| C — Evidence selection | **snapshot_only** [CONFIRMED] | (live slate; keep-all → bypassed in reproduction, `compose…:202` reads 997 raw [CONFIRMED]) | Selector INPUT pool `retrieval.evidence_rows`=1106 **IS saved** — inside the external `corpus_snapshot.json` [CONFIRMED, MAJOR correction to draft]. Fix = copy into `data/` + build replay harness [GAP: not yet in repo]. Keep-all `kept = list(scored)` at `:2459` [CONFIRMED, corrected from :2455]. |
| D — Consolidation/clustering | **snapshot_only** [CONFIRMED] | `python scripts/breadth_replay_harness.py --corpus <cp2> --domain workforce --baskets --no-verify` (logic only, real `dedup_by_finding`) [CONFIRMED] | NO in-repo producer of the cp3 `s3_consolidate` schema; serializer EXTERNAL; `grep s3_consolidate` → 0 [CONFIRMED, GAP]. True cp2 input external [CONFIRMED]. Logic deterministic + code-present (only external dep = resident NLI cross-encoder), but snapshot writer is not [CONFIRMED]. |
| E — cp3→cp4 join | **code** [CONFIRMED] | `python scripts/cp3_to_cp4_corpus.py` | Deterministic substantive payload; only `created_utc` changes byte-hash [CONFIRMED]. No golden-file test; correctness rests on fail-closed raise only [GAP]. Inputs (cp2/cp3) themselves upstream snapshot-only [CONFIRMED]. |
| F — Compose/generation | **code** (stochastic) [CONFIRMED] | `... PG_OUTLINE_AGENT=1 PG_SYNTHESIS_QUANT_DIRECTIVE=0 python scripts/compose_agentic_report_s3gear329.py --corpus data/cp4_corpus_s3gear_329.json --rq-drb-task 72` | Path fully present + runnable BUT stochastic (glm-5.2 live, temp 0.3/0.2) → reproduces ~0.43-0.45, not byte-identical [CONFIRMED]. FLAG TRAP: must export `PG_SYNTHESIS_QUANT_DIRECTIVE=0` [CONFIRMED]. `git checkout df4118a` detaches HEAD to same commit [CONFIRMED, noted]. Prior "84 verified citations" NOT supported by on-disk report (37 `[N]`/37 refs) [CONFIRMED]. |
| G — Scoring (RACE+FACT) | **code** (stochastic) [CONFIRMED] | RACE: `deepresearch_bench_race.py polaris_step3_control … --only_en --force`; FACT: `python -u -m utils.stat --input_path .../validated.jsonl …` | RACE judge = live gpt-5.5 → ~0.43-0.45 (±0.016), not bit-exact [CONFIRMED]. FACT `fact_result.txt` NOT on disk but valid_rate reproduced by execution to 84/93 [CONFIRMED]. FACT jsonl chain uncommitted, not pinned inside SECURED [CONFIRMED, GAP]. |

**Bottom line:** Stages E, F, G are `code`-reproducible (E deterministic; F/G stochastic-to-distribution). Stages A, B, C, D are `snapshot_only` — the champion's exact intermediate artifacts survive on disk, but no in-repo command regenerates them, and the two earliest stages depend on live paid network + a run that crashed post-checkpoint.

---

## 4. MINIMAL CLOSURE — regenerate a champion report from a raw query

### 4a. From a RAW QUERY (full live path)
Code/config, env slate, model endpoints unchanged from draft (all entrypoints re-verified EXACT). The **[AT RISK — no repo copy]** items are: the EXTERNAL cp3 `s3_consolidate` serializer (only in `/workspace/POLARIS` sweep harness) and the `.env` symlink → `/workspace/POLARIS/.env`. See punch-list P0-item-3 and P2-item-9.

### 4b. From the FROZEN corpus (the actually-reproducible champion path — RECIPE.md)
```
data/cp4_corpus_s3gear_329.json  --(Stage F compose, glm-5.2)-->  report.md  --(Stage G RACE/FACT)-->  0.4447 / 90.3%
```
Minimal set: `data/cp4_corpus_s3gear_329.json` + `scripts/compose_agentic_report_s3gear329.py` + the Stage-F module set + `OPENROUTER_API_KEY` + GLM-5.2, then Stage-G scorers. Everything upstream of cp4 is replaced by the frozen snapshot. cp4 is itself rebuildable from `data/cp3_s3gear_329basket_snapshot.json` + `data/cp2_evidence_pool_snapshot.json` via `cp3_to_cp4_corpus.py` (Stage E, `code`) — **but note Stage E's default `--cp2` points at the EXTERNAL `s2_hamster_i1` path** (punch-list P0-item-1).

### 4c. AT-RISK closure items
- **MISSING in repo:** the cp3 `s3_consolidate` checkpoint serializer (external only) [CONFIRMED].
- **EXTERNAL, not on local repo disk:** canonical cp2 (13.2 MB) + raw Stage-A pool (13.4 MB, which also holds the 1106-row selector-input pool + source-origin fields) [CONFIRMED].
- **NON-REGENERABLE:** 856-source raw fetch layer; `line_screen` stamps (branch-only producer); exact per-round FS-Researcher sub-query sequence (`retrieval_trace.jsonl` 0 bytes) [CONFIRMED].
- **BRANCH-DIVERGENT:** `line_screen.py` + `s2_select_replay.py` on `bot/sec-s2-select` (d3864ea), not an ancestor of HEAD `df4118a` [CONFIRMED].
- **NOT PINNED IN SECURED:** FACT jsonl chain lives only in uncommitted `results/fact/polaris_step3_control/` [CONFIRMED].

---

## 5. FINAL VERDICT

The champion's full end-to-end body is **partially preserved and only partially reproducible today**. The back half of the pipeline (Stages E→F→G, cp4 → report → 0.4447 / 84-93 FACT) is genuinely `code`-reproducible from committed artifacts: Stage E is deterministic, Stages F and G reproduce to distribution (~0.43-0.45) given live GLM-5.2 / gpt-5.5 keys, and the 84/93 FACT rate was re-derived BY EXECUTION during this audit. Every entrypoint file:line, every critical-path handoff, and every headline figure verified EXACT. But the front half (Stages A-D, query → cp3) is **snapshot_only and leans on artifacts that live outside the committed repo**, and the second-engine (Codex-terra) audit never ran, so this reconciliation rests on a single verifier. The top-3 at-risk pieces, in order: (1) the **cp3 `s3_consolidate` serializer** — no repo code can produce the cp3 schema at all, so Stage D is unregenerable if the external `/workspace/POLARIS` harness is lost (P0-item-3); (2) the **external canonical cp2 + raw Stage-A `corpus_snapshot.json`** (13.2 MB + 13.4 MB) — Stage E's default input, the 1106-row Stage-C selector pool, AND the source-origin distribution all vanish on a worktree detach (P0-items-1/2); (3) the **uncommitted FACT jsonl chain** — the 90.3% number is one `rm -rf` in an untracked results tree away from being unreproducible, and is not yet inside SECURED (P0-item-4). Net: preserve those three and the champion becomes fully reconstructable end-to-end; leave them and the body is one detached worktree away from losing its entire front half.
