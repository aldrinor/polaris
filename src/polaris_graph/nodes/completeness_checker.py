"""
Completeness checklist checker — HONEST-REBUILD R-6 Gap-3.

Loads the per-domain completeness checklist YAML. For each topic,
checks whether the retrieved evidence corpus has keyword coverage.
Uncovered topics get a list of suggested expansion queries so the
orchestrator can trigger a targeted retrieval pass.

HONESTY GUARANTEE: this module surfaces GAPS. It does NOT silently
synthesize over them. When a topic is uncovered, the final report's
Limitations paragraph MUST acknowledge it (the orchestrator injects
the gap into the pipeline_telemetry block).
"""
from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

logger = logging.getLogger("polaris_graph.completeness_checker")

_REPO_ROOT = Path(__file__).resolve().parents[3]
_CHECKLIST_DIR = _REPO_ROOT / "config" / "completeness_checklists"

# ── I-pipe-011 (#1236): shared benchmark-strict-gates switch ──────────────────
# When OFF (default) a vacuous "0 of 0" completeness (no planner facet / empty
# checklist applied → `completeness_state == "not_applicable"`) is left ADVISORY,
# exactly as before — every existing consumer is byte-identical. When the operator
# turns the SHARED benchmark flag ON, a run with no measured coverage DENOMINATOR
# must NOT read as complete: `completeness_ready` flips to False for not_applicable
# so a 0/0 run is surfaced as NOT-COMPLETE rather than a silent vacuous pass.
#
# Faithfulness note: this gate only adds a FAIL-LOUD condition (a 0/0 run is held,
# not released). It NEVER relaxes strict_verify / NLI / the 4-role D8 audit, never
# fabricates a denominator, and never changes a MEASURED fraction.
_BENCHMARK_STRICT_GATES_ENV = "PG_BENCHMARK_STRICT_GATES"
_TRUE_TOKENS = frozenset({"1", "true", "yes", "on"})


def _benchmark_strict_gates() -> bool:
    """Return True iff PG_BENCHMARK_STRICT_GATES is set to a truthy token.

    Default OFF: an unset / empty / falsy value yields False, so the strict
    0/0-is-not-complete behavior is opt-in for benchmark runs only.
    """
    raw = os.getenv(_BENCHMARK_STRICT_GATES_ENV)
    if raw is None:
        return False
    return raw.strip().lower() in _TRUE_TOKENS


@dataclass
class ChecklistTopic:
    id: str
    label: str
    keywords: list[str] = field(default_factory=list)
    applies_if: list[str] = field(default_factory=list)
    expand_queries: list[str] = field(default_factory=list)
    # I-arch-004 F11 (#1249): clinical-safety-critical topics (contraindications,
    # boxed warnings). When True AND the topic is applicable+uncovered, the sweep
    # HOLDS release (non-success) instead of shipping an advisory ok_incomplete_corpus.
    # Default False so every un-marked topic / checklist is byte-identical.
    critical: bool = False


@dataclass
class TopicCoverage:
    topic: ChecklistTopic
    applies: bool
    covered: bool
    hits: int                     # number of evidence rows that matched
    matched_keywords: list[str] = field(default_factory=list)


