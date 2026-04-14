"""
POLARIS Automated Deep Audit System (v2.0)

10-dimension quality assessment for research reports produced by the POLARIS
pipeline.  Each dimension scores 0-10 and is weighted to produce a composite
score out of 100.

Dimensions:
    D1  CoT Leakage          (15%)  Regex + heuristic detection
    D2  Faithfulness          (15%)  External placeholder (MiniCheck done elsewhere)
    D3  Semantic Duplication  (10%)  Word-level Jaccard >= 0.7 threshold
    D4  Section Balance       ( 5%)  Word distribution + Shannon entropy
    D5  Citation Quality      (10%)  [CITE:xxx] format + density per 100 words
    D6  Bibliography          (10%)  URL completeness in evidence
    D7  Perspective Coverage  (10%)  Unique perspectives + balance score
    D8  Topical Relevance     (10%)  Keyword overlap query <-> report
    D9  Coherence             (10%)  Transition density + sentence length variation
    D10 Pipeline Integrity    ( 5%)  Error / fallback counts from state

Dependencies: standard library + numpy.  NO external LLM calls.
"""

import json
import logging
import math
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Set, Tuple

import numpy as np

logger = logging.getLogger(__name__)


# =============================================================================
# Constants  (LAW VI -- all thresholds pulled from env or defaults here)
# =============================================================================

# FIX-255: Default to 0.0 (unknown = worst case) instead of 0.85.
# LAW II: Never silently assume quality when data is missing.
_DEFAULT_FAITHFULNESS: float = float(
    os.environ.get("POLARIS_DEFAULT_FAITHFULNESS", "0.0")
)

_JACCARD_DUP_THRESHOLD: float = float(
    os.environ.get("POLARIS_JACCARD_DUP_THRESHOLD", "0.7")
)

_COT_PATTERNS: List[str] = [
    r"\bLet me\b",
    r"\bI need to\b",
    r"\bFirst,",
    r"\bStep\s+\d+:",
    r"\bNow I will\b",
    r"\bthinking about\b",
    # FIX-250: Removed \bconsidering\b — legitimate research language
    r"\bIn summary, I\b",
    r"\bAs an AI\b",
    r"\bmy analysis\b",
    r"\bI should note\b",
]

# Additional heuristic patterns (meta-reasoning leaks observed in Runs #8-#11)
_COT_HEURISTIC_PATTERNS: List[str] = [
    r"\bI will now\b",
    r"\bLet's\b",
    r"\bI have identified\b",
    r"\bI'll\b",
    r"\bmy assessment\b",
    r"\bI believe\b",
    r"\bI think\b",
    r"\bI would\b",
    # FIX-250: Removed domain-conflicting patterns that cause false positives
    # on legitimate research prose (e.g. "we can see that contamination rates...")
    r"\bmy review\b",
    # FIX-265: Instruction-echo CoT patterns (Run #18 false negatives)
    # These catch LLM echoing its synthesis instructions into the output.
    r"\bI must write\b",
    r"\bI only have \d+\b",
    r"\bGiven the strict instruction\b",
    r"\bThe content stays grounded\b",
    r"\bI should indicate\b",
    r"\bI should write\b",
    r"\bI cannot invent\b",
    r"\bI am instructed\b",
    r"\bI was told to\b",
    r"\bthe provided evidence\b",
    r"^\s*\d+[a-z]\.\s",
]

_TRANSITION_WORDS: List[str] = [
    "however",
    "moreover",
    "furthermore",
    "additionally",
    "consequently",
    "therefore",
    "nevertheless",
    "nonetheless",
    "in contrast",
    "on the other hand",
    "similarly",
    "likewise",
    "meanwhile",
    "subsequently",
    "in addition",
    "as a result",
    "for example",
    "for instance",
    "in particular",
    "specifically",
    "notably",
    "indeed",
    "conversely",
    "alternatively",
]

_STOP_WORDS: Set[str] = {
    "a", "an", "the", "is", "are", "was", "were", "be", "been", "being",
    "have", "has", "had", "do", "does", "did", "will", "would", "could",
    "should", "may", "might", "shall", "can", "need", "dare", "ought",
    "used", "to", "of", "in", "for", "on", "with", "at", "by", "from",
    "as", "into", "through", "during", "before", "after", "above", "below",
    "between", "out", "off", "over", "under", "again", "further", "then",
    "once", "here", "there", "when", "where", "why", "how", "all", "each",
    "every", "both", "few", "more", "most", "other", "some", "such", "no",
    "not", "only", "own", "same", "so", "than", "too", "very", "just",
    "because", "but", "and", "or", "nor", "if", "while", "about", "up",
    "that", "this", "these", "those", "what", "which", "who", "whom",
    "it", "its", "they", "them", "their", "we", "us", "our", "he", "him",
    "his", "she", "her", "i", "me", "my", "you", "your",
}

_CITE_PATTERN = re.compile(r"\[CITE:[^\]]+\]")
_CITE_VALID_PATTERN = re.compile(r"\[CITE:[a-zA-Z0-9_\-]+\]")
# FIX-243: Also match numbered citations [1], [2], etc. (post-binding format)
_NUMBERED_CITE_PATTERN = re.compile(r"\[(\d+)\]")

# Section header patterns commonly emitted by POLARIS synthesizer
_SECTION_HEADER_PATTERN = re.compile(
    r"^(?:#{1,4}\s+.+|[A-Z][A-Za-z\s]{2,60})\s*$", re.MULTILINE
)


# =============================================================================
# Helper utilities
# =============================================================================

