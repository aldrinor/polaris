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
    model_slug: str
    provider_name: str
    surrogate_fields: tuple[str, ...]   # the metadata fields PROVEN present at preflight


def preflight(control_vars: list[str], role_pins: list[RolePin], salt: bytes) -> dict:
    """Fatal preflight. Returns the pin record to hash-pin BEFORE the run."""
    # 1. fallbacks OFF
    if os.environ.get("OPENROUTER_ALLOW_FALLBACKS", "true").strip().lower() not in ("false", "0", "no"):
        raise GateError("OPENROUTER_ALLOW_FALLBACKS must be false (it defaults TRUE)")
    # 2. singleton provider routing (served backend known a priori)
    order = (os.environ.get("OPENROUTER_PROVIDER_ORDER") or "").strip()
    if not order or len([p for p in order.split(",") if p.strip()]) != 1:
        raise GateError("OPENROUTER_PROVIDER_ORDER must pin exactly ONE provider (singleton routing)")
    # 3. required retrieval capability (else "full power" silently degrades — Codex P1)
    missing = [c for c in _REQUIRED_RETRIEVAL_CREDS if not os.environ.get(c)]
    if missing:
        raise GateError(f"required retrieval credentials absent — not full-power: {missing}")
    # 4. each role pin must declare which surrogate fields it PROVED present
    for rp in role_pins:
        if not rp.surrogate_fields:
            raise GateError(f"role {rp.role}: no served-identity surrogate fields proven present")
    cfg = build_effective_config(control_vars, salt)
    return {
        "effective_config": cfg,
        "effective_config_hash": effective_config_hash(cfg),
        "role_pins": [vars(rp) | {"surrogate_fields": list(rp.surrogate_fields)} for rp in role_pins],
        "openrouter_allow_fallbacks": False,
        "openrouter_provider_order": order,
    }


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
    # per-call completeness + per-role served-identity match (Codex P1/P2)
    pins_by_role = {rp["role"]: rp for rp in pin["role_pins"]}
    if not calls:
        raise GateError("no LLM calls captured — completeness check cannot pass")
    for c in calls:
        if not (c.prompt_messages_present and c.request_hash and c.response_metadata):
            raise GateError(f"call {c.call_id}: incomplete capture (prompt/request_hash/metadata)")
        rp = pins_by_role.get(c.role)
        if rp is None:
            raise GateError(f"call {c.call_id}: role {c.role!r} not pinned")
        for fld in rp["surrogate_fields"]:
            if fld not in c.response_metadata:
                raise GateError(f"call {c.call_id}: served metadata missing surrogate field {fld!r}")
        # served identity must match what the pin proved at preflight for the role
        if c.response_metadata.get("provider_name") != rp["provider_name"]:
            raise GateError(f"call {c.call_id}: served provider != pinned ({rp['provider_name']})")
        if c.response_metadata.get("model") not in (rp["model_slug"], None) and rp["model_slug"] not in str(c.response_metadata.get("model", "")):
            raise GateError(f"call {c.call_id}: served model != pinned ({rp['model_slug']})")
    # required retrieval backends were ACTUALLY attempted (Codex iter-5 P2)
    required = set(_REQUIRED_RETRIEVAL_CREDS_TO_BACKENDS.values())
    not_attempted = required - retrieval_backends_attempted
    if not_attempted:
        raise GateError(f"required retrieval backends never attempted this run: {not_attempted}")


_REQUIRED_RETRIEVAL_CREDS_TO_BACKENDS = {
    "SERPER_API_KEY": "serper",
    "SEMANTIC_SCHOLAR_API_KEY": "semantic_scholar",
}
