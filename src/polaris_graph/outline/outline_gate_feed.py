"""Outline FEED — the gate ↔ outline-agent seam (S3), additive + default-OFF.

The Research Planning Gate produces ONE pinned :class:`PlanningGateArtifact`
(contract + plan). At the *post-retrieval* outline stage the gate does not
replace the evidence-aware outline agent; it **FEEDS** it (consolidated design
§6, Sol §5): it pre-loads the contract's coverage obligations as PENDING gaps so
the deep-think loop CLOSES contract gaps, and it threads the retrieval *scope*
(the same ``research_frame`` / ``protocol`` used by initial retrieval) into the
outline-stage gap search so a correctly scoped first pass is not diluted by an
unconstrained follow-up query.

This module is PURE + deterministic (no network, no LLM, no I/O). It only reads
an already-pinned contract/projection and returns plain data:

  * :func:`coverage_gap_seeds` — the contract's REQUIRED coverage obligations
    (``required_coverage`` / ``must_address``) as ``(section, aspect)`` gap
    seeds. **Required topics are coverage OBLIGATIONS, not automatically
    headings** — they are pre-loaded PENDING in the gap ledger, never mapped 1:1
    onto section titles (the round-1 coverage-to-heading bug the design forbids).
  * :func:`build_term_ledger` — the binding-term → owning-section map + the set
    of exact-title / order locks, so ``update_outline`` can reject a revision
    that drops an explicit lock or the last owner of a binding term.
  * :func:`gate_scope_for_gap_search` — the ``(research_frame, protocol)`` pair a
    :class:`RetrievalProjection` compiles, threaded into the outline-stage gap
    search (:func:`outline_agent._tool_search_more_evidence`).

Guardrail posture
-----------------
* **ADD / ROUTE, never filter.** The FEED only ADDS PENDING gap todos (search
  MORE) and ROUTES the gap search to the gate's scope. It never drops a source,
  never filters the banked corpus, never removes a section that owns a binding
  term. There is no drop path here.
* **Coverage != heading.** Required coverage becomes a gap OBLIGATION with an
  ``(section="", aspect=<topic>)`` unassigned home, so the loop searches for it
  and the outliner homes it under whatever section fits — the topic is never
  forced to become its own heading.
* **Fail-open.** Every helper tolerates a degraded/empty/``None`` contract or
  projection: it returns empty data, so the caller reads the champion default
  (no seeded gaps, no ledger locks, no scoped gap search) and the run is
  byte-identical to today's champion.
* **Never invent a constraint.** Only ``force == hard`` terms (which the schema
  guarantees are ``origin == explicit``/user-backed) become binding-term ledger
  owners or locks. Inferred / preference terms contribute optional gap seeds
  only — never a lock, never a hard veto on a revision.
"""

from __future__ import annotations

from typing import Any, Optional

# Keep this module import-light: the schema types are only used for isinstance /
# attribute reads, all guarded, so a caller may pass duck-typed objects too.

# Coverage-requirement dimensions/keys that name a REQUIRED obligation. A gate
# contract carries these as ``CoverageRequirement`` objects; a looser upstream
# may hand a plain dict with ``required_coverage`` / ``must_address`` lists.
_REQUIRED_COVERAGE_KEYS: tuple[str, ...] = ("required_coverage", "must_address")


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _term_value_text(term: Any) -> str:
    """The human-readable text of a ContractTerm-ish object (or plain value)."""
    if term is None:
        return ""
    val = getattr(term, "value", term)
    if isinstance(val, (list, tuple)):
        return " ".join(_norm(v) for v in val if _norm(v)).strip()
    return _norm(val)


def _is_hard(term: Any) -> bool:
    """True iff the term is a HARD force term (schema guarantees explicit/user)."""
    force = getattr(term, "force", None)
    if force is not None:
        return str(force).strip().lower() == "hard"
    # duck-typed dict shape
    if isinstance(term, dict):
        return str(term.get("force", "")).strip().lower() == "hard"
    return False


# ---------------------------------------------------------------------------
# FEED 1 — coverage obligations -> PENDING gap seeds (NOT headings)
# ---------------------------------------------------------------------------


