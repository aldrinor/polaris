"""Language-profile-driven multilingual / cross-lingual retrieval frontier.

I-deepfix-001 R5 (#1344). DRB-II contains non-English (e.g. Chinese) tasks and
FORCES independent multi-source recall. Today the retrieval frontier is built
only from the question's own English words: ``query_decomposer`` and the
FS-Researcher facet planner emit English queries, the backends fan out English
strings, and on a zh task the highest-authority NATIVE-language primaries are
never queried — a real recall hole, not cosmetic. A competitor that queries in
the task language out-recalls POLARIS on those tasks.

WHAT THIS MODULE DOES (pure, no-network, no-LLM by default)
===========================================================
1. :func:`detect_language_profile` — reads the task's language profile from the
   question text (Unicode script detection) plus any explicit "answer in <lang>"
   instruction. Deterministic; no model.
2. :func:`expand_queries_for_profile` — given the English facet/angle queries,
   ADDS on-language queries so a native-language source and its English paraphrase
   land in the SAME multi-backend retrieval (the already-multilingual Qwen3
   reranker then scores them cross-lingually into one consolidation basket). It
   carries the question's OWN native-script terms into the query fanout (an honest
   cross-lingual query — no fabricated translation) and, when the caller injects a
   ``translate_fn`` (production may wrap the GLM mirror), also appends true
   translations. English stays a query language, so **monolingual-English tasks
   are byte-identical** (the expansion returns the input queries unchanged).

DNA (§-1.3 WEIGHT-AND-CONSOLIDATE)
==================================
Pure frontier expansion into more languages. It ADDS on-language queries only and
DROPS ZERO sources; breadth emerges from facet x language coverage, never a
target. The faithfulness engine (strict_verify / NLI / 4-role / provenance) is
untouched — this only changes WHICH queries are issued. Flag-gated
``PG_MULTILINGUAL_RETRIEVAL`` (default ON); OFF or an English-only profile =>
byte-identical to today.
"""
from __future__ import annotations

import os
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Callable, Optional, Sequence

# (english_query, target_lang_code) -> translated query. Injected by production
# (may wrap the GLM mirror). None => deterministic native-term carry only.
TranslateFn = Callable[[str, str], str]

_ON_VALUES = frozenset({"1", "true", "on", "yes"})

# Compute-safety cap on total emitted queries after multilingual expansion (never
# a breadth target — §-1.3; each query still flows the unchanged verify).
_MAX_QUERIES_ENV = "PG_MULTILINGUAL_MAX_QUERIES"
_DEFAULT_MAX_QUERIES = 40

# Unicode-script -> ISO-639-1-ish language code for the scripts DRB-II tasks use.
# Script detection is deterministic and model-free; a script maps to its dominant
# task language for query-fanout purposes (Han -> zh, Hiragana/Katakana -> ja,
# Hangul -> ko, Cyrillic -> ru, Arabic -> ar). This is a RETRIEVAL routing hint,
# never a faithfulness signal.
_SCRIPT_LANG: tuple[tuple[str, str], ...] = (
    ("HIRAGANA", "ja"),
    ("KATAKANA", "ja"),
    ("HANGUL", "ko"),
    ("CJK", "zh"),  # CJK Unified Ideographs — shared Han; default zh for routing
    ("CYRILLIC", "ru"),
    ("ARABIC", "ar"),
)

# Explicit language instructions in the question ("answer in Chinese", "用中文",
# "respond in Japanese"). Maps a lowercased language NAME to its code so an
# English-worded question that DEMANDS a non-English answer still routes native
# queries. Deterministic keyword map; not exhaustive by design (the script
# detector covers the common non-Latin cases).
_LANG_NAME_CODE: dict[str, str] = {
    "chinese": "zh",
    "mandarin": "zh",
    "中文": "zh",
    "japanese": "ja",
    "日本語": "ja",
    "korean": "ko",
    "한국어": "ko",
    "russian": "ru",
    "arabic": "ar",
    "french": "fr",
    "german": "de",
    "spanish": "es",
}
_INSTRUCTION_RE = re.compile(
    r"(?:answer|respond|reply|write|in)\s+(?:in\s+)?"
    r"(chinese|mandarin|japanese|korean|russian|arabic|french|german|spanish)",
    re.IGNORECASE,
)

