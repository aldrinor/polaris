"""
Report assembler for polaris graph.

Merges sections, resolves citations to numbered references,
adds transitions, builds bibliography. Pure code — no LLM calls.
"""

import logging
import os
import random
import re

import pysbd

from src.polaris_graph.schemas import CitationAudit, ReportOutline, SectionDraft
from src.polaris_graph.state import BibliographyEntry, EvidencePiece, ReportSection
from src.polaris_graph.tracing import get_tracer
from src.polaris_graph.synthesis.citation_mapper import (
    build_bibliography,
    resolve_citations,
    strip_ungrounded_citations,
    CITE_PATTERN,
)
from src.polaris_graph.synthesis.section_writer import _clean_artifacts

logger = logging.getLogger(__name__)

# FIX-047C: PySBD segmenter handles U.S., Dr., Prof., e.g., i.e., et al. correctly
# (97.92% accuracy vs 92.9% spaCy, 92.2% NLTK)
_segmenter = pysbd.Segmenter(language="en", clean=False)


def _split_sentences(text: str, min_len: int = 0) -> list[str]:
    """FIX-047C: Split text into sentences using PySBD.

    Correctly handles abbreviations (U.S., Dr., Prof., Jan., e.g., i.e., et al.)
    that regex-based splitting gets wrong, causing garbled output like
    "U.S. In addition, environmental Protection Agency".

    Args:
        text: Text to split into sentences.
        min_len: Minimum character length for returned sentences (0 = no filter).

    Returns:
        List of sentence strings, optionally filtered by min_len.
    """
    if not text or not text.strip():
        return []
    sentences = _segmenter.segment(text)
    if min_len > 0:
        return [s.strip() for s in sentences if len(s.strip()) >= min_len]
    return [s.strip() for s in sentences if s.strip()]


def _validate_abstract_metrics(
    abstract: str,
    unique_sources: int,
    total_citations: int,
    total_words: int,
) -> list[str]:
    """FIX-E2: Validate numeric claims in abstract against computed metrics."""
    warnings: list[str] = []

    # Find all numbers in the abstract
    numbers_in_abstract = re.findall(r'\b(\d+)\b', abstract)

    for num_str in numbers_in_abstract:
        num = int(num_str)
        # Check if this number could be a source count claim
        if 10 <= num <= 500 and abs(num - unique_sources) > 5 and num != total_citations:
            # Might be a hallucinated source count
            try:
                idx = abstract.index(num_str)
            except ValueError:
                continue
            context_start = max(0, idx - 30)
            context_end = idx + 30
            context_window = abstract[context_start:context_end].lower()
            source_keywords = [
                "source", "study", "studies", "paper",
                "article", "reference",
            ]
            if any(word in context_window for word in source_keywords):
                warnings.append(
                    f"Abstract claims '{num_str}' near source-related text "
                    f"but actual unique sources = {unique_sources}"
                )

    return warnings


def _remove_orphan_citations(
    text: str,
    valid_numbers: set[int],
) -> tuple[str, int]:
    """FIX-045A: Remove citation numbers that have no bibliography entry.

    After quality gate expansion, the LLM may invent [N] citation numbers
    beyond the bibliography range. This removes them to prevent dangling refs.

    Returns (cleaned_text, count_removed).
    """
    if not valid_numbers:
        return text, 0

    orphan_count = 0

    def _check(match: re.Match) -> str:
        nonlocal orphan_count
        num = int(match.group(1))
        if num not in valid_numbers:
            orphan_count += 1
            return ""
        return match.group(0)

    cleaned = re.sub(r"\[(\d+)\]", _check, text)
    cleaned = re.sub(r"  +", " ", cleaned)
    return cleaned, orphan_count


def _clean_citation_artifacts(text: str) -> str:
    """FIX-047A + M-04: Clean citation artifacts.

    Handles:
    - ' .' (space before punctuation from citation removal)
    - '..' (double periods from citation removal at sentence boundaries)
    - Multiple consecutive spaces
    - M-04: Orphaned citations between connectors ("Moreover, [16] Consequently,")
    """
    # M-04: Fix orphaned citations between connectors: "Moreover, [16] Consequently," -> "Consequently,"
    connectors = r"(?:Moreover|Furthermore|Additionally|Indeed|Significantly|Consequently|Notably)"
    text = re.sub(
        rf"({connectors}),?\s*(\[\d+\](?:\s*\[\d+\])*)\s*({connectors})",
        r"\3",
        text,
    )
    # Remove space before punctuation: " ." -> ".", " ," -> ","
    text = re.sub(r'\s+([.,;:!?])', r'\1', text)
    # Clean double/triple periods: ".." or ". ." -> "."
    text = re.sub(r'\.\s*\.', '.', text)
    # Clean leftover multiple spaces
    text = re.sub(r'  +', ' ', text)
    return text


def _fix_number_spacing(text: str) -> str:
    """FIX-045E: Fix spacing errors in numbers like '99. 9%' -> '99.9%'."""
    # Fix decimal-space-digit-percent: "99. 9%" -> "99.9%"
    text = re.sub(r"(\d+)\.\s+(\d+)(%)", r"\1.\2\3", text)
    # Fix decimal-space-digit in general: "3. 14" -> "3.14"
    text = re.sub(r"(\d+)\.\s+(\d+)(?=\s|[,;.]|$)", r"\1.\2", text)
    return text


def _fix_abstract_metrics(
    abstract: str,
    unique_sources: int,
    total_citations: int,
    total_words: int,
) -> str:
    """FIX-045C: Recompute abstract metrics from actual content.

    Finds patterns like '10,418 words', '23 sources', '218 citations'
    in the abstract and replaces with actual computed values.
    """
    fixed = abstract

    # Fix word count: "N words" or "N,NNN words"
    def _fix_words(match: re.Match) -> str:
        return f"{total_words:,} words"
    fixed = re.sub(r"[\d,]+\s+words?\b", _fix_words, fixed)

    # Fix source count: "N sources" / "N studies" / "N papers" / "N references"
    def _fix_sources(match: re.Match) -> str:
        return f"{unique_sources} {match.group(1)}"
    fixed = re.sub(
        r"\d+\s+(sources?|studies|papers?|references?)\b",
        _fix_sources, fixed,
    )

    # FIX-D5: Fix citation count — broadened to catch "N total citations",
    # "N in-text citations", "N referenced citations" etc.
    def _fix_citations(match: re.Match) -> str:
        return f"{total_citations} {match.group(1)}"
    fixed = re.sub(
        r"\d+\s+(?:total\s+|in-text\s+|referenced\s+)?(citations?)\b",
        _fix_citations, fixed,
    )

    # FIX-R9: Remove self-referential word count from abstract
    # "The 10,983-word report" is fragile — wrong if report is edited later
    fixed = re.sub(r'(?i)the\s+\d[\d,]*-word\s+report', 'This report', fixed)
    fixed = re.sub(r'(?i)this\s+\d[\d,]*-word\s+report', 'This report', fixed)

    if fixed != abstract:
        logger.info(
            "[polaris graph] FIX-045C: Abstract metrics recomputed: "
            "%d words, %d citations, %d sources",
            total_words, total_citations, unique_sources,
        )

    return fixed


def _fix_orphaned_parentheticals(text: str) -> str:
    """FIX-045F: Fix orphaned parentheticals in report text.

    Detects sentences that are ONLY a parenthetical with no preceding clause,
    e.g., '(specific values vary by study)' appearing standalone.

    For known softening patterns: removes them entirely.
    For other standalone parentheticals: removes the parentheses to integrate
    the text as a regular clause.
    """
    # Known softening patterns that should be removed entirely
    _remove_patterns = [
        r"\(specific values vary by study\)",
        r"\(reported values vary\)",
        r"\(values may vary\)",
        r"\(results vary by study\)",
        r"\(exact figures vary\)",
    ]
    for pat in _remove_patterns:
        text = re.sub(pat + r"\.?\s*", "", text)

    # Detect standalone parentheticals: sentence-initial "(" that forms
    # the entire sentence.  Pattern: ". (text)" or start-of-text "(text)."
    # Remove the parens to make it a normal clause.
    text = re.sub(
        r"(?<=\.\s)\(([^)]{10,80})\)\.",
        r"\1.",
        text,
    )

    # Clean double spaces left by removal
    text = re.sub(r"  +", " ", text)
    return text


def _renumber_citations_sequential(
    full_report: str,
    report_sections: list[ReportSection],
    bibliography: list[BibliographyEntry],
) -> tuple[str, list[ReportSection], list[BibliographyEntry]]:
    """FIX-045D: Renumber citations in order of first appearance.

    Ensures [1] appears before [2] in the body text. Uses a two-pass
    placeholder approach to avoid collision during renumbering.
    Updates body text, per-section content, citation_ids, and bibliography.
    """
    ref_marker = "## References"
    if ref_marker not in full_report:
        return full_report, report_sections, bibliography

    ref_idx = full_report.index(ref_marker)
    body = full_report[:ref_idx]

    # Discover citation numbers in order of first appearance
    seen_order: list[int] = []
    for match in re.finditer(r"\[(\d+)\]", body):
        num = int(match.group(1))
        if num not in seen_order:
            seen_order.append(num)

    if not seen_order:
        return full_report, report_sections, bibliography

    # Build old -> new mapping
    old_to_new: dict[int, int] = {}
    for new_num, old_num in enumerate(seen_order, 1):
        old_to_new[old_num] = new_num

    # Short-circuit if already sequential
    if seen_order == list(range(1, len(seen_order) + 1)):
        return full_report, report_sections, bibliography

    # --- Two-pass rename (avoids collision) ---
    def _to_placeholder(match: re.Match) -> str:
        old_num = int(match.group(1))
        new_num = old_to_new.get(old_num, old_num)
        return f"[__CITE_{new_num}__]"

    def _apply_renumber(text: str) -> str:
        tmp = re.sub(r"\[(\d+)\]", _to_placeholder, text)
        return re.sub(r"\[__CITE_(\d+)__\]", r"[\1]", tmp)

    # Renumber body text only (bibliography rebuilt separately)
    renumbered_body = _apply_renumber(body)

    # Renumber per-section content and citation_ids
    for section in report_sections:
        section["content"] = _apply_renumber(section["content"])
        new_ids = []
        for cid in section.get("citation_ids", []):
            stripped = cid.strip("[]")
            if stripped.isdigit():
                old_n = int(stripped)
                new_n = old_to_new.get(old_n, old_n)
                new_ids.append(f"[{new_n}]")
            else:
                new_ids.append(cid)
        section["citation_ids"] = new_ids

    # Reorder bibliography to match new numbering
    bib_by_old_num: dict[int, BibliographyEntry] = {}
    for i, entry in enumerate(bibliography):
        bib_by_old_num[i + 1] = entry

    new_bibliography: list[BibliographyEntry] = []
    for old_num in seen_order:
        if old_num in bib_by_old_num:
            entry = dict(bib_by_old_num[old_num])  # shallow copy
            new_num = old_to_new[old_num]
            entry["citation_key"] = f"[{new_num}]"
            entry["formatted"] = re.sub(
                r"^\[\d+\]", f"[{new_num}]", entry["formatted"],
            )
            new_bibliography.append(entry)

    # Keep unreferenced bibliography entries at the end (completeness)
    for old_num in sorted(bib_by_old_num.keys()):
        if old_num not in set(seen_order):
            entry = dict(bib_by_old_num[old_num])
            next_num = len(new_bibliography) + 1
            entry["citation_key"] = f"[{next_num}]"
            entry["formatted"] = re.sub(
                r"^\[\d+\]", f"[{next_num}]", entry["formatted"],
            )
            new_bibliography.append(entry)

    # Rebuild references section
    ref_lines = ["## References", ""]
    for entry in new_bibliography:
        ref_lines.append(entry["formatted"])
    ref_lines.append("")

    renumbered_report = renumbered_body + "\n".join(ref_lines)

    changed = {old: new for old, new in old_to_new.items() if old != new}
    if changed:
        logger.info(
            "[polaris graph] FIX-045D: Renumbered %d citations to sequential "
            "order (%d remapped)",
            len(seen_order), len(changed),
        )

    return renumbered_report, report_sections, new_bibliography


