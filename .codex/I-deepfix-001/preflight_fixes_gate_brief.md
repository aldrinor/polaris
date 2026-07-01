HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Reserve P0/P1 for real execution risks. Verdict APPROVE iff zero NOVEL P0 AND zero P1.

# Codex gate — I-deepfix-001 preflight fixes (make the winner slate fail-closed + STORM dead + WS-0 on)

## Why (the bug this fixes)
A paid drb_72 Gate-B run silently ran a NON-WINNER config: the FS-Researcher query-gen WINNER
(`PG_QGEN_FS_RESEARCHER`, module default OFF) was DARK — the running process did not have the flag
truthy, so `run_honest_sweep_r3.py:8370 (if _fs_researcher_enabled() or _iterresearch_enabled())` took
the legacy `else` and NO `[fs_researcher] #1296` line was emitted. A config-string preflight passed while
legacy ran. Root cause: a default-OFF flag emits no log, and nothing FAILED CLOSED pre-spend when the
slate value did not land in the process. This diff makes that impossible.

## The diff — review `.codex/I-deepfix-001/preflight_fixes.patch` (255 lines) + read the touched files for context. Repo root C:/POLARIS, read-only.
Files: `scripts/dr_benchmark/run_gate_b.py` (+~76), `src/polaris_graph/retrieval/content_relevance_judge.py` (+11), `tests/dr_benchmark/test_deepfix_winner_slate_prespend_ideepfix001.py` (new, 7 tests).

### FIX 1 — STORM killed in the slate (operator directive: STORM entirely off)
Slate force-EXACTs BOTH `PG_STORM_ENABLED=0` and `PG_STORM_ENABLED_IN_BENCHMARK=0` (run_gate_b.py:559 +
the `_BENCHMARK_FORCE_EXACT_FLAGS` list ~1873/1917 + `_BENCHMARK_PREFLIGHT_REQUIRED_OFF_FLAGS`), so no
launch-env value can re-enable STORM and the preflight fails closed if either is re-armed.

### FIX 2 — pre-spend winner-slate assertion (the teeth)
`assert_full_capability_slate_applied(smoke_scale)` (run_gate_b.py:2570) iterates every flag in
`_BENCHMARK_FORCE_ON_FLAGS | _BENCHMARK_FORCE_EXACT_FLAGS`, reconciles smoke overrides, and raises a clear
`RuntimeError [WINNER-SLATE-DARK]` naming the offending flag if `os.environ` does not match the applied
slate value (explicitly requires `PG_QGEN_FS_RESEARCHER == "1"`). It is CALLED in `run_gate_b_query`
right after `apply_full_capability_benchmark_slate(...)` and BEFORE the `run_honest_sweep_r3` sweep import
— i.e. fails closed at the earliest point, before the heavy import and long before any token spend.
Kill-switch `PG_WINNER_SLATE_PRESPEND_ASSERT` (run_gate_b.py:2567), default-ON (LAW VI).

### FIX 3 — WS-0 W5 score-chunk on the run path
Slate force-EXACTs `PG_CONTENT_RELEVANCE_SCORE_CHUNK=2` (run_gate_b.py:1391) so the W5 content-relevance
reranker never OOM-degrades on a co-resident card; plus a canary log
`[content_relevance] SCORE_CHUNK active: N pairs in M chunks` (content_relevance_judge.py, emitted only
when `len(index_groups) > 1`) so a live log proves WS-0 fired. Chunked scores are byte-identical to
one-pass (padded to global-longest) — faithfulness-neutral.

### Launch env `.codex/I-deepfix-001/a100_complete_env.sh` (single A100-80GB)
Covers the gaps the slate does NOT set: GPU device placement (all cuda:0) + WS-8 D4 recency
(`PG_DOCUMENT_TYPE_WEIGHT=1` + `PG_COMPOSITION_RECENCY=1`, deliberately out of the global slate). Belts
the 4 drift-exposed flags (FS-Researcher on / STORM both off / IterResearch off / score-chunk 2) + the
pre-spend assert on. Sets NO model env var (transport resolves generator=glm-5.2 / judge=kimi-k2.6).

## Confirm (each with a P-level if wrong)
1. STORM: fully OFF on the Gate-B path — both arms force-exacted to "0" AND preflight-required-off? Any path that re-enables STORM?
2. Pre-spend assertion: does it truly fire BEFORE spend AND before the sweep import, cover W2 (PG_QGEN_FS_RESEARCHER) plus all force-on/force-exact winners, and raise a clear abort? Any flag it should cover but misses? Any false-positive risk (a legitimately-unset flag it would wrongly abort on — check the smoke-scale reconciliation)?
3. WS-0 score-chunk: force-exacted to "2" on the path? Canary correct + faithfulness-neutral (byte-identical chunked vs one-pass)?
4. Frozen faithfulness engine (strict_verify/provenance_generator/nli_verifier/role_pipeline/judge_adapter/judge_contract/span_grounding/four_role/mirror_adapter/sentinel_adapter/credibility_pass) — name-only diff EMPTY?
5. Env: does it set any WRONG model var / override a correct model resolution? Any device/recency line that would misbehave on a single A100?
6. §-1.3: any DROP/CAP/THIN introduced? (STORM off is a loser-off, not a source drop; score-chunk is byte-identical.)

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
storm_fully_off: true|false
prespend_assertion_covers_w2_and_preimport: true|false
prespend_no_false_positive: true|false
ws0_score_chunk_on_path: true|false
frozen_engine_untouched: true|false
env_no_wrong_model_var: true|false
s13_no_drop: true|false
novel_p0: [...]
p1: [...]
convergence_call: continue | accept_remaining
```