def coverage_gap_seeds(contract: Any) -> list[dict[str, str]]:
    """The contract's REQUIRED coverage obligations as gap seeds.

    Returns a list of ``{"section": ..., "aspect": ..., "term_id": ...}``. Each
    is a coverage OBLIGATION the deep-think loop should CLOSE — pre-loaded PENDING
    in the gap ledger by the caller, so ``next_pending()`` routes a scoped gap
    search for it. **The ``section`` is deliberately left EMPTY ("(unassigned)")**
    unless the coverage requirement is bound to an EXPLICIT section: a required
    topic is a coverage obligation, not automatically a heading (the round-1 bug).

    Fail-open: a ``None`` / empty / shapeless contract yields ``[]`` (no seeds),
    so the caller keeps the champion behavior (no pre-loaded gaps).
    """
    if contract is None:
        return []
    out: list[dict[str, str]] = []
    seen: set[str] = set()

    def _add(aspect: str, term_id: str = "", section: str = "") -> None:
        aspect = _norm(aspect)
        if not aspect:
            return
        key = f"{_norm(section).lower()}||{aspect.lower()}"
        if key in seen:
            return
        seen.add(key)
        out.append({
            "section": _norm(section),
            "aspect": aspect,
            "term_id": _norm(term_id),
        })

    # 1) Structured contract: CoverageRequirement objects marked required.
    coverage = getattr(contract, "coverage", None)
    if isinstance(coverage, (list, tuple)):
        # map requirement_id -> the explicit section that owns it (if any), so a
        # coverage req the deliverable EXPLICITLY bound to a section keeps that
        # home; every other required topic stays unassigned (never a new heading).
        req_to_section = _explicit_req_sections(contract)
        for cr in coverage:
            required = getattr(cr, "required", True)
            if not required:
                continue
            aspect = _term_value_text(getattr(cr, "statement", None))
            if not aspect:
                # fall back to the requirement's own kind/id so it is still tracked
                aspect = _norm(getattr(cr, "requirement_id", ""))
            req_id = _norm(getattr(cr, "requirement_id", ""))
            term_id = _norm(getattr(getattr(cr, "statement", None), "term_id", "")) or req_id
            _add(aspect, term_id=term_id, section=req_to_section.get(req_id, ""))

    # 2) Duck-typed dict shape (a looser upstream): required_coverage/must_address.
    if isinstance(contract, dict):
        for key in _REQUIRED_COVERAGE_KEYS:
            vals = contract.get(key)
            if isinstance(vals, (list, tuple)):
                for v in vals:
                    _add(_term_value_text(v) or _norm(v))

    return out


def _explicit_req_sections(contract: Any) -> dict[str, str]:
    """Map ``requirement_id -> explicit section title`` for coverage reqs the
    deliverable EXPLICITLY placed under an exact-title-locked section. Only an
    explicit / user section counts (never an inferred/gate-proposed heading), so
    a required topic never silently becomes a heading."""
    out: dict[str, str] = {}
    sections = getattr(contract, "sections", None)
    if not isinstance(sections, (list, tuple)):
        return out
    for sec in sections:
        if not getattr(sec, "exact_title_lock", False):
            continue
        title = _term_value_text(getattr(sec, "title", None))
        if not title:
            continue
        for rid in (getattr(sec, "coverage_requirement_ids", None) or []):
            rid = _norm(rid)
            if rid:
                out[rid] = title
    return out


# ---------------------------------------------------------------------------
# FEED 2 — the term ledger (binding term -> owning sections + locks)
# ---------------------------------------------------------------------------


def build_term_ledger(
    contract: Any, coverage_matrix: Any = None,
) -> dict[str, Any]:
    """Build the immutable term ledger the outline workspace validates against.

    Returns a plain dict::

        {
          "binding_term_owners": {term_id: [section_title, ...]},  # last-owner guard
          "locked_titles": [title, ...],       # exact-title locks (explicit/user)
          "ordered_titles": [title, ...],      # order-locked titles (in order)
          "binding_term_ids": [term_id, ...],  # every hard/binding term id
        }

    Only HARD (``force == hard``, schema-guaranteed explicit/user) terms are
    binding. Section ownership is read from the plan's ``coverage_matrix`` when
    supplied (a binding term -> its ``section_ids``); a section that owns a
    binding term is protected from being dropped as the LAST owner.

    Fail-open: ``None`` / empty contract -> an empty ledger (no locks, no binding
    owners), so ``update_outline`` validation is a no-op and the run is
    byte-identical.
    """
    ledger: dict[str, Any] = {
        "binding_term_owners": {},
        "locked_titles": [],
        "ordered_titles": [],
        "binding_term_ids": [],
    }
    if contract is None:
        return ledger

    # binding term ids: every HARD term across the contract.
    binding_ids: list[str] = []
    all_terms = getattr(contract, "all_terms", None)
    if callable(all_terms):
        try:
            for t in all_terms():
                if _is_hard(t):
                    tid = _norm(getattr(t, "term_id", ""))
                    if tid:
                        binding_ids.append(tid)
        except Exception:  # noqa: BLE001 — fail-open
            binding_ids = []
    ledger["binding_term_ids"] = _dedup(binding_ids)

    # exact-title / order locks: explicit section requirements.
    locked: list[str] = []
    ordered: list[tuple[int, str]] = []
    sections = getattr(contract, "sections", None)
    if isinstance(sections, (list, tuple)):
        for sec in sections:
            title = _term_value_text(getattr(sec, "title", None))
            if not title:
                continue
            if getattr(sec, "exact_title_lock", False):
                locked.append(title)
            order = getattr(sec, "order", None)
            if isinstance(order, int) and getattr(sec, "exact_title_lock", False):
                ordered.append((order, title))
    ledger["locked_titles"] = _dedup(locked)
    ledger["ordered_titles"] = [t for _, t in sorted(ordered, key=lambda x: x[0])]

    # binding-term -> owning sections (from the coverage matrix). Only bindings
    # whose term id is in binding_ids get last-owner protection.
    owners: dict[str, list[str]] = {}
    matrix = coverage_matrix
    if matrix is None:
        matrix = getattr(getattr(contract, "plan", None), "coverage_matrix", None)
    if isinstance(matrix, (list, tuple)):
        binding_set = set(ledger["binding_term_ids"])
        # map requirement/section ids to section TITLES via the contract sections.
        sec_id_to_title = _section_id_to_title(contract)
        for binding in matrix:
            tid = _norm(getattr(binding, "contract_term_id", ""))
            if tid and tid not in binding_set:
                # the coverage-matrix may bind a coverage requirement whose
                # statement term is hard; keep only genuinely-binding ids.
                continue
            sec_ids = getattr(binding, "section_ids", None) or []
            titles = [
                sec_id_to_title.get(_norm(sid), _norm(sid))
                for sid in sec_ids if _norm(sid)
            ]
            titles = [t for t in titles if t]
            if tid and titles:
                owners.setdefault(tid, [])
                for t in titles:
                    if t not in owners[tid]:
                        owners[tid].append(t)
    ledger["binding_term_owners"] = owners
    return ledger