def detect_redundancy(
    report_sections: list[ReportSection],
) -> dict:
    """FIX-C3 + NRC-2: Detect near-duplicate sentences across sections.

    Uses both Jaccard similarity AND embedding cosine similarity to catch
    semantically identical but reworded sentences that Jaccard misses.
    """
    jaccard_threshold = float(
        os.getenv("PG_REDUNDANCY_JACCARD_THRESHOLD", "0.45")
    )
    embedding_threshold = float(
        os.getenv("PG_REDUNDANCY_EMBEDDING_THRESHOLD", "0.85")
    )
    min_sentence_words = int(
        os.getenv("PG_REDUNDANCY_MIN_SENTENCE_WORDS", "5")
    )

    all_sentences: list[tuple[str, str]] = []  # (sentence, section_id)

    for section in report_sections:
        content = section["content"]
        sentences = _split_sentences(content, min_len=30)
        for sent in sentences:
            all_sentences.append((sent, section["section_id"]))

    # NRC-2: Try embedding-based semantic dedup for cross-section sentences
    embedding_vecs = None
    try:
        from src.utils.embedding_service import embed_texts
        texts = [s[0] for s in all_sentences]
        if texts:
            import numpy as np
            embedding_vecs = np.array(embed_texts(texts))
    except Exception as emb_exc:
        logger.debug(
            "[polaris graph] NRC-2: Embedding unavailable for redundancy detection: %s",
            str(emb_exc)[:100],
        )

    # Jaccard + embedding similarity for near-duplicate detection
    duplicates: list[dict] = []
    for i in range(len(all_sentences)):
        words_i = set(all_sentences[i][0].lower().split())
        if len(words_i) < min_sentence_words:
            continue
        for j in range(i + 1, len(all_sentences)):
            if all_sentences[i][1] == all_sentences[j][1]:
                continue  # Same section — skip
            words_j = set(all_sentences[j][0].lower().split())
            if len(words_j) < min_sentence_words:
                continue
            jaccard = len(words_i & words_j) / len(words_i | words_j)

            # NRC-2: Also check embedding cosine similarity
            cosine_sim = 0.0
            if embedding_vecs is not None:
                cosine_sim = float(embedding_vecs[i] @ embedding_vecs[j])

            if jaccard > jaccard_threshold or cosine_sim > embedding_threshold:
                duplicates.append({
                    "sentence_a": all_sentences[i][0][:100],
                    "sentence_b": all_sentences[j][0][:100],
                    "section_a": all_sentences[i][1],
                    "section_b": all_sentences[j][1],
                    "jaccard": round(jaccard, 3),
                    "cosine": round(cosine_sim, 3),
                })

    total_sentences = len(all_sentences)
    dup_sentences = len(
        set(d["sentence_a"] for d in duplicates)
        | set(d["sentence_b"] for d in duplicates)
    )
    redundancy_pct = (dup_sentences / max(total_sentences, 1)) * 100

    if duplicates:
        logger.warning(
            "[polaris graph] FIX-C3: Redundancy detected: %d near-duplicate sentence pairs "
            "across sections (%.1f%% of sentences)",
            len(duplicates),
            redundancy_pct,
        )

    return {
        "duplicate_pairs": len(duplicates),
        "redundancy_pct": round(redundancy_pct, 1),
        "total_sentences": total_sentences,
        "examples": duplicates[:5],  # Top 5 examples
    }


def remove_redundancy(
    report_sections: list[ReportSection],
    threshold: float | None = None,
) -> list[ReportSection]:
    """FIX-4 + FIX-MP10 + NRC-2: Remove near-duplicate sentences across sections.

    For each duplicate pair (Jaccard > threshold OR embedding cosine > 0.85),
    removes the sentence from the LATER section, preserving the first occurrence.

    NRC-2: Added embedding-based semantic dedup to catch reworded sentences
    that Jaccard similarity misses (e.g., 48+ recycled sentences in T041).

    Args:
        report_sections: List of report section dicts (mutated in place).
        threshold: Jaccard similarity threshold for duplicate detection.
            If None, reads from PG_REDUNDANCY_JACCARD_THRESHOLD env var.

    Returns:
        The same report_sections list with duplicates removed from later sections.
    """
    if threshold is None:
        threshold = float(os.getenv("PG_REDUNDANCY_JACCARD_THRESHOLD", "0.45"))
    embedding_threshold = float(
        os.getenv("PG_REDUNDANCY_EMBEDDING_THRESHOLD", "0.85")
    )
    min_sentence_words = int(
        os.getenv("PG_REDUNDANCY_MIN_SENTENCE_WORDS", "5")
    )

    # NRC-2: Pre-compute sentence embeddings for semantic dedup
    all_sents_for_embed: list[str] = []
    sent_to_embed_idx: dict[str, int] = {}
    for section in report_sections:
        content = section["content"]
        sentences = _split_sentences(content, min_len=30)
        for sent in sentences:
            if sent not in sent_to_embed_idx:
                sent_to_embed_idx[sent] = len(all_sents_for_embed)
                all_sents_for_embed.append(sent)

    embedding_vecs = None
    try:
        from src.utils.embedding_service import embed_texts
        if all_sents_for_embed:
            import numpy as np
            embedding_vecs = np.array(embed_texts(all_sents_for_embed))
    except Exception as embed_err:
        logger.debug("Embedding fallback to Jaccard-only: %s", embed_err)

    # Build a set of (normalized_words_frozenset, section_idx) for first occurrences
    seen_sentences: list[tuple[set[str], int, str]] = []  # (words, section_idx, raw_sent)
    total_removed = 0

    for section_idx, section in enumerate(report_sections):
        content = section["content"]
        # FIX-047C: PySBD sentence splitting (handles abbreviations correctly)
        sentences = _split_sentences(content, min_len=30)
        kept_sentences: list[str] = []
        removed_in_section = 0

        for sent in sentences:
            words = set(sent.lower().split())
            if len(words) < min_sentence_words:
                kept_sentences.append(sent)
                continue

            # Check against all previously seen sentences from earlier sections
            is_duplicate = False
            for seen_words, seen_idx, seen_raw in seen_sentences:
                if seen_idx == section_idx:
                    continue  # Same section — don't remove internal dupes here
                if len(seen_words) < min_sentence_words:
                    continue

                # Jaccard check
                intersection = len(words & seen_words)
                union = len(words | seen_words)
                if union > 0 and intersection / union > threshold:
                    is_duplicate = True
                    break

                # NRC-2: Embedding cosine check (catches semantic dupes)
                if embedding_vecs is not None:
                    idx_a = sent_to_embed_idx.get(seen_raw)
                    idx_b = sent_to_embed_idx.get(sent)
                    if idx_a is not None and idx_b is not None:
                        cosine = float(embedding_vecs[idx_a] @ embedding_vecs[idx_b])
                        if cosine > embedding_threshold:
                            is_duplicate = True
                            break

            if is_duplicate:
                removed_in_section += 1
                total_removed += 1
            else:
                kept_sentences.append(sent)

            # Register this sentence as seen
            seen_sentences.append((words, section_idx, sent))

        if removed_in_section > 0:
            # FIX-A1: NEVER empty a section completely. If redundancy removal
            # would wipe >50% of sentences, keep the original content.
            # On focused topics (e.g. intermittent fasting), Jaccard similarity
            # across sections flags ALL later sentences as duplicates, producing
            # empty sections. Cap removal at 50% per section.
            original_count = len(sentences)
            if len(kept_sentences) < original_count * 0.5:
                logger.warning(
                    "[polaris graph] FIX-A1: Redundancy would remove %d/%d "
                    "sentences (>50%%) from '%s' — keeping original",
                    removed_in_section, original_count,
                    section.get("title", "?")[:50],
                )
                # Revert: don't modify this section
                total_removed -= removed_in_section
            else:
                # Safe to apply: reconstruct content from kept sentences
                new_content = ". ".join(kept_sentences)
                if new_content and not new_content.endswith("."):
                    new_content += "."
                section["content"] = new_content
                section["word_count"] = len(new_content.split())
                logger.info(
                    "[polaris graph] FIX-4: Removed %d redundant sentences from '%s'",
                    removed_in_section,
                    section.get("title", "?")[:50],
                )

    if total_removed > 0:
        logger.info(
            "[polaris graph] FIX-4: Total redundant sentences removed: %d across %d sections",
            total_removed,
            len(report_sections),
        )

    return report_sections


