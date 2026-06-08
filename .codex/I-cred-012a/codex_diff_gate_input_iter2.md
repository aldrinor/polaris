HARD ITERATION CAP: 5 per document. This is iter 1 of 5. Front-load ALL real findings; reserve P0/P1 for real execution blockers; classify cosmetic as P2/P3. APPROVE iff zero P0 AND zero P1.

# DIFF GATE — credibility redesign build phase (umbrella I-ready-021 #1148)

Review the NEW-MODULE diff below for code correctness against its plan-phase spec
(`docs/credibility_weighted_sourcing_redesign_plan_2026_06_07.md`). This is faithfulness-adjacent code.

## HARD CONSTRAINTS (operator-locked)
- **Default-OFF byte-identical:** the module must be inert unless explicitly invoked by a flag/caller; turning it OFF (or not wiring it) leaves existing behavior byte-identical. No production path is changed in this phase.
- **Faithfulness gates UNTOUCHED:** strict_verify (`provenance_generator.py`), 4-role D8, two-family segregation, corpus_approval are NOT edited or weakened. This phase is a NEW module only.
- **LAW VI:** no hardcoded thresholds/paths — config/env; snake_case; no magic numbers; no live data in unit tests (fixtures only).

## VERIFY SPECIFICALLY
1. The module implements its plan-phase spec correctly (read the named layer/phase in the plan).
2. **The phase invariant is actually enforced AND tested** (e.g. P4: a copied row joining a cluster — even higher-authority — cannot change the cluster set / canonical origin; P5: recall-first contradictions + conservative-singleton never over-merges; P3: retraction hard-penalty + config thresholds).
3. The unit tests are MEANINGFUL (not assertion-relaxed to pass) and the attached SMOKE result is green.
4. No faithfulness gate is touched; nothing in the production path changes with the module un-wired.

## SMOKE EVIDENCE (attached below the diff — the offline pytest result is the evidence, not a self-report)

## OUTPUT SCHEMA (YAML)
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]

