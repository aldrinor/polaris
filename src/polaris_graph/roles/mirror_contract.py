"""Mirror (Cohere Command-A+) two-pass RAG/JSON contract.

Cohere `response_format` (JSON mode) is NOT supported together with `documents`/`tools`
(F2, confirmed in I-meta-002 iter-2 verdict). So the Mirror role is TWO-PASS:
  pass-1: RAG-with-citations  -> grounded answer text + citation spans (each span its doc_id)
  pass-2: JSON classification -> bound to pass-1 by a content_hash

The pass-2 classification MUST be of the SAME artifact pass-1 produced, not a regenerated
or normalized one. (iter-2 fix, Codex P1-a): the binding hash covers BOTH the answer text
AND the ordered citation bindings `(span_start, span_end, doc_id)` — NOT the answer text
alone — so identical answer text with swapped or missing citation bindings does NOT pass
the hash check.

Citation span format: self-host Cohere emits `<co>...</co:doc_ids>` spans (doc_ids is a
comma-separated list). `parse_cohere_citations` parses that form and tolerates an empty
input. There is no live Cohere in this PR; the `<co>` fixture IS the assumed self-host
span shape, documented here rather than implied as verified output.
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field


@dataclass(frozen=True)
class CitationSpan:
    """One grounded citation span: a [span_start, span_end) char range over the answer
    text, attached to one or more source doc_ids."""

    span_start: int
    span_end: int
    doc_ids: tuple[str, ...]


@dataclass
class MirrorPass1:
    """Pass-1 output: the grounded answer text plus its citation spans."""

    answer_text: str
    citation_spans: list[CitationSpan] = field(default_factory=list)


@dataclass
class MirrorPass2:
    """Pass-2 output: the JSON classification, bound to pass-1 by `content_hash`."""

    content_hash: str
    classification: str
    rationale: str | None = None


# Field key for the embedded binding hash in the pass-2 input dict.
_CONTENT_HASH_KEY = "content_hash"
_ANSWER_TEXT_KEY = "answer_text"

# Self-host Cohere span: `<co>covered text</co:doc_a,doc_b>`. The doc_ids list is
# captured from the closing tag. Whitespace-tolerant around the doc_ids.
_CO_SPAN_RE = re.compile(r"<co>(.*?)</co:\s*([^>]*?)\s*>", re.DOTALL)


def _canonical_binding(pass1: MirrorPass1) -> str:
    """Deterministic canonical serialization of the pass-1 artifact for hashing.

    Covers the answer text AND the ordered list of `(span_start, span_end, doc_id)` tuples.
    Multi-doc spans are expanded to one tuple per doc_id, and the full tuple list is sorted,
    so the serialization is independent of span/doc_id authoring order but still sensitive
    to ANY change in the (start, end, doc_id) bindings. The exact same serializer is used
    by both `build_pass2_input` and `verify_pass2_binding`.

    INJECTIVITY: the answer text and the binding list are wrapped as the two elements of a
    single JSON array. Because the answer is JSON-string-escaped, there is NO ambiguous
    delimiter byte a crafted doc_id (which may legitimately contain spaces or brackets) could
    inject to collide two distinct (answer, bindings) pairs onto the same serialization —
    unlike a flat `answer + " " + bindings` concatenation. Resolves brief question 2 (P1-a).
    """
    binding_tuples: list[tuple[int, int, str]] = []
    for span in pass1.citation_spans:
        for doc_id in span.doc_ids:
            binding_tuples.append((span.span_start, span.span_end, doc_id))
    binding_tuples.sort()
    return json.dumps([pass1.answer_text, binding_tuples], separators=(",", ":"))


def _compute_content_hash(pass1: MirrorPass1) -> str:
    """sha256 over the canonical (answer_text + citation bindings) serialization."""
    canonical = _canonical_binding(pass1)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def build_pass2_input(pass1: MirrorPass1) -> dict:
    """Build the input dict handed to pass-2, embedding the composite `content_hash`.

    The hash is computed over BOTH the answer text and the ordered citation bindings
    (P1-a), so pass-2 can only validly classify the exact (answer + citations) artifact
    pass-1 produced.
    """
    return {
        _ANSWER_TEXT_KEY: pass1.answer_text,
        _CONTENT_HASH_KEY: _compute_content_hash(pass1),
    }


def verify_pass2_binding(pass1: MirrorPass1, pass2: MirrorPass2) -> bool:
    """True iff pass-2 classified the SAME (answer + citations) artifact as pass-1.

    Recomputes the composite hash from pass-1 and compares it to `pass2.content_hash`.
    Returns False if the answer text was regenerated/normalized OR if any citation binding
    (span_start, span_end, doc_id) was swapped or dropped — even when the answer text is
    byte-identical.
    """
    return _compute_content_hash(pass1) == pass2.content_hash


def parse_cohere_citations(raw: str) -> list[CitationSpan]:
    """Parse self-host Cohere `<co>...</co:doc_ids>` spans into CitationSpans.

    `span_start`/`span_end` are the [start, end) char offsets of the covered text WITHIN
    the cleaned answer (tags stripped), reconstructed as the spans are consumed left to
    right. `doc_ids` is the comma-separated list from the closing tag (empty entries
    dropped). Tolerates empty input (returns []) and tolerates a span with no doc_ids.

    Managed-form tolerance: a managed Cohere `message.citations` offset payload contains no
    `<co>` spans, so this parser returns [] for it BY DESIGN (it does not crash). Full
    managed-offset parsing is sub-PR-4's adapter; this contract covers the self-host span
    form only.
    """
    if not raw:
        return []

    spans: list[CitationSpan] = []
    cleaned_len = 0  # running length of the answer text with tags removed
    cursor = 0       # position in raw
    for match in _CO_SPAN_RE.finditer(raw):
        # Plain text before this span contributes to the cleaned-text offset.
        cleaned_len += len(raw[cursor:match.start()])
        covered_text = match.group(1)
        doc_ids_raw = match.group(2)
        doc_ids = tuple(d.strip() for d in doc_ids_raw.split(",") if d.strip())
        span_start = cleaned_len
        span_end = span_start + len(covered_text)
        spans.append(CitationSpan(span_start=span_start, span_end=span_end, doc_ids=doc_ids))
        cleaned_len = span_end
        cursor = match.end()
    return spans
