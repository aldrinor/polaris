"""
Semantic topic-relevance gate — I-scope-001 (#1244).

WHY THIS EXISTS (grounded diagnosis, do not re-derive):
A consolidated drb_72 breadth run cited 76 distinct sources with 0
fabrication, but ~9 were contamination — including 4 OFF-TOPIC-but-CREDIBLE
journals (spinal-cord stimulation, blockchain-sustainability, etc.). The
tier system rates CREDIBILITY, not RELEVANCE, so a credible-but-irrelevant
journal passes the tier gate. The lexical/embedding relevance floor ALSO
fails: en.wikipedia.org scored 0.583 relevance (above the clean median
0.500) because contaminants share generic content words with on-topic
sources. So neither tier nor embedding similarity can separate
off-topic-credible from on-topic — a TOPIC gate (semantic ON/OFF judgement
on the research-question domain) is required.

This module is the pure, LLM-based topic gate. It is DEFAULT-OFF: the
orchestrator (run_honest_sweep_r3.py) only calls it when PG_SCOPE_TOPIC_GATE
is truthy, and passes the production LLM callable + batch size. Keeping all
batching / parsing / exemption logic here (pure) means the gate is fully
unit-testable with a stub `llm_callable`, with NO OpenRouter key required.

FAITHFULNESS LOCK: this gate is SELECTION-SIDE ONLY. It can only SUBTRACT a
candidate source from the pool handed to the generator; it NEVER edits a
sentence, span, or citation. strict_verify / the NLI entailment judge / the
4-role D8 audit / provenance are UNTOUCHED — every surviving sentence still
passes the identical faithfulness stack. Subtraction cannot fabricate.

FAIL-OPEN CONTRACT (LAW II — never drop on uncertainty):
The gate drops a source ONLY on an explicit, confident OFF verdict. It KEEPS
the source (fail-open) on:
  - any LLM exception,
  - a returned verdict count that does not match the requested count,
  - any unparseable / unrecognised verdict line,
  - an empty / missing title+snippet (nothing to judge on).
A marquee / required-entity anchor is NEVER dropped, regardless of verdict.
"""

from __future__ import annotations

import logging
import os
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import urlparse

_LOGGER = logging.getLogger(__name__)

# Default batch size for PG_SCOPE_TOPIC_BATCH — how many sources are
# classified per LLM call. Bounds cost: one call covers up to this many
# sources. A small denominator keeps the prompt short + the parse simple.
_DEFAULT_TOPIC_BATCH = 25

# Cap on the title+snippet length fed per source so a batch prompt stays
# bounded even with long live-retriever statements.
# P1-4 (S2/S3 re-pass iter-5, Fable): the 320-char default fed the judge only the FIRST 320
# chars of a source — which for a fetched page is often leading nav / masthead / title chrome, NOT
# the topical content, so a context-obvious off-topic source (education-finance, climate-finance,
# social-work, lit-review-how-to, CBA-methodology, governance-of-law) read as ambiguous and the
# fail-open kept it. Raise the default to 1200 chars so the judge SEES the substantive body, and
# make it LAW VI env-tunable. Still bounded (batch prompt stays reasonable at batch 25). FAIL-OPEN
# is unchanged: more context only sharpens a CONFIDENT off-topic verdict; any doubt still keeps.
_MAX_SNIPPET_CHARS_DEFAULT = 1200


def _max_snippet_chars() -> int:
    """``PG_SCOPE_TOPIC_SNIPPET_CHARS`` (LAW VI, default 1200). A malformed / non-positive value
    falls back to the default (fail-safe: never a zero-length snippet)."""
    raw = os.environ.get("PG_SCOPE_TOPIC_SNIPPET_CHARS", "").strip()
    if not raw:
        return _MAX_SNIPPET_CHARS_DEFAULT
    try:
        value = int(raw)
    except ValueError:
        return _MAX_SNIPPET_CHARS_DEFAULT
    return value if value > 0 else _MAX_SNIPPET_CHARS_DEFAULT


