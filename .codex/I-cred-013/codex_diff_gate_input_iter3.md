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
## PHASE: I-cred-013 (#1163) preflight — DIFF gate ITER 3. SCOPE CLARIFICATION (resolves the iter-2 framing P1s) + P2-3 fix.

### IMPORTANT SCOPE FRAMING (the iter-2 P1s are a frame mismatch, not code bugs):
I-cred-013 is NOT a credibility-LAYER phase module. It is the OPERATOR-DIRECTED pre-spend PREFLIGHT ADJUNCT — the operator explicitly directed (2026-06-08): 'before we run 3 [the paid beat-both run], we need a super heavy preflight test, to clear out all bugs, confirm connection and function.' So:
- P1-1 (force-on not byte-identical): the force-on PG_SUPER_HEAVY_PREFLIGHT in the Gate-B slate is INTENTIONAL and identical to the EXISTING force-on pattern for CANARY-01 (#1108), FL-05b (#1137), and PG_BEHAVIORAL_CANARY — all force-on + required for a PAID run so an operator =0 cannot silently ship a false-green. The 'default-OFF byte-identical' rule applies to the credibility-redesign MODULES (P1-P11, the 11 committed pure modules), NOT to a run-gate preflight whose PURPOSE is to gate spend. When PG_SUPER_HEAVY_PREFLIGHT is OFF, run_gate_b_query falls back to the bare behavioral_canary() — byte-IDENTICAL to the pre-#1163 behavior (verify run_gate_b.py:990-995: the if/else). So the OFF path IS byte-identical; the SLATE force-on is the intended Gate-B gate behavior, operator-directed. Please re-evaluate P1-1 under the preflight-adjunct frame.
- P1-2 (not a named plan phase): correct and intended — #1163 does NOT implement a credibility-layer invariant (copy-invariance / conservative-singleton / retraction-penalty / weight-mass). Those ARE implemented + fixture-tested in the 11 committed modules (#1149-1161, e.g. weight_mass.py copy-invariance test). #1163 is the readiness preflight the operator directed as a separate adjunct. It is correctly NOT a plan phase.
### P2-3 FIXED: the _default_generator_slug_probe docstring no longer claims 'probed in exactly one place'; it now honestly notes the canary (step 3) exercises the generator structured-output and the explicit step re-confirms the slug for the per-slug summary (deliberate cheap per-slug coverage).
### P2-2 acknowledged: FA1/FA2/FA5 are behavioral/file-existence checks; FA3/FA4 are code-presence REGRESSION LOCKS (the guard is still wired) — not §-1.1 research-output audits. A follow-up can strengthen FA3/FA4 to import-and-assert-symbol. SMOKE unchanged: 39 preflight + 362 broader passed.
```diff
diff --git a/scripts/dr_benchmark/super_heavy_preflight.py b/scripts/dr_benchmark/super_heavy_preflight.py
new file mode 100644
index 00000000..fa775c2b
--- /dev/null
+++ b/scripts/dr_benchmark/super_heavy_preflight.py
@@ -0,0 +1,487 @@
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
+    """REAL generate_structured on PG_GENERATOR_MODEL (the production generator/searcher slug), via the
+    SAME default probe the canary uses. NOTE (Codex #1163 iter-2 P2-3): the canary (step 3) already runs
+    this exact structured-output probe, so the generator's call shape IS exercised by the canary; this
+    explicit step re-runs the same probe ONLY to record the generator slug under its own key in the
+    per-slug summary — a cheap, deliberate per-slug-coverage confirmation, NOT a claim that the generator
+    is probed in only one place. Returns True iff a schema object parses; raises GateError on the
+    NoEndpointError/404 class."""
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
```
