"""Compose + render projections (S4) — compile-only + offline.

The typed *compose* and *render* views of a pinned :class:`PlanningGateArtifact`.
These are the S4 levers the consolidated design (§5 compose/render rows, Sol §4
composition/render rows) calls out:

  * **Compose** — thread the contract's *voice* (tone / audience / point-of-view)
    into the section advisory-prose slot. **PROSE GUIDANCE ONLY** — it never
    changes routing, evidence, verification, or length gating. The generator's
    ``advisory_text`` append site (``_call_section`` -> section system prompt) is
    the exact seam this reuses; :func:`compose_voice_advisory` returns the extra
    prose to append there (empty string => the append is inert => byte-identical).
    ``document_type`` selects which *skeleton* the deliverable is; it is surfaced
    as :func:`document_type` for the render/skeleton selection, never a truncation.
  * **Render** — the contract-aware assembly view: required section titles + order,
    references-dedup-by-work policy, and the VERIFIED-only table field allow-list.
    The renderer reads these to assemble the report; it NEVER drops or edits
    verified prose and NEVER touches the citation audit.

Guardrail posture
-----------------
* **Compile-only. No network, no LLM, no I/O.** Plain data (strings, lists,
  dataclasses) from an already-pinned artifact. Never fetches, never verifies.
* **PROSE / STRUCTURE guidance, never a gate.** The compose voice is appended to
  the writer's advisory prose; it cannot drop a sentence, exclude a source, or
  alter ``strict_verify``. Length is *planning context* surfaced for the writer,
  NEVER a truncation threshold. The render view names required sections/order but
  the assembler only ADDS/ORDERS verified sections — it never fabricates one.
* **Fail-open.** Every builder tolerates a degraded / empty / ``None`` contract:
  it returns an empty string / empty lists, so the caller reads the champion
  default and the run is byte-identical to today's champion.
* **Never invent a constraint.** Only ``force == hard`` section titles (which the
  schema guarantees are ``origin == explicit`` / user-backed) become required /
  order-locked. Inferred voice terms contribute prose tone only — never a lock.

Nothing here is wired ON by default. The compose seam is threaded only when a
``compose_projection`` (or its ``voice_advisory`` string) is passed AND the gate
is active; the default kwarg is ``None`` => byte-identical champion behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

# Import-light: the schema types are used for attribute reads only, all guarded,
# so a caller may pass duck-typed spec objects too (mirrors outline_gate_feed).

FORCE_HARD = "hard"


def _norm(s: Any) -> str:
    return str(s or "").strip()


def _term_value_text(term: Any) -> str:
    """Human-readable text of a ContractTerm-ish object (or a plain value)."""
    if term is None:
        return ""
    val = getattr(term, "value", term)
    if isinstance(val, (list, tuple)):
        return ", ".join(_norm(v) for v in val if _norm(v)).strip()
    return _norm(val)


def _is_hard(term: Any) -> bool:
    force = getattr(term, "force", None)
    if force is not None:
        return str(force).strip().lower() == FORCE_HARD
    if isinstance(term, dict):
        return str(term.get("force", "")).strip().lower() == FORCE_HARD
    return False


# ---------------------------------------------------------------------------
# Contract-term dimension keys the compose/render views read.
# ---------------------------------------------------------------------------
# Voice (prose-only) lives on the deliverable spec as ``deliverable.rhetoric.*``
# or on a looser upstream as ``deliverable.tone`` / ``.audience`` / ``.pov``.
_TONE_DIMS: frozenset[str] = frozenset({
    "deliverable.rhetoric.tone", "deliverable.tone", "rhetoric.tone", "tone",
})
_AUDIENCE_DIMS: frozenset[str] = frozenset({
    "objective.audience", "deliverable.rhetoric.audience",
    "deliverable.audience", "audience",
})
_POV_DIMS: frozenset[str] = frozenset({
    "deliverable.rhetoric.point_of_view", "deliverable.rhetoric.pov",
    "deliverable.pov", "point_of_view", "pov",
})
_HEDGING_DIMS: frozenset[str] = frozenset({
    "deliverable.rhetoric.hedging", "hedging",
})
_DOCTYPE_DIMS: frozenset[str] = frozenset({
    "deliverable.kind", "deliverable.document_type", "deliverable.structure",
    "document_type", "kind",
})


def _first_term_text(terms: Any, dims: frozenset[str]) -> str:
    """First non-empty term VALUE among ``terms`` whose dimension is in ``dims``."""
    if not isinstance(terms, (list, tuple)):
        return ""
    for t in terms:
        dim = _norm(getattr(t, "dimension", "")).lower()
        if dim in dims:
            txt = _term_value_text(t)
            if txt:
                return txt
    return ""


# ---------------------------------------------------------------------------
# The projection dataclass
# ---------------------------------------------------------------------------


@dataclass
class ComposeRenderProjection:
    """Compile-time compose + render view of a pinned contract.

    Built by :func:`from_contract` / :func:`from_artifact`. Holds only plain data.
    Empty everywhere => the caller keeps the champion default (byte-identical).
    """

    # compose (prose-only voice)
    tone: str = ""
    audience: str = ""
    point_of_view: str = ""
    hedging: str = ""
    # render / skeleton selection
    doc_type: str = ""
    # render assembly (structure)
    required_titles: list[str] = field(default_factory=list)   # in required order
    ordered: bool = False                                      # order is locked
    references_dedup_by_work: bool = True                      # dedup biblio by work
    # length is PLANNING CONTEXT only — never a truncation gate
    length_note: str = ""

    # -- compose: the prose-only advisory ------------------------------------

    def voice_advisory(self) -> str:
        """The extra advisory PROSE (tone/audience/pov/hedging) for the section
        writer's system prompt. Returns ``""`` when the contract names no voice
        => the append is inert => byte-identical.

        PROSE ONLY: this text guides HOW the writer phrases already-verified
        content. It states no fact, cites no source, and can never drop a
        sentence or alter ``strict_verify``. It is appended alongside the
        existing domain ``advisory_text`` at the same seam.
        """
        parts: list[str] = []
        if self.audience:
            parts.append(f"Write for this audience: {self.audience}.")
        if self.tone:
            parts.append(f"Adopt this tone: {self.tone}.")
        if self.point_of_view:
            parts.append(f"Use this point of view: {self.point_of_view}.")
        if self.hedging:
            parts.append(f"Calibrate hedging as follows: {self.hedging}.")
        if not parts:
            return ""
        return (
            "VOICE GUIDANCE (presentation only — do not add, drop, or alter any "
            "factual claim; every sentence still verifies against its cited "
            "evidence): " + " ".join(parts)
        )

    def document_type(self) -> str:
        """The requested deliverable kind (report / review / memo / matrix / ...),
        used to select the render skeleton. ``""`` => champion default skeleton."""
        return self.doc_type

    def doc_type_directive(self) -> str:
        """The per-archetype doc-type FRAMING directive (a prose-only preamble for
        the section writer's system prompt). ``""`` when no ``doc_type`` resolves
        => inert => byte-identical.

        The framing prose is DATA in ``report_skeleton.COMPOSE_DIRECTIVES`` keyed by
        the resolved archetype (via ``KIND_SYNONYMS``); an unmapped kind falls back
        to the default archetype's directive (disclosed upstream). DIRECTIVE ONLY:
        it states no fact, cites no source, carries no digit / ``ev_`` id, asks for
        no heading. Fail-open: any import/lookup fault => ``""``."""
        if not self.doc_type:
            return ""
        try:
            from src.polaris_graph.generator.report_skeleton import (  # noqa: PLC0415
                compose_doc_type_directive,
            )
            return _norm(compose_doc_type_directive(self.doc_type))
        except Exception:  # noqa: BLE001 — fail-open: never break compose over framing
            return ""

    def compose_advisory(self) -> str:
        """The full ADDITIVE compose preamble for the section system prompt: the
        doc-type framing directive followed by the voice advisory (either may be
        empty). ``""`` when the contract names neither => inert => byte-identical.

        This is the once-per-report string the generator appends at the compose
        seam. The PER-SECTION role (``section_role_advisory``) is a separate,
        later append keyed by the section title. DIRECTIVE ONLY (no fact / digit /
        ``ev_`` id / heading)."""
        parts = [p for p in (self.doc_type_directive(), self.voice_advisory()) if p]
        return "\n\n".join(parts)

    def section_role_advisory(self, section_title: Any) -> str:
        """The per-section ROLE directive for ``section_title`` within this
        deliverable (``""`` when no doc_type resolves or the title is empty).

        The role framing is DATA in ``report_skeleton`` keyed by the resolved
        archetype; this states the section's job in the plan in a single directive
        line so the writer knows how this section serves the deliverable's shape.
        DIRECTIVE ONLY (no fact / digit / ``ev_`` id / heading). Fail-open => ``""``.
        Kept minimal: the shared doc-type framing already carries structure; this
        adds only a short per-section orientation, so a report with no per-section
        role table returns ``""`` and stays byte-identical."""
        title = _norm(section_title)
        if not self.doc_type or not title:
            return ""
        try:
            from src.polaris_graph.generator.report_skeleton import (  # noqa: PLC0415
                compose_section_role,
            )
            return _norm(compose_section_role(self.doc_type, title))
        except Exception:  # noqa: BLE001 — fail-open: never break compose over a role line
            return ""

    def has_voice(self) -> bool:
        return bool(self.tone or self.audience or self.point_of_view or self.hedging)

    # -- render: the deterministic assembly view ------------------------------

    def render_plan(self) -> dict[str, Any]:
        """The plain-data render view for the contract-aware assembler.

        A caller reads ``required_titles`` (+ ``ordered``) to order verified
        sections, ``references_dedup_by_work`` for the bibliography dedup policy,
        and ``length_note`` as reader-facing planning context (NEVER a cap).
        Everything empty => the assembler keeps the champion one-shape default.
        """
        return {
            "document_type": self.doc_type,
            "required_titles": list(self.required_titles),
            "ordered": self.ordered,
            "references_dedup_by_work": self.references_dedup_by_work,
            "length_note": self.length_note,
        }


# ---------------------------------------------------------------------------
# Compilation from a pinned contract / artifact
# ---------------------------------------------------------------------------


def from_contract(contract: Any) -> ComposeRenderProjection:
    """Compile a :class:`ComposeRenderProjection` from a contract.

    Pure + deterministic + fail-open: a ``None`` / degraded / shapeless contract
    yields an empty projection (the caller keeps the champion path).
    """
    proj = ComposeRenderProjection()
    if contract is None:
        return proj

    deliverable = getattr(contract, "deliverable", None)
    objective = getattr(contract, "objective", None)

    # voice: prefer the deliverable rhetoric terms; audience may also live on the
    # objective spec. First non-empty wins; all default to "" (inert).
    proj.tone = _first_term_text(deliverable, _TONE_DIMS)
    proj.audience = (
        _first_term_text(deliverable, _AUDIENCE_DIMS)
        or _first_term_text(objective, _AUDIENCE_DIMS)
    )
    proj.point_of_view = _first_term_text(deliverable, _POV_DIMS)
    proj.hedging = _first_term_text(deliverable, _HEDGING_DIMS)
    proj.doc_type = _first_term_text(deliverable, _DOCTYPE_DIMS)

    # render structure: only EXACT-title-locked (explicit/user) sections are
    # required titles; a required topic is NEVER a heading (round-1 bug). Order
    # is locked only when the sections carry explicit orders.
    titles_with_order: list[tuple[int, str]] = []
    plain_required: list[str] = []
    any_order = False
    sections = getattr(contract, "sections", None)
    if isinstance(sections, (list, tuple)):
        for idx, sec in enumerate(sections):
            if not getattr(sec, "exact_title_lock", False):
                continue
            title = _term_value_text(getattr(sec, "title", None))
            if not title:
                continue
            order = getattr(sec, "order", None)
            if isinstance(order, int):
                titles_with_order.append((order, title))
                any_order = True
            else:
                titles_with_order.append((idx + 10_000, title))  # keep source order
            plain_required.append(title)
    # de-dup preserving the (order, then source) sort.
    seen: set[str] = set()
    ordered_titles: list[str] = []
    for _, title in sorted(titles_with_order, key=lambda x: x[0]):
        low = title.lower()
        if low in seen:
            continue
        seen.add(low)
        ordered_titles.append(title)
    proj.required_titles = ordered_titles
    proj.ordered = any_order and bool(ordered_titles)

    # length as PLANNING CONTEXT — a reader-facing note only, never a cap.
    proj.length_note = _length_note(deliverable)

    return proj


def from_artifact(artifact: Any) -> ComposeRenderProjection:
    """Compile from a pinned :class:`PlanningGateArtifact`."""
    if artifact is None:
        return ComposeRenderProjection()
    return from_contract(getattr(artifact, "contract", None))


def _length_note(deliverable: Any) -> str:
    """A reader-facing planning note derived from any length term. NEVER a cap.

    Returns e.g. ``"target ~2000 words"`` — surfaced as context for the writer /
    render metadata only. An absent length yields ``""``.
    """
    if not isinstance(deliverable, (list, tuple)):
        return ""
    for t in deliverable:
        dim = _norm(getattr(t, "dimension", "")).lower()
        if "length" not in dim:
            continue
        txt = _term_value_text(t)
        if txt:
            return f"planning context (not a hard cap): {dim.rsplit('.', 1)[-1]}={txt}"
    return ""


# ---------------------------------------------------------------------------
# Convenience: the compose-side entrypoint used by the generator seam.
# ---------------------------------------------------------------------------


def compose_voice_advisory(compose_projection: Any) -> str:
    """The prose-only voice advisory for a compose projection (or ``""``).

    Accepts either a :class:`ComposeRenderProjection` or a duck-typed object with
    a ``voice_advisory()`` method, or ``None``. Fail-open: anything unusable =>
    ``""`` => the generator's advisory append is inert => byte-identical.
    """
    if compose_projection is None:
        return ""
    fn = getattr(compose_projection, "voice_advisory", None)
    if callable(fn):
        try:
            return _norm(fn())
        except Exception:  # noqa: BLE001 — fail-open
            return ""
    return ""
