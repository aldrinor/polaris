"""V30 Phase-2 M-63 — contract-driven section runner.

Replaces legacy per-section LLM prompts with M-58 slot-bound
prose for entities that have a FrameRow. Returns the same
`SectionResult` shape as legacy `_run_section` so downstream
assembly is unchanged.

## Architecture (per Phase-2 plan M-63 Fix #1)

- SECTION-level SectionResult, NOT slot-level. Each contract
  section (Efficacy, Mechanism, Regulatory for clinical)
  becomes ONE SectionResult whose verified_text concatenates
  `### {subsection_title}` headings + M-58 body prose per
  slot.
- Multi-entity slots render N blocks, each with its own
  `[bound_ev_id]` citation.
- Gap rows skip the LLM via `compose_gap_payload`.
- Non-gap rows call `build_slot_fill_prompt` → LLM → JSON →
  `parse_slot_fill_response` (raises on fabrication).
- Contract entity ids are registered into `evidence_pool` keyed
  by entity_id so the generalized citation-rewrite regex
  (M-63 Fix #3) resolves `[surpass_2_primary]` markers.

## Dispatch

`ContractSectionPlanExt` subclasses `SectionPlan`. When the
legacy orchestration loop sees an instance, it calls
`_run_contract_section(plan, ...)` instead of the legacy
`_run_section`. This is how `generate_multi_section_report`
routes contract vs legacy prose.

## No legacy overlap

- M-41c (under-framed trial sentences) is no-op by construction:
  body sentences carry `field: value [id].` format, no trial
  short-names. M-41c keys on short-names.
- M-44 (primary-citation validator) passes trivially: every
  sentence cites the bound ev_id.
- M-50 per-trial subsection generator is SKIPPED for entities
  whose anchor maps to a contract slot (integration layer
  enforces this).
"""
from __future__ import annotations

import asyncio
import logging
import os
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

# I-run11-010 (#1056, S2): minimum direct_quote length (chars) for a frame row to carry a verifiable
# citation span. A METADATA_ONLY row below this is routed to gap disclosure (LAW VI: env-overridable).
_MIN_VERIFIABLE_SPAN_CHARS = int(os.getenv("PG_MIN_VERIFIABLE_SPAN_CHARS", "50"))

from ..nodes.contract_outline import ContractSectionPlan, ContractSlotPlan
from ..nodes.report_contract import RequiredEntity
from ..retrieval.frame_fetcher import FrameRow, ProvenanceClass
from .slot_fill import (
    SlotFillParseError,
    SlotFillPayload,
    build_slot_fill_prompt,
    build_slot_narrative_prompt,
    compose_gap_payload,
    parse_slot_fill_response,
    render_slot_prose,
)

if TYPE_CHECKING:
    from .multi_section_generator import SectionPlan, SectionResult

logger = logging.getLogger("polaris_graph.contract_section_runner")


# I-faith-001 Fix A: failure_reasons prefixes that mark a NUMERIC drop.
# A sentence dropped for one of these reasons is a numeric fabrication
# (a number/integer not present in the cited span) and must NEVER be
# laundered back by the M-69 Fix #4 contract-entity rescue. The rescue
# exists only to undo content-overlap false-drops on verbatim M-58 slot
# prose. `failure_reasons` strings are "reason:entity[:detail]" — Fix D
# appends a ":missing=[...]" detail to the integer reason, so the prefix
# is extracted via split(":", 1)[0] to stay match-safe.
_NUMERIC_DROP_PREFIXES: frozenset[str] = frozenset({
    "number_not_in_any_cited_span",
    "no_integer_overlap_any_cited_span",
})

# I-faith-001 Fix A refinement (Codex gate P1): a deterministic gap-disclosure
# ("<field>: not extractable from available primary content") is an HONEST
# disclosure, never a numeric CLAIM. A digit embedded in the field LABEL
# (e.g. "Baseline HbA1c", "COVID-19", "T2 diabetes") must NOT make it look
# like a numeric fabrication and strip its rescue eligibility -> the honest
# disclosure would vanish from a partially-rendered slot. Such disclosures
# are always rescue-eligible. (Real narrative numeric fabrications are
# already rescue-INELIGIBLE via Fix B's allow_rescue=False narrative stream,
# independent of this guard.)
_GAP_DISCLOSURE_MARKER = "not extractable from available primary content"

# I-deepfix-001 Wave-3 PART 2 ARM B (#1344): the DEGRADED-VERIFY honest disclosure
# (``verified_compose._degraded_verify_disclosure`` — a judge-outage-emptied basket)
# is ALSO a disclosure placeholder, NOT substantive verified prose. This sentinel
# phrase is produced ONLY by that ARM-B-ON path, so recognizing it is inert when
# PG_DEGRADED_VERIFY_DISCLOSURE is OFF (no text ever carries it). Recognizing it keeps
# the frame_coverage honesty override from mis-scoring the disclosure as substantive
# prose or as a numeric fabrication (the label carries a count digit).
_DEGRADED_VERIFY_DISCLOSURE_MARKER = "entailment verification was unavailable this run"


def _is_gap_disclosure_sentence(text: Any) -> bool:
    """Shared predicate (single source of truth): True iff a sentence is a
    disclosure placeholder rather than SUBSTANTIVE verified prose — either the
    deterministic gap-disclosure ("<field>: not extractable from available primary
    content") OR the I-deepfix-001 Wave-3 ARM B degraded-verify disclosure
    ("verification incomplete: ... entailment verification was unavailable this run").

    I-ready-017 FX-07b leg-2 (#1111, root-cause design P2): centralizing this on
    `_GAP_DISCLOSURE_MARKER` so the marker cannot drift and silently let a
    placeholder count as substantive prose in the frame_coverage honesty
    override (the Class-B placeholder-kept escape).
    """
    lowered = str(text or "").lower()
    return (
        _GAP_DISCLOSURE_MARKER in lowered
        or _DEGRADED_VERIFY_DISCLOSURE_MARKER in lowered
    )


def _drop_is_numeric(sv: Any) -> bool:
    """True iff a dropped SentenceVerification failed for a NUMERIC reason
    AND is not a deterministic gap-disclosure.

    Inspects the `failure_reasons` LIST (there is no scalar drop_reason)
    and returns True if ANY reason's prefix (the text before the first
    ':') is a numeric-failure prefix. Used by the M-69 rescue loop to
    exclude numeric fabrications from rescue (I-faith-001 Fix A). Gap-
    disclosure sentences are exempt (Codex P1): an embedded label digit
    must not block their rescue.
    """
    sentence = str(getattr(sv, "sentence", "") or "")
    if _is_gap_disclosure_sentence(sentence):
        return False
    failure_reasons = getattr(sv, "failure_reasons", None) or []
    return any(
        str(reason).split(":", 1)[0] in _NUMERIC_DROP_PREFIXES
        for reason in failure_reasons
    )


def _verify_one_stream(
    *,
    raw_draft: str,
    evidence_pool: dict[str, dict[str, Any]],
    contract_entity_ids: set[str],
    rewrite_fn: Any,
    strict_verify_fn: Any,
    allow_rescue: bool,
    stream_label: str,
) -> tuple[list[Any], list[Any], list[Any], int, str]:
    """Rewrite + strict-verify ONE provenance stream, optionally applying
    the M-69 contract-entity rescue (I-faith-001 Fix B — stream separation).

    The DETERMINISTIC stream (M-58 / M-70 verbatim-guarded slot prose) is
    rescue-ELIGIBLE: ``allow_rescue=True`` runs the M-69 Fix #4 rescue with
    the Fix A `_drop_is_numeric` guard, restoring content-overlap false-drops
    while never laundering numeric fabrications.

    The NARRATIVE stream (free-form `build_slot_narrative_prompt` LLM
    paragraph) is rescue-INELIGIBLE: ``allow_rescue=False`` keeps EVERY
    dropped sentence dropped, so a narrative sentence that fails
    `verify_sentence_provenance` is never restored. This is the structural
    fix that closes the run-9 leak: the rescue blanket no longer covers the
    fabrication-prone stream.

    Returns:
        kept_sentences:   verified sentences (+ rescued, if allow_rescue)
        rescued:          the rescued SVs (empty when allow_rescue is False)
        dropped_final:    dropped SVs AFTER removing any rescued ones
        total_in:         report.total_in (for the kept/dropped math)
        rewritten_draft:  the span-token-rewritten draft for this stream

    An empty `raw_draft` short-circuits to all-empty results (no rewrite /
    verify call), which is the identical no-op behavior the disabled /
    no-narrative case produced pre-Fix-B.
    """
    if not raw_draft:
        return [], [], [], 0, ""

    # Rewrite citation markers to span tokens (M-63 Fix #3 generalized
    # regex picks up contract entity ids registered into evidence_pool by
    # the integration layer).
    rewritten_draft, _converted, _unverifiable = rewrite_fn(
        raw_draft, evidence_pool,
    )

    # Strict verify — every deterministic sentence is `Field: value [#ev:...]`
    # and the span comes from FrameRow.direct_quote.
    report = strict_verify_fn(rewritten_draft, evidence_pool)
    kept_sentences = list(getattr(report, "kept_sentences", []) or [])
    dropped_sentences = list(getattr(report, "dropped_sentences", []) or [])
    total_in = int(getattr(report, "total_in", 0) or 0)

    rescued: list[Any] = []
    if allow_rescue:
        # M-69 Fix #4 rescue (deterministic stream only). Restore a dropped
        # sentence iff its primary token resolves to a contract entity_id
        # AND it did NOT drop for a numeric reason (Fix A). The legitimate
        # content-overlap "not extractable" gap-disclosures (drop for
        # no_content_word_overlap, not numeric) remain rescue-eligible.
        for sv in dropped_sentences:
            toks = getattr(sv, "tokens", None) or []
            if not (toks and toks[0].evidence_id in contract_entity_ids):
                continue
            if _drop_is_numeric(sv):
                # Numeric fabrication — never rescue.
                continue
            rescued.append(sv)
        if rescued:
            logger.info(
                "[m63] M-69 Fix #4 (%s stream): rescued %d "
                "strict_verify-dropped contract sentences "
                "(M-58 already verified verbatim)",
                stream_label, len(rescued),
            )
            kept_sentences.extend(rescued)

    rescued_ids = {id(sv) for sv in rescued}
    dropped_final = [
        sv for sv in dropped_sentences if id(sv) not in rescued_ids
    ]
    return kept_sentences, rescued, dropped_final, total_in, rewritten_draft


@dataclass
class ContractSectionPlanExt:
    """Extended section plan carrying the contract info needed
    to dispatch to `_run_contract_section`. Mirrors
    `SectionPlan`'s public fields so existing orchestration
    code treats it as a drop-in via duck-typing.

    Codex pass-1 Q2 answer: dedicated dispatch type, not a
    sentinel field on legacy `SectionPlan`. This preserves
    contract invariants (slots, frame_rows_by_entity,
    contract_entities_by_id) explicitly.

    Named distinct from M-57's `ContractSectionPlan` per Codex
    pass-2 new issue #3.
    """

    title: str                              # SectionPlan field
    focus: str                              # SectionPlan field
    ev_ids: list[str]                       # SectionPlan field
    # M-63 additions:
    slots: tuple[ContractSlotPlan, ...]
    frame_rows_by_entity: dict[str, FrameRow]
    contract_entities_by_id: dict[str, RequiredEntity]
    research_question: str


def register_frame_rows_into_evidence_pool(
    evidence_pool: dict[str, dict[str, Any]],
    frame_rows: tuple[FrameRow, ...],
) -> None:
    """Register each FrameRow into `evidence_pool` keyed by
    entity_id so the generalized citation-rewrite regex
    (M-63 Fix #3) can resolve `[entity_id]` markers via
    `evidence_pool.get(entity_id)`.

    In-place mutation. Each synthesized evidence_pool entry carries:
      - evidence_id: entity_id (what the rewriter expects)
      - direct_quote: FrameRow.direct_quote (what strict_verify
        compares against)
      - url: FrameRow.oa_pdf_url or FrameRow.url (for citation
        resolution)
      - title, authors, journal, year: FrameRow metadata
      - v30_frame_row: True (marker for this path)

    Codex M-63 REJECT Medium 3 namespace-collision guard:

    Contract entity ids are validated at M-54 load time to NOT
    match the live-retrieval `^ev_\\d+$` pattern. That's the first
    line of defense. This registration path adds defense-in-depth:
    if the incoming evidence_pool already has a row at this key
    AND that row is NOT a v30_frame_row (i.e., it's a live-
    retrieval or legacy-pipeline row), raise rather than clobber.
    A loud error here beats a silent generator misattribution.
    Pre-existing v30_frame_row entries (e.g., from M-61 curator
    completions) may be overwritten — that's the intended
    curator-supplied wins semantics.
    """
    for row in frame_rows:
        existing = evidence_pool.get(row.entity_id)
        if existing is not None and not existing.get("v30_frame_row"):
            raise ValueError(
                f"evidence_pool collision at entity_id={row.entity_id!r}: "
                f"a non-v30 pool row already occupies this key. Contract "
                f"entity ids must not collide with live-retrieval keys. "
                f"M-54 schema validation should have prevented this; "
                f"loader may be out of sync."
            )
        evidence_pool[row.entity_id] = {
            "evidence_id": row.entity_id,
            "direct_quote": row.direct_quote or "",
            "url": row.oa_pdf_url or row.url or "",
            "title": row.title or "",
            "authors": list(row.authors),
            "journal": row.journal or "",
            "year": row.year,
            "doi": row.doi or "",
            "pmid": row.pmid or "",
            "provenance_class": row.provenance_class.value,
            # V30 phase-2 marker
            "v30_frame_row": True,
            "v30_entity_id": row.entity_id,
        }


