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
## PHASE: I-cred-013 (#1163) preflight — DIFF gate ITER 2. Iter-1 2xP1 (verifier probe not in production call shape) FIXED + Claude-reviewed line-by-line:
- _real_chat_completion_alive(role, slug) now builds the request via NEW _build_probe_request(role, slug) which REUSES the production transports' OWN request construction (NOT a re-derived generic body):
  - self_host (P1-1 fix): role_endpoint(role) [per-role PG_<ROLE>_BASE_URL + PG_<ROLE>_API_KEY] + _CHAT_COMPLETIONS_PATH (/v1/chat/completions, was /chat/completions) + _build_body; Authorization OMITTED when the per-role key is unset (mirrors OpenAICompatibleRoleTransport.complete:482-484) — a keyless vLLM no longer false-FAILS.
  - openrouter (P1-2 fix): openrouter_role_endpoint(role) + _build_openrouter_body (per-role reasoning + provider routing/require_parameters/order/allow_fallbacks) + production headers — was a generic minimal body that could pass a generic route while the real verifier route fails. endpoint/auth were already correct, unchanged.
- _clamp_probe_budget shrinks only the token MAGNITUDES (Mirror numeric reasoning cap->16 + top-level>cap; Judge/Sentinel effort KEPT + top-level->32) preserving the production 'top-level max_tokens > reasoning budget' invariant and ALL routing keys. Env knobs PG_PREFLIGHT_PROBE_MAX_TOKENS / _REASONING_TOKENS.
- P2 tests added: self_host keyed+keyless, openrouter body-match, fail-closed, clamp invariant (39 preflight tests). Probe stays sync (both transports sync) + dependency-injected (offline MockTransport drives every dead->GateError). 
HONEST LIVE caveat: tests prove the request is CONSTRUCTED identically to production (magnitudes excluded); they cannot prove offline that OpenRouter ACCEPTS the clamped body under effort=xhigh + max_tokens=32 — that one piece is first-live-probe verifiable (PG_PREFLIGHT_PROBE_MAX_TOKENS is the knob). SMOKE: 39 preflight + 362 broader (tests/dr_benchmark + tests/preflight) passed.
```diff
diff --git a/scripts/dr_benchmark/false_alarm_checks.py b/scripts/dr_benchmark/false_alarm_checks.py
new file mode 100644
index 00000000..63a27f14
--- /dev/null
+++ b/scripts/dr_benchmark/false_alarm_checks.py
@@ -0,0 +1,84 @@
+"""I-cred-013 (#1163): the 5 recurring false-alarm regression checks — as a NON-TEST module.
+
+These are the durable kills for the 5 false alarms the operator flagged as repeat-offenders. They live
+HERE (not only in ``tests/preflight/test_false_alarm_regressions.py``) so that BOTH:
+  - the pytest regression locks (CI), and
+  - the live super-heavy pre-spend preflight (``super_heavy_preflight``, runs on the paid VM)
+import the SAME assertions. The production preflight must NOT depend on ``tests/`` being importable in
+the VM launch shape (cwd/sys.path luck), so the shared logic is extracted to this importable module and
+the test module is a thin re-export.
+
+Each check is no-arg and raises ``AssertionError`` on a resurfaced false alarm (so the pytest module is a
+trivial wrapper). Offline, deterministic, no spend, no network.
+"""
+from __future__ import annotations
+
+import pathlib
+import re
+
+# Repo root = three parents up from scripts/dr_benchmark/false_alarm_checks.py.
+ROOT = pathlib.Path(__file__).resolve().parents[2]
+
+
+def check_fa1_crlf_gitattributes_rule_committed() -> None:
+    """FA1: the signed-bundle fixtures must carry a '-text' .gitattributes rule so core.autocrlf can
+    NEVER rewrite the SHA256-pinned / GPG-signed bytes to CRLF (the 'SHA256_MISMATCH / needs operator
+    signing key' false alarm). The demo key 6336C4448C1901CC is local; conformance is never env-blocked."""
+    gitattributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
+    assert re.search(r"tests/fixtures/signed_bundle/\*\*\s+-text", gitattributes), (
+        "the signed_bundle '-text' .gitattributes rule is gone — CRLF will silently re-break the "
+        "SHA256-pinned/GPG-signed fixtures and resurface the 'needs operator key' false alarm"
+    )
+
+
+def check_fa2_competitor_outputs_present() -> None:
+    """FA2: the ChatGPT + Gemini competitor DR outputs for all 5 golden Qs ARE committed — so 'we've
+    never run the head-to-head' is always a false claim. Grep the repo before asserting any negative."""
+    base = ROOT / "outputs" / "dr_benchmark" / "external_outputs"
+    questions = ["Q72_ai_labor", "Q75_metal_ions_cvd", "Q76_gut_microbiota",
+                 "Q78_parkinsons_dbs", "Q90_adas_liability"]
+    for system in ("gpt_5_5_pro", "gemini_3_1_pro"):
+        for q in questions:
+            path = base / system / f"{q}.md"
+            assert path.exists() and path.stat().st_size > 0, f"competitor output missing/empty: {path}"
+
+
+def check_fa3_run_health_fail_loud_guard_present() -> None:
+    """FA3: a degraded / dead-route run must FAIL LOUD (abort), never swallow into a false-green. The
+    behavioral run-health guard must remain wired in the Gate-B run path."""
+    src = (ROOT / "scripts" / "dr_benchmark" / "pathB_run_gate.py").read_text(encoding="utf-8")
+    assert any(tok in src for tok in ("PG_RUN_HEALTH_GATE", "abort_discovery_degraded", "PG_BEHAVIORAL_CANARY")), (
+        "the run-health / behavioral-canary fail-loud guard is gone — a dead model route could ship a "
+        "false-green run on dead discovery (the drb_72 silent-downgrade lesson)"
+    )
+
+
+def check_fa4_empty_response_failover_present() -> None:
+    """FA4: an empty-200 (mirror-blank) must be handled as an intermittent PROVIDER failure (retry /
+    failover), never silently read as the model's defect / a blank answer."""
+    src = (ROOT / "src" / "polaris_graph" / "llm" / "openrouter_client.py").read_text(encoding="utf-8")
+    assert re.search(r"empty[_ ]?response|empty.{0,8}200|allow_fallbacks|provider.{0,12}fail", src, re.I), (
+        "the empty-200 provider-failover handling is gone — mirror-blanks would be misread as a model "
+        "defect instead of an intermittent provider failure"
+    )
+
+
+def check_fa5_journal_only_gated_by_source_restriction() -> None:
+    """FA5: the journal-only adequacy floor must be gated by the protocol's source_restriction — a
+    corpus_approval_denied is NOT auto-authorize and NOT auto-fix-the-classifier; it depends on the
+    question's own declared restriction."""
+    from src.polaris_graph.nodes.journal_only_filter import journal_only_active
+    assert journal_only_active(None) is False                       # no protocol -> floor does NOT fire
+    assert journal_only_active({}) is False                          # no restriction -> floor does NOT fire
+    # a protocol that declares journal_only is flag-dependent (never crashes, never fires blindly)
+    assert journal_only_active({"source_restriction": "journal_only"}) in (True, False)
+
+
+# The 5 checks in CI/preflight order (the runtime preflight re-asserts these same five).
+ALL_CHECKS = (
+    check_fa1_crlf_gitattributes_rule_committed,
+    check_fa2_competitor_outputs_present,
+    check_fa3_run_health_fail_loud_guard_present,
+    check_fa4_empty_response_failover_present,
+    check_fa5_journal_only_gated_by_source_restriction,
+)
diff --git a/scripts/dr_benchmark/run_gate_b.py b/scripts/dr_benchmark/run_gate_b.py
index 39e026cc..356f167a 100644
--- a/scripts/dr_benchmark/run_gate_b.py
+++ b/scripts/dr_benchmark/run_gate_b.py
@@ -509,6 +509,13 @@ _FULL_CAPABILITY_BENCHMARK_SLATE: dict[str, str] = {
     # be ALIVE or the run fails closed before spend. OFF would let a dead-discovery run go green (the
     # drb_72 failure). Force-on + required below; the canary itself runs only on the live path.
     "PG_BEHAVIORAL_CANARY": "1",
+    # I-cred-013 (#1163): the SUPER-HEAVY behavioral pre-spend preflight MUST run on the real beat-both
+    # Gate-B run — it COMPOSES CANARY-01 with: EVERY model slug (generator + 3 verifiers + the
+    # credibility judge when active) ALIVE in its production call shape, STORM/discovery non-empty,
+    # host-local chromium present, and a RUNTIME re-assertion of the 5 recurring false-alarm regression
+    # locks. OFF would drop back to the lighter canary alone and let a dead verifier/STORM/browser tier
+    # ship a false-green paid run. Force-on + required below; the preflight runs only on the live path.
+    "PG_SUPER_HEAVY_PREFLIGHT": "1",
     # I-ready-017 FX-14 (#1129): force the custody-lane honesty marker ON so the paid run emits
     # custody_lane_status.json (not_applicable_planner_lane) instead of a silently-empty
     # v29_primary_custody.json / m44_primary_citation_telemetry.json when primary-trial seeds reach
@@ -566,6 +573,10 @@ _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS = (
     # I-ready-017 CANARY-01 (#1108): the behavioral pre-spend canary must be ON for a paid run — OFF
     # would let a dead-discovery / structured-output-404 run go green (the drb_72 failure).
     "PG_BEHAVIORAL_CANARY",
+    # I-cred-013 (#1163): the super-heavy behavioral preflight must be ON for a paid beat-both run — OFF
+    # drops to the lighter canary alone and lets a dead verifier/STORM/credibility/browser tier or a
+    # resurfaced false alarm ship a false-green paid run. Fail closed if it is not active.
+    "PG_SUPER_HEAVY_PREFLIGHT",
     # I-ready-017 FX-14 (#1129): custody-lane honesty marker required — otherwise an explicit
     # PG_CUSTODY_LANE_MARKER=0 survives the slate setdefault (the I-cap-005 P1-1 pattern) and the paid
     # run silently writes empty v29/m44 custody telemetry with no not_applicable disambiguation.
@@ -607,6 +618,9 @@ _BENCHMARK_FORCE_ON_FLAGS = frozenset({
     # I-ready-017 CANARY-01 (#1108): force-on the behavioral pre-spend canary so an operator =0 cannot
     # survive the slate and let a dead-discovery run go green.
     "PG_BEHAVIORAL_CANARY",
+    # I-cred-013 (#1163): force-on the super-heavy behavioral preflight so an operator =0 cannot survive
+    # the slate and silently drop the paid run back to the lighter canary alone.
+    "PG_SUPER_HEAVY_PREFLIGHT",
     # I-ready-017 FL-05b (#1137): force-on the run-health backstop so an explicit operator
     # PG_RUN_HEALTH_GATE=0 cannot survive the setdefault slate and silently restore the
     # ship-green-on-degraded-discovery behavior (the I-cap-005 P1-1 force-on pattern).
@@ -964,12 +978,21 @@ async def run_gate_b_query(
         # cannot resolve — openrouter: a pinned slug missing from the catalog; self_host: a
         # missing PG_<ROLE>_BASE_URL; either: a 4-role family collision.
         preflight_four_role_transport()
-        # I-ready-017 CANARY-01 (#1108): BEHAVIORAL pre-spend canary — real call shapes (structured
-        # output on the searcher/generator slug = the FX-01-keystone 404 class + a 1-query live search
-        # returning >0 sources) must be ALIVE, or FAIL CLOSED before any sweep spend. Live-path only
-        # (transport injected = offline test, no real calls); gated by PG_BEHAVIORAL_CANARY (slate).
-        from scripts.dr_benchmark.pathB_run_gate import behavioral_canary
-        await behavioral_canary()
+        # I-cred-013 (#1163): the SUPER-HEAVY behavioral pre-spend preflight. COMPOSES the CANARY-01
+        # behavioral canary (#1108 — structured-output on the searcher/generator slug = the FX-01-keystone
+        # 404 class + a 1-query live search >0 sources) with the heavy pre-beat-both checks: EVERY model
+        # slug (generator + the 3 verifiers + the credibility judge when active) ALIVE in its production
+        # call shape, STORM/discovery non-empty, host-local chromium present, and a RUNTIME re-assertion
+        # of the 5 recurring false-alarm regression locks. FAIL CLOSED before any sweep spend. Live-path
+        # only (transport injected = offline test, no real calls); gated by PG_SUPER_HEAVY_PREFLIGHT
+        # (slate force-on + required). When PG_SUPER_HEAVY_PREFLIGHT is off, fall back to the CANARY-01
+        # behavioral canary alone (byte-unchanged from #1108).
+        if os.getenv("PG_SUPER_HEAVY_PREFLIGHT", "0").strip().lower() in ("1", "true"):
+            from scripts.dr_benchmark.super_heavy_preflight import super_heavy_preflight
+            await super_heavy_preflight()
+        else:
+            from scripts.dr_benchmark.pathB_run_gate import behavioral_canary
+            await behavioral_canary()
         active_transport = build_gate_b_transport()
         # P2 (I-meta-007d): record the machine-readable stage marker so a future gate/manifest
         # reader can tell this benchmark OpenRouter run apart from the sovereign self-host path.
diff --git a/scripts/dr_benchmark/super_heavy_preflight.py b/scripts/dr_benchmark/super_heavy_preflight.py
new file mode 100644
index 00000000..4ddc51e7
--- /dev/null
+++ b/scripts/dr_benchmark/super_heavy_preflight.py
@@ -0,0 +1,483 @@
+"""I-cred-013 (#1163): the SUPER-HEAVY behavioral pre-spend preflight (pre-beat-both-run gate).
+
+EXTENDS the existing behavioral canary (``pathB_run_gate.behavioral_canary``, CANARY-01 #1108) rather
+than rebuilding it. The canary already probes (a) the searcher/generator structured-output call shape
+and (b) a real 1-query live search. This module ADDS the heavy checks the operator directed in #1163,
+and fails CLOSED (raises ``GateError``) before any token is spent:
+
+  1. behavioral canary (delegated, unchanged) — structured-output + 1-query live search are ALIVE.
+  2. EVERY model slug ALIVE IN ITS PRODUCTION CALL SHAPE (a real 1-token probe, not a config check
+     and not a catalog lookup):
+       - generator  -> generate_structured on PG_GENERATOR_MODEL (the FX-01-keystone 404 class;
+         shared with the canary's structured probe).
+       - mirror / sentinel / judge -> a real /chat/completions POST on the ACTIVE benchmark/self-host
+         slug resolved EXACTLY as production resolves it (verifier_model_slugs() — mode-aware, so the
+         minimax Sentinel benchmark slug is probed, not the lock's self-host slug). This real-ROUTE
+         check is LAYERED ON TOP of the catalog + reasoning-capability check the live path already runs
+         immediately before (preflight_four_role_transport): together they cover both the silent
+         dead-route class AND a reasoning-param routing refusal. The probe body itself is a minimal
+         1-token completion (it proves the slug RESOLVES + routes), not the full reasoning body.
+       - credibility judge -> a real call through its OWN sync caller
+         (make_openrouter_credibility_caller) on PG_CREDIBILITY_JUDGE_MODEL, but ONLY when the
+         credibility redesign is active in this run (PG_SWEEP_CREDIBILITY_REDESIGN) — probe-alive
+         must match production activation.
+  3. STORM/discovery is non-empty — a real, minimal STORM persona-discovery call returns >0 personas
+     (the discovery generate_structured path the drb_72 collapse silently killed).
+  4. Playwright/chromium present on the run host — reuse the FX-16 fail-closed probe
+     (pg_preflight.test_chromium_browser_available); FAIL -> GateError. HOST-LOCAL only (a local PASS
+     does not prove the VM; the VM-side chromium install is FX-16's operator-gated step).
+  5. RUNTIME re-assertion of the 5 recurring false-alarm regression locks
+     (tests/preflight/test_false_alarm_regressions.py) so none can silently resurface at run time:
+     CRLF signed-fixtures rule, competitor outputs present, fail-loud run-health guard, mirror-blank
+     provider failover, journal-only gated by source_restriction.
+
+OFFLINE-TESTABLE: every live probe is DEPENDENCY-INJECTED (a callable kwarg with a real default), so
+the OFFLINE smoke exercises the fail-closed logic (a dead slug / empty STORM / absent chromium ->
+GateError) WITHOUT real network or spend. The LIVE invocation (real defaults) runs pre-spend on the
+real Gate-B run.
+
+NO SPEND / NO NETWORK AT IMPORT: the live probe bodies import their heavy deps lazily and only run
+when called. Importing this module opens no socket.
+"""
+from __future__ import annotations
+
+import os
+from typing import Awaitable, Callable, Mapping
+
+from scripts.dr_benchmark.pathB_run_gate import GateError, behavioral_canary
+
+# The credibility-redesign master flag. The credibility judge LLM only fires in production when this is
+# active (run_honest_sweep_r3.py:4711), so its slug is probed only then — probe-alive must match the
+# run's real activation, never fail-closed on a model the run will not call.
+_CREDIBILITY_REDESIGN_FLAG = "PG_SWEEP_CREDIBILITY_REDESIGN"
+# OFF tokens — identical to the runner's read (run_honest_sweep_r3.py:4711).
+_CREDIBILITY_OFF_TOKENS = ("", "0", "false", "off", "no")
+
+
+def credibility_redesign_active() -> bool:
+    """True iff the credibility-redesign pass is active for this run (matches the runner's read)."""
+    return (
+        os.environ.get(_CREDIBILITY_REDESIGN_FLAG, "").strip().lower()
+        not in _CREDIBILITY_OFF_TOKENS
+    )
+
+
+# --------------------------------------------------------------------------- live probe defaults
+async def _default_generator_slug_probe() -> bool:
+    """REAL generate_structured on PG_GENERATOR_MODEL (the production generator/searcher slug). Reuses
+    the canary's own default probe so the generator slug is probed in EXACTLY one place (the FX-01 404
+    class). Returns True iff a schema object parses; raises GateError on the NoEndpointError/404 class."""
+    from scripts.dr_benchmark.pathB_run_gate import _default_structured_output_probe
+
+    return await _default_structured_output_probe()
+
+
+# Probe token magnitudes (LAW VI, env-overridable). A liveness probe only needs to prove the route
+# RESOLVES + the production call shape is ACCEPTED — NOT to emit a real verdict — so the per-role
+# reasoning/output budgets the production body-builder sets (Mirror 24k / Judge 16k / decomp-Sentinel
+# 16k) are clamped DOWN to a cheap, but STILL-VALID, magnitude. The clamp PRESERVES the production
+# invariant that top-level max_tokens must exceed the reasoning budget (openrouter_role_transport
+# lines 526-533); shrinking only the magnitudes keeps the provider/reasoning routing — the very
+# `require_parameters`-filtered keys whose ABSENCE is the P1-2 false-pass class — byte-identical to
+# production. Cost is driven by tokens actually GENERATED (a 1-token "ok" reply stops at EOS), not the
+# ceiling, so this is ~free while remaining a faithful, routable body.
+_PROBE_REASONING_TOKENS = int(os.getenv("PG_PREFLIGHT_PROBE_REASONING_TOKENS", "16"))
+_PROBE_MAX_TOKENS = int(os.getenv("PG_PREFLIGHT_PROBE_MAX_TOKENS", "32"))
+
+
+def _clamp_probe_budget(body: dict) -> dict:
+    """Shrink the production body's token MAGNITUDES to a cheap probe size WITHOUT changing its shape.
+
+    Mutates ``body`` in place and returns it. Preserves every routing key the production builder set
+    (``provider`` / ``reasoning`` enabled+effort or numeric cap) — those are exactly what OpenRouter's
+    ``require_parameters`` filters on, so dropping them would re-introduce the P1-2 false-pass. Only the
+    numeric budgets shrink, and they stay COHERENT with the production rule "top-level max_tokens must
+    exceed the reasoning budget":
+      - numeric reasoning cap (Mirror ``reasoning.max_tokens``): cap -> _PROBE_REASONING_TOKENS, and
+        top-level max_tokens -> a value STRICTLY above it (cap + margin).
+      - effort reasoning (Judge / decomposition-Sentinel ``reasoning.effort``): effort is KEPT
+        (mutually exclusive with reasoning.max_tokens, NOT with top-level max_tokens), only the
+        top-level max_tokens is lowered to the small probe ceiling.
+      - no reasoning block (classifier Sentinel): just lower the top-level max_tokens.
+    """
+    reasoning = body.get("reasoning")
+    if isinstance(reasoning, dict) and "max_tokens" in reasoning:
+        # Mirror's NUMERIC reasoning cap path: shrink the cap, keep top-level strictly above it.
+        reasoning["max_tokens"] = _PROBE_REASONING_TOKENS
+        body["max_tokens"] = max(_PROBE_MAX_TOKENS, _PROBE_REASONING_TOKENS + 8)
+    else:
+        # Effort-based reasoning (Judge / decomp-Sentinel) OR no reasoning (classifier Sentinel):
+        # effort and top-level max_tokens are NOT mutually exclusive, so keep the effort block as-is
+        # and only lower the top-level ceiling. (Never set max_tokens=1 — a provider may reject it.)
+        body["max_tokens"] = _PROBE_MAX_TOKENS
+    return body
+
+
+def _build_probe_request(role: str, slug: str):
+    """Build the production verifier request body+endpoint+headers for ``role`` in the ACTIVE transport
+    mode, REUSING the production transports' OWN request-construction helpers (NOT a re-derived generic
+    body). Returns ``(endpoint, headers, body)``.
+
+    - ``self_host``: ``role_endpoint(role)`` (per-role PG_<ROLE>_BASE_URL + PG_<ROLE>_API_KEY, NEVER the
+      OpenRouter key) + the ``/v1/chat/completions`` path the self-host transport appends + ``_build_body``
+      (the passthrough allowlist + the decomposition-Sentinel max_tokens floor). Authorization is OMITTED
+      when PG_<ROLE>_API_KEY is unset — EXACTLY as ``OpenAICompatibleRoleTransport.complete`` does (a
+      keyless vLLM is valid; sending an empty ``Bearer `` is a false-FAIL, the P1-1 class).
+    - ``openrouter``: ``openrouter_role_endpoint(role)`` (OpenRouter base + key + benchmark slug) + the
+      ``/chat/completions`` path + ``_build_openrouter_body`` (the per-role reasoning + provider routing
+      the production verifier call carries — the P1-2 class). Headers mirror the production transport.
+
+    The token budgets are then clamped to a cheap probe size via ``_clamp_probe_budget`` (route resolves,
+    call shape accepted, ~free). Slug RESOLUTION stays production-exact (the caller passes the
+    ``verifier_model_slugs()`` slug, which == the builder's body["model"] on both routes)."""
+    from src.polaris_graph.roles.role_transport import RoleRequest
+
+    # A minimal 1-token-ish completion request — prompt-only so _normalize_messages builds a clean
+    # single user turn (it raises without prompt/messages). Empty params: the role-specific helpers
+    # fill in reasoning/provider/max_tokens per role.
+    request = RoleRequest(role=role, model_slug=slug, prompt="ok", params={})
+
+    from scripts.dr_benchmark.run_gate_b import four_role_transport_mode
+
+    mode = four_role_transport_mode()
+    if mode == "self_host":
+        from src.polaris_graph.roles.openai_compatible_transport import (
+            _CHAT_COMPLETIONS_PATH,
+            _build_body,
+            _normalize_messages,
+            role_endpoint,
+        )
+
+        base_url, api_key, model_slug = role_endpoint(role)
+        normalized_messages = _normalize_messages(request)
+        body = _clamp_probe_budget(_build_body(request, model_slug, normalized_messages))
+        endpoint = f"{base_url}{_CHAT_COMPLETIONS_PATH}"
+        # No-leak / keyless-vLLM: Authorization ONLY when a per-role key is set (mirrors
+        # OpenAICompatibleRoleTransport.complete lines 482-484) — never an empty `Bearer `.
+        headers = {"Content-Type": "application/json"}
+        if api_key:
+            headers["Authorization"] = f"Bearer {api_key}"
+        return endpoint, headers, body
+
+    # openrouter (benchmark, default)
+    from src.polaris_graph.roles.openai_compatible_transport import _normalize_messages
+    from src.polaris_graph.roles.openrouter_role_transport import (
+        _CHAT_COMPLETIONS_PATH,
+        _build_openrouter_body,
+        openrouter_role_endpoint,
+    )
+
+    base_url, api_key, model_slug = openrouter_role_endpoint(role)
+    normalized_messages = _normalize_messages(request)
+    body = _clamp_probe_budget(_build_openrouter_body(request, model_slug, normalized_messages))
+    endpoint = f"{base_url}{_CHAT_COMPLETIONS_PATH}"
+    headers = {
+        "Authorization": f"Bearer {api_key}",
+        "Content-Type": "application/json",
+        "HTTP-Referer": "https://polaris-research.ai",
+        "X-Title": "polaris graph",
+    }
+    return endpoint, headers, body
+
+
+def _real_chat_completion_alive(
+    role: str, slug: str, *, http_client=None
+) -> bool:
+    """One real, minimal completion POST on the verifier ``role``'s slug, built in the EXACT PRODUCTION
+    CALL SHAPE for the active transport mode (``_build_probe_request`` reuses the production transports'
+    OWN endpoint/auth/body construction). A dead slug (NoEndpoint / 404 / model offline / mis-routed) is
+    a non-2xx -> ``raise_for_status()`` raises -> the caller maps it to GateError. The token budgets are
+    clamped cheap, so it is ~free. This is NOT a catalog lookup and NOT a generic minimal body: it
+    exercises the actual routing (endpoint path + auth presence/absence + provider/reasoning routing)
+    the run uses — the drb_72 silent-dead-route + mis-route class the catalog preflight alone missed.
+
+    ``http_client`` is INJECTABLE (an ``httpx.Client`` or a ``MockTransport``-backed one) so the offline
+    smoke drives the 404 -> GateError leaf with NO network; the live path passes None (a real client)."""
+    import httpx
+
+    endpoint, headers, body = _build_probe_request(role, slug)
+    own_client = http_client is None
+    client = http_client or httpx.Client(timeout=float(os.getenv("PG_PREFLIGHT_PROBE_TIMEOUT", "30")))
+    try:
+        response = client.post(endpoint, headers=headers, json=body)
+        response.raise_for_status()  # 404 / NoEndpoint -> HTTPStatusError -> GateError upstream
+        data = response.json()
+    finally:
+        if own_client:
+            client.close()
+    # A routed-but-empty 200 still proves the slug RESOLVES (routing alive); content can be empty for a
+    # 1-token probe. We only require a well-formed choices envelope.
+    return isinstance(data.get("choices"), list) and len(data["choices"]) >= 1
+
+
+def _default_verifier_slug_probe(http_client=None) -> dict[str, str]:
+    """Probe EVERY active verifier slug (mirror/sentinel/judge) in its EXACT production call shape.
+
+    Resolves each slug EXACTLY as production does, via ``run_gate_b.verifier_model_slugs()`` (mode-aware:
+    benchmark lineup on the OpenRouter route = the minimax Sentinel; the lock's self-host slugs on the
+    self_host route) — NEVER a hardcoded list and NEVER naively the lock. For each role
+    ``_real_chat_completion_alive`` builds the request via the PRODUCTION transport's own helpers
+    (``_build_probe_request``), so the probe hits the SAME endpoint path, the SAME auth presence/absence,
+    and the SAME body/provider/reasoning routing the production verifier call uses (closes both P1-1
+    self_host endpoint+auth and P1-2 openrouter provider-routing false-pass classes). Returns
+    ``{role: slug}`` of the slugs proven alive; raises GateError on the first dead slug (fail closed).
+
+    ``http_client`` is threaded into ``_real_chat_completion_alive`` so the offline smoke can drive the
+    real dead-slug -> GateError leaf with a faked 404 transport (no network). Any endpoint/config
+    resolution error (e.g. an unset self-host PG_<ROLE>_BASE_URL, an absent OPENROUTER_API_KEY) raised by
+    the production helpers is normalized to GateError — fail closed BEFORE spend."""
+    from scripts.dr_benchmark.run_gate_b import verifier_model_slugs
+
+    slugs = verifier_model_slugs()  # {mirror, sentinel, judge: slug} for the ACTIVE transport mode
+    alive: dict[str, str] = {}
+    for role, slug in slugs.items():
+        try:
+            ok = _real_chat_completion_alive(role, slug, http_client=http_client)
+        except GateError:
+            raise
+        except Exception as exc:  # any transport / 404 / NoEndpoint / config failure -> fail closed
+            raise GateError(
+                f"super-heavy preflight: verifier role {role!r} slug {slug!r} is NOT alive in its "
+                f"production call shape ({type(exc).__name__}: {exc}) — a dead/misrouted verifier "
+                f"route would silently degrade the 4-role gate. Aborting BEFORE spend."
+            )
+        if not ok:
+            raise GateError(
+                f"super-heavy preflight: verifier role {role!r} slug {slug!r} returned no well-formed "
+                f"completion envelope — the route is degraded. Aborting BEFORE spend."
+            )
+        alive[role] = slug
+    return alive
+
+
+def _default_credibility_judge_probe() -> str | None:
+    """Probe the credibility judge slug via its OWN production sync caller, but ONLY when the credibility
+    redesign is active in this run (matches production activation). Returns the probed slug, or None when
+    the redesign is OFF (the judge is not called -> nothing to probe). Raises GateError on a dead slug."""
+    if not credibility_redesign_active():
+        return None
+    from src.polaris_graph.authority.credibility_judge_caller import (
+        credibility_judge_model,
+        make_openrouter_credibility_caller,
+    )
+
+    slug = credibility_judge_model()
+    # max_tokens=1 keeps the probe ~free; the caller is the EXACT sync path _apply_judge uses.
+    caller = make_openrouter_credibility_caller(max_tokens=1)
+    try:
+        caller("ok")
+    except GateError:
+        raise
+    except Exception as exc:  # transport / 404 / cap breach -> fail closed
+        raise GateError(
+            f"super-heavy preflight: credibility judge slug {slug!r} is NOT alive in its production "
+            f"call shape ({type(exc).__name__}: {exc}) — the credibility pass is active "
+            f"({_CREDIBILITY_REDESIGN_FLAG}) but its judge route is dead. Aborting BEFORE spend."
+        )
+    return slug
+
+
+async def _default_storm_probe() -> int:
+    """REAL, minimal STORM persona-discovery call — returns the persona count. >0 proves STORM's
+    discovery generate_structured path is alive and produces non-empty output (the path the drb_72
+    collapse silently killed). Uses the EXACT production constructor (PG_GENERATOR_MODEL client +
+    _discover_perspectives), capped to 2 personas to stay cheap."""
+    from src.polaris_graph.agents.storm_interviews import _discover_perspectives
+    from src.polaris_graph.llm.openrouter_client import PG_GENERATOR_MODEL, OpenRouterClient
+
+    client = OpenRouterClient(model=PG_GENERATOR_MODEL)
+    try:
+        personas = await _discover_perspectives(
+            client,
+            query="metformin efficacy in type 2 diabetes",
+            existing_context="(preflight probe)",
+            target_count=2,
+        )
+        return len(personas or [])
+    finally:
+        await client.close()
+
+
+async def _default_chromium_probe() -> None:
+    """Reuse the FX-16 host-local fail-closed chromium probe (pg_preflight). FAIL -> GateError. A SKIP
+    (DRY mode, or intentionally-disabled cascade) is treated per its reason: an intentionally-disabled
+    cascade SKIP passes (the run won't browser-fetch); a DRY 'would FAIL in LIVE' SKIP is escalated to a
+    GateError here because the super-heavy preflight is a PAID-RUN gate (fail closed on the run host).
+
+    ASYNC + AWAITED (NOT asyncio.run): super_heavy_preflight is awaited from run_gate_b_query's ALREADY-
+    RUNNING event loop, so asyncio.run() here would raise 'cannot be called from a running event loop'
+    and crash every live run (the SAME trap the canary's _default_structured_output_probe documents).
+    The FX-16 pf.test_chromium_browser_available is itself a coroutine; await it directly."""
+    import scripts.pg_preflight as pf
+
+    result = await pf.test_chromium_browser_available()
+    if result.status == pf.PASS:
+        return
+    if result.status == pf.FAIL:
+        raise GateError(
+            f"super-heavy preflight: chromium browser-fetch tier is DEAD on this host — {result.message}"
+        )
+    # SKIP: the cascade is intentionally off (passes) vs a DRY 'would FAIL in LIVE/paid' remediation
+    # SKIP (escalate — a paid run must not proceed with a dead browser tier on the run host).
+    if "intentionally off" in result.message:
+        return
+    raise GateError(
+        f"super-heavy preflight: chromium probe SKIPped with a would-fail remediation — a paid run "
+        f"must not proceed with a dead browser-fetch tier on the run host. {result.message}"
+    )
+
+
+def _default_false_alarm_asserts() -> list[str]:
+    """RUNTIME re-assertion of the 5 recurring false-alarm regression checks. Imports the SHARED check
+    logic from ``scripts.dr_benchmark.false_alarm_checks`` (a NON-test module) — NOT ``tests/`` — so the
+    paid VM run never depends on ``tests/`` being importable. The pytest locks
+    (tests/preflight/test_false_alarm_regressions.py) wrap the SAME five functions, so CI and this
+    runtime gate assert identical conditions. An AssertionError (false alarm resurfaced) or an
+    ImportError (logic moved) is normalized to GateError (fail closed). Returns the names that passed."""
+    try:
+        from scripts.dr_benchmark.false_alarm_checks import ALL_CHECKS
+    except Exception as exc:  # the shared check logic could not even be imported -> fail closed
+        raise GateError(
+            f"super-heavy preflight: the false-alarm regression checks could not be imported "
+            f"({type(exc).__name__}: {exc}) — the 5 durable kills cannot be re-asserted. Fail closed."
+        )
+
+    passed: list[str] = []
+    for check in ALL_CHECKS:
+        try:
+            check()
+        except AssertionError as exc:  # a false alarm resurfaced -> fail closed
+            raise GateError(
+                f"super-heavy preflight: false-alarm regression lock {check.__name__} FAILED at run "
+                f"time — a recurring false alarm has silently resurfaced ({exc})."
+            )
+        except Exception as exc:  # any other failure (missing file / import) is also fail-closed
+            raise GateError(
+                f"super-heavy preflight: false-alarm regression lock {check.__name__} could not run "
+                f"({type(exc).__name__}: {exc}) — fail closed BEFORE spend."
+            )
+        passed.append(check.__name__)
+    return passed
+
+
+async def super_heavy_preflight(
+    *,
+    canary: Callable[[], Awaitable[None]] = behavioral_canary,
+    generator_slug_probe: Callable[[], Awaitable[bool]] = _default_generator_slug_probe,
+    verifier_slug_probe: Callable[[], Mapping[str, str]] = _default_verifier_slug_probe,
+    credibility_judge_probe: Callable[[], str | None] = _default_credibility_judge_probe,
+    storm_probe: Callable[[], Awaitable[int]] = _default_storm_probe,
+    chromium_probe: Callable[[], Awaitable[None]] = _default_chromium_probe,
+    false_alarm_asserts: Callable[[], list[str]] = _default_false_alarm_asserts,
+) -> dict:
+    """The SUPER-HEAVY behavioral pre-spend preflight (I-cred-013 #1163). FAIL CLOSED (GateError) unless
+    EVERY behavioral check passes. Prints SUPER_HEAVY_PREFLIGHT_OK + a per-check summary on success.
+
+    COMPOSES the unchanged ``behavioral_canary`` (its signature is NOT touched, so its committed offline
+    tests keep injecting only their two probes) with the new injectable heavy probes. EVERY probe is a
+    callable kwarg with a real default, so the OFFLINE smoke injects fakes (dead -> GateError) with no
+    network. Returns a machine-readable summary on success.
+
+    Order (cheapest deterministic checks first, so an offline regression fails before any live probe):
+      1. false-alarm regression locks (offline, deterministic) — a resurfaced false alarm fails first.
+      2. chromium host-local probe (offline file check) — a dead browser tier fails before any LLM spend.
+      3. behavioral canary (structured-output + 1-query live search) — the existing pre-spend gate.
+      4. generator slug alive (generate_structured on PG_GENERATOR_MODEL).
+      5. every verifier slug alive in its production call shape (mode-aware resolution).
+      6. credibility judge slug alive (only when the redesign is active this run).
+      7. STORM/discovery non-empty (a real minimal persona-discovery call returns >0).
+    """
+    summary: dict = {}
+
+    # 1. false-alarm regression locks (deterministic, offline) ------------------------------------
+    try:
+        summary["false_alarm_locks_passed"] = false_alarm_asserts()
+    except GateError:
+        raise
+    except Exception as exc:  # any non-GateError (e.g. an injected callable) -> fail-closed contract
+        raise GateError(
+            f"super-heavy preflight: false-alarm regression locks could not run "
+            f"({type(exc).__name__}: {exc}) — fail closed BEFORE spend."
+        )
+
+    # 2. chromium host-local fail-closed probe (offline file check) -------------------------------
+    try:
+        await chromium_probe()
+    except GateError:
+        raise
+    except Exception as exc:  # non-GateError -> fail-closed contract
+        raise GateError(
+            f"super-heavy preflight: chromium probe failed ({type(exc).__name__}: {exc}) — fail closed "
+            f"BEFORE spend."
+        )
+    summary["chromium"] = "present_or_intentionally_off"
+
+    # 3. behavioral canary (delegated, unchanged) -------------------------------------------------
+    await canary()
+    summary["behavioral_canary"] = "ok"
+
+    # 4. generator slug alive in production call shape --------------------------------------------
+    try:
+        gen_ok = await generator_slug_probe()
+    except GateError:
+        raise
+    except Exception as exc:
+        raise GateError(
+            f"super-heavy preflight: generator slug probe failed ({type(exc).__name__}: {exc}) — fail "
+            f"closed BEFORE spend."
+        )
+    if not gen_ok:
+        raise GateError(
+            "super-heavy preflight: generator slug returned no parsed structured object — the "
+            "generator's structured-output path is degraded. Aborting BEFORE spend."
+        )
+    summary["generator_slug"] = "alive"
+
+    # 5. every verifier slug alive in production call shape ---------------------------------------
+    try:
+        alive_verifiers = verifier_slug_probe()
+    except GateError:
+        raise
+    except Exception as exc:
+        raise GateError(
+            f"super-heavy preflight: verifier slug probe failed ({type(exc).__name__}: {exc}) — fail "
+            f"closed BEFORE spend."
+        )
+    if not alive_verifiers:
+        raise GateError(
+            "super-heavy preflight: verifier slug probe returned no alive roles — the 4-role verifier "
+            "stack is unreachable. Aborting BEFORE spend."
+        )
+    summary["verifier_slugs_alive"] = dict(alive_verifiers)
+
+    # 6. credibility judge slug alive (only when active this run) ---------------------------------
+    try:
+        cred_slug = credibility_judge_probe()
+    except GateError:
+        raise
+    except Exception as exc:
+        raise GateError(
+            f"super-heavy preflight: credibility judge probe failed ({type(exc).__name__}: {exc}) — "
+            f"fail closed BEFORE spend."
+        )
+    summary["credibility_judge"] = cred_slug if cred_slug is not None else "inactive_this_run"
+
+    # 7. STORM / discovery non-empty --------------------------------------------------------------
+    try:
+        n_personas = await storm_probe()
+    except GateError:
+        raise
+    except Exception as exc:
+        raise GateError(
+            f"super-heavy preflight: STORM discovery probe failed ({type(exc).__name__}: {exc}) — fail "
+            f"closed BEFORE spend."
+        )
+    if n_personas <= 0:
+        raise GateError(
+            "super-heavy preflight: STORM persona-discovery returned 0 personas — discovery is degraded "
+            "(the drb_72 silent-collapse class). Aborting BEFORE spend."
+        )
+    summary["storm_personas"] = n_personas
+
+    print("SUPER_HEAVY_PREFLIGHT_OK", flush=True)
+    return summary
diff --git a/tests/dr_benchmark/test_super_heavy_preflight_icred013.py b/tests/dr_benchmark/test_super_heavy_preflight_icred013.py
new file mode 100644
index 00000000..87c703c5
--- /dev/null
+++ b/tests/dr_benchmark/test_super_heavy_preflight_icred013.py
@@ -0,0 +1,633 @@
+"""Offline smoke for I-cred-013 (#1163): the SUPER-HEAVY behavioral pre-spend preflight.
+
+NO network, NO spend: every live probe (canary, generator-slug, verifier-slug, credibility-judge,
+STORM, chromium) and the false-alarm runtime asserts are DEPENDENCY-INJECTED, so the fail-closed
+logic is exercised with faked alive/dead results. Each new probe's dead path is asserted to raise
+GateError INDIVIDUALLY, and a fully-green path returns the machine-readable summary.
+
+Hermetic env (mirrors tests/dr_benchmark/test_behavioral_canary_canary01_iready017.py conventions).
+"""
+from __future__ import annotations
+
+import asyncio
+import os
+
+import pytest
+
+from scripts.dr_benchmark.pathB_run_gate import GateError
+from scripts.dr_benchmark.super_heavy_preflight import (
+    _CREDIBILITY_REDESIGN_FLAG,
+    credibility_redesign_active,
+    super_heavy_preflight,
+)
+
+
+@pytest.fixture(autouse=True)
+def _isolate_env():
+    snap = dict(os.environ)
+    try:
+        yield
+    finally:
+        os.environ.clear()
+        os.environ.update(snap)
+
+
+# --------------------------------------------------------------------------- all-green fakes
+async def _canary_ok() -> None:
+    return None
+
+
+async def _gen_ok() -> bool:
+    return True
+
+
+def _verifiers_ok() -> dict[str, str]:
+    return {"mirror": "z-ai/glm-5.1", "sentinel": "minimax/minimax-m2", "judge": "qwen/qwen3.6-35b-a3b"}
+
+
+def _cred_inactive() -> None:
+    return None
+
+
+def _cred_alive() -> str:
+    return "z-ai/glm-5.1"
+
+
+async def _storm_ok() -> int:
+    return 2
+
+
+async def _chromium_ok() -> None:
+    return None
+
+
+def _false_alarms_ok() -> list[str]:
+    return ["fa1", "fa2", "fa3", "fa4", "fa5"]
+
+
+def _all_green_kwargs(**overrides):
+    base = dict(
+        canary=_canary_ok,
+        generator_slug_probe=_gen_ok,
+        verifier_slug_probe=_verifiers_ok,
+        credibility_judge_probe=_cred_inactive,
+        storm_probe=_storm_ok,
+        chromium_probe=_chromium_ok,
+        false_alarm_asserts=_false_alarms_ok,
+    )
+    base.update(overrides)
+    return base
+
+
+# --------------------------------------------------------------------------- green path
+def test_super_heavy_preflight_all_green_returns_summary(capsys):
+    summary = asyncio.run(super_heavy_preflight(**_all_green_kwargs()))
+    assert "SUPER_HEAVY_PREFLIGHT_OK" in capsys.readouterr().out
+    assert summary["false_alarm_locks_passed"] == ["fa1", "fa2", "fa3", "fa4", "fa5"]
+    assert summary["chromium"] == "present_or_intentionally_off"
+    assert summary["behavioral_canary"] == "ok"
+    assert summary["generator_slug"] == "alive"
+    assert summary["verifier_slugs_alive"]["sentinel"] == "minimax/minimax-m2"
+    assert summary["credibility_judge"] == "inactive_this_run"
+    assert summary["storm_personas"] == 2
+
+
+def test_super_heavy_preflight_reports_active_credibility_slug():
+    summary = asyncio.run(super_heavy_preflight(**_all_green_kwargs(credibility_judge_probe=_cred_alive)))
+    assert summary["credibility_judge"] == "z-ai/glm-5.1"
+
+
+# --------------------------------------------------------------------------- each dead path -> GateError
+def test_fails_closed_when_a_false_alarm_regresses():
+    def _fa_regressed() -> list[str]:
+        raise GateError("false-alarm regression lock test_fa1 FAILED at run time")
+
+    with pytest.raises(GateError, match="false-alarm"):
+        asyncio.run(super_heavy_preflight(**_all_green_kwargs(false_alarm_asserts=_fa_regressed)))
+
+
+def test_fails_closed_when_chromium_dead():
+    async def _chromium_dead() -> None:
+        raise GateError("chromium browser-fetch tier is DEAD on this host")
+
+    with pytest.raises(GateError, match="chromium"):
+        asyncio.run(super_heavy_preflight(**_all_green_kwargs(chromium_probe=_chromium_dead)))
+
+
+def test_fails_closed_when_canary_fails():
+    async def _canary_dead() -> None:
+        raise GateError("behavioral canary: 1-query primary-backend search returned 0 live sources")
+
+    with pytest.raises(GateError, match="canary"):
+        asyncio.run(super_heavy_preflight(**_all_green_kwargs(canary=_canary_dead)))
+
+
+def test_fails_closed_when_generator_slug_dead():
+    async def _gen_dead() -> bool:
+        return False
+
+    with pytest.raises(GateError, match="generator slug"):
+        asyncio.run(super_heavy_preflight(**_all_green_kwargs(generator_slug_probe=_gen_dead)))
+
+
+def test_fails_closed_when_generator_probe_raises_404():
+    async def _gen_404() -> bool:
+        raise GateError("structured-output probe got NoEndpointError")
+
+    with pytest.raises(GateError, match="NoEndpointError"):
+        asyncio.run(super_heavy_preflight(**_all_green_kwargs(generator_slug_probe=_gen_404)))
+
+
+def test_normalizes_arbitrary_generator_failure_to_gateerror():
+    async def _gen_boom() -> bool:
+        raise RuntimeError("network exploded")
+
+    with pytest.raises(GateError, match="fail closed"):
+        asyncio.run(super_heavy_preflight(**_all_green_kwargs(generator_slug_probe=_gen_boom)))
+
+
+def test_fails_closed_when_a_verifier_slug_dead():
+    def _verifier_dead() -> dict[str, str]:
+        raise GateError("verifier role 'sentinel' slug 'minimax/minimax-m2' is NOT alive")
+
+    with pytest.raises(GateError, match="sentinel"):
+        asyncio.run(super_heavy_preflight(**_all_green_kwargs(verifier_slug_probe=_verifier_dead)))
+
+
+def test_fails_closed_when_no_verifiers_alive():
+    def _verifiers_empty() -> dict[str, str]:
+        return {}
+
+    with pytest.raises(GateError, match="no alive roles"):
+        asyncio.run(super_heavy_preflight(**_all_green_kwargs(verifier_slug_probe=_verifiers_empty)))
+
+
+def test_fails_closed_when_credibility_judge_dead():
+    def _cred_dead() -> str:
+        raise GateError("credibility judge slug 'z-ai/glm-5.1' is NOT alive in its production call shape")
+
+    with pytest.raises(GateError, match="credibility judge"):
+        asyncio.run(super_heavy_preflight(**_all_green_kwargs(credibility_judge_probe=_cred_dead)))
+
+
+def test_fails_closed_when_storm_empty():
+    async def _storm_empty() -> int:
+        return 0
+
+    with pytest.raises(GateError, match="0 personas"):
+        asyncio.run(super_heavy_preflight(**_all_green_kwargs(storm_probe=_storm_empty)))
+
+
+def test_normalizes_arbitrary_storm_failure_to_gateerror():
+    async def _storm_boom() -> int:
+        raise RuntimeError("storm exploded")
+
+    with pytest.raises(GateError, match="fail closed"):
+        asyncio.run(super_heavy_preflight(**_all_green_kwargs(storm_probe=_storm_boom)))
+
+
+# --------------------------------------------------------------------------- credibility-activation read
+def test_credibility_redesign_active_matches_runner_off_tokens():
+    for off in ("", "0", "false", "off", "no", "FALSE", " Off "):
+        os.environ[_CREDIBILITY_REDESIGN_FLAG] = off
+        assert credibility_redesign_active() is False, f"{off!r} must read as OFF (matches the runner)"
+    for on in ("1", "true", "on", "yes", "redesign"):
+        os.environ[_CREDIBILITY_REDESIGN_FLAG] = on
+        assert credibility_redesign_active() is True, f"{on!r} must read as ON (matches the runner)"
+
+
+def test_credibility_redesign_active_default_off():
+    os.environ.pop(_CREDIBILITY_REDESIGN_FLAG, None)
+    assert credibility_redesign_active() is False
+
+
+# --------------------------------------------------------------------------- real default probes wired
+def test_default_chromium_probe_reuses_fx16_and_fails_closed(monkeypatch):
+    """The real chromium default reuses pg_preflight's FX-16 probe and maps FAIL -> GateError (no
+    network, no real browser — the FX-16 result is monkeypatched)."""
+    import scripts.dr_benchmark.super_heavy_preflight as m
+    import scripts.pg_preflight as pf
+
+    async def _fake_fail():
+        return pf.TestResult("chromium_browser_available", pf.FAIL, "playwright install chromium ...")
+
+    monkeypatch.setattr(pf, "test_chromium_browser_available", _fake_fail)
+    with pytest.raises(GateError, match="chromium"):
+        asyncio.run(m._default_chromium_probe())
+
+
+def test_default_chromium_probe_passes_when_present(monkeypatch):
+    import scripts.dr_benchmark.super_heavy_preflight as m
+    import scripts.pg_preflight as pf
+
+    async def _fake_pass():
+        return pf.TestResult("chromium_browser_available", pf.PASS, "chromium present: /x/chrome")
+
+    monkeypatch.setattr(pf, "test_chromium_browser_available", _fake_pass)
+    assert asyncio.run(m._default_chromium_probe()) is None  # no raise
+
+
+def test_default_chromium_probe_skip_intentionally_off_passes(monkeypatch):
+    import scripts.dr_benchmark.super_heavy_preflight as m
+    import scripts.pg_preflight as pf
+
+    async def _fake_skip_off():
+        return pf.TestResult(
+            "chromium_browser_available", pf.SKIP, "PG_DISABLE_ACCESS_BYPASS=1 -- intentionally off"
+        )
+
+    monkeypatch.setattr(pf, "test_chromium_browser_available", _fake_skip_off)
+    assert asyncio.run(m._default_chromium_probe()) is None  # intentionally-off SKIP passes
+
+
+def test_default_chromium_probe_skip_would_fail_escalates(monkeypatch):
+    """A DRY 'would FAIL in LIVE/paid' SKIP must ESCALATE to GateError — the super-heavy preflight is a
+    paid-run gate, so a dead browser tier on the run host must fail closed."""
+    import scripts.dr_benchmark.super_heavy_preflight as m
+    import scripts.pg_preflight as pf
+
+    async def _fake_skip_would_fail():
+        return pf.TestResult(
+            "chromium_browser_available", pf.SKIP, "[would FAIL in LIVE/paid mode] chromium absent"
+        )
+
+    monkeypatch.setattr(pf, "test_chromium_browser_available", _fake_skip_would_fail)
+    with pytest.raises(GateError, match="would-fail remediation"):
+        asyncio.run(m._default_chromium_probe())
+
+
+def test_default_credibility_probe_noop_when_redesign_off():
+    """When the redesign is OFF, the real default probe returns None WITHOUT importing/calling the live
+    caller (no network) — probe-alive matches production activation."""
+    import scripts.dr_benchmark.super_heavy_preflight as m
+
+    os.environ.pop(_CREDIBILITY_REDESIGN_FLAG, None)
+    assert m._default_credibility_judge_probe() is None
+
+
+# --------------------------------------------------------------------------- slate wiring
+def test_super_heavy_preflight_is_in_slate_force_on_and_required():
+    """The super-heavy preflight must be force-on + required in the benchmark slate, so a paid run can
+    NEVER silently drop back to the lighter canary alone."""
+    from scripts.dr_benchmark.run_gate_b import (
+        _BENCHMARK_FORCE_ON_FLAGS,
+        _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS,
+        _FULL_CAPABILITY_BENCHMARK_SLATE,
+    )
+
+    flag = "PG_SUPER_HEAVY_PREFLIGHT"
+    assert _FULL_CAPABILITY_BENCHMARK_SLATE.get(flag) == "1"
+    assert flag in _BENCHMARK_FORCE_ON_FLAGS
+    assert flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS
+
+
+def test_super_heavy_preflight_force_on_over_preset_zero():
+    from scripts.dr_benchmark.run_gate_b import apply_full_capability_benchmark_slate
+
+    os.environ["PG_SUPER_HEAVY_PREFLIGHT"] = "0"
+    apply_full_capability_benchmark_slate()
+    assert os.environ.get("PG_SUPER_HEAVY_PREFLIGHT") == "1", "force-on did not override preset 0"
+
+
+def test_preflight_fails_closed_when_super_heavy_off():
+    from scripts.dr_benchmark.run_gate_b import (
+        _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS,
+        apply_full_capability_benchmark_slate,
+        preflight_full_capability,
+    )
+
+    apply_full_capability_benchmark_slate()
+    for flag in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS:
+        os.environ[flag] = "1"
+    os.environ["PG_STRICT_VERIFY_ENTAILMENT"] = "enforce"
+    os.environ["PG_SUPER_HEAVY_PREFLIGHT"] = "0"
+    with pytest.raises(RuntimeError) as exc:
+        preflight_full_capability()
+    assert "PG_SUPER_HEAVY_PREFLIGHT" in str(exc.value)
+
+
+def test_default_false_alarm_asserts_runs_the_committed_checks():
+    """The real default imports + runs the 5 SHARED false-alarm checks from the NON-test module (offline,
+    deterministic). They pass on a clean tree, proving the runtime re-assertion is wired to the SAME
+    checks CI enforces — and WITHOUT importing tests/ on the paid VM."""
+    import scripts.dr_benchmark.super_heavy_preflight as m
+
+    passed = m._default_false_alarm_asserts()
+    assert passed == [
+        "check_fa1_crlf_gitattributes_rule_committed",
+        "check_fa2_competitor_outputs_present",
+        "check_fa3_run_health_fail_loud_guard_present",
+        "check_fa4_empty_response_failover_present",
+        "check_fa5_journal_only_gated_by_source_restriction",
+    ]
+
+
+def test_false_alarm_runtime_assert_does_not_import_tests_module():
+    """The production runtime assert must NOT depend on the tests/ package (paid-VM launch shape). The
+    shared check logic lives in a NON-test module; importing it must NOT require tests.preflight."""
+    import scripts.dr_benchmark.false_alarm_checks as fac
+
+    assert hasattr(fac, "ALL_CHECKS") and len(fac.ALL_CHECKS) == 5
+    assert "tests" not in fac.__name__
+
+
+# --------------------------------------------------------------------------- live-loop regression
+def test_real_chromium_default_runs_inside_running_event_loop(monkeypatch):
+    """REGRESSION: super_heavy_preflight is awaited from run_gate_b_query's ALREADY-RUNNING event loop.
+    The real _default_chromium_probe must NOT call asyncio.run (that raises 'cannot be called from a
+    running event loop' and crashes every live run). Drive the REAL chromium default (FX-16 faked to
+    PASS — no real browser) through an awaited super_heavy_preflight, all network probes faked, and
+    assert it does NOT raise RuntimeError and reaches SUPER_HEAVY_PREFLIGHT_OK."""
+    import scripts.pg_preflight as pf
+    import scripts.dr_benchmark.super_heavy_preflight as m
+
+    async def _fake_pass():
+        return pf.TestResult("chromium_browser_available", pf.PASS, "chromium present: /x/chrome")
+
+    monkeypatch.setattr(pf, "test_chromium_browser_available", _fake_pass)
+
+    async def _drive():
+        # NOTE: chromium_probe is NOT injected here — the REAL m._default_chromium_probe runs, awaited
+        # from this running loop (the production shape). Only the FX-16 leaf is faked.
+        return await super_heavy_preflight(
+            **{k: v for k, v in _all_green_kwargs().items() if k != "chromium_probe"}
+        )
+
+    summary = asyncio.run(_drive())  # must NOT raise RuntimeError('running event loop')
+    assert summary["chromium"] == "present_or_intentionally_off"
+
+
+# --------------------------------------------------------------------------- REAL dead-slug -> GateError
+# This is the test that proves the drb_72 fix: the _real_chat_completion_alive leaf maps a 404 (dead
+# route / NoEndpoint) to GateError, driven through _default_verifier_slug_probe with a faked httpx
+# transport — NO network, NO spend.
+def _mock_404_client():
+    import httpx
+
+    def _handler(request):
+        return httpx.Response(404, json={"error": {"message": "No endpoints found", "code": 404}})
+
+    return httpx.Client(transport=httpx.MockTransport(_handler))
+
+
+def _mock_200_client():
+    import httpx
+
+    def _handler(request):
+        return httpx.Response(
+            200, json={"choices": [{"message": {"content": "ok"}}], "model": "probe"}
+        )
+
+    return httpx.Client(transport=httpx.MockTransport(_handler))
+
+
+def test_real_verifier_probe_maps_404_to_gateerror(monkeypatch):
+    """A dead verifier slug (404 from the route) must FAIL CLOSED with a GateError naming the role+slug —
+    the drb_72 silent-dead-route class. Driven through the REAL _real_chat_completion_alive leaf with a
+    faked 404 transport (no network)."""
+    import scripts.dr_benchmark.super_heavy_preflight as m
+    import scripts.dr_benchmark.run_gate_b as rgb
+
+    monkeypatch.setattr(rgb, "four_role_transport_mode", lambda: "openrouter")
+    monkeypatch.setattr(rgb, "verifier_model_slugs", lambda: {"mirror": "z-ai/glm-5.1"})
+    os.environ["OPENROUTER_API_KEY"] = "test-key"
+
+    client = _mock_404_client()
+    try:
+        with pytest.raises(GateError, match=r"mirror.*z-ai/glm-5.1|z-ai/glm-5.1.*mirror|NOT alive"):
+            m._default_verifier_slug_probe(http_client=client)
+    finally:
+        client.close()
+
+
+def test_real_verifier_probe_passes_on_200_envelope(monkeypatch):
+    """A live slug returning a well-formed 200 choices envelope passes (returns the {role: slug} map),
+    via the REAL leaf with a faked 200 transport (no network)."""
+    import scripts.dr_benchmark.super_heavy_preflight as m
+    import scripts.dr_benchmark.run_gate_b as rgb
+
+    monkeypatch.setattr(rgb, "four_role_transport_mode", lambda: "openrouter")
+    monkeypatch.setattr(
+        rgb,
+        "verifier_model_slugs",
+        lambda: {"mirror": "z-ai/glm-5.1", "sentinel": "minimax/minimax-m2", "judge": "qwen/qwen3.6-35b-a3b"},
+    )
+    os.environ["OPENROUTER_API_KEY"] = "test-key"
+
+    client = _mock_200_client()
+    try:
+        alive = m._default_verifier_slug_probe(http_client=client)
+    finally:
+        client.close()
+    assert alive == {
+        "mirror": "z-ai/glm-5.1",
+        "sentinel": "minimax/minimax-m2",
+        "judge": "qwen/qwen3.6-35b-a3b",
+    }
+
+
+# --------------------------------------------------------------------------- P1: probe MATCHES production
+# These tests prove the I-cred-013 diff-gate P1 fix: the verifier-slug probe REUSES the production
+# transports' OWN request construction, so it hits the SAME endpoint path, SAME auth presence/absence,
+# and SAME body/provider/reasoning routing the production verifier call uses. The actual outgoing
+# request is CAPTURED via a MockTransport handler (no network) and compared field-by-field against the
+# production transport's request — NOT a blanket dict-equal (the probe legitimately clamps the token
+# magnitudes), but field-scoped: endpoint, auth, model, provider, reasoning shape.
+def _capturing_200_client(captured: dict):
+    import httpx
+
+    def _handler(request):
+        captured["url"] = str(request.url)
+        captured["headers"] = dict(request.headers)
+        import json as _json
+
+        captured["body"] = _json.loads(request.content.decode("utf-8"))
+        return httpx.Response(200, json={"choices": [{"message": {"content": "ok"}}], "model": "probe"})
+
+    return httpx.Client(transport=httpx.MockTransport(_handler))
+
+
+def _production_openrouter_request(role: str, slug: str) -> tuple[str, dict, dict]:
+    """Build the EXACT production OpenRouter verifier request (endpoint, headers, body) for `role` —
+    the ground truth the probe must mirror on endpoint/auth/model/provider/reasoning."""
+    from src.polaris_graph.roles.openai_compatible_transport import _normalize_messages
+    from src.polaris_graph.roles.openrouter_role_transport import (
+        _CHAT_COMPLETIONS_PATH,
+        _build_openrouter_body,
+        openrouter_role_endpoint,
+    )
+    from src.polaris_graph.roles.role_transport import RoleRequest
+
+    base_url, api_key, model_slug = openrouter_role_endpoint(role)
+    req = RoleRequest(role=role, model_slug=slug, prompt="ok", params={})
+    body = _build_openrouter_body(req, model_slug, _normalize_messages(req))
+    endpoint = f"{base_url}{_CHAT_COMPLETIONS_PATH}"
+    headers = {
+        "Authorization": f"Bearer {api_key}",
+        "Content-Type": "application/json",
+        "HTTP-Referer": "https://polaris-research.ai",
+        "X-Title": "polaris graph",
+    }
+    return endpoint, headers, body
+
+
+@pytest.mark.parametrize("role", ["mirror", "sentinel", "judge"])
+def test_openrouter_probe_request_matches_production(monkeypatch, role):
+    """OpenRouter mode (P1-2): the probe's CAPTURED outgoing request must match the production verifier
+    request on endpoint path, Authorization, model, AND the provider + reasoning ROUTING keys (the
+    `require_parameters`-filtered keys whose absence was the P1-2 false-pass). Only the token MAGNITUDES
+    differ (the probe clamps them cheap)."""
+    import scripts.dr_benchmark.super_heavy_preflight as m
+    import scripts.dr_benchmark.run_gate_b as rgb
+
+    slugs = {"mirror": "z-ai/glm-5.1", "sentinel": "minimax/minimax-m2", "judge": "qwen/qwen3.6-35b-a3b"}
+    slug = slugs[role]
+    monkeypatch.setattr(rgb, "four_role_transport_mode", lambda: "openrouter")
+    os.environ["OPENROUTER_API_KEY"] = "test-key"
+
+    prod_endpoint, prod_headers, prod_body = _production_openrouter_request(role, slug)
+
+    captured: dict = {}
+    client = _capturing_200_client(captured)
+    try:
+        ok = m._real_chat_completion_alive(role, slug, http_client=client)
+    finally:
+        client.close()
+    assert ok is True
+
+    # endpoint path identical to production
+    assert captured["url"] == prod_endpoint
+    # Authorization present + identical (OpenRouter ALWAYS requires the key)
+    assert captured["headers"].get("authorization") == prod_headers["Authorization"]
+    assert "polaris-research.ai" in captured["headers"].get("http-referer", "")
+    # model + temperature + provider routing + reasoning SHAPE identical to production
+    body = captured["body"]
+    assert body["model"] == prod_body["model"] == slug
+    assert body["temperature"] == prod_body["temperature"]
+    assert body["provider"] == prod_body["provider"], "provider routing must match production EXACTLY"
+    # reasoning shape: same KEYS as production (Mirror numeric cap / Judge+Sentinel effort), magnitude
+    # of a numeric reasoning cap clamped but still STRICTLY below top-level max_tokens (production rule).
+    assert set(body.get("reasoning", {}).keys()) == set(prod_body.get("reasoning", {}).keys())
+    if "effort" in prod_body.get("reasoning", {}):
+        assert body["reasoning"]["effort"] == prod_body["reasoning"]["effort"]
+    if "max_tokens" in body.get("reasoning", {}):
+        assert body["max_tokens"] > body["reasoning"]["max_tokens"], "top max_tokens must exceed cap"
+    # token budgets are CLAMPED cheap (not the production 16k/24k) — proves ~free without changing shape
+    assert body["max_tokens"] < prod_body["max_tokens"]
+
+
+@pytest.mark.parametrize(
+    "role,base_env,key_env",
+    [
+        ("mirror", "PG_MIRROR_BASE_URL", "PG_MIRROR_API_KEY"),
+        ("sentinel", "PG_SENTINEL_BASE_URL", "PG_SENTINEL_API_KEY"),
+        ("judge", "PG_JUDGE_BASE_URL", "PG_JUDGE_API_KEY"),
+    ],
+)
+def test_self_host_probe_request_matches_production_keyed(monkeypatch, role, base_env, key_env):
+    """self_host mode (P1-1) with a per-role key SET: the probe must POST to the `/v1/chat/completions`
+    path (NOT the `/chat/completions` the old probe hardcoded) and send `Authorization: Bearer <key>` —
+    EXACTLY as OpenAICompatibleRoleTransport.complete does."""
+    import scripts.dr_benchmark.super_heavy_preflight as m
+    import scripts.dr_benchmark.run_gate_b as rgb
+
+    monkeypatch.setattr(rgb, "four_role_transport_mode", lambda: "self_host")
+    os.environ[base_env] = "http://10.0.0.9:8000"
+    os.environ[key_env] = "sk-self-host"
+
+    captured: dict = {}
+    client = _capturing_200_client(captured)
+    try:
+        ok = m._real_chat_completion_alive(role, "whatever/slug", http_client=client)
+    finally:
+        client.close()
+    assert ok is True
+    # P1-1: production self-host path appends /v1/chat/completions (the constant), NOT /chat/completions
+    assert captured["url"] == "http://10.0.0.9:8000/v1/chat/completions"
+    assert captured["headers"].get("authorization") == "Bearer sk-self-host"
+    # self-host vLLM bodies carry NO OpenRouter provider/reasoning routing
+    assert "provider" not in captured["body"]
+    assert "reasoning" not in captured["body"]
+
+
+@pytest.mark.parametrize(
+    "role,base_env,key_env",
+    [
+        ("mirror", "PG_MIRROR_BASE_URL", "PG_MIRROR_API_KEY"),
+        ("sentinel", "PG_SENTINEL_BASE_URL", "PG_SENTINEL_API_KEY"),
+    ],
+)
+def test_self_host_probe_omits_auth_when_keyless(monkeypatch, role, base_env, key_env):
+    """self_host mode (P1-1, THE false-fail the old probe caused): a KEYLESS self-host vLLM (no
+    PG_<ROLE>_API_KEY) is VALID — production omits the Authorization header entirely (never an empty
+    `Bearer `). The old probe ALWAYS sent `Bearer <empty>`, false-FAILing a valid keyless deployment.
+    The captured probe request must carry NO Authorization header."""
+    import scripts.dr_benchmark.super_heavy_preflight as m
+    import scripts.dr_benchmark.run_gate_b as rgb
+
+    monkeypatch.setattr(rgb, "four_role_transport_mode", lambda: "self_host")
+    os.environ[base_env] = "http://10.0.0.9:8000"
+    os.environ.pop(key_env, None)  # KEYLESS — the valid vLLM-without-api-key deployment
+
+    captured: dict = {}
+    client = _capturing_200_client(captured)
+    try:
+        ok = m._real_chat_completion_alive(role, "whatever/slug", http_client=client)
+    finally:
+        client.close()
+    assert ok is True
+    assert captured["url"] == "http://10.0.0.9:8000/v1/chat/completions"
+    # THE fix: no Authorization header at all (not an empty `Bearer `)
+    assert "authorization" not in captured["headers"]
+
+
+def test_self_host_probe_fails_closed_on_unset_base_url(monkeypatch):
+    """self_host mode: an UNSET PG_<ROLE>_BASE_URL is a deployment error — role_endpoint raises, and the
+    probe normalizes it to a fail-closed GateError BEFORE spend (never a silent default endpoint)."""
+    import scripts.dr_benchmark.super_heavy_preflight as m
+    import scripts.dr_benchmark.run_gate_b as rgb
+
+    monkeypatch.setattr(rgb, "four_role_transport_mode", lambda: "self_host")
+    monkeypatch.setattr(rgb, "verifier_model_slugs", lambda: {"mirror": "cohere/command-a-plus"})
+    os.environ.pop("PG_MIRROR_BASE_URL", None)  # unset -> role_endpoint raises ValueError
+
+    with pytest.raises(GateError, match=r"mirror.*NOT alive|BASE_URL|not set"):
+        m._default_verifier_slug_probe(http_client=_mock_200_client())
+
+
+def test_self_host_404_fails_closed(monkeypatch):
+    """self_host mode: a dead self-host slug (404) still fails closed with a GateError (the same
+    fail-closed contract as the openrouter route), via the production /v1/chat/completions call shape."""
+    import scripts.dr_benchmark.super_heavy_preflight as m
+    import scripts.dr_benchmark.run_gate_b as rgb
+
+    monkeypatch.setattr(rgb, "four_role_transport_mode", lambda: "self_host")
+    monkeypatch.setattr(rgb, "verifier_model_slugs", lambda: {"mirror": "cohere/command-a-plus"})
+    os.environ["PG_MIRROR_BASE_URL"] = "http://10.0.0.9:8000"
+    os.environ.pop("PG_MIRROR_API_KEY", None)
+
+    client = _mock_404_client()
+    try:
+        with pytest.raises(GateError, match=r"mirror|NOT alive"):
+            m._default_verifier_slug_probe(http_client=client)
+    finally:
+        client.close()
+
+
+def test_probe_budget_clamp_preserves_invariant():
+    """Unit: _clamp_probe_budget shrinks token magnitudes but PRESERVES the production invariant
+    (top-level max_tokens > a numeric reasoning cap) and KEEPS the routing keys (provider/reasoning)."""
+    import scripts.dr_benchmark.super_heavy_preflight as m
+
+    # numeric reasoning cap (Mirror shape)
+    body = {"reasoning": {"max_tokens": 4000}, "provider": {"order": ["x"]}, "max_tokens": 24000}
+    out = m._clamp_probe_budget(body)
+    assert out["max_tokens"] > out["reasoning"]["max_tokens"]
+    assert out["max_tokens"] < 24000 and out["reasoning"]["max_tokens"] < 4000
+    assert out["provider"] == {"order": ["x"]}  # routing untouched
+
+    # effort reasoning (Judge/Sentinel shape) — effort kept, only top-level lowered
+    body2 = {"reasoning": {"enabled": True, "effort": "xhigh"}, "max_tokens": 16384}
+    out2 = m._clamp_probe_budget(body2)
+    assert out2["reasoning"] == {"enabled": True, "effort": "xhigh"}
+    assert out2["max_tokens"] < 16384
diff --git a/tests/preflight/test_false_alarm_regressions.py b/tests/preflight/test_false_alarm_regressions.py
index db0da964..a5ede15d 100644
--- a/tests/preflight/test_false_alarm_regressions.py
+++ b/tests/preflight/test_false_alarm_regressions.py
@@ -2,67 +2,44 @@
 
 Each test FAILS if a previously-killed false alarm resurfaces. Offline, deterministic, no spend.
 These exist because the operator flagged these five as repeat-offenders he never wants to see again:
-the durable kill is a regression test, not a one-off fix."""
+the durable kill is a regression test, not a one-off fix.
+
+The check LOGIC lives in ``scripts/dr_benchmark/false_alarm_checks.py`` (a NON-test module) so the live
+super-heavy pre-spend preflight can RUNTIME-assert the SAME five checks WITHOUT importing ``tests/`` on
+the paid VM. This module is the thin pytest wrapper over that shared logic (one test per check)."""
 from __future__ import annotations
 
 import pathlib
-import re
 import sys
 
 ROOT = pathlib.Path(__file__).resolve().parents[2]
 if str(ROOT) not in sys.path:
     sys.path.insert(0, str(ROOT))
 
+from scripts.dr_benchmark.false_alarm_checks import (  # noqa: E402  (sys.path bootstrap above)
+    check_fa1_crlf_gitattributes_rule_committed,
+    check_fa2_competitor_outputs_present,
+    check_fa3_run_health_fail_loud_guard_present,
+    check_fa4_empty_response_failover_present,
+    check_fa5_journal_only_gated_by_source_restriction,
+)
+
 
 def test_fa1_crlf_gitattributes_rule_committed():
-    """FA1: the signed-bundle fixtures must carry a '-text' .gitattributes rule so core.autocrlf can
-    NEVER rewrite the SHA256-pinned / GPG-signed bytes to CRLF (the 'SHA256_MISMATCH / needs operator
-    signing key' false alarm). The demo key 6336C4448C1901CC is local; conformance is never env-blocked."""
-    gitattributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
-    assert re.search(r"tests/fixtures/signed_bundle/\*\*\s+-text", gitattributes), (
-        "the signed_bundle '-text' .gitattributes rule is gone — CRLF will silently re-break the "
-        "SHA256-pinned/GPG-signed fixtures and resurface the 'needs operator key' false alarm"
-    )
+    check_fa1_crlf_gitattributes_rule_committed()
 
 
 def test_fa2_competitor_outputs_present():
-    """FA2: the ChatGPT + Gemini competitor DR outputs for all 5 golden Qs ARE committed — so 'we've
-    never run the head-to-head' is always a false claim. Grep the repo before asserting any negative."""
-    base = ROOT / "outputs" / "dr_benchmark" / "external_outputs"
-    questions = ["Q72_ai_labor", "Q75_metal_ions_cvd", "Q76_gut_microbiota",
-                 "Q78_parkinsons_dbs", "Q90_adas_liability"]
-    for system in ("gpt_5_5_pro", "gemini_3_1_pro"):
-        for q in questions:
-            path = base / system / f"{q}.md"
-            assert path.exists() and path.stat().st_size > 0, f"competitor output missing/empty: {path}"
+    check_fa2_competitor_outputs_present()
 
 
 def test_fa3_run_health_fail_loud_guard_present():
-    """FA3: a degraded / dead-route run must FAIL LOUD (abort), never swallow into a false-green. The
-    behavioral run-health guard must remain wired in the Gate-B run path."""
-    src = (ROOT / "scripts" / "dr_benchmark" / "pathB_run_gate.py").read_text(encoding="utf-8")
-    assert any(tok in src for tok in ("PG_RUN_HEALTH_GATE", "abort_discovery_degraded", "PG_BEHAVIORAL_CANARY")), (
-        "the run-health / behavioral-canary fail-loud guard is gone — a dead model route could ship a "
-        "false-green run on dead discovery (the drb_72 silent-downgrade lesson)"
-    )
+    check_fa3_run_health_fail_loud_guard_present()
 
 
 def test_fa4_empty_response_failover_present():
-    """FA4: an empty-200 (mirror-blank) must be handled as an intermittent PROVIDER failure (retry /
-    failover), never silently read as the model's defect / a blank answer."""
-    src = (ROOT / "src" / "polaris_graph" / "llm" / "openrouter_client.py").read_text(encoding="utf-8")
-    assert re.search(r"empty[_ ]?response|empty.{0,8}200|allow_fallbacks|provider.{0,12}fail", src, re.I), (
-        "the empty-200 provider-failover handling is gone — mirror-blanks would be misread as a model "
-        "defect instead of an intermittent provider failure"
-    )
+    check_fa4_empty_response_failover_present()
 
 
 def test_fa5_journal_only_gated_by_source_restriction():
-    """FA5: the journal-only adequacy floor must be gated by the protocol's source_restriction — a
-    corpus_approval_denied is NOT auto-authorize and NOT auto-fix-the-classifier; it depends on the
-    question's own declared restriction."""
-    from src.polaris_graph.nodes.journal_only_filter import journal_only_active
-    assert journal_only_active(None) is False                       # no protocol -> floor does NOT fire
-    assert journal_only_active({}) is False                          # no restriction -> floor does NOT fire
-    # a protocol that declares journal_only is flag-dependent (never crashes, never fires blindly)
-    assert journal_only_active({"source_restriction": "journal_only"}) in (True, False)
+    check_fa5_journal_only_gated_by_source_restriction()
```