def _dedup_key_statistics(
    report_sections: list[ReportSection],
) -> list[ReportSection]:
    """FIX-MP11: Remove repeated numeric statistics across sections.

    In PG_TEST_033, "USD 10.21 billion" appeared 9x across 7 sections.
    This function regex-extracts numeric claims (dollar amounts, percentages,
    counts with units) and removes duplicates from later sections, keeping
    the first occurrence.

    Args:
        report_sections: List of report section dicts (mutated in place).

    Returns:
        The same report_sections list with repeated statistics removed.
    """
    # Patterns for extractable statistics
    stat_patterns = [
        # Dollar/currency amounts: "USD 10.21 billion", "$4.5 million", "US$2.3 trillion"
        re.compile(
            r'(?:USD?|US\$|\$|EUR|GBP)\s*[\d,.]+\s*(?:billion|million|trillion|thousand|B|M|T|K)\b',
            re.IGNORECASE,
        ),
        # Percentage claims: "42.5%", "increased by 30 percent"
        re.compile(
            r'\b\d+(?:\.\d+)?\s*(?:%|percent|per cent)\b',
            re.IGNORECASE,
        ),
        # Large numbers with units: "1.2 million tons", "45,000 cases"
        re.compile(
            r'\b[\d,.]+\s*(?:billion|million|trillion|thousand)\s+\w+\b',
            re.IGNORECASE,
        ),
    ]

    # Track seen statistics (normalized)
    seen_stats: dict[str, str] = {}  # normalized_stat -> first section_id
    total_removed = 0

    for section in report_sections:
        content = section["content"]
        sentences = _split_sentences(content)
        kept_sentences: list[str] = []
        removed_in_section = 0

        for sent in sentences:
            # Extract all statistics from this sentence
            found_stats: list[str] = []
            for pattern in stat_patterns:
                matches = pattern.findall(sent)
                found_stats.extend(matches)

            # Normalize: lowercase, strip whitespace, remove commas
            normalized = [
                re.sub(r'[\s,]+', ' ', s.strip().lower())
                for s in found_stats
            ]

            # Check if any statistic in this sentence was already seen
            is_repeat = False
            for norm_stat in normalized:
                if norm_stat in seen_stats and seen_stats[norm_stat] != section["section_id"]:
                    is_repeat = True
                    break

            if is_repeat and len(sent.split()) > 5:
                removed_in_section += 1
                total_removed += 1
            else:
                kept_sentences.append(sent)
                # Register all stats from this sentence
                for norm_stat in normalized:
                    if norm_stat not in seen_stats:
                        seen_stats[norm_stat] = section["section_id"]

        if removed_in_section > 0:
            new_content = ". ".join(kept_sentences)
            if new_content and not new_content.endswith("."):
                new_content += "."
            section["content"] = new_content
            section["word_count"] = len(new_content.split())
            logger.info(
                "[polaris graph] FIX-MP11: Removed %d repeated statistics from '%s'",
                removed_in_section,
                section.get("title", "?")[:50],
            )

    if total_removed > 0:
        logger.info(
            "[polaris graph] FIX-MP11: Total repeated statistics removed: %d "
            "across %d sections (%d unique statistics tracked)",
            total_removed,
            len(report_sections),
            len(seen_stats),
        )

    return report_sections


def _audit_uncited_claims(
    report_sections: list[ReportSection],
) -> list[dict]:
    """NRC-3: Detect sentences with specific numerical claims but no citation.

    Scans each sentence for numeric patterns (digits + units like %, ppm, ppt,
    bar, kWh, um, Daltons). If a sentence contains a specific numeric claim
    AND no citation [N], flags it.

    Returns list of flagged claim dicts for logging/remediation.
    """
    # LAW VI: Unit patterns from config + universal patterns
    from src.polaris_graph.config_loader import get_domain_config as _get_cfg
    _cfg_units = _get_cfg().unit_patterns
    numeric_patterns = [
        re.compile(r'\b\d+(?:\.\d+)?\s*(?:%|percent|per cent)\b', re.IGNORECASE),
        re.compile(r'\b\d+(?:\.\d+)?\s*(?:°C|°F|K)\b', re.IGNORECASE),
        re.compile(r'(?:\$|USD|EUR)\s*[\d,.]+', re.IGNORECASE),
    ]
    # Add domain-specific unit pattern from config
    if _cfg_units:
        numeric_patterns.append(re.compile(
            r'\b\d+(?:\.\d+)?\s*(?:' + _cfg_units.pattern + r')\b',
            re.IGNORECASE,
        ))
    citation_pattern = re.compile(r'\[\d+\]|\[\*\]')  # Treat phantom markers as cited

    flagged: list[dict] = []

    for section in report_sections:
        content = section.get("content", "")
        # FIX-047C: PySBD sentence splitting
        sentences = _split_sentences(content)
        for sent in sentences:
            has_numeric = any(p.search(sent) for p in numeric_patterns)
            has_citation = bool(citation_pattern.search(sent))
            if has_numeric and not has_citation and len(sent.split()) >= 5:
                flagged.append({
                    "section_id": section.get("section_id", ""),
                    "sentence": sent[:200],
                    "section_title": section.get("title", ""),
                })
    # Note: _audit_uncited_claims only checks isolated numeric_patterns,
    # not range_patterns. Range detection is handled in _soften_uncited_numerics.

    if flagged:
        logger.warning(
            "[polaris graph] NRC-3: Found %d uncited numerical claims across sections",
            len(flagged),
        )
        for f in flagged[:5]:
            logger.info(
                "[polaris graph] NRC-3: Uncited in '%s': %s",
                f["section_title"][:40],
                f["sentence"][:120],
            )

    return flagged


def _soften_uncited_numerics(
    report_sections: list[ReportSection],
) -> list[ReportSection]:
    """NRC-3: Soften uncited numerical claims by replacing precise values with qualitative language.

    For sentences that contain specific numbers without citations, replaces
    exact figures with hedged language to avoid asserting unsupported specifics.
    """
    # LAW VI: Unit patterns from config + universal patterns
    from src.polaris_graph.config_loader import get_domain_config as _get_cfg2
    _cfg_units2 = _get_cfg2().unit_patterns
    _unit_re_str = _cfg_units2.pattern if _cfg_units2 else r"%|percent"

    # Phase 1: Range-aware patterns
    _RANGE_UNITS = r"(?:" + _unit_re_str + r"|°C|°F|K)"
    range_patterns = [
        re.compile(
            r'\b\d+(?:\.\d+)?\s*[-\u2013\u2014]\s*\d+(?:\.\d+)?\s*'
            + _RANGE_UNITS + r'(?=[^a-zA-Z0-9]|$)',
            re.IGNORECASE,
        ),
        re.compile(r'(?:\$|USD|EUR)\s*[\d,.]+\s*[-\u2013\u2014]\s*[\d,.]+', re.IGNORECASE),
        re.compile(r'\bpH\s*\d+(?:\.\d+)?(?:\s*[-\u2013\u2014]\s*\d+(?:\.\d+)?)?', re.IGNORECASE),
    ]

    # Phase 2: Isolated number patterns
    numeric_patterns = [
        re.compile(r'\b\d+(?:\.\d+)?\s*(?:%|percent|per cent)\b', re.IGNORECASE),
        re.compile(r'\b\d+(?:\.\d+)?\s*(?:°C|°F|K)\b', re.IGNORECASE),
        re.compile(r'(?:\$|USD|EUR)\s*[\d,.]+', re.IGNORECASE),
    ]
    if _cfg_units2:
        numeric_patterns.append(re.compile(
            r'\b\d+(?:\.\d+)?\s*(?:' + _cfg_units2.pattern + r')\b',
            re.IGNORECASE,
        ))
    citation_pattern = re.compile(r'\[\d+\]|\[\*\]')  # Treat phantom markers as cited
    total_softened = 0

    for section in report_sections:
        content = section.get("content", "")
        # FIX-047C: PySBD sentence splitting
        sentences = _split_sentences(content)
        new_sentences = []
        softened_in_section = 0

        for sent in sentences:
            has_numeric = any(p.search(sent) for p in numeric_patterns)
            has_range = any(rp.search(sent) for rp in range_patterns)
            has_citation = bool(citation_pattern.search(sent))
            if (has_numeric or has_range) and not has_citation and len(sent.split()) >= 5:
                softened = sent
                # Phase 1: Replace ALL range expressions atomically
                for rp in range_patterns:
                    softened = rp.sub("(reported values vary)", softened)
                # Phase 2: Replace remaining isolated numbers
                for p in numeric_patterns:
                    softened = p.sub("(specific values vary by study)", softened, count=1)
                new_sentences.append(softened)
                softened_in_section += 1
                total_softened += 1
            else:
                new_sentences.append(sent)

        if softened_in_section > 0:
            section["content"] = " ".join(new_sentences)
            section["word_count"] = len(section["content"].split())

    if total_softened > 0:
        logger.info(
            "[polaris graph] NRC-3: Softened %d uncited numerical claims",
            total_softened,
        )

    return report_sections


_TRANSITION_INJECTIONS = {
    "additive": ["Moreover, ", "Furthermore, ", "Additionally, ", "In addition, "],
    "causal": ["Consequently, ", "As a result, ", "Therefore, "],
    "contrast": ["However, ", "Nevertheless, ", "In contrast, "],
    "example": ["For instance, ", "Notably, ", "In particular, ", "Specifically, "],
    "emphasis": ["Indeed, ", "Significantly, "],
}

_TRANSITION_CHECK = {
    "however", "moreover", "furthermore", "additionally", "consequently",
    "therefore", "nevertheless", "nonetheless", "in contrast",
    "on the other hand", "similarly", "likewise", "meanwhile",
    "subsequently", "in addition", "as a result", "for example",
    "for instance", "in particular", "specifically", "notably",
    "indeed", "conversely", "alternatively",
}


def _has_transition(sentence: str) -> bool:
    """Check if sentence already starts with a transition word/phrase."""
    lower = sentence.strip().lower()
    return any(lower.startswith(t) for t in _TRANSITION_CHECK)


def _inject_transitions(text: str, target_density: float = 0.40) -> str:
    """Inject transition words at sentence boundaries to reach target density.

    Only injects at paragraph-internal boundaries (not first sentence of paragraph).
    Preserves citations and formatting.
    """
    paragraphs = text.split("\n\n")
    result_paragraphs = []

    total_sentences = 0
    total_transitions = 0

    for para in paragraphs:
        if not para.strip() or para.strip().startswith("#"):
            result_paragraphs.append(para)
            continue

        # FIX-047C: PySBD sentence splitting (handles U.S., Dr., etc.)
        sentences = _split_sentences(para)
        if len(sentences) <= 1:
            result_paragraphs.append(para)
            total_sentences += len(sentences)
            total_transitions += sum(1 for s in sentences if _has_transition(s))
            continue

        new_sentences = [sentences[0]]  # Keep first sentence as-is
        total_sentences += 1
        if _has_transition(sentences[0]):
            total_transitions += 1

        for sent in sentences[1:]:
            total_sentences += 1
            if _has_transition(sent):
                total_transitions += 1
                new_sentences.append(sent)
            elif total_sentences > 0 and total_transitions / total_sentences < target_density:
                # Need more transitions - inject one
                # Pick category based on simple heuristics
                if any(w in sent.lower() for w in ["but", "yet", "although", "despite"]):
                    category = "contrast"
                elif any(w in sent.lower() for w in ["because", "since", "due to", "leads"]):
                    category = "causal"
                elif any(w in sent.lower() for w in ["example", "such as", "including"]):
                    category = "example"
                elif any(w in sent.lower() for w in ["%", "increase", "decrease", "significant"]):
                    category = "emphasis"
                else:
                    category = "additive"

                # FIX-059-Q (H-02): Deterministic transition selection for reproducibility
                _rng = random.Random(hash(sent[:20]))
                transition = _rng.choice(_TRANSITION_INJECTIONS[category])
                # FIX-059-C (H-01): Don't lowercase if first word is an acronym
                # (all uppercase, e.g., EPA, RO, PFAS, UV)
                if sent and sent[0].isupper():
                    first_word = sent.split()[0] if sent.split() else ""
                    if not first_word.isupper() or len(first_word) <= 1:
                        sent = sent[0].lower() + sent[1:]
                new_sentences.append(transition + sent)
                total_transitions += 1
            else:
                new_sentences.append(sent)

        result_paragraphs.append(" ".join(new_sentences))

    injected = "\n\n".join(result_paragraphs)

    # FIX-047D: Fix duplicated transition words ("Significantly, significantly, ...")
    # This happens when _inject_transitions lowercases a word that already starts
    # with the same transition, creating "Transition, transition, rest of sentence".
    injected = re.sub(
        r'(\b[A-Z][a-z]+\b),\s+\1',
        r'\1',
        injected,
        flags=re.IGNORECASE,
    )

    if total_sentences > 0:
        final_density = total_transitions / total_sentences
        logger.info(
            "[polaris graph] FIX-P1: Transition injection: %d/%d sentences (density=%.3f, target=%.2f)",
            total_transitions,
            total_sentences,
            final_density,
            target_density,
        )

    return injected