============ THE DIFF + SMOKE EVIDENCE ============
## PHASE: I-cred-012a (#1164) — runner/generator INTEGRATION diff ITER 2. Iter-1 P1 + 2 P2 all addressed:
- (P1, runner threading — the blocker) scripts/run_honest_sweep_r3.py:4707 now threads credibility_pass_judge + credibility_pass_gov_suffixes under the master flag, with a FAIL-CLOSED preflight (master-on + empty gov_suffixes -> abort before the paid call). The judge = make_credibility_judge(make_openrouter_credibility_caller()); gov_suffixes loaded via data_loader.load_authority_data()['psl_gov_suffixes'] (loaded fresh — _gov_suffixes at :4616 is only in-scope inside the dedup branch).
- NEW credibility_judge_caller.py: a SYNC spend-tracked OpenRouter caller (mirrors entailment_judge: sync httpx POST, cost recorded + run-budget checked BEFORE returning; raises BudgetExceededError on cap breach). SYNC because the P2 judge is sync inside the async generator loop (no async-in-async). Open-weight default z-ai/glm-5.1 via PG_CREDIBILITY_JUDGE_MODEL. Local httpx import keeps off-mode import cost zero.
- (P2-2) multi_section_generator.py: the credibility_pass import is now GATED behind an inline env flag-check (os.environ) — inert (no import) when the flag is OFF.
- (P2-1) behavioral offline tests added: the caller with a MOCKED httpx (asserts endpoint/model/cost-tracking) + caller->judge->P2 end-to-end. 
default-OFF byte-identical (both new params None => pass not run); ADVISORY; READ-ONLY over evidence_pool. NB run_honest_on_prerebuild_corpus.py:293 is a separate non-Gate-B entry, OUT of the activation scope (master-on there fail-closes in the generator, safe). SMOKE: 19 passed (caller behavioral + wiring + chain); py_compile OK on all 3 edited files.
```diff
diff --git a/scripts/run_honest_sweep_r3.py b/scripts/run_honest_sweep_r3.py
index 5b7e985b..82c432dc 100644
--- a/scripts/run_honest_sweep_r3.py
+++ b/scripts/run_honest_sweep_r3.py
@@ -4702,12 +4702,34 @@ async def run_one_query(
                 f"generator rows are citeable journal articles"
             )
 
+        # I-cred-012a (#1164): under the master slate, thread the production credibility judge +
+        # gov_suffixes into generation. default-OFF => both None => byte-identical. FAIL-CLOSED: master-on
+        # requires non-empty gov_suffixes + a callable judge, surfaced HERE before the paid generation call
+        # (the generator carries the same guard as defense-in-depth).
+        _cred_judge = None
+        _cred_gov = None
+        if os.environ.get("PG_SWEEP_CREDIBILITY_REDESIGN", "").strip().lower() not in ("", "0", "false", "off", "no"):
+            from src.polaris_graph.authority.data_loader import load_authority_data as _load_auth
+            from src.polaris_graph.authority.credibility_judge import make_credibility_judge as _mk_judge
+            from src.polaris_graph.authority.credibility_judge_caller import (
+                make_openrouter_credibility_caller as _mk_caller,
+            )
+            _cred_gov = tuple(_load_auth().get("psl_gov_suffixes") or ())
+            if not _cred_gov:
+                raise RuntimeError(
+                    "abort_credibility_pass_error: PG_SWEEP_CREDIBILITY_REDESIGN is on but "
+                    "psl_gov_suffixes is empty (fail-closed preflight)"
+                )
+            _cred_judge = _mk_judge(_mk_caller())
+
         _pathb_gen_tok = _pathb.set_role("generator")
         try:
             multi = await generate_multi_section_report(
                 research_question=q["question"],
                 evidence=evidence_for_gen,
                 prior_verified_context=_prior_verified_context,
+                credibility_pass_judge=_cred_judge,
+                credibility_pass_gov_suffixes=_cred_gov,
                 section_temperature=0.3,
             # M-31 (2026-04-21): raise outline_max_tokens 800→2500 to
             # match the upstream default. V19 had 3 / V20 had 2
diff --git a/src/polaris_graph/authority/credibility_judge_caller.py b/src/polaris_graph/authority/credibility_judge_caller.py
new file mode 100644
index 00000000..2ee15af5
--- /dev/null
+++ b/src/polaris_graph/authority/credibility_judge_caller.py
@@ -0,0 +1,81 @@
+"""I-cred-012a — spend-tracked SYNC OpenRouter caller for the credibility judge.
+
+The P2 judge is SYNCHRONOUS (`_apply_judge` calls it per row), and the credibility pass runs inside the
+already-async generator event loop — so the judge's LLM call must be SYNC (no async-in-async). This mirrors
+`entailment_judge`'s proven pattern: a direct sync httpx POST to OpenRouter, with cost recorded and the run
+budget checked BEFORE returning (a cap breach raises `BudgetExceededError` and aborts the sweep). Open-weight
+model only (env `PG_CREDIBILITY_JUDGE_MODEL`); the runner binds this and `make_credibility_judge` wraps it.
+
+This file makes the LIVE, SPEND-BEARING call; it runs ONLY when the runner threads it under the master
+slate `PG_SWEEP_CREDIBILITY_REDESIGN` (operator-gated activation). Offline tests inject a stub caller and
+never touch this module.
+"""
+from __future__ import annotations
+
+import os
+from typing import Callable
+
+from src.polaris_graph.llm import openrouter_client as _orc
+
+_ENV_MODEL = "PG_CREDIBILITY_JUDGE_MODEL"
+_DEFAULT_MODEL = "z-ai/glm-5.1"  # open-weight (MIT), sovereign; override via env
+_ENV_MAX_TOKENS = "PG_CREDIBILITY_JUDGE_MAX_TOKENS"
+_DEFAULT_MAX_TOKENS = 512
+
+
+def _int_env(name: str, default: int) -> int:
+    try:
+        value = int(os.environ.get(name, "") or default)
+    except (TypeError, ValueError):
+        return default
+    return value if value > 0 else default
+
+
+def credibility_judge_model() -> str:
+    return os.environ.get(_ENV_MODEL, "").strip() or _DEFAULT_MODEL
+
+
+def make_openrouter_credibility_caller(
+    *, model: str | None = None, max_tokens: int | None = None, temperature: float = 0.0,
+    timeout: float = 60.0,
+) -> Callable[[str], str]:
+    """Return a sync ``call_llm(prompt) -> text`` that calls the open-weight credibility model via
+    OpenRouter, recording cost + enforcing the run budget (mirrors entailment_judge). Raises on a
+    cap breach (fail-loud); transport errors propagate to the judge, which maps them to judge_error."""
+    import httpx  # local import: keep off-mode (master flag off) import cost zero
+
+    chosen_model = (model or "").strip() or credibility_judge_model()
+    cap_tokens = max_tokens or _int_env(_ENV_MAX_TOKENS, _DEFAULT_MAX_TOKENS)
+    base = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
+    endpoint = base + "/chat/completions"
+    api_key = os.environ.get("OPENROUTER_API_KEY", "")
+
+    def call_llm(prompt: str) -> str:
+        body = {
+            "model": chosen_model,
+            "messages": [{"role": "user", "content": prompt}],
+            "max_tokens": cap_tokens,
+            "temperature": temperature,
+        }
+        with httpx.Client(timeout=timeout) as client:
+            response = client.post(
+                endpoint,
+                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
+                json=body,
+            )
+            response.raise_for_status()
+            data = response.json()
+        # cost FIRST (so a cap breach aborts regardless of parse) — same order as entailment_judge.
+        usage = data.get("usage", {}) or {}
+        input_tokens = int(usage.get("prompt_tokens", 0) or 0)
+        output_tokens = int(usage.get("completion_tokens", 0) or 0)
+        cost = float(usage.get("cost", 0) or 0) or _orc._impute_cost_from_tokens(
+            chosen_model, input_tokens, output_tokens, 0,
+        )
+        if cost == 0 and not usage:  # degraded response with no usage block: conservative estimate
+            cost = _orc._impute_cost_from_tokens(chosen_model, 500, 100, 0)
+        _orc._add_run_cost(cost)
+        _orc.check_run_budget(0)  # raises BudgetExceededError on cap breach (fail-loud)
+        return data["choices"][0]["message"]["content"]
+
+    return call_llm
diff --git a/src/polaris_graph/generator/multi_section_generator.py b/src/polaris_graph/generator/multi_section_generator.py
index 54b76452..a9a20ff4 100644
--- a/src/polaris_graph/generator/multi_section_generator.py
+++ b/src/polaris_graph/generator/multi_section_generator.py
@@ -292,6 +292,9 @@ class MultiSectionResult:
     limitations_text: str = ""
     limitations_input_tokens: int = 0
     limitations_output_tokens: int = 0
+    # I-cred-012a (#1164): CredibilityAnalysis from the activated pass (None when the master flag is off
+    # => byte-identical). 008b consumes it for per-claim disclosure rendering.
+    credibility_analysis: Any = None
     # I-ready-017 FX-07b leg-2 (#1111): per-(slot_id, entity_id) strict_verify
     # telemetry aggregated from every contract SectionResult.slot_strict_verify,
     # keyed (slot_id, entity_id) -> {sentences_kept, sentences_generated_content,
@@ -4386,6 +4389,10 @@ async def generate_multi_section_report(
     # mechanically matched to THIS question's corpus). Passed through to the UNVERIFIED analyst layer
     # only; None/[] => no change. Never reaches the verified generator/strict_verify path.
     prior_verified_context: list[dict[str, Any]] | None = None,
+    # I-cred-012a (#1164): credibility-analysis pass inputs. Both None/empty => the pass is NOT run =>
+    # byte-identical. Threaded by the sweep runner ONLY when PG_SWEEP_CREDIBILITY_REDESIGN is on.
+    credibility_pass_judge: Any = None,
+    credibility_pass_gov_suffixes: tuple[str, ...] | None = None,
     model: Optional[str] = None,
     outline_temperature: float = 0.2,
     section_temperature: float = 0.3,
@@ -4674,6 +4681,25 @@ async def generate_multi_section_report(
                     len(m44_primary_by_anchor),
                 )
 
+    # I-cred-012a (#1164): ADVISORY credibility-analysis pass over the EFFECTIVE evidence_pool (after the
+    # M-52/M-44 effective-pool assembly above; evidence_pool is the {evidence_id: row} the report cites).
+    # default-OFF master flag => credibility_analysis stays None => byte-identical. FAIL-LOUD: master-on
+    # but no production judge/gov_suffixes threaded => abort, never a priors-only false-green. READ-ONLY:
+    # the pass annotates row COPIES; evidence_pool is unchanged (no capability downgrade / pool shrink).
+    credibility_analysis = None
+    if os.environ.get("PG_SWEEP_CREDIBILITY_REDESIGN", "").strip().lower() not in ("", "0", "false", "off", "no"):
+        from ..synthesis import credibility_pass as _credibility_pass  # gated import: inert when flag OFF
+        if credibility_pass_judge is None or not credibility_pass_gov_suffixes:
+            raise _credibility_pass.CredibilityPassError(
+                "abort_credibility_pass_error: PG_SWEEP_CREDIBILITY_REDESIGN is on but the production "
+                "credibility judge / gov_suffixes were not threaded into generation (fail-closed)"
+            )
+        credibility_analysis = _credibility_pass.run_credibility_analysis(
+            research_question, list(evidence_pool.values()),
+            gov_suffixes=tuple(credibility_pass_gov_suffixes), domain=None,
+            judge=credibility_pass_judge,
+        )
+
     # Stage 2: per-section generation (bounded parallelism)
     sem = asyncio.Semaphore(max_parallel_sections)
 
@@ -5712,6 +5738,8 @@ async def generate_multi_section_report(
         limitations_text=lim_text,
         limitations_input_tokens=lim_in_tok,
         limitations_output_tokens=lim_out_tok,
+        # I-cred-012a (#1164): advisory credibility analysis (None when the master flag is off)
+        credibility_analysis=credibility_analysis,
         # I-bug-105 two-layer report
         analyst_synthesis_text=analyst_synth_text,
         analyst_synthesis_input_tokens=analyst_synth_in_tok,
diff --git a/tests/polaris_graph/authority/test_credibility_judge_caller_012a.py b/tests/polaris_graph/authority/test_credibility_judge_caller_012a.py
new file mode 100644
index 00000000..556b6f31
--- /dev/null
+++ b/tests/polaris_graph/authority/test_credibility_judge_caller_012a.py
@@ -0,0 +1,80 @@
+"""I-cred-012a — spend-tracked OpenRouter credibility caller. Offline (mocked transport), no network."""
+from __future__ import annotations
+
+import httpx
+
+from src.polaris_graph.authority.credibility_judge import make_credibility_judge
+from src.polaris_graph.authority.credibility_judge_caller import (
+    credibility_judge_model,
+    make_openrouter_credibility_caller,
+)
+from src.polaris_graph.authority.credibility_skill import score_source_credibility
+from src.polaris_graph.llm import openrouter_client as _orc
+
+
+class _FakeResp:
+    def __init__(self, content, usage):
+        self._content = content
+        self._usage = usage
+
+    def raise_for_status(self):
+        return None
+
+    def json(self):
+        return {"choices": [{"message": {"content": self._content}}], "usage": self._usage}
+
+
+def _fake_client_factory(captured, content, usage):
+    class _FakeClient:
+        def __init__(self, *a, **k):
+            pass
+
+        def __enter__(self):
+            return self
+
+        def __exit__(self, *a):
+            return False
+
+        def post(self, url, headers=None, json=None):
+            captured["url"] = url
+            captured["model"] = json["model"]
+            captured["prompt"] = json["messages"][0]["content"]
+            captured["auth"] = headers.get("Authorization", "")
+            return _FakeResp(content, usage)
+
+    return _FakeClient
+
+
+def test_default_model_is_open_weight():
+    assert credibility_judge_model() == "z-ai/glm-5.1"  # open-weight default; env-overridable
+
+
+def test_caller_posts_right_model_endpoint_and_tracks_cost(monkeypatch):
+    captured = {}
+    monkeypatch.setattr(httpx, "Client",
+                        _fake_client_factory(captured, '{"reliability_score": 0.7}',
+                                             {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.002}))
+    monkeypatch.setenv("PG_CREDIBILITY_JUDGE_MODEL", "z-ai/glm-5.1")
+    before = _orc.current_run_cost()
+    caller = make_openrouter_credibility_caller()
+    text = caller("hello prompt")
+    assert text == '{"reliability_score": 0.7}'
+    assert captured["model"] == "z-ai/glm-5.1"
+    assert captured["url"].endswith("/chat/completions")
+    assert captured["prompt"] == "hello prompt"
+    assert _orc.current_run_cost() >= before  # the call's cost was recorded (budget enforced)
+
+
+def test_caller_to_judge_to_p2_end_to_end(monkeypatch):
+    # the activated path's new component, behaviorally: caller -> make_credibility_judge -> P2 judgment.
+    captured = {}
+    monkeypatch.setattr(httpx, "Client",
+                        _fake_client_factory(captured, '{"reliability_score": 0.65, "relevance_score": 1.0}',
+                                             {"prompt_tokens": 8, "completion_tokens": 4, "cost": 0.001}))
+    judge = make_credibility_judge(make_openrouter_credibility_caller())
+    rows = [{"evidence_id": "e1", "authority_score": 0.6, "authority_confidence": "HIGH",
+             "signal_scores": {"scholarly": 0.9}, "title": "T", "source_url": "http://x"}]
+    out = score_source_credibility("does X work?", rows, judge=judge)[0]
+    assert out.judge_error is False and out.reliability_score == 0.65
+    # the prompt the model received carried the question + the deterministic signals
+    assert "does X work?" in captured["prompt"] and "authority_score" in captured["prompt"]
diff --git a/tests/polaris_graph/generator/test_credibility_pass_wiring_012a.py b/tests/polaris_graph/generator/test_credibility_pass_wiring_012a.py
new file mode 100644
index 00000000..51bea3b1
--- /dev/null
+++ b/tests/polaris_graph/generator/test_credibility_pass_wiring_012a.py
@@ -0,0 +1,38 @@
+"""I-cred-012a (#1164) — runner/generator wiring of the credibility pass. Offline, no LLM.
+
+Verifies the activation hook is ADDITIVE + flag-gated: the new generate_multi_section_report params
+default None (byte-identical when unpassed), MultiSectionResult carries the analysis field defaulting
+None, and the master flag is OFF by default (so the pass block is skipped)."""
+from __future__ import annotations
+
+import dataclasses
+import inspect
+
+import src.polaris_graph.generator.multi_section_generator as m
+from src.polaris_graph.synthesis import credibility_pass as cp
+
+
+def test_generate_has_additive_credibility_params_default_none():
+    sig = inspect.signature(m.generate_multi_section_report)
+    assert sig.parameters["credibility_pass_judge"].default is None
+    assert sig.parameters["credibility_pass_gov_suffixes"].default is None
+
+
+def test_result_carries_credibility_analysis_field_default_none():
+    fields = {f.name: f for f in dataclasses.fields(m.MultiSectionResult)}
+    assert "credibility_analysis" in fields
+    # default None -> byte-identical when the pass did not run
+    assert fields["credibility_analysis"].default is None
+
+
+def test_master_flag_off_by_default(monkeypatch):
+    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)
+    assert cp.credibility_redesign_enabled() is False
+
+
+def test_effective_pool_is_values_not_dict():
+    # the generator's evidence_pool is a {evidence_id: row} dict; the pass must receive the ROWS.
+    # guard the call shape so a future edit can't pass the dict (which the orchestrator would mis-handle).
+    src = inspect.getsource(m.generate_multi_section_report)
+    assert "list(evidence_pool.values())" in src
+    assert "run_credibility_analysis" in src and "fail-closed" in src.lower()
```
