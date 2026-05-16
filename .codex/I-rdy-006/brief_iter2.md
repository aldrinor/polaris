HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-rdy-006 brief iter 2 (#502) — addresses iter-1 REQUEST_CHANGES

Iter-1 brief: `.codex/I-rdy-006/brief.md`. Iter-1 verdict: REQUEST_CHANGES,
`scope_ruling: class_a_only` (confirmed — Class B `qwen_*` identifier rename
carves to a follow-up). This delta addresses the 2 P1 + 2 P2.

## P1-a — `.env.example` forces the stale generator — IN SCOPE, FIXED

`.env.example` (~57-70) sets `PG_GENERATOR_MODEL` (and `OPENROUTER_DEFAULT_MODEL`)
to `deepseek/deepseek-v3.2-exp`. #502 fixes `PG_GENERATOR_MODEL` →
`deepseek/deepseek-v4-pro` and `PG_EVALUATOR_MODEL` → `google/gemma-4-31b-it`
(the locked pair). `OPENROUTER_DEFAULT_MODEL` in `.env.example` — see P1-b.

## P1-b — `openrouter_client.py:46` `OPENROUTER_DEFAULT_MODEL` default — DECISION FOR CODEX

`OPENROUTER_MODEL = getenv("OPENROUTER_DEFAULT_MODEL", "qwen/qwen3.5-plus-02-15")`.
Full `OpenRouterClient(` call-site scan (src + scripts):
- The locked GENERATOR + EVALUATOR always pass explicit `model=` —
  `multi_section_generator.py` (7 sites), `live_qwen_judge.py:140`,
  `live_deepseek_generator.py:400`, `sentence_repair.py:184`,
  `analyst_synthesis.py:343`, `auto_induction/llm_inductor.py:332`,
  `audit_ir/scope_classifier_llm.py:588`. **The locked pair never uses the
  `OPENROUTER_MODEL` default.**
- BUT no-arg `OpenRouterClient()` IS used on live paths: `scripts/live_server.py:126`
  (UI server default client), `src/polaris_graph/scope/clinical_classifier.py:239`,
  `graph_v2.py` (5 sites) / `graph_v3.py:723` (pipeline-B LangGraph),
  `audit_ir/inspector_router.py:2141`. These fall through to
  `qwen/qwen3.5-plus-02-15` — a stale "default-provider" reference (the issue
  title names "default-provider" explicitly).

**Recommendation:** change the `OPENROUTER_DEFAULT_MODEL` default to
`deepseek/deepseek-v4-pro`. Rationale: `architecture.md:337` documents
`OPENROUTER_DEFAULT_MODEL` AS "Generator model"; the generator is V4 Pro;
`openrouter_client.py` already carries full reasoning-first handling for V4 Pro
(I-gen-003), so no-arg clients will not crash. Known consequence: no-arg
utility/scope calls (clinical_classifier, live_server brief client) shift to a
reasoning-first model — slower/costlier per call, no correctness regression.
**Codex: confirm `change_default_v4pro`, or rule `split_followup`** (carve the
no-arg-default question to its own issue) **or another value.**

## P2-a — expanded Class A inventory, VERIFIED line-by-line

**Confirmed stale model-identity claims (fix in #502):**
- `architecture.md:49,53,83,92,175,176,320,325,337,339` — flatly state
  "DeepSeek V3.2-Exp" generator / "Qwen3-8B evaluator" / `OPENROUTER_DEFAULT_MODEL
  = deepseek/deepseek-v3.2-exp` / `PG_EVALUATOR_MODEL = qwen/qwen3-8b` as the
  CURRENT architecture. architecture.md is the current-state baseline → must
  read V4 Pro + Gemma 4 31B.
- `README.md:116,127` — "multi_section_generator (DeepSeek V3.2-Exp)",
  "live_qwen_judge (Qwen3-8B…)" as the current pipeline. (Line 172 is a module
  path — Class B, untouched.)
- `ground_rules.md:173` ("DeepSeek V3.2-Exp"), `316` ("Current pair: DeepSeek
  V3.2-Exp + Qwen3-8B" — explicit "Current pair" → stale). (Line 315 "Kimi K2.5
  / GLM / Qwen 3.5 Plus — historical … mentions" is an explicit history note —
  untouched. Line 195 `qwen_judge_output.json` — Class B artifact — untouched.)
- `live_deepseek_generator.py:2,4,390` — docstrings "Live DeepSeek V3.2
  generator" / "Calls the REAL DeepSeek V3.2-Exp model" — the module is
  parametrized (`OpenRouterClient(model=generator_model)` at :400); docstring
  narration is stale.

**Verified NOT stale — pushing back on iter-1 P2-a (per skeptical-of-Codex):**
- `docs/file_directory.md:249-252` — reads "the locked generator/evaluator for
  the Carney demo is **DeepSeek V4 Pro + Gemma 4 31B** …; earlier pipelines
  used DeepSeek V3.2-Exp + Qwen3-8B." This is a CORRECT historical note (states
  the locked pair correctly; V3.2+Qwen explicitly as past). **No change.**

## P2-a — `analyst_synthesis.py:310` — DECISION FOR CODEX

`analyst_synthesis.py:310` has an EXECUTABLE default
`model: str = "deepseek/deepseek-v3.2-exp"`; docstring 316-318 frames it as a
deliberate choice — "Per Codex iter-1 brief verdict: DeepSeek V3.2-Exp is the
writer (consistent with verified prose voice; Gemma stays in the
judge/evaluator role)." `multi_section_generator.py:4054-4055` echoes it. So
the Analyst Synthesis section is *deliberately* written by V3.2-Exp — a
prior-Codex-blessed split (body = V4 Pro per I-gen-003; synthesis = V3.2-Exp).

**Codex: is Analyst-Synthesis-writer = V3.2-Exp still the intended design**
(→ `leave` — `analyst_synthesis.py:310` is current intentional config, not a
stale reference; #502 leaves it), **or does I-gen-003's "V4 Pro is THE
generator" supersede it** (→ `change_v4pro`)? I lean `leave` — it is a
documented deliberate choice; flipping it is an architecture decision beyond
"purge stale references." Confirm.

## P2-b — transparency fallback regression test — IN SCOPE

Add a test under `tests/v6/` that clears `PG_EVALUATOR_MODEL` from the
environment and asserts the `/transparency` response `evaluator_models.evaluator`
== `google/gemma-4-31b-it` (and `generator` == `deepseek/deepseek-v4-pro`) —
locks the `qwen/qwen-2.5-72b` regression out.

## Class B carve-out

I will `gh issue create` an I-naming-* follow-up for the `evaluator_gate.py`
`qwen_*` field/status/reason-string rename + `live_qwen_judge.py` module
rename + `qwen_judge_output.json` artifact name. Logged at #502 close; not in
this PR.

## Confirmed Class A fixes carried from iter 1

`transparency.py:~218` + `docs/transparency.md:29` (evaluator default
`qwen/qwen-2.5-72b-instruct` → `google/gemma-4-31b-it`); `docs/runbook.md:154,
160,274`; `live_qwen_judge.py` docstrings 5,10-11,126 + the misleading "judge
is Qwen3-8B / generator is V3.2-Exp"; `openrouter_client.py` docstrings 4,820;
`evaluator_gate.py` header comments 5,17,21.

## LOC estimate

~65-75 changed lines across ~11 files + 1 new test file. Under the 200-LOC cap.

## Output schema

```yaml
verdict: APPROVE | REQUEST_CHANGES
scope_ruling: class_a_only | class_b_required | other
p1b_ruling: change_default_v4pro | split_followup | other
analyst_synthesis_ruling: leave | change_v4pro
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
p3_cosmetic: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