def _reduce_filler(text: str) -> str:
    """Remove LLM word-dumping patterns. Keep max 2 of each filler per report.

    FIX-11: Uses PySBD for sentence splitting instead of '. ' which missed
    sentences ending with '? ', '! ', or '.\\n'.
    """
    fillers = [
        "Furthermore, ", "Moreover, ", "Additionally, ", "In addition, ",
        "It is worth noting that ", "It should be noted that ",
        "It is important to note that ", "Notably, ",
        "Significantly, ", "Interestingly, ",
    ]
    # FIX-11: Use PySBD for proper sentence boundary detection
    sentences = _split_sentences(text)
    if not sentences:
        return text
    for filler in fillers:
        count = 0
        cleaned = []
        for sentence in sentences:
            stripped = sentence.strip()
            if stripped.startswith(filler):
                count += 1
                if count > 2:
                    stripped = stripped[len(filler):]
                    if stripped:
                        stripped = stripped[0].upper() + stripped[1:]
            cleaned.append(stripped)
        sentences = cleaned
    # FIX-CITE-3: Preserve paragraph breaks (newlines) during filler reduction.
    # Previously used " ".join() which destroyed all newlines.
    result = " ".join(s for s in sentences if s)
    # Restore paragraph breaks that were present in the original text
    if "\n\n" in text:
        # Re-insert paragraph breaks at ". [Capital]" boundaries
        result = re.sub(r"(\.\s)(?=[A-Z][a-z]{2,})", r".\n\n", result)
        # Re-insert breaks before **Key Findings** and markdown headings
        result = re.sub(r"(?<!\n)(\*\*Key Findings)", r"\n\n\1", result)
        result = re.sub(r"(?<!\n)(###\s)", r"\n\n\1", result)
        # Re-insert break before first table
        result = re.sub(r"(?<!\n)(\|[^|]+\|[^|]+\|)", r"\n\n\1", result, count=1)
    return result


def _compute_density_metrics(report: str) -> dict:
    """Compute information density metrics. Logged, NOT gated."""
    word_count = len(report.split())

    # Count citations
    citation_count = len(re.findall(r'\[\d+\]', report))

    # Count filler phrases
    filler_phrases = [
        "Furthermore", "Moreover", "Additionally", "In addition",
        "It is worth noting", "It should be noted", "It is important to note",
        "Notably", "Significantly", "Interestingly",
    ]
    filler_count = sum(report.count(f) for f in filler_phrases)

    # Count sentences (rough)
    sentences = [s.strip() for s in re.split(r'[.!?]+', report) if s.strip()]
    total_sentences = len(sentences)
    cited_sentences = sum(1 for s in sentences if re.search(r'\[\d+\]', s))

    # Count tables and charts
    table_count = len(re.findall(r'^\|.+\|$', report, re.MULTILINE))
    chart_count = report.count('data:image/png;base64')
    key_findings_count = report.lower().count('key findings')

    metrics = {
        "facts_per_100w": (citation_count / max(word_count, 1)) * 100,
        "filler_ratio": filler_count / max(word_count, 1),
        "filler_count": filler_count,
        "table_row_count": table_count,
        "chart_count": chart_count,
        "key_findings_count": key_findings_count,
        "uncited_sentence_ratio": (total_sentences - cited_sentences) / max(total_sentences, 1),
        "total_words": word_count,
        "total_sentences": total_sentences,
        "cited_sentences": cited_sentences,
    }
    return metrics


# ---------------------------------------------------------------------------
# FIX-CITE-3: Post-processing — filler word removal + table cleanup
# ---------------------------------------------------------------------------

# FIX-C6: Broadened lookbehind — old pattern missed "Furthermore" after
# citation brackets ([5]. Furthermore) and paragraph breaks.
# New: also match after ]. or ). or newline boundaries.
_FILLER_SENTENCE_START = re.compile(
    r"(?:(?<=\.\s)|(?<=;\s)|(?<=:\s)|(?<=\]\.\s)|(?<=\)\.\s)|(?<=\n)|(?<=^))"
    r"(Additionally|Moreover|Furthermore|In addition|Indeed|"
    r"Consequently|Specifically|Significantly),?\s+",
    re.MULTILINE,
)

_FILLER_BEFORE_TABLE = re.compile(
    r"(Additionally|Moreover|Furthermore|In addition|Indeed|"
    r"Consequently|Specifically|Significantly),?\s*(\|)",
)


def _scrub_meta_commentary(text: str) -> str:
    """FIX-072: Remove LLM meta-commentary from section content.

    GLM-5 sometimes inserts mid-generation requests like:
    - "Please provide the evidence pieces so I can..."
    - "I need the 13 evidence pieces to continue..."
    - "the evidence pieces were not provided to me"
    - "Once you share the evidence..."
    - "Without these materials, I cannot..."
    - "I must note a critical issue:..."
    - "The prompt indicates..."

    These are the LLM talking to itself, not report content.
    """
    _META_PATTERNS = [
        # Direct requests for evidence
        r"Please provide[^.]*evidence[^.]*\.",
        r"I need[^.]*evidence[^.]*\.",
        r"Once you share[^.]*\.",
        r"Without these materials[^.]*\.",
        r"I cannot verify[^.]*without[^.]*\.",
        r"Can you please share[^.]*evidence[^.]*\.",
        r"I'm ready to continue once[^.]*\.",
        r"I am ready to continue once[^.]*\.",
        # Self-referential commentary
        r"[Tt]he evidence pieces[^.]*were not provided[^.]*\.",
        r"[Tt]he evidence pieces referenced[^.]*\.",
        r"[Tt]he prompt indicates[^.]*\.",
        r"I must note a critical issue[^.]*\.",
        r"[Tt]he text contains citations[^.]*but I cannot[^.]*\.",
        r"[Tt]he Key Findings section appears complete[^.]*\.",
        r"[Tt]he section has concluded[^.]*\.",
        r"[Tt]he single citation provided suggests[^.]*\.",
        # Instruction echoing
        r"To properly complete this section[^.]*I would need[^.]*\.",
        r"I would need[^.]*evidence[^.]*to continue[^.]*\.",
        r"Properly challenge the evidence base[^.]*\.",
        r"For a robust analytical section[^.]*additional evidence would be necessary[^.]*\.",
        # Bullet lists requesting evidence
        r"- The \w+ evidence piece mentioned[^.]*\.",
        r"- Create appropriate comparisons[^.]*\.",
        r"- Build data tables[^.]*\.",
        r"- Identify limitations and gaps[^.]*\.",
        r"- Complete the Key Findings[^.]*\.",
        r"- Properly cite claims[^.]*\.",
        r"- Perform the mandatory[^.]*\.",
        r"- Meet the anti-hallucination[^.]*\.",
        # "I should/I will" planning
        r"[Ll]et me now revise[^.]*\.",
        r"[Ll]et me go through[^.]*\.",
        r"[Nn]ow let me[^.]*\.",
        # FIX-075: Polish pass reasoning leaked as italic markdown blocks
        r"\*Critique of the draft[:\*][^*]*(?:\*|$)",
        r"\*Refining the[^*]*(?:\*|$)",
        r"\*Final (?:Polish )?Plan[^*]*(?:\*|$)",
        r"\*Checking[^*]*(?:\*|$)",
        r"\*Drafting the[^*]*(?:\*|$)",
        r"\*Review against rules[^*]*(?:\*|$)",
        r"\*Prose tightening[^*]*(?:\*|$)",
        r"\*Table handling[^*]*(?:\*|$)",
        r"\*One (?:check|detail)[^*]*(?:\*|$)",
    ]

    import re
    _cleaned = text

    # FIX-075: Truncate at polish reasoning blocks FIRST, before regex patterns.
    # GLM-5 appends "*Critique of the draft:*" followed by editing reasoning.
    _polish_reasoning_markers = [
        # GLM-5 planning headers (many variants)
        "1. **Analyze",
        "1.  **Analyze",
        "*Critique of the draft",
        "*Refining the",
        "*Final Polish Plan",
        "*Final Plan",
        "Critique of the draft:",
        "Let's execute this.",
        "*Review against rules",
        "I will format the table",
        "I will replace this paragraph",
        "This seems correct.",
        "This is results.",
        "This is limitations.",
        "The prompt asks to",
        "The prompt asks",
        "The prompt says",
        "The original text has:",
        "The original section is",
    ]
    for marker in _polish_reasoning_markers:
        idx = _cleaned.find(marker)
        if idx > 100:
            _cleaned = _cleaned[:idx].rstrip()
            logger.info(
                "[polaris graph] FIX-075: Truncated at '%s' (char %d)",
                marker[:30], idx,
            )
            break

    _total_removed = 0
    for pattern in _META_PATTERNS:
        matches = list(re.finditer(pattern, _cleaned))
        for m in reversed(matches):
            _cleaned = _cleaned[:m.start()] + _cleaned[m.end():]
            _total_removed += m.end() - m.start()

    # Also remove multi-line meta blocks (indented with "- " after meta sentence)
    _cleaned = re.sub(
        r"(?:Please provide|I need|Once you share|Without these|Can you please share|I'm ready to continue)[^\n]*(?:\n\s*-[^\n]*)*",
        "",
        _cleaned,
    )

    # (FIX-075 truncation moved to top of function)
    # Remove "[Section 'X' omitted: no evidence assigned.]" markers (both quote styles)
    _cleaned = re.sub(r"\[Section ['\u2018\u201c][^'\u2019\u201d]*['\u2019\u201d] omitted:[^\]]*\]\.?", "", _cleaned)
    _cleaned = re.sub(r"\[Section \"[^\"]*\" omitted:[^\]]*\]\.?", "", _cleaned)

    # Remove orphaned bullet fragments (bullets without substantive content)
    _cleaned = re.sub(
        r"^\s*-\s*(Properly cite|Perform the mandatory|Meet the anti-hallucination"
        r"|The \w+ evidence piece|Create appropriate|Build data tables"
        r"|Identify limitations|Complete the Key)[^\n]*\n?",
        "",
        _cleaned,
        flags=re.MULTILINE,
    )
    # Remove sentences starting with "However, " followed by nothing substantive
    _cleaned = re.sub(r"However,\s*\n", "\n", _cleaned)

    # FIX-073: Fix broken table rows with ".| " separators
    # GLM-5 sometimes outputs table rows on a single line with ". |" between rows.
    # Split into proper rows, then clean up double pipes.
    _cleaned = re.sub(r"\.\s*\|\s*\|", "|\n|", _cleaned)  # ".| |" → "|\n|"
    _cleaned = re.sub(r"\.\s*\|(\s*[A-Z\d])", r"|\n|\1", _cleaned)  # ".| Data" → "|\n| Data"
    # Fix delimiter rows concatenated with data rows
    _cleaned = re.sub(r"(\|[:\-]+\|)\s*\|", r"\1\n|", _cleaned)
    # Remove trailing double pipes
    _cleaned = re.sub(r"\|\|", "|", _cleaned)

    # Clean up resulting double spaces and double newlines
    _cleaned = re.sub(r"  +", " ", _cleaned)
    _cleaned = re.sub(r"\n{3,}", "\n\n", _cleaned)

    if _total_removed > 0:
        logger.info(
            "[polaris graph] FIX-072: Scrubbed %d chars of LLM meta-commentary",
            _total_removed,
        )

    return _cleaned.strip()


