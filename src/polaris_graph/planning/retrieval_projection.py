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
# contract source-kind VALUE -> ontology facet_id (the bridge's vocabulary reuse)
# ---------------------------------------------------------------------------


def _load_scope_ontology_safe() -> dict[str, Any]:
    """Load the scope facet ontology, or ``{}`` on any fault (fail-open: the bridge
    then emits opaque facet ids and the enforcer masks nothing)."""
    try:
        from src.polaris_graph.retrieval.scope_facet_classifier import (  # noqa: PLC0415
            load_scope_ontology,
        )
        return load_scope_ontology() or {}
    except Exception:  # noqa: BLE001
        return {}


def _resolve_facet_id(value: Any, ontology: dict[str, Any]) -> tuple[str, str]:
    """Map a contract source-kind VALUE (e.g. ``"journal article"``) to an ontology
    ``(facet_id, dimension)`` via the SAME synonym table the deterministic scope
    extractor uses (LAW VI — no new vocabulary). A value matching no facet synonym
    is returned as an OPAQUE id (``opaque:<value>``, dimension ``source_type``) so it
    is NEVER dropped — it simply classifies no source (fail-open), staying disclosed.
    """
    v = _norm(value)
    if not v:
        return "", "source_type"
    best: tuple[str, str, int] = ("", "source_type", -1)
    for facet in (ontology.get("facets") or []):
        if not isinstance(facet, dict):
            continue
        fid = str(facet.get("id") or "")
        dim = str(facet.get("dimension") or "source_type")
        if not fid:
            continue
        for syn in (facet.get("synonyms") or []):
            synl = str(syn).strip().lower()
            if not synl:
                continue
            # longest matching synonym wins (most specific) — substring both ways to
            # tolerate plurals ("journal articles" == "journal article").
            if synl in v or v in synl:
                if len(synl) > best[2]:
                    best = (fid, dim, len(synl))
    if best[0]:
        return best[0], best[1]
    return f"opaque:{v}", "source_type"


# ---------------------------------------------------------------------------
# Typed retrieval POLICY (spec item 2) — the enforcement-facing compiled view
# ---------------------------------------------------------------------------


