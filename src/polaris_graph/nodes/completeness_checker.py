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

# ── BUG-7 (I-arch-006, #1262): robust drug/intervention applicability gate ────
# THE BUG: the GLP-1 / drug-pharmacology checklist (contraindications [critical],
# pancreatitis/thyroid/gallbladder, drug interactions, regulatory approval, …) was
# applied to NON-drug clinical questions (gut-microbiota, Parkinson's, metal-ions)
# purely because they route domain="clinical". `_topic_applies` only did a STATIC
# substring match of `applies_if` terms against the question OR the evidence blob,
# and topics with no `applies_if` (e.g. the CRITICAL `contraindications` topic)
# applied to EVERY clinical question unconditionally. Result: a false "7/7 fully
# covered" AND — worse — the critical-contraindications topic gating
# `abort_critical_topic_uncovered` fired spuriously (or, if incidental evidence
# mentioned a drug word, falsely read as covered) on questions that have no drug
# at all. Both are clinical-safety failures: a false-negative on applicability for
# a CRITICAL topic silently disables a real safety abort.
#
# THE FIX: a topic flagged `requires_drug_intervention: true` becomes applicable
# only when the QUESTION is actually about a drug/intervention, decided by the
# SAME config-driven recognizer the scope gate uses (`scope_gate._intervention_present`
# = canonical drug names + WHO/USAN INN-stem generative recognition + class
# anchors via the topic's own `applies_if` terms matched against the QUESTION).
# This is a robust detector, NOT a raw substring or the routing label.
#
# FAIL-CLOSED / DISCLOSE ON AMBIGUITY: if the recognizer is unavailable (PyYAML
# missing, config absent, import/build error) we CANNOT confidently conclude
# "no drug". For a CRITICAL topic we then default to APPLIES=True and DISCLOSE a
# note (never silently mark a critical safety topic non-applicable — a false
# negative would disable the abort). For a non-critical topic we fall back to the
# prior `applies_if` substring behaviour so adequacy elsewhere is unchanged.
#
# FAITHFULNESS NOTE: this only refines WHICH topics count toward the completeness
# DENOMINATOR (an input-hygiene / applicability-precision change). It NEVER
# touches strict_verify / NLI / the 4-role D8 audit / span-grounding, never drops
# or alters a verified claim, and on ambiguity it ERRS TOWARD keeping a critical
# safety topic active (held, not released). Removing a FALSE applicability is not
# a weakening — the GLP-1 drug checklist genuinely does not apply to a
# gut-microbiota question.
_DRUG_DETECTOR_ENABLED_ENV = "PG_COMPLETENESS_DRUG_DETECTOR"


def _drug_detector_enabled() -> bool:
    """Return True iff the robust drug/intervention applicability gate is on.

    Default ON (LAW VI: env-driven kill-switch, named constant, sane default).
    Set ``PG_COMPLETENESS_DRUG_DETECTOR`` to a falsy token (0/false/no/off) to
    fall back to the legacy substring-only `applies_if` behaviour for ALL topics
    — provided as an operator escape hatch, not a default. When OFF, a topic's
    ``requires_drug_intervention`` flag is ignored and applicability is the prior
    `applies_if` substring match (so the OFF path is byte-identical to pre-BUG-7).
    """
    raw = os.getenv(_DRUG_DETECTOR_ENABLED_ENV)
    if raw is None:
        return True
    return raw.strip().lower() in _TRUE_TOKENS


