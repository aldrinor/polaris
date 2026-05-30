HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# DECISION BRIEF: PR-2 role-tagging vs the REAL honest_sweep LLM topology (I-safety-002b / #925)

You APPROVED the gate-wiring design (brief v2) and PR-1's diff (capture primitives + `_call_impl` hook
+ entailment_judge capture). PR-1 is committed (731e022b). Authoring PR-2 (retrieval hooks + runner
lifecycle) I found the honest_sweep LLM topology is RICHER than the brief assumed, which creates a
role-tagging correctness fork. I need your call before I edit 4 generator/evaluator modules.

## The REAL honest_sweep LLM topology (grepped; scripts/run_honest_sweep_r3.py imports)
- **REPORT GENERATOR (deepseek-v4-pro)**: `generator/multi_section_generator.generate_multi_section_report`;
  `generator/analyst_synthesis.py:346` `OpenRouterClient(model=model)` → `:349 set_reasoning_call_context(...)`
  → `:352 client.generate(...)`. (The generator already marks itself via the reasoning call-context.)
- **EVALUATORS (gemma-4-31b)**: `evaluator/live_judge.py:139` `OpenRouterClient(model=eval_model)` →
  `:151 client.generate(...)` (model = PG_EVALUATOR_MODEL, default gemma); `evaluator/external_evaluator.run_external_evaluation`;
  the strict_verify entailment judge (`entailment_judge.py`, direct httpx, role="evaluator" already
  hooked in PR-1).
- **AUXILIARY LLMs (model = OPENROUTER_MODEL default = deepseek-v4-pro unless overridden)**:
  `audit_ir/scope_classifier_llm.py:584-589` `OpenRouterClient(model=model)` (scope gate LLM);
  `auto_induction/llm_inductor.py:332` `OpenRouterClient(model=model)` (keyword/precision inductor).
- (The dozens of other `client.generate` sites — agents/*, nodes/outline, tools/react_agent,
  graph_v2/v3 — are pipeline B / the LangGraph UI, NOT invoked by honest_sweep. Please confirm if you
  disagree.)

## The problem
PR-1's `_call_impl` hook captures with `role = current_llm_role() or "generator"`. So any auxiliary
call (scope/inductor) with NO explicit role tag is captured as **"generator"**. `assert_post_run`
then requires every "generator"-tagged call's SERVED model == the pinned generator slug. If an
auxiliary call ever serves a non-deepseek model (now or after a config change), the gate FALSE-FAILS
a legitimate full-power run. Conversely live_judge (gemma) via OpenRouterClient, if left untagged,
would be captured as "generator" serving gemma → guaranteed false-fail.

## The fork (pick one)
- **Option A — capture ALL, default "generator"** (PR-1 as-is) + tag only the evaluators. Guarantee:
  "every generator-family call in the run served deepseek; every evaluator call served gemma." STRONGER
  (polices scope/inductor too), but false-fails if any auxiliary serves a 3rd model, and couples gate
  validity to the auxiliary model config.
- **Option B — capture ONLY explicitly-tagged calls** (RECOMMENDED). Change the PR-1 hook from
  `or "generator"` to: `role = current_llm_role(); if role is None: return` (skip untagged). Then tag:
  - report generator: wrap the `generate_multi_section_report` / `analyst_synthesis` generate calls with
    `with pathB_capture.llm_role("generator"):`
  - evaluators: wrap `live_judge.judge_report` + `external_evaluator` generate calls with
    `with pathB_capture.llm_role("evaluator"):` (entailment judge already role="evaluator")
  - auxiliary scope/inductor: left untagged → NOT captured/gated.
  Guarantee: "the REPORT generator served deepseek + the report EVALUATORS served gemma, full power,
  no fallback." Matches the benchmark's purpose (faithfulness of the REPORT). Robust to auxiliary
  config. Cost: changes PR-1 hook semantics (you APPROVED `or "generator"`); needs tags at 3 modules.

## My recommendation
**Option B.** The gate's job is to prove the POLARIS *report* was produced by deepseek + verified by
gemma at full power with no fallback — not to police the scope-classifier's model. Option A's "strength"
(policing auxiliary calls) is actually a fragility (false-fail risk + config coupling) for no benchmark
benefit. Option B is the robust, purpose-matched choice.

## Questions
1. Option A or B? (I recommend B.)
2. If B: is my tag-site list COMPLETE for honest_sweep (report generator: multi_section + analyst_synthesis;
   evaluators: live_judge + external_evaluator + entailment-judge[done])? Any honest_sweep LLM call that
   produces or verifies REPORT content that I've missed and must tag?
3. If B: any concern with changing the PR-1 hook default `or "generator"` → require-explicit-role
   (auxiliary calls become uncaptured)?
4. Should the run also assert that scope/inductor did NOT serve a *fallback* (i.e., is there ANY
   benchmark value in policing auxiliary calls, or is report-generator+evaluator sufficient)?

## Output schema (return EXACTLY this)
```yaml
verdict: APPROVE | REQUEST_CHANGES
chosen_option: A | B
novel_p0: []
continuing_p0: []
p1: []
p2: []
p3: []
tag_sites_complete: true | false
missing_tag_sites: []
hook_default_change_ok: true | false
audit_aux_calls: yes | no
convergence_call: continue | accept_remaining
remaining_blockers_for_diff: []
```
Loose verdict prose without this schema will be rejected and resubmitted.
