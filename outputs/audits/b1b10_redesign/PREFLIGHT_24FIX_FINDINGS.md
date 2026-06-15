# I-arch-005 PRE-RUN PREFLIGHT — consolidated findings (NO-GO)

**Purpose:** before the 3-hour paid beat-both run, verify all 24 fixes (+M-44 +GAP1) are not just committed but actually FIRE on the real `run_gate_b --only` path. Operator demanded this ("don't waste 3 hours and find we fucked").

**Method:** two independent lanes. Claude lane = Workflow `wtm1qs471` (per-fix present/wired/flag/faithfulness + adversarial refuter). Codex lane = 3 parallel sessions (A retrieval/gov, B SWEEP always-emit, C SECTION). HEAD = `3c238c6b`, branch `bot/I-arch-002-no-dumping` (= VM `polaris_run`).

**Verdict so far: NO-GO.** Codex B + Codex C both returned NO-GO and CONVERGE on the same root causes. Codex A + the Claude Workflow still running (this doc updated on landing). **The fixes are all PRESENT and FAITHFULNESS-SAFE — the failures are pure WIRING: several fixes are dead on the benchmark path because Gate-B's forced-flag / timeout-slate block is stale.** No faithfulness risk found.

---

## BLOCKER ROOT CAUSE 1 — Gate-B does not force `PG_SWEEP_CREDIBILITY_REDESIGN` (kills the KEYSTONE + 2 more)

The forced-flag block in `run_gate_b.py:1344-1422` forces the V30 pair (PG_V30_PHASE2_ENABLED / PG_V30_ENABLED) + PG_FOUR_ROLE_MODE etc., but does NOT set `PG_SWEEP_CREDIBILITY_REDESIGN`. That single missing flag leaves these DEAD on a normal `--only` run:

- **B6/B8 multi-citation basket render (KEYSTONE).** The basket producer only runs when the flag is truthy (`multi_section_generator.py:6014-6022`). Flag-off → `credibility_analysis` stays None → `_baskets` None → `_carry_baskets` false → no basket members render on the V30 contract path (`contract_section_runner.py:922-950`). The keystone whole-basket render NEVER FIRES on the benchmark. (Faithfulness logic itself is correct when active: SUPPORTS-only, no cross-claim expansion — `provenance_generator.py:2748-2822`.)
- **B12 credibility label + B12-completion guard.** Both behind the same flag (`multi_section_generator.py:6022`). On the benchmark the credibility-unscored label + the judge=None always-release degrade never execute.