@dataclass
class RetrievalPolicy:
    """A typed, hash-stamped policy compiled from the pinned contract + plan.

    This is the enforcement-facing companion to :class:`RetrievalProjection`
    (which owns query TEXT + routing). ``RetrievalPolicy`` is the DECLARATIVE
    predicate set a caller executes as backend filters, prefetch ranking, and a
    post-fetch citable-eligibility verdict — ALWAYS upstream of the frozen
    verifier (it changes which rows are ELIGIBLE to cite, never HOW a claim is
    verified). It is pure data: no network, no LLM, no I/O.

    Fields:
      * ``allowed_source_kinds`` — hard ``scope.source_types`` values. A candidate
        whose kind matches NONE (when non-empty) is out of the citable menu.
      * ``excluded_source_kinds`` — NEGATIVE predicate (``scope.prohibited`` etc.).
        A candidate whose kind matches ANY is masked. NEVER positive query text.
      * ``date_from`` / ``date_to`` — inclusive publication-date interval (ISO
        ``YYYY-MM-DD`` or ``YYYY``), routed server-side to OpenAlex
        ``from/to_publication_date`` where a backend supports it.
      * ``languages`` — hard ``scope.source_languages`` codes/names.
      * ``named_inclusions`` / ``named_exclusions`` — specific named sources/domains
        to pin in / mask out.
      * ``quality_profile`` — a REF to a domain-neutral quality profile (e.g.
        "high") selected over already-fetched metadata; never a query word.
      * ``predicate_force`` — per-predicate ``{predicate_key: "hard"|"soft"}`` so a
        caller knows which are gating vs ranking-only.
      * ``contract_hash`` — the pinned ``contract_sha256`` this policy was compiled
        from, so retrieval/audit can assert hash identity with the compiler.
    """

    allowed_source_kinds: list[str] = field(default_factory=list)
    excluded_source_kinds: list[str] = field(default_factory=list)
    date_from: Optional[str] = None
    date_to: Optional[str] = None
    languages: list[str] = field(default_factory=list)
    named_inclusions: list[str] = field(default_factory=list)
    named_exclusions: list[str] = field(default_factory=list)
    quality_profile: Optional[str] = None
    # OPAQUE eligibility predicates (F2): hard un-normalized deontic clauses
    # preserved verbatim as post-fetch eligibility judgements (a source is judged
    # against each). NEVER a query string; NEVER a positive facet.
    opaque_eligibility: list[str] = field(default_factory=list)
    predicate_force: dict[str, str] = field(default_factory=dict)
    contract_hash: str = ""

    def is_empty(self) -> bool:
        """True when the policy carries no executable predicate (the permissive /
        empty-contract case) — a caller then applies NO filter (byte-identical)."""
        return not (
            self.allowed_source_kinds
            or self.excluded_source_kinds
            or self.date_from
            or self.date_to
            or self.languages
            or self.named_inclusions
            or self.named_exclusions
            or self.quality_profile
            or self.opaque_eligibility
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_source_kinds": list(self.allowed_source_kinds),
            "excluded_source_kinds": list(self.excluded_source_kinds),
            "date_from": self.date_from,
            "date_to": self.date_to,
            "languages": list(self.languages),
            "named_inclusions": list(self.named_inclusions),
            "named_exclusions": list(self.named_exclusions),
            "quality_profile": self.quality_profile,
            "opaque_eligibility": list(self.opaque_eligibility),
            "predicate_force": dict(self.predicate_force),
            "contract_hash": self.contract_hash,
        }

    # -- the contract -> protocol BRIDGE (spec item 1) ------------------------

    def to_scope_protocol(
        self, *, ontology: Optional[dict[str, Any]] = None
    ) -> dict[str, Any]:
        """Compile this policy into the LEGACY ``protocol`` shape the FROZEN
        ``constraint_enforcement.build_scope_enforcement`` reads.

        This is the single wire (Sol §4 "Enforcement") that makes the EXISTING
        weight-demote / mask / named-pin / hard-timeline enforcer act on the GATE's
        pinned terms instead of the parallel legacy regex extraction. It emits:

          * ``scope_constraints`` = ``{facets:[{facet_id, dimension, op, strictness,
            trigger_span}], named_include:[...], named_exclude:[...]}`` — the exact
            ``ScopeConstraints.to_dict()`` shape. ``allowed_source_kinds`` ->
            ``op=prefer`` facets; ``excluded_source_kinds`` -> ``op=exclude`` facets;
            ``named_inclusions``/``named_exclusions`` -> the named lists. Strictness
            is ``hard`` iff the policy marks that predicate hard, else ``weight``.
          * ``date_range`` = ``{"start","end"}`` from ``date_from``/``date_to``.
          * ``user_constraints`` = ``{timeline_strictness}`` (``hard`` iff the date
            predicate is hard — the wire that fires the enforcer's hard-timeline
            mask), plus ``language`` when a hard language predicate is present.

        Source-kind VALUES are resolved to ontology ``facet_id``s via the SAME
        synonym table the deterministic scope extractor uses (no new vocabulary,
        LAW VI). A value that resolves to no facet is emitted as an OPAQUE facet id
        (``opaque:<value>``) so it is NEVER silently dropped — it simply matches no
        source in ``classify_source_facets`` (fail-open demote), but it stays
        disclosed. Pure + deterministic; an empty policy compiles an empty protocol.
        """
        facets: list[dict[str, Any]] = []
        seen_facets: set[tuple[str, str]] = set()

        def _facet(facet_id: str, dimension: str, op: str, hard: bool) -> None:
            key = (facet_id, op)
            if not facet_id or key in seen_facets:
                return
            seen_facets.add(key)
            facets.append({
                "facet_id": facet_id,
                "dimension": dimension,
                "op": op,
                "strictness": "hard" if hard else "weight",
                "trigger_span": "",
            })

        ont = ontology if ontology is not None else _load_scope_ontology_safe()
        allowed_hard = str(
            (self.predicate_force or {}).get("allowed_source_kinds", "soft")
        ).lower() == "hard"
        excluded_hard = str(
            (self.predicate_force or {}).get("excluded_source_kinds", "soft")
        ).lower() == "hard"

        for kind in self.allowed_source_kinds:
            fid, dim = _resolve_facet_id(kind, ont)
            _facet(fid, dim, "prefer", allowed_hard)
        for kind in self.excluded_source_kinds:
            fid, dim = _resolve_facet_id(kind, ont)
            _facet(fid, dim, "exclude", excluded_hard)

        # named in/exclusions -> the enforcer's named_include/named_exclude lists
        # (label + identity; named-exclude is always hard per the enforcer).
        named_include = [
            {"label": str(n).strip(), "op": "include", "strictness": "weight",
             "identity": {}}
            for n in self.named_inclusions if str(n).strip()
        ]
        named_exclude = [
            {"label": str(n).strip(), "op": "exclude", "strictness": "hard",
             "identity": {}}
            for n in self.named_exclusions if str(n).strip()
        ]

        # timeline: date_range + hard-strictness wire (fires the frozen mask).
        date_hard = str(
            (self.predicate_force or {}).get("date", "soft")
        ).lower() == "hard"
        lang_hard = str(
            (self.predicate_force or {}).get("languages", "soft")
        ).lower() == "hard"

        quality_hard = str(
            (self.predicate_force or {}).get("quality_profile", "soft")
        ).lower() == "hard"

        user_constraints: dict[str, Any] = {
            "timeline_strictness": "hard" if (date_hard and (self.date_from or self.date_to))
            else "weight",
        }
        if self.date_from:
            user_constraints["date_start_iso"] = self.date_from
        if self.date_to:
            user_constraints["date_end_iso"] = self.date_to
        # F6: emit ALL hard languages (not just languages[0]) so a multi-language
        # source rule reaches the enforcer intact. ``language`` keeps the legacy
        # scalar (first) for back-compat; ``languages`` carries the full list.
        if lang_hard and self.languages:
            user_constraints["language"] = self.languages[0]
            user_constraints["languages"] = list(self.languages)
            user_constraints["language_strictness"] = "hard"
        # F6: emit the quality_profile so it is no longer decorative — the enforcer
        # (or the post-fetch eligibility stage) reads a domain-neutral quality ref
        # + its strictness. It is NEVER a query word (LAW VI); it selects a profile
        # over already-fetched metadata.
        if self.quality_profile:
            user_constraints["quality_profile"] = self.quality_profile
            user_constraints["quality_strictness"] = "hard" if quality_hard else "weight"
        # F2: opaque eligibility clauses are surfaced (disclosed) as post-fetch
        # eligibility predicates — never a facet, never query text.
        if self.opaque_eligibility:
            user_constraints["opaque_eligibility"] = list(self.opaque_eligibility)

        return {
            "scope_constraints": {
                "facets": facets,
                "named_include": named_include,
                "named_exclude": named_exclude,
            },
            "date_range": {
                "start": self.date_from,
                "end": self.date_to,
            },
            "user_constraints": user_constraints,
        }


