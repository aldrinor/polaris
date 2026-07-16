"""Candidate constraint adapter (Research Planning Gate — S0).

Reconciles the two independent deterministic "rule readers" the champion tree
now carries into ONE list of candidate constraints, each with exact prompt
spans and an origin tag:

  * the ported adversarial rule-reader
    (:mod:`src.polaris_graph.instruction.constraint_extractor`), which returns a
    :class:`~...instruction.constraint_extractor.Constraints` bundle
    (source_types / languages / recency / required_coverage / exclusions /
    format / length / tone); and
  * the champion intake extractors
    (:mod:`src.polaris_graph.retrieval.intake_constraint_extractor`) — the
    deterministic regex passes ``extract_constraints_regex`` (dates + language +
    journal-only + timeline strictness), ``extract_instruction_slots_regex``
    (comparisons / enumerations / topics / structure), and
    ``extract_scope_constraints_regex`` (source-type / jurisdiction facets +
    named sources).

Design contract (S0 — port + reconcile, NO behavior change)
-----------------------------------------------------------
* **This is a candidate list, NOT a pinned contract.** The output is the
  high-recall raw material a later contract compiler validates and pins. Nothing
  here hard-gates, excludes, or filters anything, and nothing here is wired into
  the pipeline. Callers decide what (if anything) to do with the result.
* **Deterministic wins on overlap.** When a rule-reader value and an intake
  regex value describe the same ``(dimension, canonical value)``, the intake
  (regex) candidate is authoritative for span + force; the rule-reader only
  *fills gaps* it uniquely found. Origin is recorded so the merge is auditable.
* **Exact spans preserved.** Every candidate carries the verbatim prompt spans
  that fired it, recovered as ``prompt[start:end]`` with quote equality. A span
  is emitted ONLY when the trigger substring is actually located in the prompt;
  an offset is never fabricated. Values whose trigger phrase cannot be located
  keep the value but carry an empty span list (so the compiler can still see the
  candidate, but can never treat it as span-supported / ``explicit``).
* **Force is observed, never invented.** ``hard`` appears only where a
  deterministic source already marked an exclusivity / prohibition token (intake
  ``strictness == 'hard'``, a named-exclude, or a rule-reader exclusion). Every
  other candidate is ``prefer``. This module never promotes a soft phrasing to
  hard — that is the mechanical no-invention guarantee at the candidate layer.
* **Pure + offline.** No network, no LLM construction. The rule-reader's live
  pass is the caller's responsibility; this adapter takes its already-computed
  ``Constraints`` (or dict) as input. Default: if the caller passes no
  rule-reader result, the adapter reconciles the intake extractors alone.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.polaris_graph.instruction.constraint_extractor import Constraints
from src.polaris_graph.retrieval.intake_constraint_extractor import (
    InstructionSlot,
    ScopeConstraints,
    UserConstraints,
    extract_constraints_regex,
    extract_instruction_slots_regex,
    extract_scope_constraints_regex,
)

# ---------------------------------------------------------------------------
# Origin + force vocab (candidate layer — deliberately small)
# ---------------------------------------------------------------------------

# Where a candidate came from. `deterministic` = one of the intake regex passes
# (authoritative on overlap). `rule_reader` = the ported adversarial extractor
# (gap-filler). `merged` = both sources agreed on the same (dimension, value).
ORIGIN_DETERMINISTIC = "deterministic"
ORIGIN_RULE_READER = "rule_reader"
ORIGIN_MERGED = "merged"

# Observed force. NEVER invented: `hard` only when a deterministic source already
# marked an exclusivity/prohibition; everything else is `prefer`.
FORCE_HARD = "hard"
FORCE_PREFER = "prefer"


# ---------------------------------------------------------------------------
# Types
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class PromptSpan:
    """A verbatim prompt span. ``quote`` MUST equal ``prompt[start:end]``.

    Constructed only via :func:`_locate_span`, which guarantees that invariant;
    a value whose trigger phrase is not found in the prompt yields NO span (the
    candidate is emitted with an empty span list) rather than a fabricated one.
    """

    start: int
    end: int
    quote: str

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start, "end": self.end, "quote": self.quote}


@dataclass
class CandidateConstraint:
    """One reconciled candidate constraint (NOT a pinned contract term).

    ``dimension`` is a stable string in the same open family the gate schema
    uses (e.g. ``source.types``, ``source.language``, ``date.recency``,
    ``content.coverage``, ``content.comparison``, ``deliverable.format``,
    ``deliverable.length``, ``rhetoric.tone``, ``source.named``,
    ``source.scope_facet``, ``source.jurisdiction``).
    """

    dimension: str
    value: Optional[str]
    force: str = FORCE_PREFER          # observed force; never invented as hard
    origin: str = ORIGIN_DETERMINISTIC
    spans: list[PromptSpan] = field(default_factory=list)
    # free-form provenance so the reconciliation stays auditable (which raw
    # source(s) contributed, the raw trigger phrase, any op/strictness, etc.).
    detail: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dimension": self.dimension,
            "value": self.value,
            "force": self.force,
            "origin": self.origin,
            "spans": [s.to_dict() for s in self.spans],
            "detail": dict(self.detail),
        }


# ---------------------------------------------------------------------------
# Span recovery (exact, quote-equality-guaranteed, never fabricated)
# ---------------------------------------------------------------------------

def _locate_span(prompt: str, phrase: Optional[str]) -> Optional[PromptSpan]:
    """Return the first exact occurrence of ``phrase`` in ``prompt`` as a span.

    Guarantees ``span.quote == prompt[span.start:span.end]``. Returns ``None``
    (no span) when ``phrase`` is empty or cannot be located verbatim — the
    adapter never invents an offset for a phrase it can't find.
    """
    if not prompt or not phrase:
        return None
    idx = prompt.find(phrase)
    if idx == -1:
        # Fall back to a case-insensitive locate, but keep the ACTUAL prompt
        # substring as the quote so quote-equality still holds exactly.
        low_i = prompt.lower().find(phrase.lower())
        if low_i == -1:
            return None
        return PromptSpan(low_i, low_i + len(phrase), prompt[low_i:low_i + len(phrase)])
    return PromptSpan(idx, idx + len(phrase), prompt[idx:idx + len(phrase)])


def _spans_for(prompt: str, phrases: list[Optional[str]]) -> list[PromptSpan]:
    """Locate each phrase; drop those not found; dedup by (start, end)."""
    out: list[PromptSpan] = []
    seen: set[tuple[int, int]] = set()
    for ph in phrases:
        sp = _locate_span(prompt, ph)
        if sp is None:
            continue
        key = (sp.start, sp.end)
        if key in seen:
            continue
        seen.add(key)
        out.append(sp)
    return out


# ---------------------------------------------------------------------------
# Per-dimension candidate builders from each deterministic source
# ---------------------------------------------------------------------------

def _from_user_constraints(
    prompt: str, uc: UserConstraints
) -> list[CandidateConstraint]:
    """Intake ``extract_constraints_regex`` -> candidates (dates, language,
    journal-only, timeline strictness)."""
    out: list[CandidateConstraint] = []

    # Language (ISO code). Recover the span from the raw directive that named it.
    if uc.language:
        spans = _spans_for(prompt, list(uc.raw_directives))
        out.append(CandidateConstraint(
            dimension="source.language",
            value=uc.language,
            force=FORCE_PREFER,
            origin=ORIGIN_DETERMINISTIC,
            spans=spans,
            detail={"source": "intake_regex", "raw_directives": list(uc.raw_directives)},
        ))

    # Date window (start/end). Force reflects the extractor's own strictness.
    if uc.date_start_year is not None or uc.date_end_year is not None:
        force = FORCE_HARD if uc.timeline_strictness == "hard" else FORCE_PREFER
        trigger_phrases: list[Optional[str]] = list(uc.raw_directives)
        if uc.timeline_trigger_span:
            trigger_phrases.append(uc.timeline_trigger_span)
        out.append(CandidateConstraint(
            dimension="date.recency",
            value=_date_value(uc),
            force=force,
            origin=ORIGIN_DETERMINISTIC,
            spans=_spans_for(prompt, trigger_phrases),
            detail={
                "source": "intake_regex",
                "date_start_iso": uc.date_start_iso(),
                "date_end_iso": uc.date_end_iso(),
                "timeline_strictness": uc.timeline_strictness,
                "timeline_trigger_span": uc.timeline_trigger_span,
            },
        ))

    # Journal-only is EXTRACTED-but-DORMANT in the champion (operator veto). It
    # is a real deterministic signal, so it becomes a candidate (force=prefer,
    # marked dormant) — never a hard gate. A later stage decides its fate.
    if uc.journal_only:
        out.append(CandidateConstraint(
            dimension="source.types",
            value="journal_article",
            force=FORCE_PREFER,
            origin=ORIGIN_DETERMINISTIC,
            spans=[],  # the regex path records no verbatim journal span
            detail={"source": "intake_regex", "journal_only_dormant": True},
        ))

    return out


def _date_value(uc: UserConstraints) -> Optional[str]:
    lo = uc.date_start_iso()
    hi = uc.date_end_iso()
    if lo and hi:
        return f"{lo}..{hi}"
    return lo or hi


def _from_instruction_slots(
    prompt: str, slots: list[InstructionSlot]
) -> list[CandidateConstraint]:
    """Intake ``extract_instruction_slots_regex`` -> content/coverage candidates.

    Comparisons, enumerations, requested topics and structure are coverage
    obligations (NOT headings — that mapping is deliberately not ported). Each
    slot's verbatim ``text`` recovers its span.
    """
    out: list[CandidateConstraint] = []
    for slot in slots:
        dim = {
            "comparison": "content.comparison",
            "enumeration": "content.coverage",
            "topic": "content.coverage",
            "structure": "deliverable.structure",
        }.get(slot.kind, "content.coverage")
        out.append(CandidateConstraint(
            dimension=dim,
            value=", ".join(slot.entities) if slot.entities else slot.text,
            force=FORCE_PREFER,
            origin=ORIGIN_DETERMINISTIC,
            spans=_spans_for(prompt, [slot.text]),
            detail={
                "source": "intake_regex",
                "slot_id": slot.slot_id,
                "slot_kind": slot.kind,
                "entities": list(slot.entities),
            },
        ))
    return out


def _from_scope_constraints(
    prompt: str, sc: ScopeConstraints
) -> list[CandidateConstraint]:
    """Intake ``extract_scope_constraints_regex`` -> scope-facet / named-source
    candidates. Force mirrors the facet's own strictness (hard only where the
    extractor already saw an exclusivity/prohibition token)."""
    out: list[CandidateConstraint] = []

    for facet in sc.facets:
        dim = (
            "source.jurisdiction"
            if facet.dimension == "jurisdiction"
            else "source.scope_facet"
        )
        force = FORCE_HARD if facet.strictness == "hard" else FORCE_PREFER
        out.append(CandidateConstraint(
            dimension=dim,
            value=facet.facet_id,
            force=force,
            origin=ORIGIN_DETERMINISTIC,
            spans=_spans_for(prompt, [facet.trigger_span]),
            detail={
                "source": "intake_regex",
                "op": facet.op,
                "strictness": facet.strictness,
                "facet_dimension": facet.dimension,
            },
        ))

    for named in list(sc.named_include) + list(sc.named_exclude):
        # A named-exclude is always hard (identity-enforced downstream); a
        # named-include is a boost (prefer).
        force = FORCE_HARD if named.strictness == "hard" else FORCE_PREFER
        out.append(CandidateConstraint(
            dimension="source.named",
            value=named.label,
            force=force,
            origin=ORIGIN_DETERMINISTIC,
            spans=_spans_for(prompt, [named.label]),
            detail={
                "source": "intake_regex",
                "op": named.op,
                "strictness": named.strictness,
                "identity": dict(named.identity),
            },
        ))

    return out


def _from_rule_reader(
    prompt: str, rr: Constraints
) -> list[CandidateConstraint]:
    """Ported adversarial rule-reader ``Constraints`` -> candidates.

    The rule-reader carries no character offsets, so spans are recovered by
    locating each value verbatim in the prompt. When a value's phrase is not
    present verbatim (the LLM paraphrased it), the candidate is still emitted but
    with an empty span list — never a fabricated offset. Exclusions are the only
    rule-reader dimension that carries ``hard`` force (an explicit "exclude").
    """
    out: list[CandidateConstraint] = []

    for st in rr.source_types:
        out.append(CandidateConstraint(
            dimension="source.types", value=st, force=FORCE_PREFER,
            origin=ORIGIN_RULE_READER, spans=_spans_for(prompt, [st]),
            detail={"source": "rule_reader"},
        ))
    for lang in rr.languages:
        # The rule-reader emits a NORMALIZED ISO code (e.g. "en"); a bare 2-char
        # code matches stray substrings ("...intellig-en-ce..."), so we do NOT
        # try to span-locate it. The deterministic intake pass owns the real
        # language span; on overlap the merge keeps that authoritative span.
        out.append(CandidateConstraint(
            dimension="source.language", value=lang, force=FORCE_PREFER,
            origin=ORIGIN_RULE_READER, spans=[],
            detail={"source": "rule_reader", "no_span": "normalized_iso_code"},
        ))
    if rr.recency:
        out.append(CandidateConstraint(
            dimension="date.recency", value=rr.recency, force=FORCE_PREFER,
            origin=ORIGIN_RULE_READER, spans=_spans_for(prompt, [rr.recency]),
            detail={"source": "rule_reader"},
        ))
    for cov in rr.required_coverage:
        out.append(CandidateConstraint(
            dimension="content.coverage", value=cov, force=FORCE_PREFER,
            origin=ORIGIN_RULE_READER, spans=_spans_for(prompt, [cov]),
            detail={"source": "rule_reader"},
        ))
    for exc in rr.exclusions:
        out.append(CandidateConstraint(
            dimension="content.exclusion", value=exc, force=FORCE_HARD,
            origin=ORIGIN_RULE_READER, spans=_spans_for(prompt, [exc]),
            detail={"source": "rule_reader", "kind": "exclusion"},
        ))
    if rr.format:
        out.append(CandidateConstraint(
            dimension="deliverable.format", value=rr.format, force=FORCE_PREFER,
            origin=ORIGIN_RULE_READER, spans=_spans_for(prompt, [rr.format]),
            detail={"source": "rule_reader"},
        ))
    if rr.length:
        out.append(CandidateConstraint(
            dimension="deliverable.length", value=rr.length, force=FORCE_PREFER,
            origin=ORIGIN_RULE_READER, spans=_spans_for(prompt, [rr.length]),
            detail={"source": "rule_reader"},
        ))
    if rr.tone:
        out.append(CandidateConstraint(
            dimension="rhetoric.tone", value=rr.tone, force=FORCE_PREFER,
            origin=ORIGIN_RULE_READER, spans=_spans_for(prompt, [rr.tone]),
            detail={"source": "rule_reader"},
        ))

    return out


# ---------------------------------------------------------------------------
# Reconciliation (deterministic wins on overlap; rule-reader fills gaps)
# ---------------------------------------------------------------------------

# Language and source-type values normalize the same way in both sources
# (constraint_extractor and intake both emit ISO lang codes and
# ``journal_article`` etc.), so a plain casefold key is a sound overlap test.
def _overlap_key(c: CandidateConstraint) -> tuple[str, str]:
    return (c.dimension, (c.value or "").strip().casefold())


def _merge_pair(
    det: CandidateConstraint, rr: CandidateConstraint
) -> CandidateConstraint:
    """Deterministic candidate wins on span + force; record that both agreed and
    union the spans (the rule-reader may have located a span the regex path
    didn't, and vice-versa)."""
    merged_spans = list(det.spans)
    seen = {(s.start, s.end) for s in merged_spans}
    for s in rr.spans:
        if (s.start, s.end) not in seen:
            merged_spans.append(s)
            seen.add((s.start, s.end))
    detail = dict(det.detail)
    detail["also_seen_by"] = "rule_reader"
    detail["rule_reader_detail"] = dict(rr.detail)
    return CandidateConstraint(
        dimension=det.dimension,
        value=det.value,            # deterministic value is authoritative
        force=det.force,            # deterministic force is authoritative
        origin=ORIGIN_MERGED,
        spans=merged_spans,
        detail=detail,
    )


def reconcile_candidates(
    prompt: str,
    *,
    rule_reader: "Constraints | dict[str, Any] | None" = None,
    ontology: "dict[str, Any] | None" = None,
) -> list[CandidateConstraint]:
    """Reconcile the deterministic intake extractors with the rule-reader.

    Parameters
    ----------
    prompt:
        The raw task prompt (spans are recovered against this exact text).
    rule_reader:
        The ported adversarial rule-reader result — a
        :class:`~...instruction.constraint_extractor.Constraints`, its
        ``to_dict()`` form, or ``None`` to reconcile the intake extractors
        alone. This adapter NEVER runs the live rule-reader itself; the caller
        supplies an already-computed result (keeping the adapter offline/pure).
    ontology:
        Optional scope ontology override forwarded to
        ``extract_scope_constraints_regex`` (tests inject a fixture; production
        loads the default).

    Returns
    -------
    list[CandidateConstraint]
        High-recall candidates with exact spans + origin. Deterministic
        candidates come first (they win on overlap); rule-reader-only candidates
        follow. This is a candidate list, NOT a pinned contract.
    """
    prompt = prompt or ""

    # --- deterministic pass (the three champion intake regex extractors) ---
    uc = extract_constraints_regex(prompt)
    slots = extract_instruction_slots_regex(prompt)
    try:
        sc = extract_scope_constraints_regex(prompt, ontology=ontology)
    except Exception:  # noqa: BLE001 — fail-open: no scope facets on ontology miss
        sc = ScopeConstraints(source="regex")

    deterministic: list[CandidateConstraint] = []
    deterministic.extend(_from_user_constraints(prompt, uc))
    deterministic.extend(_from_instruction_slots(prompt, slots))
    deterministic.extend(_from_scope_constraints(prompt, sc))

    # --- rule-reader pass (gap-filler) ---
    rr_obj: Optional[Constraints] = None
    if isinstance(rule_reader, Constraints):
        rr_obj = rule_reader
    elif isinstance(rule_reader, dict):
        rr_obj = _constraints_from_dict(rule_reader)
    rule_candidates = _from_rule_reader(prompt, rr_obj) if rr_obj is not None else []

    # --- reconcile: deterministic wins on overlap; rule-reader fills gaps ---
    by_key: dict[tuple[str, str], CandidateConstraint] = {}
    ordered: list[CandidateConstraint] = []
    for c in deterministic:
        key = _overlap_key(c)
        by_key[key] = c
        ordered.append(c)

    for rc in rule_candidates:
        key = _overlap_key(rc)
        existing = by_key.get(key)
        if existing is not None and existing.origin != ORIGIN_RULE_READER:
            # overlap -> merge into the deterministic winner in place
            idx = ordered.index(existing)
            merged = _merge_pair(existing, rc)
            ordered[idx] = merged
            by_key[key] = merged
        elif existing is None:
            by_key[key] = rc
            ordered.append(rc)
        # (a rule-reader/rule-reader dup collapses onto the first)

    return ordered


def _constraints_from_dict(d: dict[str, Any]) -> Constraints:
    """Rebuild a :class:`Constraints` from its ``to_dict()`` form (tolerant)."""
    def _list(v: Any) -> list[str]:
        return [str(x) for x in v] if isinstance(v, (list, tuple)) else ([] if v in (None, "") else [str(v)])

    def _opt(v: Any) -> Optional[str]:
        return None if v in (None, "") else str(v)

    return Constraints(
        source_types=_list(d.get("source_types")),
        languages=_list(d.get("languages")),
        recency=_opt(d.get("recency")),
        required_coverage=_list(d.get("required_coverage")),
        exclusions=_list(d.get("exclusions")),
        format=_opt(d.get("format")),
        length=_opt(d.get("length")),
        tone=_opt(d.get("tone")),
    )
