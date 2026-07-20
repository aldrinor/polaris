#!/usr/bin/env python3
"""Text rules shared by the payload checker and the operator voice checker.

Both of those tools have to answer the same questions: is this one sentence or
five, is this one word or forty, and is there anything in the text that a
reader cannot see. When those answers lived in two files they drifted, and a
trick that was blocked in one place passed in the other. They live here now.

Standard library only. No project imports, so this file can be copied whole.
"""

from __future__ import annotations

import re
import unicodedata

# Characters that are invisible, or that reorder what a reader hears, or that
# let one string pretend to be another.
INVISIBLE = {
    0x00AD,  # soft hyphen
    0x061C,  # arabic letter mark
    0x180E,  # mongolian vowel separator
    0x200B,  # zero width space
    0x200C,  # zero width non joiner
    0x200D,  # zero width joiner
    0x200E,  # left to right mark
    0x200F,  # right to left mark
    0x2028,  # line separator
    0x2029,  # paragraph separator
    0x202A,  # left to right embedding
    0x202B,  # right to left embedding
    0x202C,  # pop directional formatting
    0x202D,  # left to right override
    0x202E,  # right to left override
    0x2060,  # word joiner
    0x2061,
    0x2062,
    0x2063,
    0x2064,
    0x2066,  # left to right isolate
    0x2067,  # right to left isolate
    0x2068,  # first strong isolate
    0x2069,  # pop directional isolate
    0xFEFF,  # zero width no break space
}

# Letters from other alphabets that look exactly like plain ones.
CONFUSABLES = {
    "А": "A", "В": "B", "Е": "E", "К": "K", "М": "M",
    "Н": "H", "О": "O", "Р": "P", "С": "C", "Т": "T",
    "У": "Y", "Х": "X", "а": "a", "е": "e", "о": "o",
    "р": "p", "с": "c", "у": "y", "х": "x", "і": "i",
    "ј": "j", "ѕ": "s", "Ј": "J", "Ѕ": "S", "І": "I",
    "Α": "A", "Β": "B", "Ε": "E", "Ζ": "Z", "Η": "H",
    "Ι": "I", "Κ": "K", "Μ": "M", "Ν": "N", "Ο": "O",
    "Ρ": "P", "Τ": "T", "Υ": "Y", "Χ": "X", "ο": "o",
}

# Dashes that are not the plain hyphen. They render the same and read the same.
DASHES = {
    "‐": "-", "‑": "-", "‒": "-", "–": "-",
    "—": "-", "―": "-", "−": "-", "﹘": "-",
    "﹣": "-", "－": "-",
}

# Sentence enders from other writing systems, folded to a plain full stop.
TERMINATORS = {
    "。": ".", "．": ".", "！": "!", "？": "?",
    "۔": ".", "।": ".", "…": ".", "‼": "!", "⁇": "?", "⁈": "?", "⁉": "!",
}

_MARK = "\x00"
_BREAK = "\x01"

# Runs of single letters each followed by a dot: e.g. i.e. a.m. U.S.A.
# Every dot inside the run is protected, not only the last one.
_LETTER_RUN = re.compile(r"\b((?:[A-Za-z]\.){2,})")
# Titles and short forms that are followed by a capital in normal writing.
_ALWAYS_ABBREV = r"\b(dr|mr|mrs|ms|prof|st|jr|sr|no|fig|vs|al|inc|ltd|co)\."
# Short forms that only hide a sentence end when a lowercase word follows.
# Written out in both casings on purpose: this pass must NOT run with the
# ignore case flag, because that flag also makes the lowercase test below
# match a capital, which is the very thing it has to reject.
_SOFT_ABBREV = r"\b([Ee]tc|[Cc]f|[Aa]pprox|[Rr]esp|[Ii]ncl|[Ee]st|[Mm]in|[Mm]ax)\."
_FILE_EXTENSION = (
    r"(?<=\w)\.(py|md|json|txt|log|ya?ml|js|ts|tsx|jsx|sh|ps1|bat|c|h|cpp|go|rs"
    r"|rb|java|kt|swift|toml|ini|cfg|csv|tsv|html?|xml|patch|diff|sql|env|lock)\b"
)

# HTML that carries structure a listener never hears.
HTML_STRUCTURE = re.compile(
    r"</?(ul|ol|li|table|thead|tbody|tr|td|th|p|div|br|blockquote|h[1-6]|dl|dd|dt)\b"
    r"[^>]*>",
    re.IGNORECASE,
)

# One word, keeping hyphenated compounds and apostrophes whole.
_WORD = re.compile(r"[^\W\d_]+(?:[-'’][^\W\d_]+)*|\d[\d.,:]*")