def _section_id_to_title(contract: Any) -> dict[str, str]:
    out: dict[str, str] = {}
    sections = getattr(contract, "sections", None)
    if isinstance(sections, (list, tuple)):
        for sec in sections:
            sid = _norm(getattr(sec, "section_id", ""))
            title = _term_value_text(getattr(sec, "title", None))
            if sid and title:
                out[sid] = title
    return out


# ---------------------------------------------------------------------------
# FEED 3 — the gate's retrieval scope for the outline-stage gap search
# ---------------------------------------------------------------------------


def gate_scope_for_gap_search(
    projection: Any, *, base_question: str = "",
) -> tuple[Any, Optional[dict[str, Any]]]:
    """The ``(research_frame, protocol)`` a :class:`RetrievalProjection` compiles.

    THE BUG FIX seam (both designers): ``outline_agent._tool_search_more_evidence``
    calls ``run_live_retrieval`` WITHOUT ``research_frame`` / ``protocol`` today, so
    the outline-stage gap search runs UNSCOPED even under a hard journal / language
    / jurisdiction contract. This returns the SAME scope levers the initial
    retrieval used, so the gap query keeps that scope.

    Fail-open: a ``None`` projection (or one that routes nothing) yields
    ``(None, None)`` — exactly the champion ``run_live_retrieval`` defaults, so the
    gap search is byte-identical to today.
    """
    if projection is None:
        return (None, None)
    frame = None
    protocol = None
    to_frame = getattr(projection, "to_research_frame", None)
    if callable(to_frame):
        try:
            frame = to_frame()
        except Exception:  # noqa: BLE001 — fail-open
            frame = None
    to_proto = getattr(projection, "to_protocol", None)
    if callable(to_proto):
        try:
            protocol = to_proto(base_question=base_question)
        except Exception:  # noqa: BLE001 — fail-open
            protocol = None
    return (frame, protocol)


# ---------------------------------------------------------------------------
# update_outline validation — reject dropping a lock / last binding owner
# ---------------------------------------------------------------------------


def validate_revision_against_ledger(
    ledger: Optional[dict[str, Any]],
    *,
    titles_before: list[str],
    titles_after: list[str],
) -> list[str]:
    """Return a list of VIOLATION reasons if the revision drops an explicit lock or
    the last owner of a binding term. Empty list => the revision is allowed.

    ``titles_before`` / ``titles_after`` are the section title lists before and
    after the proposed op set. A violation is:

      * a ``locked_title`` present before but absent after (explicit title lock
        dropped), OR
      * a binding term whose EVERY owning section is absent after (the last owner
        of a binding requirement dropped).

    Fail-open: a ``None`` / empty ledger => ``[]`` (no constraint), byte-identical.
    A retitle that keeps the same count but renames a locked title IS a violation
    (the locked title disappeared) — the caller may then defer the op.
    """
    if not ledger:
        return []
    before = {_norm(t) for t in (titles_before or []) if _norm(t)}
    after = {_norm(t) for t in (titles_after or []) if _norm(t)}
    violations: list[str] = []

    for locked in (ledger.get("locked_titles") or []):
        locked_n = _norm(locked)
        if locked_n in before and locked_n not in after:
            violations.append(f"explicit_title_lock_dropped:{locked_n!r}")

    owners: dict[str, list[str]] = ledger.get("binding_term_owners") or {}
    for tid, sec_titles in owners.items():
        present_before = [t for t in sec_titles if _norm(t) in before]
        if not present_before:
            # the binding term had no owner present before — nothing to protect.
            continue
        present_after = [t for t in sec_titles if _norm(t) in after]
        if not present_after:
            violations.append(f"last_owner_of_binding_term_dropped:{tid!r}")

    return violations


# ---------------------------------------------------------------------------
# small utils
# ---------------------------------------------------------------------------


def _dedup(items: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for it in items:
        it = _norm(it)
        if it and it.lower() not in seen:
            seen.add(it.lower())
            out.append(it)
    return out