# A maximal run of native-script (non-ASCII-letter) characters — the question's
# own native terms, carried into the query fanout for an honest cross-lingual query.
_NATIVE_TERM_RE = re.compile(r"[^\x00-\x7f]+(?:\s+[^\x00-\x7f]+)*")


@dataclass(frozen=True)
class LanguageProfile:
    """The task's detected language profile for retrieval routing.

    ``languages`` is the ordered, de-duplicated list of language codes the
    frontier should query in — ALWAYS including English (English stays a query
    language so monolingual-English recall is never lost). ``non_english`` are
    just the additional languages (empty for an English-only task).
    """

    primary: str = "en"
    languages: tuple[str, ...] = ("en",)
    scripts: tuple[str, ...] = ()

    @property
    def non_english(self) -> tuple[str, ...]:
        return tuple(code for code in self.languages if code != "en")

    @property
    def is_multilingual(self) -> bool:
        return bool(self.non_english)


def multilingual_enabled() -> bool:
    """True iff `PG_MULTILINGUAL_RETRIEVAL` is truthy (default ON).

    OFF => the expansion is a byte-identical no-op regardless of the profile.
    """
    return os.getenv("PG_MULTILINGUAL_RETRIEVAL", "1").strip().lower() in _ON_VALUES


def _max_queries() -> int:
    raw = os.getenv(_MAX_QUERIES_ENV, "").strip()
    if not raw:
        return _DEFAULT_MAX_QUERIES
    try:
        return max(1, int(raw))
    except ValueError:
        return _DEFAULT_MAX_QUERIES


def _char_script(ch: str) -> Optional[str]:
    """Return a coarse script bucket name for a character, or None for ASCII/marks."""
    try:
        name = unicodedata.name(ch)
    except ValueError:
        return None
    for token in ("HIRAGANA", "KATAKANA", "HANGUL", "CJK", "CYRILLIC", "ARABIC"):
        if token in name:
            return token
    return None


def detect_language_profile(
    question: str, *, instruction: Optional[str] = None
) -> LanguageProfile:
    """Detect the task language profile from the question text + any explicit
    language instruction. Pure / deterministic / no-LLM.

    The profile carries EVERY language the frontier should query in — English
    always, plus any non-English language detected from (a) the non-Latin scripts
    present in the question body and (b) an explicit "answer in <language>"
    instruction. An all-ASCII question with no instruction => English-only
    (``is_multilingual`` False) => the expansion is a no-op.
    """
    text = question or ""
    scripts_found: list[str] = []
    langs: list[str] = ["en"]  # English is always a query language.

    # (a) Script detection over the question body.
    seen_scripts: set[str] = set()
    for ch in text:
        bucket = _char_script(ch)
        if bucket and bucket not in seen_scripts:
            seen_scripts.add(bucket)
    for token, code in _SCRIPT_LANG:
        if token in seen_scripts:
            scripts_found.append(token)
            if code not in langs:
                langs.append(code)

    # (b) Explicit "answer in <language>" instruction (in the question OR a
    # separate instruction string). Catches an English-worded question that
    # demands a non-English answer.
    hay = f"{text}\n{instruction or ''}"
    for m in _INSTRUCTION_RE.finditer(hay):
        code = _LANG_NAME_CODE.get(m.group(1).lower())
        if code and code not in langs:
            langs.append(code)
    for name, code in _LANG_NAME_CODE.items():
        if name in hay.lower() and code not in langs:
            langs.append(code)

    # Primary = the first non-English language if any (the dominant native), else en.
    non_en = [c for c in langs if c != "en"]
    primary = non_en[0] if non_en else "en"
    return LanguageProfile(
        primary=primary,
        languages=tuple(langs),
        scripts=tuple(scripts_found),
    )


