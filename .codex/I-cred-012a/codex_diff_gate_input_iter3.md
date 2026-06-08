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
## PHASE: I-cred-012a (#1164) runner/generator integration — DIFF gate ITER 3. Iter-2 2xP1 + 3xP2 all addressed:
- (P1-1 control-surface bypass) credibility_judge_caller.py REWRITTEN to mirror entailment_judge's full surface: check_family_segregation(evaluator_model) at construction; PROVIDER PINNING via pathB_capture.get_role_provider('evaluator') -> provider{order,[allow_fallbacks:False],require_parameters} (no silent failover to non-sovereign/flaky provider); PATH-B capture_llm_call(role='evaluator') + raw-IO sink record(call_type='credibility_judge'); cost via _impute_cost_from_tokens/_add_run_cost + persistent append_cost_ledger_row(session_id,call_type,cost_usd,...) + check_run_budget. Missing OPENROUTER_API_KEY fails loud.
- (P1-2 masked budget breach) make_credibility_judge re-raises BudgetExceededError BEFORE the broad except (no longer -> judge_error{}); run_credibility_analysis re-raises (CredibilityPassError, BudgetExceededError) so a cap breach reaches the sweep budget-abort, not error_unexpected.
- (P2-3 LAW VI) timeout + degraded-token estimates now env-surfaced (PG_CREDIBILITY_JUDGE_TIMEOUT_S / _DEGRADED_*_TOKENS).
- (P2-1/P2-2 tests) strict cost delta (==recorded cost), provider-pin-no-fallback behavioral, budget-breach propagation through caller+judge, family-check-wired spy, missing-key fail-loud, caller->judge->P2 end-to-end. SMOKE: 32 passed.
```diff
diff --git a/src/polaris_graph/authority/credibility_judge.py b/src/polaris_graph/authority/credibility_judge.py
index b6743024..9311de09 100644
--- a/src/polaris_graph/authority/credibility_judge.py
+++ b/src/polaris_graph/authority/credibility_judge.py
@@ -108,9 +108,12 @@ def make_credibility_judge(call_llm: Callable[[str], str]) -> Callable[[str, dic
         raise ValueError("make_credibility_judge requires an injected call_llm(prompt) -> text")
 
     def judge(research_question: str, payload: dict) -> dict:
+        from src.polaris_graph.llm.openrouter_client import BudgetExceededError
         prompt = build_credibility_prompt(research_question, payload)
         try:
             text = call_llm(prompt)
+        except BudgetExceededError:
+            raise  # Codex #012a P1-2: a budget-cap breach MUST abort the sweep, never be masked as judge_error
         except Exception:
             return {}  # transport failure for this row => P2 judge_error (isolated, bounded)
         return parse_credibility_response(text)
diff --git a/src/polaris_graph/authority/credibility_judge_caller.py b/src/polaris_graph/authority/credibility_judge_caller.py
new file mode 100644
index 00000000..fcc6bfce
--- /dev/null
+++ b/src/polaris_graph/authority/credibility_judge_caller.py
@@ -0,0 +1,159 @@
+"""I-cred-012a — spend-tracked, gate-observed SYNC OpenRouter caller for the credibility judge.
+
+The P2 judge is SYNCHRONOUS and runs inside the already-async generator loop, so the LLM call must be sync
+(no async-in-async). This MIRRORS the proven `entailment_judge` control surface exactly so the credibility
+judge is NOT an unobserved/unpinned bypass (Codex I-cred-012a iter-2 P1-1):
+  * FAMILY SEGREGATION at construction — the credibility model must differ from the generator family.
+  * PROVIDER PINNING — when the Gate-B Path-B gate is active, pin to the preflight-resolved evaluator
+    provider with allow_fallbacks=False (so it can't silently fail over to a non-sovereign/flaky provider).
+  * PATH-B CAPTURE (role="evaluator") + RAW-IO SINK — so the two-family/observability gate sees the call.
+  * COST + BUDGET — cost recorded and `check_run_budget` enforced; `BudgetExceededError` PROPAGATES (it is
+    NOT caught here and must not be masked downstream) so a cap breach reaches the sweep's budget-abort.
+
+The credibility judge is an EVALUATOR-family advisory call (same role surface as the entailment judge);
+open-weight model only (env `PG_CREDIBILITY_JUDGE_MODEL`). Runs ONLY when the runner threads it under the
+master slate (operator-gated). Offline tests inject a stub caller and never reach this module.
+"""
+from __future__ import annotations
+
+import os
+import time
+import uuid
+from typing import Callable
+
+from src.polaris_graph.llm import openrouter_client as _orc
+
+_ENV_MODEL = "PG_CREDIBILITY_JUDGE_MODEL"
+_DEFAULT_MODEL = "z-ai/glm-5.1"                       # open-weight (MIT), sovereign; override via env
+_ENV_MAX_TOKENS = "PG_CREDIBILITY_JUDGE_MAX_TOKENS"
+_DEFAULT_MAX_TOKENS = 512
+_ENV_TIMEOUT_S = "PG_CREDIBILITY_JUDGE_TIMEOUT_S"
+_DEFAULT_TIMEOUT_S = 60.0
+_ENV_DEGRADED_PROMPT_TOKENS = "PG_CREDIBILITY_JUDGE_DEGRADED_PROMPT_TOKENS"
+_DEFAULT_DEGRADED_PROMPT_TOKENS = 500
+_ENV_DEGRADED_COMPLETION_TOKENS = "PG_CREDIBILITY_JUDGE_DEGRADED_COMPLETION_TOKENS"
+_DEFAULT_DEGRADED_COMPLETION_TOKENS = 100
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
+def _float_env(name: str, default: float) -> float:
+    try:
+        value = float(os.environ.get(name, "") or default)
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
+    timeout: float | None = None,
+) -> Callable[[str], str]:
+    """Return a sync ``call_llm(prompt) -> text`` that calls the open-weight credibility model via the SAME
+    control surface as the entailment judge: family-checked, provider-pinned, Path-B-captured, cost +
+    budget enforced. ``BudgetExceededError`` propagates (a cap breach must abort the sweep, not be masked)."""
+    import httpx  # local import: keep off-mode (master flag off) import cost zero
+
+    # Two-family invariant (§9.1.1): the credibility judge (evaluator-family advisory) must NOT share the
+    # generator's family. Raises at construction if misconfigured.
+    chosen_model = (model or "").strip() or credibility_judge_model()
+    _orc.check_family_segregation(evaluator_model=chosen_model)
+
+    cap_tokens = max_tokens or _int_env(_ENV_MAX_TOKENS, _DEFAULT_MAX_TOKENS)
+    call_timeout = timeout or _float_env(_ENV_TIMEOUT_S, _DEFAULT_TIMEOUT_S)
+    base = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
+    endpoint = base + "/chat/completions"
+    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
+    if not api_key:
+        raise RuntimeError("PG_SWEEP_CREDIBILITY_REDESIGN credibility judge requires OPENROUTER_API_KEY")
+
+    def call_llm(prompt: str) -> str:
+        started = time.monotonic()
+        json_body: dict = {
+            "model": chosen_model,
+            "messages": [{"role": "user", "content": prompt}],
+            "temperature": temperature,
+            "max_tokens": cap_tokens,
+        }
+        # PROVIDER PINNING (mirror entailment_judge): pin to the preflight-resolved evaluator provider,
+        # allow_fallbacks=False — never silently fail over to a non-sovereign/untested provider.
+        try:
+            from src.polaris_graph.benchmark import pathB_capture as _pathb
+            gate_provider = _pathb.get_role_provider("evaluator")
+        except Exception:  # noqa: BLE001 — routing lookup must never break the call
+            _pathb = None
+            gate_provider = None
+        if gate_provider:
+            json_body["provider"] = {
+                "order": [gate_provider], "allow_fallbacks": False, "require_parameters": True,
+            }
+
+        with httpx.Client(timeout=call_timeout) as client:
+            response = client.post(
+                endpoint,
+                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
+                json=json_body,
+            )
+            response.raise_for_status()
+            data = response.json()
+
+        # PATH-B two-family capture + raw-IO sink (so the gate observes this evaluator-role call).
+        try:
+            if _pathb is not None and _pathb.is_active():
+                _pathb.capture_llm_call(
+                    role="evaluator",
+                    messages=[{"role": "user", "content": prompt}],
+                    raw_response=data,
+                )
+        except Exception:  # noqa: BLE001 — capture must never break the call
+            pass
+        try:
+            io_sink = _orc.current_raw_io_sink()
+            if io_sink is not None:
+                io_sink.record(
+                    call_id=uuid.uuid4().hex, call_type="credibility_judge", role="evaluator",
+                    request=json_body, raw_response=data,
+                    duration_ms=(time.monotonic() - started) * 1000.0, status="ok",
+                )
+        except Exception:  # noqa: BLE001
+            pass
+
+        # COST + BUDGET first (so a cap breach aborts regardless of parse) — same order as entailment_judge.
+        usage = data.get("usage", {}) or {}
+        input_tokens = int(usage.get("prompt_tokens", 0) or 0)
+        output_tokens = int(usage.get("completion_tokens", 0) or 0)
+        cost = float(usage.get("cost", 0) or 0) or _orc._impute_cost_from_tokens(
+            chosen_model, input_tokens, output_tokens, 0,
+        )
+        if cost == 0 and not usage:  # degraded response, no usage block: conservative estimate
+            cost = _orc._impute_cost_from_tokens(
+                chosen_model,
+                _int_env(_ENV_DEGRADED_PROMPT_TOKENS, _DEFAULT_DEGRADED_PROMPT_TOKENS),
+                _int_env(_ENV_DEGRADED_COMPLETION_TOKENS, _DEFAULT_DEGRADED_COMPLETION_TOKENS),
+                0,
+            )
+        _orc._add_run_cost(cost)
+        try:
+            _orc.append_cost_ledger_row(
+                session_id=_orc.current_run_id() or "credibility_judge",
+                call_type="credibility_judge",
+                cost_usd=cost,
+                input_tokens=input_tokens,
+                output_tokens=output_tokens,
+            )
+        except Exception:  # noqa: BLE001 — persistent ledger IO is non-critical
+            pass
+        _orc.check_run_budget(0)  # raises BudgetExceededError on cap breach (MUST propagate — not masked)
+        return data["choices"][0]["message"]["content"]
+
+    return call_llm
diff --git a/src/polaris_graph/synthesis/credibility_pass.py b/src/polaris_graph/synthesis/credibility_pass.py
index 8f6b7d83..248ff7b2 100644
--- a/src/polaris_graph/synthesis/credibility_pass.py
+++ b/src/polaris_graph/synthesis/credibility_pass.py
@@ -104,14 +104,17 @@ def run_credibility_analysis(
             "judge; refusing to run priors-only (a false-green advisory). Wire the production judge or "
             "leave PG_SWEEP_CREDIBILITY_REDESIGN off."
         )
+    from src.polaris_graph.llm.openrouter_client import BudgetExceededError
     try:
         return _run_chain(
             research_question, rows,
             gov_suffixes=gov_suffixes, domain=domain, judge=judge, now_year=now_year,
         )
-    except CredibilityPassError:
+    except (CredibilityPassError, BudgetExceededError):
+        # CredibilityPassError = fail-loud abort; BudgetExceededError (Codex #012a P1-2) must reach the
+        # sweep's budget-abort path cleanly, NOT be masked as a generic credibility-pass error.
         raise
-    except Exception as exc:  # ANY wired-module failure → fail-loud abort, never a silent false-green
+    except Exception as exc:  # ANY OTHER wired-module failure → fail-loud abort, never a silent false-green
         raise CredibilityPassError(
             f"abort_credibility_pass_error: a wired credibility module failed "
             f"({type(exc).__name__}): {exc}"
diff --git a/tests/polaris_graph/authority/test_credibility_judge_caller_012a.py b/tests/polaris_graph/authority/test_credibility_judge_caller_012a.py
new file mode 100644
index 00000000..50392c3c
--- /dev/null
+++ b/tests/polaris_graph/authority/test_credibility_judge_caller_012a.py
@@ -0,0 +1,120 @@
+"""I-cred-012a — spend-tracked, gate-observed credibility caller. Offline (mocked transport), no network."""
+from __future__ import annotations
+
+import httpx
+import pytest
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
+@pytest.fixture(autouse=True)
+def _env(monkeypatch):
+    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
+    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")  # glm != deepseek => family ok
+    monkeypatch.setenv("PG_CREDIBILITY_JUDGE_MODEL", "z-ai/glm-5.1")
+    _orc.reset_run_cost()  # isolate per-test run cost (the budget-breach test accumulates 999.0)
+
+
+def _fake_client(captured, content, usage):
+    class _Resp:
+        def raise_for_status(self):
+            return None
+
+        def json(self):
+            return {"choices": [{"message": {"content": content}}], "usage": usage}
+
+    class _Client:
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
+            captured["body"] = json
+            captured["prompt"] = json["messages"][0]["content"]
+            return _Resp()
+
+    return _Client
+
+
+def test_default_model_is_open_weight():
+    assert credibility_judge_model() == "z-ai/glm-5.1"
+
+
+def test_strict_cost_delta_and_endpoint(monkeypatch):
+    captured = {}
+    monkeypatch.setattr(httpx, "Client", _fake_client(
+        captured, '{"reliability_score": 0.7}', {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.002}))
+    before = _orc.current_run_cost()
+    text = make_openrouter_credibility_caller()("hi")
+    assert text == '{"reliability_score": 0.7}'
+    assert captured["url"].endswith("/chat/completions") and captured["model"] == "z-ai/glm-5.1"
+    assert abs(_orc.current_run_cost() - before - 0.002) < 1e-9  # STRICT delta == the call's recorded cost
+
+
+def test_provider_pinned_no_fallback_when_gate_active(monkeypatch):
+    captured = {}
+    monkeypatch.setattr(httpx, "Client", _fake_client(captured, "{}", {"cost": 0.001}))
+    from src.polaris_graph.benchmark import pathB_capture as _pathb
+    monkeypatch.setattr(_pathb, "get_role_provider",
+                        lambda role: "fireworks" if role == "evaluator" else None)
+    make_openrouter_credibility_caller()("hi")
+    assert captured["body"]["provider"] == {
+        "order": ["fireworks"], "allow_fallbacks": False, "require_parameters": True}
+
+
+def test_budget_breach_propagates_through_caller_and_judge(monkeypatch):
+    from src.polaris_graph.llm.openrouter_client import BudgetExceededError
+    monkeypatch.setattr(httpx, "Client", _fake_client({}, "{}", {"cost": 999.0}))
+
+    def _boom(*a, **k):
+        raise BudgetExceededError("cap breached")
+
+    monkeypatch.setattr(_orc, "check_run_budget", _boom)
+    caller = make_openrouter_credibility_caller()
+    with pytest.raises(BudgetExceededError):
+        caller("hi")
+    # P1-2: the breach must NOT be masked as judge_error — it propagates through make_credibility_judge.
+    judge = make_credibility_judge(caller)
+    with pytest.raises(BudgetExceededError):
+        judge("q", {"title": "t"})
+
+
+def test_missing_api_key_fails_loud(monkeypatch):
+    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
+    with pytest.raises(RuntimeError):
+        make_openrouter_credibility_caller()
+
+
+def test_family_segregation_is_checked_at_construction(monkeypatch):
+    # P1-1: the caller MUST run the two-family check on the credibility model (so a misconfig that puts it
+    # in the generator's family fails loudly). Verify the check is wired (not its internal behavior).
+    called = {}
+    monkeypatch.setattr(_orc, "check_family_segregation", lambda **kw: called.update(kw))
+    make_openrouter_credibility_caller(model="z-ai/glm-5.1")
+    assert called.get("evaluator_model") == "z-ai/glm-5.1"
+
+
+def test_caller_to_judge_to_p2_end_to_end(monkeypatch):
+    captured = {}
+    monkeypatch.setattr(httpx, "Client", _fake_client(
+        captured, '{"reliability_score": 0.65, "relevance_score": 1.0}',
+        {"prompt_tokens": 8, "completion_tokens": 4, "cost": 0.001}))
+    judge = make_credibility_judge(make_openrouter_credibility_caller())
+    rows = [{"evidence_id": "e1", "authority_score": 0.6, "authority_confidence": "HIGH",
+             "signal_scores": {"scholarly": 0.9}, "title": "T", "source_url": "http://x"}]
+    out = score_source_credibility("does X work?", rows, judge=judge)[0]
+    assert out.judge_error is False and out.reliability_score == 0.65
+    assert "does X work?" in captured["prompt"] and "authority_score" in captured["prompt"]
```