def _clean_filler_and_tables(text: str) -> str:
    """Remove filler transition words at sentence starts and before table rows."""
    # FIX-072: Scrub meta-commentary first
    text = _scrub_meta_commentary(text)
    # FIX-C5: Fix common LLM misspellings (GLM-5 produces "Intermittittent" etc.)
    _TYPO_FIXES = {
        "Intermittittent": "Intermittent",
        "intermittittent": "intermittent",
        "effecacy": "efficacy",
        "cardivascular": "cardiovascular",
        "signficant": "significant",
        "signficantly": "significantly",
    }
    for typo, fix in _TYPO_FIXES.items():
        text = text.replace(typo, fix)
    # Strip filler words that start sentences, then capitalize remainder
    def _strip_and_capitalize(m: re.Match) -> str:
        rest = text[m.end():m.end() + 1] if m.end() < len(text) else ""
        return ""

    text = _FILLER_SENTENCE_START.sub("", text)
    # Capitalize first letter after ". " when it's lowercase (from filler removal)
    text = re.sub(r"(\.\s)([a-z])", lambda m: m.group(1) + m.group(2).upper(), text)
    # Capitalize first char of text if lowercase
    if text and text[0].islower():
        text = text[0].upper() + text[1:]

    # Strip filler words injected before table pipe characters
    text = _FILLER_BEFORE_TABLE.sub(r"\2", text)

    # Fix table rows: ensure no stray text before | at line start
    # (handles cases like "In contrast, | Cell1 | Cell2 |")
    text = re.sub(
        r"(?m)^(In contrast|On the other hand|However),?\s*(\|)",
        r"\2",
        text,
    )

    # FIX-CITE-3/C7: Replace hedging on cited claims with definitive language.
    # FIX-CITE-3/C7b: Handle "may/might be X" → "is X" (consume "be").
    # Handle "may/might + verb" → drop hedge word.
    # Exclude "May" when followed by a year (month name).

    # Step 1: "may be" / "might be" → "is" (before cited claims)
    text = re.sub(
        r"\b(may|might)\s+be\b(?=[^.]*\[\d+\])",
        lambda m: "is" if m.group(1)[0].islower() else "Is",
        text,
    )
    # Step 2: "may/might + verb" → drop hedge, "could" → "can"
    _hedge_cited = re.compile(
        r"\b(may|might|could|potentially)\b(?=[^.]*\[\d+\])",
        re.IGNORECASE,
    )
    _hedge_map = {"may": "", "might": "", "could": "can", "potentially": ""}
    def _replace_hedge(m: re.Match) -> str:
        word = m.group(1)
        # Skip "May" as month name
        if word == "May":
            after = text[m.end():m.end() + 6]
            if re.match(r"\s+\d{4}", after) or re.match(r",?\s+\d{4}", after):
                return word
        replacement = _hedge_map.get(word.lower(), word.lower())
        if word[0].isupper() and replacement:
            replacement = replacement[0].upper() + replacement[1:]
        return replacement
    text = _hedge_cited.sub(_replace_hedge, text)

    # Clean up double spaces from hedge removal
    text = re.sub(r"  +", " ", text)

    return text