def ascii_safe(text: str) -> str:
    """Make text printable on a plain console."""
    out = []
    for ch in text:
        if 32 <= ord(ch) < 127 or ch == "\t":
            out.append(ch)
        else:
            out.append("<U+%04X>" % ord(ch))
    return "".join(out)


def find_invisible(text: str) -> str | None:
    """Return the first invisible or reordering character, or None."""
    for ch in text:
        if ord(ch) in INVISIBLE:
            return ch
        category = unicodedata.category(ch)
        if category in ("Cf", "Co", "Cs"):
            return ch
        if category == "Cc" and ch not in "\t\n\r":
            return ch
    return None


def fold_confusables(text: str) -> str:
    """Turn lookalike letters into the plain letter they imitate."""
    stripped = unicodedata.normalize("NFKD", text)
    stripped = "".join(c for c in stripped if not unicodedata.combining(c))
    return "".join(CONFUSABLES.get(c, c) for c in stripped)


def fold_for_matching(text: str) -> str:
    """Normalize a line before looking for banned words in it.

    Folds width and lookalike letters, turns every kind of dash into a plain
    hyphen, and removes the markdown emphasis marks that split a word in two
    on screen while reading as one word out loud.
    """
    work = unicodedata.normalize("NFKC", text)
    work = fold_confusables(work)
    work = "".join(DASHES.get(c, c) for c in work)
    work = re.sub(r"(\*{1,3}|_{1,3}|~{2})", "", work)
    return work


def normalize_terminators(text: str) -> str:
    for source, target in TERMINATORS.items():
        text = text.replace(source, target)
    return text


def split_sentences(text: str) -> list[str]:
    """Split into sentences without breaking on decimals, files or short forms.

    A line break ends a sentence even with no full stop, because a listener
    hears the pause. A capital letter straight after a full stop ends one too,
    so removing the space does not hide a sentence. Closing HTML tags that end
    a paragraph or a line also end a sentence.
    """
    work = normalize_terminators(text.strip())
    if not work:
        return []

    work = HTML_STRUCTURE.sub(_BREAK, work)
    work = re.sub(r"(\d)\.(\d)", lambda m: m.group(1) + _MARK + m.group(2), work)
    work = _LETTER_RUN.sub(lambda m: m.group(1).replace(".", _MARK), work)
    work = re.sub(
        _FILE_EXTENSION, lambda m: _MARK + m.group(1), work, flags=re.IGNORECASE
    )
    work = re.sub(
        _ALWAYS_ABBREV, lambda m: m.group(0)[:-1] + _MARK, work, flags=re.IGNORECASE
    )
    work = re.sub(
        _SOFT_ABBREV + r"(?=\s+[a-z])", lambda m: m.group(0)[:-1] + _MARK, work
    )

    work = re.sub(r"[\r\n]+", " %s " % _BREAK, work)
    # A capital straight after a full stop starts a new sentence, so deleting
    # the space does not hide one. Lower case is left alone, because that is
    # how a file name or a version number reads.
    work = re.sub(r"(?<=[.!?])(?=[A-ZÀ-ÞĀ-ſ])", " ", work)

    pieces = re.split(r"(?<=[.!?])\s+|\s*%s\s*" % _BREAK, work)
    return [p.replace(_MARK, ".").strip() for p in pieces if p and p.strip()]


def count_sentences(text: str) -> int:
    return len(split_sentences(text))


def count_words(sentence: str) -> int:
    """Count spoken words. Slashes and punctuation do not join words together."""
    return len(_WORD.findall(sentence))


def build_term_pattern(term: str) -> re.Pattern:
    """One banned word or phrase, with the endings it really takes.

    The old pattern glued endings onto the whole word, so `leverage` plus `ing`
    asked for `leverageing` and the real word `leveraging` walked through. A
    word ending in a silent e drops it first, and a word ending in y turns it
    into ies.
    """
    parts = [p for p in re.split(r"[-\s]+", term.strip()) if p]
    if not parts:
        raise ValueError("A banned term cannot be empty.")

    last = parts[-1]
    if len(last) > 2 and last.endswith("e"):
        stem = re.escape(last[:-1])
        tail = stem + r"(?:e(?:s|d|ly)?|es|ed|ing|ence|ance|ement|ation)"
    elif len(last) > 2 and last.endswith("y"):
        stem = re.escape(last[:-1])
        tail = stem + r"(?:y|ies|ily|ied)"
    else:
        tail = re.escape(last) + r"(?:s|es|d|ed|ing|ly|ally|ness|ity)?"

    head = [re.escape(p) for p in parts[:-1]]
    core = r"[-\s]+".join(head + [tail]) if head else tail
    # A hyphen is a boundary, not part of the word, so `leverage-based` is caught.
    return re.compile(r"(?<!\w)" + core + r"(?!\w)", re.IGNORECASE)