@dataclass
class CompletenessReport:
    domain: str
    topics: list[TopicCoverage] = field(default_factory=list)
    total_applicable: int = 0
    total_covered: int = 0
    total_uncovered: int = 0
    expand_queries: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)

    @property
    def covered_fraction(self) -> float:
        if self.total_applicable == 0:
            return 1.0
        return self.total_covered / self.total_applicable

    @property
    def completeness_state(self) -> str:
        """FX-10 (I-ready-017): three-valued-logic state for the completeness check.

        When no checklist topic applies (``total_applicable == 0``) the numeric
        ``covered_fraction`` is a VACUOUS 1.0 — that is NOT_APPLICABLE, not a measured
        pass (SQL 3VL: an empty applicable set is UNKNOWN/NULL, never TRUE). The numeric
        stays as-is (consumers compare it and must not hit a TypeError), and this state
        field is what disambiguates a vacuous 1.0 from a genuinely-measured 1.0.
        """
        return "not_applicable" if self.total_applicable == 0 else "measured"

    @property
    def completeness_ready(self) -> bool:
        """I-pipe-011 (#1236): is this completeness result a NON-vacuous PASS?

        Three-valued logic, gated by ``PG_BENCHMARK_STRICT_GATES``:

        * ``measured`` (real denominator, ``total_applicable > 0``): READY iff the
          measured fraction clears ``min_covered_fraction`` (default 0.5) — same
          measured behaviour in both flag states.
        * ``not_applicable`` (``total_applicable == 0`` → vacuous ``covered_fraction``
          of 1.0 from an empty checklist / no planner facet):
            - flag OFF (default): READY (advisory pass — byte-identical to the prior
              behaviour where a 0/0 result was never a release blocker).
            - flag ON (benchmark strict): NOT READY. A run with no measured coverage
              DENOMINATOR must not read as complete; 0/0 is surfaced as NOT-COMPLETE
              so the gate FAILS LOUD instead of passing vacuously.

        This NEVER touches strict_verify / NLI / the 4-role D8 audit, never invents a
        denominator, and never alters a measured fraction. It only adds a held verdict
        for an empty denominator when the benchmark flag is on.
        """
        return self.is_complete()

    def is_complete(self, *, min_covered_fraction: float = 0.5) -> bool:
        """Parametrised form of :pyattr:`completeness_ready` (testable threshold).

        ``min_covered_fraction`` only affects the ``measured`` branch; the
        ``not_applicable`` branch is decided solely by ``PG_BENCHMARK_STRICT_GATES``.
        """
        if self.completeness_state == "not_applicable":
            # 0/0: vacuous. Strict benchmark mode refuses to call it complete.
            return not _benchmark_strict_gates()
        # Measured denominator: identical decision regardless of the flag.
        return self.covered_fraction >= min_covered_fraction

    def uncovered_topic_ids(self) -> list[str]:
        return [
            tc.topic.id
            for tc in self.topics
            if tc.applies and not tc.covered
        ]

    def uncovered_critical_topic_ids(self) -> list[str]:
        """I-arch-004 F11 (#1249): ids of APPLICABLE, UNCOVERED topics marked
        ``critical: true`` in the checklist YAML (e.g. ``contraindications``).

        A clinical report that ships with zero coverage of a critical-safety topic
        (contraindications, boxed warnings) is a clinical-safety hole — the
        completeness gate previously treated ALL uncovered topics as advisory
        (``ok_incomplete_corpus``). This surfaces the critical subset so the sweep can
        HOLD release (non-success) for them while non-critical gaps stay advisory.

        Empty unless a topic is explicitly marked critical in the checklist, so
        every existing (un-marked) checklist yields [] -> byte-identical behaviour."""
        return [
            tc.topic.id
            for tc in self.topics
            if tc.applies and not tc.covered and getattr(tc.topic, "critical", False)
        ]


def load_checklist(domain: str) -> list[ChecklistTopic]:
    """Load config/completeness_checklists/{domain}.yaml."""
    if yaml is None:
        logger.warning("[completeness] yaml not available; no checklist loaded")
        return []
    path = _CHECKLIST_DIR / f"{domain}.yaml"
    if not path.exists():
        logger.info("[completeness] no checklist for domain=%r", domain)
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:
        logger.warning("[completeness] yaml parse failed for %r: %s", path, exc)
        return []
    topics_raw = data.get("topics") or []
    topics: list[ChecklistTopic] = []
    for t in topics_raw:
        if not isinstance(t, dict):
            continue
        tid = str(t.get("id") or "").strip()
        if not tid:
            continue
        topics.append(ChecklistTopic(
            id=tid,
            label=str(t.get("label") or tid),
            keywords=[str(k).lower() for k in (t.get("keywords") or [])],
            applies_if=[str(a).lower() for a in (t.get("applies_if") or [])],
            expand_queries=[str(q) for q in (t.get("expand_queries") or [])],
            # I-arch-004 F11 (#1249): optional `critical: true` marks a clinical-safety
            # topic whose uncovered state HOLDS release. Absent/false -> byte-identical.
            critical=bool(t.get("critical", False)),
        ))
    return topics


def _topic_applies(
    topic: ChecklistTopic,
    research_question: str,
    evidence_blob: str,
) -> bool:
    """Return True if the topic should be checked for this query.

    A topic with no `applies_if` always applies. A topic with
    `applies_if` terms applies only if any term is found in the
    research_question OR the evidence pool (since "GLP-1" might be
    implied by the drug name).
    """
    if not topic.applies_if:
        return True
    q_lower = (research_question or "").lower()
    e_lower = (evidence_blob or "").lower()
    for term in topic.applies_if:
        if term in q_lower or term in e_lower:
            return True
    return False


