"""Path-B run gate: fatal preflight + post-run enforcement for the DR head-to-head.

I-safety-002b (#925), Codex-APPROVE'd plan v5 (5 review rounds). The existing
`model_pin.json` is non-gating telemetry, `OPENROUTER_ALLOW_FALLBACKS` defaults true, and
"full power" silently degrades if a retrieval key is missing. This gate makes the run
full-power + correctly-modeled + drift-free + secret-safe, ENFORCED not asserted-in-prose.

Pure-logic core (this module) is fixture-tested with NO live system. The runner wiring
(prompt-capture at the LLM call boundary) consumes these functions.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

# Env-var name patterns the runner+client read (Codex: enumerate, do not handpick).
_CONTROL_PREFIXES = ("PG_", "OPENROUTER_")
# A var name is a SECRET (redact value) iff it looks like a credential. NOTE: exclude the
# many *_MAX_TOKENS / *_TOKEN_BUDGET knobs — those are config, not secrets.
_SECRET_SUFFIXES = ("_API_KEY", "_SECRET", "_ACCESS_TOKEN", "_AUTH_TOKEN")
_SECRET_EXPLICIT = {
    "OPENROUTER_API_KEY", "SERPER_API_KEY", "SEMANTIC_SCHOLAR_API_KEY",
    "EXA_API_KEY", "OPEN_PAGERANK_API_KEY",
    # Codex PR-2 diff iter-1 P2: PG_PATHB_GATE_SALT is the HMAC salt used by
    # build_effective_config to redact secrets — it MUST not be persisted in the pin.
    "PG_PATHB_GATE_SALT",
}
_REQUIRED_RETRIEVAL_CREDS = ("SERPER_API_KEY", "SEMANTIC_SCHOLAR_API_KEY")
# Run-affecting env that is NOT PG_*/OPENROUTER_* prefixed — must still be in the config hash
# (Codex P1: retrieval creds/knobs were missing from the whole-surface enumeration).
_EXTRA_CONTROL_ENV = (
    "SERPER_API_KEY", "SEMANTIC_SCHOLAR_API_KEY", "EXA_API_KEY", "OPEN_PAGERANK_API_KEY",
)


def full_control_surface(roots: list[Path]) -> list[str]:
    """Complete run-affecting env set = enumerated PG_*/OPENROUTER_* UNION the extra
    retrieval/credential env (Codex P1 — these affect the run but aren't prefix-matched)."""
    return sorted(set(enumerate_control_surface(roots)) | set(_EXTRA_CONTROL_ENV))


def control_surface_sources(roots: list[Path]) -> dict[str, list[str]]:
    """name -> sorted ['<relpath>:<lineno>', ...] provenance for each control var (Codex P2)."""
    extra = "|".join(re.escape(n) for n in _EXTRA_CONTROL_ENV)
    pat = re.compile(
        rf"os\.(?:getenv|environ\.get)\(\s*['\"]((?:PG_|OPENROUTER_)[A-Z0-9_]+|{extra})['\"]"
        rf"|os\.environ\[\s*['\"]((?:PG_|OPENROUTER_)[A-Z0-9_]+|{extra})['\"]"
    )
    out: dict[str, set[str]] = {}
    for root in roots:
        for py in root.rglob("*.py"):
            try:
                lines = py.read_text(encoding="utf-8", errors="ignore").splitlines()
            except OSError:
                continue
            for i, line in enumerate(lines, 1):
                for m in pat.finditer(line):
                    name = m.group(1) or m.group(2)
                    out.setdefault(name, set()).add(f"{py.as_posix()}:{i}")
    return {k: sorted(v) for k, v in out.items()}

# I-meta-002 PR-9/M4: a lock `serving_route` starting with this prefix is a self-hosted vLLM
# verifier box (Mirror / Sentinel / Judge), NOT OpenRouter. Self-host roles skip OpenRouter
# resolution at preflight and are checked via the served {endpoint, model} (no provider_name).
_SELF_HOST_ROUTE_PREFIX = "vast_self_host"
# Per-role self-host endpoint env-var stem (mirrors openai_compatible_transport, LAW VI).
_SELF_HOST_BASE_URL_ENV_TEMPLATE = "PG_{role}_BASE_URL"

# Volatile response fields EXCLUDED from the served-identity surrogate (Codex iter-5 P2).
_VOLATILE_METADATA_FIELDS = frozenset(
    {"id", "request_id", "created", "timestamp", "usage", "prompt_tokens",
     "completion_tokens", "total_tokens", "latency", "latency_ms", "cost", "x-request-id"}
)


class GateError(RuntimeError):
    """Fatal gate violation — the run is INVALID and must be discarded, never scored."""


def is_secret_var(name: str) -> bool:
    """True iff `name` is a credential whose VALUE must be redacted (not a *_TOKENS knob)."""
    if name in _SECRET_EXPLICIT:
        return True
    if name.endswith(("_MAX_TOKENS", "_TOKENS", "_TOKEN_BUDGET")):
        return False
    return name.endswith(_SECRET_SUFFIXES)


def enumerate_control_surface(roots: list[Path]) -> list[str]:
    """Scan source for every PG_*/OPENROUTER_* env var actually read (Codex: complete set).

    Greps os.getenv / os.environ.get / os.environ[...] reads — NOT a handpicked list.
    """
    pat = re.compile(
        r"os\.(?:getenv|environ\.get)\(\s*['\"]((?:PG_|OPENROUTER_)[A-Z0-9_]+)['\"]"
        r"|os\.environ\[\s*['\"]((?:PG_|OPENROUTER_)[A-Z0-9_]+)['\"]"
    )
    found: set[str] = set()
    for root in roots:
        for py in root.rglob("*.py"):
            try:
                text = py.read_text(encoding="utf-8", errors="ignore")
            except OSError:
                continue
            for m in pat.finditer(text):
                found.add(m.group(1) or m.group(2))
    return sorted(found)


def _redact(name: str, value: str | None, salt: bytes) -> dict:
    """Secret presence record: present/length/salted-HMAC only — never the value (Codex P1)."""
    if value is None:
        return {"present": False, "length": 0, "salted_hmac": None}
    digest = hmac.new(salt, value.encode("utf-8"), hashlib.sha256).hexdigest()
    return {"present": True, "length": len(value), "salted_hmac": digest}


def build_effective_config(control_vars: list[str], salt: bytes) -> dict:
    """Snapshot the full control surface; secret VALUES redacted (Codex P1)."""
    cfg: dict[str, dict] = {}
    for name in control_vars:
        val = os.environ.get(name)
        if is_secret_var(name):
            cfg[name] = {"secret": True, **_redact(name, val, salt)}
        else:
            cfg[name] = {"secret": False, "value": val, "set": val is not None}
    return cfg


def effective_config_hash(cfg: dict) -> str:
    return hashlib.sha256(json.dumps(cfg, sort_keys=True).encode("utf-8")).hexdigest()


def served_identity(call_metadata: dict) -> str:
    """Stable per-role served-identity surrogate (Codex iter-4 P1 + iter-5 P2).

    OpenRouter has no stable `model_version`; use provider_name + model + system_fingerprint
    (+ any stable router metadata), EXCLUDING volatile fields. Missing the agreed surrogate
    fields is caught by the caller (fatal), not silently hashed to a constant here.
    """
    stable = {
        k: v for k, v in call_metadata.items()
        if k not in _VOLATILE_METADATA_FIELDS
    }
    return hashlib.sha256(json.dumps(stable, sort_keys=True).encode("utf-8")).hexdigest()


@dataclass
class RolePin:
    role: str            # "generator" | "evaluator" | "mirror" | "sentinel" | "judge"
    model_slug: str      # FULL OpenRouter slug, e.g. "deepseek/deepseek-v4-pro" — EXACT match
    provider_name: str
    surrogate_fields: tuple[str, ...]   # the metadata fields PROVEN present at preflight
    canonical_slug: str | None = None   # I-bug-945 (#931): OpenRouter dated snapshot resolved
    # at preflight via GET /api/v1/models. The alias `model_slug` is the env-pin handle; the
    # canonical_slug (e.g. deepseek/deepseek-v4-pro-20260423) is what gets served as `model`
    # in chat completions and is the actual pre-registration anchor in pathB_gate_pin.json.
    # Trailing defaulted field per Codex P2#3 (don't break positional RolePin call sites).
    serving_route: str | None = None    # I-meta-002 PR-9/M4: the lock-sourced serving_route
    # for this role (e.g. "openrouter" | "vast_self_host" | "vast_self_host_bf16"). When it
    # starts with "vast_self_host", preflight takes the self-host branch (NO OpenRouter
    # resolution) and assert_post_run enforces served==pinned via _pathb_served instead of
    # provider_name. None / "openrouter" => the unchanged OpenRouter path. Trailing defaulted.
    base_url: str | None = None          # I-meta-002 PR-9/M4: the configured PG_<ROLE>_BASE_URL
    # captured at preflight (trailing slash stripped). assert_post_run compares the served
    # endpoint to THIS pinned value (drift-safe — PG_<ROLE>_BASE_URL is built via .format() so
    # it is not in the grepped control surface / config-drift hash). Trailing defaulted.


def _role_surrogate(metadata: dict, surrogate_fields: tuple[str, ...] | list) -> str:
    """The served-identity surrogate over the PINNED fields only (Codex P1 — exact pin)."""
    picked = {f: metadata.get(f) for f in surrogate_fields}
    return hashlib.sha256(json.dumps(picked, sort_keys=True).encode("utf-8")).hexdigest()


def preflight(
    control_vars: list[str],
    role_pins: list[RolePin],
    salt: bytes,
    reachability_prober=None,
    source_map: dict[str, list[str]] | None = None,
    roots: list[Path] | None = None,
    offline: bool = False,
    enforce_architecture_coverage: bool = True,
) -> dict:
    """Fatal preflight. Returns the pin record to hash-pin BEFORE the run.

    The gate FORCES the complete control surface (Codex iter-2 P1): it always unions the
    retrieval/credential env into `control_vars`, and if `roots` is given it also unions the
    grepped PG_*/OPENROUTER_* surface — so a caller passing `[]` cannot produce an empty config.

    Reachability is enforce-by-default for real runs (Codex iter-2 P1): if `offline` is False
    and no prober is given, `real_retrieval_prober` is used (live ping). Tests pass
    `offline=True` to skip the network. `reachability_checked=False` is therefore only
    possible in an explicitly-offline (test) run, never a real run gate.
    """
    # FORCE the complete control surface (retrieval creds always; grepped surface if roots given)
    surface = set(control_vars or [])
    if roots:
        surface |= set(full_control_surface(roots))
    surface |= set(_EXTRA_CONTROL_ENV)
    control_vars = sorted(surface)
    # reachability: enforce-by-default for real runs
    if not offline and reachability_prober is None:
        reachability_prober = real_retrieval_prober
    # 1. fallbacks OFF
    if os.environ.get("OPENROUTER_ALLOW_FALLBACKS", "true").strip().lower() not in ("false", "0", "no"):
        raise GateError("OPENROUTER_ALLOW_FALLBACKS must be false (it defaults TRUE)")
    # 2. provider routing — per-role resolution at preflight (I-bug-946 #932).
    # The env supplies a candidate list (comma-separated). Each role's actual served provider
    # is resolved via OpenRouter's per-model endpoints endpoint and pinned per role. The old
    # "singleton" check rejected multi-provider orders, but disjoint model provider sets
    # require a multi-entry order (e.g. fireworks for deepseek-v4-pro, novita for gemma).
    order = (os.environ.get("OPENROUTER_PROVIDER_ORDER") or "").strip()
    provider_order_list = [p.strip() for p in order.split(",") if p.strip()]
    if not provider_order_list:
        raise GateError("OPENROUTER_PROVIDER_ORDER must list at least one candidate provider")
    # 3. required retrieval capability — PRESENCE *and* REACHABILITY (Codex P1)
    missing = [c for c in _REQUIRED_RETRIEVAL_CREDS if not os.environ.get(c)]
    if missing:
        raise GateError(f"required retrieval credentials absent — not full-power: {missing}")
    if reachability_prober is not None:
        for cred, backend in _REQUIRED_RETRIEVAL_CREDS_TO_BACKENDS.items():
            if not reachability_prober(backend):
                raise GateError(f"retrieval backend {backend!r} unreachable/invalid-key — not full-power")
    # I-meta-002 PR-9/M4: lock-sourced role -> serving_route map. Self-host roles
    # (serving_route: vast_self_host*) DO NOT resolve via OpenRouter; the generator
    # (serving_route: openrouter) and any role absent from the lock keep the OpenRouter path.
    serving_routes = _role_serving_routes()
    # 4. each role pin must declare which surrogate fields it PROVED present + a full slug
    for rp in role_pins:
        if not rp.surrogate_fields:
            raise GateError(f"role {rp.role}: no served-identity surrogate fields proven present")
        if "/" not in rp.model_slug:
            raise GateError(f"role {rp.role}: model_slug must be the FULL slug (provider/model), got {rp.model_slug!r}")
        # I-meta-002 PR-9/M4 self-host branch: a self-hosted vLLM verifier (Mirror / Sentinel /
        # Judge) is NOT on OpenRouter. Validate its PG_<ROLE>_BASE_URL is configured (fail-closed,
        # LAW VI: a self-host role with no endpoint is a deployment error, never a silent default)
        # and record the pinned base_url + serving_route for the post-run served==pinned check.
        # NO network here (env presence + lock read only — the live /v1/models identity probe is
        # the M2 canary, not preflight). Skip canonical_slug + OpenRouter provider resolution.
        route = serving_routes.get(rp.role)
        rp.serving_route = route
        if _is_self_host_route(route):
            base_url_env = _SELF_HOST_BASE_URL_ENV_TEMPLATE.format(role=rp.role.upper())
            base_url = os.environ.get(base_url_env)
            if not base_url:
                raise GateError(
                    f"role {rp.role}: self-host serving_route {route!r} requires {base_url_env} "
                    f"to be set (the self-hosted endpoint must be configured, LAW VI)"
                )
            rp.base_url = base_url.rstrip("/")
            continue
        # I-bug-945 (#931): resolve OpenRouter alias to its dated canonical_slug at preflight.
        # The catalog is the single source of truth; fail closed if the alias is unknown.
        # Skipped on offline runs (unit tests pass canonical_slug directly when needed).
        if not offline and rp.canonical_slug is None:
            rp.canonical_slug = resolve_canonical_slug(rp.model_slug)
        # I-bug-946 (#932): resolve per-role provider via /api/v1/models/<id>/endpoints.
        # Codex iter-1 diff P1: online preflight MUST always overwrite provider_name from
        # the resolver, because _role_pins() previously pre-seeded provider_name from the
        # env's first entry (now changed to empty, but the always-overwrite invariant is
        # the defense-in-depth — any future caller passing a non-empty provider_name still
        # gets re-resolved at preflight, so the persisted pin reflects the actual resolution).
        # Offline tests skip the resolver; if provider_name is empty under offline, fall
        # back to the env's first entry (test-compat — tests still drive the pipeline via
        # OPENROUTER_PROVIDER_ORDER and expect the served provider to match the pin).
        if not offline:
            rp.provider_name = resolve_role_provider(rp.model_slug, provider_order_list)
        elif not rp.provider_name and provider_order_list:
            rp.provider_name = provider_order_list[0]
    # I-bug-946 (Codex iter 2 P2#3 + iter-1 diff P2#2): enforce that the effective
    # entailment model equals the effective evaluator model. Compare EFFECTIVE values
    # (with their defaults) so a single env override that diverges from the default still
    # fails closed — not only the "both env vars set divergently" case.
    _DEFAULT_ENTAILMENT_MODEL = "google/gemma-4-31b-it"  # mirror entailment_judge.py:79
    _DEFAULT_EVALUATOR_MODEL = "google/gemma-4-31b-it"   # mirror pathB_runner.py:37
    eff_entail = (os.environ.get("PG_ENTAILMENT_MODEL") or _DEFAULT_ENTAILMENT_MODEL).strip()
    eff_eval = (os.environ.get("PG_EVALUATOR_MODEL") or _DEFAULT_EVALUATOR_MODEL).strip()
    if eff_entail != eff_eval:
        raise GateError(
            f"effective PG_ENTAILMENT_MODEL={eff_entail!r} != effective PG_EVALUATOR_MODEL"
            f"={eff_eval!r}; the gate cannot pin two different evaluator-family models"
        )
    # I-meta-001 (#933) Step 9: enforce architecture coverage at preflight.
    # If config/architecture/polaris_runtime_lock.yaml exists, its required_roles set
    # MUST match the role_pins set (every locked role pinned). Gate refuses if missing.
    # offline=True implies test mode (unit fixtures intentionally use 2-role pins);
    # tests can also explicitly opt out via enforce_architecture_coverage=False.
    _enforce_coverage = enforce_architecture_coverage and not offline
    arch_coverage = (
        _assert_architecture_coverage(role_pins) if _enforce_coverage
        else {"status": "skipped", "missing_roles": [], "lock_status": None,
              "warning": "architecture coverage check skipped (offline=True or enforce=False)"}
    )
    cfg = build_effective_config(control_vars, salt)
    return {
        "effective_config": cfg,
        "effective_config_hash": effective_config_hash(cfg),
        "control_vars": control_vars,             # the RESOLVED surface (post-run rebuilds from this)
        "control_source_map": source_map or {},   # name -> [file:line, ...] provenance (Codex P2)
        "role_pins": [vars(rp) | {"surrogate_fields": list(rp.surrogate_fields)} for rp in role_pins],
        "architecture_coverage": arch_coverage,  # I-meta-001 Step 9
        "reachability_checked": reachability_prober is not None,
        "openrouter_allow_fallbacks": False,
        "openrouter_provider_order": order,
    }


def _assert_architecture_coverage(role_pins: list) -> dict:
    """I-meta-001 (#933) Step 9: refuse the smoke unless every locked architecture role
    is present in role_pins.

    Loads ``config/architecture/polaris_runtime_lock.yaml``. If the lock exists AND
    its status is ``locked``, every ``required_roles`` key must appear in role_pins.
    If status is ``codex_approved_pending_operator_signature`` (the explicit operator
    freeze state), the gate refuses ALL smokes — smokes resume only after the lock is
    promoted to ``locked`` via scripts/architecture/verify_lock.py.

    When the lock file is missing (legacy path / pre-Step-4 commits), behavior is
    permissive: accept any role_pins shape but emit a warning in the returned dict.

    Returns a dict {"status": ..., "missing_roles": [...], "lock_status": ...}.
    Raises GateError when coverage is enforced and violated.
    """
    from pathlib import Path
    lock_path = Path(__file__).resolve().parents[2] / "config" / "architecture" / "polaris_runtime_lock.yaml"
    if not lock_path.exists():
        return {"status": "no_lock", "missing_roles": [], "lock_status": None,
                "warning": "no config/architecture/polaris_runtime_lock.yaml — coverage not enforced"}

    try:
        import yaml  # type: ignore[import-not-found]
        lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise GateError(f"architecture lock unreadable: {exc}") from exc

    lock_status = lock.get("status")
    required_roles = set(lock.get("required_roles", {}).keys())
    pinned_roles = {rp.role for rp in role_pins}
    missing = required_roles - pinned_roles

    if lock_status == "codex_approved_pending_operator_signature":
        raise GateError(
            "architecture lock status is 'codex_approved_pending_operator_signature' — "
            "smokes FROZEN per operator directive (I-meta-001 #933). Promote the lock to "
            "status: locked via scripts/architecture/verify_lock.py after all propagation "
            "checkpoints are complete + tests pass + operator commits."
        )

    if lock_status == "locked" and missing:
        raise GateError(
            f"architecture coverage incomplete: locked roles {required_roles!r} "
            f"but pinned only {pinned_roles!r}; missing {missing!r}. The 4-role "
            f"architecture requires generator + mirror + sentinel + judge."
        )

    return {
        "status": "ok" if not missing else "partial",
        "missing_roles": sorted(missing),
        "lock_status": lock_status,
        "required_roles": sorted(required_roles),
        "pinned_roles": sorted(pinned_roles),
    }


def _role_serving_routes() -> dict[str, str]:
    """I-meta-002 PR-9/M4: map ``role -> serving_route`` from the runtime architecture lock.

    Reads ``config/architecture/polaris_runtime_lock.yaml`` (the single machine-readable source
    of truth). The serving_route tells preflight + assert_post_run which roles are self-hosted
    vLLM boxes (``serving_route: vast_self_host*``) vs OpenRouter (``serving_route: openrouter``).

    Degrades gracefully (Codex M4 design): a missing / unreadable lock returns ``{}`` so EVERY
    role falls through to the unchanged OpenRouter path. This keeps the offline
    generator+evaluator unit fixtures green — ``evaluator`` is not in the lock (=> not self-host)
    and ``generator`` is ``serving_route: openrouter`` (=> OpenRouter path unchanged). This helper
    is independent of the freeze in ``_assert_architecture_coverage``: it NEVER raises on lock
    status (the spend-freeze stays solely in that function, M4 criterion #3).
    """
    lock_path = Path(__file__).resolve().parents[2] / "config" / "architecture" / "polaris_runtime_lock.yaml"
    if not lock_path.exists():
        return {}
    try:
        import yaml  # type: ignore[import-not-found]
        lock = yaml.safe_load(lock_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    required = (lock or {}).get("required_roles") or {}
    routes: dict[str, str] = {}
    for role, spec in required.items():
        route = (spec or {}).get("serving_route")
        if route:
            routes[role] = str(route)
    return routes


def _is_self_host_route(serving_route: str | None) -> bool:
    """True iff ``serving_route`` designates a self-hosted vLLM box (vast_self_host*)."""
    return bool(serving_route) and serving_route.startswith(_SELF_HOST_ROUTE_PREFIX)


def _self_host_endpoint_surrogate(served_model: str, served_endpoint: str) -> str:
    """Single-valued served-identity surrogate for a self-host role.

    A self-hosted vLLM response carries NO provider_name / system_fingerprint, so the served
    identity is the (model, endpoint) pair (Codex M4). Used for the per-role no-mid-run-drift
    check in assert_post_run — distinct from the OpenRouter surrogate over surrogate_fields.
    """
    picked = {"model": served_model, "endpoint": served_endpoint}
    return hashlib.sha256(json.dumps(picked, sort_keys=True).encode("utf-8")).hexdigest()


def resolve_role_provider(model_slug: str, provider_order: list[str]) -> str:
    """I-bug-946 (#932): resolve a role's served provider at preflight.

    OpenRouter's GET /api/v1/models/<id>/endpoints returns the providers that actually serve
    a model. Smoke #15 demonstrated that without per-role resolution, OpenRouter silently
    routes a role to a provider OUTSIDE the env-pinned order (gemma is not on Fireworks, so
    the evaluator was routed to Novita despite `OPENROUTER_PROVIDER_ORDER=fireworks` +
    `allow_fallbacks=false`). The gate caught it correctly; the pin model was wrong.

    Algorithm:
      1. Fetch /api/v1/models/<id>/endpoints; parse `data.endpoints`.
      2. Eligible = endpoints with status absent OR status==0. status != 0 means degraded /
         lower-priority per OpenRouter docs (Codex iter-2 P2#4).
      3. Intersect eligible providers (case-insensitive) with `provider_order`.
      4. Return the catalog-cased provider_name of the FIRST match in `provider_order`.
      5. Fail closed with diagnostic if no match OR endpoints list is empty.

    Codex APPROVE iter 2 on choice C, brief at .codex/I-bug-946/brief_iter2.md.
    """
    import requests
    api_key = os.environ.get("OPENROUTER_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    url = f"https://openrouter.ai/api/v1/models/{model_slug}/endpoints"
    try:
        r = requests.get(url, headers=headers, timeout=20)
        r.raise_for_status()
        endpoints = r.json().get("data", {}).get("endpoints", [])
    except Exception as exc:
        raise GateError(f"OpenRouter endpoints catalog unreachable for {model_slug!r}: {exc}") from exc
    if not endpoints:
        raise GateError(f"OpenRouter has no endpoints for model {model_slug!r} (model offline?)")
    eligible: list[str] = []
    for ep in endpoints:
        status = ep.get("status")
        if status is None or status == 0:
            name = ep.get("provider_name")
            if name:
                eligible.append(name)
    if not eligible:
        raise GateError(
            f"OpenRouter has no eligible (status==0) endpoints for {model_slug!r}; "
            f"all endpoints degraded"
        )
    eligible_lower = {n.lower(): n for n in eligible}  # case-insensitive lookup, catalog cased value
    for wanted in provider_order:
        catalog_cased = eligible_lower.get(wanted.strip().lower())
        if catalog_cased is not None:
            return catalog_cased
    raise GateError(
        f"OPENROUTER_PROVIDER_ORDER={provider_order!r} has no intersection with eligible "
        f"endpoints for {model_slug!r}; available: {sorted(set(eligible))}"
    )


def resolve_canonical_slug(model_slug: str) -> str | None:
    """I-bug-945 (#931): Resolve OpenRouter alias to its dated canonical_slug at preflight.

    OpenRouter exposes a list at GET /api/v1/models with `id` (alias) + `canonical_slug`
    (dated snapshot) per entry. The chat-completions response returns `model=<canonical_slug>`
    while the env pin uses `<id>`. Resolving at preflight lets `assert_post_run` accept the
    served canonical_slug without losing pre-registration integrity — the resolved value is
    persisted in `pathB_gate_pin.json` and becomes the audit anchor.

    Returns the canonical_slug, or None if it equals model_slug (no dated suffix exposed).
    Raises GateError if the slug is not in the catalog (fail closed) — Codex P2#2.
    """
    import requests
    api_key = os.environ.get("OPENROUTER_API_KEY")
    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    try:
        r = requests.get("https://openrouter.ai/api/v1/models", headers=headers, timeout=20)
        r.raise_for_status()
        data = r.json().get("data", [])
    except Exception as exc:
        raise GateError(f"OpenRouter models catalog unreachable: {exc}") from exc
    for m in data:
        if m.get("id") == model_slug:
            cs = m.get("canonical_slug")
            return cs if cs and cs != model_slug else None
    raise GateError(f"OpenRouter catalog has no entry for pinned slug {model_slug!r} (alias unknown)")


def real_retrieval_prober(backend: str) -> bool:
    """Minimal live reachability ping per backend (Codex P1). Returns True iff a valid
    response. Cheap; runs once at preflight. Imported lazily to keep the module light."""
    import requests
    try:
        if backend == "serper":
            r = requests.post(
                "https://google.serper.dev/search",
                headers={"X-API-KEY": os.environ["SERPER_API_KEY"], "Content-Type": "application/json"},
                json={"q": "metformin"}, timeout=15,
            )
            return r.status_code == 200
        if backend == "semantic_scholar":
            r = requests.get(
                "https://api.semanticscholar.org/graph/v1/paper/search",
                headers={"x-api-key": os.environ["SEMANTIC_SCHOLAR_API_KEY"]},
                params={"query": "metformin", "limit": 1}, timeout=20,
            )
            return r.status_code == 200
    except Exception:
        return False
    return False


# ---------------------------------------------------------------------------
# I-ready-017 CANARY-01 (#1108): behavioral pre-spend canary.
# The drb_72 held run's preflight checked CONFIG + the 4 VERIFIER slugs but NOT the
# searcher/generator generate_structured call shape (the FX-01-keystone 404 class that silently
# killed agentic discovery) nor a real 1-query search. A dead route was SWALLOWED -> a "green" run on
# dead discovery (~7 sources from "1000 URLs"). This canary tests BEHAVIOR — real call shapes, every
# probed component ALIVE — and FAILS CLOSED before any full-run spend. chromium is intentionally NOT
# probed: the benchmark fetch path is httpx (live_retriever), not a headless browser; chromium
# readiness is FX-16 (VM-side).
# ---------------------------------------------------------------------------
_BEHAVIORAL_CANARY_ENV = "PG_BEHAVIORAL_CANARY"


def _default_structured_output_probe() -> bool:
    """REAL generate_structured call on the default generator/searcher slug (OPENROUTER_DEFAULT_MODEL —
    the deepseek reasoning-first model whose structured-output 404 was the FX-01 keystone). Returns
    True iff a schema object parses; raises GateError on the NoEndpointError/404 class. Tiny schema +
    budget keep it cheap; the 404 failure path returns immediately (before any generation)."""
    import asyncio

    from pydantic import BaseModel

    from src.polaris_graph.llm.openrouter_client import NoEndpointError, OpenRouterClient

    class _CanaryProbe(BaseModel):
        ok: bool

    async def _run() -> bool:
        client = OpenRouterClient()  # OPENROUTER_DEFAULT_MODEL = the searcher/generator slug
        try:
            result = await client.generate_structured(
                prompt='Reply with JSON only: {"ok": true}.',
                schema=_CanaryProbe,
                max_tokens=128,
            )
            return result is not None
        finally:
            await client.close()

    try:
        return asyncio.run(_run())
    except NoEndpointError as exc:
        raise GateError(
            "behavioral canary: structured-output probe got NoEndpointError on the searcher/generator "
            f"slug — the FX-01-keystone 404 class that silently kills discovery. Aborting BEFORE spend. "
            f"({exc})"
        )


def _default_live_search_probe() -> int:
    """REAL primary-backend search call shape (the function the pipeline actually uses); returns the
    live result count. >0 confirms discovery produces sources (the drb_72 collapse returned ~7)."""
    from src.polaris_graph.retrieval.live_retriever import _serper_search

    return len(_serper_search("metformin efficacy in type 2 diabetes", num=3))


def behavioral_canary(
    *,
    structured_output_probe=_default_structured_output_probe,
    live_search_probe=_default_live_search_probe,
) -> None:
    """Pre-spend BEHAVIORAL canary (CANARY-01, #1108). FAIL CLOSED (GateError) unless the REAL call
    shapes the full run depends on are ALIVE — NOT a config-flag check. Prints BEHAVIORAL_CANARY_OK on
    success. Gated by PG_BEHAVIORAL_CANARY (slate-activated for the run); a no-op when off.

    Probes (the gap the drb_72 'green run on dead discovery' preflight missed):
      1. structured-output on the searcher/generator slug — the FX-01-keystone generate_structured 404
         class (the old preflight checked only the 4 VERIFIER slugs).
      2. a real 1-query primary-backend search returning >0 live results — catches the silent
         discovery-collapse.

    The probes are injectable so the canary LOGIC is unit-tested offline (faked dead/alive) without
    network; the LIVE invocation (real probes) runs pre-spend on the real Gate-B run.
    """
    if os.getenv(_BEHAVIORAL_CANARY_ENV, "0").strip().lower() not in ("1", "true"):
        return  # opt-in; off = no-op (byte-unchanged behavior)
    if not structured_output_probe():
        raise GateError(
            "behavioral canary: structured-output probe returned no parsed object on the "
            "searcher/generator slug — the structured-output path is degraded. Aborting BEFORE spend."
        )
    n_sources = live_search_probe()
    if n_sources <= 0:
        raise GateError(
            "behavioral canary: 1-query primary-backend search returned 0 live sources — discovery is "
            "degraded (the drb_72 silent-collapse: ~7 sources from '1000 URLs'). Aborting BEFORE spend."
        )
    print("BEHAVIORAL_CANARY_OK", flush=True)


@dataclass
class LLMCall:
    call_id: str
    role: str
    prompt_messages_present: bool
    request_hash: str | None
    response_metadata: dict   # served {model, provider_name, system_fingerprint, ...}


def assert_post_run(
    pin: dict,
    control_vars: list[str],
    salt: bytes,
    calls: list[LLMCall],
    retrieval_backends_attempted: set[str],
) -> dict:
    """Fatal post-run gate (Codex). Any violation ⇒ run INVALID, discard + re-run.

    Returns the established per-role served-identity surrogates on success."""
    # config no-drift — rebuild from the SAME resolved surface preflight pinned (not a
    # caller-passed list, which could differ / bypass; Codex iter-2).
    pinned_vars = pin.get("control_vars", control_vars)
    cfg_now = effective_config_hash(build_effective_config(pinned_vars, salt))
    if cfg_now != pin["effective_config_hash"]:
        raise GateError("effective_config drifted between preflight and post-run")
    pins_by_role = {rp["role"]: rp for rp in pin["role_pins"]}
    if not calls:
        raise GateError("no LLM calls captured — completeness check cannot pass")
    # COMPLETENESS: every pinned role must appear (Codex P1 — uncaptured evaluator/judge invisible)
    roles_seen = {c.role for c in calls}
    missing_roles = set(pins_by_role) - roles_seen
    if missing_roles:
        raise GateError(f"completeness: pinned role(s) with no captured LLM call: {missing_roles}")
    surrogate_by_role: dict[str, set[str]] = {}
    for c in calls:
        if not (c.prompt_messages_present and c.request_hash and c.response_metadata):
            raise GateError(f"call {c.call_id}: incomplete capture (prompt/request_hash/metadata)")
        rp = pins_by_role.get(c.role)
        if rp is None:
            raise GateError(f"call {c.call_id}: role {c.role!r} not pinned")
        # I-meta-002 PR-9/M4 self-host branch: a self-hosted vLLM verifier (Mirror / Sentinel /
        # Judge) carries NO provider_name — its served identity is the M1 `_pathb_served`
        # {endpoint, model}, which pathB_capture.build_response_metadata flattens onto the
        # captured metadata as top-level `model` + `endpoint` keys (provider_name/
        # system_fingerprint are dropped for a vLLM response). Read those flattened keys and
        # fail-closed assert served model == pinned model_slug AND served endpoint == the
        # PINNED base_url (drift-safe: PG_<ROLE>_BASE_URL is not in the config-drift hash;
        # comparing against the value pinned at preflight is what catches a wrong-box serve).
        # Missing endpoint and/or model => the `_pathb_served` block never reached capture =>
        # fatal. This branch fires BEFORE the surrogate-field / provider OpenRouter checks
        # (which would spuriously fail on a self-host call that has no provider_name).
        if _is_self_host_route(rp.get("serving_route")):
            served_model = c.response_metadata.get("model")
            served_endpoint = c.response_metadata.get("endpoint")
            if served_model is None or served_endpoint is None:
                raise GateError(
                    f"call {c.call_id}: self-host role {c.role!r} captured no served identity "
                    f"(_pathb_served endpoint/model missing): model={served_model!r} "
                    f"endpoint={served_endpoint!r}"
                )
            pinned_model = rp["model_slug"]
            if served_model != pinned_model:
                raise GateError(
                    f"call {c.call_id}: self-host role {c.role!r} served model {served_model!r} "
                    f"!= pinned model_slug {pinned_model!r}"
                )
            pinned_base_url = (rp.get("base_url") or "")
            if pinned_base_url.rstrip("/") != served_endpoint.rstrip("/"):
                raise GateError(
                    f"call {c.call_id}: self-host role {c.role!r} served endpoint "
                    f"{served_endpoint!r} != pinned base_url {rp.get('base_url')!r}"
                )
            surrogate_by_role.setdefault(c.role, set()).add(
                _self_host_endpoint_surrogate(served_model, served_endpoint.rstrip("/"))
            )
            continue
        for fld in rp["surrogate_fields"]:
            if fld not in c.response_metadata:
                raise GateError(f"call {c.call_id}: served metadata missing surrogate field {fld!r}")
        # EXACT provider + EXACT full-slug model match (Codex P1 — no loose substring).
        # I-bug-944 (#925 smoke #13): provider comparison is case-insensitive (OpenRouter
        # returns "Fireworks" / "DeepInfra" with title case while the pin env var
        # OPENROUTER_PROVIDER_ORDER is documented lower-case; case-mismatch is identity-
        # equivalent and must not gate-fail an otherwise full-power run). Model slug stays
        # case-sensitive — slugs are canonical.
        served_provider = (c.response_metadata.get("provider_name") or "").strip().lower()
        pinned_provider = (rp["provider_name"] or "").strip().lower()
        if served_provider != pinned_provider:
            raise GateError(f"call {c.call_id}: served provider {c.response_metadata.get('provider_name')!r} != pinned {rp['provider_name']!r}")
        # I-bug-945 (#931): accept served model matching EITHER the pinned alias OR the
        # canonical_slug resolved at preflight. The OpenRouter chat-completions response
        # returns `model=<canonical_slug>` while the env pin is the alias; both are identity-
        # equivalent and recorded in the persisted pin (pathB_gate_pin.json).
        served_model = c.response_metadata.get("model")
        accepted_models = {rp["model_slug"]}
        if rp.get("canonical_slug"):
            accepted_models.add(rp["canonical_slug"])
        if served_model not in accepted_models:
            raise GateError(
                f"call {c.call_id}: served model {served_model!r} matches neither pinned "
                f"alias {rp['model_slug']!r} nor canonical_slug {rp.get('canonical_slug')!r}"
            )
        # I-bug-945 P2#4 (Codex): normalize served `model` to the alias before surrogate
        # compute, so a same-role mix of alias and canonical_slug calls produces a single
        # surrogate value (otherwise raw-model drift would false-fail the mid-run check).
        normalized_metadata = dict(c.response_metadata)
        normalized_metadata["model"] = rp["model_slug"]
        surrogate_by_role.setdefault(c.role, set()).add(_role_surrogate(normalized_metadata, rp["surrogate_fields"]))
    # per-role served identity must be SINGLE-VALUED across the run (no mid-run drift, Codex P1)
    for role, ids in surrogate_by_role.items():
        if len(ids) != 1:
            raise GateError(f"role {role}: served-identity surrogate drifted across calls ({len(ids)} distinct)")
    # required retrieval backends were ACTUALLY attempted (Codex iter-5 P2)
    required = set(_REQUIRED_RETRIEVAL_CREDS_TO_BACKENDS.values())
    not_attempted = required - retrieval_backends_attempted
    if not_attempted:
        raise GateError(f"required retrieval backends never attempted this run: {not_attempted}")
    return {"served_identity_by_role": {r: next(iter(ids)) for r, ids in surrogate_by_role.items()}}


_REQUIRED_RETRIEVAL_CREDS_TO_BACKENDS = {
    "SERPER_API_KEY": "serper",
    "SEMANTIC_SCHOLAR_API_KEY": "semantic_scholar",
}
