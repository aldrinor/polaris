"""Post-extraction content quality scoring (v3 Hybrid RC-4).

Rejects garbled, boilerplate, and low-information content before it enters
the evidence pipeline. All heuristic — no LLM calls, zero cost.

Scoring uses min(check_scores) — any single failing check vetoes the content.
This prevents the averaging bug where one 0.1 check is drowned by four 1.0 checks.

Env vars:
    PG_V3_CONTENT_QUALITY_GATE: "1" to enable (default "0")
    PG_V3_CONTENT_QUALITY_THRESHOLD: minimum quality score 0.0-1.0 (default "0.3")
"""

import re
import logging
from collections import Counter

logger = logging.getLogger(__name__)

# Boilerplate patterns
_BOILERPLATE_PATTERNS = [
    re.compile(r"cookie\s+(policy|consent|notice)", re.I),
    re.compile(r"subscribe\s+(now|to|for)", re.I),
    re.compile(r"privacy\s+policy", re.I),
    re.compile(r"terms\s+(of\s+)?(service|use)", re.I),
    re.compile(r"all\s+rights\s+reserved", re.I),
    re.compile(r"sign\s+up\s+for\s+(our|the)\s+newsletter", re.I),
    re.compile(r"share\s+this\s+(article|post|page)", re.I),
    re.compile(r"accept\s+(all\s+)?cookies", re.I),
    re.compile(r"manage\s+(cookie|consent)\s+preferences", re.I),
]

# Mojibake / encoding error patterns
_ENCODING_ERROR_PATTERNS = [
    re.compile(r"\xc3[\xa0-\xbf]"),        # Double-encoded UTF-8 (Latin-1 mojibake)
    re.compile(r"\xc2[\x80-\xbf]"),        # UTF-8 control char mojibake
    re.compile(r"\ufffd"),                  # Unicode replacement character
    re.compile(r"&[a-z]+;"),               # Unresolved HTML entities
    re.compile(r"\u2019|\u201c|\u201d"),    # Smart quotes that survived as raw Unicode
]


def score_content_quality(text: str, url: str = "") -> tuple[float, list[str]]:
    """Score content quality 0.0-1.0.

    Returns (score, reasons_for_rejection).
    Reject below PG_V3_CONTENT_QUALITY_THRESHOLD (default 0.3).

    Uses min(check_scores) so any single failing check vetoes the content.
    This fixes the averaging bug where bad content passed because 4 of 5 checks
    returned 1.0 and the average stayed above threshold.

    Six heuristic checks:
    1. Length: reject < 500 chars (likely paywall shell)
    2. Encoding quality: mojibake density
    3. Repetition: any 3-word phrase repeated 5+ times per 1000 words
    4. Boilerplate ratio: cookie/subscribe/terms density
    5. Information density: sentences with numbers or proper nouns
    6. Vocabulary diversity: unique words / total words ratio
    """
    reasons: list[str] = []
    scores: list[float] = []
    words = text.lower().split()
    word_count = max(len(words), 1)

    # 1. Length check
    stripped = text.strip()
    if len(stripped) < 500:
        reasons.append(f"too_short:{len(stripped)}")
        scores.append(0.1)
    else:
        scores.append(1.0)

    # 2. Encoding quality: mojibake density
    encoding_errors = sum(len(p.findall(text)) for p in _ENCODING_ERROR_PATTERNS)
    encoding_ratio = encoding_errors / word_count
    if encoding_ratio > 0.05:
        reasons.append(f"mojibake:{encoding_ratio:.2f}")
        scores.append(0.1)
    elif encoding_ratio > 0.02:
        reasons.append(f"mojibake_mild:{encoding_ratio:.2f}")
        scores.append(0.4)
    else:
        scores.append(1.0)

    # 3. Repetition detection: any 3-word phrase repeated excessively
    # Threshold scales with document length: 5 per 1000 words
    if len(words) >= 10:
        trigrams = [" ".join(words[i:i + 3]) for i in range(len(words) - 2)]
        trigram_counts = Counter(trigrams)
        # Skip trivially common trigrams (articles, prepositions)
        _trivial = {"the", "a", "an", "of", "in", "to", "for", "and", "is", "it", "on", "at", "by"}
        max_repeat = 0
        top_trigram = ""
        for tg, cnt in trigram_counts.most_common(5):
            tg_words = set(tg.split())
            # Skip trigrams where all words are trivial
            if tg_words.issubset(_trivial):
                continue
            if cnt > max_repeat:
                max_repeat = cnt
                top_trigram = tg

        repeat_threshold = max(5, word_count // 200)  # ~5 per 1000 words
        if max_repeat >= repeat_threshold:
            reasons.append(f"repetition:{top_trigram}x{max_repeat}")
            scores.append(0.15)
        else:
            scores.append(1.0)
    else:
        scores.append(1.0)

    # 4. Boilerplate ratio: boilerplate matches per 100 words
    boilerplate_matches = sum(len(p.findall(text)) for p in _BOILERPLATE_PATTERNS)
    boilerplate_per_100w = boilerplate_matches / max(word_count / 100, 1)
    if boilerplate_per_100w > 3.0:
        reasons.append(f"boilerplate_heavy:{boilerplate_per_100w:.1f}")
        scores.append(0.1)
    elif boilerplate_per_100w > 1.0:
        reasons.append(f"boilerplate:{boilerplate_per_100w:.1f}")
        scores.append(0.25)
    else:
        scores.append(1.0)

    # 5. Information density: sentences with numbers or proper nouns
    sentences = re.split(r'(?<=[.!?])\s+', text)
    if len(sentences) >= 3:
        info_sentences = sum(
            1 for s in sentences
            if re.search(r'\d+\.?\d*|[A-Z][a-z]{2,}', s)
        )
        info_ratio = info_sentences / max(len(sentences), 1)
        if info_ratio < 0.15:
            reasons.append(f"low_info_density:{info_ratio:.2f}")
            scores.append(0.2)
        elif info_ratio < 0.30:
            reasons.append(f"mild_low_info:{info_ratio:.2f}")
            scores.append(0.5)
        else:
            scores.append(1.0)
    else:
        scores.append(0.5)

    # 6. Vocabulary diversity: unique words / total words
    # Garbled or machine-translated text often has very low diversity
    if word_count >= 50:
        unique_ratio = len(set(words)) / word_count
        if unique_ratio < 0.15:
            reasons.append(f"low_vocab_diversity:{unique_ratio:.2f}")
            scores.append(0.15)
        elif unique_ratio < 0.25:
            reasons.append(f"mild_low_vocab:{unique_ratio:.2f}")
            scores.append(0.4)
        else:
            scores.append(1.0)
    else:
        scores.append(1.0)

    # Use MIN — any single check failing should veto the content.
    # The old average formula let bad content through: avg(1,1,0.1,1,1)=0.82
    overall = min(scores) if scores else 0.0
    return round(overall, 3), reasons