def _compile_keyword_re(keywords: list[str]) -> re.Pattern:
    if not keywords:
        return re.compile(r"(?!x)x")  # never matches
    parts = [re.escape(k) for k in keywords]
    return re.compile(r"|".join(parts), re.IGNORECASE)


def check_completeness(
    *,
    domain: str,
    research_question: str,
    evidence_rows: list[dict[str, Any]],
    min_hits_to_cover: int = 1,
    drug_or_topic_hint: str = "",
) -> CompletenessReport:
    """Check evidence rows against the domain's completeness checklist.

    Args:
        domain: scope-template domain name.
        research_question: the user's query (drives applies_if filter).
        evidence_rows: evidence dicts with 'direct_quote' / 'statement'.
        min_hits_to_cover: min # of evidence rows that must match at
            least one keyword for a topic to be "covered" (default 1).
        drug_or_topic_hint: optional {drug} substitution for expand_queries
            (otherwise uses first significant noun from the question).

    Returns CompletenessReport with per-topic coverage + expand_queries
    for uncovered topics.
    """
    topics = load_checklist(domain)
    if not topics:
        return CompletenessReport(domain=domain, notes=["no_checklist_loaded"])

    # Build an all-evidence text blob for applies_if checks
    evidence_blob = " ".join(
        (ev.get("direct_quote") or "") + " " + (ev.get("statement") or "")
        for ev in evidence_rows
    )

    # Pick a substitution token for {drug}/{topic}/{company}/{product}
    # placeholders in expand_queries. Use explicit hint if given, else
    # attempt to pull a drug name or the first significant noun from
    # the research_question.
    token = (drug_or_topic_hint or "").strip()
    if not token:
        try:
            from src.polaris_graph.nodes.scope_gate import _DRUG_NAME_RE
            m = _DRUG_NAME_RE.search(research_question)
            if m:
                token = m.group(1)
        except Exception:
            pass
    if not token:
        # First capitalized or salient noun phrase, naive fallback
        m = re.search(r"\b([A-Z][A-Za-z\-]{3,})\b", research_question)
        if m:
            token = m.group(1)
    if not token:
        token = "topic"

    coverages: list[TopicCoverage] = []
    all_expand_queries: list[str] = []

    for topic in topics:
        applies = _topic_applies(topic, research_question, evidence_blob)
        if not applies:
            coverages.append(TopicCoverage(
                topic=topic, applies=False,
                covered=False, hits=0,
            ))
            continue

        kw_re = _compile_keyword_re(topic.keywords)
        hits = 0
        matched: list[str] = []
        for ev in evidence_rows:
            quote = (
                (ev.get("direct_quote") or "")
                + " "
                + (ev.get("statement") or "")
            )
            m = kw_re.search(quote)
            if m:
                hits += 1
                if m.group(0).lower() not in matched:
                    matched.append(m.group(0).lower())

        covered = hits >= min_hits_to_cover
        coverages.append(TopicCoverage(
            topic=topic, applies=True, covered=covered,
            hits=hits, matched_keywords=matched,
        ))

        if not covered:
            # Substitute placeholders
            for q in topic.expand_queries:
                q_sub = (
                    q.replace("{drug}", token)
                     .replace("{topic}", token)
                     .replace("{company}", token)
                     .replace("{product}", token)
                )
                all_expand_queries.append(q_sub)

    applicable = sum(1 for c in coverages if c.applies)
    covered_n = sum(1 for c in coverages if c.applies and c.covered)
    uncovered_n = applicable - covered_n

    notes: list[str] = []
    if uncovered_n > 0:
        uncovered_labels = [
            c.topic.label for c in coverages
            if c.applies and not c.covered
        ]
        notes.append(
            f"{uncovered_n}/{applicable} applicable topic(s) uncovered: "
            f"{uncovered_labels}"
        )

    return CompletenessReport(
        domain=domain,
        topics=coverages,
        total_applicable=applicable,
        total_covered=covered_n,
        total_uncovered=uncovered_n,
        expand_queries=all_expand_queries,
        notes=notes,
    )