def _build_not_extractable_payload(
    slot: ContractSlotPlan,
    entity_id: str,
    frame_row: FrameRow,
    required_fields: tuple[str, ...],
) -> SlotFillPayload:
    """Build an all-not_extractable SlotFillPayload for a non-gap
    row where the LLM failed (network error, schema parse error,
    etc.). The payload still cites the bound ev_id so M-59 surfaces
    it as FAIL_MIN_FIELDS (curator-actionable) rather than silently
    dropping the entity.

    Cannot use `compose_gap_payload` — that helper hard-raises on
    non-gap provenance by design (Codex M-58 audit symmetric guard
    against routing bugs).
    """
    from .slot_fill import SlotFieldFill, SlotFillPayload as _SFP
    fills = tuple(
        SlotFieldFill(
            field_name=fname,
            status="not_extractable",
            value=None,
            bound_ev_id=entity_id,
            source_span=None,
        )
        for fname in required_fields
    )
    return _SFP(
        slot_id=slot.slot_id,
        entity_id=entity_id,
        subsection_title=slot.subsection_title,
        bound_ev_id=entity_id,
        fields=fills,
        provenance_class=frame_row.provenance_class.value,
    )


# A1 (iarch006 RC1) — basket fallback. Default ON; byte-identical when no
# basket data is threaded (credibility_analysis None => empty index => no
# corroborators). LAW VI: env-overridable kill switch.
_A1_BASKET_FALLBACK_OFF_VALUES = frozenset({"0", "false", "off", "no", ""})


def _a1_basket_fallback_enabled() -> bool:
    """A1 — True (default) unless PG_A1_BASKET_FALLBACK is set off. Accepts the
    SAME falsey vocabulary as the nearby feature flags (Codex iarch007 P1 #3:
    was `!= "0"` only, which silently ignored `false`/`off`/`no`)."""
    return (
        os.getenv("PG_A1_BASKET_FALLBACK", "1").strip().lower()
        not in _A1_BASKET_FALLBACK_OFF_VALUES
    )


def _frame_row_has_usable_quote(frame_row: FrameRow) -> bool:
    """A1 — True iff a frame row carries a verifiable span (real fetched
    prose), i.e. NOT a shell / gap / metadata-only-empty row. Same floor the
    slot-fill path uses (`_MIN_VERIFIABLE_SPAN_CHARS`)."""
    if frame_row.provenance_class == ProvenanceClass.FRAME_GAP_UNRECOVERABLE:
        return False
    return len((frame_row.direct_quote or "").strip()) >= _MIN_VERIFIABLE_SPAN_CHARS


# FIX 4 (I-deepfix-001 #1344, audit c026) — false-gap K-span fallback.
# The contract-slot emit loop discloses a "curator-actionable gap" whenever
# strict_verify kept ZERO composed sentences for a slot. But the slot's BOUND
# entity may still carry a real, strict_verify-passing span in evidence_pool
# (audit c026: Brynjolfsson [6] carried "+15% worker productivity" / "5,172
# support agents" that were DELETED under a FALSE gap label). This flag renders
# that span VERBATIM with its citation instead of the false gap — RETAIN not
# drop (§-1.3), faithfulness-neutral (a verbatim span is grounded by
# construction and we VERIFY it via the SAME strict_verify path, never assert).
# LAW VI env-overridable; DEFAULT ON (I-deepfix-001 wire+activate wave,
# feedback_wire_activate_core_archive_2026_07_05): the emit loop renders the
# retained verified K-span in place of a FALSE gap. Setting the flag to any
# falsey value (0/false/off/no) restores the byte-identical gap-disclosure path.
_FALSE_GAP_KSPAN_OFF_VALUES = frozenset({"0", "false", "off", "no", ""})

# LAW VI — min alphabetic words for a LEADING line to count as real prose rather
# than page furniture (nav bullets / masthead residue) during K-span body
# reconstruction. A leading bullet/rule line with fewer than this many alpha
# words AND no digit is dropped as chrome; a real numeric/prose line always
# clears it. Env-overridable; ``int(...)`` fails LOUD on a malformed value.
_KSPAN_MIN_PROSE_WORDS = int(os.getenv("PG_CONTRACT_KSPAN_MIN_PROSE_WORDS", "4"))


def _false_gap_kspan_enabled() -> bool:
    """FIX 4 — True (default) unless ``PG_CONTRACT_FALSE_GAP_KSPAN`` is set off.
    Default ON (activated in the I-deepfix-001 wire+activate wave); accepts the
    SAME falsey vocabulary as the nearby feature flags (Codex iarch007 P1 #3: a
    bare ``!= "0"`` silently ignores ``false``/``off``/``no``)."""
    return (
        os.getenv("PG_CONTRACT_FALSE_GAP_KSPAN", "1").strip().lower()
        not in _FALSE_GAP_KSPAN_OFF_VALUES
    )


def _kspan_fallback_body(
    *,
    primary_ev: str,
    evidence_pool: dict[str, dict[str, Any]],
    marker_num: int,
    rewrite_fn: Any,
    strict_verify_fn: Any,
) -> str | None:
    """FIX 4 — if the bound entity has ANY strict_verify-passing span, return a
    body reconstructed from ONLY those passing sentences (markers stripped +
    leading page chrome excluded, single ``[marker_num]`` re-appended) to render
    in place of a false gap; else ``None`` (genuinely no usable span → the caller
    gap-discloses).

    Same grounded-by-construction idiom as ``abstractive_writer``'s K-span: the
    span is fetched primary-source text, so a verbatim restatement carries every
    decimal and full content-word overlap and passes strict_verify. We still run
    the entity's span through the IDENTICAL rewrite → strict_verify path the
    composed body uses (``allow_rescue=False`` — the span must pass on its own
    merits, no rescue laundering), so a non-usable span (empty / metadata-only /
    numeric-only shell) correctly yields ``None``. The faithfulness engine is
    BYTE-UNTOUCHED — this only RE-USES it as the gate."""
    row = evidence_pool.get(primary_ev) or {}
    span = str(row.get("direct_quote") or "").strip()
    if len(span) < _MIN_VERIFIABLE_SPAN_CHARS:
        return None
    # Build the verify draft by attaching the bound-entity marker to EACH
    # sentence of the span (inserted BEFORE the terminal punctuation so the
    # marker stays inside its sentence — a marker AFTER the period splits off
    # as a token-less fragment and every sentence would false-drop as
    # ``no_provenance_token``). Run it through the SAME rewrite→strict_verify
    # machinery the composed body uses; ``kept`` non-empty means the bound
    # entity has AT LEAST ONE strict_verify-passing span.
    from .provenance_generator import split_into_sentences
    _marked: list[str] = []
    for _sent in split_into_sentences(span):
        _sent = _sent.rstrip()
        if not _sent:
            continue
        if _sent[-1] in ".!?":
            _marked.append(f"{_sent[:-1].rstrip()} [{primary_ev}]{_sent[-1]}")
        else:
            _marked.append(f"{_sent} [{primary_ev}]")
    if not _marked:
        return None
    draft = " ".join(_marked)
    kept, _rescued, _dropped, _total, _rewritten = _verify_one_stream(
        raw_draft=draft,
        evidence_pool=evidence_pool,
        contract_entity_ids=set(),
        rewrite_fn=rewrite_fn,
        strict_verify_fn=strict_verify_fn,
        allow_rescue=False,
        stream_label="fix4_false_gap_kspan",
    )
    if not kept:
        return None
    # I-deepfix-001 (#1344) FIX 4 harden: reconstruct the body from ONLY the
    # strict_verify-PASSING sentences' cleaned text — NEVER the raw full span,
    # which dumps the leading page chrome (ToC / nav bullets / masthead) that
    # precedes the real prose. Each rendered sentence individually passed
    # strict_verify, so grounding is preserved; the leading chrome (the one
    # legit hard-drop per §-1.3) is excluded. Return None only when zero
    # sentences leave usable prose after cleaning.
    import re as _re  # noqa: PLC0415 (lazy: zero cost off this fallback path)
    from .chrome_furniture_screen import _alpha_word_count
    # I-deepfix-001 (#1369) FIX A — strip ONLY the EXACT provenance / citation
    # marker LITERALS, never a generic lowercase-word pattern. The prior
    # `\[[a-z0-9_]+\]` alternative removed ANY single lowercase_snake bracket
    # token, so a substantive verified hedge that is a plain lowercase word —
    # [unadjusted], [baseline], [placebo], [crude], [sic], [not adjusted] —
    # was silently deleted AFTER strict_verify passed, ALTERING the verified
    # claim. We now strip exactly: (1) the [#ev:id:start-end] provenance span
    # token, (2) the KNOWN bound entity_id LITERALS for this slot — primary_ev
    # plus every evidence_pool key, i.e. the exact id strings the composer
    # inserts as [entity_id] provenance markers — each regex-escaped, and (3) a
    # pure numeric [N] citation. A real qualifier word is NOT a bound entity_id,
    # so it never matches (2) and SURVIVES. Faithfulness-neutral: this only
    # prevents removal of verified substance.
    _known_marker_ids = {str(primary_ev)}
    _known_marker_ids.update(str(_k) for _k in evidence_pool.keys())
    _id_alt = "|".join(
        _re.escape(_mid)
        for _mid in sorted(_known_marker_ids, key=len, reverse=True)
        if _mid
    )
    _marker_pattern = r"\s*\[#ev:[^\]]*\]|\s*\[\d+\]"  # (1) provenance token + (3) [N] numeric
    if _id_alt:
        _marker_pattern += rf"|\s*\[(?:{_id_alt})\]"   # (2) EXACT bound entity_id literals only
    _marker_re = _re.compile(_marker_pattern)
    _clean_sentences: list[str] = []
    for _sv in kept:
        # (a) strip provenance markers ([entity_id] / [#ev:id:start-end]).
        _demarked = _marker_re.sub("", str(getattr(_sv, "sentence", "") or ""))
        # (b) drop LEADING page-furniture lines (whole-LINE only, never an
        # inline partial strip of a welded claim): a line is furniture iff it
        # is empty OR starts with a bullet/rule glyph AND carries fewer than
        # _KSPAN_MIN_PROSE_WORDS alpha words AND no digit. A real numeric/prose
        # line always clears it and stops the leading-strip.
        _seen_prose = False
        _out_lines: list[str] = []
        for _ln in _demarked.replace("\xad", "").split("\n"):
            _core = _ln.strip()
            if not _seen_prose:
                if not _core:
                    continue
                if (
                    _core[0] in "-*•·|–—"
                    and _alpha_word_count(_core) < _KSPAN_MIN_PROSE_WORDS
                    and not _re.search(r"\d", _core)
                ):
                    continue  # leading furniture line
                _seen_prose = True
            _out_lines.append(_core)
        _residue = " ".join(_l for _l in _out_lines if _l).strip()
        if _residue:
            _clean_sentences.append(_residue)
    if not _clean_sentences:
        return None
    return f"{' '.join(_clean_sentences)}[{marker_num}]"


def _basket_fallback_corroborators_for_slot(
    *,
    slot_entity_ids: list[str],
    cluster_id_by_evidence: dict[str, list[str]] | None,
    basket_supports_by_cluster: dict[str, list[str]],
    evidence_pool: dict[str, dict[str, Any]],
    already_bound: set[str],
) -> list[str]:
    """A1 — same-claim corroborator evidence_ids to re-bind a slot whose
    primary URL(s) came back as fetch-layer SHELLS (A1a routed them to
    METADATA_ONLY/not_extractable, leaving the slot's real case-law / source
    content unbound at ``v30_entity_id: None``).

    Joins via the slot's own bound entity_ids -> ``cluster_id_by_evidence`` ->
    the basket's independently SPAN-VERIFIED (SUPPORTS) members, the IDENTICAL
    faithfulness logic as ``verified_corroborators_for_tokens``:
      - SUPPORTS-only (the verified-origin members, never the advisory
        clustered total);
      - anti-cross-claim — only a token mapping to EXACTLY ONE cluster is
        expanded (a multi-cluster source can't be attributed to ONE claim);
      - a corroborator is kept ONLY if it (a) is not already bound to the slot
        and (b) carries a usable verifiable span in ``evidence_pool``.

    SCOPE NOTE (Codex iarch007 P1 #2): this join is keyed on the slot's bound
    entity_ids. A genuinely UNRECOVERABLE slot — every bound entity is a
    content-less shell that NEVER produced an extracted claim — is, by
    construction, absent from ``cluster_id_by_evidence`` (the claim graph only
    contains entities whose row content yielded an AtomicClaim). For such a
    slot this returns [] and the slot correctly stays a disclosed gap stub.
    Reaching a cluster for a fully-content-less slot would require a
    MANY-cluster linkage (query_origin / section / "same required entity"),
    which is cross-claim and would RELAX the basket's anti-cross-claim
    faithfulness rule — out of bounds. The recoverable case (a slot whose
    frame_row is a shell yet whose pool row clustered via abstract content) DOES
    fire here.

    FAITHFULNESS: this returns CANDIDATES to route through the UNCHANGED
    slot-fill -> strict_verify path. It binds nothing itself, drops nothing,
    relaxes no threshold. The basket carries tier/authority as a WEIGHT only.
    Returns [] when basket data is absent => byte-identical OFF path."""
    if not basket_supports_by_cluster:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for _eid in slot_entity_ids:
        _ccids = (cluster_id_by_evidence or {}).get(_eid, []) or []
        # Anti-cross-claim: only an UNAMBIGUOUS single-cluster source may
        # corroborate (mirrors verified_corroborators_for_tokens).
        if len(_ccids) != 1:
            continue
        for _support_eid in basket_supports_by_cluster.get(_ccids[0], []):
            if _support_eid in seen or _support_eid in already_bound:
                continue
            _pool_row = evidence_pool.get(_support_eid)
            if not _pool_row:
                continue
            # Must carry a real verifiable span — a corroborator that is itself
            # a shell / metadata-only row cannot rescue the slot.
            if len(str(_pool_row.get("direct_quote") or "").strip()) < _MIN_VERIFIABLE_SPAN_CHARS:
                continue
            seen.add(_support_eid)
            out.append(_support_eid)
    return out


