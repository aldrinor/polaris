"""Acceptance tests for the champion-side comparison-bundle builder.

Fully offline: loads the champion corpus, derives all eight facets from each row's
``direct_quote`` (nothing is inferred), and asserts the builder emits at least one
NON-TRIVIAL comparison bundle (>=2 members, a shared outcome, and — for a refusal —
a populated ``why``). Prints the bundle count and a couple of examples.

The builder is offline and regex-only (no LLM). ``build_bundles(rows, same_work_groups)``
is the flag-independent planning path; ``build_comparison_bundles(corpus)`` is the
default-OFF flag-gated entry point and must return ``[]`` when the flag is unset.
"""

import json
import os
from collections import Counter

import pytest

from src.polaris_graph.instruction.comparison_bundles import (
    BUNDLE_KINDS,
    build_bundles,
    build_comparison_bundles,
    is_enabled,
)

CORPUS_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "data", "cp4_corpus_s3gear_329.json",
)


@pytest.fixture(scope="module")
def corpus():
    with open(CORPUS_PATH, encoding="utf-8") as fh:
        return json.load(fh)


def test_flag_default_off():
    """The integration flag is default-OFF (OFF path is byte-identical today)."""
    assert is_enabled() is False


def test_build_comparison_bundles_off_is_empty(corpus):
    """Flag-gated entry point returns [] when the flag is unset."""
    assert build_comparison_bundles(corpus) == []


def test_build_comparison_bundles_on(corpus, monkeypatch):
    """Flag-gated entry point matches the direct builder when the flag is on."""
    monkeypatch.setenv("PG_COMPARISON_BUNDLES", "1")
    assert is_enabled() is True
    gated = build_comparison_bundles(corpus)
    direct = build_bundles(corpus["evidence"], corpus.get("same_work_groups"))
    assert len(gated) == len(direct)
    assert len(gated) >= 1


def test_nontrivial_bundle_with_why(corpus):
    """>=1 non-trivial bundle with >=2 members and a populated 'why'."""
    bundles = build_bundles(corpus["evidence"], corpus.get("same_work_groups"))
    assert bundles, "expected the builder to emit at least one bundle"

    # Every emitted bundle has the task-requested shape.
    for b in bundles:
        assert set(b) >= {
            "outcome", "kind", "members", "comparable", "why", "apparent_conflict",
            "evidence_tier", "shared", "varies", "score", "note",
        }
        assert b["kind"] in BUNDLE_KINDS
        # comparable <=> empty why (the honesty invariant).
        assert bool(b["why"]) == (not b["comparable"])

    non_trivial = [b for b in bundles if len(b["members"]) >= 2 and b["why"]]
    assert non_trivial, "expected >=1 non-trivial bundle (>=2 members, populated why)"


def test_no_self_corroboration(corpus):
    """No multi-member bundle pairs two rows of the SAME work (same_work_id guard)."""
    swid = {}
    for g in corpus.get("same_work_groups", []) or []:
        for eid in g.get("member_evidence_ids", []) or []:
            swid[eid] = g.get("same_work_id")
    bundles = build_bundles(corpus["evidence"], corpus.get("same_work_groups"))
    for b in bundles:
        if len(b["members"]) == 2:
            a, c = b["members"]
            ga, gc = swid.get(a), swid.get(c)
            if ga is not None and gc is not None:
                assert ga != gc, f"self-corroboration bundle across one work: {b['kind']} {b['members']}"


def test_bundle_stats(corpus, capsys):
    """Print bundle count + a couple of examples (informational, always passes)."""
    bundles = build_bundles(corpus["evidence"], corpus.get("same_work_groups"))
    by_kind = Counter(b["kind"] for b in bundles)
    comparable_n = sum(b["comparable"] for b in bundles)
    conflict_n = sum(b["apparent_conflict"] for b in bundles)

    lines = [
        "",
        "=== COMPARISON-BUNDLE STATS (champion corpus, 997 rows) ===",
        f"  TOTAL bundles          : {len(bundles)}",
        f"  by kind                : {dict(by_kind)}",
        f"  comparable=True        : {comparable_n}",
        f"  apparent_conflict=True : {conflict_n}",
        "",
        "  --- examples (top by score) ---",
    ]
    for b in bundles[:2]:
        lines.append(
            f"  [{b['kind']}] outcome={b['outcome']} members={b['members']} "
            f"score={b['score']} comparable={b['comparable']}"
        )
        lines.append(f"      shared={b['shared']} varies={b['varies']}")
        if b["why"]:
            lines.append(f"      why={b['why'][:2]}")
    # Show one refusal and one uncountered boundary if present.
    for kind in ("SAME_UNIT_OPPOSITE_DIRECTION", "NOT_A_COMPARISON", "UNCOUNTERED"):
        ex = next((b for b in bundles if b["kind"] == kind), None)
        if ex:
            lines.append(f"  [{kind} example] outcome={ex['outcome']} members={ex['members']} "
                         f"why={ex['why'][:1]}")

    with capsys.disabled():
        print("\n".join(lines))

    assert len(bundles) >= 1
