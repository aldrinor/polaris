"""Script-aware content tokenization for the strict_verify grounding floor (L4).

I-deepfix-001 L4 (GH #1344) — CJK / multilingual-aware strict_verify.

WHY THIS EXISTS
---------------
The faithfulness engine's content-word-overlap floor was tuned on English: both
``provenance_generator._content_words`` and
``clinical_generator.strict_verify._content_words`` extract tokens with a
Latin-only regex (``[A-Za-z]...``). On a non-Latin claim that regex returns the
EMPTY set, which produced TWO unacceptable behaviours:

  * recall loss — a genuine Chinese/Japanese/Korean/Arabic claim that IS grounded
    in its cited span mis-counts ZERO shared content words and is dropped
    spuriously; and, worse,
  * a FAITHFULNESS HOLE — where the caller SKIPS the overlap floor when the
    sentence has no Latin content words (``if sentence_content:``), a non-Latin
    claim could ride through with NO lexical grounding at all.

The second is lethal in the Telus clinical context.

WHAT THIS MODULE DOES
---------------------
It is an ADDITIVE, script-aware companion to each caller's existing Latin
extractor. The caller keeps its own Latin path byte-for-byte (English behaviour
is unchanged) and UNIONS the tokens produced here:

  * CJK (Han ideographs, Hiragana, Katakana, Hangul) has no word spaces, so we
    emit overlapping CHARACTER BIGRAMS — the standard IR segmentation for CJK
    (cf. Lucene ``CJKBigramFilter``). Identical CJK substrings in a claim and its
    span therefore share bigrams and overlap correctly.
  * Other space-delimited non-Latin scripts (Arabic, Cyrillic, Greek, Hebrew,
    Armenian, Georgian, Devanagari, ...) are whitespace-tokenized into whole-word
    tokens the same way Latin is.

FAIL-CLOSED, NEVER GUESS
------------------------
Scripts that have NO word spaces AND no bigram convention we trust (Thai, Lao,
Khmer, Myanmar, Tibetan) cannot be segmented without a language model / dictionary
we do not run here. For those, ``has_unsegmentable_content`` returns True so the
caller FAILS CLOSED (drops the sentence) rather than guessing a grounding it
cannot establish. This only ever TIGHTENS the engine; it relaxes nothing.

All behaviour is env-gated (LAW VI) and DEFAULT-OFF: with
``PG_STRICT_VERIFY_SCRIPT_AWARE`` UNSET (the production default) this module is a
no-op that is byte-identical to the pre-L4 Latin-only engine. Set
``PG_STRICT_VERIFY_SCRIPT_AWARE=1`` (or ``true``/``on``/``yes``) to turn on the
multilingual grounding tightening. The default-OFF revert contract is what keeps
an English/production run's strict_verify behaviour unchanged until the run
config deliberately opts in.
"""

from __future__ import annotations

import os
import re

# ── Env kill-switch (LAW VI) ────────────────────────────────────────────────
_ENV_SCRIPT_AWARE = "PG_STRICT_VERIFY_SCRIPT_AWARE"

# ── CJK ranges (bigram-segmented; no word spaces) ───────────────────────────
# Han (Unified + Ext-A + Compat) + Hiragana/Katakana (+ phonetic ext + halfwidth)
# + Hangul syllables + Han Ext-B..F (astral). Anything here is grouped into
# overlapping character bigrams.
_CJK_CLASS = (
    "㐀-䶿"          # CJK Unified Ideographs Extension A
    "一-鿿"          # CJK Unified Ideographs
    "豈-﫿"          # CJK Compatibility Ideographs
    "぀-ヿ"          # Hiragana + Katakana
    "ㇰ-ㇿ"          # Katakana Phonetic Extensions
    "ｦ-ﾟ"          # Halfwidth Katakana
    "가-힣"          # Hangul Syllables
    "\U00020000-\U0003ffff"  # CJK Unified Ideographs Extension B..F (astral)
)
_CJK_RE = re.compile(f"[{_CJK_CLASS}]+")
_CJK_ANY = re.compile(f"[{_CJK_CLASS}]")