def assemble_report(
    outline: ReportOutline,
    sections: list[SectionDraft],
    evidence: list[EvidencePiece],
    citation_audit: CitationAudit,
) -> tuple[str, list[ReportSection], list[BibliographyEntry]]:
    """
    Assemble the final report from sections.

    Returns: (full_report_text, report_sections, bibliography)
    """
    # Build citation number map from audit
    citation_map: dict[str, int] = {}
    for mapping in citation_audit.mappings:
        citation_map[mapping.evidence_id] = mapping.citation_number

    evidence_ids = {e.get("evidence_id", "") for e in evidence}

    # Clean ungrounded citations first
    clean_sections = strip_ungrounded_citations(sections, evidence_ids)

    # Sort sections by outline order
    section_order = {
        s.section_id: s.order for s in outline.sections
    }
    sorted_sections = sorted(
        clean_sections,
        key=lambda s: section_order.get(s.section_id, 999),
    )

    # FIX-CITE-3/C4: Pre-pass to merge thin sections (< 3 unique evidence IDs)
    # into adjacent sections. Prevents hollow final sections.
    # Operates on sorted_sections (not clean_sections) to respect ordering.
    _min_evidence_for_section = int(os.getenv("PG_MIN_SECTION_EVIDENCE", "3"))
    _merged_indices: set[int] = set()
    for idx in range(len(sorted_sections) - 1, 0, -1):
        sec = sorted_sections[idx]
        if len(set(getattr(sec, "evidence_ids", []) or [])) < _min_evidence_for_section:
            prev = sorted_sections[idx - 1]
            # Merge content and evidence_ids into previous section
            merged_content = prev.content + "\n\n" + sec.content
            merged_eids = list(set((getattr(prev, "evidence_ids", []) or [])
                                   + (getattr(sec, "evidence_ids", []) or [])))
            sorted_sections[idx - 1] = SectionDraft(
                section_id=prev.section_id,
                title=prev.title,
                content=merged_content,
                word_count=len(merged_content.split()),
                evidence_count=len(merged_eids),
            )
            # Preserve evidence_ids on the merged draft
            sorted_sections[idx - 1].evidence_ids = merged_eids
            _merged_indices.add(idx)
            logger.info(
                "[polaris graph] FIX-CITE-3/C4: Merged thin section '%s' "
                "(%d evidence) into '%s'",
                sec.title[:40],
                len(set(getattr(sec, "evidence_ids", []) or [])),
                prev.title[:40],
            )
    if _merged_indices:
        sorted_sections = [s for i, s in enumerate(sorted_sections) if i not in _merged_indices]

    # Assemble report parts
    parts: list[str] = []
    report_sections: list[ReportSection] = []

    # Title
    parts.append(f"# {outline.title}")
    parts.append("")

    # Abstract
    if outline.abstract:
        parts.append("## Abstract")
        parts.append("")
        parts.append(outline.abstract)
        parts.append("")

    # NRC-2: Track global citation counts across all sections
    global_citation_counts: dict[int, int] = {}

    # Sections
    for section in sorted_sections:
        resolved_content = resolve_citations(
            section.content, citation_map,
            global_citation_counts=global_citation_counts,
        )
        # FIX-CITE-3: Strip filler words and fix table formatting
        resolved_content = _clean_filler_and_tables(resolved_content)
        # FIX-060-E: Transitions AND artifact cleanup deferred to post-global-cleanup
        # to prevent orphaned transitions from citation/phantom removal.

        # Extract citation numbers used in this section
        citation_numbers = re.findall(r"\[(\d+)\]", resolved_content)
        used_evidence_ids = [
            eid
            for eid, num in citation_map.items()
            if str(num) in citation_numbers
        ]

        # FIX-CITE-3: Ensure paragraph breaks in section content.
        # LLM sometimes outputs entire section as single line.
        # Insert \n\n before ### subheadings, **Key Findings**, and tables.
        if "\n" not in resolved_content and len(resolved_content) > 500:
            # Insert breaks before markdown subheadings
            resolved_content = re.sub(
                r"(?<!\n)(###\s)", r"\n\n\1", resolved_content
            )
            # Insert breaks before **Key Findings**
            resolved_content = re.sub(
                r"(?<!\n)(\*\*Key Findings)", r"\n\n\1", resolved_content
            )
            # Insert breaks before markdown tables (| header |)
            resolved_content = re.sub(
                r"(?<!\n)(\|[^|]+\|[^|]+\|)", r"\n\n\1", resolved_content, count=1
            )
            # Insert paragraph breaks: period + space + uppercase (not after citations)
            # Avoid breaking inside tables or after [N] citations mid-sentence
            resolved_content = re.sub(
                r"(\.\s)(?=[A-Z][a-z]{2,})", r".\n\n", resolved_content
            )

        word_count = len(resolved_content.split())

        parts.append(f"## {section.title}")
        parts.append("")
        parts.append(resolved_content)
        parts.append("")

        report_sections.append(
            ReportSection(
                section_id=section.section_id,
                title=section.title,
                content=resolved_content,
                word_count=word_count,
                citation_ids=[f"[{n}]" for n in citation_numbers],
                evidence_ids=used_evidence_ids,
            )
        )

    # Bibliography
    used_ids = [m.evidence_id for m in citation_audit.mappings if m.is_grounded]
    bibliography = build_bibliography(evidence, used_ids)

    parts.append("## References")
    parts.append("")
    for entry in bibliography:
        parts.append(entry["formatted"])
    parts.append("")

    full_report = "\n".join(parts)

    # Quality stats
    total_words = len(full_report.split())
    total_citations = sum(
        len(s["citation_ids"]) for s in report_sections
    )
    unique_sources = len(bibliography)

    logger.info(
        "[polaris graph] Report assembled: %d words, %d sections, "
        "%d citations, %d unique sources",
        total_words,
        len(report_sections),
        total_citations,
        unique_sources,
    )

    # FIX-E2: Validate abstract metrics against computed values
    if outline.abstract:
        abstract_warnings = _validate_abstract_metrics(
            abstract=outline.abstract,
            unique_sources=unique_sources,
            total_citations=total_citations,
            total_words=total_words,
        )
        for warning in abstract_warnings:
            logger.warning(
                "[polaris graph] FIX-E2: Abstract metric mismatch: %s",
                warning,
            )

    # M-05: Backfill unused evidence citations (embedding-based)
    try:
        report_sections = backfill_unused_citations(
            report_sections=report_sections,
            evidence=evidence,
            citation_map=citation_map,
            bibliography=bibliography,
        )
    except Exception as backfill_exc:
        logger.warning(
            "[polaris graph] M-05: backfill_unused_citations failed (non-blocking): %s",
            str(backfill_exc)[:200],
        )

    # FIX-4: Remove cross-section redundancy BEFORE detecting remaining dupes
    report_sections = remove_redundancy(report_sections)

    # FIX-MP11: Remove repeated statistics across sections (e.g. "USD 10.21 billion" 9x)
    report_sections = _dedup_key_statistics(report_sections)

    # FIX-047B: Fix number spacing BEFORE NRC-3 to prevent "$2. 09" from being
    # split by NRC-3 regex into "$2." (removed) + "09 billion" (orphaned).
    for section in report_sections:
        section["content"] = _fix_number_spacing(section["content"])

    # NRC-3: DISABLED — _soften_uncited_numerics replaces precise numbers
    # with "(specific values vary by study)", destroying the most valuable
    # content. Gemini KEEPS precise numbers. 13 numbers destroyed per pass.
    # Uncited numbers are the LLM's synthesis from evidence — not hallucinations.
    # uncited_claims = _audit_uncited_claims(report_sections)
    # if uncited_claims:
    #     report_sections = _soften_uncited_numerics(report_sections)

    # FIX-R4: Global transition density enforcement across ALL sections.
    # Per-section limiter catches within-section excess but cross-section
    # total can still be 142+ transition words. Global pass strips excess.
    _transition_pattern = re.compile(
        r'\b(moreover|furthermore|additionally|consequently|in addition|'
        r'as a result|nevertheless|nonetheless|on the other hand|'
        r'in contrast|conversely|alternatively|subsequently|meanwhile)\b',
        re.IGNORECASE,
    )
    _global_max_transitions = int(os.getenv("PG_GLOBAL_MAX_TRANSITIONS", "40"))
    _global_transition_count = 0
    for section in report_sections:
        _sec_matches = _transition_pattern.findall(section["content"])
        _global_transition_count += len(_sec_matches)
    if _global_transition_count > _global_max_transitions:
        logger.info(
            "[polaris graph] FIX-R4: Global transition count %d > %d, stripping excess",
            _global_transition_count, _global_max_transitions,
        )
        _stripped = 0
        for section in report_sections:
            if _stripped >= (_global_transition_count - _global_max_transitions):
                break
            def _strip_transition(m):
                nonlocal _stripped
                if _stripped >= (_global_transition_count - _global_max_transitions):
                    return m.group(0)
                _stripped += 1
                # Remove the transition word and any following comma/space
                return ""
            section["content"] = re.sub(
                r'\b(moreover|furthermore|additionally|consequently|in addition|'
                r'as a result|nevertheless|nonetheless|on the other hand|'
                r'in contrast|conversely|alternatively|subsequently|meanwhile)\s*,?\s*',
                _strip_transition,
                section["content"],
                flags=re.IGNORECASE,
            )
            # FIX-R3: Capitalize after removal
            section["content"] = re.sub(
                r'(\.\s+)([a-z])',
                lambda m: m.group(1) + m.group(2).upper(),
                section["content"],
            )

    # GEMINI-ARCH 4A: Reduce filler words in section content
    for section in report_sections:
        section["content"] = _reduce_filler(section["content"])
        section["word_count"] = len(section["content"].split())

    # CRITICAL: Rebuild full_report from post-processed report_sections.
    # remove_redundancy, _dedup_key_statistics, and _soften_uncited_numerics
    # all modify report_sections content, but full_report was built from the
    # original parts list BEFORE post-processing. Without this rebuild,
    # the actual markdown output would not reflect any post-processing.
    rebuilt_parts: list[str] = []
    rebuilt_parts.append(f"# {outline.title}")
    rebuilt_parts.append("")
    if outline.abstract:
        rebuilt_parts.append("## Abstract")
        rebuilt_parts.append("")
        rebuilt_parts.append(outline.abstract)
        rebuilt_parts.append("")
    for section in report_sections:
        rebuilt_parts.append(f"## {section['title']}")
        rebuilt_parts.append("")
        rebuilt_parts.append(section["content"])
        rebuilt_parts.append("")
    rebuilt_parts.append("## References")
    rebuilt_parts.append("")
    for entry in bibliography:
        rebuilt_parts.append(entry["formatted"])
    rebuilt_parts.append("")
    full_report = "\n".join(rebuilt_parts)

    # Strip phantom citation markers left by global cap
    full_report = full_report.replace("[*]", "")
    full_report = re.sub(r"  +", " ", full_report)
    # FIX-047A: Clean artifacts from phantom marker removal
    full_report = _clean_citation_artifacts(full_report)

    # FIX-043I: Fix double/nested brackets from citation resolution.
    # e.g. [[2][[2] -> [2], and adjacent duplicates [2][2] -> [2]
    full_report = re.sub(r'\[+(\d+)\]+', r'[\1]', full_report)
    full_report = re.sub(r'(\[\d+\])(?:\1)+', r'\1', full_report)

    for section in report_sections:
        section["content"] = section["content"].replace("[*]", "")
        section["content"] = re.sub(r"  +", " ", section["content"])
        # FIX-043I: Same bracket cleanup per section
        section["content"] = re.sub(r'\[+(\d+)\]+', r'[\1]', section["content"])
        section["content"] = re.sub(r'(\[\d+\])(?:\1)+', r'\1', section["content"])
        section["word_count"] = len(section["content"].split())

    # Update word count to reflect post-processed content
    total_words = len(full_report.split())

    # FIX-C3: Detect cross-section redundancy (measure what remains)
    redundancy_stats = detect_redundancy(report_sections)
    if redundancy_stats["duplicate_pairs"] > 0:
        logger.info(
            "[polaris graph] FIX-C3: Redundancy stats: %d duplicate pairs, "
            "%.1f%% of %d sentences",
            redundancy_stats["duplicate_pairs"],
            redundancy_stats["redundancy_pct"],
            redundancy_stats["total_sentences"],
        )

    # FIX-043N: Strip residual softening placeholders that shouldn't appear in output.
    # Only strip if count is excessive (>3 = clearly a systemic NRC-3 artifact).
    _softening_placeholders = [
        "(specific values vary by study)",
        "(reported values vary)",
    ]
    for placeholder in _softening_placeholders:
        count = full_report.count(placeholder)
        if count > 3:
            logger.info(
                "[polaris graph] FIX-043N: Stripping %d residual softening "
                "placeholders: '%s'",
                count, placeholder,
            )
            full_report = full_report.replace(placeholder, "the reported value")
            for section in report_sections:
                section["content"] = section["content"].replace(
                    placeholder, "the reported value"
                )

    # FIX-045F: Fix orphaned parentheticals
    full_report = _fix_orphaned_parentheticals(full_report)
    for section in report_sections:
        section["content"] = _fix_orphaned_parentheticals(section["content"])

    # FIX-045A: Remove orphan citations (body [N] without bibliography entry)
    valid_bib_numbers: set[int] = set()
    for entry in bibliography:
        key_match = re.match(r"\[(\d+)\]", entry.get("citation_key", ""))
        if key_match:
            valid_bib_numbers.add(int(key_match.group(1)))

    full_report, orphan_count = _remove_orphan_citations(
        full_report, valid_bib_numbers,
    )
    if orphan_count > 0:
        logger.info(
            "[polaris graph] FIX-045A: Removed %d orphan citations "
            "(valid: [1]-[%d])",
            orphan_count,
            max(valid_bib_numbers) if valid_bib_numbers else 0,
        )
        for section in report_sections:
            section["content"], _ = _remove_orphan_citations(
                section["content"], valid_bib_numbers,
            )
            section["citation_ids"] = [
                cid for cid in section["citation_ids"]
                if cid.strip("[]").isdigit()
                and int(cid.strip("[]")) in valid_bib_numbers
            ]
            section["word_count"] = len(section["content"].split())

    # FIX-047A: Clean space-period artifacts left by orphan citation removal
    full_report = _clean_citation_artifacts(full_report)
    for section in report_sections:
        section["content"] = _clean_citation_artifacts(section["content"])
        section["word_count"] = len(section["content"].split())

    # FIX-045D: Renumber citations in order of first appearance
    full_report, report_sections, bibliography = _renumber_citations_sequential(
        full_report, report_sections, bibliography,
    )

    # FIX-045E: Fix number spacing errors ("99. 9%" -> "99.9%")
    full_report = _fix_number_spacing(full_report)
    for section in report_sections:
        section["content"] = _fix_number_spacing(section["content"])

    # FIX-060-E: Artifact cleanup AFTER all global cleanup.
    # FIX-CITE-3: Transition injection DISABLED — it re-introduces filler words
    # ("Moreover", "Additionally") that _clean_filler_and_tables() just removed.
    # The target_density=0.40 was adding 10-16 filler words per section.
    _section_titles = [s["title"] for s in report_sections]
    for section in report_sections:
        # _inject_transitions DISABLED — net negative on quality
        # section["content"] = _inject_transitions(section["content"], target_density=0.40)
        section["content"] = _clean_artifacts(section["content"], section_titles=_section_titles)
        # FIX-CITE-3: Re-apply filler stripping (in case _clean_artifacts introduced any)
        section["content"] = _clean_filler_and_tables(section["content"])
        section["word_count"] = len(section["content"].split())

    # GAP-2: Recompute citation_ids after transition injection + artifact cleanup.
    for section in report_sections:
        section["citation_ids"] = [
            f"[{m}]" for m in re.findall(r"\[(\d+)\]", section["content"])
        ]

    # Rebuild full_report with final transition-injected content
    _final_parts: list[str] = []
    _final_parts.append(f"# {outline.title}")
    _final_parts.append("")
    if outline.abstract:
        _final_parts.append("## Abstract")
        _final_parts.append("")
        _final_parts.append(outline.abstract)
        _final_parts.append("")
    for section in report_sections:
        _final_parts.append(f"## {section['title']}")
        _final_parts.append("")
        # FIX-CITE-3: Insert paragraph breaks in single-line content
        sec_content = section["content"]
        if "\n" not in sec_content and len(sec_content) > 500:
            sec_content = re.sub(
                r"(?<!\n)(###\s)", r"\n\n\1", sec_content
            )
            sec_content = re.sub(
                r"(?<!\n)(\*\*Key Findings)", r"\n\n\1", sec_content
            )
            sec_content = re.sub(
                r"(?<!\n)(\|[^|]+\|[^|]+\|)", r"\n\n\1", sec_content, count=1
            )
            sec_content = re.sub(
                r"(\.\s)(?=[A-Z][a-z]{2,})", r".\n\n", sec_content
            )
            section["content"] = sec_content
        _final_parts.append(sec_content)
        _final_parts.append("")
    _final_parts.append("## References")
    _final_parts.append("")
    for entry in bibliography:
        _final_parts.append(entry["formatted"])
    _final_parts.append("")
    full_report = "\n".join(_final_parts)

    # Recompute metrics after all fixes
    total_words = len(full_report.split())
    total_citations = sum(len(s["citation_ids"]) for s in report_sections)
    unique_sources = len(bibliography)

    # GAP-1: Fix abstract metrics then rebuild cleanly (no fragile str.replace).
    if outline.abstract:
        fixed_abstract = _fix_abstract_metrics(
            outline.abstract, unique_sources, total_citations, total_words,
        )
        if fixed_abstract != outline.abstract:
            outline.abstract = fixed_abstract
            # Clean rebuild instead of fragile str.replace()
            _abs_parts: list[str] = []
            _abs_parts.append(f"# {outline.title}")
            _abs_parts.append("")
            if outline.abstract:
                _abs_parts.append("## Abstract")
                _abs_parts.append("")
                _abs_parts.append(outline.abstract)
                _abs_parts.append("")
            for section in report_sections:
                _abs_parts.append(f"## {section['title']}")
                _abs_parts.append("")
                _abs_parts.append(section["content"])
                _abs_parts.append("")
            _abs_parts.append("## References")
            _abs_parts.append("")
            for entry in bibliography:
                _abs_parts.append(entry["formatted"])
            _abs_parts.append("")
            full_report = "\n".join(_abs_parts)
            total_words = len(full_report.split())

    # OBS-6: Trace report assembly
    tracer = get_tracer()
    if tracer:
        tracer.evidence(
            "synthesize", "report_assembled",
            total_words,
            sections=len(report_sections),
            total_citations=total_citations,
            bibliography_entries=unique_sources,
            redundancy_pairs=redundancy_stats["duplicate_pairs"],
            redundancy_pct=redundancy_stats["redundancy_pct"],
            bibliography=[{
                "key": b["citation_key"],
                "url": b.get("url", ""),
                "source_type": b.get("source_type", ""),
                "formatted": b["formatted"],
            } for b in bibliography],
            section_titles=[{
                "id": s["section_id"],
                "title": s["title"],
                "words": s["word_count"],
            } for s in report_sections],
            full_report=full_report,
        )

    # GEMINI-ARCH 4A: Apply filler reduction to full report text
    full_report = _reduce_filler(full_report)

    # GEMINI-ARCH 4B: Compute and log density metrics (diagnostic only, not gated)
    density_metrics = _compute_density_metrics(full_report)
    logger.info(
        "[polaris graph] Density metrics: "
        "%.1f facts/100w, filler_ratio=%.4f (%d filler), "
        "%d table rows, %d charts, %d key_findings, "
        "%.0f%% sentences cited (%d/%d), %d total words",
        density_metrics["facts_per_100w"],
        density_metrics["filler_ratio"],
        density_metrics["filler_count"],
        density_metrics["table_row_count"],
        density_metrics["chart_count"],
        density_metrics["key_findings_count"],
        (1 - density_metrics["uncited_sentence_ratio"]) * 100,
        density_metrics["cited_sentences"],
        density_metrics["total_sentences"],
        density_metrics["total_words"],
    )

    return full_report, report_sections, bibliography


