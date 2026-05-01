"""CAN_REAL data redaction for OTEL spans + structured logs.

Per CLAUDE.md security posture, `CAN_REAL` data MUST NOT cross to non-
Canadian observability infrastructure. Token counts, latencies, model
ids are always emittable (no PII); prompt + completion content for
CAN_REAL data is replaced with sha256 hash + length only.

This module provides the scrubbing primitives. Phase 2A wires them into
the OTEL span pipeline; Phase 1 ships the substrate + tests.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any, Literal

DataClassification = Literal[
    "PUBLIC_SYNTHETIC",
    "CAN_REAL",
    "PRIVATE",
    "CLIENT",
    "UNKNOWN",
]

REDACT_KINDS: set[DataClassification] = {"CAN_REAL", "PRIVATE", "CLIENT"}

_SENSITIVE_KEY_RE = re.compile(
    r"^(gen_ai\.prompt|gen_ai\.completion|polaris\.span_text|polaris\.user_input|polaris\.evidence_text|password|secret|api[_-]?key|token)$",
    re.IGNORECASE,
)


def _hash_with_length(text: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
    return f"sha256:{digest}:len={len(text)}"


def redact_attributes(
    attributes: dict[str, Any],
    *,
    classification: DataClassification = "UNKNOWN",
) -> dict[str, Any]:
    """Return a new dict with sensitive content redacted to hash+length.

    Pass-through fields (always emitted unchanged):
    - gen_ai.usage.* (token counts)
    - gen_ai.request.model, gen_ai.response.model
    - gen_ai.response.finish_reasons
    - polaris.cost_usd, polaris.run_id, polaris.template
    - any non-sensitive key

    Redacted fields when classification ∈ REDACT_KINDS:
    - gen_ai.prompt, gen_ai.completion, polaris.span_text,
      polaris.user_input, polaris.evidence_text, password, secret,
      api_key/api-key, token
    """
    if classification not in REDACT_KINDS:
        return dict(attributes)

    out: dict[str, Any] = {}
    for k, v in attributes.items():
        if _SENSITIVE_KEY_RE.match(k):
            if isinstance(v, str):
                out[k] = _hash_with_length(v)
            elif isinstance(v, list):
                out[k] = [
                    _hash_with_length(item) if isinstance(item, str) else "[redacted]"
                    for item in v
                ]
            else:
                out[k] = "[redacted]"
        else:
            out[k] = v
    out["polaris.classification"] = classification
    out["polaris.redaction_applied"] = True
    return out


def redact_for_log(message: str, classification: DataClassification = "UNKNOWN") -> str:
    """Redact a free-text log message when classification requires it."""
    if classification not in REDACT_KINDS:
        return message
    return _hash_with_length(message)


def set_span_attributes_safe(
    span: Any,
    attributes: dict[str, Any],
    *,
    classification: DataClassification = "UNKNOWN",
) -> None:
    """Apply redact_attributes then set on an OTEL span.

    Caller-side helper — the intended replacement for direct
    `span.set_attribute(k, v)` calls when emitting spans that may carry
    CAN_REAL / PRIVATE / CLIENT data. The opentelemetry SDK is duck-
    typed (anything with `.set_attribute(name, value)`).

    A None span is a no-op (safe in environments where OTEL is disabled).
    A per-attribute exception does not cascade through the span.
    """
    if span is None:
        return
    redacted = redact_attributes(attributes, classification=classification)
    set_attribute = getattr(span, "set_attribute", None)
    if set_attribute is None:
        return
    for k, v in redacted.items():
        try:
            set_attribute(k, v)
        except Exception:
            continue