def _split_sentences(text: str) -> List[str]:
    """Split text into sentences using a regex heuristic.

    FIX-263: Split on any sentence-ending punctuation followed by whitespace,
    not just uppercase. The old pattern missed lowercase starts after periods
    (e.g. "...study. advanced systems..." stayed merged).
    """
    # Split on sentence-ending punctuation followed by 1+ whitespace chars
    raw = re.split(r"(?<=[.!?])\s+", text)
    sentences = [s.strip() for s in raw if len(s.strip()) > 2]
    return sentences


def _tokenize_words(text: str) -> List[str]:
    """Lowercase word tokenization (alphanumeric only)."""
    return re.findall(r"[a-z0-9]+", text.lower())


def _significant_words(text: str) -> List[str]:
    """Return non-stop-word tokens from *text*."""
    return [w for w in _tokenize_words(text) if w not in _STOP_WORDS]


def _jaccard_similarity(set_a: Set[str], set_b: Set[str]) -> float:
    """Word-level Jaccard similarity between two token sets."""
    if not set_a or not set_b:
        return 0.0
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    return intersection / union if union > 0 else 0.0


def _shannon_entropy(distribution: List[float]) -> float:
    """Shannon entropy (base-2) of a probability distribution.

    A perfectly uniform distribution of *n* categories has entropy log2(n).
    """
    total = sum(distribution)
    if total == 0:
        return 0.0
    probs = [v / total for v in distribution if v > 0]
    return -sum(p * math.log2(p) for p in probs)


def _extract_sections(report: str) -> Dict[str, str]:
    """Extract named sections from a Markdown report.

    Returns a dict mapping section title -> section body text.
    """
    lines = report.split("\n")
    sections: Dict[str, str] = {}
    current_title: Optional[str] = None
    current_body: List[str] = []

    for line in lines:
        stripped = line.strip()
        # Detect Markdown headers (## Title or ### Title)
        header_match = re.match(r"^#{1,4}\s+(.+)$", stripped)
        if header_match:
            # Save previous section
            if current_title is not None:
                sections[current_title] = "\n".join(current_body).strip()
            current_title = header_match.group(1).strip()
            current_body = []
        else:
            current_body.append(line)

    # Save last section
    if current_title is not None:
        sections[current_title] = "\n".join(current_body).strip()

    # If no headers found, treat entire report as one section
    if not sections:
        sections["Full Report"] = report.strip()

    return sections


# =============================================================================
# Main audit class
# =============================================================================