def _synth_frame_row_for_corroborator(
    *,
    corroborator_ev_id: str,
    pool_row: dict[str, Any],
    rendering_slot: str,
    entity_type: str,
) -> FrameRow:
    """A1 — wrap a same-claim corroborator's pool row in a minimal OPEN_ACCESS
    FrameRow so it flows through the UNCHANGED ``_fill_one_slot`` -> slot-fill
    -> strict_verify path (no second verify path). The corroborator already
    carries a usable ``direct_quote`` (the caller checked the floor); year is
    coerced to int when present."""
    _year_raw = pool_row.get("year")
    try:
        _year = int(_year_raw) if _year_raw not in (None, "") else None
    except (TypeError, ValueError):
        _year = None
    _authors_raw = pool_row.get("authors") or ()
    _authors = tuple(_authors_raw) if isinstance(_authors_raw, (list, tuple)) else ()
    return FrameRow(
        entity_id=corroborator_ev_id,
        entity_type=entity_type,
        rendering_slot=rendering_slot,
        provenance_class=ProvenanceClass.OPEN_ACCESS,
        direct_quote=str(pool_row.get("direct_quote") or ""),
        quote_source="a1_basket_corroborator",
        doi=(str(pool_row.get("doi")) or None) if pool_row.get("doi") else None,
        pmid=(str(pool_row.get("pmid")) or None) if pool_row.get("pmid") else None,
        oa_pdf_url=None,
        url=(str(pool_row.get("url")) or None) if pool_row.get("url") else None,
        title=(str(pool_row.get("title")) or None) if pool_row.get("title") else None,
        authors=_authors,
        journal=(str(pool_row.get("journal")) or None) if pool_row.get("journal") else None,
        year=_year,
        failure_reason=None,
        retrieval_attempts=(),
        retrieval_timings=(),
    )


def contract_sentence_citation_nums(
    sv: Any,
    tokens: list,
    ev_to_num: dict[str, int],
    *,
    basket_supports_by_cluster: dict[str, list[str]],
    cluster_id_by_evidence: Any,
    evidence_pool: dict[str, dict[str, Any]],
    basket_by_cluster: dict[str, dict[str, Any]],
) -> list[int]:
    """The V30 contract slot-regroup's per-sentence citation-number decision, extracted so the
    benchmark render path's attachment logic is behaviorally testable WITHOUT the async
    LLM-driven ``run_contract_section`` machinery (§-1.4: prove the effect fires in the OUTPUT,
    not that a string is present).

    Returns the ordered list of bibliography numbers attached to THIS sentence:
      * its OWN strict-verified tokens (minus relevance-demoted/refuted eids), then
      * each basket corroborator whose CLAIM-LOCAL span grounds THIS sentence
        (``corroborator_grounds_sentence_via_basket`` — the SAME single decision the legacy
        resolver applies, so a corroborator filtered off S1 can NOT be reattached to S1 via the
        section-wide ``ev_to_num`` it earned on S2). Faithfulness-TIGHTENING; engine untouched.
    OFF path (empty ``basket_supports_by_cluster``) => only own tokens => byte-identical regroup.
    """
    from .provenance_generator import (  # noqa: PLC0415
        verified_corroborators_with_clusters_for_tokens,
        corroborator_grounds_sentence_via_basket,
        _verifier_cleaned_text,
        _citation_nli_purity_enabled,
        _own_token_span_reasserts,
    )

    _demoted_eids = (
        (getattr(sv, "relevance_demoted_eids", None) or frozenset())
        | (getattr(sv, "relevance_refuted_eids", None) or frozenset())
    )
    _corro_claim_text = _verifier_cleaned_text(getattr(sv, "sentence", "") or "")
    used_nums: list[int] = []
    # I-deepfix-001 P2 (#1344): OWN-TOKEN bounds+overlap re-assert on the V30 contract regroup.
    # Gate-B forces THIS path (not the flat resolver body), so the render-time own-token purity
    # re-assert MUST also run here — a withheld bad own token is still registered in
    # ev_to_num / biblio_slice by the resolver (line ~1615), so without this it would be
    # reattached into the SHIPPED slot body and the render-time purity fix would be a no-op on
    # the benchmark path. Mirror the resolver's own-token pass/withhold + minimum-retention guard
    # EXACTLY (``resolve_provenance_to_citations_with_count``): re-assert each own token's stored
    # (start,end) against the CURRENT ``direct_quote`` via the SAME predicate, WITHHOLD its inline
    # [N] on failure (the source STAYS in the bibliography), and never let a sentence go
    # cited->uncited. The withhold DECISION here is deterministic and identical to the resolver's
    # on the same tokens, and the resolver already recorded the purity telemetry on that decision
    # (its discarded flat body) — so we ACT here WITHOUT a second telemetry increment, which also
    # keeps the withheld_own_token count from being inflated by the two paths. OFF (=0) =>
    # ``_own_token_span_reasserts`` skipped => byte-identical legacy own-token regroup.
    _purity_on = _citation_nli_purity_enabled()
    _own_pass: list[int] = []
    _own_withheld: list[int] = []
    for tok in tokens:
        if tok.evidence_id in _demoted_eids:
            continue
        n = ev_to_num.get(tok.evidence_id)
        if n is None:
            continue
        if _purity_on and not _own_token_span_reasserts(
            tok, evidence_pool, _corro_claim_text
        ):
            if n not in _own_withheld:
                _own_withheld.append(n)
        elif n not in _own_pass:
            _own_pass.append(n)
    # MINIMUM-RETENTION GUARD (same as the resolver): never strand a sentence's own support —
    # if EVERY surviving own token would be withheld, KEEP them all (never cited->uncited).
    if _purity_on and _own_withheld and not _own_pass:
        _own_pass = list(_own_withheld)
        _own_withheld = []
    for n in _own_pass:
        if n not in used_nums:
            used_nums.append(n)
    for _corro_eid, _corro_ccid in verified_corroborators_with_clusters_for_tokens(
        [tok.evidence_id for tok in tokens],
        basket_supports_by_cluster=basket_supports_by_cluster,
        cluster_id_by_evidence=cluster_id_by_evidence,
        evidence_pool=evidence_pool,
    ):
        if _corro_eid in _demoted_eids:
            continue
        if not corroborator_grounds_sentence_via_basket(
            _corro_claim_text, _corro_eid, basket_by_cluster,
            selected_cluster_id=_corro_ccid,
        ):
            continue
        n = ev_to_num.get(_corro_eid)
        if n is not None and n not in used_nums:
            used_nums.append(n)
    return used_nums


def _contract_dedup_enabled() -> bool:
    """I-wire-014 (#1336): outer gate for the CONTRACT-section consolidate-keep-all
    dedup. Mirrors the SAME flags the multi_section path's anti-restatement pass
    routes through inside ``fact_dedup.build_groups`` — the literal/Jaccard prose
    seam (``PG_FACT_DEDUP_PROSE``) and the NLI mutual-entailment prose seam
    (``PG_CONSOLIDATION_NLI_PROSE``). DEFAULT-OFF on BOTH => the contract path is
    byte-identical to today. ON => the restatement cluster (e.g. the drb_72 "probability
    of computerisation ... Gaussian process classifier" x8 in Empirical_Displacement) is
    consolidated by KEEP-FIRST-VERBATIM index drops — the primary restatement is kept
    verbatim and redundant occurrences whose citation set is a SUBSET of the survivor's
    are dropped, so every citation of the merged members survives on the kept primary
    (§-1.3 CONSOLIDATE-keep-all); no LLM rewrite/cross-reference is produced. Read here so
    the outer block self-skips with zero side effects when the operator hasn't turned the
    seam on; ``build_groups`` re-reads the same flags internally to decide which prose
    clusterer fires."""

    def _on(name: str) -> bool:
        return os.getenv(name, "0").strip().lower() not in ("", "0", "false", "off", "no")

    return _on("PG_FACT_DEDUP_PROSE") or _on("PG_CONSOLIDATION_NLI_PROSE")


async def _consolidate_contract_section_sentences(
    section_title: str,
    kept_sentences: list[Any],
    evidence_pool: dict[str, dict[str, Any]],
    *,
    strict_verify_fn: Any,
    dedup_llm_callable: Any,
) -> tuple[list[Any], dict[str, Any]]:
    """Consolidate degenerate intra-section restatements on ONE contract section by
    KEEP-FIRST-VERBATIM index drops — no LLM rewrite, no re-verify, faithfulness FROZEN.

    I-wire-014 (#1336 / #4b): the contract path's keystone consolidation. ``kept_sentences``
    are SentenceVerification objects whose ``.sentence`` carries the PRE-resolve
    ``[#ev:id:start-end]`` provenance tokens; they are POSITIONALLY aligned with the section
    sentence list fed to ``fact_dedup.build_groups`` (index i <-> kept_sentences[i]). We run
    the SAME gated prose clusterers the certified multi_section path uses (literal/Jaccard +
    bidirectional-NLI, behind PG_FACT_DEDUP_PROSE / PG_CONSOLIDATION_NLI[_PROSE]) and keep the
    PRIMARY restatement of each cluster VERBATIM (already upstream-verified, so it can never
    fail a re-verify), dropping a redundant by its OCCURRENCE INDEX only when its citation SET
    and numbers are a SUBSET of the primary's. CONSOLIDATE-KEEP-ALL (§-1.3): the kept primary
    already carries every citation + number of every dropped redundant, byte-identical
    duplicates collapse (distinct indexes), and nothing distinct, cited, or numeric is lost.

    ``strict_verify_fn`` and ``dedup_llm_callable`` are accepted for call-site stability but
    are UNUSED on this keep-first-verbatim path (no rewrite is produced, so nothing needs
    re-verification and no LLM is called). The outer ``_contract_dedup_enabled()`` gate
    (default-OFF) governs whether this runs at all.

    Returns (new_kept_sentences, telemetry).
    """

    # Single-section feed. fact_dedup keys by section title; the prose paths
    # cluster WITHIN a section (the NLI path requires m.section == primary.section),
    # so a one-section dict is exactly what consolidates the intra-section restatements.
    # The list is POSITIONALLY aligned with ``kept_sentences`` (index i <-> kept_sentences[i]),
    # which is what makes the index-based drop below correct even for byte-identical duplicates.
    sentence_strs: list[str] = [sv.sentence for sv in kept_sentences]
    sections_for_dedup: dict[str, list[str]] = {section_title: sentence_strs}

    # I-wire-014 #4b (Codex diff-gate iter-2 P1 fix): keep-first-VERBATIM, NO LLM rewrite, drops keyed by
    # OCCURRENCE INDEX — never by sentence STRING. The prior approach (fact_dedup.dedup_pass) ran an LLM
    # cross-ref REWRITE that drifts on the terse contract slot sentences and FAILS strict_verify, so the
    # revert-on-fail fallback reverted EVERY cluster and the degenerate restatements never collapsed
    # ("probability of computerisation" x17 survived). A string-keyed drop ALSO cannot collapse a
    # byte-identical duplicate (dropping the shared string would delete the primary too) — the exact case
    # the operator flagged. ROBUST FIX: use the redundancy GROUPS directly (build_groups = the gated
    # Jaccard + bidirectional-NLI prose clusterers, the SAME clusterers the certified multi_section path
    # uses) and KEEP the PRIMARY restatement VERBATIM (already upstream strict_verify-passed, so no
    # re-verify can ever drop it). DROP a redundant by its list INDEX only when (a) it is in this section,
    # (b) it is NOT the primary's index and is no group's primary slot, and (c) its citation SET is a
    # SUBSET of the primary's AND its numbers are a SUBSET. Because the kept primary already carries every
    # citation + number the dropped redundant had, §-1.3 CONSOLIDATE-KEEP-ALL holds: nothing distinct,
    # cited, or numeric is ever lost, byte-identical duplicates DO collapse (distinct indexes), and there
    # is no rewrite that can fail the faithfulness gate (strict_verify / NLI / 4-role / span UNCHANGED).
    from .fact_dedup import (  # noqa: PLC0415
        build_groups as _build_groups,
        _nli_cite_set as _cite_set,
        _nli_num_set as _num_set,
        _CITATION_TOKEN_RE as _cite_strip_re,
    )

    n_kept = len(kept_sentences)
    groups = _build_groups(sections_for_dedup, section_order=[section_title])
    # Every slot that is SOME group's primary is protected from being dropped, even if a different
    # (cross-path) group lists the same index as a redundant — the verbatim primary must always survive.
    primary_idxs: set[int] = {
        g.primary.index
        for g in groups
        if g.primary.section == section_title and 0 <= g.primary.index < n_kept
    }
    drop_idx: set[int] = set()
    n_groups_used = 0
    for g in groups:
        primary = g.primary
        if primary.section != section_title or not (0 <= primary.index < n_kept):
            continue
        p_cites = _cite_set(primary.sentence)
        p_nums = _num_set(primary.sentence)
        grp_dropped = 0
        for r in g.redundants:
            if (
                r.section == section_title
                and 0 <= r.index < n_kept
                and r.index != primary.index      # never drop the primary's own slot
                and r.index not in primary_idxs   # never drop ANY group's primary slot
                and r.index not in drop_idx       # idempotent
                and _cite_set(r.sentence) <= p_cites   # no citation lost (primary carries them)
                and _num_set(r.sentence) <= p_nums      # no distinct number lost
            ):
                drop_idx.add(r.index)
                grp_dropped += 1
        if grp_dropped:
            n_groups_used += 1

    # I-wire-014 #4b (Codex diff-gate iter-3 P1): build_groups' numeric path emits ONLY CROSS-section
    # groups (fact_dedup.py:891 distinct_sections<2 skip) and the prose/Jaccard + NLI paths skip
    # non-empty numeric signatures, so a sentence carrying a %/$/year restated VERBATIM within ONE
    # contract section forms no group and never collapses (common in clinical/regulatory contract prose).
    # A byte-identical restatement (modulo citation tokens + whitespace/case) is UNAMBIGUOUSLY the same
    # claim — collapse it here under the SAME §-1.3 guard. Survivor = the occurrence carrying the SUPERSET
    # citation set (ties -> earliest); a duplicate occurrence is dropped only when its cite-set is a SUBSET
    # of the survivor's (numbers identical by construction). Identical text => zero false-merge risk, so
    # the architecture's deliberate intra-section numeric DISTINCT-claim protection (which guards DIFFERENT
    # text sharing a number) is untouched. A slot that is any build_groups primary is never dropped here.
    def _exact_norm(_s: str) -> str:
        return " ".join(_cite_strip_re.sub(" ", _s).split()).lower()

    by_norm: dict[str, list[int]] = {}
    for i, sv in enumerate(kept_sentences):
        by_norm.setdefault(_exact_norm(sv.sentence), []).append(i)
    for norm_text, idxs in by_norm.items():
        if not norm_text or len(idxs) < 2:
            continue
        cites_by_idx = {i: _cite_set(kept_sentences[i].sentence) for i in idxs}
        # survivor = largest cite-set, ties broken to the earliest occurrence; never dropped.
        survivor = max(idxs, key=lambda i: (len(cites_by_idx[i]), -i))
        s_cites = cites_by_idx[survivor]
        grp_dropped = 0
        for i in idxs:
            if (
                i != survivor
                and i not in drop_idx
                and i not in primary_idxs       # never drop a verbatim build_groups primary
                and cites_by_idx[i] <= s_cites  # no citation lost (survivor carries them)
            ):
                drop_idx.add(i)
                grp_dropped += 1
        if grp_dropped:
            n_groups_used += 1

    telemetry = {
        "n_groups": n_groups_used,
        "n_redundants": len(drop_idx),
        "n_rewrites_applied": 0,           # keep-first-verbatim => NO LLM rewrite
        "n_rewrites_verified_drop": 0,     # primary kept verbatim => no re-verify can drop it
        "contract_dedup_mode": "keep_first_verbatim",
    }
    if not drop_idx:
        return list(kept_sentences), telemetry
    new_kept = [sv for i, sv in enumerate(kept_sentences) if i not in drop_idx]
    return new_kept, telemetry


