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
    pat = re.compile(
        r"os\.(?:getenv|environ\.get)\(\s*['\"]((?:PG_|OPENROUTER_)[A-Z0-9_]+)['\"]"
        r"|os\.environ\[\s*['\"]((?:PG_|OPENROUTER_)[A-Z0-9_]+)['\"]"
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
    role: str            # "generator" | "evaluator"
    model_slug: str      # FULL OpenRouter slug, e.g. "deepseek/deepseek-v4-pro" — EXACT match
    provider_name: str
    surrogate_fields: tuple[str, ...]   # the metadata fields PROVEN present at preflight


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
) -> dict:
    """Fatal preflight. Returns the pin record to hash-pin BEFORE the run.

    `reachability_prober(backend) -> bool` actually pings each required retrieval backend
    (Codex P1: presence != reachability; an invalid/rate-limited key must FAIL preflight).
    Injectable so fixtures don't hit the network.
    """
    # 1. fallbacks OFF
    if os.environ.get("OPENROUTER_ALLOW_FALLBACKS", "true").strip().lower() not in ("false", "0", "no"):
        raise GateError("OPENROUTER_ALLOW_FALLBACKS must be false (it defaults TRUE)")
    # 2. singleton provider routing (served backend known a priori)
    order = (os.environ.get("OPENROUTER_PROVIDER_ORDER") or "").strip()
    if not order or len([p for p in order.split(",") if p.strip()]) != 1:
        raise GateError("OPENROUTER_PROVIDER_ORDER must pin exactly ONE provider (singleton routing)")
    # 3. required retrieval capability — PRESENCE *and* REACHABILITY (Codex P1)
    missing = [c for c in _REQUIRED_RETRIEVAL_CREDS if not os.environ.get(c)]
    if missing:
        raise GateError(f"required retrieval credentials absent — not full-power: {missing}")
    if reachability_prober is not None:
        for cred, backend in _REQUIRED_RETRIEVAL_CREDS_TO_BACKENDS.items():
            if not reachability_prober(backend):
                raise GateError(f"retrieval backend {backend!r} unreachable/invalid-key — not full-power")
    # 4. each role pin must declare which surrogate fields it PROVED present + a full slug
    for rp in role_pins:
        if not rp.surrogate_fields:
            raise GateError(f"role {rp.role}: no served-identity surrogate fields proven present")
        if "/" not in rp.model_slug:
            raise GateError(f"role {rp.role}: model_slug must be the FULL slug (provider/model), got {rp.model_slug!r}")
    cfg = build_effective_config(control_vars, salt)
    return {
        "effective_config": cfg,
        "effective_config_hash": effective_config_hash(cfg),
        "control_source_map": source_map or {},   # name -> [file:line, ...] provenance (Codex P2)
        "role_pins": [vars(rp) | {"surrogate_fields": list(rp.surrogate_fields)} for rp in role_pins],
        "reachability_checked": reachability_prober is not None,
        "openrouter_allow_fallbacks": False,
        "openrouter_provider_order": order,
    }


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
) -> None:
    """Fatal post-run gate (Codex). Any violation ⇒ run INVALID, discard + re-run."""
    # config no-drift
    cfg_now = effective_config_hash(build_effective_config(control_vars, salt))
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
        for fld in rp["surrogate_fields"]:
            if fld not in c.response_metadata:
                raise GateError(f"call {c.call_id}: served metadata missing surrogate field {fld!r}")
        # EXACT provider + EXACT full-slug model match (Codex P1 — no loose substring)
        if c.response_metadata.get("provider_name") != rp["provider_name"]:
            raise GateError(f"call {c.call_id}: served provider {c.response_metadata.get('provider_name')!r} != pinned {rp['provider_name']!r}")
        if c.response_metadata.get("model") != rp["model_slug"]:
            raise GateError(f"call {c.call_id}: served model {c.response_metadata.get('model')!r} != pinned {rp['model_slug']!r}")
        # accumulate the per-role served-identity surrogate (over the pinned fields)
        surrogate_by_role.setdefault(c.role, set()).add(_role_surrogate(c.response_metadata, rp["surrogate_fields"]))
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