# ── Unsegmentable ranges (no spaces, no trusted bigram convention) ──────────
# A run of >=2 of these letters => we cannot segment => fail-closed. A lone
# stray character does not trip the guard (avoids false-dropping an English
# sentence with a single decorative glyph).
_UNSEGMENTABLE_CLASS = (
    "฀-๿"  # Thai
    "຀-໿"  # Lao
    "ༀ-࿿"  # Tibetan
    "က-႟"  # Myanmar
    "ក-៿"  # Khmer
)
_UNSEGMENTABLE_RUN_RE = re.compile(f"[{_UNSEGMENTABLE_CLASS}]{{2,}}")

# ── Word run of ANY Unicode letter (script-agnostic) ────────────────────────
# ``[^\W\d_]`` = a word character that is neither a digit nor underscore = a
# Unicode letter in any script. Used to pick out non-Latin, non-CJK
# space-delimited words (Arabic / Cyrillic / Greek / Hebrew / Devanagari / ...).
_LETTER_WORD_RE = re.compile(r"[^\W\d_]+", re.UNICODE)
_LATIN_ANY = re.compile(r"[A-Za-z]")
_UNSEG_ANY = re.compile(f"[{_UNSEGMENTABLE_CLASS}]")

# Minimum codepoint length for a non-Latin space-delimited word to count as a
# content token (mirrors the Latin ">=3 chars / >=2 overlap" conservatism while
# allowing 2-char CJK-adjacent scripts a fair floor).
_MIN_OTHER_WORD_LEN = 2


def script_aware_enabled() -> bool:
    """``PG_STRICT_VERIFY_SCRIPT_AWARE`` master gate (default OFF => byte-identical).

    With the env UNSET (the production default) this returns ``False`` and the
    module is a no-op: both public helpers return their empty/false identity so
    the caller's Latin-only path is byte-identical to the pre-L4 engine (LAW VI
    revert contract). Only an explicit ON value (``1``/``true``/``on``/``yes``/
    ``enabled``) activates the multilingual grounding tightening, which the run
    config opts into deliberately. Consistent with the other I-deepfix-001 W-fixes
    (all default-OFF, enabled via the run slate).
    """
    return os.getenv(_ENV_SCRIPT_AWARE, "0").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def cjk_bigrams(text: str) -> set[str]:
    """Overlapping character bigrams for every CJK run in ``text``.

    A single-character run yields the unigram (so a lone ideograph still
    produces a token). ``"糖尿病"`` -> ``{"糖尿", "尿病"}``.
    """
    out: set[str] = set()
    for run in _CJK_RE.findall(text):
        chars = list(run)
        if len(chars) == 1:
            out.add(chars[0])
            continue
        for i in range(len(chars) - 1):
            out.add(chars[i] + chars[i + 1])
    return out


def _other_script_words(text: str) -> set[str]:
    """Whole-word tokens for space-delimited NON-Latin, NON-CJK scripts.

    Latin words are the caller's own responsibility (English byte-identical);
    CJK is handled by :func:`cjk_bigrams`; unsegmentable scripts are excluded
    here and handled by :func:`has_unsegmentable_content`.
    """
    out: set[str] = set()
    for m in _LETTER_WORD_RE.finditer(text):
        w = m.group(0)
        if _LATIN_ANY.search(w):
            continue          # Latin => caller handles it
        if _CJK_ANY.search(w):
            continue          # CJK => cjk_bigrams handles it
        if _UNSEG_ANY.search(w):
            continue          # unsegmentable => fail-closed path handles it
        wl = w.lower()
        if len(wl) >= _MIN_OTHER_WORD_LEN:
            out.add(wl)
    return out


def extra_script_tokens(text: str) -> set[str]:
    """Non-Latin content tokens to UNION with the caller's Latin content words.

    Returns CJK bigrams plus space-delimited non-Latin whole words. Empty when
    the master gate is off or the text carries no non-Latin content — so a
    caller unioning this in keeps English behaviour byte-identical.
    """
    if not text or not script_aware_enabled():
        return set()
    return cjk_bigrams(text) | _other_script_words(text)


def has_unsegmentable_content(text: str) -> bool:
    """True iff ``text`` carries a run of >=2 letters in an UNSEGMENTABLE script.

    The caller must FAIL CLOSED (drop the sentence) when this is True: we cannot
    establish lexical grounding for Thai/Lao/Khmer/Myanmar/Tibetan without a
    segmenter we do not run, and guessing a pass would be the lethal
    weakened-positive failure mode. Off when the master gate is off.
    """
    if not text or not script_aware_enabled():
        return False
    return bool(_UNSEGMENTABLE_RUN_RE.search(text))