def topic_gate_enabled() -> bool:
    """Kill-switch ``PG_SCOPE_TOPIC_GATE`` (default ON — I-deepfix-001 DEFER-1).

    Default flipped ``"0"->"1"`` (2026-06-30): the gate is the SEMANTIC
    discriminator the cite-surface off-topic suppression keys on (a lexical floor
    cannot separate on-topic from off-topic — disproven on drb_72). It is §-1.3
    keystone-compatible: the DEFAULT verdict is DEMOTE-not-DROP (every source stays
    in the pool, the confident-OFF ones carry the ``topic_offtopic_demoted``
    sidecar), so turning it ON adds a disclosed WEIGHT, never a hard filter. Set
    ``PG_SCOPE_TOPIC_GATE=0`` to restore the byte-identical legacy (gate never
    called) behaviour."""
    raw = os.environ.get("PG_SCOPE_TOPIC_GATE", "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


def resume_run_topic_judge_enabled() -> bool:
    """Kill-switch ``PG_RESUME_RUN_TOPIC_JUDGE`` (default OFF — I-deepfix-001 wave-2).

    A RESUME normally SKIPS this gate (the orchestrator guards the call with
    ``not _resume_active`` because the corpus_snapshot is reloaded post-selection). That
    leaves every reloaded row UNJUDGED, so an off-topic source can leak into the finding
    surface. When this flag is set, the orchestrator ALSO runs the EXISTING
    :func:`classify_topic_relevance` on a resume, so the reloaded rows get a topic verdict
    stamped. Default OFF => the ``not _resume_active`` short-circuit holds => byte-identical
    (the judge is not run on a resume, exactly as before)."""
    raw = os.environ.get("PG_RESUME_RUN_TOPIC_JUDGE", "").strip().lower()
    return raw in ("1", "true", "on", "yes", "enabled")


def mark_topic_judge_ran() -> None:
    """Set the run-scoped signal ``PG_TOPIC_JUDGE_RAN=1`` the moment the topic judge has
    executed this run (fresh or the resume path opened by
    :func:`resume_run_topic_judge_enabled`). The downstream unjudged-topic quarantine
    (``weighted_enrichment.topic_judge_ran`` / ``partition_unjudged_topic_rows``) reads this
    to prove the judge ran — so a row that STILL lacks a verdict is a genuine leak
    (quarantinable), NEVER a legitimately-skipped-judge false positive. Process/run-scoped
    (each sweep is its own process); the quarantine ALSO derives the same fact from the data,
    so this write is the explicit belt to that suspenders."""
    os.environ["PG_TOPIC_JUDGE_RAN"] = "1"


def topic_gate_hard_drop_enabled() -> bool:
    """LEGACY escape hatch ``PG_SCOPE_TOPIC_GATE_HARD_DROP`` (default OFF).

    §-1.3 (WEIGHT, DON'T FILTER — the operator names the "scope hard-filter" as a
    BANNED anti-pattern; the ONLY hard gate is the faithfulness engine): a
    confident-OFF source is, by DEFAULT, KEPT in the pool and DEMOTED (disclosed
    as off-topic), NEVER hard-dropped. Topicality is a WEIGHT, not a DROP — the
    source still flows to composition where the UNCHANGED strict_verify / NLI /
    4-role faithfulness engine is the only gate. Set this flag truthy ONLY to
    restore the pre-I-deepfix-001 hard-drop (audit / reversal); the default
    keep-all + demote is the §-1.3-correct behavior."""
    raw = os.environ.get("PG_SCOPE_TOPIC_GATE_HARD_DROP", "0").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


def topic_gate_subject_aspect_split_enabled() -> bool:
    """Flag ``PG_TOPIC_GATE_SUBJECT_ASPECT_SPLIT`` (default ON — I-deepfix-003 #1374 Fix 3).

    Splits the single confident-OFF verdict into two kinds:
      - ``OFF_ASPECT`` — the SAME subject entity but a DIFFERENT aspect / use-case /
        population than the question asks about (a topic-adjacent hub, e.g. an
        education-AI paper for a labor-market question). DEMOTE-and-keep, NEVER deletable.
      - ``OFF_SUBJECT`` — a CLEARLY DIFFERENT subject entity (different field / domain —
        scholar-mill / unrelated-domain junk). This is the ONLY deletable OFF: it alone
        carries the ``topic_off_subject=True`` sidecar the downstream junk-deletion gate
        keys on.
    A legacy plain ``OFF`` parses as OFF_ASPECT (conservative — never delete on the old
    verdict form). Set ``PG_TOPIC_GATE_SUBJECT_ASPECT_SPLIT=0`` to restore the
    byte-identical legacy ON/OFF prompt + parser (no ``topic_off_subject`` stamp)."""
    raw = os.environ.get("PG_TOPIC_GATE_SUBJECT_ASPECT_SPLIT", "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


def junk_chrome_before_offtopic_enabled() -> bool:
    """Flag ``PG_JUNK_CHROME_BEFORE_OFFTOPIC`` (default ON — I-deepfix-003 #1374 Fix 4).

    A chrome non-source (bot/captcha/cookie/404/login/empty — a FAILED FETCH, not a source)
    has nothing real to judge for topicality. When ON, such a row is NOT sent to the topic
    judge at all: it is KEPT (flows to the downstream content-integrity stamp + chrome-delete
    leg) and is NEVER stamped ``topic_off_subject`` / ``topic_offtopic_demoted``, so a garbled
    body + a chrome title can never be mislabeled ``confirmed_offtopic`` (Cause 3). OFF =>
    byte-identical legacy (every non-exempt row with judgeable text is judged)."""
    raw = os.environ.get("PG_JUNK_CHROME_BEFORE_OFFTOPIC", "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


# Content fields scanned (widest-first) for the chrome detector — mirrors the
# run_honest_sweep_r3 content-integrity stamp pass so the two screens judge the SAME body.
_CHROME_BODY_FIELDS = (
    "fetched_body", "full_text", "content", "extracted_text", "raw_content",
    "raw_text", "page_text", "direct_quote", "statement", "source_text", "body", "text",
)


def _row_is_chrome_nonsource(row: dict[str, Any]) -> bool:
    """True iff the CONTENT-INTEGRITY detector confirms this row is a chrome non-source
    (bot/captcha/cookie/404/login/empty). Reads a pre-existing ``content_integrity_junk``
    stamp first (cheap), else runs the pure leaf detector on the WIDEST body + url + title
    (the long-body Zyte-recovery guard inside the detector protects a real source whose title
    is a stale bot page). FAIL-OPEN: any import / error / non-dict => False (row is judged
    normally — a detector bug must never silently skip a real source)."""
    try:
        if not isinstance(row, dict):
            return False
        v = row.get("content_integrity_junk")
        if bool(v) and str(v).strip().lower() not in ("0", "false", "no", "off", ""):
            return True
        from src.tools.access_bypass import (  # noqa: PLC0415
            detect_content_integrity_junk as _detect_ci_junk,
        )
        body = max(
            (str(row.get(_bk) or "") for _bk in _CHROME_BODY_FIELDS),
            key=len, default="",
        )
        url = str(row.get("source_url") or row.get("url") or "")
        title = str(row.get("title") or row.get("source_title") or row.get("statement") or "")
        is_junk, _cls = _detect_ci_junk(body, url, title)
        return bool(is_junk)
    except Exception:  # noqa: BLE001 — a detector defect must never skip a real source
        return False


def topic_batch_size() -> int:
    """``PG_SCOPE_TOPIC_BATCH`` (default 25), the max sources per LLM call.
    A non-positive / unparseable value falls back to the default (FAIL-SAFE:
    a garbage batch size must never produce a zero-size loop)."""
    raw = os.environ.get("PG_SCOPE_TOPIC_BATCH", "").strip()
    if not raw:
        return _DEFAULT_TOPIC_BATCH
    try:
        value = int(raw)
    except ValueError:
        return _DEFAULT_TOPIC_BATCH
    return value if value > 0 else _DEFAULT_TOPIC_BATCH


@dataclass
class TopicGateResult:
    """Return value of :func:`classify_topic_relevance`."""

    kept_rows: list[dict[str, Any]]
    dropped_rows: list[dict[str, Any]]
    dropped_titles: list[str] = field(default_factory=list)
    n_in: int = 0
    n_kept: int = 0
    n_dropped_offtopic: int = 0
    n_exempt: int = 0
    notes: list[str] = field(default_factory=list)
    # I-deepfix-001 (§-1.3 WEIGHT-not-FILTER): confident-OFF sources that were
    # KEPT-and-DEMOTED instead of hard-dropped (the DEFAULT). They remain in
    # ``kept_rows`` (the source flows to composition) but are disclosed here as
    # off-topic-demoted. Empty when the legacy hard-drop flag is set.
    demoted_rows: list[dict[str, Any]] = field(default_factory=list)
    demoted_titles: list[str] = field(default_factory=list)
    n_demoted_offtopic: int = 0


def _row_title_text(row: dict[str, Any]) -> str:
    """Title-like text accessor mirroring evidence_selector._row_title_text.

    Live evidence rows populate ``statement`` with ``cand.title[:300]`` (not
    ``title``). Precedence: explicit ``title`` > ``statement`` >
    ``source_title`` > "". Returns a plain string (never None)."""
    for key in ("title", "statement", "source_title"):
        v = row.get(key)
        if isinstance(v, str) and v:
            return v
    return ""


def _row_snippet_text(row: dict[str, Any]) -> str:
    """Short snippet for the topic judgement. Uses ``snippet`` /
    ``direct_quote`` (whichever is present), bounded to _MAX_SNIPPET_CHARS."""
    for key in ("snippet", "direct_quote", "summary"):
        v = row.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()[:_max_snippet_chars()]
    return ""


def _row_is_marquee_anchor(row: dict[str, Any]) -> bool:
    """True iff the row is a marquee / required-entity anchor that must NOT be
    dropped. Mirrors evidence_selector._row_is_marquee_anchor (I-pipe-006
    #1231) — a truthy ``is_marquee`` / ``required_entity`` / ``anchor_seed`` /
    ``is_anchor`` / ``entity_anchor`` / ``marquee`` flag, OR a
    ``required_entity``/``anchor`` substring in ``seed_source`` /
    ``query_origin`` / ``seed_query_origin``."""
    if not isinstance(row, dict):
        return False
    for flag in ("is_marquee", "required_entity", "anchor_seed", "is_anchor",
                 "entity_anchor", "marquee"):
        if row.get(flag):
            return True
    seed_source = str(row.get("seed_source") or "").lower()
    if "required_entity" in seed_source or "anchor" in seed_source:
        return True
    for origin_key in ("query_origin", "seed_query_origin"):
        origin = str(row.get(origin_key) or "").lower()
        if "required_entity" in origin or "anchor" in origin:
            return True
    return False


# ─────────────────────────────────────────────────────────────────────────
# P0-1 (S2/S3 re-pass) — category-consistency fail-open + on-topic anchors
# ─────────────────────────────────────────────────────────────────────────
# ev_308 (BLS OES Paralegals), ev_310, ev_318 were whole-dropped OFF_SUBJECT while same-class
# sibling wage/occupational pages were KEPT — a §-1.3.1 violation ("credible on-topic NEVER
# deleted"). Two general, question-agnostic guards:
#   (b) CATEGORY-CONSISTENCY fail-open (deterministic, DEFAULT ON): a row about to be stamped the
#       deletable OFF_SUBJECT is DOWNGRADED to OFF_ASPECT (demote-KEEP) when a sibling in the SAME
#       category (registrable host + numeric-template path family) was verdicted ON / OFF_ASPECT —
#       inconsistency ⇒ uncertainty ⇒ KEEP.
#   (a) ON-TOPIC ANCHORS (prompt context, DEFAULT OFF pending eval): salient corpus-recurrent
#       entity phrases injected as ON-TOPIC context so an occupational-outlook/wage page for an
#       exposed entity reads ON. Default OFF so an un-vetted judge-prompt nudge never silently
#       lowers precision; (b) is the active deterministic fix.
def _topic_category_consistency_enabled() -> bool:
    """``PG_TOPIC_CATEGORY_CONSISTENCY`` kill switch (LAW VI, DEFAULT ON, P0-1b). OFF =>
    byte-identical legacy (no OFF_SUBJECT downgrade)."""
    return os.environ.get("PG_TOPIC_CATEGORY_CONSISTENCY", "1").strip().lower() not in (
        "0", "false", "no", "off", "",
    )


def _ontopic_anchors_enabled() -> bool:
    """``PG_TOPIC_ONTOPIC_ANCHORS`` kill switch (LAW VI, DEFAULT OFF, P0-1a). ON => inject
    corpus-salient entity phrases as ON-TOPIC context in the judge prompt. Default OFF: the
    deterministic category-consistency guard (b) is the shipped fix; the prompt nudge is opt-in
    (an un-vetted judge-prompt change must never silently degrade precision)."""
    return os.environ.get("PG_TOPIC_ONTOPIC_ANCHORS", "0").strip().lower() in (
        "1", "true", "on", "yes", "enabled",
    )


def _authoritative_reference_ontopic_enabled() -> bool:
    """``PG_TOPIC_AUTHORITATIVE_REFERENCE_ONTOPIC`` kill switch (LAW VI, DEFAULT ON — S2/S3
    re-pass Fable Fix 4). ON => the judge prompt states that an AUTHORITATIVE statistical /
    government / regulatory / registry REFERENCE page about an entity within the question's
    derived scope is ON-topic (a plain data table is still the evidence the question needs, so
    it must not be marked OFF for being a table rather than an argued narrative). This is a
    scope-aware, question-agnostic clarification derived from the RESEARCH QUESTION at run time
    (no hardcoded entity/occupation list); it can only make the judge KEEP more (reduces the
    over-deletion of e.g. official occupational-outlook / wage pages), never delete more. OFF =>
    byte-identical legacy prompt (the clarification line is not emitted)."""
    return os.environ.get(
        "PG_TOPIC_AUTHORITATIVE_REFERENCE_ONTOPIC", "1"
    ).strip().lower() not in ("0", "false", "no", "off", "")


def _category_signature(row: dict[str, Any]) -> str:
    """A category signature = registrable host + URL path with DIGIT-BEARING segments templated
    to ``#`` (P0-1b). This groups a NUMERIC-TEMPLATE page family (BLS OES ``/oes/current/
    oes232011.htm`` ~ ``oes436014.htm`` -> ``host/oes/current/#``) without collapsing distinct
    slug-articles (two different ``/wiki/<article>`` pages keep distinct signatures — no false
    grouping). Returns "" when the URL is missing OR has no numeric-template segment (the guard
    is then inert for that row — fail-safe, never over-groups). Pure/deterministic."""
    url = str(row.get("source_url") or row.get("url") or "").strip()
    if not url:
        return ""
    try:
        parsed = urlparse(url)
    except Exception:  # noqa: BLE001
        return ""
    host = (parsed.hostname or "").lower()
    if host.startswith("www."):
        host = host[4:]
    if not host:
        return ""
    segs = [s for s in (parsed.path or "").split("/") if s]
    templated: list[str] = []
    has_digit_seg = False
    for s in segs:
        if any(ch.isdigit() for ch in s):
            templated.append("#")
            has_digit_seg = True
        else:
            templated.append(s.lower())
    if not has_digit_seg:
        return ""  # no numeric-template family signal -> no grouping (guard inert for this row)
    return host + "/" + "/".join(templated)


# 2-4 capitalized words = a candidate entity phrase (BLS occupation names, org names, etc.).
_ONTOPIC_ANCHOR_PHRASE_RE = re.compile(
    r"\b([A-Z][A-Za-z0-9&.\-]+(?:\s+[A-Z][A-Za-z0-9&.\-]+){1,3})\b"
)


def _derive_ontopic_anchors(
    judged_meta: list[tuple[str, str]], *, min_occurrences: int = 3, cap: int = 12,
) -> list[str]:
    """Corpus-salient entity phrases: capitalized 2-4-word phrases recurring across >=
    ``min_occurrences`` judged titles, capped to ``cap`` (P0-1a). General/question-agnostic —
    derived at runtime from the corpus, nothing hardcoded. Empty when nothing recurs."""
    counter: Counter[str] = Counter()
    seen_per_title: list[set[str]] = []
    for title, _snippet in judged_meta:
        phrases: set[str] = set()
        for m in _ONTOPIC_ANCHOR_PHRASE_RE.finditer(title or ""):
            phrase = m.group(1).strip()
            if len(phrase) >= 6:
                phrases.add(phrase)
        seen_per_title.append(phrases)
    for phrases in seen_per_title:
        for p in phrases:
            counter[p] += 1
    return [p for p, c in counter.most_common() if c >= min_occurrences][:cap]


# ─────────────────────────────────────────────────────────────────────────
# P0-2 (S2/S3 re-pass iter-2) — QUESTION-DELIVERABLE ANCHORS (default ON)
# ─────────────────────────────────────────────────────────────────────────
# ROOT CAUSE (Fable, forensic on the fresh 04:15 disclosure): the topic judge
# whole-dropped credible ON-topic OCCUPATION sources (BLS occupational-outlook /
# wage pages for Lawyers, Financial Analysts, paralegals, data-entry, medical-
# transcription, ...) as OFF_SUBJECT. The drb_72 question REQUIRES an occupation
# case-study table (a mandated "Application Area/Occupation" column), so an
# authoritative page ABOUT a required occupation is exactly the evidence the
# deliverable needs — even when the page never names the core technology. The
# category-consistency guard could not save them: the judge stamped the WHOLE
# occupation category OFF, so no same-category sibling was KEPT for the guard to
# key on. The corpus-recurrent ``_derive_ontopic_anchors`` leg (default OFF) also
# cannot help — the anchors come from the CORPUS, and the corpus's occupation
# pages were the ones being dropped.
#
# THE FIX (general, question-agnostic): derive the DELIVERABLE AXES the QUESTION
# TEXT itself demands — its required table columns, quoted headers, enumerated
# occupations/industries, and the axis nouns (occupations / industries / sectors
# / professions / application areas / case studies) it asks the report to break
# findings down by — and inject them into the judge prompt as explicit ON-TOPIC
# scope: a source whose SUBJECT is one of the question-required occupations /
# industries / application areas is ON even if it does not mention the core
# technology. The anchors come from the QUESTION, never from the corpus or a
# hardcoded entity/occupation list, so it generalizes to ANY research question
# (a question that asks for no occupation/industry breakdown yields no axis
# anchors => the injection is inert => byte-identical). Fail-open preserved.
def _question_deliverable_anchors_enabled() -> bool:
    """``PG_TOPIC_QUESTION_DELIVERABLE_ANCHORS`` kill switch (LAW VI, DEFAULT ON, P0-2). ON =>
    the judge prompt is told that a source whose subject is one of the question-required
    deliverable axes (occupations / industries / application areas the QUESTION demands a
    breakdown by) is ON-topic even without the core technology. It can only make the judge
    KEEP more (never delete more); §-1.3.1 credible-on-topic-never-deleted. OFF => byte-identical
    legacy prompt (no deliverable-axis block)."""
    return os.environ.get(
        "PG_TOPIC_QUESTION_DELIVERABLE_ANCHORS", "1"
    ).strip().lower() not in ("0", "false", "no", "off", "")


# A quoted phrase in the question is almost always a REQUIRED entity / table-column header
# (ASCII, curly, or single quotes). Bounded 2..60 chars so a long quoted sentence is skipped.
_DELIVERABLE_QUOTED_RE = re.compile(
    "[“”\"]([^“”\"]{2,60})[“”\"]"
    "|[‘’']([^‘’']{2,60})[‘’']"
)
# An enumeration the question spells out ("such as X, Y and Z", "including A/B").
_DELIVERABLE_ENUM_RE = re.compile(
    r"(?:such as|including|like|e\.g\.,?|for example|namely|specifically)\s+([^.;:\n]{3,180})",
    re.IGNORECASE,
)
# The deliverable-axis nouns a question demands a breakdown BY. Presence of one of these means
# the report must cover per-occupation / per-industry / per-application cases, so an
# authoritative page ABOUT such an entity is on-topic even without the core technology.
_DELIVERABLE_AXIS_NOUN_RE = re.compile(
    r"\b(occupations?|industr(?:y|ies)|sectors?|professions?|job roles?|"
    r"application areas?|use cases?|case stud(?:y|ies)|disciplines?|specialt(?:y|ies))\b",
    re.IGNORECASE,
)


def _derive_question_deliverable_anchors(
    research_question: str, *, cap: int = 24,
) -> list[str]:
    """The DELIVERABLE AXES the QUESTION TEXT itself demands (P0-2): quoted table-column
    headers / required entities, spelled-out enumerations, and the axis nouns the report
    must break findings down by. General + question-agnostic — every anchor is lifted from
    the QUESTION, nothing is hardcoded or corpus-derived. Empty when the question asks for
    no such breakdown (the injection is then inert => byte-identical legacy)."""
    q = " ".join(str(research_question or "").split())
    if not q:
        return []
    anchors: list[str] = []
    seen: set[str] = set()

    def _add(phrase: str) -> None:
        p = " ".join(str(phrase or "").split()).strip(" .,;:—–-/|\"'")
        key = p.casefold()
        if p and 2 <= len(p) <= 60 and any(ch.isalnum() for ch in p) and key not in seen:
            seen.add(key)
            anchors.append(p)

    for m in _DELIVERABLE_QUOTED_RE.finditer(q):
        _add(m.group(1) or m.group(2) or "")
    for m in _DELIVERABLE_ENUM_RE.finditer(q):
        for part in re.split(r",|;|/|\band\b|\bor\b", m.group(1)):
            _add(part)
    for m in _DELIVERABLE_AXIS_NOUN_RE.finditer(q):
        _add(m.group(1))
    return anchors[:cap]


def _build_batch_prompt(
    research_question: str,
    batch: list[tuple[int, str, str]],
    *,
    subject_aspect_split: bool = False,
    ontopic_anchors: list[str] | None = None,
    deliverable_anchors: list[str] | None = None,
) -> str:
    """Build a single ON/OFF-topic classification prompt for a batch of
    sources. ``batch`` is a list of (local_index, title, snippet). The LLM is
    asked to return exactly one line per source: ``<index>: ON`` or
    ``<index>: OFF``. Confident-OFF-only is enforced at parse time.

    ``subject_aspect_split`` (I-deepfix-003 #1374 Fix 3): when True the OFF verdict
    is split into ``OFF_ASPECT`` (same subject, wrong aspect — kept/demoted) and
    ``OFF_SUBJECT`` (clearly different subject — the only deletable OFF). When False
    (the byte-identical legacy) the prompt asks only for ``ON`` / ``OFF``."""
    # I-deepfix-003 #1374 Fix 3: the STEP-2 rubric, the domain-neutral example, the
    # OUTPUT CONTRACT, and the trailer are the ONLY segments that differ between the
    # legacy two-verdict form and the three-verdict subject/aspect split. Everything
    # else (STEP 1, the date-blind rule, the fail-open) is byte-identical in both. The
    # ``else`` strings below reproduce the legacy prompt EXACTLY (byte-identical OFF).
    if subject_aspect_split:
        step2_line = (
            "STEP 2 — for EACH numbered source below, choose EXACTLY ONE verdict: "
            "ON if the source plausibly bears on BOTH the subject entity AND that "
            "specific aspect; OFF_ASPECT if the source is about the SAME subject "
            "entity but a DIFFERENT aspect / use-case / population than the question "
            "asks about (same subject, wrong question — a topic-adjacent hub that is "
            "KEPT and only demoted, never removed); OFF_SUBJECT if the source is "
            "about a CLEARLY DIFFERENT subject entity (different field, disease, "
            "domain — e.g. an unrelated-domain or scholar-mill paper). When you are "
            "unsure between OFF_ASPECT and OFF_SUBJECT, choose OFF_ASPECT (the "
            "safer, keep-and-demote verdict)."
        )
        example_line = (
            "Example (domain-neutral): if the question is about entity X and aspect "
            "A, then a source about entity X but aspect B is OFF_ASPECT; a source "
            "about a clearly different entity Y is OFF_SUBJECT; a source about entity "
            "X and aspect A is ON."
        )
        output_contract_line = (
            "OUTPUT CONTRACT (strict — the parser accepts nothing else): OUTPUT ONLY "
            "THE VERDICT LINES, exactly one per source, each line EXACTLY in the form "
            "`<index>: ON`, `<index>: OFF_ASPECT`, or `<index>: OFF_SUBJECT`. Do NOT "
            "write the entity or aspect names, any reasoning, any explanation, or any "
            "other words — not on a verdict line and not anywhere else in the output."
        )
        trailer_line = (
            "VERDICTS (one `<index>: ON|OFF_ASPECT|OFF_SUBJECT` line per source):"
        )
    else:
        step2_line = (
            "STEP 2 — for EACH numbered source below, mark it ON only if it plausibly "
            "bears on BOTH the subject entity AND that specific aspect. A source about "
            "the SAME entity but a DIFFERENT aspect / use-case / population than the "
            "question asks about is OFF-TOPIC — same subject, wrong question. A source "
            "about a clearly different subject entity (different field, disease, "
            "population) is also OFF-TOPIC."
        )
        example_line = (
            "Example (domain-neutral): if the question is about entity X and aspect A, "
            "then a source about entity X but aspect B is OFF; a source about entity X "
            "and aspect A is ON."
        )
        output_contract_line = (
            "OUTPUT CONTRACT (strict — the parser accepts nothing else): OUTPUT ONLY "
            "THE VERDICT LINES, exactly one per source, each line EXACTLY in the form "
            "`<index>: ON` or `<index>: OFF`. Do NOT write the entity or aspect names, "
            "any reasoning, any explanation, or any other words — not on a verdict "
            "line and not anywhere else in the output."
        )
        trailer_line = "VERDICTS (one `<index>: ON|OFF` line per source):"
    lines = [
        "You are a strict topic-relevance classifier for a research report.",
        "",
        f"RESEARCH QUESTION:\n{research_question.strip()}",
        "",
        *(
            [
                "ON-TOPIC CONTEXT (entities recurring across this research corpus — a source "
                "whose subject is one of these is ON-topic for the question's subject; this "
                "does NOT waive the aspect test): " + "; ".join(ontopic_anchors),
                "",
            ]
            if ontopic_anchors else []
        ),
        # I-deepfix-001 FF4-ASPECT (v2, forensic-corrected): FACET-SCOPED rubric
        # (was entity-only) + a STRICT verdict-only output contract. An
        # entity-only "different subject?" prompt is structurally blind to a
        # same-entity / wrong-ASPECT source (e.g. a GenAI-in-education paper
        # grounding a GenAI-labor-market question): the shared entity satisfies
        # "not a different field" and the fail-open keeps it ON. The two-step
        # rubric below makes the model name the question's SUBJECT ENTITY *and*
        # its SPECIFIC ASPECT *silently* (internal reasoning only), then requires
        # a source to bear on BOTH. It is domain-agnostic (LAW VI — the aspect is
        # derived at runtime from the RESEARCH QUESTION; nothing domain-specific
        # is hardcoded) and preserves the explicit fail-open.
        #
        # FORENSIC ADJUSTMENT #2 (off-topic fix_change_needed): the entity+aspect
        # naming MUST stay INTERNAL and the output MUST be strictly one
        # `<index>: ON|OFF` line per source and nothing else. Inline reasoning on
        # a verdict line ("1: this is about L2 writing, OFF") is not recognised by
        # _parse_batch_verdicts (below, unchanged) -> count mismatch -> the WHOLE
        # batch fails OPEN, silently letting the off-aspect source survive. So the
        # output contract is hardened here rather than the parser being relaxed.
        "STEP 1 (do this SILENTLY — this reasoning must NOT appear anywhere in "
        "your output): read the RESEARCH QUESTION and name to yourself its two "
        "parts — the SUBJECT ENTITY it is about, and the SPECIFIC ASPECT it asks "
        "about that entity (the outcome, relation, sub-domain, use-case, or "
        "population the question is actually asking about).",
        "",
        step2_line,
        "",
        example_line,
        "",
        # I-deepfix-001 (drb_72 forensic): the seminal on-topic papers were wrongly marked OFF
        # because the question text embeds a DATE window ("before June 2023") and the judge read a
        # post-cutoff date/marker in a snippet as a "different aspect". TOPICALITY IS DATE-BLIND.
        "TOPICALITY IS DATE-BLIND: a publication date — or ANY date in the research question — is "
        "NOT an aspect. NEVER mark a source OFF because of its publication date or a date range in "
        "the question; recency is a SEPARATE axis handled elsewhere. Judge ONLY subject-entity + "
        "aspect. An exposure / projection / potential-impact / early-evidence study of the "
        "question's aspect is ON (it bears on that aspect), not OFF.",
        "",
        *(
            [
                "AUTHORITATIVE REFERENCE PAGES ARE ON-TOPIC: an official statistical, "
                "government, regulatory, or registry reference page (for example a national "
                "labor-statistics / occupational-outlook / wage page, a standards body, or an "
                "official product/entity registry) ABOUT an entity, occupation, product, or "
                "population that falls WITHIN the question's subject scope is ON — it is exactly "
                "the authoritative evidence the question needs, even when the page itself is a "
                "plain data table or reference entry rather than an argued narrative. Judge the "
                "ENTITY + ASPECT, never the page's prose style or format.",
                "",
            ]
            if _authoritative_reference_ontopic_enabled() else []
        ),
        # P0-2 (S2/S3 re-pass iter-2): QUESTION-DELIVERABLE AXES. When the RESEARCH QUESTION
        # itself demands a breakdown by occupation / industry / application area (its required
        # table columns / enumerated axes), a source whose SUBJECT is one of those required
        # axes is ON — it supplies a required case/column of the deliverable — even if it never
        # names the core technology. Anchors are lifted from the QUESTION (never the corpus),
        # so this is inert for a question that asks for no such breakdown.
        *(
            [
                "QUESTION-REQUIRED DELIVERABLE AXES: the report this question asks for must "
                "break its findings down by these axes / columns that the RESEARCH QUESTION "
                "ITSELF names: " + "; ".join(deliverable_anchors) + ". A source whose SUBJECT "
                "is one of the question-required occupations, industries, sectors, professions, "
                "or application areas is ON-topic even if it does NOT mention the core "
                "technology / subject of the question — it supplies a required case or column "
                "of the deliverable (for example, an official occupational-outlook, wage, or "
                "industry-statistics page for an occupation or industry the report must cover "
                "is ON). Judge the ENTITY against BOTH the core question AND these required "
                "deliverable axes; when a source clearly fills a required axis, prefer ON.",
                "",
            ]
            if deliverable_anchors else []
        ),
        "FAIL-OPEN: if you genuinely cannot tell whether the source addresses the "
        "question's specific aspect, mark it ON. When in doubt, answer ON.",
        "",
        output_contract_line,
        "",
        "SOURCES:",
    ]
    for local_idx, title, snippet in batch:
        text = title.strip()
        if snippet:
            text = f"{text} — {snippet}" if text else snippet
        if not text:
            text = "(no title or snippet)"
        lines.append(f"{local_idx}: {text}")
    lines.append("")
    lines.append(trailer_line)
    return "\n".join(lines)


def _parse_batch_verdicts(
    raw: str,
    expected_indices: list[int],
) -> dict[int, bool] | None:
    """Parse the LLM batch response into ``{local_index: is_offtopic}``.

    Returns None (FAIL-OPEN signal — keep the whole batch) when the parse is
    not exactly one recognised verdict per requested index. A recognised
    verdict line is ``<index>: ON`` or ``<index>: OFF`` (case-insensitive,
    tolerant of surrounding punctuation). Anything else => fail-open."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    verdicts: dict[int, bool] = {}
    wanted = set(expected_indices)
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        idx_part, _, verdict_part = stripped.partition(":")
        idx_token = idx_part.strip().lstrip("-").strip()
        if not idx_token.isdigit():
            continue
        idx = int(idx_token)
        if idx not in wanted:
            continue
        verdict_token = verdict_part.strip().lower()
        # Confident ON / confident OFF only. Anything ambiguous is ignored
        # (so the count check below will trip fail-open).
        if verdict_token.startswith("on"):
            verdicts[idx] = False
        elif verdict_token.startswith("off"):
            verdicts[idx] = True
        # else: leave unset -> count mismatch -> fail-open
    if set(verdicts.keys()) != wanted:
        # Missing / extra / unparseable verdicts: keep the whole batch.
        return None
    return verdicts


def _parse_batch_verdicts_split(
    raw: str,
    expected_indices: list[int],
) -> dict[int, str] | None:
    """Parse the three-verdict (subject/aspect split) LLM response into
    ``{local_index: "ON" | "OFF_ASPECT" | "OFF_SUBJECT"}``.

    Returns None (FAIL-OPEN — keep the whole batch) on the SAME conditions as the
    legacy :func:`_parse_batch_verdicts`: empty/blank input, or any result that is
    not exactly one recognised verdict per requested index. Recognised verdict
    tokens (case-insensitive, separator-tolerant so ``off subject`` / ``off-subject``
    / ``off_subject`` all match): ``on`` -> ON, ``off_subject`` -> OFF_SUBJECT,
    ``off_aspect`` -> OFF_ASPECT, and a legacy bare ``off`` -> OFF_ASPECT
    (conservative — the old verdict form is NEVER treated as deletable). Anything
    unrecognised is ignored so the count check below trips fail-open."""
    if not isinstance(raw, str) or not raw.strip():
        return None
    verdicts: dict[int, str] = {}
    wanted = set(expected_indices)
    for line in raw.splitlines():
        stripped = line.strip()
        if not stripped or ":" not in stripped:
            continue
        idx_part, _, verdict_part = stripped.partition(":")
        idx_token = idx_part.strip().lstrip("-").strip()
        if not idx_token.isdigit():
            continue
        idx = int(idx_token)
        if idx not in wanted:
            continue
        # Normalise separators so "off subject"/"off-subject"/"off_subject" collapse.
        norm = verdict_part.strip().lower().replace("-", "_").replace(" ", "_")
        if norm.startswith("on"):
            verdicts[idx] = "ON"
        elif norm.startswith("off_subject") or norm.startswith("offsubject"):
            verdicts[idx] = "OFF_SUBJECT"
        elif norm.startswith("off_aspect") or norm.startswith("offaspect"):
            verdicts[idx] = "OFF_ASPECT"
        elif norm.startswith("off"):
            # Legacy bare OFF -> OFF_ASPECT (conservative: never delete on the
            # old verdict form).
            verdicts[idx] = "OFF_ASPECT"
        # else: unrecognised -> leave unset -> count mismatch -> fail-open.
    if set(verdicts.keys()) != wanted:
        return None
    return verdicts


def classify_topic_relevance(
    sources: list[dict[str, Any]],
    research_question: str,
    llm_callable: Callable[[str], str],
    *,
    batch_size: int | None = None,
    primary_trial_anchors: list[str] | None = None,
    anchor_predicate: Callable[[dict[str, Any]], bool] | None = None,
) -> TopicGateResult:
    """Drop sources CONFIDENTLY classified OFF-topic for the research question.

    Pure + side-effect-free (apart from logging): the caller supplies the LLM
    via ``llm_callable(prompt: str) -> str`` so this is fully unit-testable
    with a stub. Marquee / required-entity anchors are EXEMPT (never dropped).
    FAIL-OPEN: any LLM exception, count mismatch, or unparseable verdict keeps
    the whole batch. Drops ONLY on an explicit confident OFF verdict.

    Args:
        sources: evidence rows (selection-stage, post floor + dedup).
        research_question: the user's raw question (the topic anchor).
        llm_callable: synchronous ``str -> str`` LLM interface.
        batch_size: sources per LLM call (default :func:`topic_batch_size`).
        primary_trial_anchors: named-trial anchors; a row matching one is
            exempt (handled via ``anchor_predicate`` when supplied).
        anchor_predicate: optional extra "is this a primary anchor" test
            (the orchestrator passes the selector's anchor matcher so the
            exemption is identical to the floor stage). Marquee detection is
            always applied in addition.

    Returns:
        TopicGateResult with kept/dropped rows + honest telemetry.
    """
    n_in = len(sources)
    if n_in == 0:
        return TopicGateResult(
            kept_rows=[], dropped_rows=[], n_in=0, n_kept=0,
            n_dropped_offtopic=0, notes=["topic_gate: empty pool"],
        )
    if not (research_question or "").strip():
        # Nothing to anchor on — FAIL-OPEN, keep everything.
        return TopicGateResult(
            kept_rows=list(sources), dropped_rows=[], n_in=n_in,
            n_kept=n_in, n_dropped_offtopic=0,
            notes=["topic_gate: empty research_question — fail-open"],
        )

    size = batch_size if (batch_size and batch_size > 0) else topic_batch_size()

    def _is_exempt(row: dict[str, Any]) -> bool:
        if _row_is_marquee_anchor(row):
            return True
        if anchor_predicate is not None:
            try:
                return bool(anchor_predicate(row))
            except Exception:
                return False
        return False

    # Partition exempt rows out — they bypass classification entirely.
    exempt_rows: list[dict[str, Any]] = []
    judged_rows: list[dict[str, Any]] = []
    judged_meta: list[tuple[str, str]] = []  # (title, snippet) per judged row
    # I-deepfix-003 (#1374) Fix 4 (topic-side): chrome non-sources are NOT judged (nothing real
    # to judge) — tracked separately so they never inflate the marquee-``exempt`` telemetry, and
    # they stay in ``sources`` so the DEFAULT keep-all path still returns them (the chrome-delete
    # leg removes them later). Read the flag ONCE.
    chrome_skip = junk_chrome_before_offtopic_enabled()
    n_chrome_skipped = 0
    for row in sources:
        if _is_exempt(row):
            exempt_rows.append(row)
            continue
        if chrome_skip and _row_is_chrome_nonsource(row):
            # A failed fetch, not a source — never judge it, never stamp it off-topic.
            n_chrome_skipped += 1
            continue
        title = _row_title_text(row)
        snippet = _row_snippet_text(row)
        if not title and not snippet:
            # Nothing to judge on -> keep (fail-open per-row).
            exempt_rows.append(row)
            continue
        judged_rows.append(row)
        judged_meta.append((title, snippet))

    # Confident-OFF verdicts are accumulated in the loop. The kept set is
    # computed once below preserving the caller's ORIGINAL order — critical
    # because `evidence_for_gen` arrives already ranked best-first (relevance x
    # authority) and there is NO re-rank between this gate and the generator.
    # Partitioning exempt/kept to the end would push high-value marquee / anchor
    # rows to the tail of the list the generator sees (a real regression on the
    # gate-ON acceptance path).
    #
    # I-deepfix-001 (§-1.3 WEIGHT, DON'T FILTER — the operator names the "scope
    # hard-filter" as a BANNED anti-pattern; the ONLY hard gate is the
    # faithfulness engine): a confident-OFF source is, BY DEFAULT, KEPT in the
    # pool and DEMOTED (disclosed off-topic via the ``topic_offtopic_demoted``
    # sidecar), NEVER hard-dropped. Topicality is a WEIGHT — the source still
    # flows to composition where the UNCHANGED strict_verify / NLI / 4-role
    # engine is the only gate. The legacy hard-drop is preserved behind
    # ``PG_SCOPE_TOPIC_GATE_HARD_DROP`` (audit / reversal). Order is unchanged in
    # BOTH modes (no tail-partition), so a demoted row stays best-first-ranked.
    hard_drop = topic_gate_hard_drop_enabled()
    rescue_on_stamp = os.environ.get("PG_TOPIC_GATE_RESCUE_ON_STAMP", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )
    # I-deepfix-003 #1374 Fix 3: split the OFF verdict into OFF_ASPECT (demote-keep) vs
    # OFF_SUBJECT (the only deletable OFF). Default ON; OFF = byte-identical legacy prompt
    # + two-verdict parser + no ``topic_off_subject`` sidecar.
    split = topic_gate_subject_aspect_split_enabled()
    offtopic_rows: list[dict[str, Any]] = []
    offtopic_titles: list[str] = []
    ontopic_rows: list[dict[str, Any]] = []  # I-deepfix-001: confident-ON, for the rescue False-stamp
    # I-deepfix-003 Fix 3: confident-OFF_SUBJECT rows (a subset of offtopic_rows) — the
    # ONLY rows that receive the deletable ``topic_off_subject=True`` sidecar. Empty
    # unless the subject/aspect split is enabled.
    offsubject_rows: list[dict[str, Any]] = []
    # I-deepfix-003 gate-fix (Codex P1): confident-OFF_ASPECT rows (same entity, wrong
    # aspect — demote-KEEP, NEVER deletable). Tracked so the deletable ``topic_off_subject``
    # sidecar can be CLEARED to False on them (demote path below) — a STALE True baked into
    # corpus_snapshot by an earlier run must NEVER survive on a row THIS run re-verdicts
    # OFF_ASPECT (it would be misread as a fresh OFF_SUBJECT and deleted). Empty unless the
    # subject/aspect split is enabled.
    offaspect_rows: list[dict[str, Any]] = []

    # P0-1a (default OFF): corpus-salient on-topic anchors derived once from the judged titles.
    ontopic_anchors = (
        _derive_ontopic_anchors(judged_meta) if _ontopic_anchors_enabled() else []
    )
    # P0-2 (default ON): question-DELIVERABLE axes derived once from the QUESTION TEXT (the
    # occupations / industries / application areas / required table columns the report must
    # cover). Injected as explicit ON-TOPIC scope so a credible page ABOUT a required
    # occupation/industry is not whole-dropped as OFF_SUBJECT (§-1.3.1 credible-on-topic-never-
    # deleted). General/question-agnostic — empty for a question that demands no such breakdown.
    deliverable_anchors = (
        _derive_question_deliverable_anchors(research_question)
        if _question_deliverable_anchors_enabled() else []
    )
    if deliverable_anchors:
        _LOGGER.info(
            "[scope] topic_gate P0-2 question-deliverable anchors (%d) injected as ON-TOPIC "
            "scope: %s", len(deliverable_anchors), "; ".join(deliverable_anchors[:12]),
        )

    for start in range(0, len(judged_rows), size):
        end = min(start + size, len(judged_rows))
        batch_rows = judged_rows[start:end]
        batch_meta = judged_meta[start:end]
        batch = [
            (local_idx, batch_meta[local_idx][0], batch_meta[local_idx][1])
            for local_idx in range(len(batch_rows))
        ]
        expected = [b[0] for b in batch]
        prompt = _build_batch_prompt(
            research_question, batch, subject_aspect_split=split,
            ontopic_anchors=ontopic_anchors,
            deliverable_anchors=deliverable_anchors,
        )
        try:
            raw = llm_callable(prompt)
        except Exception as exc:  # FAIL-OPEN on any LLM error -> keep batch.
            _LOGGER.warning(
                "[scope] topic_gate batch LLM error — fail-open, keeping "
                "%d sources: %s", len(batch_rows), str(exc)[:200],
            )
            continue
        if split:
            verdicts = _parse_batch_verdicts_split(raw, expected)
        else:
            verdicts = _parse_batch_verdicts(raw, expected)
        if verdicts is None:  # FAIL-OPEN on count mismatch / unparseable.
            _LOGGER.warning(
                "[scope] topic_gate batch unparseable / count mismatch — "
                "fail-open, keeping %d sources", len(batch_rows),
            )
            continue
        for local_idx, row in enumerate(batch_rows):
            v = verdicts.get(local_idx)
            if split:
                # Three-verdict split. Both OFF kinds are DEMOTED (weight); only
                # OFF_SUBJECT additionally carries the deletable sidecar below.
                if v == "OFF_SUBJECT":
                    offtopic_rows.append(row)
                    offtopic_titles.append(batch_meta[local_idx][0] or "(no title)")
                    offsubject_rows.append(row)
                elif v == "OFF_ASPECT":
                    offtopic_rows.append(row)
                    offtopic_titles.append(batch_meta[local_idx][0] or "(no title)")
                    offaspect_rows.append(row)
                elif v == "ON":
                    ontopic_rows.append(row)
                continue
            if v is True:  # confident OFF only
                offtopic_rows.append(row)
                # batch_meta is already the per-batch slice -> index locally.
                offtopic_titles.append(batch_meta[local_idx][0] or "(no title)")
            elif v is False:  # confident ON
                # I-deepfix-001 (drb_72 forensic): RESCUE semantics. Historically the gate wrote
                # ONLY True (never False), so a re-judge (PG_RESUME_RUN_TOPIC_JUDGE) could ADD demotes
                # but never CLEAR a stale bad stamp baked into the corpus_snapshot by an earlier run.
                # Stamping False on a confident-ON verdict lets a fixed-prompt re-judge un-bury the
                # seminal papers wrongly demoted upstream. Faithfulness-neutral: downstream
                # (_is_confirmed_offtopic keys on `is True`; is_topic_unjudged on `is not None`) already
                # handles False. Gated PG_TOPIC_GATE_RESCUE_ON_STAMP (default ON); OFF = byte-identical.
                ontopic_rows.append(row)

    # P0-1b (S2/S3 re-pass) — CATEGORY-CONSISTENCY fail-open (§-1.3.1: credible on-topic NEVER
    # deleted). A row this run verdicted the DELETABLE OFF_SUBJECT is DOWNGRADED to OFF_ASPECT
    # (demote-KEEP, deletable sidecar cleared) when a sibling in the SAME category (registrable
    # host + numeric-template path family, e.g. the BLS OES /oes/current/# occupational-wage
    # family) was verdicted ON or OFF_ASPECT — an inconsistent whole-drop is uncertainty by
    # definition, so KEEP. Deterministic, fail-open, disclosed. Only under the subject/aspect
    # split (OFF_SUBJECT is the only deletable verdict). Kill switch OFF => byte-identical.
    if split and _topic_category_consistency_enabled() and offsubject_rows:
        kept_categories: set[str] = set()
        for row in ontopic_rows:
            sig = _category_signature(row)
            if sig:
                kept_categories.add(sig)
        for row in offaspect_rows:
            sig = _category_signature(row)
            if sig:
                kept_categories.add(sig)
        if kept_categories:
            retained_offsubject: list[dict[str, Any]] = []
            n_downgraded = 0
            for row in offsubject_rows:
                sig = _category_signature(row)
                if sig and sig in kept_categories:
                    offaspect_rows.append(row)  # same-category sibling kept => KEEP (demote only)
                    n_downgraded += 1
                else:
                    retained_offsubject.append(row)
            offsubject_rows = retained_offsubject
            if n_downgraded:
                _LOGGER.info(
                    "[scope] topic_gate P0-1b category-consistency: %d OFF_SUBJECT source(s) "
                    "downgraded to OFF_ASPECT (same-category sibling kept — credible on-topic "
                    "never deleted, §-1.3.1)", n_downgraded,
                )

    if hard_drop:
        # LEGACY (explicit opt-in): hard-drop the confident-OFF set.
        _off_ids = {id(r) for r in offtopic_rows}
        kept_rows = [r for r in sources if id(r) not in _off_ids]
        dropped_rows, dropped_titles = offtopic_rows, offtopic_titles
        demoted_rows: list[dict[str, Any]] = []
        demoted_titles: list[str] = []
    else:
        # DEFAULT (§-1.3 keep-all + demote): KEEP every source (original order),
        # disclose the confident-OFF set as DEMOTED, and stamp a faithfulness-
        # neutral sidecar so a downstream weighter can sink it WITHOUT dropping.
        kept_rows = list(sources)
        for row in offtopic_rows:
            row["topic_offtopic_demoted"] = True
        # I-deepfix-001 (drb_72): RESCUE — stamp False on confident-ON rows so a fixed-prompt
        # re-judge CLEARS a stale bad True baked into the corpus_snapshot by an earlier run.
        # Gated PG_TOPIC_GATE_RESCUE_ON_STAMP (default ON); OFF => no False stamp = byte-identical.
        if rescue_on_stamp:
            for row in ontopic_rows:
                row["topic_offtopic_demoted"] = False
        # I-deepfix-003 #1374 Fix 3: stamp the deletable sidecar ONLY on OFF_SUBJECT
        # rows (a clearly different subject — scholar-mill / unrelated-domain junk).
        # OFF_ASPECT rows carry ONLY ``topic_offtopic_demoted`` (demote-keep, never
        # deletable). The downstream junk-deletion gate keys deletion on this sidecar.
        for row in offsubject_rows:
            row["topic_off_subject"] = True
        # I-deepfix-003 gate-fix (Codex P1): POP the deletable sidecar off every row THIS run
        # re-judged NON-OFF_SUBJECT (confident-ON or OFF_ASPECT). The sidecar was only ever SET
        # True (above) and never cleared, so a STALE topic_off_subject=True reloaded from an
        # earlier run's corpus_snapshot survived on a row the CURRENT judge verdicts OFF_ASPECT
        # — run_honest_sweep_r3 builds its fresh OFF_SUBJECT id set from ``demoted_rows where
        # topic_off_subject is True``, so that stale row entered the set and was deleted as
        # ``confirmed_offtopic_subject`` (defeating Fix 2 fresh-verdict-only AND Fix 3
        # OFF_ASPECT=demote-KEEP). Popping makes the sidecar reflect ONLY THIS run's verdict.
        # ``pop(..., None)`` REMOVES a stale True but is a no-op on a clean row (key never
        # present) — so a fresh non-OFF_SUBJECT row stays sidecar-ABSENT (the contract downstream
        # and the tests both assert absence, not False). Guarded by ``split`` so
        # PG_TOPIC_GATE_SUBJECT_ASPECT_SPLIT=0 is byte-identical (legacy path never writes it).
        if split:
            for row in offaspect_rows:
                row.pop("topic_off_subject", None)
            for row in ontopic_rows:
                row.pop("topic_off_subject", None)
        dropped_rows, dropped_titles = [], []
        demoted_rows, demoted_titles = offtopic_rows, offtopic_titles

    verb = "dropped_offtopic" if hard_drop else "demoted_offtopic"
    notes = [
        f"topic_gate: in={n_in} kept={len(kept_rows)} "
        f"{verb}={len(offtopic_rows)} exempt={len(exempt_rows)} "
        f"chrome_skipped={n_chrome_skipped} "
        f"batch_size={size}"
    ]
    if offtopic_titles:
        _LOGGER.info(
            "[scope] topic_gate %s %d off-topic source(s): %s",
            "DROPPED" if hard_drop else "DEMOTED(kept, disclosed)",
            len(offtopic_titles),
            "; ".join(t[:120] for t in offtopic_titles),
        )

    return TopicGateResult(
        kept_rows=kept_rows,
        dropped_rows=dropped_rows,
        dropped_titles=dropped_titles,
        n_in=n_in,
        n_kept=len(kept_rows),
        n_dropped_offtopic=len(dropped_rows),
        n_exempt=len(exempt_rows),
        notes=notes,
        demoted_rows=demoted_rows,
        demoted_titles=demoted_titles,
        n_demoted_offtopic=len(demoted_rows),
    )
