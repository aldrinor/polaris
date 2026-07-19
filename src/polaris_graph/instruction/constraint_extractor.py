"""Instruction Constraint Extractor.

A general, prompt-agnostic LLM pass that reads a free-text task prompt and
returns the concrete deliverable constraints the author must honor. It is
adversarially prompted to surface BURIED constraints — rules phrased
mid-sentence, tucked into a subordinate clause, or dropped as a soft aside
("ideally...", "where possible...", "and please keep it...") — not just the
obvious headline ask.

Design notes
------------
* Standalone module. Nothing here is wired into the driver or generator; the
  caller decides what (if anything) to do with the returned dict.
* Reuses the repo's existing LLM gateway (``OpenRouterClient.generate``). No
  API keys are hardcoded — the client reads ``OPENROUTER_API_KEY`` / model
  from the environment exactly as every other module does.
* The live LLM call is split from the pure parser. ``parse_constraints_json``
  turns a raw model string into a normalized :class:`Constraints`, so the shape
  can be unit-tested with a fixture and no network.

Typed fields (all keys always present in the returned dict)
-----------------------------------------------------------
``source_types``     list[str]  e.g. ['journal_article']
``languages``        list[str]  e.g. ['en'] (ISO-639-1 where known)
``recency``          str|None   a cutoff phrase/date, e.g. 'since 2020', or None
``required_coverage``list[str]  topical slots the prompt implies/names
``exclusions``       list[str]  things to exclude (source kinds, topics, ...)
``format``           str|None   e.g. 'literature_review'
``length``           str|None   e.g. '3000 words' / '10 pages', or None
``tone``             str|None   e.g. 'academic', or None
"""

from __future__ import annotations

import json
import logging
import os
import re
from dataclasses import dataclass, field
from typing import Any, Optional
from src.polaris_graph.settings import resolve

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Canonical field set + normalization vocab
# ---------------------------------------------------------------------------

# The full, ordered set of keys the extractor guarantees on every result dict.
_FIELDS: tuple[str, ...] = (
    "source_types",
    "languages",
    "recency",
    "required_coverage",
    "exclusions",
    "format",
    "length",
    "tone",
)

_LIST_FIELDS: frozenset[str] = frozenset(
    {"source_types", "languages", "required_coverage", "exclusions"}
)
_SCALAR_FIELDS: frozenset[str] = frozenset({"recency", "format", "length", "tone"})

# Light, deterministic canonicalization so common phrasings collapse to stable
# tokens the rest of the pipeline can match on. This is intentionally shallow —
# the LLM does the semantic lifting; this only tidies synonyms it emits.
_SOURCE_TYPE_ALIASES: dict[str, str] = {
    "journal article": "journal_article",
    "journal articles": "journal_article",
    "journal-article": "journal_article",
    "journal": "journal_article",
    "peer reviewed journal article": "journal_article",
    "peer-reviewed journal article": "journal_article",
    "peer reviewed article": "peer_reviewed",
    "peer-reviewed": "peer_reviewed",
    "peer reviewed": "peer_reviewed",
    "academic paper": "journal_article",
    "scholarly article": "journal_article",
    "conference paper": "conference_paper",
    "working paper": "working_paper",
    "preprint": "preprint",
    "book": "book",
    "book chapter": "book_chapter",
    "report": "report",
    "government report": "government_report",
    "news article": "news_article",
    "news": "news_article",
    "blog": "blog_post",
    "blog post": "blog_post",
    "website": "website",
    "grey literature": "grey_literature",
    "gray literature": "grey_literature",
}

# ISO-639-1 canonicalization for the languages the prompt is likely to name.
_LANGUAGE_ALIASES: dict[str, str] = {
    "english": "en",
    "en": "en",
    "eng": "en",
    "english-language": "en",
    "english language": "en",
    "spanish": "es",
    "french": "fr",
    "german": "de",
    "chinese": "zh",
    "mandarin": "zh",
    "japanese": "ja",
    "portuguese": "pt",
    "italian": "it",
    "russian": "ru",
    "arabic": "ar",
    "korean": "ko",
    "dutch": "nl",
}

_FORMAT_ALIASES: dict[str, str] = {
    "literature review": "literature_review",
    "lit review": "literature_review",
    "systematic review": "systematic_review",
    "scoping review": "scoping_review",
    "narrative review": "narrative_review",
    "meta analysis": "meta_analysis",
    "meta-analysis": "meta_analysis",
    "essay": "essay",
    "report": "report",
    "white paper": "white_paper",
    "policy brief": "policy_brief",
    "briefing": "briefing",
    "summary": "summary",
    "blog post": "blog_post",
    "article": "article",
}


