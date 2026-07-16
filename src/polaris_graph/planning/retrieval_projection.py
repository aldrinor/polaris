"""Retrieval projection (S2) — the no-starvation core, compile-only + offline.

This is the typed *retrieval view* of a pinned :class:`PlanningGateArtifact`
(contract + plan). It is the S2 lever the consolidated design (§5, §4 retrieval
row) calls out: the gate's scope must reach FS-Researcher **query generation**
and backend **routing** BEFORE the first fetch — never as a post-fetch filter of
a frozen corpus (the banned 997->131 anti-pattern).

A :class:`RetrievalProjection` COMPILES the contract+plan into exactly the three
levers ``live_retriever.run_live_retrieval`` already exposes but the driver never
populates from the gate:

  * ``research_frame``  — a :class:`research_planner.ResearchFrame` whose
    ``evidence_needs`` are ROUTED from the contract's ``source_types`` (journal /
    academic / scholarly -> ``primary_literature`` = *GO FIND journals*, routing
    the S2 / OpenAlex scholarly adapters), plus entities / comparators /
    jurisdictions for the field-agnostic need-type registry;
  * ``amplified_queries`` — query TEXT built from the plan's MANDATORY query
    intents: concepts + required-terms, plus native-language sub-queries for a
    hard ``source_languages`` term, plus per-entity sub-queries, plus the hard
    scope terms folded into the query text so a "journal-only" rule shapes
    discovery from the first query;
  * ``protocol`` — the frame's anchor protocol (``to_anchor_protocol``), so the
    amplified sub-queries validate against the frame's tokens.

Guardrail posture
-----------------
* **Compile-only. No network, no LLM, no I/O.** This module builds plain data
  (lists of strings, a dataclass) from an already-pinned artifact. It NEVER
  fetches. The only cross-module import is the champion ``ResearchFrame`` (a pure
  dataclass) which it constructs; that construction runs the frame's own
  ``validate_evidence_needs`` so a routed need is always a valid enum member.
* **ADD / ROUTE, never filter.** Every method returns queries or routing hints
  that ENLARGE or STEER discovery. There is no drop path here. The mechanized
  997-guard (:func:`candidate_query_count`) counts the candidate query/evidence
  lanes so a caller can assert the gate path never REDUCES the lane count vs the
  no-gate path — at planning level, before any fetch.
* **Hard vs soft.** A HARD scope term (``force==hard``, which the schema
  guarantees is explicit/user-backed) is folded into query TEXT and routed to a
  backend need. A SOFT term (preference/open) contributes ranking/entity breadth
  but is NEVER allowed to gate. This module cannot introduce a hard filter — it
  only emits query strings + need tokens.
* **Fail-open.** Every builder tolerates a degraded/empty contract: an empty
  contract yields an empty projection (no needs, no amplified queries), so the
  caller reads the champion default (``research_frame=None`` path) and the run is
  byte-identical. Constructing the projection NEVER raises for a shape problem.

Nothing here is wired ON by default. ``fs_researcher_query_gen`` /
``live_retriever`` / ``run_one_query`` accept a ``retrieval_plan=None`` kwarg
(default None => champion behaviour); the projection is threaded only when the
``PG_GATE`` flag is set and an artifact exists. See :mod:`gate_flags`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.polaris_graph.planning.planning_gate_schema import (
    FORCE_HARD,
    PlanningGateArtifact,
    QueryIntent,
    ResearchContract,
    ResearchExecutionPlan,
)

# ---------------------------------------------------------------------------
# source_type -> evidence_need routing (the "GO FIND journals" map)
# ---------------------------------------------------------------------------
# Maps a contract ``scope.source_types`` value (free-string, model-emitted) onto
# the field-agnostic ``EVIDENCE_NEEDS`` enum the need-type router routes adapters
# off. This is the load-bearing S2 routing: a "journal articles only" contract
# term (task-72) routes ``primary_literature`` = the S2 + OpenAlex + scholarly-
# graph adapters, so FS goes and FINDS journals from the first query instead of
# filtering a general corpus afterwards.
#
# Each key is matched as a case-insensitive SUBSTRING of the normalized source
# type, so "peer-reviewed journal article", "academic paper", "scholarly
# article" all route primary_literature. Unmatched source types contribute no
# need (the router's safe generic fallback applies), never an error.
_SOURCE_TYPE_NEED_MAP: tuple[tuple[str, str], ...] = (
    ("journal", "primary_literature"),
    ("peer-review", "primary_literature"),
    ("peer review", "primary_literature"),
    ("academic", "primary_literature"),
    ("scholarly", "primary_literature"),
    ("scientific", "primary_literature"),
    ("paper", "primary_literature"),
    ("study", "primary_literature"),
    ("preprint", "primary_literature"),
    ("regulation", "regulatory"),
    ("regulatory", "regulatory"),
    ("guideline", "regulatory"),
    ("law", "legal"),
    ("legal", "legal"),
    ("case law", "legal"),
    ("statute", "legal"),
    ("court", "legal"),
    ("statistic", "statistical"),
    ("census", "statistical"),
    ("survey data", "statistical"),
    ("dataset", "datasets"),
    ("standard", "standards"),
    ("news", "news_press"),
    ("press", "news_press"),
    ("media", "news_press"),
    ("filing", "company_filings"),
    ("sec ", "company_filings"),
    ("10-k", "company_filings"),
    ("annual report", "company_filings"),
)


def _norm(s: Any) -> str:
    return str(s or "").strip().lower()


def source_type_to_need(source_type: Any) -> Optional[str]:
    """Route a single contract ``source_type`` value onto an ``EVIDENCE_NEEDS``
    token, or ``None`` if it matches no known family (the router falls back to
    the safe generic set — never an error)."""
    st = _norm(source_type)
    if not st:
        return None
    for needle, need in _SOURCE_TYPE_NEED_MAP:
        if needle in st:
            return need
    return None


# ---------------------------------------------------------------------------
# The projection
# ---------------------------------------------------------------------------


@dataclass
class RetrievalProjection:
    """Compile-time retrieval view of a pinned contract + plan.

    Built by :func:`from_artifact` (or :meth:`ResearchContract.to_research_frame`
    via the thin methods added to the schema). Holds only plain data; the
    ``research_frame`` is materialized lazily by :meth:`to_research_frame` so this
    dataclass has no heavy import at construction.
    """

    contract: ResearchContract
    plan: ResearchExecutionPlan
    original_prompt: str = ""

    # Precomputed routing tokens (validated against the frame enum lazily).
    evidence_needs: list[str] = field(default_factory=list)
    jurisdictions: list[str] = field(default_factory=list)
    entities: list[str] = field(default_factory=list)
    comparators: list[str] = field(default_factory=list)
    # Hard scope-term VALUES (verbatim), folded into query text + surfaced for a
    # backend-native filter by a caller that supports one. NEVER a drop here.
    hard_scope_terms: list[str] = field(default_factory=list)
    # Soft/preference scope-term values — ranking hints only, never a gate.
    soft_scope_terms: list[str] = field(default_factory=list)
    # Hard source-language codes/names (e.g. "en"); drive native-language lanes.
    hard_languages: list[str] = field(default_factory=list)

    # -- amplified query text (the FS frontier seed) --------------------------

    def to_amplified_queries(self, *, base_question: str = "") -> list[str]:
        """The gate's query TEXT for ``run_live_retrieval(amplified_queries=...)``.

        Built from the plan's MANDATORY query intents (concepts + required
        terms), each scope-anchored by folding the hard scope terms into the
        query string so the FIRST query already carries "journal" / "English"
        etc. Then per-entity sub-queries and native-language lanes are ADDED.
        Order-stable, de-duplicated (case-insensitively), never truncated here.

        This is strictly ADDITIVE: it returns candidate query strings; the caller
        (FS-Researcher / live_retriever) runs each through the UNCHANGED
        per-query retrieval + frozen faithfulness engine. Nothing is dropped.
        """
        out: list[str] = []
        seen: set[str] = set()

        def _add(q: str) -> None:
            qs = (q or "").strip()
            if not qs:
                return
            key = qs.lower()
            if key in seen:
                return
            seen.add(key)
            out.append(qs)

        scope_suffix = " ".join(self.hard_scope_terms).strip()

        for qi in self.plan.mandatory_query_intents():
            for text in _intent_query_texts(qi):
                if scope_suffix and scope_suffix.lower() not in text.lower():
                    _add(f"{text} {scope_suffix}")
                else:
                    _add(text)

        # per-entity sub-queries (sub-entity discovery), anchored on the base
        # question so a bare entity does not drift into its broad field.
        anchor = (base_question or self.original_prompt or "").strip()
        for ent in self.entities:
            ent = (ent or "").strip()
            if not ent:
                continue
            if anchor:
                _add(f"{ent} {anchor}")
            else:
                _add(ent)

        # native-language lanes: for a HARD source-language, ADD the scope-anchored
        # query in that language slot (the routing hint; the multilingual lane in
        # FS translates). We surface a language-tagged variant of the first few
        # mandatory concepts so a "source: English-language" rule reaches the
        # multilingual reserve as an explicit lane rather than being inferred.
        # (English is the pipeline default; a non-English hard language adds a
        # native tag so the reserve fires.)
        for lang in self.hard_languages:
            lang = (lang or "").strip()
            if not lang or lang.lower() in ("en", "english"):
                continue
            for qi in self.plan.mandatory_query_intents()[:2]:
                for text in _intent_query_texts(qi):
                    _add(f"{text} ({lang})")

        return out

    # -- scope terms ----------------------------------------------------------

    def to_scope_terms(self) -> dict[str, list[str]]:
        """The hard/soft scope split + language lanes, as plain lists.

        A caller that supports a backend-native filter reads ``hard`` for the
        explicit prohibitions/requirements (journal-only, English-only) and
        ``soft`` for ranking preferences. This is a compile view — it never
        applies a filter itself. The 997-guard reads the union count.
        """
        return {
            "hard": list(self.hard_scope_terms),
            "soft": list(self.soft_scope_terms),
            "languages": list(self.hard_languages),
            "evidence_needs": list(self.evidence_needs),
        }

    # -- research frame (backend routing) -------------------------------------

    def to_research_frame(self) -> Any:
        """Materialize a champion :class:`ResearchFrame` for backend routing.

        ``evidence_needs`` route the need-type registry (primary_literature ->
        S2/OpenAlex scholarly adapters = GO FIND journals). Entities/comparators
        seed the anchor tokens. Jurisdictions route jurisdiction scopes. Runs the
        frame's own ``validate_evidence_needs`` so a routed need is always a valid
        enum member; an unroutable source type simply contributes no need (safe
        generic fallback), never an error.

        Returns ``None`` when the projection carries NOTHING to route (empty
        needs AND no entities/jurisdictions) so the caller keeps the champion
        ``research_frame=None`` (byte-identical) path.
        """
        if not (self.evidence_needs or self.entities or self.jurisdictions
                or self.comparators):
            return None
        from src.polaris_graph.planning.research_planner import (  # noqa: PLC0415
            ResearchFrame,
            validate_evidence_needs,
            validate_jurisdiction_shapes,
        )
        # validate/normalize; drop any that fail SHAPE rather than raise (compile
        # view is fail-open — a bad token contributes nothing, never aborts).
        try:
            needs = validate_evidence_needs(self.evidence_needs)
        except Exception:  # noqa: BLE001
            needs = [n for n in self.evidence_needs
                     if _safe_need(n)]
        try:
            juris = validate_jurisdiction_shapes(self.jurisdictions)
        except Exception:  # noqa: BLE001
            juris = []
        return ResearchFrame(
            entities=list(self.entities),
            comparators=list(self.comparators),
            constraints=list(self.hard_scope_terms),
            evidence_needs=needs,
            jurisdictions=juris,
        )

    def to_protocol(self, *, base_question: str = "") -> Optional[dict[str, Any]]:
        """The anchor protocol for ``validate_amplified_queries`` (from the frame).

        ``None`` when there is no frame to anchor (keeps the champion path)."""
        frame = self.to_research_frame()
        if frame is None:
            return None
        anchor = (base_question or self.original_prompt or "").strip()
        return frame.to_anchor_protocol(anchor)

    # -- the mechanized 997-guard (planning level) ----------------------------

    def candidate_query_count(self, *, base_question: str = "") -> int:
        """Count the candidate query/evidence lanes this projection ADDS.

        The 997-guard: a caller asserts ``gate_count >= no_gate_count`` so the
        gate path can NEVER reduce the candidate query/evidence-need count vs the
        no-gate path — at PLANNING level, before any fetch. Counts distinct
        amplified queries plus routed evidence needs (each a discovery lane)."""
        return (
            len(self.to_amplified_queries(base_question=base_question))
            + len(self.evidence_needs)
        )


def _safe_need(n: Any) -> bool:
    from src.polaris_graph.planning.research_planner import EVIDENCE_NEEDS  # noqa: PLC0415
    return _norm(n) in EVIDENCE_NEEDS


def _intent_query_texts(qi: QueryIntent) -> list[str]:
    """The query string(s) a single :class:`QueryIntent` contributes.

    Prefers a concept+required-term join; falls back to alternate phrasings, then
    the raw thread question via concepts. Always returns at least one non-empty
    string when the intent carries any text."""
    parts: list[str] = []
    core = " ".join([*qi.concepts, *qi.required_terms]).strip()
    if core:
        parts.append(core)
    for alt in qi.alternate_phrasings:
        alt = (alt or "").strip()
        if alt:
            parts.append(alt)
    if not parts:
        # nothing structured — fall back to any single concept/phrasing.
        for cand in [*qi.concepts, *qi.alternate_phrasings]:
            if (cand or "").strip():
                parts.append(cand.strip())
                break
    return parts


# ---------------------------------------------------------------------------
# Compilation from a pinned artifact / contract
# ---------------------------------------------------------------------------

# Scope dimensions whose VALUES are folded into query text as scope terms.
_SCOPE_TEXT_DIMENSIONS: tuple[str, ...] = (
    "scope.source_types",
    "scope.source_quality",  # high-quality/peer-reviewed steers the citable menu
    "scope.domains",
    "scope.geographies",
    "scope.prohibited",  # a prohibition is disclosed as a term the caller may filter
)
_LANGUAGE_DIMENSIONS: tuple[str, ...] = (
    "scope.source_languages",
    "scope.languages",
)


def from_contract_and_plan(
    contract: ResearchContract,
    plan: ResearchExecutionPlan,
    *,
    original_prompt: str = "",
) -> RetrievalProjection:
    """Compile a :class:`RetrievalProjection` from a contract + plan.

    Pure + deterministic. Walks the contract's scope + content terms and the
    plan's query intents to derive routing tokens. Fail-open: a degraded/empty
    contract yields an empty projection (the caller keeps the champion path).
    """
    evidence_needs: list[str] = []
    jurisdictions: list[str] = []
    entities: list[str] = []
    comparators: list[str] = []
    hard_scope_terms: list[str] = []
    soft_scope_terms: list[str] = []
    hard_languages: list[str] = []

    def _dedup_add(lst: list[str], val: Any) -> None:
        s = str(val or "").strip()
        if not s:
            return
        if s.lower() not in {x.lower() for x in lst}:
            lst.append(s)

    for term in contract.scope:
        dim = _norm(term.dimension)
        val = term.value
        if val in (None, "", [], {}):
            continue
        vals = val if isinstance(val, (list, tuple)) else [val]

        if dim in _LANGUAGE_DIMENSIONS:
            if term.force == FORCE_HARD:
                for v in vals:
                    _dedup_add(hard_languages, v)
            continue

        # source_types route evidence needs (the GO-FIND-journals map).
        if dim == "scope.source_types":
            for v in vals:
                need = source_type_to_need(v)
                if need:
                    _dedup_add(evidence_needs, need)

        if dim in ("scope.jurisdictions", "scope.geographies"):
            for v in vals:
                _dedup_add(jurisdictions, str(v).strip().upper()[:4])

        # fold the value into the hard/soft scope text bucket.
        bucket = hard_scope_terms if term.force == FORCE_HARD else soft_scope_terms
        if dim in _SCOPE_TEXT_DIMENSIONS or term.force == FORCE_HARD:
            for v in vals:
                _dedup_add(bucket, v)

    # entities + comparators from the content spec (sub-entity discovery breadth).
    for ent in contract.content_terms:
        if _norm(ent.dimension).startswith("content.entit") and ent.value:
            _dedup_add(entities, ent.value)
    for cov in contract.coverage:
        if cov.kind in ("entity",) and cov.statement.value:
            _dedup_add(entities, cov.statement.value)
        if cov.kind in ("comparison",):
            for c in cov.compare_on:
                if c.value:
                    _dedup_add(comparators, c.value)

    return RetrievalProjection(
        contract=contract,
        plan=plan,
        original_prompt=original_prompt,
        evidence_needs=evidence_needs,
        jurisdictions=jurisdictions,
        entities=entities,
        comparators=comparators,
        hard_scope_terms=hard_scope_terms,
        soft_scope_terms=soft_scope_terms,
        hard_languages=hard_languages,
    )


def from_artifact(artifact: PlanningGateArtifact) -> RetrievalProjection:
    """Compile a :class:`RetrievalProjection` from a pinned artifact."""
    return from_contract_and_plan(
        artifact.contract,
        artifact.plan,
        original_prompt=artifact.original_prompt,
    )


# ---------------------------------------------------------------------------
# Transitional adapter: champion ResearchPlan -> projection (the FS seam fix)
# ---------------------------------------------------------------------------


class _ChampionPlanProjection(RetrievalProjection):
    """A projection whose amplified queries ARE the champion plan's ``sub_queries``.

    S2 seam fix (design §5): the FS-Researcher branch in ``run_one_query``
    currently passes only ``_clean_question`` and DISCARDS
    ``_research_plan.sub_queries``. This adapter wraps a champion
    ``research_planner.ResearchPlan`` as a :class:`RetrievalProjection` so the FS
    frontier is seeded with those sub-queries (the gate's pre-retrieval lanes)
    plus the frame's ``evidence_needs`` routing — BEFORE any fetch. Until the full
    gate artifact is wired into ``run_one_query`` (a later step), this carries the
    already-computed champion plan into the FS query frontier instead of throwing
    it away. It NEVER drops a source; it only ADDS the sub-queries the FS branch
    was discarding, and only when ``PG_GATE`` is ON.
    """

    def __init__(self, research_plan: Any, *, original_prompt: str = "") -> None:
        frame = getattr(research_plan, "frame", None)
        sub_queries = list(getattr(research_plan, "sub_queries", []) or [])
        super().__init__(
            contract=ResearchContract(),
            plan=ResearchExecutionPlan(),
            original_prompt=original_prompt,
            evidence_needs=list(getattr(frame, "evidence_needs", []) or []),
            jurisdictions=list(getattr(frame, "jurisdictions", []) or []),
            entities=list(getattr(frame, "entities", []) or []),
            comparators=list(getattr(frame, "comparators", []) or []),
        )
        self._sub_queries = sub_queries
        self._frame = frame

    def to_amplified_queries(self, *, base_question: str = "") -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for q in self._sub_queries:
            qs = (q or "").strip()
            if qs and qs.lower() not in seen:
                seen.add(qs.lower())
                out.append(qs)
        return out

    def to_research_frame(self) -> Any:
        return self._frame

    def to_protocol(self, *, base_question: str = "") -> Optional[dict[str, Any]]:
        if self._frame is None:
            return None
        try:
            return self._frame.to_anchor_protocol(
                (base_question or self.original_prompt or "").strip()
            )
        except Exception:  # noqa: BLE001
            return None


def from_champion_plan(
    research_plan: Any, *, original_prompt: str = ""
) -> Optional[RetrievalProjection]:
    """Adapt a champion ``ResearchPlan`` into a projection, or ``None`` if it has
    no usable sub-queries (keep the champion FS path)."""
    if research_plan is None:
        return None
    if not list(getattr(research_plan, "sub_queries", []) or []):
        return None
    return _ChampionPlanProjection(research_plan, original_prompt=original_prompt)