def _year_to_iso_from(value: Any) -> Optional[str]:
    """Coerce a scope.date value (``"2024"`` / ``"2024-03"`` / ``"from 2024"``)
    into an inclusive ISO ``from`` date (``YYYY-01-01`` for a bare year). Returns
    ``None`` when no 4-digit year is present — a caller then applies no date
    filter (fail-open)."""
    import re as _re
    s = str(value or "").strip()
    m = _re.search(r"(19|20)\d{2}", s)
    if not m:
        return None
    year = m.group(0)
    # a bare year -> Jan 1 of that year (inclusive "from YEAR onward").
    tail = s[m.end():].lstrip("-/ ")
    mo = _re.match(r"(\d{1,2})", tail)
    if mo:
        month = max(1, min(12, int(mo.group(1))))
        return f"{year}-{month:02d}-01"
    return f"{year}-01-01"


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
    # EXCLUSIONS (scope.prohibited): NEGATIVE predicates. These are values the
    # user forbade ("no blogs", "exclude press releases"). They are NEVER folded
    # into positive query text (the pre-Phase-C bug: a prohibition became a
    # positive query suffix, steering discovery TOWARD the excluded kind). They
    # are surfaced ONLY as a negative eligibility predicate a caller applies
    # against a candidate's metadata (post-fetch, upstream of the frozen verifier).
    excluded_scope_terms: list[str] = field(default_factory=list)
    # NEGATIVE named-source predicates ("don't use Reuters"): NEVER query text,
    # surfaced only as named exclusions the eligibility stage masks on.
    named_exclusions: list[str] = field(default_factory=list)
    # Named-source INCLUSIONS ("Use Reuters and AP"): a retrieval boost, surfaced
    # as named inclusions — never a hard mask on their own.
    named_inclusions: list[str] = field(default_factory=list)
    # OPAQUE eligibility terms (F2): a hard, un-normalized deontic clause preserved
    # verbatim as a POST-FETCH eligibility predicate (a source is judged against
    # it later). It is NEVER folded into positive query text — doing so re-steers
    # discovery toward the very thing an exclusion forbids (the pre-Phase-C bug).
    opaque_eligibility_terms: list[str] = field(default_factory=list)
    # Hard source-language codes/names (e.g. "en"); drive native-language lanes.
    hard_languages: list[str] = field(default_factory=list)
    # Champion-plan breadth: sub-queries ADDED to the amplified frontier so the
    # contract-driven projection keeps the champion planner's discovery breadth
    # (spec item 1: "merged additively with the champion plan's sub_queries so we
    # keep breadth but the CONTRACT drives scope"). Purely ADDITIVE — never a
    # filter; each is scope-anchored like a mandatory intent's text.
    extra_amplified_queries: list[str] = field(default_factory=list)

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

        # champion-plan breadth: ADD the champion planner's sub-queries, each
        # scope-anchored so the CONTRACT's hard scope still shapes discovery while
        # the champion's breadth is preserved (spec item 1). Purely additive.
        for text in self.extra_amplified_queries:
            text = (text or "").strip()
            if not text:
                continue
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
            "excluded": list(self.excluded_scope_terms),
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

    # -- typed retrieval policy (spec item 2) ---------------------------------

    def to_retrieval_policy(self) -> RetrievalPolicy:
        """Compile the typed, hash-stamped :class:`RetrievalPolicy`.

        Walks the SAME pinned contract the projection was built from and reads its
        scope terms into declarative predicates: allowed/excluded source kinds, a
        publication-date interval, languages, named in/exclusions, a quality
        profile ref, and per-predicate hard/soft force. Stamps the contract's
        canonical ``contract_sha256`` as ``contract_hash`` so retrieval + audit can
        assert hash identity with the compiler. Pure + deterministic; an empty
        contract compiles an empty policy (``is_empty()`` -> caller applies no
        filter, byte-identical).
        """
        from src.polaris_graph.planning.planning_gate_schema import sha256_of

        allowed: list[str] = []
        # Seed the NEGATIVE + named + opaque predicate sets from the projection
        # buckets already computed by ``from_contract_and_plan`` (one routing truth:
        # exclusions/named/opaque were classified there, never re-derived from a
        # drifting dimension-name list — F6). The contract walk below only fills the
        # positive/date/language/quality predicates + per-predicate force.
        excluded: list[str] = list(self.excluded_scope_terms)
        languages: list[str] = list(self.hard_languages)
        named_incl: list[str] = list(self.named_inclusions)
        named_excl: list[str] = list(self.named_exclusions)
        opaque: list[str] = list(self.opaque_eligibility_terms)
        quality_profile: Optional[str] = None
        date_from: Optional[str] = None
        date_to: Optional[str] = None
        force: dict[str, str] = {}

        def _add(lst: list[str], v: Any) -> None:
            s = str(v or "").strip()
            if s and s.lower() not in {x.lower() for x in lst}:
                lst.append(s)

        for term in self.contract.scope:
            dim = _norm(term.dimension)
            val = term.value
            if val in (None, "", [], {}):
                continue
            vals = val if isinstance(val, (list, tuple)) else [val]
            is_hard = term.force == FORCE_HARD

            if dim == "scope.source_types":
                for v in vals:
                    _add(allowed, v)
                force.setdefault("allowed_source_kinds", "hard" if is_hard else "soft")
            elif dim in _EXCLUSION_DIMENSIONS:
                # values already captured in excluded_scope_terms; record force.
                force.setdefault("excluded_source_kinds", "hard" if is_hard else "soft")
            elif dim in _NAMED_EXCLUSION_DIMENSIONS:
                # values already captured in named_excl; record force. A named
                # exclusion is always hard downstream (identity-enforced).
                force.setdefault("named_exclusions", "hard")
            elif dim in _OPAQUE_DIMENSIONS:
                # F2: opaque terms are a hard eligibility predicate to be JUDGED
                # later — never a query string / positive facet. Record force only.
                force.setdefault("opaque_eligibility", "hard" if is_hard else "soft")
            elif dim in ("scope.date", "scope.dates", "scope.published_after",
                         "scope.recency"):
                iso = _year_to_iso_from(vals[0])
                if iso and (date_from is None or iso > date_from):
                    date_from = iso
                force.setdefault("date", "hard" if is_hard else "soft")
            elif dim in ("scope.published_before", "scope.date_to"):
                iso = _year_to_iso_from(vals[0])
                if iso:
                    date_to = iso
            elif dim in _LANGUAGE_DIMENSIONS:
                if is_hard:
                    for v in vals:
                        _add(languages, v)
                    force.setdefault("languages", "hard")
            elif dim == "scope.source_quality":
                quality_profile = str(vals[0]).strip() or None
                force.setdefault("quality_profile", "hard" if is_hard else "soft")
            elif dim in ("scope.named_sources", "scope.include_sources",
                         "scope.inclusions"):
                for v in vals:
                    _add(named_incl, v)
                force.setdefault("named_inclusions", "hard" if is_hard else "soft")

        contract_hash = ""
        try:
            contract_hash = sha256_of(self.contract.to_dict())
        except Exception:  # noqa: BLE001 — hash is best-effort provenance, never fatal
            contract_hash = ""

        return RetrievalPolicy(
            allowed_source_kinds=allowed,
            excluded_source_kinds=excluded,
            date_from=date_from,
            date_to=date_to,
            languages=languages,
            named_inclusions=named_incl,
            named_exclusions=named_excl,
            quality_profile=quality_profile,
            opaque_eligibility=opaque,
            predicate_force=force,
            contract_hash=contract_hash,
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
    # NOTE: ``scope.prohibited`` is DELIBERATELY absent. A prohibition is a
    # NEGATIVE predicate — it must NEVER be folded into positive query text (the
    # pre-Phase-C bug where "no blogs" became a "blogs" query suffix). It is
    # routed to ``excluded_scope_terms`` and surfaced as a negative eligibility
    # predicate instead. See ``_EXCLUSION_DIMENSIONS``.
)
# Scope dimensions whose VALUES are NEGATIVE predicates (exclusions). Never query
# text; only a masking eligibility predicate a caller applies to candidate metadata.
# ``scope.excluded_source_kinds`` is the canonical F1 target ("no blogs" / "do not
# cite blogs"); the legacy aliases are kept so an older persisted contract routes.
_EXCLUSION_DIMENSIONS: tuple[str, ...] = (
    "scope.excluded_source_kinds",
    "scope.prohibited",
    "scope.excluded_source_types",
    "scope.exclusions",
)
# NEGATIVE named-source predicates ("don't use Reuters") — routed to
# ``RetrievalPolicy.named_exclusions`` + an ``op=exclude`` named entry, never query text.
_NAMED_EXCLUSION_DIMENSIONS: tuple[str, ...] = (
    "scope.excluded_sources",
    "scope.exclude_sources",
)
# OPAQUE dimensions: a hard OPAQUE clause is a first-class eligibility predicate
# (judged post-fetch against each source), NEVER positive query text. (F2.)
_OPAQUE_DIMENSIONS: tuple[str, ...] = (
    "scope.opaque",
    "content.opaque",
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
    excluded_scope_terms: list[str] = []
    named_exclusions: list[str] = []
    named_inclusions: list[str] = []
    opaque_eligibility_terms: list[str] = []

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

        # EXCLUSIONS FIRST: a prohibition is a NEGATIVE predicate. Route its values
        # to the excluded bucket and CONTINUE — it must NEVER reach the positive
        # query-text fold below (the pre-Phase-C "no blogs" -> "blogs" bug).
        if dim in _EXCLUSION_DIMENSIONS:
            for v in vals:
                _dedup_add(excluded_scope_terms, v)
            continue

        # NEGATIVE NAMED predicates ("don't use Reuters"): a named exclusion, never
        # query text. CONTINUE so it cannot fold into hard_scope_terms below.
        if dim in _NAMED_EXCLUSION_DIMENSIONS:
            for v in vals:
                _dedup_add(named_exclusions, v)
            continue

        # NAMED INCLUSIONS ("Use Reuters and AP"): a retrieval boost, surfaced as a
        # named inclusion. Kept out of hard_scope_terms — a named source is a source
        # IDENTITY predicate, not a generic scope adjective folded into query text.
        if dim in ("scope.named_sources", "scope.include_sources", "scope.inclusions"):
            for v in vals:
                _dedup_add(named_inclusions, v)
            continue

        # OPAQUE (F2): a hard un-normalized deontic clause. It is a POST-FETCH
        # eligibility predicate, NEVER positive query text. CONTINUE so the raw
        # clause text can never land in hard_scope_terms and be suffixed onto every
        # query (which would steer discovery toward what an exclusion forbids). An
        # opaque term whose operator is NOT_IN (an exclude-cue clause) routes to the
        # NEGATIVE bucket so it masks rather than merely being judged.
        if dim in _OPAQUE_DIMENSIONS:
            op = _norm(getattr(term, "operator", ""))
            for v in vals:
                if op == "not_in":
                    _dedup_add(excluded_scope_terms, v)
                else:
                    _dedup_add(opaque_eligibility_terms, v)
            continue

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
        excluded_scope_terms=excluded_scope_terms,
        named_exclusions=named_exclusions,
        named_inclusions=named_inclusions,
        opaque_eligibility_terms=opaque_eligibility_terms,
    )


