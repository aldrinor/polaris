"""I-bench-veracity-003 PR-1 (#1225): subtraction-safe source-breadth anti-concentration.

Unit tests for the within-tier distinct-source interleave + per-source saturation cap
helpers in `multi_section_generator`. These test the PURE reorder logic that decides
WHICH candidate spans the generator sees first — every faithfulness gate (strict_verify,
NLI-enforce, 4-role) is downstream and unchanged, so these tests assert the selection
invariants Codex's brief review locked: default-off byte-identity, tier preservation,
reserved-aware distinctness, soft cap with within-tier backfill, and source-key fallback.
"""

# Third-Party
import pytest

# Local
from src.polaris_graph.generator.multi_section_generator import (
    _build_source_key_fn,
    _normalize_source_key,
    _spread_within_tier,
)


def _evidence(specs):
    """specs: list of (ev_id, source_url) -> evidence rows."""
    return [{"evidence_id": e, "source_url": u} for e, u in specs]


def test_normalize_source_key():
    assert _normalize_source_key("https://A.com/") == "a.com"
    assert _normalize_source_key("http://a.com/p") == "a.com/p"
    assert _normalize_source_key("HTTPS://Example.com/Path/") == "example.com/path"
    assert _normalize_source_key("") is None
    assert _normalize_source_key(None) is None


def test_source_key_fallback_to_evidence_id():
    key = _build_source_key_fn(_evidence([("x", "https://e.com/a"), ("y", "")]))
    assert key("x") == "e.com/a"
    assert key("y").startswith("__evid__:")  # missing url -> its own source
    assert key("unknown").startswith("__evid__:")  # unmapped id -> its own source


def test_off_is_byte_identical():
    seq = ["a1", "a2", "b1", "c1"]
    key = _build_source_key_fn(
        _evidence([("a1", "http://A"), ("a2", "http://A"), ("b1", "http://B"), ("c1", "http://C")])
    )
    # both knobs off => input returned unchanged (default-off byte-identity)
    assert _spread_within_tier(seq, key, set(), 0, False) == seq


def test_interleave_surfaces_distinct_sources_first():
    seq = ["a1", "a2", "a3", "b1", "c1"]
    key = _build_source_key_fn(
        _evidence([("a1", "http://A"), ("a2", "http://A"), ("a3", "http://A"),
                   ("b1", "http://B"), ("c1", "http://C")])
    )
    out = _spread_within_tier(seq, key, set(), 0, True)
    # first three rows are three DISTINCT sources, not three of A
    assert {key(out[0]), key(out[1]), key(out[2])} == {"a", "b", "c"}
    # pure reorder: the SET of ev_ids is invariant
    assert sorted(out) == sorted(seq)


def test_reserved_aware_does_not_resurface_reserved_source_first():
    seq = ["a1", "b1", "b2"]
    key = _build_source_key_fn(_evidence([("a1", "http://A"), ("b1", "http://B"), ("b2", "http://B")]))
    # source A already represented in `reserved` (seen={"a"}) -> a fresh source leads
    out = _spread_within_tier(seq, key, {"a"}, 0, True)
    assert key(out[0]) == "b"
    assert sorted(out) == sorted(seq)


def test_per_source_cap_pushes_overflow_to_back_no_interleave():
    seq = ["a1", "a2", "a3", "b1"]
    key = _build_source_key_fn(
        _evidence([("a1", "http://A"), ("a2", "http://A"), ("a3", "http://A"), ("b1", "http://B")])
    )
    out = _spread_within_tier(seq, key, set(), 2, False)  # cap 2/source
    # a3 (3rd A) is pushed to the back (soft cap: moved, NOT dropped)
    assert out[-1] == "a3"
    assert sorted(out) == sorted(seq)  # nothing dropped


def test_per_source_cap_with_interleave_overflow_after_primary():
    seq = ["a1", "a2", "a3", "b1", "b2"]
    key = _build_source_key_fn(
        _evidence([("a1", "u/A"), ("a2", "u/A"), ("a3", "u/A"), ("b1", "u/B"), ("b2", "u/B")])
    )
    out = _spread_within_tier(seq, key, set(), 2, True)  # cap 2, interleave
    # the cap-exceeding 3rd A row is last (overflow); first rows alternate sources
    assert out[-1] == "a3"
    assert key(out[0]) != key(out[1])  # distinct sources lead
    assert sorted(out) == sorted(seq)


def test_cap_backfill_within_tier_below_never_promoted():
    """Caller pattern: spread above-tier, then below-tier with above's keys seen.
    A capped-out ABOVE-floor row must still precede any below-floor row."""
    above = ["a1", "a2", "a3"]   # source A x3
    below = ["d1"]               # source D (below floor)
    key = _build_source_key_fn(
        _evidence([("a1", "u/A"), ("a2", "u/A"), ("a3", "u/A"), ("d1", "u/D")])
    )
    sa = _spread_within_tier(above, key, set(), 2, True)
    sb = _spread_within_tier(below, key, {key(e) for e in sa}, 2, True)
    rest = sa + sb
    # a3 is the above-floor overflow (cap 2) — it MUST come before the below-floor d1
    assert rest.index("a3") < rest.index("d1")
    assert sorted(rest) == sorted(above + below)


def test_cap_does_not_strand_capacity_single_source():
    # one source, cap 1: overflow is moved back but NOT dropped, so truncation can
    # still backfill from it if capacity remains.
    seq = ["a1", "a2", "a3"]
    key = _build_source_key_fn(_evidence([("a1", "u/A"), ("a2", "u/A"), ("a3", "u/A")]))
    out = _spread_within_tier(seq, key, set(), 1, True)
    assert sorted(out) == sorted(seq)  # all three retained (backfill, not stranded)
    assert out[0] == "a1"  # primary first


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