@dataclass
class Constraints:
    """Normalized constraint bundle.

    Every field is populated (lists default empty, scalars default ``None``) so
    downstream code never has to guard for a missing key.
    """

    source_types: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    recency: Optional[str] = None
    required_coverage: list[str] = field(default_factory=list)
    exclusions: list[str] = field(default_factory=list)
    format: Optional[str] = None
    length: Optional[str] = None
    tone: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        """Return the canonical dict with all keys present, in field order."""
        return {
            "source_types": list(self.source_types),
            "languages": list(self.languages),
            "recency": self.recency,
            "required_coverage": list(self.required_coverage),
            "exclusions": list(self.exclusions),
            "format": self.format,
            "length": self.length,
            "tone": self.tone,
        }


# ---------------------------------------------------------------------------
# Prompt (adversarial — hunt buried constraints)
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = (
    "You are a meticulous requirements analyst. Your job is to read a task "
    "prompt written for a report author and extract EVERY constraint the "
    "author must obey to produce an acceptable deliverable.\n\n"
    "Be adversarial about BURIED constraints. Constraints are frequently NOT "
    "stated as a clean bullet list — they hide:\n"
    "  * mid-sentence ('...citing only high-quality, English-language journal "
    "articles.')\n"
    "  * in subordinate clauses ('which should exclude opinion pieces')\n"
    "  * as soft asides ('ideally peer-reviewed', 'where possible since 2020', "
    "'and please keep the tone academic')\n"
    "  * implied by the deliverable type (a 'literature review' implies scholarly "
    "sources and a review structure).\n\n"
    "Extract only what the prompt actually asks for or clearly implies. Do NOT "
    "invent constraints that are not supported by the text. If a field is not "
    "constrained, leave it empty/null — do not guess.\n\n"
    "Return STRICT JSON only (no prose, no code fences) with EXACTLY these keys:\n"
    "  source_types: array of strings — kinds of sources allowed/required "
    "(e.g. 'journal_article', 'peer_reviewed'). If the prompt restricts to a "
    "source kind ('only ... journal articles'), list ONLY that kind.\n"
    "  languages: array of strings — required source languages (prefer ISO-639-1 "
    "like 'en').\n"
    "  recency: string or null — any recency/date-window rule (e.g. 'since 2020', "
    "'last 5 years').\n"
    "  required_coverage: array of strings — specific topics/sub-questions/slots "
    "the review must cover, as named or clearly implied by the prompt.\n"
    "  exclusions: array of strings — anything to exclude (source kinds, topics, "
    "regions).\n"
    "  format: string or null — the deliverable format (e.g. 'literature_review', "
    "'systematic_review', 'report', 'essay').\n"
    "  length: string or null — any length/word/page target.\n"
    "  tone: string or null — required tone/register (e.g. 'academic', 'formal').\n"
)

_USER_TEMPLATE = (
    "Extract the deliverable constraints from the following task prompt.\n"
    "Read it twice: once for the obvious headline ask, and once hunting for "
    "constraints buried mid-sentence or phrased as soft asides.\n\n"
    "TASK PROMPT:\n"
    '"""\n{prompt}\n"""\n\n'
    "Return the strict JSON object now."
)


# ---------------------------------------------------------------------------
# Pure parser (no network) — usable directly for fixture-based tests
# ---------------------------------------------------------------------------

def _strip_code_fences(raw: str) -> str:
    """Remove ```json ... ``` / ``` ... ``` fences if the model added them."""
    text = raw.strip()
    if text.startswith("```"):
        # drop first fence line
        text = text.split("\n", 1)[1] if "\n" in text else text
        # drop trailing fence
        if text.rstrip().endswith("```"):
            text = text.rstrip()[: -3]
    return text.strip()


def _extract_json_object(raw: str) -> str:
    """Return the first balanced ``{...}`` object substring in ``raw``.

    Falls back to the whole (fence-stripped) string if no braces are found, so
    ``json.loads`` raises a clear error the caller can handle.
    """
    text = _strip_code_fences(raw)
    start = text.find("{")
    if start == -1:
        return text
    depth = 0
    in_str = False
    esc = False
    for i in range(start, len(text)):
        ch = text[i]
        if in_str:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    return text[start:]


def _as_str_list(value: Any) -> list[str]:
    """Coerce a JSON value into a clean list of non-empty trimmed strings."""
    if value is None:
        return []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, (list, tuple)):
        items = list(value)
    else:
        items = [value]
    out: list[str] = []
    seen: set[str] = set()
    for it in items:
        if it is None:
            continue
        s = str(it).strip()
        if not s:
            continue
        key = s.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(s)
    return out


def _as_opt_str(value: Any) -> Optional[str]:
    """Coerce a scalar JSON value into a trimmed string or None."""
    if value is None:
        return None
    if isinstance(value, (list, tuple)):
        value = next((v for v in value if v not in (None, "")), None)
        if value is None:
            return None
    s = str(value).strip()
    if not s or s.lower() in ("none", "null", "n/a", "na"):
        return None
    return s


def _canon_list(items: list[str], aliases: dict[str, str]) -> list[str]:
    """Map each item through ``aliases`` (case/whitespace-insensitive), dedup."""
    out: list[str] = []
    seen: set[str] = set()
    for it in items:
        key = re.sub(r"[\s_]+", " ", it.strip().lower())
        canon = aliases.get(key, it.strip())
        dk = canon.lower()
        if dk in seen:
            continue
        seen.add(dk)
        out.append(canon)
    return out


