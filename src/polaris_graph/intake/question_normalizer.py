"""Question normalizer — deterministic pre-processing of raw user input.

Per slice 001 architecture proposal §"Data shapes" / §"Module boundaries".

Transforms a raw user-typed string into a NormalizedQuestion with:
  - Unicode NFC normalization (canonical composed form)
  - Whitespace collapse (multiple spaces/tabs/newlines → single space)
  - Control-character stripping (except tab/newline which become spaces
    before whitespace-collapse)
  - Length bounds enforcement (3 chars min, 1000 chars max post-normalization)
  - Language detection stub (slice 001 is English-only; returns "en")

This is the boundary between "raw user typing" and "normalized question
that classifier/ambiguity-detector can reason about." Pure function — no
network, no I/O, no side effects.

Input contract:
    raw: str — anything the user typed, including weird Unicode forms,
              emoji, RTL text, control chars, mixed whitespace, etc.

Output contract:
    NormalizedQuestion(
        raw=<original verbatim>,
        normalized=<NFC + whitespace-collapsed + control-stripped>,
        lang="en",
        char_count=<len(normalized)>,
        detected_at_utc=<utcnow>,
    )

Raises:
    QuestionTooShort if normalized length < MIN_CHARS (3)
    QuestionTooLong  if normalized length > MAX_CHARS (1000)
"""

from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from typing import Literal

from pydantic import BaseModel, Field

MIN_CHARS = 3
MAX_CHARS = 1000

# Match any Unicode control char (categories Cc, Cf) EXCEPT \t \n \r which
# we whitespace-collapse below. Cs (surrogates) are also stripped — they
# shouldn't appear in valid UTF-8 input but defend against malformed input.
_CONTROL_CHAR_RE = re.compile(
    r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\ud800-\udfff]"
)
# Whitespace collapse: any run of whitespace → single ASCII space
_WHITESPACE_RUN_RE = re.compile(r"\s+")


class QuestionTooShort(ValueError):
    """Raised when the normalized question is shorter than MIN_CHARS."""


class QuestionTooLong(ValueError):
    """Raised when the normalized question is longer than MAX_CHARS."""


class NormalizedQuestion(BaseModel):
    """A user question after deterministic pre-processing.

    Downstream classifier and ambiguity detector operate on `normalized`,
    not `raw`. The `raw` field is preserved for audit / display.
    """

    raw: str = Field(description="Original user input, verbatim, before normalization")
    normalized: str = Field(description="NFC + whitespace-collapsed + control-stripped form")
    lang: Literal["en"] = Field(default="en", description="Detected language (slice 001 is English-only)")
    char_count: int = Field(description="Length of `normalized` in characters")
    detected_at_utc: datetime = Field(description="UTC timestamp at normalization time")


def normalize(raw: str) -> NormalizedQuestion:
    """Normalize a raw user-typed question.

    Args:
        raw: User input. Any string, including weird Unicode, mixed
             whitespace, control characters.

    Returns:
        NormalizedQuestion with `raw` preserved and `normalized` cleaned.

    Raises:
        QuestionTooShort: if normalized length < 3 chars (after stripping)
        QuestionTooLong:  if normalized length > 1000 chars
        TypeError:        if `raw` is not a str
    """
    if not isinstance(raw, str):
        raise TypeError(f"normalize() expected str, got {type(raw).__name__}")

    # Step 1: Unicode NFC normalization.
    # NFC = Canonical Composition. "café" written as "e + combining acute"
    # (NFD) becomes "é" (NFC). Necessary for downstream regex/string compare
    # to behave deterministically.
    nfc = unicodedata.normalize("NFC", raw)

    # Step 2: Strip control characters (except tab/newline which become
    # whitespace, handled by step 3).
    no_control = _CONTROL_CHAR_RE.sub("", nfc)

    # Step 3: Whitespace collapse + strip leading/trailing.
    collapsed = _WHITESPACE_RUN_RE.sub(" ", no_control).strip()

    # Step 4: Length bounds.
    char_count = len(collapsed)
    if char_count < MIN_CHARS:
        raise QuestionTooShort(
            f"normalized length {char_count} < MIN_CHARS={MIN_CHARS}"
        )
    if char_count > MAX_CHARS:
        raise QuestionTooLong(
            f"normalized length {char_count} > MAX_CHARS={MAX_CHARS}"
        )

    return NormalizedQuestion(
        raw=raw,
        normalized=collapsed,
        lang="en",
        char_count=char_count,
        detected_at_utc=datetime.now(timezone.utc),
    )
