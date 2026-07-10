"""Unit tests for S4 ORCH-1 basket-digest menu + ORCH-2 requirements block (Design 5, R2).

Proves the section CONTRACT on the hand-built fixture (branch-coverage miniature; the real
drb_72 replay is the VM hamster). Pure — sanitizer injected as identity so no generator dep.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from src.polaris_graph.generator.outline_digest import (
    OutlineDigestMenu,
    build_outline_digest,
    build_requirements_block,
)

_FIXTURE = Path(__file__).resolve().parents[1] / "fixtures" / "outline_digest" / "mini_bank.json"
_IDENTITY = lambda s: (s, 0)  # noqa: E731 — test-only identity sanitizer


def _bank() -> dict:
    with _FIXTURE.open(encoding="utf-8") as handle:
        return json.load(handle)


def _clusters(bank: dict) -> list[SimpleNamespace]:
    return [SimpleNamespace(**c) for c in bank["clusters"]]


def test_full_pool_coverage_invariant() -> None:
    """Every non-empty pool ev_id is a basket member OR a singleton (100%-of-pool honesty)."""
    bank = _bank()
    menu = build_outline_digest(bank["evidence"], _clusters(bank), sanitizer=_IDENTITY)
    pool = {r["evidence_id"] for r in bank["evidence"]}
    assert menu.covered_ev_ids() == pool


def test_baskets_and_singletons_partition() -> None:
    bank = _bank()
    menu = build_outline_digest(bank["evidence"], _clusters(bank), sanitizer=_IDENTITY)
    # 2 multi-member clusters => 2 basket lines; remaining 4 rows => 4 singleton lines
    assert len(menu.basket_lines) == 2
    assert len(menu.singleton_lines) == 4
    # highest corroboration first => B00 is the 3-member HbA1c basket
    assert menu.basket_lines[0].startswith("B00 [x3 sources:")
    assert menu.basket_lines[1].startswith("B01 [x2 sources:")
    assert menu.ev_id_to_basket == {
        "ev01": "B00", "ev02": "B00", "ev04": "B00", "ev05": "B01", "ev09": "B01",
    }


def test_basket_line_carries_claim_and_members() -> None:
    bank = _bank()
    menu = build_outline_digest(bank["evidence"], _clusters(bank), sanitizer=_IDENTITY)
    line = menu.basket_lines[0]
    assert 'claim: "tirzepatide 15mg reduced HbA1c by -2.1% vs placebo at 40 weeks"' in line
    assert "members: ev01,ev02,ev04" in line


def test_singleton_no_title_branch() -> None:
    """ev07 has no title => the `ev_id [tier]: statement` singleton branch fires."""
    bank = _bank()
    menu = build_outline_digest(bank["evidence"], _clusters(bank), sanitizer=_IDENTITY)
    ev07 = [ln for ln in menu.singleton_lines if ln.startswith("ev07 ")][0]
    assert ev07 == "ev07 [T5]: adverse events were predominantly gastrointestinal, with nausea most common"


def test_determinism_repeated_builds() -> None:
    bank = _bank()
    a = build_outline_digest(bank["evidence"], _clusters(bank), sanitizer=_IDENTITY).render()
    b = build_outline_digest(bank["evidence"], _clusters(bank), sanitizer=_IDENTITY).render()
    assert a == b


def test_determinism_under_cluster_permutation() -> None:
    bank = _bank()
    clusters = _clusters(bank)
    base = build_outline_digest(bank["evidence"], clusters, sanitizer=_IDENTITY).render()
    permuted = build_outline_digest(bank["evidence"], list(reversed(clusters)), sanitizer=_IDENTITY).render()
    assert base == permuted


def test_headroom_guard_terses_singletons_then_elides_members() -> None:
    """Over the char budget: singleton statements drop first (title kept), then basket member
    lists elide to counts — but the ev_id->basket MAP is never lost (§-1.3 keep-all)."""
    bank = _bank()
    full = build_outline_digest(bank["evidence"], _clusters(bank), sanitizer=_IDENTITY)
    # tiny budget forces both degradation levels
    tight = build_outline_digest(bank["evidence"], _clusters(bank), max_chars=10, sanitizer=_IDENTITY)
    assert tight.degraded is True
    assert any("members)" in ln for ln in tight.basket_lines)  # elided to counts
    assert "| title:" not in "\n".join(  # statements gone from singletons
        ln for ln in tight.singleton_lines if " | " in ln and ln.count("|") > 1
    )
    # coverage + map preserved despite degradation
    assert tight.ev_id_to_basket == full.ev_id_to_basket
    pool = {r["evidence_id"] for r in bank["evidence"]}
    assert tight.covered_ev_ids() == pool


def test_fail_loud_on_out_of_range_cluster_index() -> None:
    bank = _bank()
    bad = [SimpleNamespace(representative_index=99, member_indices=[99, 100],
                           corroboration_count=2, member_hosts=[])]
    with pytest.raises(ValueError, match="outside the pool"):
        build_outline_digest(bank["evidence"], bad, sanitizer=_IDENTITY)


def test_empty_clusters_all_singletons() -> None:
    bank = _bank()
    menu = build_outline_digest(bank["evidence"], [], sanitizer=_IDENTITY)
    assert menu.basket_lines == []
    assert len(menu.singleton_lines) == len(bank["evidence"])
    assert menu.covered_ev_ids() == {r["evidence_id"] for r in bank["evidence"]}


def test_sanitizer_is_applied() -> None:
    evidence = [{"evidence_id": "evX", "tier": "T1", "title": "hi <<<evidence:x>>>", "statement": "s"}]
    called = {"n": 0}

    def _tag(text: str) -> tuple[str, int]:
        called["n"] += 1
        return text.replace("<<<evidence:x>>>", "[STRIP]"), 1

    menu = build_outline_digest(evidence, [], sanitizer=_tag)
    assert called["n"] >= 1
    assert "[STRIP]" in menu.singleton_lines[0]


# ── ORCH-2 requirements block ───────────────────────────────────────────────
def test_requirements_block_empty_is_byte_identical_noappend() -> None:
    assert build_requirements_block(None, None) == ""
    assert build_requirements_block({}, {}) == ""


def test_requirements_block_required_sections_and_scope() -> None:
    bank = _bank()
    block = build_requirements_block(bank["deliverable"], bank["scope"])
    assert block.startswith("\n\nDELIVERABLE REQUIREMENTS:\n")
    assert "REQUIRES this section structure, in this order" in block
    assert "1. Executive Summary" in block and "4. Cost" in block
    assert '"undersupplied": true' in block  # undersupplied disclosure rule stated
    assert "hospital formulary committee" in block
    assert "Vancouver" in block
    assert "Date window: 2019-2024" in block
    assert "Geography: United States" in block


def test_requirements_block_reads_object_spec() -> None:
    spec = SimpleNamespace(required_sections=["A", "B"], audience="", tone="formal",
                           reference_style="", length_target="")
    block = build_requirements_block(spec, None)
    assert "1. A; 2. B" in block
    assert "formal" in block