async def _fill_one_slot(
    slot: ContractSlotPlan,
    entity_id: str,
    frame_row: FrameRow,
    contract_entity: RequiredEntity,
    research_question: str,
    llm_call: Any,  # async callable(prompt) -> (response_text, in_tok, out_tok)
) -> tuple[SlotFillPayload, int, int]:
    """Produce a SlotFillPayload for one (slot, entity) pair.

    V31 (M-70) dispatch: regulatory entities (FDA, EMA, NICE, HC)
    route through `regulatory_synthesizer` instead of M-58 contract
    slot extraction. Codex strategic review 2026-04-25: M-58's
    verbatim-substring contract is too rigid for page-scale prose
    synthesis; regulatory entities need PROSE synthesis from
    segmented page sections, not field-level extraction.

    Three paths for non-regulatory:
      - gap row (FRAME_GAP_UNRECOVERABLE): `compose_gap_payload`, no LLM call.
      - non-gap row, LLM raises (network / timeout):
        `_build_not_extractable_payload`, fail-loud via M-59 FAIL_MIN_FIELDS.
      - non-gap row, parse raises: `_build_not_extractable_payload`.
      - non-gap row, happy path: `parse_slot_fill_response`.

    Codex M-63 REJECT Blocker 2 fix: non-gap LLM-exception path
    previously called `compose_gap_payload`, which hard-raises on
    non-gap provenance. That turned a planned honest fallback into
    a hard pipeline failure. Now both exception paths route to
    `_build_not_extractable_payload` (see its docstring for rationale).
    """
    required_fields = tuple(contract_entity.required_fields)

    if frame_row.provenance_class == ProvenanceClass.FRAME_GAP_UNRECOVERABLE:
        payload = compose_gap_payload(slot, frame_row, required_fields)
        return payload, 0, 0

    # I-run11-010 (#1056, S2): a METADATA_ONLY frame row with an empty/near-empty direct_quote has no
    # verifiable span to cite — emit an honest all-not_extractable payload (surfaced by M-59 as
    # FAIL_MIN_FIELDS / curator-actionable) WITHOUT calling the LLM on an empty span, so strict_verify
    # is not the ONLY thing standing between an empty authoritatively-cited T1 span and a generated
    # claim. NOT compose_gap_payload — that helper HARD-RAISES on non-gap provenance by design (the
    # M-58 symmetric guard); _build_not_extractable_payload is the sanctioned non-gap skip path. A
    # METADATA_ONLY row that DOES carry a usable quote (>= the verifiable-span floor) still extracts.
    if (
        frame_row.provenance_class == ProvenanceClass.METADATA_ONLY
        and len((frame_row.direct_quote or "").strip()) < _MIN_VERIFIABLE_SPAN_CHARS
    ):
        payload = _build_not_extractable_payload(
            slot, frame_row.entity_id, frame_row, required_fields
        )
        return payload, 0, 0

    # V31 dispatch: regulatory entities go through M-70 prose
    # synthesis instead of M-58 field extraction.
    from .regulatory_synthesizer import (
        is_regulatory_entity,
        build_regulatory_synthesis_prompt,
        parse_regulatory_synthesis_response,
        RegulatorySynthesisError,
        _segment_regulatory_text,
    )
    if is_regulatory_entity(contract_entity):
        segments = _segment_regulatory_text(
            frame_row.direct_quote or "",
            required_fields,
            contract_entity.jurisdiction,
        )
        if not segments:
            # No headings matched — fall back to all not_extractable.
            # M-68 gap-disclosure fallback at the section level
            # will still render the heading + cited gap.
            logger.info(
                "[m70] no regulatory segments matched for "
                "entity_id=%r jurisdiction=%r — degrading to "
                "all not_extractable",
                entity_id, contract_entity.jurisdiction,
            )
            payload = _build_not_extractable_payload(
                slot, entity_id, frame_row, required_fields,
            )
            return payload, 0, 0
        prompt = build_regulatory_synthesis_prompt(
            slot, frame_row, contract_entity, segments,
            research_question,
        )
        try:
            response_text, in_tok, out_tok = await llm_call(prompt)
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "[m70] LLM call failed for entity_id=%r: %s",
                entity_id, exc,
            )
            payload = _build_not_extractable_payload(
                slot, entity_id, frame_row, required_fields,
            )
            return payload, 0, 0
        try:
            payload = parse_regulatory_synthesis_response(
                response_text, slot, frame_row, required_fields,
                segments,
            )
        except RegulatorySynthesisError as exc:
            logger.warning(
                "[m70] regulatory synthesis parse failed for "
                "entity_id=%r: %s", entity_id, exc,
            )
            payload = _build_not_extractable_payload(
                slot, entity_id, frame_row, required_fields,
            )
            return payload, in_tok, out_tok
        return payload, in_tok, out_tok

    # Non-regulatory: legacy M-58 path.
    prompt = build_slot_fill_prompt(
        slot, frame_row, required_fields, research_question,
    )
    try:
        response_text, in_tok, out_tok = await llm_call(prompt)
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "[m63] LLM call failed for entity_id=%r slot_id=%r: %s",
            entity_id, slot.slot_id, exc,
        )
        payload = _build_not_extractable_payload(
            slot, entity_id, frame_row, required_fields,
        )
        return payload, 0, 0

    try:
        payload = parse_slot_fill_response(
            response_text, slot, frame_row, required_fields,
        )
    except SlotFillParseError as exc:
        logger.warning(
            "[m63] slot-fill parse failed for entity_id=%r: %s",
            entity_id, exc,
        )
        payload = _build_not_extractable_payload(
            slot, entity_id, frame_row, required_fields,
        )
        return payload, in_tok, out_tok

    return payload, in_tok, out_tok


