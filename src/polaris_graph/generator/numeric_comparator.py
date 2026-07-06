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

_ENV_NUMERIC_COMPARATOR = "PG_NUMERIC_COMPARATOR"


def numeric_comparator_enabled() -> bool:
    """``PG_NUMERIC_COMPARATOR`` gate (default OFF, LAW VI). OFF => the composer never consults the
    comparator and the cross-source relation set stays {conflict, agreement, extension, neutral}
    (byte-identical). ON => a NEUTRAL pair whose two baskets carry FULLY-comparable numeric claims is
    upgraded to the ``comparison`` connective. This is a WEIGHT/CONSOLIDATE surfacing lever, never a
    cap / target / thinner (§-1.3)."""
    return os.getenv(_ENV_NUMERIC_COMPARATOR, "0").strip().lower() not in ("", "0", "false", "off", "no")


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
    if disc_a != disc_b:
        return None  # different claim identity (measure/unit/entity/qualifier) => not comparable
    if val_a == val_b:
        return None  # identical values => same claim, no comparison to draw
    return NUMERIC_COMPARISON_RELATION


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