def _intervention_detected_or_ambiguous(research_question: str) -> tuple[bool, bool]:
    """Detect a drug/intervention in the QUESTION via the scope-gate recognizer.

    Returns ``(detected, ambiguous)``:

    * ``detected`` — True iff ``scope_gate._intervention_present`` recognised a
      drug/intervention token in ``research_question``. A clean ``None`` from the
      recognizer is a CONFIDENT negative (``detected=False, ambiguous=False``),
      NOT ambiguity — the recognizer ran and found no intervention.
    * ``ambiguous`` — True iff the recognizer could not be consulted at all
      (import failure / missing PyYAML / missing config / build error). In that
      case ``detected`` is False but the caller MUST treat a critical topic as
      fail-closed (applies) per BUG-7.

    This reuses the SAME recognizer the scope gate uses so completeness
    applicability and scope recognition cannot drift apart.
    """
    try:
        from src.polaris_graph.nodes.scope_gate import _intervention_present
        token = _intervention_present(research_question or "")
        return (token is not None), False
    except Exception as exc:  # config/import unavailable -> genuine ambiguity
        logger.warning(
            "[completeness] intervention recognizer unavailable (%s); "
            "fail-closed for critical topics per BUG-7 (#1262)",
            exc,
        )
        return False, True


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
    # BUG-7 (I-arch-006, #1262): drug/intervention-pharmacology topics
    # (contraindications, GLP-1 class risks, drug interactions, regulatory
    # approval, adverse events, …) only make sense when the QUESTION is actually
    # about a drug/intervention. When True, applicability is gated by a robust
    # config-driven drug/intervention detector (see `_topic_applies`) instead of
    # the previous "any clinical question" / raw-substring path that wrongly
    # marked these topics applicable for NON-drug clinical questions
    # (gut-microbiota, Parkinson's, metal-ions) just because they routed
    # domain="clinical". Default False -> every un-marked topic is byte-identical.
    requires_drug_intervention: bool = False


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
            # BUG-7 (I-arch-006, #1262): optional `requires_drug_intervention: true`
            # gates the topic on a robust drug/intervention detector (not the
            # routing label / a raw substring). Absent/false -> byte-identical.
            requires_drug_intervention=bool(
                t.get("requires_drug_intervention", False)
            ),
        ))
    return topics


# ── BUG-20 (I-arch-011): domain-adaptive checklist routing ────────────────────
# THE BUG: a `clinical` question routes UNCONDITIONALLY to clinical.yaml — the
# GLP-1 / drug-efficacy template. Applied to a Parkinson's / deep-brain-stimulation
# (DBS) question, 6 of its 7 topics are `requires_drug_intervention` and become
# non-applicable (correctly, post-BUG-7), leaving a SINGLE applicable topic
# (population_subgroups) that incidentally matches -> "1 of 1 covered" reads as
# "100% complete". The topics a reviewer of a DBS question actually expects —
# device efficacy (UPDRS-III), patient selection, hardware complications,
# stimulation/programming adverse effects, warning signs — are NEVER MEASURED.
# That is a false completeness PASS via the wrong-domain checklist.
#
# THE FIX: route the `clinical` question to a SUB-DOMAIN checklist whose
# `routing_terms` match the QUESTION (e.g. clinical_neuro_device.yaml for a
# Parkinson's/DBS question), so the applicable topics match what is being asked.
# Routing is config-driven (LAW VI): each candidate sub-domain checklist declares
# its own `routing_terms`; no question with zero matches changes domain, so every
# current question stays byte-identical. Matching is against the QUESTION only —
# never incidental evidence text — and the most-specific (most matched terms)
# candidate wins.
#
# FAITHFULNESS NOTE: this only refines WHICH checklist supplies the completeness
# DENOMINATOR. It never touches strict_verify / NLI / the 4-role D8 audit /
# span-grounding, never drops or alters a verified claim, and adds no cap/floor.
# Choosing the RIGHT checklist makes a false 100% honest — a faithfulness
# improvement, not a relaxation.

# `clinical`-rooted sub-domain checklists eligible for question routing. Each must
# declare `routing_terms` in its YAML. Listed by parent domain so a future parent
# domain can add routed sub-checklists without touching unrelated domains.
_ROUTED_SUBDOMAINS: dict[str, tuple[str, ...]] = {
    "clinical": ("clinical_neuro_device",),
}


def _load_routing_terms(domain: str) -> list[str]:
    """Return the lower-cased ``routing_terms`` declared in {domain}.yaml.

    Empty when the file is missing / has no routing_terms / yaml unavailable —
    so a checklist with no routing_terms is never selected by the router.
    """
    if yaml is None:
        return []
    path = _CHECKLIST_DIR / f"{domain}.yaml"
    if not path.exists():
        return []
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception as exc:  # pragma: no cover - defensive
        logger.warning("[completeness] routing_terms parse failed for %r: %s", path, exc)
        return []
    raw = data.get("routing_terms") or []
    return [str(t).lower().strip() for t in raw if str(t).strip()]


