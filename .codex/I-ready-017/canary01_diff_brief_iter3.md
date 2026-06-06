# CANARY-01 (#1108) diff-gate — ITER 3 of 5

```
HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
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

## What CANARY-01 is

The drb_72 held run's preflight checked CONFIG + the 4 verifier slugs but NOT the
searcher/generator `generate_structured` call shape (the FX-01-keystone 404 that silently killed
discovery) nor a real 1-query search → a dead route was swallowed → a green run on dead discovery.
`behavioral_canary()` tests BEHAVIOR via real call shapes and FAILS CLOSED before spend. It is the
4th of 4 rerun-gating P0s; FX-01/FX-02/FX-03 are already VERIFIED.

## Your iter-2 finding → fixed (the ONLY change in this iter)

- **P1 (blocker)**: `pathB_run_gate.py:555` constructed `OpenRouterClient()` (i.e.
  `OPENROUTER_DEFAULT_MODEL`) for the structured-output probe, NOT the effective `PG_GENERATOR_MODEL`
  slug the live STORM/agentic structured calls use. So the canary could pass while the real
  generator slug's structured path is dead (green-on-dead-discovery recreated). **FIXED**:
  `_default_structured_output_probe` now imports `PG_GENERATOR_MODEL` from
  `src.polaris_graph.llm.openrouter_client` and constructs
  `OpenRouterClient(model=PG_GENERATOR_MODEL)`. `PG_GENERATOR_MODEL` is
  `os.getenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")` at `openrouter_client.py:429` — the
  SAME constant `multi_section_generator` / the live searcher import and use, so the probe now
  exercises the exact slug the live discovery path uses.

## Evidence (offline; no spend) — review `.codex/I-ready-017/canary01_codex_diff.patch`

- The probe constructs the client with the live generator slug (verified in the diff).
- New regression test `test_default_structured_probe_uses_pg_generator_model`: monkeypatches
  `openrouter_client.PG_GENERATOR_MODEL` to a DISTINCT sentinel (`"test/generator-slug-XYZ"`, not the
  default) + a `_RecordingClient` fake that records its constructor `model=`, then asserts the probe
  built the client with `PG_GENERATOR_MODEL`. A regression to bare `OpenRouterClient()` /
  `OPENROUTER_DEFAULT_MODEL` would fail this test.
- 19 tests pass (10 CANARY-01 + 5 FX-03 slate + 4 readiness precedent).

## Iter-1/2 findings already closed (context, not re-asking)

- iter-1 P1 (`asyncio.run` inside the `run_gate_b_query` event loop → RuntimeError) — FIXED: canary +
  default structured probe are `async`, awaited at the call site; no `asyncio.run` on the live path.
- iter-1 P2 (only `NoEndpointError` normalized) — FIXED: canary converts ANY probe exception to
  `GateError` ("fail closed BEFORE spend").
- iter-1 P2 (chromium) — you ACCEPTED: benchmark fetch = httpx/Serper, not headless browser; Chromium
  is FX-16 (VM-side). The live-search probe covers the real discovery path. No change.

## Question

Does the structured-output probe now exercise the effective live generator/searcher slug
(`PG_GENERATOR_MODEL`), closing the green-on-dead-discovery gap? Anything else blocking the
behavioral pre-spend canary? Diff: `.codex/I-ready-017/canary01_codex_diff.patch` (isolated vs FX-03
tip `8dc823f5`).
