"""Centralized secret redaction — defense-in-depth for diagnostic OUTPUT only.

The S4 threat model established that POLARIS does NOT log secret values today: API
keys and tokens are read from ``os.environ`` and passed straight into HTTP headers or
subprocess ``env=`` mappings; no code path serializes, ``repr``\\ s, or logs a config
object that carries a secret, and no exception message interpolates ``os.environ``.

This module is therefore **defense-in-depth**, not a fix for an active leak. It gives a
single, well-tested place to scrub secrets if and when a human-facing diagnostic path is
added (a "dump the effective settings" command, a config ``__repr__``, an error context
that echoes the environment). Wiring it at those boundaries means a future contributor
who prints a settings mapping cannot accidentally spill a key.

**Scope contract (oracle byte-identical).** Redaction is applied ONLY to strings/mappings
that are about to become diagnostic OUTPUT (a log line, a serialized config dump, an
exception message). It must NEVER be called on pipeline data, evidence text, retrieval
results, or anything that flows into the report — those bytes must be unchanged. Nothing
in this module touches hot-path code.

Two entry points:

* :func:`redact` — mask secret-bearing values in a ``str`` or a ``Mapping``. For a mapping,
  a value is masked when its KEY looks secret (matches :data:`SECRET_KEY_RE`). For a string,
  any registered known-secret substring is masked, plus common inline ``key=value`` /
  ``"key": "value"`` / ``Authorization: Bearer <tok>`` shapes whose key looks secret.
* :func:`safe_repr` — a ``repr``-style rendering of a config/dataclass/object with its
  secret-looking attributes masked, safe to put in a log or exception.
"""

from __future__ import annotations

import re
from typing import Any, Mapping

REDACTED = "***REDACTED***"

# A KEY (env var name, dict key, attribute name) is treated as secret-bearing when it
# contains any of these tokens, case-insensitively. Each token is matched with a WORD-ish
# boundary (segment edge = start/end or a non-letter like ``_``/``-``/``.``) so ``AUTH_TOKEN``
# and ``access_token`` match while the pervasive non-secret ``max_tokens`` (plural TOKENS)
# and words like ``author`` do NOT — a false positive on a hot config key like
# ``PG_*_MAX_TOKENS`` would be visually noisy in a dump, and word-bounding avoids it while
# still erring toward masking anything genuinely secret-shaped.
# ``AUTHORIZATION`` is included whole (it is the HTTP header that carries a bearer/basic
# secret) — bare ``AUTH`` alone would not match it because ``AUTHORIZATION`` has no boundary
# after ``AUTH``.
_SECRET_KEY_TOKENS = (
    "KEY",
    "TOKEN",
    "SECRET",
    "PASSWORD",
    "PASSWD",
    "CREDENTIAL",
    "AUTH",
    "AUTHORIZATION",
)

# A segment boundary is a non-letter char or the string edge. This makes "TOKEN" match in
# "AUTH_TOKEN"/"access-token"/"apiToken"(camelCase: uppercase T after lowercase) but not in
# "tokens"/"max_tokens" (trailing 's' is a letter, so no right boundary).
_BOUNDARY = r"(?:^|(?<=[^A-Za-z]))(?:{tok})(?=$|[^A-Za-z])"
SECRET_KEY_RE = re.compile(
    "|".join(_BOUNDARY.format(tok=re.escape(t)) for t in _SECRET_KEY_TOKENS),
    re.IGNORECASE,
)

# Process-wide registry of literal secret VALUES to scrub from free text even when the
# surrounding key is unknown (e.g. a token that leaked into an upstream library's error
# string). Kept small and populated explicitly via register_known_secret(); we never scan
# os.environ implicitly, to avoid surprising behaviour and to keep this import side-effect
# free.
_KNOWN_SECRET_VALUES: set[str] = set()

# Minimum length for a registered known secret to be scrubbed, so short/empty values can
# never turn ordinary text into a wall of redactions.
_MIN_KNOWN_SECRET_LEN = 6

# Inline "<key> = <value>" / '"<key>": "<value>"' / "<key>: Bearer <value>" shapes. Group 1
# is the key (checked against SECRET_KEY_RE), group 2 the separator+prefix we keep, group 3
# the value we mask.
# The secret token inside the key is word-bounded (``(?<![A-Za-z])`` before, ``(?![A-Za-z])``
# after) with the SAME rationale as SECRET_KEY_RE: ``max_tokens=8000`` in a free-text line
# must NOT be redacted (plural TOKENS), while ``AUTH_TOKEN=...`` / ``api_key: ...`` /
# ``Authorization: Bearer ...`` must. The key run may carry non-letter segments (``_.-``) on
# either side of the token.
_INLINE_RE = re.compile(
    r"""
    (["']?[A-Za-z0-9_.\-]*?        # (1) key name (may be quoted), non-greedy
        (?<![A-Za-z])
        (?:KEY|TOKEN|SECRET|PASSWORD|PASSWD|CREDENTIAL|AUTH)
        (?![A-Za-z])
        [A-Za-z0-9_.\-]*["']?)
    (\s*[:=]\s*                    # (2) separator
        (?:["']|Bearer\s+|Basic\s+)?)  #     optional opening quote / scheme prefix
    ([^\s"',}&]+)                  # (3) the value
    """,
    re.IGNORECASE | re.VERBOSE,
)

