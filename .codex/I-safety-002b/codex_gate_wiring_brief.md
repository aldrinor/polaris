HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# BRIEF: wire pathB_run_gate into a real POLARIS run path (I-safety-002b / #925, the open step-3 P1-3)

This is a BRIEF review (approve the APPROACH before I write the diff). The gold-rubric answer key is
FROZEN (Codex APPROVE iter 2, freeze_pin.txt). The enforcement gate `scripts/dr_benchmark/pathB_run_gate.py`
is fixture-green but **enforces only in fixtures — it is wired into NOTHING** (your own step-3 P1-3, still
open). This brief proposes the wiring so a real POLARIS full-power run is preflight-gated, all-LLM-calls
captured, retrieval-attempts logged, and `assert_post_run` runs BEFORE any scoring.

## Adjacent-file scan (files I have ALSO checked, with anchors)
- `scripts/dr_benchmark/pathB_run_gate.py` — gate API: `preflight(control_vars, role_pins, salt, reachability_prober, source_map, roots, offline)` → pin dict; `LLMCall(call_id, role, prompt_messages_present, request_hash, response_metadata)`; `assert_post_run(pin, control_vars, salt, calls, retrieval_backends_attempted)`. RolePin requires `surrogate_fields` PROVEN present at preflight + FULL slug.
- `src/polaris_graph/llm/openrouter_client.py` — `LLMResponse` (line 659) has `raw_response: Optional[dict]` (669) = the full provider JSON `data` (set line 1651). `model=data.get("model", self.model)` (1649). Async `generate` (2001) + `generate_structured` (2311) are the two completion entry points. There is ALREADY a run-scoped capture pattern to mirror: I-gen-004 reasoning-trace sink via contextvars `_REASONING_SINK_CTX` / `_REASONING_CALL_CTX` (113-141), `set_reasoning_sink` / `set_reasoning_call_context`, captured in `_capture_reasoning_trace` (144-186) — best-effort, never breaks generation. The reasoning sink is generator-only (no-op unless a call-context is set).
- `scripts/run_honest_sweep_r3.py` — `run_one_query` (1157), `main_async` (3241, argparse 3245), `main` (3535). This is the full-power runner (the one the gate is for).
- Retrieval backends: `src/polaris_graph/retrieval/{live_retriever.py, domain_backends.py}` invoke serper + semantic_scholar (the two `_REQUIRED_RETRIEVAL_CREDS_TO_BACKENDS`).
- Two-family segregation (`openrouter_client.check_family_segregation`) means generator (deepseek/deepseek-v4-pro) and evaluator (google/gemma-4-31b-it) are distinct configured roles — the per-role pins the gate enforces.

## Proposed design
1. **New module `src/polaris_graph/benchmark/pathB_capture.py`** (pure, importable; no heavy deps):
   - contextvars: `_LLM_CALL_SINK` (list collector), `_LLM_ROLE` (str|None), `_RETRIEVAL_ATTEMPTED` (set).
   - `register_pathB_capture()` / `clear()`; `set_llm_role(role)`; `record_retrieval_attempt(backend)`;
     `collected_calls() -> list[LLMCall]`; `attempted_backends() -> set[str]`.
   - `build_response_metadata(raw_response, served_model) -> dict` = `{"model": served_model, "provider_name": raw_response.get("provider"), "system_fingerprint": raw_response.get("system_fingerprint")}` (drop keys whose value is None so the surrogate is over PROVEN-present fields only).
   - `request_hash(messages) -> str` = sha256 over the serialized prompt messages.