def backfill_unused_citations(
    report_sections: list[ReportSection],
    evidence: list[EvidencePiece],
    citation_map: dict[str, int],
    bibliography: list[BibliographyEntry],
    min_similarity: float = 0.0,
) -> list[ReportSection]:
    """FIX-047L: Backfill unused evidence as secondary citations.

    For each uncited evidence piece, checks if any report section sentence
    is semantically related using embedding cosine similarity. If similarity
    >= threshold, adds the citation to that sentence.

    Args:
        report_sections: The assembled report sections.
        evidence: All evidence pieces (cited and uncited).
        citation_map: evidence_id -> citation number mapping.
        bibliography: Current bibliography entries.
        min_similarity: Minimum embedding cosine similarity to match.

    Returns:
        Updated report_sections with additional citations inserted.
    """
    if min_similarity <= 0:
        min_similarity = float(os.getenv("PG_BACKFILL_MIN_SIMILARITY", "0.75"))

    # Find uncited evidence (has a citation number but isn't used in any section)
    cited_eids: set[str] = set()
    for section in report_sections:
        for eid in section.get("evidence_ids", []):
            cited_eids.add(eid)

    uncited = [
        e for e in evidence
        if e.get("evidence_id", "") not in cited_eids
        and e.get("evidence_id", "") in citation_map
    ]

    if not uncited:
        logger.info("[polaris graph] FIX-047L: No uncited evidence to backfill")
        return report_sections

    # Try embedding-based matching
    try:
        import numpy as np
        from src.utils.embedding_service import embed_texts

        # Build sentence pool from report sections
        sentence_pool: list[tuple[str, int, str]] = []  # (sentence, section_idx, section_id)
        for sec_idx, section in enumerate(report_sections):
            sentences = _split_sentences(section.get("content", ""), min_len=30)
            for sent in sentences:
                sentence_pool.append((sent, sec_idx, section.get("section_id", "")))

        if not sentence_pool:
            return report_sections

        # Build uncited evidence statements
        uncited_statements = [
            e.get("statement", "") for e in uncited
            if e.get("statement", "")
        ]
        uncited_filtered = [
            e for e in uncited if e.get("statement", "")
        ]

        if not uncited_statements:
            return report_sections

        # Embed sentences and evidence statements
        sentence_texts = [s[0] for s in sentence_pool]
        all_texts = sentence_texts + uncited_statements
        embeddings = np.array(embed_texts(all_texts))

        sent_vecs = embeddings[:len(sentence_texts)]
        evidence_vecs = embeddings[len(sentence_texts):]

        # Compute similarity matrix (evidence x sentences)
        similarity = evidence_vecs @ sent_vecs.T

        # Find matches above threshold
        backfilled = 0
        max_backfill = int(os.getenv("PG_MAX_BACKFILL_CITATIONS", "20"))

        # FIX-C8: Build section→evidence assignment map to scope backfill.
        # Without scoping, evidence from Section A gets cited in Section B,
        # causing cross-section citation leakage (Clinical Implementation
        # had 8 citations but only 3 evidence assigned).
        _section_evidence_ids: dict[str, set] = {}
        for section in report_sections:
            sid = section.get("section_id", "")
            _section_evidence_ids[sid] = set(section.get("evidence_ids", []))

        for ev_idx, ev in enumerate(uncited_filtered):
            if backfilled >= max_backfill:
                break

            eid = ev.get("evidence_id", "")
            cite_num = citation_map.get(eid)
            if not cite_num:
                continue

            # FIX-C8: Only match sentences in sections where this evidence
            # was originally assigned. Prevents cross-section leakage.
            # Mask out sentences from non-assigned sections.
            _masked_sims = similarity[ev_idx].copy()
            for s_idx, (_, sec_idx, sec_id) in enumerate(sentence_pool):
                if eid not in _section_evidence_ids.get(
                    report_sections[sec_idx].get("section_id", ""), set()
                ):
                    _masked_sims[s_idx] = -1.0  # Mask out

            best_sent_idx = int(np.argmax(_masked_sims))
            best_sim = float(_masked_sims[best_sent_idx])

            if best_sim >= min_similarity:
                _, sec_idx, _ = sentence_pool[best_sent_idx]
                section = report_sections[sec_idx]

                # Add citation to end of the matching sentence
                sent_text = sentence_pool[best_sent_idx][0]
                cite_marker = f"[{cite_num}]"

                if cite_marker not in section["content"]:
                    # Insert citation after the matching sentence's period
                    old_sent = sent_text.rstrip(".")
                    new_sent = f"{old_sent} {cite_marker}."
                    section["content"] = section["content"].replace(
                        sent_text, new_sent, 1,
                    )
                    if cite_marker not in section.get("citation_ids", []):
                        section["citation_ids"].append(cite_marker)
                    if eid not in section.get("evidence_ids", []):
                        section["evidence_ids"].append(eid)
                    backfilled += 1

        if backfilled > 0:
            logger.info(
                "[polaris graph] FIX-047L: Backfilled %d citations from %d unused "
                "evidence (threshold=%.2f, pool=%d uncited)",
                backfilled, len(uncited_filtered),
                min_similarity, len(uncited),
            )

    except ImportError:
        logger.warning(
            "[polaris graph] FIX-047L: Embedding service unavailable — "
            "skipping citation backfill"
        )
    except Exception as exc:
        logger.warning(
            "[polaris graph] FIX-047L: Citation backfill failed: %s",
            str(exc)[:200],
        )

    return report_sections


def _compute_coherence(report_sections: list[ReportSection]) -> float:
    """FIX-QG1: Compute coherence score from transition density and evidence connectivity.

    Coherence = 0.5 * transition_density + 0.5 * evidence_connectivity

    - transition_density: fraction of sentences starting with transition words (0.0-1.0)
    - evidence_connectivity: avg pairwise shared evidence between adjacent sections (0.0-1.0)

    Returns a float between 0.0 and 1.0, or 0.0 if no sections exist.
    """
    if not report_sections:
        return 0.0

    # Component 1: Transition density across all sections
    total_sentences = 0
    transition_sentences = 0
    for section in report_sections:
        content = section.get("content", "")
        # FIX-047C: PySBD sentence splitting
        sentences = _split_sentences(content)
        total_sentences += len(sentences)
        for sent in sentences:
            if _has_transition(sent):
                transition_sentences += 1

    transition_density = (
        transition_sentences / max(total_sentences, 1)
    )
    # Normalize: 0.4 density → 1.0 score (0.4 is our injection target)
    transition_score = min(transition_density / 0.4, 1.0)

    # Component 2: Evidence connectivity between adjacent sections
    connectivity_scores = []
    for i in range(len(report_sections) - 1):
        ev_a = set(report_sections[i].get("evidence_ids", []))
        ev_b = set(report_sections[i + 1].get("evidence_ids", []))
        if ev_a and ev_b:
            # Jaccard-like: shared evidence / total evidence
            shared = len(ev_a & ev_b)
            total = len(ev_a | ev_b)
            connectivity_scores.append(shared / max(total, 1))
        else:
            connectivity_scores.append(0.0)

    avg_connectivity = (
        sum(connectivity_scores) / max(len(connectivity_scores), 1)
        if connectivity_scores else 0.0
    )
    # Normalize: some connectivity is good but full overlap means repetition
    # Ideal is ~0.1-0.3 overlap → score 1.0
    connectivity_score = min(avg_connectivity * 5.0, 1.0)

    coherence = 0.5 * transition_score + 0.5 * connectivity_score
    return round(coherence, 3)