def _route_checklist_domain(domain: str, research_question: str) -> str:
    """Resolve the checklist domain to use for ``research_question`` (BUG-20).

    Returns ``domain`` unchanged unless a registered sub-domain checklist's
    ``routing_terms`` match the QUESTION. When two sub-domains match, the one with
    the MOST matched terms wins (most-specific). A clean no-match leaves ``domain``
    untouched -> byte-identical routing for every current question.
    """
    candidates = _ROUTED_SUBDOMAINS.get(domain)
    if not candidates:
        return domain
    q_lower = (research_question or "").lower()
    if not q_lower:
        return domain
    best_domain = domain
    best_score = 0
    for sub in candidates:
        terms = _load_routing_terms(sub)
        score = sum(1 for term in terms if term and term in q_lower)
        if score > best_score:
            best_score = score
            best_domain = sub
    if best_domain != domain:
        logger.info(
            "[completeness] BUG-20 routed domain=%r -> sub-domain=%r "
            "(matched %d routing term(s) in the question)",
            domain, best_domain, best_score,
        )
    return best_domain


def _legacy_applies_if(
    topic: ChecklistTopic,
    research_question: str,
    evidence_blob: str,
) -> bool:
    """Legacy substring `applies_if` match (question OR evidence pool).

    A topic with no `applies_if` always matches. A topic with `applies_if`
    terms matches iff any term is found in the research_question OR the
    evidence pool (since "GLP-1" might be implied by the drug name). This is
    the pre-BUG-7 behaviour, retained verbatim for non-drug topics and for the
    OFF kill-switch path.
    """
    if not topic.applies_if:
        return True
    q_lower = (research_question or "").lower()
    e_lower = (evidence_blob or "").lower()
    for term in topic.applies_if:
        if term in q_lower or term in e_lower:
            return True
    return False