**Fix:** force `PG_SWEEP_CREDIBILITY_REDESIGN=1` in the Gate-B forced-flag block (it is the campaign's intended path — B6/B8 IS the credibility redesign). Verify no unintended side path activates; add to the preflight required-flags floor. Codex-gate.

## BLOCKER ROOT CAUSE 2 — Gate-B timeout SLATE still enforces the OLD inverted values (kills B20/B21/B24 + leaves the paid path with NO run-level hang guard)

The B21/B24 right-sizing landed only in the MODULE DEFAULTS; the Gate-B SLATE that overrides them at runtime was NOT updated, and its preflight floors actively REQUIRE the old values:

- `run_gate_b.py:470-481` slate sets `PG_GENERATOR_LLM_TIMEOUT_SECONDS=6500` (overrides B24's 600) and `PG_SECTION_WALLCLOCK_SECONDS=9000` (overrides B21's 1800).
- `run_gate_b.py:1008-1013` preflight REQUIRES the 9000 section floor; `run_gate_b.py:1171-1183` preflight FAILS if the live generator timeout is below 6500. So even the right module default is force-reverted + floor-locked.
- **Worst:** B20 run-level wall-clock (`asyncio.wait_for`) exists ONLY in `run_honest_sweep_r3.main_async:10417-10433`. The paid path is `run_gate_b.py:1962 asyncio.run(run_gate_b_query)` → `run_gate_b_query` directly `await run_one_query` (`run_gate_b.py:1462-1470`) with NO wait_for / deadline. **On the real run there is NO run-level hang guard — the exact drb_76 silent-hang the fix was meant to kill.** Gate-B also never sets `PG_RUN_WALL_CLOCK_SEC`.

Effective paid ordering today: per-call 6500 / section 9000 / run-wall absent — the requested 600 < 1800 < 7200 is NOT in force.

**Fix:** update the Gate-B slate to the right-sized values (generator 600, section 1800), set `PG_RUN_WALL_CLOCK_SEC=7200`, flip the preflight floors to match (require ordering per-call < section < run-wall, not the old absolutes), and PORT B20's `asyncio.wait_for(run_one_query, run_wall)` + timeout-finalizer into `run_gate_b_query` (so the paid path has the run-level guard). Reconcile the explicit 1200s contract-slot stall timeout (`multi_section_generator.py:6161-6221`). Codex-gate.

## BLOCKER ROOT CAUSE 3 — `run_one_query` calls the LEGACY conflict entrypoint (kills B13)

`run_one_query` calls `detect_semantic_conflicts_for_rows` (`run_honest_sweep_r3.py:5624-5633`), not `detect_semantic_conflicts_for_rows_with_unscored`. When `unscored_out` is None the conflict_unscored label is skipped instead of surfaced to manifest glue (`semantic_conflict_detector.py:330-339`).

**Fix:** switch the call to the `_with_unscored` variant + thread `unscored_out` into the disclosed-gaps manifest glue. Codex-gate.

---

## PASSED (PRESENT + WIRED + FAITH + FLAG ok) — per Codex B + C
- B2/B3 budgets default (PG_GEN_ROW_CAPS escape hatch off, char budget 120000, _budget_trim_ev_ids on default path, tail-drop telemetry).
- B5/B7 strict_verify + 4-role LABEL-not-block; D8 binding gate intact (NOT bypassed); D8 HOLD still withholds findings body.
- B11 Universal Artifact Finalizer (finally, every non-hang exit; no-op on existing report).
- B15-B19 post-success holds → labels under always-release; OFF path preserves abort_* + return (#1071 intact).
- B23 status-schema parity CI gate (genuine AST scan, no whitelist, bites on injected status).
- M-44 default outline path no count-eviction (count-pop only under PG_GEN_ROW_CAPS); V30 contract plans preserved.
- GAP1 --resume threaded 3 hops → _resume_active reconstruct; default OFF byte-identical.

## CODEX A (retrieval/governance) — landed, NO-GO, same root cause
- **B1 semantic scorer DEAD** — only runs when `PG_RELEVANCE_SCORER=semantic_v2` (evidence_selector.py:589,596); Gate-B sets PG_RELEVANCE_FLOOR etc. but NOT PG_RELEVANCE_SCORER, and the required-flag list (run_gate_b.py:770) omits it. Relevance-floor selection runs on the OLD lexical scorer. Faithfulness untouched.
- **B4 retrieval relevance gate DEAD** — `PG_RETRIEVAL_RELEVANCE_GATE` defaults OFF (live_retriever.py:3145,3164); unset → falls back to legacy `_rerank_and_reserve` (live_retriever.py:3786). Gate-B doesn't set/require it. Faithfulness untouched.
- **B9 — PASS** (PRESENT+WIRED+FAITH+FLAG): general-by-default domain spine; run path reads q["domain"]; blank→general; explicit non-clinical never routes clinical.
- **B10 — runtime CLEAN (not a run blocker)**: no gemma reaches any role/side-judge (all default GLM/deepseek/minimax/qwen); token resolver default-on, reads live /models, clamps only down. ONLY gap = DEMO/TEST fixtures still contain gemma strings (build_canonical_demo_bundle.py:150,217; some web/public + tests/fixtures bundle metadata) — NOT on the run_gate_b path. **P2 cleanup follow-up, does NOT gate the run.**

## CONSOLIDATED RUN-GATING BLOCKERS (all 3 Codex lanes, unanimous) — ONE root cause + 1 call swap
The single dominant root cause: **Gate-B's slate / forced-flag / required-flag / timeout block in `run_gate_b.py` is stale.** Fix = activate the flags + right-size the timeout slate + add the run-level guard + swap one call:
1. Set `PG_RELEVANCE_SCORER=semantic_v2` (→ B1) + add to required-flags floor.
2. Set `PG_RETRIEVAL_RELEVANCE_GATE=1` (→ B4) + required-flags floor.
3. Set `PG_SWEEP_CREDIBILITY_REDESIGN=1` (→ B6/B8 KEYSTONE + B12 + B12-completion) + required-flags floor.
4. Swap `run_one_query`'s conflict call to `detect_semantic_conflicts_for_rows_with_unscored` + thread `unscored_out` → manifest glue (→ B13). [run_honest_sweep_r3.py:5624-5633]
5. Timeout slate: set `PG_GENERATOR_LLM_TIMEOUT_SECONDS=600`, `PG_SECTION_WALLCLOCK_SECONDS=1800`, `PG_RUN_WALL_CLOCK_SEC=7200`; FLIP the preflight floors (currently require 6500/9000 — change to assert ordering per-call<section<run-wall); add `asyncio.wait_for(run_one_query, run_wall)` + B11 timeout-finalizer to `run_gate_b_query` (→ B20/B21/B24). [run_gate_b.py:470-481, 1008-1013, 1144-1183, 1462-1470]

**ACTIVATION CAVEAT (new preflight item):** flags 1-3 make the benchmark run the new semantic scorer + relevance gate + credibility-basket path for the FIRST time end-to-end. B1's semantic_v2 needs an embedding model — confirm it loads on the CPU-only VM (sentence-transformers cached) or B1 fails. This is exactly why a single cheap CANARY question must run + be §-1.1-audited BEFORE the full 5-Q spend.

## CRITICAL — B24's timeout VALUES are themselves wrong (deeper finding while building the fix)
The preflight checked WIRING, not whether B24's new values (gen 600 / section 1800 / run-wall 7200) are correct. They are NOT:
- The slate comment (I-arch-004 A2 #1248, run_gate_b.py:473-481) sized gen=6500/section=9000 deliberately: a big section budget is 64000 tokens at ~15 tok/s = ~4250s, and **"the drb_72 death was the 600s wall-clock killing the V30 section mid-stream x2."**
- Real completed drb_72 run: `elapsed_s = 5179.9` (~86 min total). So a legit single-query run is ~86 min; sections finish in minutes typically but a near-max section can be long.
- => B24's gen=600s would TRUNCATE sections → empty report → a 3-hour waste of the OPPOSITE kind. Do NOT apply B24's literal values.

**Corrected sizing (no truncation + clean ordering + real run-level guard):** keep generous per-call/section timeouts, add the MISSING run-level wait_for. Proposed ordered hierarchy (all > the observed 86-min real run, none low enough to truncate a real section): **generator ~3600s < section-wall ~5400s < run-wall ~9000s**. The real hang fix is the run-level `asyncio.wait_for` backstop on the paid path + correct ordering, NOT shrinking the per-call timeout. Codex must review the SIZING specifically.

## CLAUDE WORKFLOW (wtm1qs471) — landed, NO-GO, 4th lane
- **Triple-confirms B1**: PG_RELEVANCE_SCORER defaults 'lexical', NO setter anywhere in slate/force-on/force-exact/required-flags/inline/preflight or any env/sh/yaml → embedding scorer + restored relevance filter never run (keep-all). (Codex A + Workflow + my reading all agree.)
- **B16 hardening (non-blocking warning)**: PG_REDACT_HELD_UNSUPPORTED reads default '1' (run_honest_sweep_r3.py:9025) but is NOT force-pinned → a stray operator =0 would skip the B16 reconciliation/quarantine block. Recommend force-pin. (B16 itself = GO; this is defense-in-depth.)
- Note: ~23 verify-agents hit API rate limits (3 Codex + 28-agent workflow ran concurrently — over-parallelized). Key findings (B1, B16) still produced; B1 is independently triple-confirmed so the cross-check holds.

## FIXES APPLIED so far (run_gate_b.py, UNCOMMITTED, parse-OK)
- B1: force `PG_RELEVANCE_SCORER=semantic_v2` in the forced-flag block + value-equals preflight assertion (fail-closed if not semantic_v2).
- B4: force `PG_RETRIEVAL_RELEVANCE_GATE=1` + added to required-flags floor.
- B6/B8/B12: force `PG_SWEEP_CREDIBILITY_REDESIGN=1` + added to required-flags floor.
- B16 hardening: force-pin `PG_REDACT_HELD_UNSUPPORTED=1`.

## FIX PROGRESS — 5 of 6 blockers done (parse-OK, uncommitted)
- DONE B1/B4/B6-8/B12 (run_gate_b.py forced-flag block + required-flags floor + PG_RELEVANCE_SCORER value-equals assertion).
- DONE B16 hardening (run_gate_b.py force-pin PG_REDACT_HELD_UNSUPPORTED=1).
- DONE B13 (run_honest_sweep_r3.py:5624): swapped to `detect_semantic_conflicts_for_rows_with_unscored`, attaches `conflict_unscored` to the `retrieval` dataclass carrier → the EXISTING glue (`_collect_judge_unscored_labels` at the manifest write ~:9902) routes it to disclosed_gaps. Faithfulness unchanged.

## REMAINING — the last + most delicate (then Codex-gate ALL + RE-RUN preflight)
- **B20/B21/B24 (timeout)**: add the MISSING run-level `asyncio.wait_for` to `run_gate_b_query` (REPLICATE the proven main_async pattern at run_honest_sweep_r3.py:10417-10433, incl. the timeout-finalizer — do NOT freelance) + set `PG_RUN_WALL_CLOCK_SEC` + flip the slate values (run_gate_b.py:480-481, 6500/9000) + the preflight floors (1008-1013 require 9000, 1144-1183 require ≥6500) to a clean ordered hierarchy. **CORRECTED sizing (NOT B24's 600/1800 — that truncates per #1248 + the 86-min real run): generator ~3600 < section ~5400 < run-wall ~9000.** Codex must scrutinize the sizing specifically.

## ACTIVATION CAVEAT (carry to the canary): flags B1/B4/B6-8 run NEW paths end-to-end for the first time; B1 needs an embedding model on the CPU-only VM — the single cheap canary + §-1.1 audit must confirm before the 5-Q spend.

## FIX PLAN (after A + Workflow land; surgical, Codex-gated, faithfulness untouched)
All three root causes are WIRING/activation fixes in `run_gate_b.py` (+ one call swap in `run_honest_sweep_r3.py`). None touches a faithfulness gate. Build via Claude Codex Workflow, Codex the only gate, then RE-RUN this preflight to confirm GO before any spend.
