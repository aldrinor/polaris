"""I-deepfix-001 Wave-3a (#1344) — numeric-comparator legacy arm-default clinical-safety guard.

The numeric comparator (``PG_NUMERIC_COMPARATOR``) upgrades a NEUTRAL cross-source pair to a
``comparison`` connective ONLY when the two numeric findings are IDENTICAL on every positively-known
discriminator except the value. The LEGACY merge key ``claim_graph._normalized_key_numeric`` carries a
NO-CUE arm as the non-blank DEFAULT ``"treatment"`` (contradiction_detector.py:1601, kept for OFF
byte-identity). ``"treatment"`` is non-blank, so the pre-existing blank guard did NOT catch it — two
findings whose arm was NEVER positively extracted (both defaulted to ``"treatment"``) would have licensed
a SAME-arm comparison that was never established. That is the lethal over-relax a wrong cross-source
numeric comparison can imply a wrong dose/effect. This suite pins the Wave-3a fix:

  (a) two findings each with a MISSING (no-cue -> ``"treatment"``) arm are NOT comparable;
  (b) two findings with the SAME explicitly-extracted arm (+ all other discriminators matching, differing
      values) ARE comparable — the real comparison still fires (no regression);
  (c) OFF (``PG_NUMERIC_COMPARATOR`` unset) -> the comparator is never consulted (byte-identical dark path).

Pure fixtures; no live models, no network. The guard mirrors ``claim_graph._unknown_arm`` and is a strict
NO-OP on redesign keys (which singleton-force a defaulted arm upstream).
"""
from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from src.polaris_graph.generator.numeric_comparator import (  # noqa: E402
    _LEGACY_ARM_UNKNOWN_SENTINEL,
    _numeric_comparability_key,
    license_numeric_comparison,
    numeric_comparator_enabled,
)


# A legacy ``_normalized_key_numeric``-shaped tuple (value at index 3, arm at index 6). Defaults are FULLY
# populated + POSITIVELY KNOWN (arm="comparator_adjacent" is a real placebo-cue arm, NOT the no-cue
# "treatment" sentinel) so a full match licenses a comparison; a test that wants the fail-closed path
# passes an unknown/blank field explicitly.
def _num_key(subject, predicate, value, unit="percent", dose="10mg",
             arm="comparator_adjacent", endpoint="hba1c"):
    return ("numeric", subject, predicate, float(value), unit, dose, arm, endpoint)


def test_missing_arm_default_treatment_not_comparable():
    """(a) Two findings each with a MISSING arm (extractor no-cue default ``"treatment"``) must NOT be
    upgraded to a comparison, even though every OTHER discriminator matches and the values differ. A
    defaulted ``"treatment"`` arm is UNKNOWN, not positively same-arm."""
    # sanity: the fixed sentinel is exactly the extractor's no-cue default.
    assert _LEGACY_ARM_UNKNOWN_SENTINEL == "treatment"

    a = _num_key("drug x", "reduces a1c", 1.5, arm="treatment")
    b = _num_key("drug x", "reduces a1c", 1.1, arm="treatment")  # differs ONLY in value; both arm-unknown

    # The comparability view fails closed for a defaulted-arm key.
    assert _numeric_comparability_key(a) is None
    assert _numeric_comparability_key(b) is None
    # And no comparison is licensed between two arm-unknown findings.
    assert license_numeric_comparison(a, b) is None
    # Case/whitespace variants of the sentinel are equally unknown (defense-in-depth).
    assert _numeric_comparability_key(_num_key("drug x", "reduces a1c", 1.5, arm=" Treatment ")) is None
    # A defaulted-arm key is not comparable against a fully-known key either.
    good = _num_key("drug x", "reduces a1c", 1.9)  # arm="comparator_adjacent" (positively known)
    assert license_numeric_comparison(a, good) is None


def test_same_explicit_arm_all_matching_is_comparable():
    """(b) NO REGRESSION: two findings with the SAME explicitly-extracted arm and all other discriminators
    matching (differing values) ARE upgraded to a comparison — the real comparison path still works."""
    a = _num_key("drug x", "reduces a1c", 1.5, arm="comparator_adjacent")
    b = _num_key("drug x", "reduces a1c", 1.1, arm="comparator_adjacent")  # differs ONLY in value
    assert _numeric_comparability_key(a) is not None
    assert _numeric_comparability_key(b) is not None
    assert license_numeric_comparison(a, b) == "comparison"

    # A non-sentinel arm string (e.g. an alternate positively-known label) also compares normally.
    c = _num_key("drug y", "raises ldl", 3.0, arm="active")
    d = _num_key("drug y", "raises ldl", 2.4, arm="active")
    assert license_numeric_comparison(c, d) == "comparison"

    # Different explicit arms => not the same claim identity => fail closed (unchanged behavior).
    assert license_numeric_comparison(
        _num_key("drug x", "reduces a1c", 1.5, arm="comparator_adjacent"),
        _num_key("drug x", "reduces a1c", 1.1, arm="active"),
    ) is None


def test_off_flag_is_dark_path():
    """(c) OFF: with ``PG_NUMERIC_COMPARATOR`` unset the comparator gate reports disabled — the composer
    never consults the comparator (byte-identical dark path). The pure key/relation functions remain
    importable + deterministic; the fix lives entirely inside this flag-gated module."""
    prior = os.environ.pop("PG_NUMERIC_COMPARATOR", None)
    try:
        assert not numeric_comparator_enabled()
    finally:
        if prior is not None:
            os.environ["PG_NUMERIC_COMPARATOR"] = prior

    # Explicit truthy values enable the gate; falsy/unset disable it (mirrors numeric_comparator_enabled).
    for val, expected in (("1", True), ("true", True), ("on", True),
                          ("0", False), ("false", False), ("", False), ("off", False)):
        prior = os.environ.get("PG_NUMERIC_COMPARATOR")
        os.environ["PG_NUMERIC_COMPARATOR"] = val
        try:
            assert numeric_comparator_enabled() is expected, f"{val!r} -> {expected}"
        finally:
            if prior is None:
                os.environ.pop("PG_NUMERIC_COMPARATOR", None)
            else:
                os.environ["PG_NUMERIC_COMPARATOR"] = prior


def test_redesign_singleton_key_still_fails_closed():
    """Redesign keys never reach the comparator carrying ``"treatment"`` (build_merge_key singleton-forces a
    defaulted arm upstream). The already-forced ``__unresolved__`` singleton stays not-comparable — the new
    legacy guard is a strict NO-OP on it (tag != 'numeric')."""
    singleton = ("__unresolved__", "numeric", "clinical", "eid", "uid")
    assert _numeric_comparability_key(singleton) is None
    good = _num_key("drug x", "reduces a1c", 1.5)
    assert license_numeric_comparison(good, singleton) is None


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-x", "-q"]))
