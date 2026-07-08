"""I-deepfix-001 Wave-2a (#1344) — the DETERMINISTIC, FAIL-CLOSED numeric comparator.

A cross-source analytical unit may want to co-locate two verified numbers so a reader can compare them
("study A reported X%; for comparison, study B reported Y%"). That is only faithful when the two numbers
measure the SAME thing: same entity, same measure, same unit, same denominator / baseline / time-window —
every discriminating field equal AND positively known. If ANY field is missing or ambiguous, comparing
the two numbers is misleading, so this comparator FAILS CLOSED to the neutral connective (under-relax is
safe; over-relax is lethal — a wrong "for comparison" across incompatible denominators is a clinical
faithfulness violation).

THE KEY REUSE (why this is safe by construction): every atomic numeric claim already carries a
``normalized_key`` — the conservative merge key built by ``claim_graph._normalized_key_numeric`` (legacy
path) or ``claim_graph.build_merge_key`` (redesign path). The REDESIGN key is fully fail-closed: any
unknown / defaulted / ambiguous discriminator forces a per-claim ``__unresolved__`` singleton, so a
non-singleton redesign key carries every discriminator positively known. The LEGACY key does NOT
self-fail-close on every field: ``claim_graph._normalized_key_numeric`` sentinels ONLY on a blank SUBJECT,
so a blank predicate / unit / dose / arm / endpoint passes straight through as ``""``. Blank is UNKNOWN,
not positively known, so THIS module ENFORCES the missing guard (Fable P1, clinical-safety):
``_numeric_comparability_key`` additionally requires EVERY discriminator to be non-blank — a strict
tightening that is a NO-OP on redesign keys (already all-non-blank) and CLOSES the legacy blank-unit hole
(licensing "for comparison" between %-points and mmol/mol whose unit was never established is the lethal
over-relax). This comparator does NOT re-extract, re-parse, or relax anything — it reads the retained key
and asks a pure question: are these two numeric claims IDENTICAL on every POSITIVELY-KNOWN discriminator
EXCEPT the value, with DIFFERING values? If yes, ``comparison`` is licensed; otherwise ``None``
(fail-closed to neutral).

VALUE-POSITION INVARIANT (asserted defensively): across ALL three numeric key builders the tag is at
index 0 == ``"numeric"`` and the EXACT float value is at index 3:
  * legacy  ``_normalized_key_numeric`` -> ``("numeric", subject, predicate, value, unit, dose, arm, endpoint_phrase)``
  * redesign ``MERGE_KEY_SPEC[("numeric", "clinical")]``    -> ``[kind_tag, subject, predicate, value, unit, dose, ...]``
  * redesign ``MERGE_KEY_SPEC[("numeric", "nonclinical")]`` -> ``[kind_tag, subject, predicate, value, unit, endpoint_phrase]``
The comparability key is the merge key with the value slot removed (all discriminators, in order); two
claims are comparable iff those discriminator tuples are EQUAL (so their lengths — hence their key builder
+ domain — also match). A qualitative / sentinel / short / non-float key => ``None`` (fail-closed).

PURE: no network, no model, no faithfulness-file import, no input mutation. Arithmetic is ``==`` / ``!=``
over the ALREADY-VERIFIED float values; each clause keeps its OWN provenance token. snake_case. LAW VI:
gated by ``PG_NUMERIC_COMPARATOR`` (default OFF) at the call site — when off (or no key lookup threaded)
this module is never consulted and the composer is byte-identical.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Optional

logger = logging.getLogger(__name__)

# The comparative RELATION key + its (non-directional) connective phrase live in
# ``cross_source_synthesis.LICENSED_CONNECTIVES``; this constant is the relation key the composer sets.
NUMERIC_COMPARISON_RELATION = "comparison"

# The numeric merge-key tag (index 0) + the EXACT value slot index (index 3) — the cross-builder
# invariant documented above. A key that does not match this shape is NOT a comparable numeric claim.
_NUMERIC_TAG = "numeric"
_VALUE_SLOT_INDEX = 3
_MIN_NUMERIC_KEY_LEN = 4  # tag, subject, predicate, value (nonclinical redesign is the shortest at 6)

# Wave-3a (I-deepfix-001 #1344, clinical-safety): the LEGACY ``_normalized_key_numeric`` key is a fixed
# 8-tuple ``("numeric", subject, predicate, value, unit, dose, arm, endpoint_phrase)`` and it carries a
# NO-CUE arm as the non-blank DEFAULT ``"treatment"`` (contradiction_detector.py:1601, kept for OFF
# byte-identity — Codex Slice-B P1). ``"treatment"`` is non-blank, so the blank guard in
# ``_numeric_comparability_key`` does NOT catch it: two findings whose arm was NEVER positively extracted
# (both defaulted to ``"treatment"``) would license a SAME-arm ``comparison`` that was never established —
# the lethal over-relax. Mirror ``claim_graph._unknown_arm`` (which treats ``"treatment"`` AS UNKNOWN on
# the redesign path): a legacy arm slot == ``"treatment"`` is UNKNOWN -> fail closed. The REDESIGN key
# already singleton-forces a defaulted arm UPSTREAM (build_merge_key via _unknown_arm), so a redesign key
# NEVER reaches the comparator carrying ``"treatment"`` -> this is a strict NO-OP on redesign keys and
# closes the LEGACY path only. arm is the ONLY legacy discriminator with a non-blank unknown default
# (dose / endpoint / etc. default to ``""`` — already caught by the blank guard; a defaulted "unknown"
# subject is already sentinelled by ``_normalized_key_numeric`` itself).
_LEGACY_NUMERIC_KEY_LEN = 8       # ("numeric", subject, predicate, value, unit, dose, arm, endpoint_phrase)
_LEGACY_ARM_SLOT_INDEX = 6        # arm position in the full legacy 8-tuple
_LEGACY_ARM_UNKNOWN_SENTINEL = "treatment"  # extractor no-cue arm default == UNKNOWN (claim_graph._unknown_arm)

_ENV_NUMERIC_COMPARATOR = "PG_NUMERIC_COMPARATOR"

# I-deepfix-001 (#1369) STEP 3 — construct-level cross-source numeric comparison. The exact-discriminator
# path below only licenses a comparison when two numbers share the SAME subject/entity/unit; that is why
# Frey-Osborne "702 occupations / computerisation", Eloundou "1.8% -> 46% of jobs", and ILO "24% of
# clerical tasks" — all EXPOSURE_SHARE measures in % — never paired (different subjects) and 892 extracted
# numbers rendered zero comparison. The CLOSED, deterministic construct-tag map below lets two numeric
# atoms compare when they share a UNIT and a KNOWN construct even with different subject strings. It is
# FAIL-CLOSED: an unknown construct (no lexicon hit) is NOT comparable — a construct is NEVER forced.
_ENV_CONSTRUCT_COMPARISON = "PG_NUMERIC_CONSTRUCT_COMPARISON"
_CONSTRUCT_LEXICON: tuple[tuple[str, tuple[str, ...]], ...] = (
    # (construct_tag, needle substrings)  — FIRST match wins (priority order). CLOSED set (Fable/coord spec).
    ("EXPOSURE_SHARE", ("exposure", "exposed", "susceptib", "affected", "at-risk", "at risk", "computeris", "computeriz")),
    ("LABOR_EFFECT", ("employment", "wage", "displace", "job-loss", "job loss", "jobs lost", "unemploy")),
    ("PRODUCTIVITY", ("productivity", "output")),
)


def numeric_comparator_enabled() -> bool:
    """``PG_NUMERIC_COMPARATOR`` gate (default OFF, LAW VI). OFF => the composer never consults the
    comparator and the cross-source relation set stays {conflict, agreement, extension, neutral}
    (byte-identical). ON => a NEUTRAL pair whose two baskets carry FULLY-comparable numeric claims is
    upgraded to the ``comparison`` connective. This is a WEIGHT/CONSOLIDATE surfacing lever, never a
    cap / target / thinner (§-1.3)."""
    return os.getenv(_ENV_NUMERIC_COMPARATOR, "0").strip().lower() not in ("", "0", "false", "off", "no")


def _construct_comparison_enabled() -> bool:
    """``PG_NUMERIC_CONSTRUCT_COMPARISON`` gate (default OFF in code, LAW VI; slate pins ON). OFF => only
    the exact-discriminator comparison path fires (byte-identical). ON => two positively-known numeric keys
    that share a UNIT and a KNOWN construct tag but differ in subject are ALSO licensed for the
    non-directional ``comparison`` connective."""
    return os.getenv(_ENV_CONSTRUCT_COMPARISON, "0").strip().lower() not in ("", "0", "false", "off", "no")


def _construct_tag(normalized_key: Any) -> Optional[tuple]:
    """``(construct_tag, unit)`` for a positively-known numeric key, or ``None`` (fail-closed).

    ``construct_tag`` is the FIRST-matching CLOSED lexicon entry over the key's subject+predicate text;
    no hit => ``None`` (an unknown construct is never forced to compare). ``unit`` is the merge key's unit
    discriminator (legacy layout: original index 4 => discriminators[3]); the comparability view has
    already fail-closed on a BLANK unit, so ``unit`` here is always positively known. Pure; never raises."""
    view = _numeric_comparability_key(normalized_key)
    if view is None:
        return None
    disc, _val = view
    # disc = (tag, subject, predicate, unit, dose, arm, endpoint) on the legacy layout; scan the SEMANTIC
    # fields (everything past the "numeric" tag) for the construct lexicon.
    text = " ".join(str(d) for d in disc[1:]).lower()
    tag: Optional[str] = None
    for cand, needles in _CONSTRUCT_LEXICON:
        if any(n in text for n in needles):
            tag = cand
            break
    if tag is None:
        return None
    unit = str(disc[3]).strip().lower() if len(disc) > 3 else ""
    return (tag, unit)


def _numeric_comparability_key(normalized_key: Any) -> Optional[tuple]:
    """The comparability view of a numeric ``normalized_key``: ``(discriminators_tuple, value_float)``
    where ``discriminators_tuple`` is the merge key with the value slot removed (every discriminator, in
    order) and ``value_float`` is the EXACT verified value.

    Returns ``None`` (FAIL-CLOSED — treated as not-comparable) for anything that is not a
    FULLY-positively-known numeric merge key:
      * a non-tuple / too-short key;
      * a key whose tag (index 0) is not ``"numeric"`` — i.e. a qualitative key, the legacy
        ``__numeric_unknown__`` sentinel, or the redesign ``__unresolved__`` singleton;
      * a key whose value slot (index 3) is not a real number;
      * a key with ANY BLANK discriminator (empty / whitespace). The REDESIGN key never reaches here with
        a blank discriminator (``build_merge_key`` already singleton-forces on any unknown field), but the
        LEGACY ``_normalized_key_numeric`` sentinels ONLY on a blank SUBJECT — a blank predicate / unit /
        dose / arm / endpoint passes straight through as ``""``. Blank is UNKNOWN, not positively known, so
        this module ENFORCES the missing guard HERE (Fable P1, clinical-safety): any blank discriminator
        fails closed. This is a strict tightening (NO-OP on redesign keys) — never compare two numbers
        whose unit / entity / baseline was never established.
    Pure; never raises."""
    if not isinstance(normalized_key, tuple) or len(normalized_key) < _MIN_NUMERIC_KEY_LEN:
        return None
    if normalized_key[0] != _NUMERIC_TAG:
        return None
    value = normalized_key[_VALUE_SLOT_INDEX]
    # bool is an int subclass but is never a real measured value — reject it explicitly.
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    discriminators = normalized_key[:_VALUE_SLOT_INDEX] + normalized_key[_VALUE_SLOT_INDEX + 1:]
    # Fable P1 (clinical-safety): EVERY discriminator field beyond the ``"numeric"`` tag must be POSITIVELY
    # KNOWN (non-blank). The legacy key does NOT self-fail-close on a blank non-subject field, and comparing
    # two values across an unknown unit / entity / baseline (%-points vs mmol/mol) is the lethal over-relax.
    # A single blank/empty/whitespace discriminator => fail closed. (``discriminators[0]`` is the tag.)
    for slot in discriminators[1:]:
        if not str(slot).strip():
            return None
    # Wave-3a (clinical-safety, mirrors claim_graph._unknown_arm): the LEGACY key carries a NO-CUE arm as
    # the non-blank sentinel ``"treatment"`` (index 6 of the fixed 8-tuple), which the blank guard above
    # does NOT catch. Two arm-unknown findings both default to ``"treatment"``; licensing a comparison
    # implies a same-arm claim that was NEVER positively established (the lethal over-relax). Fail closed on
    # it. LEGACY key ONLY (len == 8): the redesign key already singleton-forces a defaulted arm upstream, so
    # it never reaches here carrying ``"treatment"`` -> strict NO-OP on redesign keys.
    if (
        len(normalized_key) == _LEGACY_NUMERIC_KEY_LEN
        and str(normalized_key[_LEGACY_ARM_SLOT_INDEX]).strip().lower() == _LEGACY_ARM_UNKNOWN_SENTINEL
    ):
        return None
    return (discriminators, float(value))


def license_numeric_comparison(key_a: Any, key_b: Any) -> Optional[str]:
    """Decide whether a COMPARATIVE connective is licensed between two claim clusters, from their retained
    numeric ``normalized_key`` tuples.

    Returns ``NUMERIC_COMPARISON_RELATION`` (``"comparison"``) IFF:
      * both keys reduce to a comparability view (both are positively-known numeric merge keys), AND
      * their discriminator tuples are EQUAL — every field (measure/entity/unit/denominator/baseline/
        time-window as carried by the merge-key spec) matches AND is positively known, AND
      * the two verified values DIFFER (equal values would already have shared a cluster — there is no
        "comparison" to draw between two identical numbers).
    Otherwise ``None`` (FAIL-CLOSED to the neutral connective): any missing / ambiguous / differing
    discriminator, a non-numeric key, or equal values. Pure; deterministic; arithmetic is ``==`` / ``!=``
    over already-verified floats. NEVER asserts a direction (larger/smaller) — the connective is
    non-directional and each clause keeps its own token."""
    ca = _numeric_comparability_key(key_a)
    cb = _numeric_comparability_key(key_b)
    if ca is None or cb is None:
        return None
    disc_a, val_a = ca
    disc_b, val_b = cb
    if val_a == val_b:
        return None  # identical values => same claim, no comparison to draw
    if disc_a == disc_b:
        return NUMERIC_COMPARISON_RELATION  # exact claim-identity comparison (measure/unit/entity match)
    # I-deepfix-001 (#1369) STEP 3: construct-level fallback — DIFFERENT subjects but SAME unit + SAME
    # KNOWN construct (Frey-Osborne vs Eloundou vs ILO, all EXPOSURE_SHARE in %). ``_construct_tag`` returns
    # ``(construct_tag, unit)`` and is None on an unknown construct, so the equality below requires BOTH the
    # construct AND the unit to match — a different construct (exposure % vs wage pp) or a different unit
    # never pairs (fail-closed). Values already differ (guarded above). The connective stays the
    # non-directional "comparison"; each clause keeps its own [#ev] token and no direction/magnitude is
    # asserted, so faithfulness is preserved by quotation (§-1.3). Gated by PG_NUMERIC_CONSTRUCT_COMPARISON.
    if _construct_comparison_enabled():
        cta = _construct_tag(key_a)
        ctb = _construct_tag(key_b)
        if cta is not None and cta == ctb:
            return NUMERIC_COMPARISON_RELATION
    return None


def build_numeric_key_lookup(claims: Any) -> dict[str, tuple]:
    """``{claim_cluster_id: normalized_key}`` for every ``kind == "numeric"`` atomic claim.

    All claims in a cluster share the SAME ``normalized_key`` by construction (that is what clustered
    them), so a last-writer-wins map is well-defined. A claim with no ``claim_cluster_id`` or no
    ``normalized_key`` is skipped. The composer threads this map so a basket's ``claim_cluster_id`` can be
    resolved to its numeric merge key for the comparator. Pure; empty on ``None`` / non-numeric input."""
    out: dict[str, tuple] = {}
    for claim in (claims or []):
        try:
            if str(getattr(claim, "kind", "") or "").strip().lower() != _NUMERIC_TAG:
                continue
            ccid = str(getattr(claim, "claim_cluster_id", "") or "")
            key = getattr(claim, "normalized_key", None)
        except AttributeError:
            continue
        if not ccid or not isinstance(key, tuple):
            continue
        out[ccid] = key
    return out
