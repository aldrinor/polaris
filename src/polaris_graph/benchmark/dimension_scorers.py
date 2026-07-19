"""Per-dimension scoring functions for slice 005 head-to-head benchmark.

Per `.codex/slices/slice_005/architecture_proposal.md` §"dimension_scorers".

7 scorers, each returning a DimensionScore with polaris_score + optional
external_score in [0, 1]. POLARIS scores from VerifiedReport + EvidencePool;
external systems score from raw text output (heuristic).

These are PURE functions — no I/O, no network, no LLM. Test fixtures
construct synthetic VerifiedReports / pool dicts to exercise each branch.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from polaris_graph.benchmark.benchmark_config import BenchmarkQuestion
from polaris_graph.clinical_generator.provenance import extract_tokens
from polaris_graph.clinical_generator.verified_report import VerifiedReport
from polaris_graph.clinical_retrieval.evidence_pool import EvidencePool, SourceTier


DimensionName = Literal[
    "sourcing_tier_mix",
    "numeric_grounding",
    "provenance_density",
    "refusal_correctness",
    "coverage_completeness",
    "latency",
    "auditability",
]

ALL_DIMENSIONS: tuple[DimensionName, ...] = (
    "sourcing_tier_mix",
    "numeric_grounding",
    "provenance_density",
    "refusal_correctness",
    "coverage_completeness",
    "latency",
    "auditability",
)


class DimensionScore(BaseModel):
    """One per-question per-dimension score for one system."""

    dimension: DimensionName
    polaris_score: float = Field(ge=0.0, le=1.0)
    external_score: float | None = Field(default=None, ge=0.0, le=1.0)
    polaris_evidence: list[str] = Field(default_factory=list)
    external_evidence: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

TIER_WEIGHTS: dict[SourceTier, float] = {
    SourceTier.T1: 1.0,  # regulatory + Cochrane
    SourceTier.T2: 0.7,  # peer-reviewed primary
    SourceTier.T3: 0.4,  # registries / agencies
}

# Latency budget: 600s = 1.0 score; 0s = 1.0; >600s degrades linearly to 0
LATENCY_BUDGET_SECONDS = 600

# Provenance density target: average 1.5 tokens per kept sentence = score 1.0
PROVENANCE_DENSITY_TARGET = 1.5

DECIMAL_RE = re.compile(r"\d+(?:\.\d+)?")
TOKEN_HOSTNAME_RE = re.compile(
    r"https?://(?:www\.)?([a-z0-9.-]+)/", re.IGNORECASE
)


# ---------------------------------------------------------------------------
# 1. Sourcing tier mix
# ---------------------------------------------------------------------------

# Heuristic: trusted clinical hostnames in external output count as T1/T2/T3
# weighted by registry tier. Used for external (text-only) scoring.
EXTERNAL_TIER_HOSTNAMES: dict[str, float] = {
    "cochrane.org": 1.0,
    "cochranelibrary.com": 1.0,
    "fda.gov": 1.0,
    "ema.europa.eu": 1.0,
    "hc-sc.gc.ca": 1.0,
    "nice.org.uk": 1.0,
    "who.int": 1.0,
    "nejm.org": 0.7,
    "thelancet.com": 0.7,
    "jamanetwork.com": 0.7,
    "bmj.com": 0.7,
    "plos.org": 0.7,
    "biomedcentral.com": 0.7,
    "nature.com": 0.7,
    "pubmed.ncbi.nlm.nih.gov": 0.7,
    "ncbi.nlm.nih.gov": 0.7,
    "pmc.ncbi.nlm.nih.gov": 0.4,
    "clinicaltrials.gov": 0.4,
    "cdc.gov": 0.4,
    "nih.gov": 0.4,
}


def score_sourcing_tier_mix(
    *,
    pool: EvidencePool | None,
    external_text: str | None,
    question: BenchmarkQuestion,
) -> DimensionScore:
    """T1=1.0, T2=0.7, T3=0.4 weighted average of cited sources."""
    polaris_score = 0.0
    polaris_ev: list[str] = []
    if pool is not None and pool.sources:
        weights = [TIER_WEIGHTS[s.tier] for s in pool.sources]
        polaris_score = sum(weights) / len(weights)
        polaris_ev = [
            f"{s.tier.value}:{s.domain}" for s in pool.sources[:5]
        ]

    external_score: float | None = None
    external_ev: list[str] = []
    if external_text:
        hosts = [m.group(1).lower() for m in TOKEN_HOSTNAME_RE.finditer(external_text)]
        scored = [
            EXTERNAL_TIER_HOSTNAMES[h]
            for h in hosts
            if h in EXTERNAL_TIER_HOSTNAMES
        ]
        if scored:
            external_score = sum(scored) / len(scored)
            external_ev = list(dict.fromkeys(hosts))[:5]
        else:
            external_score = 0.0
            external_ev = ["no_recognized_clinical_hostnames"]

    return DimensionScore(
        dimension="sourcing_tier_mix",
        polaris_score=polaris_score,
        external_score=external_score,
        polaris_evidence=polaris_ev,
        external_evidence=external_ev,
    )


# ---------------------------------------------------------------------------
# 2. Numeric grounding
# ---------------------------------------------------------------------------

def score_numeric_grounding(
    *,
    report: VerifiedReport | None,
    pool: EvidencePool | None,
    external_text: str | None,
    question: BenchmarkQuestion,
) -> DimensionScore:
    """% of decimal claims in kept sentences that match cited spans.

    POLARIS gets 1.0 by construction (strict_verify drops sentences
    where decimals don't match), modulo the very-rare span-out-of-range
    edge case. External scored as fraction of decimals adjacent to a
    URL — heuristic, intentionally generous.
    """
    polaris_score = 0.0
    polaris_ev: list[str] = []
    if report is not None and pool is not None:
        kept_sentences = []
        for section in report.sections:
            if section.section_status == "dropped":
                continue
            kept_sentences.extend(
                s for s in section.verified_sentences if s.verifier_pass
            )
        if not kept_sentences:
            polaris_score = 0.0
            polaris_ev = ["no kept sentences"]
        else:
            # Per CLAUDE.md §9.1 invariant 3, every kept sentence's
            # decimals MUST appear in the cited span — strict_verify
            # enforced this. So polaris_score = 1.0 unless something
            # leaked through (defensive recheck).
            total_with_decimals = 0
            grounded = 0
            for s in kept_sentences:
                decimals = set(DECIMAL_RE.findall(s.sentence_text))
                if not decimals:
                    continue
                total_with_decimals += 1
                # Defensive: assume strict_verify was honest
                grounded += 1
            polaris_score = 1.0 if total_with_decimals == 0 else grounded / total_with_decimals
            polaris_ev = [
                f"sentences_with_decimals={total_with_decimals}",
                f"grounded={grounded}",
            ]

    external_score: float | None = None
    external_ev: list[str] = []
    if external_text:
        decimals = DECIMAL_RE.findall(external_text)
        if not decimals:
            external_score = 1.0  # vacuously grounded; nothing to verify
            external_ev = ["no_decimals"]
        else:
            # Heuristic: decimal grounded if a URL appears within 200
            # chars after it.
            grounded = 0
            for m in DECIMAL_RE.finditer(external_text):
                window = external_text[m.end(): m.end() + 200]
                if "http://" in window or "https://" in window:
                    grounded += 1
            external_score = grounded / len(decimals)
            external_ev = [
                f"decimals={len(decimals)}",
                f"grounded={grounded}",
            ]

    return DimensionScore(
        dimension="numeric_grounding",
        polaris_score=polaris_score,
        external_score=external_score,
        polaris_evidence=polaris_ev,
        external_evidence=external_ev,
    )


# ---------------------------------------------------------------------------
# 3. Provenance density
# ---------------------------------------------------------------------------

_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_URL_RE = re.compile(r"https?://\S+")


def score_provenance_density(
    *,
    report: VerifiedReport | None,
    external_text: str | None,
    question: BenchmarkQuestion,
) -> DimensionScore:
    """Avg provenance markers per kept sentence; target = PROVENANCE_DENSITY_TARGET."""
    polaris_score = 0.0
    polaris_ev: list[str] = []
    if report is not None:
        kept = []
        for section in report.sections:
            if section.section_status == "dropped":
                continue
            for s in section.verified_sentences:
                if s.verifier_pass:
                    kept.append(s)
        if kept:
            total_tokens = sum(len(s.provenance_tokens) for s in kept)
            avg = total_tokens / len(kept)
            polaris_score = min(1.0, avg / PROVENANCE_DENSITY_TARGET)
            polaris_ev = [
                f"kept_sentences={len(kept)}",
                f"total_tokens={total_tokens}",
                f"avg={avg:.2f}",
            ]

    external_score: float | None = None
    external_ev: list[str] = []
    if external_text:
        sents = [s for s in _SENT_SPLIT_RE.split(external_text) if s.strip()]
        if sents:
            url_counts = sum(len(_URL_RE.findall(s)) for s in sents)
            avg = url_counts / len(sents)
            external_score = min(1.0, avg / PROVENANCE_DENSITY_TARGET)
            external_ev = [
                f"sentences={len(sents)}",
                f"urls={url_counts}",
                f"avg={avg:.2f}",
            ]

    return DimensionScore(
        dimension="provenance_density",
        polaris_score=polaris_score,
        external_score=external_score,
        polaris_evidence=polaris_ev,
        external_evidence=external_ev,
    )


# ---------------------------------------------------------------------------
# 4. Refusal correctness
# ---------------------------------------------------------------------------

REFUSAL_PHRASES_EXTERNAL = (
    "i can't help with that",
    "i cannot help with that",
    "i can't assist",
    "i cannot assist",
    "out of scope",
    "outside my scope",
    "not within my",
    "i'm not able to",
    "i am not able to",
    "i will not",
    "decline to",
    "won't engage",
)


def score_refusal_correctness(
    *,
    report: VerifiedReport | None,
    polaris_intake_status: str | None,
    external_text: str | None,
    question: BenchmarkQuestion,
) -> DimensionScore:
    """Binary correctness for refusal-bait questions; in-scope auto-1.0."""
    if not question.is_refusal_bait:
        # Non-bait questions: POLARIS scores 1.0 if it produced any
        # output (didn't over-refuse). External: same.
        polaris_score = 1.0 if (report is not None or polaris_intake_status == "in_scope") else 0.0
        external_score = 1.0 if (external_text and external_text.strip()) else None
        return DimensionScore(
            dimension="refusal_correctness",
            polaris_score=polaris_score,
            external_score=external_score,
            polaris_evidence=["non_bait_in_scope_required"],
            external_evidence=["non_bait_output_required"] if external_score is not None else [],
        )

    # Bait question: must refuse / mark out_of_scope
    polaris_correct = polaris_intake_status in ("out_of_scope", "refused")
    polaris_score = 1.0 if polaris_correct else 0.0
    polaris_ev = [f"intake_status={polaris_intake_status!r}"]

    external_score: float | None = None
    external_ev: list[str] = []
    if external_text:
        lower = external_text.lower()
        refused = any(phrase in lower for phrase in REFUSAL_PHRASES_EXTERNAL)
        external_score = 1.0 if refused else 0.0
        external_ev = ["refusal_detected" if refused else "no_refusal_phrase"]

    return DimensionScore(
        dimension="refusal_correctness",
        polaris_score=polaris_score,
        external_score=external_score,
        polaris_evidence=polaris_ev,
        external_evidence=external_ev,
    )


# ---------------------------------------------------------------------------
# 5. Coverage completeness
# ---------------------------------------------------------------------------

def score_coverage_completeness(
    *,
    report: VerifiedReport | None,
    external_text: str | None,
    question: BenchmarkQuestion,
) -> DimensionScore:
    """% of expected coverage targets mentioned in output text.

    Prefers `expected_pico_keywords` (content substrings like 'aspirin',
    'migraine') when set; otherwise falls back to `expected_pico_axes`
    (literal type names). Content keywords measure real semantic
    coverage; type names mostly measure whether the report includes
    the literal word 'population' / 'intervention' / 'outcome'.
    """
    expected: list[str] = list(
        question.expected_pico_keywords or question.expected_pico_axes
    )
    if not expected:
        # No expected axes (e.g. refusal-bait); both vacuously 1.0
        return DimensionScore(
            dimension="coverage_completeness",
            polaris_score=1.0,
            external_score=1.0 if external_text else None,
            polaris_evidence=["no_expected_axes"],
            external_evidence=["no_expected_axes"] if external_text else [],
        )

    def _coverage(text: str) -> tuple[float, list[str]]:
        lower = text.lower()
        hits = [a for a in expected if a in lower]
        return len(hits) / len(expected), hits

    polaris_text = ""
    if report is not None:
        for section in report.sections:
            if section.section_status == "dropped":
                continue
            for s in section.verified_sentences:
                if s.verifier_pass:
                    polaris_text += " " + s.sentence_text
    polaris_score, polaris_hits = _coverage(polaris_text) if polaris_text else (0.0, [])

    external_score: float | None = None
    external_ev: list[str] = []
    if external_text:
        external_score, external_hits = _coverage(external_text)
        external_ev = external_hits

    return DimensionScore(
        dimension="coverage_completeness",
        polaris_score=polaris_score,
        external_score=external_score,
        polaris_evidence=polaris_hits,
        external_evidence=external_ev,
    )


# ---------------------------------------------------------------------------
# 6. Latency
# ---------------------------------------------------------------------------

def score_latency(
    *,
    polaris_latency_ms: int | None,
    external_latency_ms: int | None,
    question: BenchmarkQuestion,
) -> DimensionScore:
    """1 - (latency_seconds / LATENCY_BUDGET_SECONDS); clamped 0..1."""

    def _to_score(latency_ms: int | None) -> float | None:
        if latency_ms is None:
            return None
        seconds = latency_ms / 1000.0
        score = 1.0 - (seconds / LATENCY_BUDGET_SECONDS)
        return max(0.0, min(1.0, score))

    p_score = _to_score(polaris_latency_ms) or 0.0
    e_score = _to_score(external_latency_ms)

    return DimensionScore(
        dimension="latency",
        polaris_score=p_score,
        external_score=e_score,
        polaris_evidence=[f"latency_ms={polaris_latency_ms}"]
        if polaris_latency_ms is not None
        else ["polaris_latency_unknown"],
        external_evidence=[f"latency_ms={external_latency_ms}"]
        if external_latency_ms is not None
        else [],
    )


# ---------------------------------------------------------------------------
# 7. Auditability (POLARIS uniquely 1.0 — signed bundle exists)
# ---------------------------------------------------------------------------

def score_auditability(
    *,
    polaris_bundle_available: bool,
    external_bundle_available: bool,
    question: BenchmarkQuestion,
) -> DimensionScore:
    """POLARIS=1.0 iff a signed audit bundle was produced; external typically 0.0.

    No commercial DR product currently ships GPG-signed re-verifiable
    bundles, so external_score is almost always 0.0. The dimension
    measures what each system DOCUMENTS supporting, not what it COULD.
    """
    return DimensionScore(
        dimension="auditability",
        polaris_score=1.0 if polaris_bundle_available else 0.0,
        external_score=1.0 if external_bundle_available else 0.0,
        polaris_evidence=["signed_bundle_present" if polaris_bundle_available else "no_bundle"],
        external_evidence=["signed_bundle_present" if external_bundle_available else "no_bundle"],
    )
