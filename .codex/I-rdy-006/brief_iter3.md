HARD ITERATION CAP: 5 per document. This is iter 3 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-rdy-006 brief iter 3 (#502) — complete verified inventory, all rulings baked

Iter-1/2: `brief.md`, `brief_iter2.md`. Iter-2 verdict REQUEST_CHANGES with
rulings: `scope_ruling=class_a_only`, `p1b_ruling=change_default_v4pro`,
`analyst_synthesis_ruling=change_v4pro` — all baked in below. This is the
COMPLETE, comprehensively-grepped, verified inventory.

## Comprehensive sweep done

`grep -i "DeepSeek V3.2|deepseek-v3.2|deepseek/deepseek-v3|Qwen3-8B|qwen3-8b|
qwen/qwen|V4 Flash|v4-flash"` across `src/` + `docs/` + root `*.md` + `config/`
→ 35 files; each match verified as stale-current-claim vs legitimate-historical.

## #502 SCOPE — the complete Class A fix list

### Code — model defaults / executable values
- `transparency.py:~218` — evaluator fallback `qwen/qwen-2.5-72b-instruct` →
  `google/gemma-4-31b-it`.
- `openrouter_client.py:46` — `OPENROUTER_DEFAULT_MODEL` default
  `qwen/qwen3.5-plus-02-15` → `deepseek/deepseek-v4-pro` (Codex iter-2 p1b).
- `analyst_synthesis.py:310` — `model` default `deepseek/deepseek-v3.2-exp` →
  `deepseek/deepseek-v4-pro` (Codex iter-2 analyst_synthesis_ruling).
- `sentence_repair.py:148,254` — `model` default `deepseek/deepseek-v3.2-exp` →
  `deepseek/deepseek-v4-pro` (same executable-default class).
- `.env.example` — `PG_GENERATOR_MODEL` → `deepseek/deepseek-v4-pro`,
  `PG_EVALUATOR_MODEL` → `google/gemma-4-31b-it`, `OPENROUTER_DEFAULT_MODEL` →
  `deepseek/deepseek-v4-pro`.

### Code — stale docstrings / comments / log strings
- `live_qwen_judge.py` docstrings 5,10-11,126.
- `openrouter_client.py` docstrings 4,820.
- `live_deepseek_generator.py` docstrings 2,4,390.
- `evaluator_gate.py` header comments 5,17,21.
- `hallucination_detector.py:24` — docstring "Qwen 3 32B evaluator while
  generator is DeepSeek V3.2".
- `multi_section_generator.py:438,4054` — stale narration comments.
- `run_honest_sweep_r3.py:319,1944` — stale generator log strings.
- `run_live_honest_cycle.py:9,10,217,328,346` — header + log strings.
- `run_honest_on_prerebuild_corpus.py:18,385` — header + log strings.
- `model_pin.py:26` — docstring example `"evaluator": "qwen/qwen3.5-plus"` →
  update the illustrative value to the locked pair.

### Docs — current-state claims
- `architecture.md:49,53,83,92,175,176,320,325,337,339`.
- `README.md:116,127`.
- `ground_rules.md:173,316`.
- `docs/runbook.md:154,160,274`.
- `docs/transparency.md:29`.

### New test
- `tests/v6/` — transparency fallback regression test: clear
  `PG_EVALUATOR_MODEL` → assert `/transparency` shows `google/gemma-4-31b-it`.

## VERIFIED NOT stale — explicitly NOT touched

- `file_directory.md:249-252` — correct historical note (Codex iter-2 agreed).
- `polaris_locked_scope.md:27` — correct historical note ("V4 Flash overridden
  to V4 Pro by operator directive").
- `multi_section_generator.py:283` — dated M-31 (2026-04-21) historical
  bug-rationale comment, not a current-pair claim.
- Historical/superseded docs keep their refs: `docs/experiments/*`,
  `docs/pipeline_audit_context/*`, `docs/carney_delivery_plan_v5_*`,
  `docs/hardware_decision.md` (model-bakeoff record), `docs/walkthroughs/*`,
  `docs/gemma_4_verification.md`, `docs/carney_handover/*`, `docs/blockers.md`,
  `docs/task_acceptance_matrix.yaml` (HISTORICAL doc).

## ONE flagged scope question for Codex

`carney_delivery_plan_v6_2.md:439` reads "Hardware Path C V4 Flash on 8× H200
OVH BHS Canada is now CONFIRMED" — a stale HARDWARE-path claim (V4 Flash was
overridden to V4 Pro per operator; `polaris_locked_scope.md:27` records the
override correctly). `carney_delivery_plan_v6_2.md` is the canonical mission
doc. **I propose this is OUT of #502** — #502 targets generator/evaluator MODEL
config; a stale hardware-path line in the canonical mission doc is a
canonical-doc reconciliation (its own follow-up), and the authoritative
`polaris_locked_scope.md` §1 is already correct. Codex: confirm `out`, or rule
`in`.

## Class B carve-out (unchanged, per iter-1/2 scope_ruling)

`evaluator_gate.py` `qwen_*` fields/status/reasons, the `partial_qwen_advisory`
/ `ok_qwen_advisory` status strings (incl. `run_honest_sweep_r3.py:178,196`),
the `live_qwen_judge.py` module rename, and the `qwen_judge_output.json`
artifact name → a separate I-naming-style follow-up issue (`gh issue create`
at #502 close).

## LOC estimate

~17 files, mostly 1-3 lines each + 1 new test file ≈ 100-130 LOC. Under the
200-LOC cap.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
carney_plan_439_ruling: out | in
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
