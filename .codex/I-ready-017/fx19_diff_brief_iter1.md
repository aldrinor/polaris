# FX-19 (#1127) diff-gate — ITER 1 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## Output schema (REQUIRED — reply with EXACTLY this YAML, nothing else)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## Scope
Two concerns in this diff (vs FX-17 verified tip `70010869`). Diff:
`.codex/I-ready-017/fx19_codex_diff.patch`.

**(1) FX-19 (#1127) — RETIRE `PG_AMPLIFICATION_VARIANTS`.** Your plan-gate Q6 said RETIRE.
Documentation + comments only, NO code-logic change. Faithfulness-safe.

**(2) Test-regression hotfix** surfaced by the full-suite run after FX-17/FX-18 merged. Test-only.

## FX-19 — the bug, §-1.1 on the REAL held trace
- `PG_AMPLIFICATION_VARIANTS` (`state.py:72`, default 3) is consumed ONLY in the legacy static path of
  `searcher.execute_searches` (`:303,311`). That path is unreachable on the agentic slate: the function
  returns `execute_agentic_search(...)` early at `searcher.py:291-292` when
  `PG_AGENTIC_SEARCH_ENABLED and client`. The benchmark runs agentic ON.
- **Held drb_72 confirms inert:** `outputs/audits/I-ready-017/query_breadth_generators_findings.md`
  records `PG_AMPLIFICATION_VARIANTS=8 → 0 "Query amplification" log lines → UNWIRED (dead in benchmark
  path)`. The only emitter of that log is the legacy block (`:305-312`); zero lines ⇒ never invoked.
- Yet `docs/capability_downgrade_audit_2026_06_04.md:34,80` advertised it as a HIGH-impact lever — a
  dead knob sold as capability.

## FX-19 — the fix (RETIRE; doc + comments only)
- `state.py:71-78` + `searcher.py` amplification block: comments marking it legacy-static-path-only,
  inert under the agentic early-return; KEPT (not deleted) because the non-agentic lane still uses it.
- `docs/capability_downgrade_audit_2026_06_04.md`: row + env token annotated **RETIRED** /
  do-not-set-for-benchmark. (NOTE: this doc was previously UNTRACKED — committing it here tracks it for
  the first time, so the diff shows it as a new 90-line file; the FX-19-relevant change is the single
  annotated row at :34 + the env token at :81.)
- §-1.1: `outputs/audits/I-ready-017/fx19_amplification_retire_audit.md`.

## FX-19 — evidence
- Offline smoke `test_fx19_amplification_retired_iready017.py` → 2 passed:
  - **amplifier unreachable under agentic**: `PG_AGENTIC_SEARCH_ENABLED=1` → `execute_searches` hands
    off to `execute_agentic_search`; `_import_amplifier` (monkeypatched to raise) is NEVER called.
  - **legacy lane intact**: `PG_AGENTIC_SEARCH_ENABLED=0`, `PG_AMPLIFICATION_VARIANTS=2` → amplifier IS
    invoked and 10 amplified queries are trimmed to cap `original_count(1)*2 = 2`.

## Test-regression hotfix (concern 2 — please verify it masks nothing)
Full-suite run after FX-17/FX-18 surfaced two breakages the targeted smoke runs missed:
- **FX-17 (#1126) added `api_calls` kwarg to `_serper_search`.** Four test mocks with a fixed
  `(query, num=10)` signature raised `TypeError`. Added `api_calls=None` to:
  `test_source_discovery_phase2._fake_serper`, `test_research_planner_phase1.CaptureSearch.serper`,
  `test_post_fetch_loop_timeout` stub, `test_fx18` lambda. Pure signature alignment.
- **FX-18 (#1122) wired `openalex_search` (default-ON) into `run_live_retrieval`.** The "zero network"
  `_stub_pipeline` did not disable it, so the offline timeout test hit the REAL OpenAlex API and got 24
  candidates instead of 4. Fix: `monkeypatch.setenv("PG_OPENALEX_SEARCH", "0")` in `_stub_pipeline`.
  Please confirm this env-disable is correct test isolation and is NOT hiding a real run_live_retrieval
  bug (the production default-ON behavior is intended per your FX-18 Q8; the test simply shouldn't make
  network calls).
- Result: `test_post_fetch_loop_timeout` 5/5; the affected set green.

## Faithfulness
No grounding / strict_verify / 4-role change anywhere. FX-19 = zero behavior change on any execution
path. Hotfix = test-only. No-silent-downgrade-aligned (stop advertising a dead lever; keep network out
of offline tests).

## Question
Is the RETIRE correct + faithfulness-safe (knob provably dead on the agentic/benchmark path, legacy lane
intact), and is the test-regression hotfix sound (mock signature alignment + offline network isolation,
masking nothing)? Anything blocking APPROVE?