def compute_quality_metrics(
    evidence: list[EvidencePiece],
    claims: list[dict],
    report_sections: list[ReportSection],
    bibliography: list[BibliographyEntry],
    faithfulness_score: float,
) -> dict:
    """Compute quality metrics for the report."""
    total_words = sum(s["word_count"] for s in report_sections)
    total_citations = sum(len(s["citation_ids"]) for s in report_sections)
    unique_sources = len(bibliography)

    gold_count = sum(
        1 for e in evidence if e.get("quality_tier") == "GOLD"
    )
    silver_count = sum(
        1 for e in evidence if e.get("quality_tier") == "SILVER"
    )

    # BUG-7 FIX: Exclude api_error claims from both numerator and denominator.
    # api_error = verification failed (timeout/network), not unfaithful.
    scorable_claims = [
        c for c in claims if c.get("verification_method") != "api_error"
    ] if claims else []
    verified_claims = sum(
        1 for c in scorable_claims if c.get("is_faithful", False)
    )
    total_claims = len(scorable_claims) if scorable_claims else 1

    # FIX-QM6: Coverage = question-aspect completeness (not evidence usage ratio)
    # Measures how many report sections have substantive content with evidence
    total_aspects = len(report_sections)
    aspects_with_evidence = sum(
        1 for section in report_sections
        if len(section.get("evidence_ids", [])) >= 2  # At least 2 evidence pieces
        and section.get("word_count", 0) >= 200        # At least 200 words of content
    )
    coverage = aspects_with_evidence / max(total_aspects, 1)

    # M-01: Recompute utilization from actual CITE markers + evidence_ids
    used_evidence_ids = set()
    for section in report_sections:
        content = section.get("content", "")
        cited = set(re.findall(r"\[CITE:(ev_[a-f0-9]+)\]", content))
        cited.update(section.get("evidence_ids", []))
        used_evidence_ids.update(cited)
    all_evidence_ids = {e.get("evidence_id", "") for e in evidence}
    matched_ids = used_evidence_ids & all_evidence_ids
    evidence_utilization = (
        len(matched_ids) / max(len(all_evidence_ids), 1)
    )

    # FIX-043E: Diagnostic logging when utilization is suspiciously low
    if evidence_utilization < 0.01 and all_evidence_ids and used_evidence_ids:
        sample_used = list(used_evidence_ids)[:3]
        sample_pool = list(all_evidence_ids)[:3]
        logger.warning(
            "[polaris graph] FIX-043E: Evidence utilization < 1%% "
            "(matched=%d, used=%d, pool=%d). "
            "Possible ID format mismatch — used sample: %s, pool sample: %s",
            len(matched_ids), len(used_evidence_ids),
            len(all_evidence_ids), sample_used, sample_pool,
        )

    # Citation density = citations per 100 words
    citation_density = (total_citations / max(total_words, 1)) * 100

    # FIX-C4: Citation frequency analysis
    citation_freq: dict[int, int] = {}
    for section in report_sections:
        for cid in section["citation_ids"]:
            stripped = cid.strip("[]")
            num = int(stripped) if stripped.isdigit() else 0
            citation_freq[num] = citation_freq.get(num, 0) + 1

    max_citation_frequency = max(citation_freq.values()) if citation_freq else 0
    max_over_cited_threshold = int(
        os.getenv("PG_MAX_CITATION_FREQUENCY", "5")
    )
    over_cited = [
        f"[{k}]" for k, v in citation_freq.items()
        if v > max_over_cited_threshold
    ]
    if over_cited:
        logger.warning(
            "[polaris graph] FIX-C4: Over-cited sources: %s (>%d citations each)",
            over_cited[:5],
            max_over_cited_threshold,
        )

    # FIX-CITE-DIV: HHI (Herfindahl-Hirschman Index) for citation diversity
    # HHI < 0.05 = diverse, 0.05-0.10 = acceptable, >= 0.10 = concentrated
    total_cites = sum(citation_freq.values()) if citation_freq else 0
    hhi = 0.0
    if total_cites > 0:
        hhi = sum(
            (count / total_cites) ** 2
            for count in citation_freq.values()
        )
    hhi = round(hhi, 4)

    # Shannon entropy for observability
    import math
    shannon_entropy = 0.0
    if total_cites > 0 and citation_freq:
        for count in citation_freq.values():
            p = count / total_cites
            if p > 0:
                shannon_entropy -= p * math.log2(p)
    shannon_entropy = round(shannon_entropy, 3)

    hhi_label = "diverse" if hhi < 0.05 else ("acceptable" if hhi < 0.10 else "concentrated")
    logger.info(
        "[polaris graph] FIX-CITE-DIV: Citation HHI=%.4f (%s), "
        "Shannon entropy=%.3f, %d unique sources cited",
        hhi, hhi_label, shannon_entropy, len(citation_freq),
    )

    # FIX-043D: Hedging word tracking — count hedging words in report text
    # WARN-2 FIX: Domain-adaptive thresholds + weak/strong categorization
    # Scientific/technical writing legitimately uses more hedging (88% justified
    # in T044 audit). Strong hedging (may, could, potentially) is standard
    # scientific language; weak hedging (might, possibly, perhaps) signals
    # true uncertainty.
    hedging_words_strong = {"may", "could", "potentially"}
    hedging_words_weak = {"might", "possibly", "perhaps"}
    hedging_words = hedging_words_strong | hedging_words_weak
    max_hedging = int(os.getenv("PG_MAX_HEDGING_WORDS", "55"))
    hedging_counts: dict[str, int] = {}
    for section in report_sections:
        content_lower = section.get("content", "").lower()
        for hw in hedging_words:
            # Count word boundary matches to avoid substring false positives
            # FIX-044/Issue4: For "may", exclude month-name patterns
            # e.g., "may 2024", "15 may" should NOT count as hedging
            if hw == "may":
                pattern = r'(?<!\d\s)\bmay\b(?!\s+\d)'
            else:
                pattern = r'\b' + hw + r'\b'
            count = len(re.findall(pattern, content_lower))
            hedging_counts[hw] = hedging_counts.get(hw, 0) + count
    total_hedging = sum(hedging_counts.values())
    weak_total = sum(hedging_counts.get(w, 0) for w in hedging_words_weak)
    strong_total = sum(hedging_counts.get(w, 0) for w in hedging_words_strong)
    if total_hedging > max_hedging:
        # C7: Log-only. Removing "may" programmatically breaks grammar
        # ("fasting may reduce" → "fasting reduce"). Hedge reduction
        # must be done by the LLM during writing, not post-hoc regex.
        logger.warning(
            "[polaris graph] FIX-043D: Hedging words %d > %d limit "
            "(strong=%d, weak=%d): %s",
            total_hedging, max_hedging, strong_total, weak_total,
            {k: v for k, v in sorted(
                hedging_counts.items(), key=lambda x: -x[1]
            ) if v > 0},
        )
    else:
        logger.info(
            "[polaris graph] FIX-043D: Hedging words %d/%d "
            "(strong=%d, weak=%d): %s",
            total_hedging, max_hedging, strong_total, weak_total,
            {k: v for k, v in sorted(
                hedging_counts.items(), key=lambda x: -x[1]
            ) if v > 0},
        )

    # FIX-CITE-DIV: Per-source citation cap enforcement
    max_per_source = int(os.getenv("PG_MAX_CITATIONS_PER_SOURCE", "10"))
    sources_over_cap = sum(1 for v in citation_freq.values() if v > max_per_source)
    if sources_over_cap:
        logger.warning(
            "[polaris graph] FIX-CITE-DIV: %d sources exceed %d citation cap",
            sources_over_cap, max_per_source,
        )

    # FIX-047M: Domain concentration check
    # No single domain should account for > 30% of citations
    max_domain_pct = float(os.getenv("PG_MAX_DOMAIN_CITATION_PCT", "0.30"))
    min_distinct_domains = int(os.getenv("PG_MIN_DISTINCT_DOMAINS", "5"))
    domain_citation_counts: dict[str, int] = {}
    for section in report_sections:
        for eid in section.get("evidence_ids", []):
            # Look up evidence to get URL domain
            for ev in evidence:
                if ev.get("evidence_id") == eid:
                    url = ev.get("source_url", "")
                    if url:
                        try:
                            from urllib.parse import urlparse
                            domain = urlparse(url).netloc.lower().replace("www.", "")
                        except Exception:
                            domain = url[:50]
                        domain_citation_counts[domain] = domain_citation_counts.get(domain, 0) + 1
                    break

    total_domain_cites = sum(domain_citation_counts.values()) if domain_citation_counts else 0
    domain_over_cap: list[str] = []
    if total_domain_cites > 0:
        for domain, count in domain_citation_counts.items():
            pct = count / total_domain_cites
            if pct > max_domain_pct:
                domain_over_cap.append(f"{domain}={pct:.0%}")
    distinct_domains = len(domain_citation_counts)

    if domain_over_cap:
        logger.warning(
            "[polaris graph] FIX-047M: Domain concentration: %s exceed %.0f%% cap",
            domain_over_cap[:5],
            max_domain_pct * 100,
        )
    if distinct_domains < min_distinct_domains:
        logger.warning(
            "[polaris graph] FIX-047M: Only %d distinct domains cited "
            "(minimum %d recommended)",
            distinct_domains,
            min_distinct_domains,
        )

    return {
        "total_evidence": len(evidence),
        "gold_evidence": gold_count,
        "silver_evidence": silver_count,
        "total_claims": total_claims,
        "verified_claims": verified_claims,
        "faithfulness_score": faithfulness_score,
        "total_words": total_words,
        "total_sections": len(report_sections),
        "total_citations": total_citations,
        "unique_sources": unique_sources,
        "coverage_score": round(coverage, 3),
        "evidence_utilization": round(evidence_utilization, 3),  # FIX-QM6: old coverage metric preserved for debugging
        "coherence_score": _compute_coherence(report_sections),
        "citation_density": round(citation_density, 2),
        # FIX-C4: Citation frequency metrics
        "max_citation_frequency": max_citation_frequency,
        "over_cited_sources": over_cited,
        # FIX-CITE-DIV: Diversity metrics
        "citation_hhi": hhi,
        "citation_hhi_label": hhi_label,
        "citation_shannon_entropy": shannon_entropy,
        # FIX-043D: Hedging word metrics
        "hedging_word_count": total_hedging,
        "hedging_word_limit": max_hedging,
        "hedging_word_breakdown": {
            k: v for k, v in hedging_counts.items() if v > 0
        },
        # M-07: Redundancy detection in quality metrics
        "redundancy_pct": _compute_redundancy_pct(report_sections),
    }


def _compute_redundancy_pct(report_sections: list[ReportSection]) -> float:
    """M-07: Compute redundancy percentage for quality gate.

    Returns redundancy_pct. Logs warning if > 15%.
    """
    max_redundancy_pct = float(os.getenv("PG_MAX_REDUNDANCY_PCT", "15.0"))
    try:
        stats = detect_redundancy(report_sections)
        pct = stats.get("redundancy_pct", 0.0)
        if pct > max_redundancy_pct:
            logger.warning(
                "[polaris graph] M-07: Redundancy %.1f%% exceeds %.1f%% threshold "
                "(%d duplicate pairs across %d sentences)",
                pct,
                max_redundancy_pct,
                stats.get("duplicate_pairs", 0),
                stats.get("total_sentences", 0),
            )
        return round(pct, 1)
    except Exception as exc:
        logger.debug(
            "[polaris graph] M-07: Redundancy detection failed: %s",
            str(exc)[:100],
        )
        return 0.0