def _topic_applies(
    topic: ChecklistTopic,
    research_question: str,
    evidence_blob: str,
) -> tuple[bool, str]:
    """Return ``(applies, disclosure_note)`` for a checklist topic.

    BUG-7 (I-arch-006, #1262) — drive a drug/intervention-pharmacology topic's
    applicability from a ROBUST detector, not the routing label or a raw
    substring.

    Non-drug topics (``requires_drug_intervention`` unset) keep the EXACT
    pre-BUG-7 `applies_if` substring semantics (question OR evidence pool), so
    their applicability is byte-identical.

    A topic flagged ``requires_drug_intervention: true`` applies iff the QUESTION
    is actually about a drug/intervention. "About a drug/intervention" is decided
    by EITHER:
      * the scope-gate recognizer (`_intervention_present`) finding a specific
        drug name / INN-stem in the question, OR
      * one of the topic's own `applies_if` CLASS anchors (e.g. "glp-1",
        "incretin") appearing in the QUESTION — these are intervention-class
        signals, not incidental evidence text.
    The detector deliberately consults the QUESTION only: a drug word that merely
    appears in retrieved EVIDENCE for a non-drug question must not flip a
    pharmacology topic on (that was the false-positive path).

    Once the question is confirmed to be about a drug/intervention, the topic's
    NORMAL `applies_if` filter still applies (so the GLP-1-class topic stays gated
    to GLP-1 questions and does not fire for metformin). For a topic with no
    `applies_if` (the CRITICAL `contraindications` topic), drug-presence is the
    sole gate.

    FAIL-CLOSED / DISCLOSE ON AMBIGUITY: if the recognizer cannot be consulted
    (import/config error), a CRITICAL ``requires_drug_intervention`` topic defaults
    to applies=True with a disclosure note — never silently mark a critical safety
    topic non-applicable. A non-critical topic falls back to the legacy substring
    match (adequacy elsewhere unchanged).

    Faithfulness: applicability only refines the completeness DENOMINATOR; it
    never touches strict_verify / NLI / 4-role / span-grounding, never drops a
    verified claim, and errs toward keeping a critical safety topic active.
    """
    legacy = _legacy_applies_if(topic, research_question, evidence_blob)

    # Non-drug topic, or kill-switch OFF -> exact pre-BUG-7 behaviour.
    if not topic.requires_drug_intervention or not _drug_detector_enabled():
        return legacy, ""

    q_lower = (research_question or "").lower()
    class_anchor_in_question = any(
        term in q_lower for term in topic.applies_if
    )
    detected, ambiguous = _intervention_detected_or_ambiguous(research_question)

    if ambiguous:
        # Recognizer unavailable: we cannot confidently conclude "no drug".
        if topic.critical:
            # Fail-closed: keep the critical safety topic active + disclose.
            return True, (
                f"applicability of critical topic {topic.id!r} could not be "
                f"determined (intervention recognizer unavailable); kept "
                f"applicable fail-closed per BUG-7 (#1262)"
            )
        # Non-critical: fall back to the legacy substring match (no change to
        # adequacy on ambiguity).
        return legacy, ""

    drug_or_intervention_present = detected or class_anchor_in_question
    if not drug_or_intervention_present:
        # Confident negative from the recognizer (+ no class anchor).
        if topic.critical:
            # Codex P1 (#1262): the recognizer (the SAME one the scope gate uses)
            # has incomplete brand/trade-name coverage, so a "confident no-drug" can
            # be a MISS on a real drug question — silently dropping a CRITICAL
            # contraindications topic would disable `abort_critical_topic_uncovered`
            # (a clinical-safety failure). A keyword "drug signal" heuristic to
            # auto-fail-closed proved a false-positive MINEFIELD (negation:
            # "non-pharmacological", "medication-free"; polysemy: "capsule endoscopy",
            # "monoclonal gammopathy"), and over-firing it would SPURIOUSLY HOLD a
            # non-drug report. Per Codex's explicit "fail-closed OR DISCLOSE" guidance
            # AND the operator's disclose-don't-hold directive, we take the DISCLOSE
            # path: keep applies=False (a non-drug report is NEVER spuriously held)
            # but ALWAYS emit a disclosure note, so the decision is auditable and the
            # skipped safety check is SURFACED FOR REVIEW rather than vanishing
            # silently — if this is in fact a drug question whose brand the recognizer
            # missed, the gap is disclosed in the report, not hidden.
            return False, (
                f"critical topic {topic.id!r}: marked non-applicable — the drug/"
                f"intervention recognizer found no known intervention in the question. "
                f"DISCLOSED (not silent): if this is a drug question with an "
                f"unrecognized brand/trade name, verify contraindications coverage "
                f"manually (Codex P1, #1262)."
            )
        # Non-critical confident negative: a drug-pharmacology topic does not apply
        # (the BUG-7 fix); a clean "no drug" is not ambiguity, no disclosure noise.
        return False, ""

    # The question IS about a drug/intervention. Apply the topic's normal
    # `applies_if` filter so class-specific topics stay gated to their class.
    return legacy, ""


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
        research_question: the user's query (drives the `applies_if` filter and,
            for `requires_drug_intervention` topics, the BUG-7 robust
            drug/intervention applicability gate — see `_topic_applies`).
        evidence_rows: evidence dicts with 'direct_quote' / 'statement'.
        min_hits_to_cover: min # of evidence rows that must match at
            least one keyword for a topic to be "covered" (default 1).
        drug_or_topic_hint: optional {drug} substitution for expand_queries
            (otherwise uses first significant noun from the question).

    Returns CompletenessReport with per-topic coverage + expand_queries
    for uncovered topics.
    """
    # BUG-20 (I-arch-011): route to a question-matched sub-domain checklist
    # (e.g. a Parkinson's/DBS question -> clinical_neuro_device) instead of the
    # fixed drug-efficacy clinical template. No-match -> domain unchanged.
    resolved_domain = _route_checklist_domain(domain, research_question)
    topics = load_checklist(resolved_domain)
    if not topics:
        return CompletenessReport(domain=resolved_domain, notes=["no_checklist_loaded"])

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
    # BUG-7 (I-arch-006, #1262): disclosure notes for any critical drug topic whose
    # applicability was decided by the recognizer — (a) fail-closed (kept applicable)
    # when the recognizer was UNAVAILABLE / ambiguous, or (b) pure-disclose (kept
    # NON-applicable but surfaced for review) on a recognizer confident-negative.
    applicability_disclosures: list[str] = []

    for topic in topics:
        applies, disclosure = _topic_applies(
            topic, research_question, evidence_blob
        )
        if disclosure:
            applicability_disclosures.append(disclosure)
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
    # BUG-7 (I-arch-006, #1262): surface any critical-topic applicability disclosure
    # — a fail-closed (recognizer-unavailable) note OR a pure-disclose (recognizer
    # confident-negative) note — so the decision is DISCLOSED, never silent.
    notes.extend(applicability_disclosures)

    return CompletenessReport(
        domain=resolved_domain,
        topics=coverages,
        total_applicable=applicable,
        total_covered=covered_n,
        total_uncovered=uncovered_n,
        expand_queries=all_expand_queries,
        notes=notes,
    )