class AutomatedDeepAudit:
    """10-dimension automated deep audit for POLARIS research reports.

    Usage::

        auditor = AutomatedDeepAudit()
        result = auditor.audit(state_dict)
        # or
        result = auditor.audit_from_file("outputs/P12/S1V001.json")

    The returned dict is fully JSON-serializable and suitable for storage in
    ``state/progress_ledger.jsonl`` or display in dashboards.
    """

    AUDIT_VERSION = "2.0"

    def __init__(self) -> None:
        self.weights: Dict[str, float] = {
            "d1_cot_leakage": 0.15,
            "d2_faithfulness": 0.15,
            "d3_semantic_duplication": 0.10,
            "d4_section_balance": 0.05,
            "d5_citation_quality": 0.10,
            "d6_bibliography": 0.10,
            "d7_perspective_coverage": 0.10,
            "d8_topical_relevance": 0.10,
            "d9_coherence": 0.10,
            "d10_pipeline_integrity": 0.05,
        }

        # Pre-compile CoT regex patterns for performance
        self._cot_compiled: List[re.Pattern] = [
            re.compile(p, re.IGNORECASE) for p in _COT_PATTERNS
        ]
        self._cot_heuristic_compiled: List[re.Pattern] = [
            re.compile(p, re.IGNORECASE) for p in _COT_HEURISTIC_PATTERNS
        ]

    # -----------------------------------------------------------------
    # FIX-245: Evidence entry parser (handles dict, Pydantic, and str repr)
    # -----------------------------------------------------------------

    @staticmethod
    def _parse_evidence_entry(ev) -> Dict[str, Any]:
        """Parse evidence entry regardless of format.

        Evidence entries may be:
        - dict (JSON deserialized)
        - Pydantic model (with model_dump())
        - Object with attributes (e.g. Evidence dataclass)
        - String representation ("evidence_id='ev_xxx' source_url='https://...'")

        Returns a dict with available fields.
        """
        if isinstance(ev, dict):
            return ev
        if hasattr(ev, "model_dump"):
            return ev.model_dump()
        if hasattr(ev, "source_url"):
            return {
                k: getattr(ev, k, None)
                for k in ("evidence_id", "source_url", "title", "text",
                           "perspective_origins", "authors", "author")
            }
        if isinstance(ev, str):
            result: Dict[str, Any] = {}
            for match in re.finditer(r"(\w+)='([^']*)'", ev):
                result[match.group(1)] = match.group(2)
            # Parse list fields like perspective_origins
            for list_match in re.finditer(r"(\w+)=\[([^\]]*)\]", ev):
                key = list_match.group(1)
                vals = list_match.group(2)
                if vals.strip():
                    result[key] = [v.strip().strip("'\"") for v in vals.split(",")]
                else:
                    result[key] = []
            return result
        return {}

    # -----------------------------------------------------------------
    # Public API
    # -----------------------------------------------------------------

    def audit_from_file(self, path: str) -> Dict[str, Any]:
        """Load a result JSON from *path* and run the full audit.

        The file must be a JSON object with at least ``draft_report`` or
        ``final_report`` and ideally the full ResearchState.

        Raises:
            FileNotFoundError: If *path* does not exist.
            json.JSONDecodeError: If the file is not valid JSON.
        """
        if not os.path.isfile(path):
            raise FileNotFoundError(f"Audit target not found: {path}")

        with open(path, "r", encoding="utf-8") as fh:
            state = json.load(fh)

        return self.audit(state)

    def audit(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Run all 10 dimensions against *state* and return the scored result.

        Parameters
        ----------
        state : dict
            A dictionary conforming to the POLARIS ``ResearchState`` structure.
            At minimum must contain ``draft_report`` or ``final_report``.

        Returns
        -------
        dict
            JSON-serializable audit result with ``total_score``, ``dimensions``,
            and ``metadata``.
        """
        report = self._extract_report(state)
        if not report:
            logger.error("No report text found in state (checked final_report, draft_report)")
            return self._empty_result("No report text found in state")

        sentences = _split_sentences(report)
        word_count = len(_tokenize_words(report))
        sections = _extract_sections(report)
        original_query = state.get("original_query", "")

        # Run each dimension
        d1 = self._score_d1_cot_leakage(report, sentences)
        d2 = self._score_d2_faithfulness(state)
        d3 = self._score_d3_semantic_duplication(sentences)
        d4 = self._score_d4_section_balance(sections)
        d5 = self._score_d5_citation_quality(report, word_count)
        d6 = self._score_d6_bibliography(state)
        d7 = self._score_d7_perspective_coverage(state)
        d8 = self._score_d8_topical_relevance(report, original_query)
        d9 = self._score_d9_coherence(report, sentences)
        d10 = self._score_d10_pipeline_integrity(state)

        dimensions_raw = [
            ("D1 CoT Leakage", "d1_cot_leakage", d1),
            ("D2 Faithfulness", "d2_faithfulness", d2),
            ("D3 Semantic Duplication", "d3_semantic_duplication", d3),
            ("D4 Section Balance", "d4_section_balance", d4),
            ("D5 Citation Quality", "d5_citation_quality", d5),
            ("D6 Bibliography", "d6_bibliography", d6),
            ("D7 Perspective Coverage", "d7_perspective_coverage", d7),
            ("D8 Topical Relevance", "d8_topical_relevance", d8),
            ("D9 Coherence", "d9_coherence", d9),
            ("D10 Pipeline Integrity", "d10_pipeline_integrity", d10),
        ]

        dimensions: List[Dict[str, Any]] = []
        total_score: float = 0.0

        for display_name, key, dim_result in dimensions_raw:
            weight = self.weights[key]
            raw_score = float(dim_result["score"])
            # Clamp to [0, 10]
            clamped = max(0.0, min(10.0, raw_score))
            weighted = round(clamped * weight, 4)
            total_score += weighted

            dimensions.append({
                "name": display_name,
                "key": key,
                "score": round(clamped, 2),
                "weight": weight,
                "weighted": round(weighted, 2),
                "details": dim_result.get("details", {}),
            })

        total_score_rounded = round(total_score * 10, 1)  # scale to /100

        return {
            "total_score": total_score_rounded,
            "dimensions": dimensions,
            "metadata": {
                "audit_version": self.AUDIT_VERSION,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "word_count": word_count,
                "sentence_count": len(sentences),
                "section_count": len(sections),
                "original_query": original_query,
                "vector_id": state.get("vector_id", "unknown"),
            },
        }

    # -----------------------------------------------------------------
    # D1 -- CoT Leakage
    # -----------------------------------------------------------------

    def _score_d1_cot_leakage(
        self, report: str, sentences: List[str]
    ) -> Dict[str, Any]:
        """Detect chain-of-thought / meta-reasoning leakage in the report.

        Scores 10 (no leakage) down to 0 (severe leakage).
        """
        if not sentences:
            return {"score": 10.0, "details": {"leaked_lines": 0, "total_lines": 0}}

        leaked_lines: List[Dict[str, Any]] = []

        for idx, sentence in enumerate(sentences):
            matched_patterns: List[str] = []

            # Primary patterns (high confidence)
            for compiled in self._cot_compiled:
                if compiled.search(sentence):
                    matched_patterns.append(compiled.pattern)

            # Heuristic patterns (moderate confidence)
            for compiled in self._cot_heuristic_compiled:
                if compiled.search(sentence):
                    matched_patterns.append(compiled.pattern)

            # FIX-256: REMOVED citation-context filter (was FIX-250).
            # The filter suppressed heuristic CoT patterns in cited sentences,
            # but CoT CAN leak INTO cited text (e.g. "My analysis shows X [CITE:ev_123]").
            # Removing this ensures ALL CoT patterns are flagged regardless of citations.

            if matched_patterns:
                leaked_lines.append({
                    "line_index": idx,
                    "text_preview": sentence[:120],
                    "patterns_matched": matched_patterns,
                })

        total = len(sentences)
        leaked_count = len(leaked_lines)
        leakage_rate = leaked_count / total if total > 0 else 0.0

        # Scoring curve:
        #   0% leakage  -> 10.0
        #   5% leakage  -> 8.0
        #  15% leakage  -> 5.0
        #  30%+ leakage -> 0.0
        if leakage_rate <= 0.0:
            score = 10.0
        elif leakage_rate >= 0.30:
            score = 0.0
        else:
            # Linear interpolation: 10 - (leakage_rate / 0.30) * 10
            score = 10.0 * (1.0 - leakage_rate / 0.30)

        return {
            "score": round(score, 2),
            "details": {
                "leaked_lines": leaked_count,
                "total_lines": total,
                "leakage_rate": round(leakage_rate, 4),
                "examples": leaked_lines[:10],  # Cap for readability
            },
        }

    # -----------------------------------------------------------------
    # D2 -- Faithfulness (placeholder -- external MiniCheck)
    # -----------------------------------------------------------------

    def _score_d2_faithfulness(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Return faithfulness score from state or configurable default.

        MiniCheck verification is performed externally by the auditor agent.
        This dimension accepts the result if present, otherwise falls back
        to a configurable default (env: POLARIS_DEFAULT_FAITHFULNESS).
        """
        # Try multiple known state keys for faithfulness
        faithfulness: Optional[float] = None

        # FIX-247: Prefer pipeline_faithfulness (immune key from finalize_node)
        for key in ("pipeline_faithfulness", "post_hoc_faithfulness", "faithfulness", "faithfulness_score"):
            val = state.get(key)
            if val is not None and isinstance(val, (int, float)):
                faithfulness = float(val)
                break

        # Check nested audit_result
        if faithfulness is None:
            audit_result = state.get("audit_result", {})
            if isinstance(audit_result, dict):
                val = audit_result.get("faithfulness")
                if val is not None and isinstance(val, (int, float)):
                    faithfulness = float(val)

        # Check factscore as alternative
        if faithfulness is None:
            factscore = state.get("factscore")
            if factscore is not None and isinstance(factscore, (int, float)):
                faithfulness = float(factscore)

        source = "state"
        if faithfulness is None:
            faithfulness = _DEFAULT_FAITHFULNESS
            source = "default"
            # FIX-255: LOUD WARNING when faithfulness is missing (LAW II)
            logger.warning(
                "D2 FAITHFULNESS MISSING: No faithfulness score found in state. "
                "Defaulting to %.2f (worst-case). This WILL lower the audit score. "
                "Ensure the pipeline calculates faithfulness before auditing.",
                _DEFAULT_FAITHFULNESS,
            )

        # Clamp to [0, 1]
        faithfulness = max(0.0, min(1.0, faithfulness))

        # Scale 0-1 faithfulness to 0-10 score
        score = faithfulness * 10.0

        return {
            "score": round(score, 2),
            "details": {
                "faithfulness_value": round(faithfulness, 4),
                "source": source,
                "default_used": source == "default",
            },
        }

    # -----------------------------------------------------------------
    # D3 -- Semantic Duplication
    # -----------------------------------------------------------------

    def _score_d3_semantic_duplication(
        self, sentences: List[str]
    ) -> Dict[str, Any]:
        """Detect near-duplicate sentences via word-level Jaccard similarity.

        Compares all sentence pairs.  Pairs with Jaccard >= threshold (default
        0.7) are counted as duplicates.
        """
        if len(sentences) < 2:
            return {
                "score": 10.0,
                "details": {
                    "duplicate_pairs": 0,
                    "total_pairs": 0,
                    "duplication_rate": 0.0,
                },
            }

        # Pre-tokenize into word sets
        token_sets: List[Set[str]] = [
            set(_tokenize_words(s)) for s in sentences
        ]

        duplicate_pairs: List[Dict[str, Any]] = []
        total_pairs = 0
        n = len(sentences)

        for i in range(n):
            for j in range(i + 1, n):
                # Skip very short sentences (< 5 words) -- they cause false
                # positives (e.g. "See Table 1." vs "See Table 2.")
                if len(token_sets[i]) < 5 or len(token_sets[j]) < 5:
                    continue

                total_pairs += 1
                sim = _jaccard_similarity(token_sets[i], token_sets[j])
                if sim >= _JACCARD_DUP_THRESHOLD:
                    duplicate_pairs.append({
                        "i": i,
                        "j": j,
                        "similarity": round(sim, 4),
                        "text_i_preview": sentences[i][:80],
                        "text_j_preview": sentences[j][:80],
                    })

        dup_count = len(duplicate_pairs)
        duplication_rate = dup_count / total_pairs if total_pairs > 0 else 0.0

        # Scoring curve:
        #   0 dup pairs -> 10
        #   dup_rate 1% -> ~9
        #   dup_rate 5% -> ~7
        #   dup_rate 15%+ -> 0
        if duplication_rate <= 0.0:
            score = 10.0
        elif duplication_rate >= 0.15:
            score = 0.0
        else:
            score = 10.0 * (1.0 - duplication_rate / 0.15)

        return {
            "score": round(score, 2),
            "details": {
                "duplicate_pairs": dup_count,
                "total_pairs": total_pairs,
                "duplication_rate": round(duplication_rate, 4),
                "threshold": _JACCARD_DUP_THRESHOLD,
                "worst_pairs": sorted(
                    duplicate_pairs,
                    key=lambda p: p["similarity"],
                    reverse=True,
                )[:10],
            },
        }

    # -----------------------------------------------------------------
    # D4 -- Section Balance
    # -----------------------------------------------------------------

    def _score_d4_section_balance(
        self, sections: Dict[str, str]
    ) -> Dict[str, Any]:
        """Evaluate word-count distribution across sections via Shannon entropy.

        A perfectly balanced report (all sections equal length) scores 10.
        Extreme imbalance (one section dominates) scores near 0.
        """
        if len(sections) <= 1:
            # Single section -- cannot measure balance, give neutral score
            word_counts = {
                name: len(_tokenize_words(body))
                for name, body in sections.items()
            }
            return {
                "score": 5.0,
                "details": {
                    "section_count": len(sections),
                    "word_counts": word_counts,
                    "entropy": 0.0,
                    "max_entropy": 0.0,
                    "balance_ratio": 0.0,
                    "note": "Single section -- neutral score assigned",
                },
            }

        word_counts: Dict[str, int] = {}
        for name, body in sections.items():
            word_counts[name] = len(_tokenize_words(body))

        counts_list = list(word_counts.values())
        total_words = sum(counts_list)

        if total_words == 0:
            return {
                "score": 0.0,
                "details": {
                    "section_count": len(sections),
                    "word_counts": word_counts,
                    "entropy": 0.0,
                    "max_entropy": 0.0,
                    "balance_ratio": 0.0,
                },
            }

        entropy = _shannon_entropy(counts_list)
        max_entropy = math.log2(len(counts_list))  # uniform distribution
        balance_ratio = entropy / max_entropy if max_entropy > 0 else 0.0

        # Also penalize critically thin sections (< 50 words)
        thin_sections = [
            name for name, wc in word_counts.items() if 0 < wc < 50
        ]
        thin_penalty = min(len(thin_sections) * 1.0, 4.0)  # up to -4 points

        # Base score from balance ratio (0-10)
        score = balance_ratio * 10.0 - thin_penalty
        score = max(0.0, score)

        return {
            "score": round(score, 2),
            "details": {
                "section_count": len(sections),
                "word_counts": word_counts,
                "entropy": round(entropy, 4),
                "max_entropy": round(max_entropy, 4),
                "balance_ratio": round(balance_ratio, 4),
                "thin_sections": thin_sections,
                "thin_penalty": round(thin_penalty, 2),
            },
        }

    # -----------------------------------------------------------------
    # D5 -- Citation Quality
    # -----------------------------------------------------------------

    def _score_d5_citation_quality(
        self, report: str, word_count: int
    ) -> Dict[str, Any]:
        """Validate [CITE:xxx] format and measure citation density.

        Checks:
        - Total citation tokens found
        - Unique citation IDs
        - Malformed citations (e.g. [CITE:], [CITE:source1])
        - Density per 100 words
        """
        all_cites = _CITE_PATTERN.findall(report)
        valid_cites = _CITE_VALID_PATTERN.findall(report)

        # FIX-243: If no [CITE:xxx] format found, try numbered [N] format
        citation_format = "cite_token"
        if not all_cites:
            numbered_matches = _NUMBERED_CITE_PATTERN.findall(report)
            if numbered_matches:
                citation_format = "numbered"
                all_cites = [f"[{n}]" for n in numbered_matches]
                valid_cites = all_cites  # numbered format is inherently valid
                logger.info(
                    f"[FIX-243] D5: No [CITE:xxx] found, using numbered [N] format "
                    f"({len(all_cites)} citations)"
                )

        total_cites = len(all_cites)
        valid_count = len(valid_cites)
        malformed_count = total_cites - valid_count

        # Extract unique citation IDs
        unique_ids: Set[str] = set()
        if citation_format == "numbered":
            for cite in valid_cites:
                unique_ids.add(cite)  # e.g. "[1]", "[2]"
        else:
            for cite in valid_cites:
                # Extract the ID from [CITE:xxx]
                cite_id = cite[6:-1]  # strip "[CITE:" and "]"
                unique_ids.add(cite_id)

        unique_count = len(unique_ids)
        density_per_100w = (total_cites / word_count * 100) if word_count > 0 else 0.0

        # Detect placeholder citations
        placeholder_patterns = [
            r"\[CITE:source\d*\]",
            r"\[CITE:ref\d*\]",
            r"\[CITE:citation\d*\]",
            r"\[CITE:\]",
            r"\[CITE:xxx\]",
            r"\[CITE:TBD\]",
        ]
        placeholder_count = 0
        for pat in placeholder_patterns:
            placeholder_count += len(re.findall(pat, report, re.IGNORECASE))

        # Malformed rate
        malformed_rate = malformed_count / total_cites if total_cites > 0 else 0.0

        # FIX-258: Scoring components (each 0-10, averaged):
        # 1. Density score: sigmoid curve centered at 3 citations/100w (STORM-level)
        #    - 0 citations: hard 0.0 (not 3.0)
        #    - < 1.0: ramp up (sparse)
        #    - 1.0-5.0: sweet spot (8.0-10.0)
        #    - > 6.0: gentle decline (over-citing)
        if density_per_100w <= 0:
            density_score = 0.0
        elif density_per_100w < 1.0:
            density_score = density_per_100w * 8.0  # linear ramp to 8.0 at 1.0
        elif density_per_100w <= 5.0:
            # Smooth curve: peak 10.0 at ~3.0, 8.0 at edges (1.0 and 5.0)
            center = 3.0
            density_score = 10.0 - 2.0 * ((density_per_100w - center) / 2.0) ** 2
            density_score = max(8.0, min(10.0, density_score))
        elif density_per_100w <= 10.0:
            density_score = 8.0 - (density_per_100w - 5.0) * 1.2  # decline to 2.0
        else:
            density_score = max(0.0, 2.0 - (density_per_100w - 10.0) * 0.4)

        # 2. Unique count score: target >= 10 unique citations
        if unique_count >= 30:
            unique_score = 10.0
        elif unique_count >= 10:
            unique_score = 7.0 + (unique_count - 10) / 20 * 3.0
        elif unique_count >= 5:
            unique_score = 4.0 + (unique_count - 5) / 5 * 3.0
        else:
            unique_score = unique_count / 5 * 4.0

        # 3. Quality score: penalize malformed / placeholder
        quality_score = 10.0
        if malformed_rate > 0:
            quality_score -= malformed_rate * 15.0  # harsh penalty
        quality_score -= placeholder_count * 2.0
        quality_score = max(0.0, quality_score)

        # FIX-258: Hard zero for reports with no citations at all
        if total_cites == 0:
            score = 0.0
        else:
            # Composite
            score = (density_score * 0.35 + unique_score * 0.35 + quality_score * 0.30)

        return {
            "score": round(score, 2),
            "details": {
                "total_citations": total_cites,
                "valid_citations": valid_count,
                "malformed_citations": malformed_count,
                "malformed_rate": round(malformed_rate, 4),
                "unique_citation_ids": unique_count,
                "placeholder_citations": placeholder_count,
                "density_per_100_words": round(density_per_100w, 2),
                "sub_scores": {
                    "density": round(density_score, 2),
                    "unique_count": round(unique_score, 2),
                    "quality": round(quality_score, 2),
                },
            },
        }

    # -----------------------------------------------------------------
    # D6 -- Bibliography
    # -----------------------------------------------------------------

    def _score_d6_bibliography(self, state: Dict[str, Any]) -> Dict[str, Any]:
        """Check URL completeness in evidence / bibliography.

        Examines evidence_chain and bibliography entries for the presence of
        valid source URLs.
        """
        # S6: Compatibility — wiki path writes `evidence`, other paths write
        # `evidence_chain`. Read both; take whichever is non-empty.
        evidence_chain = state.get("evidence_chain") or state.get("evidence", [])
        bibliography = state.get("bibliography", [])

        # FIX-245: Parse evidence entries regardless of format
        evidence_with_url = 0
        evidence_total = len(evidence_chain)
        for ev in evidence_chain:
            ev_dict = self._parse_evidence_entry(ev)
            url = ev_dict.get("source_url", "")
            if url and isinstance(url, str) and url.startswith("http"):
                evidence_with_url += 1

        evidence_url_rate = (
            evidence_with_url / evidence_total if evidence_total > 0 else 0.0
        )

        # Count bibliography entries with URLs, titles, authors
        bib_total = len(bibliography)
        bib_with_url = 0
        bib_with_title = 0
        bib_with_authors = 0

        for entry in bibliography:
            if not isinstance(entry, dict):
                continue
            url = entry.get("source_url", "") or entry.get("url", "")
            if url and isinstance(url, str) and url.startswith("http"):
                bib_with_url += 1
            title = entry.get("title", "")
            if title and isinstance(title, str) and len(title.strip()) > 3:
                bib_with_title += 1
            # FIX-244: Handle both "authors" (list) and "author" (string)
            authors = entry.get("authors", []) or entry.get("author", "")
            if isinstance(authors, str) and authors.strip():
                bib_with_authors += 1
            elif isinstance(authors, list) and len(authors) > 0:
                bib_with_authors += 1

        bib_url_rate = bib_with_url / bib_total if bib_total > 0 else 0.0
        bib_title_rate = bib_with_title / bib_total if bib_total > 0 else 0.0
        bib_author_rate = bib_with_authors / bib_total if bib_total > 0 else 0.0

        # FIX-261: Consistent bibliography scoring — both missing and bad bib
        # are scored proportionally to actual metadata completeness.
        # Missing bib no longer scores HIGHER than a bad bib.
        if bib_total > 0:
            # Bibliography exists: score based on metadata completeness
            bib_quality = bib_url_rate * 0.40 + bib_title_rate * 0.30 + bib_author_rate * 0.30
            score = bib_quality * 10.0
        elif evidence_total > 0:
            # No bibliography but evidence exists: score on evidence URLs, capped at 5.0
            score = evidence_url_rate * 5.0
        else:
            score = 0.0

        return {
            "score": round(score, 2),
            "details": {
                "evidence_total": evidence_total,
                "evidence_with_url": evidence_with_url,
                "evidence_url_rate": round(evidence_url_rate, 4),
                "bibliography_total": bib_total,
                "bibliography_with_url": bib_with_url,
                "bibliography_with_title": bib_with_title,
                "bibliography_with_authors": bib_with_authors,
                "bibliography_url_rate": round(bib_url_rate, 4),
                "bibliography_title_rate": round(bib_title_rate, 4),
                "bibliography_author_rate": round(bib_author_rate, 4),
            },
        }

    # -----------------------------------------------------------------
    # D7 -- Perspective Coverage
    # -----------------------------------------------------------------

    def _score_d7_perspective_coverage(
        self, state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Count unique perspectives and measure balance across evidence.

        Reads ``perspective_origins`` (legacy) OR ``perspective`` (current)
        from evidence entries and, if available, the ``perspective_coverage``
        summary from state.

        S6: Two field drifts fixed — `evidence_chain` vs `evidence` (wiki path
        writes the latter) and `perspective_origins` vs `perspective` (current
        analyzer writes singular field). Reads both; takes whichever non-empty.
        """
        # S6: Compatibility layer — read both state keys
        evidence_chain = state.get("evidence_chain") or state.get("evidence", [])

        # Collect all perspective origins
        perspective_counts: Dict[str, int] = {}
        tagged_count = 0
        total_evidence = len(evidence_chain)

        for ev in evidence_chain:
            # FIX-245: Parse evidence entries regardless of format
            ev_dict = self._parse_evidence_entry(ev)
            # S6: read both legacy `perspective_origins` (list) and current
            # `perspective` (string). Normalize to list.
            origins = ev_dict.get("perspective_origins") or ev_dict.get("perspective", [])
            if isinstance(origins, str):
                origins = [origins] if origins.strip() else []

            if origins and isinstance(origins, list) and len(origins) > 0:
                tagged_count += 1
                for p in origins:
                    if isinstance(p, str) and p.strip():
                        perspective_counts[p.strip()] = perspective_counts.get(p.strip(), 0) + 1

        unique_perspectives = len(perspective_counts)
        tagging_rate = tagged_count / total_evidence if total_evidence > 0 else 0.0

        # Balance score via Shannon entropy
        if unique_perspectives > 1:
            counts_list = list(perspective_counts.values())
            entropy = _shannon_entropy(counts_list)
            max_entropy = math.log2(unique_perspectives)
            balance_score = entropy / max_entropy if max_entropy > 0 else 0.0
        elif unique_perspectives == 1:
            balance_score = 0.0
        else:
            balance_score = 0.0

        # Also check state-level perspective_coverage if available
        state_coverage = state.get("perspective_coverage", {})
        if isinstance(state_coverage, dict) and state_coverage:
            state_balance = state_coverage.get("balance_score", balance_score)
            # Use state value if it provides additional signal
            if isinstance(state_balance, (int, float)):
                balance_score = max(balance_score, float(state_balance))

        # Scoring:
        #   Unique perspectives: target >= 5 for full marks
        #   Balance: 0-1 range
        #   Tagging rate: percentage of evidence with perspective tags
        if unique_perspectives >= 8:
            perspective_score = 10.0
        elif unique_perspectives >= 5:
            perspective_score = 7.0 + (unique_perspectives - 5) / 3 * 3.0
        elif unique_perspectives >= 3:
            perspective_score = 4.0 + (unique_perspectives - 3) / 2 * 3.0
        elif unique_perspectives >= 1:
            perspective_score = unique_perspectives * 2.0
        else:
            perspective_score = 0.0

        # Combine perspective count (50%), balance (30%), tagging rate (20%)
        score = (
            perspective_score * 0.50
            + balance_score * 10.0 * 0.30
            + tagging_rate * 10.0 * 0.20
        )

        return {
            "score": round(min(10.0, score), 2),
            "details": {
                "unique_perspectives": unique_perspectives,
                "perspective_distribution": perspective_counts,
                "balance_score": round(balance_score, 4),
                "tagged_evidence": tagged_count,
                "total_evidence": total_evidence,
                "tagging_rate": round(tagging_rate, 4),
            },
        }

    # -----------------------------------------------------------------
    # D8 -- Topical Relevance
    # -----------------------------------------------------------------

    def _score_d8_topical_relevance(
        self, report: str, original_query: str
    ) -> Dict[str, Any]:
        """Measure keyword overlap between the original query and the report.

        Uses significant (non-stop-word) terms from the query and checks their
        presence in the report text.
        """
        if not original_query or not original_query.strip():
            return {
                "score": 5.0,
                "details": {
                    "note": "No original_query available -- neutral score",
                    "query_keywords": [],
                    "found_keywords": [],
                    "overlap_rate": 0.0,
                },
            }

        query_keywords = _significant_words(original_query)
        if not query_keywords:
            return {
                "score": 5.0,
                "details": {
                    "note": "No significant words in query -- neutral score",
                    "query_keywords": [],
                    "found_keywords": [],
                    "overlap_rate": 0.0,
                },
            }

        # De-duplicate query keywords
        unique_query_keywords = list(dict.fromkeys(query_keywords))

        report_words_set = set(_tokenize_words(report))

        found_keywords: List[str] = []
        missing_keywords: List[str] = []
        for kw in unique_query_keywords:
            if kw in report_words_set:
                found_keywords.append(kw)
            else:
                missing_keywords.append(kw)

        overlap_rate = (
            len(found_keywords) / len(unique_query_keywords)
            if unique_query_keywords
            else 0.0
        )

        # Also measure frequency of query terms in report (density)
        report_words_list = _tokenize_words(report)
        total_report_words = len(report_words_list)
        keyword_frequency = 0
        query_keyword_set = set(unique_query_keywords)
        for w in report_words_list:
            if w in query_keyword_set:
                keyword_frequency += 1

        keyword_density = (
            keyword_frequency / total_report_words if total_report_words > 0 else 0.0
        )

        # Scoring:
        #   Overlap rate drives 70% of score
        #   Density bonus for 30%
        overlap_score = overlap_rate * 10.0

        # FIX-262: Keyword density — symmetric curve penalizing both extremes.
        # Target: 2-5% is healthy research prose. Below = weak coverage, above = keyword stuffing.
        if keyword_density <= 0:
            density_score = 0.0
        elif keyword_density < 0.02:
            # Under 2%: linear ramp (sparse keyword coverage)
            density_score = (keyword_density / 0.02) * 7.0
        elif keyword_density <= 0.05:
            # 2-5%: sweet spot (full marks)
            density_score = 10.0
        elif keyword_density <= 0.10:
            # 5-10%: mild penalty (slightly over-focused)
            density_score = 10.0 - (keyword_density - 0.05) * 80.0  # 10.0 -> 6.0
        else:
            # >10%: severe penalty (keyword stuffing)
            density_score = max(0.0, 6.0 - (keyword_density - 0.10) * 30.0)

        score = overlap_score * 0.70 + density_score * 0.30

        return {
            "score": round(min(10.0, score), 2),
            "details": {
                "query_keywords": unique_query_keywords,
                "found_keywords": found_keywords,
                "missing_keywords": missing_keywords,
                "overlap_rate": round(overlap_rate, 4),
                "keyword_frequency": keyword_frequency,
                "keyword_density": round(keyword_density, 4),
                "sub_scores": {
                    "overlap": round(overlap_score, 2),
                    "density": round(density_score, 2),
                },
            },
        }

    # -----------------------------------------------------------------
    # D9 -- Coherence
    # -----------------------------------------------------------------

    def _score_d9_coherence(
        self, report: str, sentences: List[str]
    ) -> Dict[str, Any]:
        """Assess coherence via transition word density and sentence length
        variation (coefficient of variation).

        Higher transition density suggests better logical flow.  Moderate
        sentence length variation indicates varied but not erratic writing.
        """
        if not sentences or len(sentences) < 3:
            return {
                "score": 5.0,
                "details": {
                    "note": "Too few sentences for coherence analysis",
                    "transition_density": 0.0,
                    "sentence_length_cv": 0.0,
                },
            }

        # Transition word density (per sentence)
        report_lower = report.lower()
        transition_hits = 0
        for tw in _TRANSITION_WORDS:
            transition_hits += len(re.findall(r"\b" + re.escape(tw) + r"\b", report_lower))

        transition_density = transition_hits / len(sentences)

        # Sentence length variation (coefficient of variation)
        sentence_lengths = np.array(
            [len(_tokenize_words(s)) for s in sentences], dtype=np.float64
        )
        mean_length = float(np.mean(sentence_lengths))
        std_length = float(np.std(sentence_lengths))
        cv = std_length / mean_length if mean_length > 0 else 0.0

        # Scoring:
        # Transition density: target 0.3-0.8 per sentence
        if transition_density <= 0.0:
            trans_score = 0.0
        elif transition_density < 0.1:
            trans_score = transition_density / 0.1 * 3.0
        elif transition_density <= 0.8:
            trans_score = 3.0 + (transition_density - 0.1) / 0.7 * 7.0
        elif transition_density <= 1.5:
            trans_score = 10.0  # very good
        else:
            trans_score = max(5.0, 10.0 - (transition_density - 1.5) * 2.0)

        # CV: target 0.3-0.7 (moderate variation)
        # Too low (< 0.2) = monotonous, too high (> 1.0) = erratic
        if cv < 0.1:
            cv_score = 3.0
        elif cv < 0.3:
            cv_score = 3.0 + (cv - 0.1) / 0.2 * 4.0
        elif cv <= 0.7:
            cv_score = 10.0
        elif cv <= 1.0:
            cv_score = 10.0 - (cv - 0.7) / 0.3 * 5.0
        else:
            cv_score = max(0.0, 5.0 - (cv - 1.0) * 5.0)

        score = trans_score * 0.60 + cv_score * 0.40

        return {
            "score": round(score, 2),
            "details": {
                "transition_hits": transition_hits,
                "transition_density_per_sentence": round(transition_density, 4),
                "mean_sentence_length_words": round(mean_length, 1),
                "std_sentence_length_words": round(std_length, 1),
                "sentence_length_cv": round(cv, 4),
                "sub_scores": {
                    "transition": round(trans_score, 2),
                    "length_variation": round(cv_score, 2),
                },
            },
        }

    # -----------------------------------------------------------------
    # D10 -- Pipeline Integrity
    # -----------------------------------------------------------------

    def _score_d10_pipeline_integrity(
        self, state: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Assess pipeline health from error and fallback counts in state.

        Reads ``errors``, ``agent_trace``, and gating case to evaluate how
        cleanly the pipeline executed.
        """
        errors = state.get("errors", [])
        error_count = len(errors) if isinstance(errors, list) else 0

        # Count fallbacks from agent_trace
        agent_trace = state.get("agent_trace", [])
        fallback_count = 0
        if isinstance(agent_trace, list):
            for entry in agent_trace:
                if isinstance(entry, dict):
                    action = str(entry.get("action", "")).lower()
                    if "fallback" in action or "retry" in action:
                        fallback_count += 1

        # FIX-259: Gating case penalty — recalibrated so downgraded reports
        # cost more than minor pipeline errors (was 1/4/8, now 3/6/9).
        gating_case = state.get("gating_case", "")
        gating_penalty = 0.0
        if gating_case == "CASE_4":
            gating_penalty = 9.0
        elif gating_case == "CASE_3":
            gating_penalty = 6.0
        elif gating_case == "CASE_2":
            gating_penalty = 3.0

        # Base: 10, subtract for errors and fallbacks
        # Each error costs 0.5, each fallback costs 0.25
        error_penalty = min(error_count * 0.5, 5.0)
        fallback_penalty = min(fallback_count * 0.25, 3.0)

        score = 10.0 - error_penalty - fallback_penalty - gating_penalty
        score = max(0.0, score)

        return {
            "score": round(score, 2),
            "details": {
                "error_count": error_count,
                "fallback_count": fallback_count,
                "gating_case": gating_case,
                "penalties": {
                    "errors": round(error_penalty, 2),
                    "fallbacks": round(fallback_penalty, 2),
                    "gating": round(gating_penalty, 2),
                },
                "error_samples": [
                    (str(e)[:120] if not isinstance(e, dict) else {
                        k: str(v)[:80] for k, v in list(e.items())[:3]
                    })
                    for e in (errors[:5] if isinstance(errors, list) else [])
                ],
            },
        }

    # -----------------------------------------------------------------
    # Internal helpers
    # -----------------------------------------------------------------

    def _extract_report(self, state: Dict[str, Any]) -> str:
        """Extract the report text from state, preferring final_report."""
        for key in ("final_report", "draft_report"):
            report = state.get(key)
            if report and isinstance(report, str) and len(report.strip()) > 0:
                return report.strip()
        return ""

    def _empty_result(self, reason: str) -> Dict[str, Any]:
        """Return a zero-score result when the audit cannot proceed."""
        dimensions = []
        for display_name, key in [
            ("D1 CoT Leakage", "d1_cot_leakage"),
            ("D2 Faithfulness", "d2_faithfulness"),
            ("D3 Semantic Duplication", "d3_semantic_duplication"),
            ("D4 Section Balance", "d4_section_balance"),
            ("D5 Citation Quality", "d5_citation_quality"),
            ("D6 Bibliography", "d6_bibliography"),
            ("D7 Perspective Coverage", "d7_perspective_coverage"),
            ("D8 Topical Relevance", "d8_topical_relevance"),
            ("D9 Coherence", "d9_coherence"),
            ("D10 Pipeline Integrity", "d10_pipeline_integrity"),
        ]:
            dimensions.append({
                "name": display_name,
                "key": key,
                "score": 0.0,
                "weight": self.weights[key],
                "weighted": 0.0,
                "details": {"error": reason},
            })

        return {
            "total_score": 0.0,
            "dimensions": dimensions,
            "metadata": {
                "audit_version": self.AUDIT_VERSION,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "word_count": 0,
                "sentence_count": 0,
                "section_count": 0,
                "original_query": "",
                "vector_id": "unknown",
                "error": reason,
            },
        }