# ``Bearer <tok>`` / ``Basic <tok>`` anywhere — masks the credential in an Authorization
# header value regardless of the surrounding key name (``Authorization`` itself does not
# contain a word-bounded secret token). Group 1 is the scheme prefix we keep.
_SCHEME_RE = re.compile(r"\b(Bearer\s+|Basic\s+)([A-Za-z0-9._\-+/=]+)", re.IGNORECASE)


def register_known_secret(value: str | None) -> None:
    """Register a literal secret VALUE so :func:`redact` scrubs it from free text.

    No-op for falsy or too-short values. Idempotent. Callers typically register the API
    keys they just read from the environment so a downstream library's opaque error string
    can be scrubbed before it is logged.
    """
    if value and len(value) >= _MIN_KNOWN_SECRET_LEN:
        _KNOWN_SECRET_VALUES.add(value)


def is_secret_key(key: str) -> bool:
    """True when ``key`` (an env var / dict key / attribute name) looks secret-bearing."""
    return bool(SECRET_KEY_RE.search(key))


def _redact_str(text: str) -> str:
    out = text
    # 1) Scrub any registered literal secret value (longest first, so a value that is a
    #    substring of another does not leave a partial tail behind).
    for secret in sorted(_KNOWN_SECRET_VALUES, key=len, reverse=True):
        if secret in out:
            out = out.replace(secret, REDACTED)
    # 2) Scrub inline key=value shapes whose key looks secret.
    out = _INLINE_RE.sub(lambda m: f"{m.group(1)}{m.group(2)}{REDACTED}", out)
    # 3) Scrub Bearer/Basic scheme credentials (Authorization header values).
    out = _SCHEME_RE.sub(lambda m: f"{m.group(1)}{REDACTED}", out)
    return out


def redact(value: Any) -> Any:
    """Return a redacted copy of ``value`` for diagnostic output.

    * ``Mapping`` → a new ``dict`` with each value masked when its key looks secret, and
      otherwise recursively redacted (so nested mappings/strings are covered).
    * ``str`` → known-secret substrings and inline secret ``key=value`` shapes masked.
    * ``list``/``tuple`` → element-wise redaction, preserving the container type.
    * anything else → returned unchanged.

    Pure: never mutates its argument. Behaviour-neutral for the pipeline because it is only
    ever applied to strings/mappings destined for a log, dump, or exception message.
    """
    if isinstance(value, Mapping):
        result: dict[Any, Any] = {}
        for k, v in value.items():
            if isinstance(k, str) and is_secret_key(k):
                result[k] = REDACTED
            else:
                result[k] = redact(v)
        return result
    if isinstance(value, str):
        return _redact_str(value)
    if isinstance(value, (list, tuple)):
        redacted = [redact(v) for v in value]
        return type(value)(redacted)
    return value


def safe_repr(obj: Any) -> str:
    """``repr``-style rendering of ``obj`` with secret-looking attributes masked.

    Handles plain objects (via ``__dict__``), objects exposing ``model_dump`` (pydantic) or
    ``_asdict`` (namedtuple), and mappings. Any attribute/key whose name looks secret is
    shown as ``***REDACTED***``. Falls back to :func:`redact` of ``repr(obj)`` for objects
    with no introspectable fields, so it is always safe to interpolate into a log line.
    """
    fields: Mapping[str, Any] | None = None
    if isinstance(obj, Mapping):
        fields = obj
    elif hasattr(obj, "model_dump") and callable(obj.model_dump):
        try:
            fields = obj.model_dump()
        except Exception:
            fields = None
    elif hasattr(obj, "_asdict") and callable(obj._asdict):
        try:
            fields = obj._asdict()
        except Exception:
            fields = None
    elif hasattr(obj, "__dict__") and obj.__dict__:
        fields = vars(obj)

    if fields is None:
        return redact(repr(obj))

    redacted = redact(dict(fields))
    inner = ", ".join(f"{k}={v!r}" for k, v in redacted.items())
    name = type(obj).__name__ if not isinstance(obj, Mapping) else "dict"
    return f"{name}({inner})"