def _canon_scalar(value: Optional[str], aliases: dict[str, str]) -> Optional[str]:
    if value is None:
        return None
    key = re.sub(r"[\s_]+", " ", value.strip().lower())
    return aliases.get(key, value.strip())


def parse_constraints_json(raw: str) -> Constraints:
    """Parse a raw LLM JSON string into a normalized :class:`Constraints`.

    Pure and deterministic — no network. Tolerant of code fences, surrounding
    prose, missing keys, and scalar-vs-list mismatches. Unknown keys are
    ignored. Raises ``ValueError`` only if no JSON object can be located.
    """
    obj_text = _extract_json_object(raw)
    try:
        data = json.loads(obj_text)
    except json.JSONDecodeError as exc:  # pragma: no cover - defensive
        raise ValueError(f"constraint extractor: non-JSON model output: {exc}") from exc
    if not isinstance(data, dict):
        raise ValueError("constraint extractor: model output was not a JSON object")

    c = Constraints(
        source_types=_canon_list(
            _as_str_list(data.get("source_types")), _SOURCE_TYPE_ALIASES
        ),
        languages=_canon_list(
            _as_str_list(data.get("languages")), _LANGUAGE_ALIASES
        ),
        recency=_as_opt_str(data.get("recency")),
        required_coverage=_as_str_list(data.get("required_coverage")),
        exclusions=_as_str_list(data.get("exclusions")),
        format=_canon_scalar(_as_opt_str(data.get("format")), _FORMAT_ALIASES),
        length=_as_opt_str(data.get("length")),
        tone=_as_opt_str(data.get("tone")),
    )
    return c


# ---------------------------------------------------------------------------
# Live LLM pass
# ---------------------------------------------------------------------------

def _live_enabled() -> bool:
    """Whether a live LLM call is permitted for the extractor.

    Default OFF for tests/CI so importing/exercising the parser never hits the
    network. The live gate follows the repo's env-flag convention (read at call
    time so the harness can toggle without re-import). A present
    ``OPENROUTER_API_KEY`` alone is not sufficient — the flag must be truthy —
    which keeps unit runs hermetic even on a developer box that has a key.
    """
    return resolve("PG_CONSTRAINT_EXTRACT_LIVE").strip().lower() in (
        "1",
        "true",
        "yes",
        "on",
    )


async def extract_constraints_async(
    prompt: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    client: Any = None,
) -> dict[str, Any]:
    """Adversarially extract deliverable constraints from ``prompt`` (async).

    Reuses the repo LLM gateway (:class:`OpenRouterClient`). Pass ``client`` to
    inject a stub/mock in tests (any object with an async ``generate(prompt,
    system, max_tokens, temperature)`` returning an object with a ``.content``
    string). When ``client`` is None, a real client is constructed only if the
    live gate (``PG_CONSTRAINT_EXTRACT_LIVE``) is enabled; otherwise this raises
    ``RuntimeError`` so a test never silently hits the network.

    Returns the canonical constraint dict (all keys present).
    """
    if not isinstance(prompt, str) or not prompt.strip():
        # Empty prompt -> empty constraints (no call). Keeps callers simple.
        return Constraints().to_dict()

    if client is None:
        if not _live_enabled():
            raise RuntimeError(
                "constraint extractor: live LLM disabled. Set "
                "PG_CONSTRAINT_EXTRACT_LIVE=1 to enable a real call, or pass a "
                "client= stub in tests."
            )
        # Lazy import so the OFF/parser path never imports the HTTP client.
        from src.polaris_graph.llm.openrouter_client import (  # noqa: PLC0415
            OpenRouterClient,
        )

        client = OpenRouterClient(model=model)

    user_prompt = _USER_TEMPLATE.format(prompt=prompt.strip())
    response = await client.generate(
        prompt=user_prompt,
        system=_SYSTEM_PROMPT,
        max_tokens=max_tokens,
        temperature=temperature,
    )
    raw = getattr(response, "content", None) or ""
    constraints = parse_constraints_json(raw)
    return constraints.to_dict()


def extract_constraints(
    prompt: str,
    *,
    model: Optional[str] = None,
    temperature: float = 0.0,
    max_tokens: int = 1024,
    client: Any = None,
) -> dict[str, Any]:
    """Synchronous wrapper around :func:`extract_constraints_async`.

    Runs the async extractor to completion. Raises ``RuntimeError`` if called
    from within a running event loop (use the async variant there).
    """
    import asyncio

    try:
        asyncio.get_running_loop()
    except RuntimeError:
        pass
    else:  # already in a loop
        raise RuntimeError(
            "extract_constraints() cannot be called from a running event loop; "
            "await extract_constraints_async() instead."
        )
    return asyncio.run(
        extract_constraints_async(
            prompt,
            model=model,
            temperature=temperature,
            max_tokens=max_tokens,
            client=client,
        )
    )
