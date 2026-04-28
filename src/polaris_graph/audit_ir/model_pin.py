"""M-D11 (Phase D): Model + version pinning.

Per FINAL_PLAN M-D11: every audit bundle records exact model
versions, prompt versions, retrieval-source versions, plus
inductor type + version (Phase D specific). Re-run-from-pin
capability lets a future operator reproduce a historical run.

This module ships **phase 1 — pin capture and serialization**.
Phase 2 (replay: load pin → configure pipeline to match → run)
is a separate module that depends on this one being stable.

## Pin shape

ModelPin captures:
  - run_id: the run this pin was captured from
  - captured_at: unix timestamp
  - llm_model: OpenRouter model identifier (e.g. "qwen/qwen3.5-plus-02-15")
  - llm_provider: where the model was served (openrouter / direct)
  - prompt_version: hash of the system prompt(s) used
  - retrieval_source_versions: dict of {source: version}
    (e.g. {"crossref": "v1", "pubmed": "2024-12", "unpaywall": "v2"})
  - inductor_type: which auto-induction inductor was active
    (e.g. "KeywordInductor v5" or "LLMAugmentedInductor")
  - inductor_version_hash: hash of the inductor's keyword profile
    or LLM classifier prompt — captures structural changes that
    would alter routing behavior
  - validation_set_hash: hash of the M-D1 validation set file
    if the run involved induction

The pin is JSON-serializable and round-trips cleanly. Re-run-
from-pin (M-D11 phase 2) loads this and configures the pipeline.

## Why pin separately from M-16 audit bundle

M-16's audit bundle captures evidence + claims + provenance —
the WHAT of an audit. M-D11 captures the HOW: the
configuration of generators, retrievers, inductors. This split
matters for Phase D governance (M-D9 regression lab) which
diffs pin-to-pin to spot configuration drift independent of
content drift.
"""

from __future__ import annotations

import hashlib
import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ModelPin:
    """One audit run's model + version + configuration pin.

    Frozen because pin records are immutable once written —
    replaying a run requires the pin's exact bit-pattern at
    capture time. Mutating in place would lose reproducibility.
    """

    run_id: str
    captured_at: float
    llm_model: str
    llm_provider: str = "openrouter"
    prompt_version_hash: str = ""
    retrieval_source_versions: dict[str, str] = field(default_factory=dict)
    inductor_type: str | None = None
    inductor_version_hash: str | None = None
    validation_set_hash: str | None = None
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


def capture_pin(
    *,
    run_id: str,
    llm_model: str,
    llm_provider: str = "openrouter",
    system_prompt: str | None = None,
    retrieval_source_versions: dict[str, str] | None = None,
    inductor_type: str | None = None,
    inductor_profile_text: str | None = None,
    validation_set_path: Path | str | None = None,
    notes: str = "",
    captured_at: float | None = None,
) -> ModelPin:
    """Capture a ModelPin from the current runtime configuration.

    Hashes are computed lazily — pass `system_prompt` text and
    let this function hash it, rather than passing a pre-computed
    hash. That way the pin captures the actual prompt text
    rather than trusting the caller's hash.
    """
    if not run_id.strip():
        raise ModelPinError("run_id must be non-empty")
    if not llm_model.strip():
        raise ModelPinError("llm_model must be non-empty")

    prompt_hash = _hash_text(system_prompt) if system_prompt else ""
    inductor_hash = (
        hash_inductor_profile(inductor_profile_text)
        if inductor_profile_text
        else None
    )
    vs_hash = (
        hash_file(validation_set_path)
        if validation_set_path is not None
        else None
    )
    return ModelPin(
        run_id=run_id.strip(),
        captured_at=captured_at if captured_at is not None else time.time(),
        llm_model=llm_model.strip(),
        llm_provider=llm_provider.strip(),
        prompt_version_hash=prompt_hash,
        retrieval_source_versions=dict(retrieval_source_versions or {}),
        inductor_type=inductor_type,
        inductor_version_hash=inductor_hash,
        validation_set_hash=vs_hash,
        notes=notes,
    )


def pin_to_dict(pin: ModelPin) -> dict[str, Any]:
    """JSON-safe dict representation."""
    return asdict(pin)


def pin_to_json(pin: ModelPin, *, indent: int = 2) -> str:
    """Serialize a pin to JSON with stable key ordering."""
    return json.dumps(pin_to_dict(pin), indent=indent, sort_keys=True)


def pin_from_dict(data: dict[str, Any]) -> ModelPin:
    """Reconstruct a ModelPin from its dict form. Raises
    ModelPinError on schema violations."""
    if not isinstance(data, dict):
        raise ModelPinError(
            f"pin data must be a dict; got {type(data).__name__}"
        )
    required = ("run_id", "captured_at", "llm_model")
    for key in required:
        if key not in data:
            raise ModelPinError(f"pin data missing required key: {key!r}")
    try:
        return ModelPin(
            run_id=str(data["run_id"]),
            captured_at=float(data["captured_at"]),
            llm_model=str(data["llm_model"]),
            llm_provider=str(data.get("llm_provider", "openrouter")),
            prompt_version_hash=str(data.get("prompt_version_hash", "")),
            retrieval_source_versions=dict(
                data.get("retrieval_source_versions") or {}
            ),
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
            notes=str(data.get("notes", "")),
        )
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
    """
    return (
        a.llm_model == b.llm_model
        and a.llm_provider == b.llm_provider
        and a.prompt_version_hash == b.prompt_version_hash
        and a.retrieval_source_versions == b.retrieval_source_versions
        and a.inductor_type == b.inductor_type
        and a.inductor_version_hash == b.inductor_version_hash
        and a.validation_set_hash == b.validation_set_hash
    )