async def run_contract_section(
    plan: ContractSectionPlanExt,
    evidence_pool: dict[str, dict[str, Any]],
    *,
    llm_call: Any,
    section_result_cls: Any,  # SectionResult class (injected to avoid
                               # circular import)
    strict_verify_fn: Any,     # strict_verify callable (injected)
    rewrite_fn: Any,           # _rewrite_draft_with_spans (injected)
    credibility_analysis: Any = None,  # I-cred-008b (#1162): advisory per-claim disclosure; None => byte-identical
    # I-arch-004 F32 (#1255): adapter for the per-entity NARRATIVE paragraph call.
    # The narrative is PROSE; `llm_call` is the JSON-only contract-slot adapter
    # (system: "JSON only, no prose") used for slot-fill + regulatory synthesis,
    # whose responses are parsed as JSON. Passing prose through the JSON-only
    # system message gave the model conflicting instructions. When None, fall back
    # to `llm_call` so existing callers stay byte-identical. The faithfulness gate
    # (per-sentence verify in the rescue-INELIGIBLE narrative stream) is unchanged.
    narrative_llm_call: Any = None,
    # I-beatboth-003 (#1280): injectable SURE-RAG relevance judge. Threaded into the
    # resolve_provenance_to_citations call below so the gate's per-citation demotion fires on
    # THIS production render path (the V30 contract slot-regroup, which the §-1.4 harness
    # mocks). None (default) => the live GLM-5.2 judge (gate only ON under PG_RELEVANCE_GATE);
    # with the gate OFF the param is inert => byte-identical.
    relevance_judge_fn: Any = None,
) -> tuple[Any, list[SlotFillPayload]]:
    """Run one contract SECTION. Returns (SectionResult,
    list[SlotFillPayload]). The payloads are threaded back to
    M-64 for real M-59 validation at sweep integration time.

    Legacy-compatible output shape (Codex M-63 REJECT Blocker 3):

    - `verified_text` has `[N]` numbered-citation markers (NOT raw
      `[#ev:...]` span tokens) so report.md renders as a reader
      expects.
    - `biblio_slice` is a populated list of
      {num, evidence_id, url, tier, statement} dicts so the global
      bibliography merge + per-section [N] remap both work.
    - `### {subsection_title}` headings are re-injected AFTER
      strict_verify and citation resolution, grouped by slot, so
      strict_verify never sees heading prose (it would fail the
      content-word overlap check).
    """
    from .provenance_generator import (
        resolve_provenance_to_citations,
        _strip_bogus_ev_markers,
        _bogus_marker_evidence_id,
        _BOGUS_EV_MARKER_RE,
        _RESOLVE_MIN_CONTENT_WORDS,
        _RESOLVE_MIN_PROSE_CHARS,
        # I-arch-005 B6/B8 (#1257): the keystone basket index helpers the V30 contract
        # slot-regroup feeds into the extracted contract_sentence_citation_nums helper (which
        # itself imports verified_corroborators_for_tokens + the I-beatboth-011 P1#1 claim-local
        # corroborator filter), so the per-sentence attachment decision is IDENTICAL to the
        # legacy resolver's.
        _basket_for_biblio,
        build_basket_supports_by_cluster,
    )

    # I-arch-004 F32 (#1255): resolve the narrative-paragraph adapter. None => use
    # the JSON-only `llm_call` (byte-identical to the pre-fix behaviour for callers
    # that do not pass a prose adapter). The production caller threads the prose
    # adapter so the narrative is generated under a prose system message.
    _narrative_call = narrative_llm_call if narrative_llm_call is not None else llm_call

    payloads: list[SlotFillPayload] = []
    total_in_tok = 0
    total_out_tok = 0
    # I-arch-004 F02(c) (#1255): count narrative paragraphs that came back empty so an
    # empty narrative is SURFACED (warned + counted), never silently dropped at the
    # `if narr_text and narr_text.strip()` guard below. Supplementary stream → counted,
    # not fatal (deterministic slot prose remains the primary deliverable).
    _empty_narrative_slots = 0
    all_entity_ids: list[str] = []

    # entity_id -> slot_id so kept sentences can be regrouped into
    # slot blocks after strict_verify.
    entity_to_slot_id: dict[str, str] = {}
    # slot_id -> subsection_title + preserve order from outline
    slot_order: list[str] = []
    slot_subsection: dict[str, str] = {}
    # slot_id -> primary entity_id (first entity in slot.entity_ids).
    # Used by M-68 Fix #1b (Qwen citation_tightness regression):
    # gap-disclosure prose must carry a citation marker pointing
    # at the bound contract entity so Qwen's citation-tightness
    # rule passes. Without this, run-8 release_allowed=False
    # despite all 15 slots rendering (Structure win → release loss).
    slot_primary_entity: dict[str, str] = {}

    # Per-slot raw prose blocks (body-only — no headings) so the
    # text handed to strict_verify has no non-sentence lines.
    #
    # I-faith-001 Fix B (STREAM SEPARATION) + Fix C / regulatory: THREE
    # parallel block lists, one per provenance stream:
    #   - DETERMINISTIC (rescue-ELIGIBLE): the M-58 `render_slot_prose` output.
    #     `parse_slot_fill_response` enforces `value == source_span`, so the
    #     ENTIRE rendered prose is verbatim source text. The M-69 rescue's
    #     premise — undo content-overlap false-drops on legitimately-verbatim
    #     slot prose — holds ONLY for this stream.
    #   - REGULATORY (rescue-INELIGIBLE): the M-70 `render_regulatory_prose`
    #     output. Its parser verbatim-checks ONLY the one `source_span` phrase,
    #     not the LLM-synthesized 50-80 word `value` paragraph — so it has the
    #     SAME fabrication shape as the narrative stream and must NOT be
    #     rescued.
    #   - NARRATIVE (rescue-INELIGIBLE): the free-form
    #     `build_slot_narrative_prompt` LLM paragraph (fabrication-prone — V4
    #     Pro ignored the prompt's "strict_verify will reject hallucinations"
    #     instruction and invented 14%/35%/attrition/CSAT/partial-equilibrium
    #     in run-9).
    # The three streams are verified SEPARATELY downstream so the M-69
    # contract-entity rescue protects ONLY the deterministic stream — the
    # regulatory and narrative sentences must pass `verify_sentence_provenance`
    # on their own with NO rescue. Keeping them split here (rather than tagging
    # a joined draft) means stream origin is DEFINITIONAL — which pass produced
    # the kept sentence — with no fingerprint collision or sentence-split-seam
    # risk.
    raw_body_blocks: list[str] = []           # deterministic stream
    regulatory_body_blocks: list[str] = []    # M-70 regulatory stream
    narrative_body_blocks: list[str] = []     # narrative stream

    # I-ready-017 FX-07b leg-2 (#1111, root-cause design): TOKEN-INDEPENDENT
    # per-entity count of SUBSTANTIVE drafted fields (status=="extracted"),
    # captured during generation BEFORE _rewrite_draft_with_spans can strip an
    # unspannable marker. This is the signal the frame_coverage honesty override
    # uses to tell "the generator drafted real content that strict_verify then
    # dropped" (engineer/pipeline fault) apart from "the generator only had
    # not-extractable placeholders to emit" (curator gap) — closing the Class-A
    # (metadata_only/empty-quote) escape where the dropped disclosure sentences
    # carry no [#ev:] token and were thus invisible to token-counted metrics.
    _substantive_drafted_by_entity: dict[str, int] = {}

    # A1 (iarch006 RC1) — HOISTED basket index for the slot-level fallback.
    # The same per-cluster SUPPORTS index the B6/B8 inline render uses below is
    # built ONCE here so the slot loop can re-bind a SHELL slot to same-claim
    # corroborators BEFORE verification. Reads ONLY credibility_analysis (no
    # loop dependency); None / OFF => empty index => no fallback, byte-identical.
    _baskets = getattr(credibility_analysis, "baskets", None)
    _cluster_id_by_evidence = getattr(
        credibility_analysis, "cluster_id_by_evidence", None
    )
    _carry_baskets = (
        _baskets is not None and _cluster_id_by_evidence is not None
    )
    _basket_supports_by_cluster: dict[str, list[str]] = {}
    # I-beatboth-011 P1#1: hoist the per-cluster PROJECTED basket map to function scope (default
    # empty) so the V30 slot-regroup below can ground each corroborator against its CLAIM-LOCAL
    # span via corroborator_grounds_sentence_via_basket — the SAME anti-mis-attribution filter
    # the legacy resolver applies. On the OFF path it stays {} and the corro loop never fires
    # (empty _basket_supports_by_cluster => no corroborators) => byte-identical regroup.
    _basket_by_cluster: dict[str, dict[str, Any]] = {}
    if _carry_baskets:
        for _basket in (_baskets or []):
            _ccid = str(getattr(_basket, "claim_cluster_id", "") or "")
            if _ccid:
                _basket_by_cluster[_ccid] = _basket_for_biblio(_basket)
        _basket_supports_by_cluster = build_basket_supports_by_cluster(
            _basket_by_cluster
        )
    _a1_fallback_on = _a1_basket_fallback_enabled()

    for slot in plan.slots:
        if not slot.entity_ids:
            # Defensive: outline compiler shouldn't emit empty slots,
            # but guard anyway.
            continue

        slot_order.append(slot.slot_id)
        slot_subsection[slot.slot_id] = slot.subsection_title
        slot_primary_entity[slot.slot_id] = slot.entity_ids[0]

        # I-faith-001 Fix B / Fix C: per-slot prose split by provenance stream.
        slot_det_prose: list[str] = []       # deterministic (M-58 verbatim)
        slot_reg_prose: list[str] = []       # M-70 regulatory LLM-synthesized
        slot_narrative_prose: list[str] = []  # narrative LLM paragraph
        for entity_id in slot.entity_ids:
            all_entity_ids.append(entity_id)
            entity_to_slot_id[entity_id] = slot.slot_id
            frame_row = plan.frame_rows_by_entity.get(entity_id)
            contract_entity = plan.contract_entities_by_id.get(entity_id)

            if frame_row is None or contract_entity is None:
                # Pipeline fault — shouldn't happen given M-57
                # validates parallelism. Skip silently; M-59 will
                # surface the missing entity as FAIL_MISSING_PAYLOAD.
                logger.warning(
                    "[m63] pipeline fault: entity_id=%r missing "
                    "frame_row=%s or contract_entity=%s",
                    entity_id,
                    frame_row is None,
                    contract_entity is None,
                )
                continue

            payload, in_tok, out_tok = await _fill_one_slot(
                slot=slot,
                entity_id=entity_id,
                frame_row=frame_row,
                contract_entity=contract_entity,
                research_question=plan.research_question,
                llm_call=llm_call,
            )
            total_in_tok += in_tok
            total_out_tok += out_tok
            payloads.append(payload)

            # V31 dispatch: regulatory entities use prose render
            # (multi-sentence paragraphs per field), not the
            # M-58 `Field: value [id].` slot prose.
            #
            # I-faith-001 Fix C / regulatory classification: M-70
            # `render_regulatory_prose` emits the LLM-SYNTHESIZED
            # `field.value` (a 50-80 word paragraph). Its parser
            # (`parse_regulatory_synthesis_response`) verbatim-checks ONLY the
            # one `source_span` PHRASE against the segment — NOT the whole
            # prose value — so a regulatory paragraph can carry LLM-introduced
            # connective/qualitative content beyond the single verified phrase.
            # That is the SAME fabrication shape as the free-form narrative
            # stream, and UNLIKE the M-58 deterministic stream where
            # `parse_slot_fill_response` enforces `value == source_span` (the
            # entire rendered prose is verbatim source text). The M-69
            # contract-entity rescue's premise — "undo content-overlap
            # false-drops on legitimately-VERBATIM slot prose" — therefore does
            # NOT hold for regulatory prose. Route it to the rescue-INELIGIBLE
            # `slot_reg_prose` stream so a regulatory sentence that fails
            # `verify_sentence_provenance` is never laundered back into `kept`.
            from .regulatory_synthesizer import (
                is_regulatory_entity,
                render_regulatory_prose,
            )
            if is_regulatory_entity(contract_entity):
                # Regulatory stream — rescue-INELIGIBLE (LLM-synthesized prose,
                # only the source_span phrase is verbatim-verified).
                slot_reg_prose.append(render_regulatory_prose(payload))
            else:
                # Deterministic stream: M-58 verbatim-substring-guarded prose
                # (`parse_slot_fill_response` enforces value == source_span).
                # Rescue-eligible.
                slot_det_prose.append(render_slot_prose(payload))

            # v1.1 A.1 option 4c (2026-04-30): two-tier rendering.
            # Append an LLM-generated 200-300w narrative paragraph
            # FROM THE SAME PAYLOAD. Preserves M-58 frame-coverage
            # manifest + audit trail (the deterministic prose
            # above stays intact) AND adds narrative depth to
            # close BEAT-BOTH on narrative_length +
            # contradiction_handling_grammar.
            #
            # Rollback: PG_USE_NARRATIVE_PARAGRAPH=0 disables.
            # Default ON.
            #
            # I-faith-001 Fix B: the narrative paragraph goes into the
            # SEPARATE narrative stream (`slot_narrative_prose`), which is
            # verified with NO M-69 rescue. Pre-Fix-B this prose was joined
            # with the deterministic slot prose before verify, so the
            # contract-entity rescue laundered fabricated narrative sentences
            # (14%/35%/attrition) back into `kept` — the run-9 leak. Now a
            # narrative sentence that fails `verify_sentence_provenance` drops
            # for good and never reaches the rescue loop.
            #
            # v1.1 A.1 4c v3: also enable narrative for regulatory
            # entities — render_regulatory_prose already gives a
            # multi-sentence paragraph but it's still ~80-120 words
            # per slot; competitors integrate regulatory context
            # into 250+ word narrative blocks. Adds the LLM
            # narrative paragraph alongside the existing
            # render_regulatory_prose output (two-tier).
            #
            # Gap payloads still skipped (no extracted fields).
            import os as _os
            narrative_enabled = (
                _os.environ.get("PG_USE_NARRATIVE_PARAGRAPH", "1") != "0"
            )
            has_extracted = any(
                f.status == "extracted" for f in payload.fields
            )
            # I-ready-017 FX-07b leg-2 (#1111): record token-independent
            # substantive-drafted count per entity (extracted fields become real
            # prose; not_extractable fields are disclosure placeholders). Summed
            # across this entity's payload(s) in the slot.
            _substantive_drafted_by_entity[entity_id] = (
                _substantive_drafted_by_entity.get(entity_id, 0)
                + sum(1 for f in payload.fields if f.status == "extracted")
            )
            if narrative_enabled and has_extracted:
                narr_prompt = build_slot_narrative_prompt(
                    payload,
                    subsection_title=slot.subsection_title,
                    research_question=plan.research_question,
                )
                if narr_prompt:
                    try:
                        # I-arch-004 F32 (#1255): the narrative paragraph is PROSE
                        # — route it through the prose adapter (`_narrative_call`),
                        # NOT the JSON-only `llm_call` used for slot-fill / regulatory
                        # synthesis. Falls back to `llm_call` when no prose adapter
                        # was threaded (byte-identical for legacy callers).
                        narr_text, narr_in, narr_out = await _narrative_call(
                            narr_prompt,
                        )
                        total_in_tok += narr_in
                        total_out_tok += narr_out
                        if narr_text and narr_text.strip():
                            # Narrative stream — rescue-INELIGIBLE (Fix B).
                            slot_narrative_prose.append(narr_text.strip())
                        else:
                            # I-arch-004 F02(c) (#1255): do NOT silently drop an empty
                            # narrative. Pre-fix, an empty `narr_text` (the degenerate
                            # blank-completion proximate cause — the LLM produced no
                            # narrative after consuming wall-clock) fell through this guard
                            # INVISIBLY: no log, no counter, the gap untraceable. Surface it
                            # loud + count it so A1's gap-stub / a re-run handles it visibly.
                            # The narrative is SUPPLEMENTARY (the deterministic slot prose is
                            # the primary deliverable), so this does NOT hard-fail the
                            # section — a blank narrative must not regress a section whose
                            # deterministic stream is fine.
                            _empty_narrative_slots += 1
                            logger.warning(
                                "[m63] I-arch-004 F02(c): empty narrative paragraph for "
                                "slot %r (entity_id=%r) — surfaced, not silently dropped "
                                "(deterministic slot prose unaffected).",
                                slot.slot_id, entity_id,
                            )
                    except Exception as exc:
                        logger.warning(
                            "[m63] narrative-paragraph LLM call "
                            "failed for slot %r: %s",
                            slot.slot_id, exc,
                        )

        # A1 (iarch006 RC1) — BASKET FALLBACK. Fire ONLY when this slot's bound
        # entities all came back as fetch-layer SHELLS (A1a routed the primary
        # URLs to METADATA_ONLY/not_extractable, so the deterministic + regulatory
        # streams are EMPTY) — the exact Q90 failure where ev_323/388/390 sat in
        # the pool unbound (v30_entity_id: None). Re-bind the slot to same-claim
        # corroborators via the EXISTING basket machinery and route each through
        # the UNCHANGED `_fill_one_slot` -> slot-fill -> strict_verify path. The
        # gap stub still renders downstream (M-68 Fix #1) when no corroborator
        # yields verified prose. OFF / no-basket => no corroborators => byte-
        # identical. Never drops, never relaxes a threshold.
        _slot_has_real_prose = bool(slot_det_prose or slot_reg_prose)
        _slot_frame_rows_all_shell = all(
            (plan.frame_rows_by_entity.get(eid) is None)
            or (not _frame_row_has_usable_quote(plan.frame_rows_by_entity[eid]))
            for eid in slot.entity_ids
        )
        if (
            _a1_fallback_on
            and not _slot_has_real_prose
            and _slot_frame_rows_all_shell
            and _basket_supports_by_cluster
        ):
            _corro_ids = _basket_fallback_corroborators_for_slot(
                slot_entity_ids=list(slot.entity_ids),
                cluster_id_by_evidence=_cluster_id_by_evidence,
                basket_supports_by_cluster=_basket_supports_by_cluster,
                evidence_pool=evidence_pool,
                already_bound=set(slot.entity_ids),
            )
            for _corro_eid in _corro_ids:
                _pool_row = evidence_pool.get(_corro_eid) or {}
                # Reuse the slot's contract entity (same required_fields / claim)
                # — the corroborator backs the SAME claim cluster, so the slot's
                # field contract applies. Skip if the slot has no contract entity.
                _primary_eid = slot.entity_ids[0]
                _contract_entity = plan.contract_entities_by_id.get(_primary_eid)
                if _contract_entity is None:
                    continue
                _synth_row = _synth_frame_row_for_corroborator(
                    corroborator_ev_id=_corro_eid,
                    pool_row=_pool_row,
                    rendering_slot=slot.slot_id,
                    # RequiredEntity carries `type` (the raw YAML field); the
                    # synthetic row's entity_type is metadata only (strict_verify
                    # keys on direct_quote/spans, not entity_type).
                    entity_type=str(getattr(_contract_entity, "type", "") or ""),
                )
                # Register the corroborator's entity_id -> slot so the post-verify
                # regroup buckets its kept sentences into THIS slot. Also map into
                # the evidence_pool already done upstream (the row exists there).
                entity_to_slot_id[_corro_eid] = slot.slot_id
                all_entity_ids.append(_corro_eid)
                logger.info(
                    "[m63] A1 basket fallback: slot %r shell — re-binding "
                    "same-claim corroborator ev=%s (routes through unchanged "
                    "strict_verify)", slot.slot_id, _corro_eid,
                )
                _c_payload, _c_in, _c_out = await _fill_one_slot(
                    slot=slot,
                    entity_id=_corro_eid,
                    frame_row=_synth_row,
                    contract_entity=_contract_entity,
                    research_question=plan.research_question,
                    llm_call=llm_call,
                )
                total_in_tok += _c_in
                total_out_tok += _c_out
                payloads.append(_c_payload)
                from .regulatory_synthesizer import (
                    is_regulatory_entity as _is_reg,
                    render_regulatory_prose as _render_reg,
                )
                if _is_reg(_contract_entity):
                    slot_reg_prose.append(_render_reg(_c_payload))
                else:
                    slot_det_prose.append(render_slot_prose(_c_payload))
                _substantive_drafted_by_entity[_corro_eid] = (
                    _substantive_drafted_by_entity.get(_corro_eid, 0)
                    + sum(1 for f in _c_payload.fields if f.status == "extracted")
                )

        if slot_det_prose:
            raw_body_blocks.append(" ".join(slot_det_prose))
        if slot_reg_prose:
            regulatory_body_blocks.append(" ".join(slot_reg_prose))
        if slot_narrative_prose:
            narrative_body_blocks.append(" ".join(slot_narrative_prose))

    # I-arch-004 F02(c) (#1255): surface the section-level empty-narrative count once so
    # the gap is visible in the run log (per-slot warnings above give the detail). Not
    # fatal — the deterministic stream is the primary deliverable.
    if _empty_narrative_slots:
        logger.warning(
            "[m63] I-arch-004 F02(c): %d narrative paragraph(s) came back empty in "
            "section %r — surfaced (not silently dropped); deterministic prose unaffected.",
            _empty_narrative_slots, plan.title,
        )

    # Body-only raw drafts (no `### headings` — they'd poison
    # strict_verify's content-overlap check), ONE PER STREAM.
    # I-faith-001 Fix B / Fix C: the deterministic, regulatory, and narrative
    # prose are kept in separate drafts and verified separately so the M-69
    # rescue can be applied to the deterministic stream ONLY.
    det_raw_draft = " ".join(raw_body_blocks)
    regulatory_raw_draft = " ".join(regulatory_body_blocks)
    narrative_raw_draft = " ".join(narrative_body_blocks)

    contract_entity_ids = set(plan.contract_entities_by_id.keys())

    # ── DETERMINISTIC stream (M-58 verbatim-guarded slot prose) ────────
    # Rescue-ELIGIBLE: the M-69 Fix #4 rescue exists ONLY to undo
    # content-overlap false-drops on legitimately-verbatim slot prose (the
    # SURPASS-5 25K-char regression). `parse_slot_fill_response` enforces
    # `value == source_span`, so the entire rendered prose is verbatim source
    # text. Fix A's `_drop_is_numeric` guard keeps it from laundering numeric
    # fabrications.
    (
        det_kept_sentences,
        det_rescued,
        det_dropped_final,
        det_total_in,
        det_rewritten_draft,
    ) = await asyncio.to_thread(
        _verify_one_stream,
        raw_draft=det_raw_draft,
        evidence_pool=evidence_pool,
        contract_entity_ids=contract_entity_ids,
        rewrite_fn=rewrite_fn,
        strict_verify_fn=strict_verify_fn,
        allow_rescue=True,
        stream_label="deterministic",
    )

    # ── REGULATORY stream (M-70 `render_regulatory_prose` LLM synthesis) ─
    # Rescue-INELIGIBLE (Fix C / regulatory classification): the M-70 parser
    # verbatim-checks ONLY the one `source_span` phrase, not the full
    # LLM-synthesized prose value — so a regulatory sentence carries the SAME
    # fabrication risk as the narrative stream. Each regulatory sentence must
    # pass `verify_sentence_provenance` on its own with NO rescue.
    (
        reg_kept_sentences,
        _reg_rescued,  # always empty — rescue disabled for this stream
        reg_dropped_final,
        reg_total_in,
        reg_rewritten_draft,
    ) = await asyncio.to_thread(
        _verify_one_stream,
        raw_draft=regulatory_raw_draft,
        evidence_pool=evidence_pool,
        contract_entity_ids=contract_entity_ids,
        rewrite_fn=rewrite_fn,
        strict_verify_fn=strict_verify_fn,
        allow_rescue=False,
        stream_label="regulatory",
    )

    # ── NARRATIVE stream (free-form `build_slot_narrative_prompt` LLM) ──
    # Rescue-INELIGIBLE (Fix B): this is the fabrication-prone stream. Each
    # narrative sentence must pass `verify_sentence_provenance` on its own;
    # any drop (numeric OR qualitative content-overlap) stays dropped. This
    # closes the run-9 leak at the structural level — Fix A alone could not
    # catch the qualitative fabrications (attrition/CSAT/partial-equilibrium)
    # because they carry no fabricated integer.
    (
        narr_kept_sentences,
        _narr_rescued,  # always empty — rescue disabled for this stream
        narr_dropped_final,
        narr_total_in,
        narr_rewritten_draft,
    ) = await asyncio.to_thread(
        _verify_one_stream,
        raw_draft=narrative_raw_draft,
        evidence_pool=evidence_pool,
        contract_entity_ids=contract_entity_ids,
        rewrite_fn=rewrite_fn,
        strict_verify_fn=strict_verify_fn,
        allow_rescue=False,
        stream_label="narrative",
    )

    # ── Merge the three streams ────────────────────────────────────────
    # The downstream regroup (~line 700) re-buckets every kept sentence into
    # its originating slot via the first token's evidence_id, so cross-slot
    # ordering is reconstructed regardless of merge order. WITHIN a slot, all
    # deterministic sentences precede regulatory, which precede narrative
    # (pre-Fix-B a multi-entity slot interleaved det(e1),narr(e1),...; now it
    # is det(...),reg(...),narr(...)). This reordering is faithfulness-neutral
    # — the same verified sentences, only the in-slot sequence and citation
    # numbering may shift. Deterministic-first is the intended ordering
    # (verbatim slot facts lead, regulatory + narrative depth follow). A slot
    # is either M-58 OR M-70 per entity, so det and reg do not co-occur for the
    # same entity — only the merge ORDER is defined here, not a mixing rule.
    kept_sentences = (
        det_kept_sentences + reg_kept_sentences + narr_kept_sentences
    )
    # I-cred-008b (#1162) SITE 3/4 (V30 contract): populate the advisory per-claim disclosure on the
    # merged kept SVs BEFORE the resolve below — the contract runner then MANUALLY rebuilds prose from
    # sv.sentence (the per-slot regroup), so populating here makes the four fields ride along into the
    # SectionResult.kept_sentences_pre_resolve emitted at the end of this function. None => byte-identical.
    if credibility_analysis is not None:
        from ..synthesis.credibility_pass import apply_disclosure_to_svs
        kept_sentences = apply_disclosure_to_svs(kept_sentences, credibility_analysis)
    rescued = det_rescued  # regulatory + narrative streams contribute no rescues
    # Combined raw + rewritten drafts (telemetry parity with pre-Fix-B).
    raw_draft = " ".join(
        d for d in (det_raw_draft, regulatory_raw_draft, narrative_raw_draft)
        if d
    )
    rewritten_draft = " ".join(
        d for d in (
            det_rewritten_draft, reg_rewritten_draft, narr_rewritten_draft,
        )
        if d
    )
    # Combined dropped list (excludes deterministic rescues by construction).
    dropped_sentences = (
        det_dropped_final + reg_dropped_final + narr_dropped_final
    )

    # FIX 1 (PART-B, I-arch-002 [8]) — strict_verify OVER-DROP basket re-anchor on
    # THE PRIMARY LIVE BENCHMARK PATH (Gate-B forces PG_V30_PHASE2_ENABLED=1 so
    # EVERY section ships through this runner — this is the path that fires on Q76).
    # A single-cited, single-cluster DROPPED claim is re-anchored to a basket
    # sibling that INDEPENDENTLY passes the UNCHANGED single-span isolation gate;
    # else it stays dropped + disclosed (B5/B7 unchanged). P1-2: the MASTER gate
    # `PG_BASKET_REPAIR_ENABLED` defaults OFF => the pass is never constructed
    # (byte-identical); the max-cycles bound is consulted only when ENABLED.
    # `credibility_analysis is None` (master flag OFF / always-release
    # degrade) also no-ops. Re-anchored survivors route through the SAME post-merge
    # path as normally-kept sentences: M-41c policy filter (no-op by construction
    # here per the module header, but applied for invariant parity) + the advisory
    # disclosure populate (re-applied so survivors carry it, like the merged kept
    # list at 1125-1127) BEFORE the resolve below.
    from .multi_section_generator import (
        _basket_repair_enabled,
        _basket_repair_max_cycles,
        _recover_via_sibling_basket,
    )
    if (
        _basket_repair_enabled()
        and _basket_repair_max_cycles() > 0
        and credibility_analysis is not None
        and dropped_sentences
    ):
        # P1-1 (Codex diff-gate) + deeper-edge fix: capture each dropped sentence's
        # ORIGINAL primary cited evidence_id (the slot-mapped one) BY id() BEFORE the
        # IN-PLACE re-anchor mutation (`_recover_via_sibling_basket` mutates the same
        # SV object and returns it, so id() is stable across the call). After
        # re-anchor, the sibling's eid is NOT in `entity_to_slot_id`, so the slot
        # regroup below (line ~1316) would map it to None and DROP the recovered claim
        # from `verified_text` — present in biblio yet never rendered.
        #
        # The FIRST P1-1 attempt registered the sibling eid into the GLOBAL
        # `entity_to_slot_id` via setdefault. That is unsafe in two edge cases Codex
        # re-flagged: (a) the sibling eid is ALREADY slot-bound (setdefault no-ops, so
        # the recovered claim renders under the sibling's existing slot, not its own);
        # (b) TWO dropped SVs from DIFFERENT original slots re-anchor to the SAME
        # sibling (the first setdefault wins, so the second claim renders under the
        # first claim's slot). Both are real slot MIS-ATTRIBUTION.
        #
        # Fix: record THIS SV's own original slot on the SV itself
        # (`reanchor_original_slot_id`, an additive ATTRIBUTION-only field) and consult
        # it FIRST in the slot regroup — a per-SV override that cannot collide across
        # SVs and never mutates the global map. The original eid's slot is resolved
        # against `entity_to_slot_id` here (unmutated), so a genuinely unmapped
        # original eid still leaves the claim unrendered (no home slot to attribute to).
        import re as _slot_prov_re_mod
        _slot_prov_re = _slot_prov_re_mod.compile(r"\[#ev:([^:\]]+):(\d+)-(\d+)\]")
        _orig_primary_eid_by_sv_id: dict[int, str] = {}
        for _dsv in dropped_sentences:
            _dtext = getattr(_dsv, "sentence", "") or ""
            _dm = _slot_prov_re.search(_dtext)
            if _dm is not None:
                _orig_primary_eid_by_sv_id[id(_dsv)] = _dm.group(1)
        _reanchored_svs, _still_dropped = _recover_via_sibling_basket(
            dropped_sentences, evidence_pool, credibility_analysis,
        )
        if _reanchored_svs:
            # PER-SV slot override: stamp each re-anchored SV with the slot ITS OWN
            # original cited token belonged to, so the post-merge slot regroup (which
            # keys on tokens[0].evidence_id via the global map) renders the recovered
            # claim under its ORIGINAL slot. Set on the SV (a declared dataclass field)
            # so `dataclasses.replace` inside apply_disclosure_to_svs carries it
            # through the disclosure re-populate. Only when the original eid was itself
            # slot-mapped (else the sibling has no home slot and the claim legitimately
            # stays unrendered). NO global-map mutation => no cross-SV leak.
            for _ra_sv in _reanchored_svs:
                _orig_eid = _orig_primary_eid_by_sv_id.get(id(_ra_sv))
                _orig_slot = (
                    entity_to_slot_id.get(_orig_eid) if _orig_eid else None
                )
                if _orig_slot is None:
                    continue
                try:
                    _ra_sv.reanchor_original_slot_id = _orig_slot
                except Exception:
                    # A frozen / non-mutable SV cannot carry the override — leave it
                    # unstamped (it falls back to the global-map lookup, never crashes).
                    continue
            from .multi_section_generator import (
                filter_underframed_trial_sentences,
            )
            from ..synthesis.credibility_pass import apply_disclosure_to_svs
            _ra_kept, _ra_dropped_m41c = filter_underframed_trial_sentences(
                _reanchored_svs
            )
            # Re-apply the advisory per-claim disclosure so re-anchored survivors
            # carry the same fields the merged kept list got at 1125-1127. ADVISORY:
            # never re-runs strict_verify / flips is_verified.
            if credibility_analysis is not None and _ra_kept:
                _ra_kept = apply_disclosure_to_svs(_ra_kept, credibility_analysis)
            kept_sentences = kept_sentences + _ra_kept
            # Honest id-based drop accounting: the whole re-anchored set leaves the
            # dropped list (M-41c-failed ones rejoin it), no double-count.
            _reanchored_ids = {id(sv) for sv in _reanchored_svs}
            dropped_sentences = [
                sv for sv in dropped_sentences
                if id(sv) not in _reanchored_ids
            ] + list(_ra_dropped_m41c)
            logger.info(
                "[contract_section] FIX1 sibling-basket re-anchor: re-cited %d "
                "strict-verify-dropped sentence(s) to an independently-entailing "
                "basket sibling (%d failed M-41c policy filter)",
                len(_ra_kept), len(_ra_dropped_m41c),
            )

    total_in = det_total_in + reg_total_in + narr_total_in
    kept = len(kept_sentences)
    dropped = total_in - kept

    # I-wire-014 (#1336): CONTRACT-section consolidate-keep-all dedup. The fact_dedup
    # B11 same-span + NLI/Jaccard prose seams were wired ONLY into the multi_section
    # path (multi_section_generator.py:7675); contract sections (Foundational_Theory,
    # Empirical_Displacement, Generative_AI_Evidence) ran NO dedup, so a same-claim
    # restatement cluster (the drb_72 "probability of computerisation ... Gaussian
    # process classifier" x8 in Empirical_Displacement) survived verbatim into the
    # rendered report. Run the SAME consolidate-keep-all dedup HERE — on the section's
    # verified SVs, BEFORE the slot-regroup + resolve below assemble the body — via the
    # keep-first-VERBATIM index-drop in `_consolidate_contract_section_sentences` (no LLM
    # rewrite, no re-verify; the primary restatement is kept verbatim). GATED behind the SAME
    # flags as the multi_section pass (PG_FACT_DEDUP_PROSE / PG_CONSOLIDATION_NLI_PROSE) so it
    # is DEFAULT-OFF-safe and byte-identical when the operator hasn't enabled the seam.
    # CONSOLIDATE-KEEP-ALL (§-1.3): every citation of every merged member is preserved (the
    # kept primary carries the superset); the faithfulness engine is untouched. Updates
    # `kept`/`dropped` so post-resolve accounting stays honest.
    if _contract_dedup_enabled() and len(kept_sentences) >= 2:
        try:
            _kept_before_dedup = kept
            kept_sentences, _contract_dedup_telemetry = (
                await _consolidate_contract_section_sentences(
                    plan.title,
                    kept_sentences,
                    evidence_pool,
                    strict_verify_fn=strict_verify_fn,
                    dedup_llm_callable=None,  # keep-first-verbatim path: no LLM rewrite is produced
                )
            )
            _new_kept = len(kept_sentences)
            if _new_kept != _kept_before_dedup:
                # dropped accounting: total_in is fixed; a consolidated redundant left the
                # kept body (its verbatim primary survives, carrying every citation), so
                # dropped rises by exactly the kept-count delta. No source is lost (keep-all);
                # this is the redundant-sentence-count shift.
                dropped += _kept_before_dedup - _new_kept
                kept = _new_kept
            logger.info(
                "[contract_section] I-wire-014 consolidate-keep-all dedup: "
                "%d -> %d kept sentence(s) (groups=%s, redundants=%s, "
                "rewrites_applied=%s, rewrites_verified_drop=%s)",
                _kept_before_dedup,
                _new_kept,
                _contract_dedup_telemetry.get("n_groups"),
                _contract_dedup_telemetry.get("n_redundants"),
                _contract_dedup_telemetry.get("n_rewrites_applied"),
                _contract_dedup_telemetry.get("n_rewrites_verified_drop"),
            )
        except Exception as _dedup_exc:
            # Safe-fail (§-1.3 CONSOLIDATE-DON'T-DROP): a dedup error must NEVER delete
            # corroborating cited sentences. On any failure, keep the original verified
            # SVs verbatim and proceed (the dedup is an OPTIMIZATION, not a gate).
            logger.warning(
                "[contract_section] I-wire-014 dedup pass failed (%s); keeping "
                "original verified sentences verbatim (consolidate-keep-all, §-1.3)",
                _dedup_exc,
            )

    # I-arch-005 B6/B8 (#1257) — THE KEYSTONE on the V30 contract path.
    # The benchmark (Gate-B) forces PG_V30_PHASE2_ENABLED=1, so EVERY section
    # ships through this contract runner — NOT the legacy _run_section. Threading
    # the per-claim baskets + the evidence->cluster binding into the resolve call
    # below is what makes a multi-source claim render ALL its independently
    # span-verified (SUPPORTS) corroborating citations in the REAL benchmark
    # report (the legacy-path wiring alone never reached it). None / empty (master
    # flag OFF) => the resolver's _carry_baskets gate is False => byte-identical
    # legacy inline render. `_baskets`, `_cluster_id_by_evidence`,
    # `_carry_baskets` and `_basket_supports_by_cluster` are HOISTED above the
    # slot loop (A1) and reused here — same single-source-of-truth index, no
    # recompute / drift.
    # ── resolve provenance → [N] citations + biblio_slice ──────
    # `resolve_provenance_to_citations` flattens into a single
    # string. We need per-slot grouping AND legacy-shape output,
    # so we call it first to get the resolved body + biblio, then
    # re-thread the resolution through the slot boundaries.
    # Threading baskets here makes the resolver ALSO enrich biblio_slice with the
    # corroborator members' numbered rows via its _num_for, so the slot-regroup
    # below can look those corroborators up in ev_to_num.
    # I-beatboth-003 (#1280): this call ALSO runs the SURE-RAG relevance gate (when
    # PG_RELEVANCE_GATE is ON) and CACHES the FINAL post-retention demote + refute sets on each
    # kept SV (sv.relevance_demoted_eids = Insufficient-only; sv.relevance_refuted_eids =
    # Refuted-only — two DISTINCT sets per Codex iter-2 P1#1b, plus the persisted
    # relevance_refuted_contradiction soft-warning). The slot-regroup below reads BOTH cached
    # sets and drops their UNION — so the demotion fires in `sentences_by_slot` (the shipped
    # body), not just the discarded `resolved_body`. OFF path => no judge call, sets stay None
    # => byte-identical. Same kept_sentences objects + same baskets here as in the slot loop,
    # so the cached decision is valid for both.
    resolved_body, biblio_slice = resolve_provenance_to_citations(
        kept_sentences, evidence_pool,
        baskets=_baskets,
        cluster_id_by_evidence=_cluster_id_by_evidence,
        relevance_judge_fn=relevance_judge_fn,
    )

    # Build a per-sentence resolved list (parallel to
    # kept_sentences) so we can group by originating slot.
    # Re-do the per-sentence resolution inline — cheap and keeps
    # us in lockstep with `resolve_provenance_to_citations`'s
    # acceptance rules (≥3 content words, ≥15 chars).
    # F10 (I-arch-004 A3): the contract path's authoritative `verified_text` is
    # this inline slot regroup (NOT the flat `resolved_body`), so the honest
    # post-resolve verified count is the number of sentences actually emitted into
    # the slot prose here — `_emitted_into_slots`. The pre-resolve `kept` overstated
    # it (degenerate fragments + F31 bogus-only drop here).
    sentences_by_slot: dict[str, list[str]] = {sid: [] for sid in slot_order}
    _emitted_into_slots = 0
    ev_to_num = {b["evidence_id"]: b["num"] for b in biblio_slice}
    import re as _re
    _prov_re = _re.compile(r"\[#ev:([^:\]]+):(\d+)-(\d+)\]")
    for sv in kept_sentences:
        raw = getattr(sv, "sentence", "") or ""
        tokens = getattr(sv, "tokens", None) or []
        # F31 (I-arch-004 A3): SURGICAL span-grounding drop — fires ONLY when the
        # sentence carried a BOGUS bracketed marker (`[ev_<slug>]` / `[ev:...]`
        # whose id is not a real pool row) AND has NO valid `[#ev:...]` grounding.
        # A normal cited sentence (valid grounding) and a no-bracket pass-through
        # sentence (no bogus marker) are both untouched — mirrors the resolver.
        _has_valid_grounding = any(
            getattr(t, "evidence_id", "") in evidence_pool for t in tokens
        )
        _has_bogus_marker = any(
            _bogus_marker_evidence_id(m.group(0)[1:-1]) not in evidence_pool
            for m in _BOGUS_EV_MARKER_RE.finditer(raw)
        )
        if _has_bogus_marker and not _has_valid_grounding:
            continue
        stripped = _prov_re.sub("", raw).strip()
        # F31: strip any leaked bogus `[ev_<slug>]` marker so it neither ships in
        # the slot prose nor inflates the content-word floor (same as the resolver).
        stripped = _strip_bogus_ev_markers(stripped, evidence_pool).strip()
        stripped = _re.sub(r"\s+([.!?,;])", r"\1", stripped)
        content_w = _re.findall(r"[A-Za-z]+", stripped)
        # F10 (I-arch-004 A3): the SAME named resolution floor the resolver uses
        # (§9.4 no-magic-numbers; removes the 3/15 hard-code drift Codex flagged).
        if (
            len(content_w) < _RESOLVE_MIN_CONTENT_WORDS
            or len(stripped) < _RESOLVE_MIN_PROSE_CHARS
        ):
            continue
        # Determine the slot via the first token's ev_id.
        if not tokens:
            continue
        primary_ev = tokens[0].evidence_id
        # FIX 1 (PART-B, I-arch-002 [8]) P1-1 deeper-edge: a basket-repair re-anchored
        # SV carries its OWN original slot in `reanchor_original_slot_id`. Consult that
        # PER-SV override FIRST so each recovered claim renders under ITS OWN original
        # slot — even when the sibling eid (now tokens[0].evidence_id) already has a
        # global binding or is reused by several recovered claims from DIFFERENT slots.
        # None (the off-path / non-recovered default) => fall through to the global map,
        # so normally-kept sentences are byte-identical.
        _override_slot = getattr(sv, "reanchor_original_slot_id", None)
        slot_id = (
            _override_slot
            if _override_slot is not None
            else entity_to_slot_id.get(primary_ev)
        )
        if slot_id is None:
            continue
        # I-beatboth-003 (#1280): the cached FINAL (post-minimum-retention) sets of evidence_ids
        # the SURE-RAG relevance judge demoted (Insufficient -> listed-not-load-bearing) or
        # refuted (-> contradiction flag) for THIS sentence — computed ONCE in the resolve call
        # above. EXCLUDE those eids from the inline support set here so the demotion fires in the
        # SHIPPED slot body (not just the discarded flat resolved_body). None (OFF path / gate
        # off) => empty => byte-identical legacy regroup. The retention guard already ran in
        # resolve(), so a sentence whose last support would have been demoted has EMPTY sets
        # here (never stranded).
        #
        # iter-2 (Codex P1#1b): Insufficient and Refuted are now cached as TWO DISTINCT sets on
        # the SV. The inline-support exclusion is the UNION of the two — both an Insufficient
        # demotion and a Refuted contradiction-flag remove the cite from inline support (the
        # Refuted contradiction is ALSO recorded as the persisted
        # ``relevance_refuted_contradiction`` soft-warning by resolve()). Reading both via
        # getattr keeps the OFF/legacy path (no attribute) byte-identical.
        # I-arch-005 B6/B8 (#1257) own-token + INLINE multi-citation basket render on the V30
        # contract path (the keystone reaching the benchmark report), I-beatboth-003 demotion,
        # and the I-beatboth-011 P1#1 claim-local-span corroborator filter are computed by ONE
        # extracted module-level helper (contract_sentence_citation_nums) so the benchmark-path
        # attachment decision is behaviorally testable and IDENTICAL to the legacy resolver's:
        # a corroborator filtered off S1 there can NOT be reattached to S1 here via the
        # section-wide ev_to_num it earned on S2. Empty index (OFF path) => own tokens only =>
        # byte-identical legacy single-citation regroup.
        used_nums = contract_sentence_citation_nums(
            sv,
            tokens,
            ev_to_num,
            basket_supports_by_cluster=_basket_supports_by_cluster,
            cluster_id_by_evidence=_cluster_id_by_evidence,
            evidence_pool=evidence_pool,
            basket_by_cluster=_basket_by_cluster,
        )
        markers = "".join(f"[{n}]" for n in used_nums)
        sentences_by_slot.setdefault(slot_id, []).append(stripped + markers)
        _emitted_into_slots += 1

    # Emit final verified_text with re-injected headings.
    # V30 Phase-2 M-68 Fix #1 (Codex run-7 audit directive):
    # a slot MUST NEVER silently drop from the body — even when
    # strict_verify kept zero sentences for it, emit the heading
    # plus an explicit gap-disclosure sentence. Pre-fix behaviour
    # silently omitted SURPASS-6, FDA Mounjaro, EMA EPAR, HC
    # Mounjaro in run-7 despite frame_coverage=pass for all four,
    # producing a structural LB vs both competitors.
    #
    # M-68 Fix #1b (run-8 Qwen citation_tightness regression):
    # gap-disclosure prose must carry a citation marker pointing
    # at the bound contract entity. Without it, Qwen flags
    # citation_tightness=needs_revision, blocking release_allowed.
    # Synthesize a bibliography entry for the bound entity if it
    # didn't already get one from kept_sentences.
    # I-ready-017 FX-07b leg-2 (#1111): count kept AND dropped strict_verify
    # sentences PER ENTITY via [#ev:entity_id:..] tokens (the SAME _prov_re used
    # for kept attribution above). PER-ENTITY — not per slot-primary — because
    # real slots are multi-entity: a non-primary entity whose generated prose was
    # fully dropped must get its own (slot,entity) telemetry row, and a primary
    # entity must NOT be shielded by a sibling entity's kept sentence (Codex
    # diff-gate iter-1 P1). The per-(slot,entity) rows are emitted after the slot
    # loop into `slot_strict_verify`. Pure telemetry — no behaviour change.
    from collections import Counter as _Counter
    _kept_by_entity: _Counter = _Counter()
    for _ksv in kept_sentences:
        _kraw = getattr(_ksv, "sentence", "") or ""
        for _km in _prov_re.finditer(_kraw):
            _kept_by_entity[_km.group(1)] += 1
    _dropped_by_entity: _Counter = _Counter()
    for _dsv in dropped_sentences:
        _draw = getattr(_dsv, "sentence", "") or ""
        for _dm in _prov_re.finditer(_draw):
            _dropped_by_entity[_dm.group(1)] += 1
    # I-ready-017 FX-07b leg-2 (#1111, root-cause design): SUBSTANTIVE kept
    # count per entity = kept sentences EXCLUDING gap-disclosure placeholders.
    # Attributed to the sentence's PRIMARY token (tokens[0]) — the same rule the
    # slot-regroup uses — so a multi-token sentence cannot inflate a secondary
    # entity's substantive-kept (Codex root-cause P2 / aggregation-edgecase P2).
    # This closes the Class-B escape (eloundou: kept>0 but all placeholders read
    # pass) — a placeholder is NOT substantive verified prose.
    _kept_substantive_by_entity: _Counter = _Counter()
    for _ksv in kept_sentences:
        if _is_gap_disclosure_sentence(getattr(_ksv, "sentence", "")):
            continue
        _ktoks = getattr(_ksv, "tokens", None) or []
        if _ktoks:
            _kept_substantive_by_entity[_ktoks[0].evidence_id] += 1

    verified_blocks: list[str] = []
    slot_drop_log: list[dict[str, Any]] = []  # M-66a-T telemetry
    for slot_id in slot_order:
        body_sentences = sentences_by_slot.get(slot_id) or []
        heading = f"### {slot_subsection[slot_id]}"
        if body_sentences:
            body = " ".join(body_sentences)
            verified_blocks.append(f"{heading}\n\n{body}")
            slot_drop_log.append({
                "slot_id": slot_id,
                "kept_sentences": len(body_sentences),
                "disposition": "rendered_with_content",
            })
        else:
            # M-68 Fix #1b: ensure the gap disclosure carries a
            # citation marker for the bound entity. Synthesize a
            # biblio entry on demand if the entity wasn't already
            # cited via kept_sentences.
            primary_ev = slot_primary_entity.get(slot_id, "")
            if primary_ev and primary_ev not in ev_to_num:
                ev = evidence_pool.get(primary_ev, {})
                # M-69 Fix #2: prefer the contract entity's
                # label_name (e.g., "Mounjaro Canadian Product
                # Monograph", "TA924") for regulatory entities
                # when the FrameRow has no title. Pre-fix
                # fallback to the bare entity_id produced ugly
                # bibliography entries like
                # `statement=fda_zepbound_label`.
                contract_entity = plan.contract_entities_by_id.get(
                    primary_ev,
                )
                label = (
                    getattr(contract_entity, "label_name", None)
                    if contract_entity is not None else None
                )
                statement_candidates = [
                    ev.get("statement"),
                    ev.get("title"),
                    label,
                    primary_ev,
                ]
                statement = next(
                    (s for s in statement_candidates if s), primary_ev,
                )
                new_num = len(biblio_slice) + 1
                biblio_slice.append({
                    "num": new_num,
                    "evidence_id": primary_ev,
                    "url": ev.get("url") or ev.get("source_url") or "",
                    "tier": ev.get("tier", ""),
                    "statement": statement[:300],
                })
                ev_to_num[primary_ev] = new_num
            # FIX 4 (I-deepfix-001 #1344, audit c026): BEFORE disclosing a false
            # gap, check whether the bound entity has ANY strict_verify-passing
            # span in evidence_pool. If so, render that span VERBATIM (K-span
            # fallback) with its [N] citation, RETAINING the real finding instead
            # of deleting it under a false gap label (§-1.3 RETAIN-not-drop). The
            # emitted span is grounded by construction and re-verified via the
            # SAME strict_verify path — faithfulness-neutral. Env-flag-gated; OFF
            # => kspan_body stays None (short-circuit, no call) and the code falls
            # straight through to the byte-identical gap disclosure below.
            kspan_body = None
            _kspan_flag_on = _false_gap_kspan_enabled()
            if _kspan_flag_on and primary_ev:
                kspan_body = _kspan_fallback_body(
                    primary_ev=primary_ev,
                    evidence_pool=evidence_pool,
                    marker_num=ev_to_num[primary_ev],
                    rewrite_fn=rewrite_fn,
                    strict_verify_fn=strict_verify_fn,
                )
            # FIX 4 anti-dark [activation] canary (I-deepfix-001 #1344): one line
            # per gap-candidate slot classifying the false-gap-K-span decision
            # (flag_off / kspan_none / kspan_rendered). Default-ON => a released
            # run always carries this marker, proving the retention path is live.
            if kspan_body is not None:
                _kspan_state = "kspan_rendered"
            elif not _kspan_flag_on:
                _kspan_state = "flag_off"
            else:
                _kspan_state = "kspan_none"
            logger.info(
                "[activation] contract_false_gap_kspan: slot=%s kept=%d rendered=%s",
                slot_id, (1 if kspan_body is not None else 0), _kspan_state,
            )
            if kspan_body is not None:
                verified_blocks.append(f"{heading}\n\n{kspan_body}")
                slot_drop_log.append({
                    "slot_id": slot_id,
                    "kept_sentences": 1,
                    "disposition": "rendered_kspan_fallback",
                })
                logger.info(
                    "[deepfix-fix4] slot %r rendered verified K-span fallback "
                    "for bound entity %r (false-gap averted)",
                    slot_id, primary_ev,
                )
                continue
            if primary_ev:
                marker = f"[{ev_to_num[primary_ev]}]"
                gap_sentence = (
                    f"Contract-bound content for {primary_ev} did not "
                    f"survive strict verification against retrieved "
                    f"primary source text; this slot is a curator-"
                    f"actionable gap. See manifest.frame_coverage_report "
                    f"and human_gap_tasks.json for per-entity detail."
                    f"{marker}"
                )
            else:
                # Fallback if no primary entity (defensive — outline
                # compiler enforces non-empty entity_ids per slot).
                gap_sentence = (
                    "Contract-bound content did not survive strict "
                    "verification; curator-actionable gap."
                )
            verified_blocks.append(f"{heading}\n\n{gap_sentence}")
            slot_drop_log.append({
                "slot_id": slot_id,
                "kept_sentences": 0,
                "disposition": "rendered_as_gap_disclosure",
            })
            logger.info(
                "[m63] slot %r rendered as gap disclosure "
                "(strict_verify kept 0 sentences)", slot_id,
            )

    # I-ready-017 FX-07b leg-2 (#1111) — Codex diff-gate iter-1 P1:
    # emit ONE strict_verify telemetry row PER (slot_id, entity_id), NOT one
    # per slot keyed to the slot's primary entity. Real contract slots are
    # multi-entity; the frame_coverage honesty override is per-ENTITY, so each
    # bound entity needs its own {sentences_kept, sentences_generated_content}
    # counted from the per-entity [#ev:entity_id:..] attribution above
    # (_kept_by_entity / _dropped_by_entity). This way a non-primary entity
    # whose generated prose was fully dropped gets its own row (and can flip to
    # generation_failed), and a primary entity is never shielded by a sibling
    # entity's kept sentence. Pure telemetry — no behaviour change.
    slot_strict_verify: list[dict[str, Any]] = []
    for slot in plan.slots:
        if not slot.entity_ids:
            continue
        for entity_id in slot.entity_ids:
            _kept = int(_kept_by_entity.get(entity_id, 0))
            _dropped = int(_dropped_by_entity.get(entity_id, 0))
            _frow = plan.frame_rows_by_entity.get(entity_id)
            _pc = getattr(
                getattr(_frow, "provenance_class", None), "value", "",
            ) if _frow is not None else ""
            # has_usable_quote: derived from the SAME floor that contract
            # rendering uses (_MIN_VERIFIABLE_SPAN_CHARS) — i.e. the generator
            # COULD have produced verifiable prose. quote_len/min_quote_chars
            # are emitted for auditability (Codex root-cause P2).
            _qlen = len((getattr(_frow, "direct_quote", "") or "").strip())
            slot_strict_verify.append({
                "slot_id": slot.slot_id,
                "entity_id": entity_id,
                "sentences_kept": _kept,
                "sentences_generated_content": _kept + _dropped,
                # FX-07b root-cause design: token-independent substantive signals
                # that decide the honesty override (drafted real content + zero
                # substantive kept + usable quote = pipeline fault; otherwise a
                # curator gap). See frame_manifest.compose_frame_coverage.
                "sentences_drafted_substantive": int(
                    _substantive_drafted_by_entity.get(entity_id, 0)
                ),
                "sentences_kept_substantive": int(
                    _kept_substantive_by_entity.get(entity_id, 0)
                ),
                "has_usable_quote": _qlen >= _MIN_VERIFIABLE_SPAN_CHARS,
                "quote_len": _qlen,
                "min_quote_chars": _MIN_VERIFIABLE_SPAN_CHARS,
                "provenance_class": _pc,
            })

    if verified_blocks:
        verified_text = "\n\n".join(verified_blocks)
    else:
        # No slots at all — genuine empty-section fallback.
        verified_text = ""

    # Only flag dropped_due_to_failure when there are literally
    # no verified_blocks (no slots or no headings emitted). With
    # the gap-disclosure fallback, every slot renders at minimum
    # a heading, so this should only fire on plan.slots being
    # empty — which M-57 shouldn't emit.
    dropped_due_to_failure = (
        not verified_blocks and len(all_entity_ids) > 0
    )

    # I-gen-005 Step 1.5 iter-2 (Codex P1): populate final per-sentence
    # telemetry fields so verification_details.json reflects contract
    # sections' kept/dropped state.
    #
    # I-faith-001 Fix B: `dropped_sentences` is already
    # `det_dropped_final + narr_dropped_final` — the per-stream helper
    # returns each stream's POST-rescue dropped list, so deterministic
    # rescues are already excluded. The `rescued_ids` filter is therefore
    # a defensive no-op (kept for clarity that rescues are never in the
    # final dropped list).
    rescued_ids = {id(sv) for sv in rescued}
    final_dropped_svs = [
        sv for sv in dropped_sentences if id(sv) not in rescued_ids
    ]
    result = section_result_cls(
        title=plan.title,
        focus=plan.focus,
        ev_ids_assigned=all_entity_ids,
        raw_draft=raw_draft,
        rewritten_draft=rewritten_draft,
        verified_text=verified_text,
        biblio_slice=biblio_slice,
        # F10 (I-arch-004 A3): report the POST-resolve emitted count
        # (`_emitted_into_slots` — sentences actually rendered into the slot prose
        # that becomes verified_text), NOT `kept` (the pre-resolve kept-list
        # length). The inline regroup drops degenerate fragments + F31 bogus-only
        # sentences, so `kept` overstated what shipped as verified prose. The
        # resolver-dropped delta is rolled into sentences_dropped so verified +
        # dropped stays consistent, and `error` keys on the honest emitted count.
        sentences_verified=_emitted_into_slots,
        sentences_dropped=dropped + max(0, kept - _emitted_into_slots),
        regen_attempted=False,  # M-63 doesn't regenerate — M-58
                                # fabrication check is per-field
        dropped_due_to_failure=dropped_due_to_failure,
        input_tokens=total_in_tok,
        output_tokens=total_out_tok,
        error="" if _emitted_into_slots > 0 else "no_sentences_verified",
        # I-gen-005 Step 1.5 iter-2 (Codex P1 contract_runner:683):
        # final kept + dropped SVs after rescue path. Rescued SVs are
        # in kept_sentences_pre_resolve; non-rescued drops are in
        # dropped_sentences_final.
        # I-wire-014 (#1336): the consolidate-keep-all dedup above (gated on
        # PG_FACT_DEDUP_PROSE / PG_CONSOLIDATION_NLI_PROSE, default-OFF) may now
        # CONSOLIDATE same-claim restatements within a contract section. When it
        # fires, kept_sentences here is the POST-dedup list (the redundant
        # paraphrases are merged into the primary, citations preserved §-1.3);
        # the dedup is a consolidation, not a strict_verify drop, so it is NOT
        # added to dropped_sentences_final (which carries only verify failures).
        # With both flags OFF, no dedup runs and this list is byte-identical.
        kept_sentences_pre_resolve=list(kept_sentences),
        dropped_sentences_final=final_dropped_svs,
        # I-ready-017 FX-07b leg-2 (#1111): per-(slot,entity) strict_verify
        # telemetry for the frame_coverage honesty override (Codex diff-gate
        # iter-1 P1 — per entity, not per slot-primary).
        slot_strict_verify=slot_strict_verify,
    )
    return result, payloads


def is_contract_section(plan: Any) -> bool:
    """Duck-typed check: is this a ContractSectionPlanExt?
    Used by orchestration loop to dispatch without importing
    the extended class (keeps generator edit minimal)."""
    return isinstance(plan, ContractSectionPlanExt)
