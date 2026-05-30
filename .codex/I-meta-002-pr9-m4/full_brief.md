HARD ITERATION CAP: 5 per document. This is iter 1 of the M4 DIFF gate.
- Front-load ALL real findings in iter 1. No drip-feeding.
- Reserve P0/P1 for real execution/safety risks; classify the rest P2/P3.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (emit this exact YAML block as your final output)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

# Codex DIFF-gate — I-meta-002 PR-9/M4: self-host served==pinned

M4 makes the Path-B gate verify that each self-hosted verifier box serves the EXACT pinned model.
Part of the no-spend 4-role readiness sequence (M1 transport, M2 serving config + identity probe,
M3a/M3b builder + seam — all committed + Codex-APPROVE'd). NO MONEY / NO NETWORK in this PR.

## HARD CONSTRAINTS (operator-locked)
- NO SPEND / NO NETWORK: self-host preflight is env + lock read only (no network); assert_post_run
  uses captured/stub metadata; generator-path unit tests run offline=True. The live served==pinned
  check fires only during the later paid canary. No real Vast/OpenRouter call in any tested path.
- Frozen, no drift: claim_audit_scorer.py, runtime lock (NOT promoted — status stays
  codex_approved_pending_operator_signature), M1 openai_compatible_transport.py, pathB_capture.py,
  pathB_runner.py logic. M4 only EXTENDS pathB_run_gate.py.
- D8 remains the single binding gate. _assert_architecture_coverage must still raise while the lock
  is pending operator signature (M4 must NOT relax it).

## What to verify in the diff
1. **Self-host preflight branch**: roles whose lock serving_route starts with `vast_self_host` SKIP
   OpenRouter canonical-slug + provider resolution; instead the gate validates `PG_<ROLE>_BASE_URL`
   is set (fail-closed GateError naming the env var if unset) and pins base_url (trailing-slash
   stripped) + serving_route on the RolePin. Generator (serving_route openrouter) UNCHANGED. This
   branch must be independent of `offline` (env + lock read only — production runs offline=False).
   `_role_serving_routes()` degrades to {} on missing/unreadable lock so unknown roles keep the
   OpenRouter path (confirm this degradation can't silently bypass a self-host check for a real role).
2. **assert_post_run self-host branch**: self-host roles read served `model` + `endpoint` from the
   captured metadata (NOTE: build_response_metadata FLATTENS _pathb_served to top-level `model` +
   `endpoint` keys; there is no literal `_pathb_served` key in response_metadata — confirm the gate
   reads the right keys). Fail-closed (fatal GateError) on: missing endpoint/model, served model !=
   pinned model_slug, served endpoint != pinned base_url (trailing-slash tolerant). Compares against
   the value pinned at preflight. Generator path (provider_name present) UNCHANGED.
3. **_assert_architecture_coverage UNTOUCHED** — still raises while lock pending operator signature.
   Confirm M4 did not replicate/relax that freeze.
4. **Backward-compat**: pathB_gate_pin.json gains 2 additive fields (serving_route, base_url); all
   consumers read role_pins by key with .get(); no additionalProperties:false validator. Confirm safe.
5. Fail-closed everywhere; no silent fallback; a self-host role serving the WRONG model or WRONG box
   must ABORT the gate (this is the served==pinned safety invariant M4 exists to enforce).

## SMOKE (build agent, this session)
- python -c "import scripts.dr_benchmark.pathB_run_gate" — OK
- pytest tests/dr_benchmark tests/roles tests/architecture -q — 389 passed (+9 new M4 gate tests; 2
  pathB_runner fixtures updated to the self-host contract).
- verify_lock --consistency — exit 0 (lock NOT promoted).
- gate_a_dry_run — OVERALL PASS, exit 0.
- tests/polaris_graph not re-run here (M4 touches only pathB_run_gate.py + dr_benchmark tests; the
  49 tests/polaris_graph failures are PRE-EXISTING per the M3b stash-comparison, unrelated to M4).
- No network / no spend in any tested path; frozen files unchanged (git diff verified).

## DIFF (follows)

diff --git a/scripts/dr_benchmark/pathB_run_gate.py b/scripts/dr_benchmark/pathB_run_gate.py
index 017e34df..bce32bb4 100644
--- a/scripts/dr_benchmark/pathB_run_gate.py
+++ b/scripts/dr_benchmark/pathB_run_gate.py
@@ -65,6 +65,13 @@ def control_surface_sources(roots: list[Path]) -> dict[str, list[str]]:
                     out.setdefault(name, set()).add(f"{py.as_posix()}:{i}")
     return {k: sorted(v) for k, v in out.items()}
 
+# I-meta-002 PR-9/M4: a lock `serving_route` starting with this prefix is a self-hosted vLLM
+# verifier box (Mirror / Sentinel / Judge), NOT OpenRouter. Self-host roles skip OpenRouter
+# resolution at preflight and are checked via the served {endpoint, model} (no provider_name).
+_SELF_HOST_ROUTE_PREFIX = "vast_self_host"
+# Per-role self-host endpoint env-var stem (mirrors openai_compatible_transport, LAW VI).
+_SELF_HOST_BASE_URL_ENV_TEMPLATE = "PG_{role}_BASE_URL"
+
 # Volatile response fields EXCLUDED from the served-identity surrogate (Codex iter-5 P2).
 _VOLATILE_METADATA_FIELDS = frozenset(
     {"id", "request_id", "created", "timestamp", "usage", "prompt_tokens",
@@ -146,7 +153,7 @@ def served_identity(call_metadata: dict) -> str:
 
 @dataclass
 class RolePin:
-    role: str            # "generator" | "evaluator"
+    role: str            # "generator" | "evaluator" | "mirror" | "sentinel" | "judge"
     model_slug: str      # FULL OpenRouter slug, e.g. "deepseek/deepseek-v4-pro" — EXACT match
     provider_name: str
     surrogate_fields: tuple[str, ...]   # the metadata fields PROVEN present at preflight
@@ -155,6 +162,15 @@ class RolePin:
     # canonical_slug (e.g. deepseek/deepseek-v4-pro-20260423) is what gets served as `model`
     # in chat completions and is the actual pre-registration anchor in pathB_gate_pin.json.
     # Trailing defaulted field per Codex P2#3 (don't break positional RolePin call sites).
+    serving_route: str | None = None    # I-meta-002 PR-9/M4: the lock-sourced serving_route
+    # for this role (e.g. "openrouter" | "vast_self_host" | "vast_self_host_bf16"). When it
+    # starts with "vast_self_host", preflight takes the self-host branch (NO OpenRouter
+    # resolution) and assert_post_run enforces served==pinned via _pathb_served instead of
+    # provider_name. None / "openrouter" => the unchanged OpenRouter path. Trailing defaulted.
+    base_url: str | None = None          # I-meta-002 PR-9/M4: the configured PG_<ROLE>_BASE_URL
+    # captured at preflight (trailing slash stripped). assert_post_run compares the served
+    # endpoint to THIS pinned value (drift-safe — PG_<ROLE>_BASE_URL is built via .format() so
+    # it is not in the grepped control surface / config-drift hash). Trailing defaulted.
 
 
 def _role_surrogate(metadata: dict, surrogate_fields: tuple[str, ...] | list) -> str:
@@ -213,12 +229,34 @@ def preflight(
         for cred, backend in _REQUIRED_RETRIEVAL_CREDS_TO_BACKENDS.items():
             if not reachability_prober(backend):
                 raise GateError(f"retrieval backend {backend!r} unreachable/invalid-key — not full-power")
+    # I-meta-002 PR-9/M4: lock-sourced role -> serving_route map. Self-host roles
+    # (serving_route: vast_self_host*) DO NOT resolve via OpenRouter; the generator
+    # (serving_route: openrouter) and any role absent from the lock keep the OpenRouter path.
+    serving_routes = _role_serving_routes()
     # 4. each role pin must declare which surrogate fields it PROVED present + a full slug
     for rp in role_pins:
         if not rp.surrogate_fields:
             raise GateError(f"role {rp.role}: no served-identity surrogate fields proven present")
         if "/" not in rp.model_slug:
             raise GateError(f"role {rp.role}: model_slug must be the FULL slug (provider/model), got {rp.model_slug!r}")
+        # I-meta-002 PR-9/M4 self-host branch: a self-hosted vLLM verifier (Mirror / Sentinel /
+        # Judge) is NOT on OpenRouter. Validate its PG_<ROLE>_BASE_URL is configured (fail-closed,
+        # LAW VI: a self-host role with no endpoint is a deployment error, never a silent default)
+        # and record the pinned base_url + serving_route for the post-run served==pinned check.
+        # NO network here (env presence + lock read only — the live /v1/models identity probe is
+        # the M2 canary, not preflight). Skip canonical_slug + OpenRouter provider resolution.
+        route = serving_routes.get(rp.role)
+        rp.serving_route = route
+        if _is_self_host_route(route):
+            base_url_env = _SELF_HOST_BASE_URL_ENV_TEMPLATE.format(role=rp.role.upper())
+            base_url = os.environ.get(base_url_env)
+            if not base_url:
+                raise GateError(
+                    f"role {rp.role}: self-host serving_route {route!r} requires {base_url_env} "
+                    f"to be set (the self-hosted endpoint must be configured, LAW VI)"
+                )
+            rp.base_url = base_url.rstrip("/")
+            continue
         # I-bug-945 (#931): resolve OpenRouter alias to its dated canonical_slug at preflight.
         # The catalog is the single source of truth; fail closed if the alias is unknown.
         # Skipped on offline runs (unit tests pass canonical_slug directly when needed).
@@ -332,6 +370,53 @@ def _assert_architecture_coverage(role_pins: list) -> dict:
     }
 
 
+def _role_serving_routes() -> dict[str, str]:
+    """I-meta-002 PR-9/M4: map ``role -> serving_route`` from the runtime architecture lock.
+
+    Reads ``config/architecture/polaris_runtime_lock.yaml`` (the single machine-readable source
+    of truth). The serving_route tells preflight + assert_post_run which roles are self-hosted
+    vLLM boxes (``serving_route: vast_self_host*``) vs OpenRouter (``serving_route: openrouter``).
+
+    Degrades gracefully (Codex M4 design): a missing / unreadable lock returns ``{}`` so EVERY
+    role falls through to the unchanged OpenRouter path. This keeps the offline
+    generator+evaluator unit fixtures green — ``evaluator`` is not in the lock (=> not self-host)
+    and ``generator`` is ``serving_route: openrouter`` (=> OpenRouter path unchanged). This helper
+    is independent of the freeze in ``_assert_architecture_coverage``: it NEVER raises on lock
+    status (the spend-freeze stays solely in that function, M4 criterion #3).
+    """
+    lock_path = Path(__file__).resolve().parents[2] / "config" / "architecture" / "polaris_runtime_lock.yaml"
+    if not lock_path.exists():
+        return {}
+    try:
+        import yaml  # type: ignore[import-not-found]
+        lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
+    except Exception:
+        return {}
+    required = (lock or {}).get("required_roles") or {}
+    routes: dict[str, str] = {}
+    for role, spec in required.items():
+        route = (spec or {}).get("serving_route")
+        if route:
+            routes[role] = str(route)
+    return routes
+
+
+def _is_self_host_route(serving_route: str | None) -> bool:
+    """True iff ``serving_route`` designates a self-hosted vLLM box (vast_self_host*)."""
+    return bool(serving_route) and serving_route.startswith(_SELF_HOST_ROUTE_PREFIX)
+
+
+def _self_host_endpoint_surrogate(served_model: str, served_endpoint: str) -> str:
+    """Single-valued served-identity surrogate for a self-host role.
+
+    A self-hosted vLLM response carries NO provider_name / system_fingerprint, so the served
+    identity is the (model, endpoint) pair (Codex M4). Used for the per-role no-mid-run-drift
+    check in assert_post_run — distinct from the OpenRouter surrogate over surrogate_fields.
+    """
+    picked = {"model": served_model, "endpoint": served_endpoint}
+    return hashlib.sha256(json.dumps(picked, sort_keys=True).encode("utf-8")).hexdigest()
+
+
 def resolve_role_provider(model_slug: str, provider_order: list[str]) -> str:
     """I-bug-946 (#932): resolve a role's served provider at preflight.
 
@@ -478,6 +563,42 @@ def assert_post_run(
         rp = pins_by_role.get(c.role)
         if rp is None:
             raise GateError(f"call {c.call_id}: role {c.role!r} not pinned")
+        # I-meta-002 PR-9/M4 self-host branch: a self-hosted vLLM verifier (Mirror / Sentinel /
+        # Judge) carries NO provider_name — its served identity is the M1 `_pathb_served`
+        # {endpoint, model}, which pathB_capture.build_response_metadata flattens onto the
+        # captured metadata as top-level `model` + `endpoint` keys (provider_name/
+        # system_fingerprint are dropped for a vLLM response). Read those flattened keys and
+        # fail-closed assert served model == pinned model_slug AND served endpoint == the
+        # PINNED base_url (drift-safe: PG_<ROLE>_BASE_URL is not in the config-drift hash;
+        # comparing against the value pinned at preflight is what catches a wrong-box serve).
+        # Missing endpoint and/or model => the `_pathb_served` block never reached capture =>
+        # fatal. This branch fires BEFORE the surrogate-field / provider OpenRouter checks
+        # (which would spuriously fail on a self-host call that has no provider_name).
+        if _is_self_host_route(rp.get("serving_route")):
+            served_model = c.response_metadata.get("model")
+            served_endpoint = c.response_metadata.get("endpoint")
+            if served_model is None or served_endpoint is None:
+                raise GateError(
+                    f"call {c.call_id}: self-host role {c.role!r} captured no served identity "
+                    f"(_pathb_served endpoint/model missing): model={served_model!r} "
+                    f"endpoint={served_endpoint!r}"
+                )
+            pinned_model = rp["model_slug"]
+            if served_model != pinned_model:
+                raise GateError(
+                    f"call {c.call_id}: self-host role {c.role!r} served model {served_model!r} "
+                    f"!= pinned model_slug {pinned_model!r}"
+                )
+            pinned_base_url = (rp.get("base_url") or "")
+            if pinned_base_url.rstrip("/") != served_endpoint.rstrip("/"):
+                raise GateError(
+                    f"call {c.call_id}: self-host role {c.role!r} served endpoint "
+                    f"{served_endpoint!r} != pinned base_url {rp.get('base_url')!r}"
+                )
+            surrogate_by_role.setdefault(c.role, set()).add(
+                _self_host_endpoint_surrogate(served_model, served_endpoint.rstrip("/"))
+            )
+            continue
         for fld in rp["surrogate_fields"]:
             if fld not in c.response_metadata:
                 raise GateError(f"call {c.call_id}: served metadata missing surrogate field {fld!r}")
diff --git a/tests/dr_benchmark/test_pathB_run_gate.py b/tests/dr_benchmark/test_pathB_run_gate.py
index e4c82703..46c6b139 100644
--- a/tests/dr_benchmark/test_pathB_run_gate.py
+++ b/tests/dr_benchmark/test_pathB_run_gate.py
@@ -575,3 +575,121 @@ def test_full_control_surface_includes_retrieval_creds() -> None:
     from scripts.dr_benchmark.pathB_run_gate import full_control_surface
     surface = full_control_surface([Path("scripts/dr_benchmark")])
     assert "SERPER_API_KEY" in surface and "SEMANTIC_SCHOLAR_API_KEY" in surface
+
+
+# --- I-meta-002 PR-9/M4: self-host served==pinned (NO NETWORK, stub metadata) -------------
+# The runtime lock pins three self-hosted vLLM verifier roles (serving_route: vast_self_host*):
+#   mirror   -> cohere/command-a-plus           (vast_self_host_bf16)
+#   sentinel -> ibm-granite/granite-guardian-4.1-8b (vast_self_host)
+#   judge    -> qwen/qwen3.6-35b-a3b            (vast_self_host_fp8)
+# Preflight branches on serving_route (NO OpenRouter resolution; validate PG_<ROLE>_BASE_URL);
+# assert_post_run consumes the M1 _pathb_served {endpoint, model} (flattened by
+# build_response_metadata onto top-level model+endpoint keys) and fails closed on a wrong
+# model / wrong box. These tests inject stub captured-metadata dicts — no real endpoint.
+
+_MIRROR_SLUG = "cohere/command-a-plus"
+_SENTINEL_SLUG = "ibm-granite/granite-guardian-4.1-8b"
+_MIRROR_BASE_URL = "http://10.0.0.5:8000"
+
+
+def _self_host_pin(role: str, slug: str) -> RolePin:
+    """A self-host RolePin: surrogate_fields are unused by the self-host branch, but the
+    preflight no-empty-surrogate guard still requires them non-empty (matches _role_pins())."""
+    return RolePin(role, slug, "", ("provider_name", "model"))
+
+
+def test_preflight_self_host_passes_when_base_url_set(monkeypatch) -> None:
+    """A self-host role (mirror) passes preflight when PG_MIRROR_BASE_URL is set; NO OpenRouter
+    resolution fires (offline=True keeps the generator path off-network too)."""
+    _full_power_env(monkeypatch)
+    monkeypatch.setenv("PG_MIRROR_BASE_URL", _MIRROR_BASE_URL + "/")  # trailing slash tolerated
+    pins = [_self_host_pin("mirror", _MIRROR_SLUG)]
+    pin = preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)
+    rp = pin["role_pins"][0]
+    assert rp["serving_route"] == "vast_self_host_bf16"
+    assert rp["base_url"] == _MIRROR_BASE_URL  # trailing slash stripped at pin time
+    # Self-host role is NOT resolved via OpenRouter: provider_name stays empty.
+    assert rp["provider_name"] == ""
+
+
+def test_preflight_self_host_fatal_when_base_url_unset(monkeypatch) -> None:
+    """Fail-closed (LAW VI): a self-host role with no PG_<ROLE>_BASE_URL is a deployment error."""
+    _full_power_env(monkeypatch)
+    monkeypatch.delenv("PG_SENTINEL_BASE_URL", raising=False)
+    pins = [_self_host_pin("sentinel", _SENTINEL_SLUG)]
+    with pytest.raises(GateError, match="PG_SENTINEL_BASE_URL"):
+        preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)
+
+
+def test_post_run_self_host_passes_when_model_and_endpoint_match(monkeypatch) -> None:
+    """assert_post_run passes when served model == pinned slug AND served endpoint == base_url.
+    The served metadata carries ONLY model+endpoint (the flattened _pathb_served, no provider)."""
+    _full_power_env(monkeypatch)
+    monkeypatch.setenv("PG_MIRROR_BASE_URL", _MIRROR_BASE_URL)
+    pins = [_self_host_pin("mirror", _MIRROR_SLUG)]
+    pin = preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)
+    # Served endpoint reported WITH a trailing slash — must still match (trailing-slash tolerant).
+    good = [LLMCall("c1", "mirror", True, "h",
+                    {"model": _MIRROR_SLUG, "endpoint": _MIRROR_BASE_URL + "/"})]
+    res = assert_post_run(pin, [], _SALT, good, {"serper", "semantic_scholar"})
+    assert "mirror" in res["served_identity_by_role"]
+
+
+def test_post_run_self_host_fatal_on_missing_pathb_served(monkeypatch) -> None:
+    """Missing endpoint/model (the _pathb_served block never reached capture) => fatal."""
+    _full_power_env(monkeypatch)
+    monkeypatch.setenv("PG_MIRROR_BASE_URL", _MIRROR_BASE_URL)
+    pins = [_self_host_pin("mirror", _MIRROR_SLUG)]
+    pin = preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)
+    # Only model present, endpoint absent -> the served-identity block is incomplete.
+    bad = [LLMCall("c1", "mirror", True, "h", {"model": _MIRROR_SLUG})]
+    with pytest.raises(GateError, match="captured no served identity"):
+        assert_post_run(pin, [], _SALT, bad, {"serper", "semantic_scholar"})
+
+
+def test_post_run_self_host_fatal_on_wrong_model(monkeypatch) -> None:
+    """A self-host box serving the WRONG model must abort the gate (clinical-safety: a wrong
+    verifier model is a silent capability downgrade)."""
+    _full_power_env(monkeypatch)
+    monkeypatch.setenv("PG_MIRROR_BASE_URL", _MIRROR_BASE_URL)
+    pins = [_self_host_pin("mirror", _MIRROR_SLUG)]
+    pin = preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)
+    bad = [LLMCall("c1", "mirror", True, "h",
+                   {"model": "cohere/command-r-plus", "endpoint": _MIRROR_BASE_URL})]
+    with pytest.raises(GateError, match="served model"):
+        assert_post_run(pin, [], _SALT, bad, {"serper", "semantic_scholar"})
+
+
+def test_post_run_self_host_fatal_on_wrong_endpoint(monkeypatch) -> None:
+    """A self-host call served from the WRONG box (endpoint != pinned base_url) must abort."""
+    _full_power_env(monkeypatch)
+    monkeypatch.setenv("PG_MIRROR_BASE_URL", _MIRROR_BASE_URL)
+    pins = [_self_host_pin("mirror", _MIRROR_SLUG)]
+    pin = preflight([], pins, _SALT, offline=True, enforce_architecture_coverage=False)
+    bad = [LLMCall("c1", "mirror", True, "h",
+                   {"model": _MIRROR_SLUG, "endpoint": "http://10.0.0.99:8000"})]
+    with pytest.raises(GateError, match="served endpoint"):
+        assert_post_run(pin, [], _SALT, bad, {"serper", "semantic_scholar"})
+
+
+def test_post_run_generator_openrouter_path_unchanged(monkeypatch) -> None:
+    """The generator (serving_route: openrouter, provider_name present) is UNCHANGED: it still
+    goes through the provider+model OpenRouter checks, not the self-host branch."""
+    _full_power_env(monkeypatch)
+    pin = preflight([], _gen_pin(), _SALT, offline=True, enforce_architecture_coverage=False)
+    # generator's serving_route is 'openrouter' in the lock => OpenRouter path.
+    assert pin["role_pins"][0]["serving_route"] == "openrouter"
+    good = [_good_call("generator")]
+    res = assert_post_run(pin, [], _SALT, good, {"serper", "semantic_scholar"})
+    assert "generator" in res["served_identity_by_role"]
+
+
+def test_role_serving_routes_maps_lock(monkeypatch) -> None:
+    """The lock-sourced route map carries each role's serving_route (generator openrouter;
+    mirror/sentinel/judge vast_self_host*)."""
+    from scripts.dr_benchmark.pathB_run_gate import _role_serving_routes
+    routes = _role_serving_routes()
+    assert routes["generator"] == "openrouter"
+    assert routes["mirror"].startswith("vast_self_host")
+    assert routes["sentinel"].startswith("vast_self_host")
+    assert routes["judge"].startswith("vast_self_host")
diff --git a/tests/dr_benchmark/test_pathB_runner.py b/tests/dr_benchmark/test_pathB_runner.py
index c36672db..f9fb6558 100644
--- a/tests/dr_benchmark/test_pathB_runner.py
+++ b/tests/dr_benchmark/test_pathB_runner.py
@@ -28,6 +28,16 @@ _FOUR_ROLE_SLUGS = {
     "judge": _JUDGE_SLUG,
 }
 
+# I-meta-002 PR-9/M4: the 3 self-hosted vLLM verifier roles (serving_route: vast_self_host*)
+# require a configured PG_<ROLE>_BASE_URL at preflight and serve from THAT box. The post-run
+# gate compares the served endpoint to the pinned base_url, so the captured-metadata endpoint
+# below MUST equal the env value set in _full_power_env (single source of truth, no network).
+_SELF_HOST_BASE_URLS = {
+    "mirror": "http://10.0.0.5:8000",
+    "sentinel": "http://10.0.0.6:8000",
+    "judge": "http://10.0.0.7:8000",
+}
+
 
 def _full_power_env(monkeypatch) -> None:
     monkeypatch.setenv("OPENROUTER_ALLOW_FALLBACKS", "false")
@@ -42,20 +52,39 @@ def _full_power_env(monkeypatch) -> None:
     # keep it equal to the default entailment model (gemma) so that gate stays satisfied. It
     # is NOT a role pin anymore (the 4-role set is generator/mirror/sentinel/judge).
     monkeypatch.setenv("PG_EVALUATOR_MODEL", "google/gemma-4-31b-it")
+    # I-meta-002 PR-9/M4: each self-host verifier role's endpoint must be configured at
+    # preflight (LAW VI fail-closed). Env-only — NO network in these offline tests.
+    for role, base_url in _SELF_HOST_BASE_URLS.items():
+        monkeypatch.setenv(f"PG_{role.upper()}_BASE_URL", base_url)
 
 
 def _capture_four_roles(pc) -> None:
     """Capture one served completion per locked role (generator/mirror/sentinel/judge).
 
     The post-run gate requires every PINNED role to appear in captured calls; the 4-role pin
-    set therefore needs a capture for each. Provider is the offline-pinned 'deepinfra' (the
-    only entry in OPENROUTER_PROVIDER_ORDER), and each served model matches its role's pin.
+    set therefore needs a capture for each.
+
+    Role-specific served shape (I-meta-002 PR-9/M4):
+    - generator (serving_route: openrouter) keeps the OpenRouter raw shape (provider +
+      served model); it still goes through the OpenRouter provider+model post-run checks. The
+      provider is the offline-pinned 'deepinfra' (the only entry in OPENROUTER_PROVIDER_ORDER).
+    - mirror/sentinel/judge (serving_route: vast_self_host*) carry the M1 self-host raw shape
+      raw['_pathb_served'] = {'endpoint': base_url, 'model': served_model} — exactly what
+      openai_compatible_transport stashes — which build_response_metadata flattens onto the
+      captured metadata as top-level model+endpoint keys for the served==pinned check. The
+      endpoint matches the PG_<ROLE>_BASE_URL set in _full_power_env (same source of truth).
     """
     for role, slug in _FOUR_ROLE_SLUGS.items():
+        if role in _SELF_HOST_BASE_URLS:
+            raw_response = {
+                "_pathb_served": {"endpoint": _SELF_HOST_BASE_URLS[role], "model": slug}
+            }
+        else:
+            raw_response = {"provider": "deepinfra", "model": slug}
         pc.capture_llm_call(
             role=role,
             messages=[{"role": "user", "content": role}],
-            raw_response={"provider": "deepinfra", "model": slug},
+            raw_response=raw_response,
         )
 
 