def native_terms(question: str) -> list[str]:
    """Extract the question's own native-script term runs (ordered, de-duplicated).

    These are the honest cross-lingual seed: carrying the question's real
    native-language terms into the query fanout surfaces native-language sources
    WITHOUT fabricating a translation. Returns [] for an all-ASCII question.
    """
    out: list[str] = []
    seen: set[str] = set()
    for m in _NATIVE_TERM_RE.finditer(question or ""):
        term = " ".join(m.group(0).split()).strip()
        if term and term not in seen:
            seen.add(term)
            out.append(term)
    return out


def expand_queries_for_profile(
    queries: Sequence[str],
    profile: LanguageProfile,
    question: str,
    *,
    translate_fn: Optional[TranslateFn] = None,
    max_queries: Optional[int] = None,
) -> list[str]:
    """Add on-language queries for a multilingual profile; byte-identical for an
    English-only profile (or when the flag is OFF).

    The English queries are preserved FIRST and UNCHANGED (English stays a query
    language). Then, for a multilingual profile:

    * the question's own native-script terms are emitted as a standalone query,
      and prepended to each English query as a cross-lingual augmented query
      (honest — the terms are the question's real native words, no fabricated
      translation);
    * when ``translate_fn`` is injected (production may wrap the GLM mirror), a
      true translation of each English query into each non-English language is
      also appended.

    All additions are de-duplicated (order-preserving) and the whole list is
    capped by `PG_MULTILINGUAL_MAX_QUERIES` (compute-safety, never a breadth
    target). DROPS ZERO input queries.

    Args:
        queries: the English facet/angle queries.
        profile: the detected :class:`LanguageProfile`.
        question: the raw question (source of native-script terms).
        translate_fn: optional ``(query, lang) -> translated_query``.
        max_queries: override for `PG_MULTILINGUAL_MAX_QUERIES` (tests).

    Returns:
        The expanded query list (English-first). Unchanged input list when the
        flag is OFF or the profile is English-only.
    """
    base = [q for q in (queries or []) if (q or "").strip()]
    if not multilingual_enabled() or not profile.is_multilingual:
        return list(base)

    cap = _max_queries() if max_queries is None else max(1, int(max_queries))
    out: list[str] = []
    seen: set[str] = set()

    def _dedup_clean(text: str) -> "str | None":
        cleaned = " ".join((text or "").split()).strip()
        if not cleaned:
            return None
        key = cleaned.lower()
        if key in seen:
            return None
        seen.add(key)
        return cleaned

    # 1) English queries first, unchanged — NEVER dropped. The compute-safety cap applies
    # to the multilingual ADDITIONS only; truncating an input seed would contradict the
    # "DROPS ZERO input queries" contract (Fable P2). So every base query is emitted, and
    # the additions are bounded so the total never exceeds max(cap, len(base)).
    for q in base:
        cleaned = _dedup_clean(q)
        if cleaned is not None:
            out.append(cleaned)

    # Additions ceiling: the compute cap, but never below the (fully-kept) base count.
    ceiling = max(cap, len(out))

    def _add(text: str) -> bool:
        # Check the ceiling BEFORE appending: appending first (then testing) would
        # emit one extra multilingual addition whenever `out` is already AT the
        # ceiling — the off-by-one that let the total reach ceiling+1 (Codex P2).
        # A full frontier stops here without consuming `seen` or the input span.
        if len(out) >= ceiling:
            return False
        cleaned = _dedup_clean(text)
        if cleaned is None:
            return True
        out.append(cleaned)
        return len(out) < ceiling

    terms = native_terms(question)
    native_phrase = " ".join(terms).strip()

    # 2) The question's own native terms as a standalone cross-lingual query.
    if native_phrase and not _add(native_phrase):
        return out

    # 3) Native-term-augmented cross-lingual variants of each English query.
    if native_phrase:
        for q in base:
            if not _add(f"{native_phrase} {q}"):
                return out

    # 4) True translations when a translator is injected (production GLM mirror).
    if translate_fn is not None:
        for lang in profile.non_english:
            for q in base:
                try:
                    translated = translate_fn(q, lang)
                except Exception:  # noqa: BLE001 — translation is best-effort
                    continue
                if translated and not _add(translated):
                    return out

    return out