2. **Hook in `openrouter_client.generate` + `generate_structured`** (mirror `_capture_reasoning_trace`, best-effort try/except, never breaks the call): after a completed response, if a pathB sink is registered, append `LLMCall(call_id, role=current_llm_role() or "untagged", prompt_messages_present=bool(messages), request_hash=request_hash(messages), response_metadata=build_response_metadata(result.raw_response, result.model))`.
3. **Role tagging**: the generator call path sets `set_llm_role("generator")`; the evaluator path sets `set_llm_role("evaluator")` (same idea as the existing reasoning call-context). assert_post_run already enforces served-model == pinned-model PER ROLE, so a mis-tag or a wrong-served-model is caught.
4. **Retrieval-attempt logging**: at the serper + semantic_scholar call sites, call `record_retrieval_attempt("serper"|"semantic_scholar")` when the request is issued (so `assert_post_run` confirms both required backends were actually attempted).
5. **Runner integration in `run_honest_sweep_r3.py`** behind a `--pathB-gate` flag (off by default; the benchmark run sets it):
   - At start: build role_pins (generator deepseek/deepseek-v4-pro, evaluator google/gemma-4-31b-it, provider from OPENROUTER_PROVIDER_ORDER), call `preflight(control_vars=[], role_pins, salt, roots=[Path("src/polaris_graph"), Path("scripts")], offline=False)` → real reachability ping. **surrogate_fields**: do a tiny preflight probe call per role to learn which of {provider_name, model, system_fingerprint} are actually present in the served metadata, and pin EXACTLY those (system_fingerprint may be absent from DeepInfra — then surrogate = provider_name+model, still exact-match enforced). Persist the pin to the run dir.
   - During: register the capture sink.
   - After the run, BEFORE scoring: `assert_post_run(pin, [], salt, collected_calls(), attempted_backends())`; on GateError, mark the run INVALID and do NOT score.
   - Salt from env (`PG_PATHB_GATE_SALT`), never logged.
6. **Tests** (`tests/dr_benchmark/test_pathB_capture.py`, pure, no live): sink collects calls; role tagging; response_metadata drops None fields; request_hash stable; retrieval-attempt set; end-to-end with fake calls passes assert_post_run; a wrong-served-model fake fails.

## Open design questions for you (decide so the diff is right first time)
A. **Role attribution**: is `set_llm_role()` at the generator/evaluator call sites the right seam, or should role be inferred from the served model matching a pinned slug? (I lean explicit tagging so a wrong-model-for-role is detectable, not silently re-bucketed.)
B. **surrogate_fields probe**: is a per-role preflight probe call acceptable (1 cheap call/role), or should I derive surrogate_fields from the FIRST real call of each role and fail the run if later calls drift? (Probe is cleaner pre-registration; first-call is cheaper.)
C. **system_fingerprint absence**: confirm it is acceptable for the surrogate to be provider_name+model when the provider omits system_fingerprint (exact provider+model match is still enforced; the surrogate just can't be finer).
D. **LOC/PR**: this likely exceeds the 200-LOC cap (new module + 2 client hooks + 2 retrieval hooks + runner flag + tests). Split into (PR-1 capture module+tests, PR-2 client+retrieval hooks, PR-3 runner integration) or one exemption-justified PR?
E. **Separate risk (not gate code, but affects the run)**: POLARIS is clinical-tuned (scope gate, clinical tier classifier, corpus adequacy for RCTs/guidelines). Golden questions #72 (AI-labor economics) and #90 (ADAS law) are NON-clinical. Will the scope gate `abort_scope_rejected` them or corpus-adequacy fail? Should the plan include a 1-question operator-supervised smoke run on #72 or #90 to confirm non-clinical viability BEFORE wiring + 5 full runs?

## Output schema (return EXACTLY this)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: []
continuing_p0: []
p1: []
p2: []
p3: []
answers:
  A_role_attribution: <your call>
  B_surrogate_probe: <your call>
  C_system_fingerprint_absence: <ok | not-ok + why>
  D_pr_split: <your call>
  E_nonclinical_smoke_run: <your call>
convergence_call: continue | accept_remaining
remaining_blockers_for_diff: []
```
Loose verdict prose without this schema will be rejected and resubmitted.
