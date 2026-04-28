"""M-D11 (Phase D): Model + version pinning.

Per FINAL_PLAN M-D11: every audit bundle records exact model
versions, prompt versions, retrieval-source versions, plus
inductor type + version (Phase D specific) AND environment
toggles that affect routing/prompt selection. Re-run-from-pin
capability lets a future operator reproduce a historical run.

This module ships **phase 1 — pin capture and serialization**.
Phase 2 (replay: load pin → configure pipeline to match → run)
is a separate module that depends on this one being stable.

## Schema version

`PIN_SCHEMA_VERSION = "v3"`. Every pin carries this version
explicitly. `pin_from_dict` rejects mismatched versions loudly
so future schema changes don't silently misload historical pins.

## Pin shape (v3)

ModelPin captures:
  - run_id: the run this pin was captured from
  - captured_at: unix timestamp
  - pin_schema_version: "v2" (explicit forward-compat marker)
  - llm_models: {role: model_id} — e.g. {"generator": "z-ai/glm-5.1",
    "evaluator": "qwen/qwen3.5-plus", "judge": "...", "inductor": "..."}.
    The current honest_pipeline + audit_ir loader carry distinct
    generator/evaluator/judge models; phase 2 needs all of them
    to rehydrate.
  - llm_providers: {role: provider} — auto-filled with "openrouter"
    for each role unless overridden.
  - prompt_version_hashes: {role: SHA-256 hex} — empty for roles
    without a captured system prompt (allowed, since some roles
    may use the model's default prompt).
  - retrieval_source_versions: dict of {source: version}
    (e.g. {"crossref": "v1", "pubmed": "2024-12", "unpaywall": "v2"})
  - inductor_type: which auto-induction inductor was active
    (e.g. "KeywordInductor v5" or "LLMAugmentedInductor")
  - inductor_version_hash: hash of the inductor's keyword profile
    or LLM classifier prompt — captures structural changes that
    would alter routing behavior
  - validation_set_hash: hash of the M-D1 validation set file
    if the run involved induction
  - env_snapshot: {var_name: value} captured environment toggles
    that affect routing, prompt selection, verification gates, AND
    LLM call profile (token budgets). Empty string for unset vars
    so the snapshot shape is stable. See
    `DEFAULT_REPLAY_ENV_VARS` for the recommended capture set
    (verified against actual `os.getenv` call sites in
    `docs/pipeline_audit_context/08_env_var_inventory.md`).
  - notes: free-form operator context (excluded from replay
    equivalence)

The pin is JSON-serializable and round-trips cleanly. Re-run-
from-pin (M-D11 phase 2) loads this and configures the pipeline.

## Why pin separately from M-16 audit bundle

M-16's audit bundle captures evidence + claims + provenance —
the WHAT of an audit. M-D11 captures the HOW: the
configuration of generators, retrievers, inductors, and the
runtime environment that influenced their behavior. This split
matters for Phase D governance (M-D9 regression lab) which
diffs pin-to-pin to spot configuration drift independent of
content drift.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Iterable
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


PIN_SCHEMA_VERSION = "v3"


# Environment variables that influence routing, prompt selection,
# verification gates, OR LLM call profile (token budgets) in the
# current honest_pipeline + openrouter_client + synthesis stack.
# Capturing these at run time makes pins truly replay-safe: two
# pins with identical model ids but divergent env are NOT
# replay-equivalent.
#
# Names verified against actual `os.getenv` call sites — see
# `docs/pipeline_audit_context/08_env_var_inventory.md`. Per
# Codex round-2 review (commit 472b865), the set must include
# call-profile knobs (max_tokens) since they materially change
# generated outputs even when the prompt + model are identical.
DEFAULT_REPLAY_ENV_VARS: tuple[str, ...] = (
    # OpenRouter routing
    "OPENROUTER_BASE_URL",
    "OPENROUTER_DEFAULT_MODEL",
    "OPENROUTER_PROVIDER_ORDER",
    "OPENROUTER_ALLOW_FALLBACKS",
    "OPENROUTER_REQUIRE_PARAMETERS",
    "OPENROUTER_PROVIDER_REQUIRE_PARAMETERS",
    # Synthesis prompt mode + structural feature toggles
    "PG_V3_ANALYTICAL_PROMPT",
    "PG_V3_DEPTH_GATE",
    "PG_V3_SURFACE_ANALYSIS",
    "PG_V3_COMPARISON_TABLES",
    "PG_PHASE_5_ENABLED",
    "POLARIS_CITEFIRST_ENABLED",
    # Verification gates (provenance + NLI faithfulness)
    "PG_PROVENANCE_MIN_CONTENT_OVERLAP",
    "PG_NLI_ENABLED",
    "PG_NLI_THRESHOLD",
    "PG_NLI_DISPUTE_THRESHOLD",
    "PG_NLI_CONTEXT_WINDOW",
    "PG_NLI_DOMAIN_ADAPTIVE",
    "PG_NLI_DOMAIN_FLOOR",
    "PG_FAITHFULNESS_NLI_THRESHOLD",
    # LLM call profile — token budgets that change outputs even
    # with identical model + prompt
    "PG_SECTION_WRITER_MAX_TOKENS",
    "PG_SECTION_CONTINUATION_MAX_TOKENS",
    "PG_GLM5_MIN_MAX_TOKENS",
)


# Backward-compat alias. Older callers may import
# `DEFAULT_ROUTING_ENV_VARS`; the name was narrowed in v3 to
# `DEFAULT_REPLAY_ENV_VARS` (broader scope: routing + gates +
# call profile). Keep alias so internal callers don't break.
DEFAULT_ROUTING_ENV_VARS: tuple[str, ...] = DEFAULT_REPLAY_ENV_VARS


@dataclass(frozen=True)
class ModelPin:
    """One audit run's model + version + configuration pin.

    Frozen because pin records are immutable once written —
    replaying a run requires the pin's exact bit-pattern at
    capture time. Mutating in place would lose reproducibility.
    """

    run_id: str
    captured_at: float
    pin_schema_version: str = PIN_SCHEMA_VERSION
    llm_models: dict[str, str] = field(default_factory=dict)
    llm_providers: dict[str, str] = field(default_factory=dict)
    prompt_version_hashes: dict[str, str] = field(default_factory=dict)
    retrieval_source_versions: dict[str, str] = field(default_factory=dict)
    inductor_type: str | None = None
    inductor_version_hash: str | None = None
    validation_set_hash: str | None = None
    env_snapshot: dict[str, str] = field(default_factory=dict)
    # Free-form notes for operator context — not used by replay,
    # only for human readability.
    notes: str = ""


class ModelPinError(ValueError):
    """Raised on malformed pin schema / serialization issues."""


def _hash_text(text: str) -> str:
    """SHA-256 hex digest of UTF-8-encoded text. Used for prompt
    hashes + inductor version hashes."""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def hash_file(path: Path | str) -> str:
    """SHA-256 of a file. Used for validation_set_hash and any
    other content-addressable artifact pin."""
    p = Path(path)
    if not p.exists():
        raise ModelPinError(f"file does not exist: {p}")
    h = hashlib.sha256()
    with p.open("rb") as fp:
        for chunk in iter(lambda: fp.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def hash_inductor_profile(profile_text: str) -> str:
    """Hash an inductor's keyword profile / system prompt /
    config text. Any structural change that would alter routing
    decisions changes the hash."""
    return _hash_text(profile_text)


def capture_env_snapshot(
    names: Iterable[str] = DEFAULT_REPLAY_ENV_VARS,
) -> dict[str, str]:
    """Capture current values of named environment variables.

    Missing variables are recorded as empty string so the
    snapshot has stable shape across runs (a missing var and a
    var set to "" are treated the same — neither overrides
    routing in the current stack).
    """
    snapshot: dict[str, str] = {}
    for name in names:
        if not isinstance(name, str) or not name.strip():
            raise ModelPinError(
                "env var names must be non-empty strings"
            )
        snapshot[name.strip()] = os.environ.get(name.strip(), "")
    return snapshot


def _validate_role_dict(
    field_name: str,
    data: Any,
    *,
    require_non_empty: bool = True,
) -> dict[str, str]:
    """Validate a role-keyed dict: keys+values are non-empty
    strings. Returns a normalized (stripped-key/value) dict."""
    if not isinstance(data, dict):
        raise ModelPinError(
            f"{field_name} must be a dict, got {type(data).__name__}"
        )
    if require_non_empty and not data:
        raise ModelPinError(f"{field_name} must be non-empty")
    out: dict[str, str] = {}
    for role, value in data.items():
        if not isinstance(role, str) or not role.strip():
            raise ModelPinError(
                f"{field_name} role keys must be non-empty strings"
            )
        if not isinstance(value, str) or not value.strip():
            raise ModelPinError(
                f"{field_name}[{role!r}] must be non-empty string"
            )
        out[role.strip()] = value.strip()
    return out


def _validate_retrieval_source_versions(data: Any) -> dict[str, str]:
    """Validate retrieval_source_versions: dict of str→str. Empty
    dict is allowed (no retrieval sources)."""
    if not isinstance(data, dict):
        raise ModelPinError(
            f"retrieval_source_versions must be a dict, "
            f"got {type(data).__name__}"
        )
    out: dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(k, str) or not k.strip():
            raise ModelPinError(
                "retrieval_source_versions keys must be non-empty strings"
            )
        if not isinstance(v, str):
            raise ModelPinError(
                f"retrieval_source_versions[{k!r}] must be string, "
                f"got {type(v).__name__}"
            )
        out[k] = v
    return out


def _validate_env_snapshot(data: Any) -> dict[str, str]:
    """Validate env_snapshot shape: str→str (None values become
    "")."""
    if not isinstance(data, dict):
        raise ModelPinError(
            f"env_snapshot must be a dict, got {type(data).__name__}"
        )
    out: dict[str, str] = {}
    for k, v in data.items():
        if not isinstance(k, str) or not k.strip():
            raise ModelPinError(
                "env_snapshot keys must be non-empty strings"
            )
        if v is None:
            out[k.strip()] = ""
        elif isinstance(v, str):
            out[k.strip()] = v
        else:
            raise ModelPinError(
                f"env_snapshot[{k!r}] must be string or None"
            )
    return out


def capture_pin(
    *,
    run_id: str,
    llm_models: dict[str, str],
    llm_providers: dict[str, str] | None = None,
    role_prompts: dict[str, str] | None = None,
    retrieval_source_versions: dict[str, str] | None = None,
    inductor_type: str | None = None,
    inductor_profile_text: str | None = None,
    validation_set_path: Path | str | None = None,
    env_snapshot: dict[str, str] | None = None,
    capture_env_var_names: Iterable[str] | None = None,
    notes: str = "",
    captured_at: float | None = None,
) -> ModelPin:
    """Capture a ModelPin from the current runtime configuration.

    `llm_models` is a {role: model_id} dict — at minimum one role
    (typically "generator") must be set. The honest_pipeline
    today separates generator/evaluator/judge/inductor; pass each
    one's model id under the corresponding role key.

    Hashes are computed lazily — pass `role_prompts` text and let
    this function hash it, rather than passing pre-computed
    hashes. That way the pin captures the actual prompt text
    rather than trusting the caller's hash.

    `env_snapshot` and `capture_env_var_names` are mutually
    exclusive: pass `env_snapshot` to provide a pre-captured
    snapshot, or `capture_env_var_names` to capture now from
    `os.environ`. If neither is passed, env_snapshot is empty.
    """
    if not run_id.strip():
        raise ModelPinError("run_id must be non-empty")

    models = _validate_role_dict("llm_models", llm_models)

    providers_in = (
        _validate_role_dict(
            "llm_providers", llm_providers, require_non_empty=False
        )
        if llm_providers is not None
        else {}
    )
    unknown_provider_roles = set(providers_in) - set(models)
    if unknown_provider_roles:
        raise ModelPinError(
            f"llm_providers has unknown roles "
            f"(not in llm_models): {sorted(unknown_provider_roles)}"
        )
    providers = dict(providers_in)
    for role in models:
        providers.setdefault(role, "openrouter")

    prompt_hashes: dict[str, str] = {}
    if role_prompts is not None:
        prompts_validated = _validate_role_dict(
            "role_prompts", role_prompts, require_non_empty=False
        )
        unknown_prompt_roles = set(prompts_validated) - set(models)
        if unknown_prompt_roles:
            raise ModelPinError(
                f"role_prompts has unknown roles "
                f"(not in llm_models): {sorted(unknown_prompt_roles)}"
            )
        for role, text in prompts_validated.items():
            prompt_hashes[role] = _hash_text(text)

    inductor_hash = (
        hash_inductor_profile(inductor_profile_text)
        if inductor_profile_text is not None
        else None
    )
    vs_hash = (
        hash_file(validation_set_path)
        if validation_set_path is not None
        else None
    )

    if env_snapshot is not None and capture_env_var_names is not None:
        raise ModelPinError(
            "pass env_snapshot or capture_env_var_names, not both"
        )
    if env_snapshot is not None:
        env_final = _validate_env_snapshot(env_snapshot)
    elif capture_env_var_names is not None:
        env_final = capture_env_snapshot(capture_env_var_names)
    else:
        env_final = {}

    retrieval_validated = _validate_retrieval_source_versions(
        retrieval_source_versions or {}
    )

    return ModelPin(
        run_id=run_id.strip(),
        captured_at=captured_at if captured_at is not None else time.time(),
        pin_schema_version=PIN_SCHEMA_VERSION,
        llm_models=models,
        llm_providers=providers,
        prompt_version_hashes=prompt_hashes,
        retrieval_source_versions=retrieval_validated,
        inductor_type=inductor_type,
        inductor_version_hash=inductor_hash,
        validation_set_hash=vs_hash,
        env_snapshot=env_final,
        notes=notes,
    )


def pin_to_dict(pin: ModelPin) -> dict[str, Any]:
    """JSON-safe dict representation."""
    return asdict(pin)


def pin_to_json(pin: ModelPin, *, indent: int = 2) -> str:
    """Serialize a pin to JSON with stable key ordering."""
    return json.dumps(pin_to_dict(pin), indent=indent, sort_keys=True)


def pin_from_dict(data: dict[str, Any]) -> ModelPin:
    """Reconstruct a ModelPin from its dict form, re-applying
    every invariant that capture_pin enforces.

    This is symmetric with capture_pin: a malformed dict must NOT
    produce a ModelPin that compares/serializes as if it were
    valid. Empty role dicts, missing required keys, and schema-
    version mismatches all raise ModelPinError.
    """
    if not isinstance(data, dict):
        raise ModelPinError(
            f"pin data must be a dict; got {type(data).__name__}"
        )

    schema_version = data.get("pin_schema_version")
    if schema_version != PIN_SCHEMA_VERSION:
        raise ModelPinError(
            f"pin_schema_version mismatch: got {schema_version!r}, "
            f"expected {PIN_SCHEMA_VERSION!r}"
        )

    required = ("run_id", "captured_at", "llm_models")
    for key in required:
        if key not in data:
            raise ModelPinError(f"pin data missing required key: {key!r}")

    try:
        run_id_raw = data["run_id"]
        if not isinstance(run_id_raw, str) or not run_id_raw.strip():
            raise ModelPinError("run_id must be non-empty string")
        run_id = run_id_raw.strip()

        captured_at = float(data["captured_at"])

        llm_models = _validate_role_dict("llm_models", data["llm_models"])

        providers_raw = data.get("llm_providers", {}) or {}
        llm_providers = _validate_role_dict(
            "llm_providers", providers_raw, require_non_empty=False
        )
        unknown_p = set(llm_providers) - set(llm_models)
        if unknown_p:
            raise ModelPinError(
                f"llm_providers has unknown roles: {sorted(unknown_p)}"
            )
        missing_p = set(llm_models) - set(llm_providers)
        if missing_p:
            raise ModelPinError(
                f"llm_providers missing roles "
                f"(every model role needs a provider): {sorted(missing_p)}"
            )

        prompts_raw = data.get("prompt_version_hashes", {}) or {}
        prompt_version_hashes = _validate_role_dict(
            "prompt_version_hashes", prompts_raw, require_non_empty=False
        )
        unknown_h = set(prompt_version_hashes) - set(llm_models)
        if unknown_h:
            raise ModelPinError(
                f"prompt_version_hashes has unknown roles: {sorted(unknown_h)}"
            )

        retrieval = _validate_retrieval_source_versions(
            data.get("retrieval_source_versions") or {}
        )

        env_raw = data.get("env_snapshot", {}) or {}
        env_snapshot = _validate_env_snapshot(env_raw)

        return ModelPin(
            run_id=run_id,
            captured_at=captured_at,
            pin_schema_version=str(schema_version),
            llm_models=llm_models,
            llm_providers=llm_providers,
            prompt_version_hashes=prompt_version_hashes,
            retrieval_source_versions=retrieval,
            inductor_type=(
                str(data["inductor_type"])
                if data.get("inductor_type") is not None
                else None
            ),
            inductor_version_hash=(
                str(data["inductor_version_hash"])
                if data.get("inductor_version_hash") is not None
                else None
            ),
            validation_set_hash=(
                str(data["validation_set_hash"])
                if data.get("validation_set_hash") is not None
                else None
            ),
            env_snapshot=env_snapshot,
            notes=str(data.get("notes", "")),
        )
    except ModelPinError:
        raise
    except (TypeError, ValueError) as exc:
        raise ModelPinError(f"pin data schema violation: {exc}") from exc


def pin_from_json(text: str) -> ModelPin:
    """Parse + validate JSON pin."""
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ModelPinError(f"pin JSON decode failed: {exc}") from exc
    return pin_from_dict(data)


def pins_equivalent_for_replay(a: ModelPin, b: ModelPin) -> bool:
    """Two pins are replay-equivalent if all configuration-
    affecting fields match. `run_id`, `captured_at`, and `notes`
    are excluded — they're metadata, not configuration. This is
    the function M-D11 phase 2 (replay) uses to decide whether a
    new run reproduces a historical pin's exact configuration.

    Note: `pin_schema_version` IS compared — different schema
    versions are not replay-equivalent (they encode different
    sets of fields).
    """
    return (
        a.pin_schema_version == b.pin_schema_version
        and a.llm_models == b.llm_models
        and a.llm_providers == b.llm_providers
        and a.prompt_version_hashes == b.prompt_version_hashes
        and a.retrieval_source_versions == b.retrieval_source_versions
        and a.inductor_type == b.inductor_type
        and a.inductor_version_hash == b.inductor_version_hash
        and a.validation_set_hash == b.validation_set_hash
        and a.env_snapshot == b.env_snapshot
    )