def from_artifact(artifact: PlanningGateArtifact) -> RetrievalProjection:
    """Compile a :class:`RetrievalProjection` from a pinned artifact."""
    return from_contract_and_plan(
        artifact.contract,
        artifact.plan,
        original_prompt=artifact.original_prompt,
    )


def from_artifact_with_champion_breadth(
    artifact: PlanningGateArtifact,
    research_plan: Any = None,
    *,
    original_prompt: str = "",
) -> RetrievalProjection:
    """The live FS seam projection: the CONTRACT drives scope, the champion plan
    ADDS breadth.

    Compiles ``from_artifact(artifact)`` (so the pinned contract's hard scope
    terms, evidence-need routing, entities and languages are authoritative), then
    ADDITIVELY folds the champion ``research_plan``'s ``sub_queries`` into the
    amplified frontier and its ``frame`` routing tokens (entities / evidence needs
    / jurisdictions / comparators) into the projection — never dropping a lane.

    Spec item 1: ``from_champion_plan`` shipped an EMPTY contract (scope never
    reached retrieval); this keeps the champion's breadth but lets the CONTRACT
    own scope. ``research_plan=None`` degrades to a plain :func:`from_artifact`.
    """
    proj = from_artifact(artifact)
    if research_plan is None:
        if original_prompt and not proj.original_prompt:
            proj.original_prompt = original_prompt
        return proj

    def _dedup_extend(lst: list[str], vals: Any) -> None:
        seen = {x.lower() for x in lst}
        for v in vals or []:
            s = str(v or "").strip()
            if s and s.lower() not in seen:
                seen.add(s.lower())
                lst.append(s)

    proj.extra_amplified_queries = list(
        getattr(research_plan, "sub_queries", []) or []
    )

    frame = getattr(research_plan, "frame", None)
    if frame is not None:
        _dedup_extend(proj.entities, getattr(frame, "entities", []))
        _dedup_extend(proj.comparators, getattr(frame, "comparators", []))
        _dedup_extend(proj.jurisdictions, getattr(frame, "jurisdictions", []))
        _dedup_extend(proj.evidence_needs, getattr(frame, "evidence_needs", []))

    if original_prompt and not proj.original_prompt:
        proj.original_prompt = original_prompt
    return proj


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
