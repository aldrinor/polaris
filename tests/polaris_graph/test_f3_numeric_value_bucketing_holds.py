"""F3-3a (I-deepfix-001 #1369) — numeric VALUE-BUCKETING is UNTOUCHED by the qualitative widening.

The F3-3a change widens ONLY the QUALITATIVE candidate nomination (non-numeric claims). The
NUMERIC merge key + value-bucketing must stay byte-identical: two sources that share a subject
but assert DIFFERENT numeric values (0.42% vs 0.5%) must NEVER merge — a value collision is a
different fact, and merging it would be a fabricated corroboration (§-1.3 / the F3 anti-fab law).

This asserts the invariant at the merge-key level (``_finding_key``) and the NLI-bucket level
(``_cluster_value_bucket``), the two places the "0.42 vs 0.5 must never merge" rule lives.
"""
from __future__ import annotations

import types

from src.polaris_graph.synthesis.finding_dedup import _cluster_value_bucket, _finding_key


def _claim(value: float):
    """A minimal ExtractedNumericClaim-shaped object for the finding key (same subject/predicate/
    unit/dose/arm/endpoint — ONLY the numeric value differs)."""
    return types.SimpleNamespace(
        subject="output per worker",
        value=value,
        predicate="rose",
        unit="%",
        dose="",
        arm="",
        endpoint_phrase="",
    )


def test_finding_key_distinct_for_different_values_clinical():
    """CLINICAL key (verbatim strict subject): 0.42 and 0.5 yield DISTINCT keys => never merge."""
    k_042 = _finding_key(_claim(0.42), "ev_a", 0, exact_value=True, clinical=True)
    k_050 = _finding_key(_claim(0.50), "ev_b", 0, exact_value=True, clinical=True)
    assert k_042 != k_050, f"0.42 vs 0.5 must key distinctly (clinical); got {k_042} == {k_050}"
    # everything EXCEPT the value slot is identical (proves ONLY the value discriminates)
    assert k_042[0] == k_050[0] and k_042[1] == k_050[1] and k_042[3:] == k_050[3:]
    assert k_042[2] == 0.42 and k_050[2] == 0.5


def test_finding_key_distinct_for_different_values_nonclinical_folded():
    """NON-clinical folded-subject key: the subject folds but the value still discriminates, so
    0.42 vs 0.5 remain DISTINCT keys."""
    k_042 = _finding_key(_claim(0.42), "ev_a", 0, exact_value=True, clinical=False)
    k_050 = _finding_key(_claim(0.50), "ev_b", 0, exact_value=True, clinical=False)
    assert k_042 != k_050
    assert k_042[2] == 0.42 and k_050[2] == 0.5


def test_finding_key_distinct_for_different_values_rounded():
    """The legacy round(value, 3) slot (exact_value=False) still keeps 0.42 vs 0.5 distinct."""
    k_042 = _finding_key(_claim(0.42), "ev_a", 0, exact_value=False, clinical=True)
    k_050 = _finding_key(_claim(0.50), "ev_b", 0, exact_value=False, clinical=True)
    assert k_042 != k_050


def test_same_value_same_subject_keys_collide():
    """Control: the SAME subject AND the SAME value DO share a key (so the distinctness above is
    the value doing the work, not an unrelated field)."""
    k1 = _finding_key(_claim(0.42), "ev_a", 0, exact_value=True, clinical=True)
    k2 = _finding_key(_claim(0.42), "ev_b", 0, exact_value=True, clinical=True)
    assert k1 == k2


def test_value_bucket_separates_042_from_050():
    """The NLI value-bucket (used to gate which numeric clusters may be NLI-compared) puts 0.42 and
    0.5 in DIFFERENT buckets, so they can never be NLI-paired for a merge."""
    k_042 = _finding_key(_claim(0.42), "ev_a", 0, exact_value=True, clinical=True)
    k_050 = _finding_key(_claim(0.50), "ev_b", 0, exact_value=True, clinical=True)
    b_042 = _cluster_value_bucket(k_042, [], [])
    b_050 = _cluster_value_bucket(k_050, [], [])
    assert b_042 != b_050, f"value buckets must differ (0.42 vs 0.5); got {b_042} == {b_050}"
    assert b_042 == 0.42 and b_050 == 0.5
