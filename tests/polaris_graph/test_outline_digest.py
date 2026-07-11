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


# ── PUSH A: same-work-aware digest (work-level corroboration + singleton fold) ──────────────
def _same_work_evidence() -> list[dict]:
    """Six rows: a 3-member basket that is really 2 works (ev1==ev2), plus three singletons of
    which two (ev4==ev5) are the same work and ev6 is distinct."""
    return [
        {"evidence_id": "ev1", "tier": "T1", "title": "A", "statement": "claim one"},
        {"evidence_id": "ev2", "tier": "T1", "title": "A2", "statement": "claim two"},
        {"evidence_id": "ev3", "tier": "T2", "title": "B", "statement": "claim three"},
        {"evidence_id": "ev4", "tier": "T1", "title": "C", "statement": "s4"},
        {"evidence_id": "ev5", "tier": "T1", "title": "C2", "statement": "s5"},
        {"evidence_id": "ev6", "tier": "T3", "title": "D", "statement": "s6"},
    ]


def _same_work_cluster() -> list[SimpleNamespace]:
    return [SimpleNamespace(representative_index=0, member_indices=[0, 1, 2],
                            corroboration_count=3, member_hosts=[])]


_SAME_WORK_GROUPS = [
    {"member_evidence_ids": ["ev1", "ev2"], "canonical_index": 0, "same_work_id": "url:w1"},
    {"member_evidence_ids": ["ev4", "ev5"], "canonical_index": 3, "same_work_id": "url:w2"},
]


def test_same_work_none_is_byte_identical() -> None:
    """same_work_groups=None (default) must render byte-identical to omitting the argument."""
    ev, cl = _same_work_evidence(), _same_work_cluster()
    a = build_outline_digest(ev, cl, sanitizer=_IDENTITY)
    b = build_outline_digest(ev, cl, sanitizer=_IDENTITY, same_work_groups=None)
    assert a.render() == b.render()
    assert a.basket_lines[0].startswith("B00 [x3 sources:")  # legacy row-count head
    assert len(a.singleton_lines) == 3                        # no fold
    assert a.singleton_alias_ev_ids == {}


def test_same_work_basket_renders_work_level_keeping_all_members() -> None:
    ev, cl = _same_work_evidence(), _same_work_cluster()
    menu = build_outline_digest(ev, cl, sanitizer=_IDENTITY, same_work_groups=_SAME_WORK_GROUPS)
    line = menu.basket_lines[0]
    assert line.startswith("B00 [x2 works (3 rows):")   # 3 rows corroborate 2 distinct works
    assert "members: ev1,ev2,ev3" in line               # every member id still disclosed
    assert menu.basket_work_corroboration["B00"] == 2


def test_same_work_singletons_collapse_and_stay_covered() -> None:
    ev, cl = _same_work_evidence(), _same_work_cluster()
    menu = build_outline_digest(ev, cl, sanitizer=_IDENTITY, same_work_groups=_SAME_WORK_GROUPS)
    # ev4 + ev5 are one work => ONE singleton line (ev4 canonical, ev5 folded); ev6 stands alone.
    assert len(menu.singleton_lines) == 2
    assert menu.singleton_alias_ev_ids == {"ev4": ["ev5"]}
    ev4_line = [ln for ln in menu.singleton_lines if ln.startswith("ev4 ")][0]
    assert "(+1 same-work: ev5)" in ev4_line
    # every alias is still accounted for — 100%-of-pool invariant holds
    assert menu.covered_ev_ids() == {"ev1", "ev2", "ev3", "ev4", "ev5", "ev6"}


# ── ORCH-2 requirements block ───────────────────────────────────────────────
def test_requirements_block_empty_is_byte_identical_noappend() -> None:
    assert build_requirements_block(None, None) == ""
    assert build_requirements_block({}, {}) == ""


def test_requirements_block_required_sections_and_scope() -> None:
    bank = _bank()
    block = build_requirements_block(bank["deliverable"], bank["scope"])
    assert block.startswith("\n\nDELIVERABLE REQUIREMENTS:\n")
    assert "REQUIRES this section structure, in this order" in block
    # item 1c: required titles are rendered QUOTED (so the model copies the text inside the quotes,
    # not the list number) with an explicit "do NOT include the list number" instruction.
    assert '1. "Executive Summary"' in block and '4. "Cost' in block
    assert "do NOT include the list number" in block
    assert '"undersupplied": true' in block  # undersupplied disclosure rule stated
    assert "hospital formulary committee" in block
    assert "Vancouver" in block
    assert "Date window: 2019-2024" in block
    assert "Geography: United States" in block


def test_requirements_block_reads_object_spec() -> None:
    spec = SimpleNamespace(required_sections=["A", "B"], audience="", tone="formal",
                           reference_style="", length_target="")
    block = build_requirements_block(spec, None)
    assert '1. "A"; 2. "B"' in block  # item 1c: quoted required titles
    assert "formal" in block


# ── Fable fix wave (I-arch s4-outline): items 3, 4, 5, 6c, 10 ────────────────────────────────
from src.polaris_graph.generator.outline_digest import (  # noqa: E402
    _build_alias_map,
    _is_chrome_interstitial,
    _is_title_like,
    _normalized_title_key,
)


def _row(ev_id: str, title: str, stmt: str = "", tier: str = "T1") -> dict:
    return {"evidence_id": ev_id, "title": title, "statement": stmt, "tier": tier}


def _cl(rep: int, members: list[int], corr: int) -> SimpleNamespace:
    return SimpleNamespace(representative_index=rep, member_indices=members,
                           corroboration_count=corr, member_hosts=[])


def test_item3a_chrome_prefix_title_keys_identically() -> None:
    """item 3a: '(PDF) X' must key IDENTICALLY to 'X' (the leading 'pdf' is alnum and would
    otherwise split one work into two). The two rows fold to ONE work."""
    ev = [
        _row("e1", "GPTs are GPTs: Labor Market Impact Potential of LLMs"),
        _row("e2", "(PDF) GPTs are GPTs: Labor Market Impact Potential of LLMs"),
    ]
    alias = _build_alias_map([], ev)  # work-aware, cp3 empty => title fold only
    assert alias["e1"] == alias["e2"]
    # the raw normalized key of the clean title equals the chrome-stripped one
    assert _normalized_title_key("GPTs are GPTs: Labor Market Impact Potential of LLMs") \
        == _normalized_title_key("(PDF) GPTs are GPTs: Labor Market Impact Potential of LLMs")


def test_item3b_truncation_prefix_fold() -> None:
    """item 3b: a truncated title whose key is a PREFIX of the full title's key folds to one work."""
    ev = [
        _row("e1", "Experimental Evidence on the Productivity Effects of Generative AI at Work"),
        _row("e2", "Experimental Evidence on the Productivity Effects of ..."),
        _row("e3", "Experimental Evidence on the Productivity Effects of Generative AI…"),
    ]
    alias = _build_alias_map([], ev)
    assert alias["e1"] == alias["e2"] == alias["e3"]  # all one work


def test_item3b_prefix_fold_false_merge_guard_non_truncated_stays_separate() -> None:
    """item 2/3b guard (reproduced false merge): ev_044 'Artificial Intelligence and the Labor
    Market' (a distinct paper) is a full, NON-truncated title that merely happens to be a PREFIX of
    ev_073 '...- Sciences Po' (a different work). Because ev_044's title was never truncated, the
    prefix fold must NOT fire — the two stay two works. Only a TRUNCATED short key may prefix-fold."""
    ev = [
        _row("ev044", "Artificial Intelligence and the Labor Market"),
        _row("ev073", "Artificial Intelligence and the Labor Market - Sciences Po"),
    ]
    alias = _build_alias_map([], ev)
    # neither folds onto the other -> resolve to DIFFERENT work keys (each its own work)
    assert alias.get("ev044", "ev044") != alias.get("ev073", "ev073")


def test_item3b_truncated_variant_of_same_still_folds() -> None:
    """item 2/3b: the guard keeps REAL truncations folding — a truncated copy of ev_044's title
    (ending '...') DOES fold onto the full ev_044 title (the truncation signal is present)."""
    ev = [
        _row("ev044", "Artificial Intelligence and the Labor Market"),
        _row("ev044b", "Artificial Intelligence and the Labor Mark..."),
    ]
    alias = _build_alias_map([], ev)
    assert alias["ev044"] == alias["ev044b"]  # truncated variant folds onto the full title


def test_item4_false_merge_guard_two_cp3_works_stay_separate() -> None:
    """item 4: two DISTINCT cp3 works sharing one normalized title do NOT false-merge; each keeps
    its own cp3 key, and an unclaimed title-only third member folds onto the title key."""
    ev = [
        _row("e1", "Recommendation of the Council on Artificial Intelligence", tier="T3"),
        _row("e2", "Recommendation of the Council on Artificial Intelligence", tier="T3"),
        _row("e3", "Recommendation of the Council on Artificial Intelligence", tier="T3"),
    ]
    swg = [
        {"member_evidence_ids": ["e1"], "canonical_index": 0, "same_work_id": "doi:workA"},
        {"member_evidence_ids": ["e2"], "canonical_index": 1, "same_work_id": "doi:workB"},
    ]
    alias = _build_alias_map(swg, ev)
    assert alias["e1"] == "doi:workA"          # stays on its own cp3 key
    assert alias["e2"] == "doi:workB"          # stays on its own cp3 key
    assert alias["e1"] != alias["e2"]          # the two cp3 works are NOT merged
    assert alias["e3"] not in ("doi:workA", "doi:workB")  # unclaimed folds onto the title key


def test_item4_single_cp3_key_unifies_group() -> None:
    """item 4: a title group carrying exactly ONE cp3 key unifies the whole group onto it."""
    ev = [
        _row("e1", "GPTs are GPTs An Early Look at the Labor Market Impact"),
        _row("e2", "GPTs are GPTs An Early Look at the Labor Market Impact"),
    ]
    swg = [{"member_evidence_ids": ["e1"], "canonical_index": 0, "same_work_id": "doi:gpts"}]
    alias = _build_alias_map(swg, ev)
    assert alias["e1"] == "doi:gpts"
    assert alias["e2"] == "doi:gpts"


def _drow(ev_id: str, title: str, doi: str, url: str, tier: str = "T1") -> dict:
    return {"evidence_id": ev_id, "title": title, "statement": f"claim {ev_id}",
            "tier": tier, "doi": doi, "source_url": url}


def test_item5_doi_fold_same_doi_different_url_unify_one_work() -> None:
    """item 5 (DOI fold): three rows sharing ONE ``10.`` DOI at THREE distinct URLs with THREE
    distinct titles fold to a single ``doi:`` work — the same-DOI-different-URL split the cp3 URL
    keying missed."""
    ev = [
        _drow("d1", "Wages and AI A Randomized Study of Software Engineers", "10.5/paper", "https://arxiv.org/abs/1"),
        _drow("d2", "Press Release on the Software Engineer Wage Experiment", "10.5/paper", "https://newswire.example/2"),
        _drow("d3", "Blog Recap of the Engineer Wage Experiment Findings", "10.5/paper", "https://blog.example/3"),
    ]
    alias = _build_alias_map([], ev)  # work-aware, cp3 empty => DOI fold only
    assert alias["d1"] == alias["d2"] == alias["d3"] == "doi:10.5/paper"


def test_item5_doi_fold_distinct_dois_stay_separate() -> None:
    """item 5 guard: rows with DISTINCT DOIs are NOT folded (byte-identical to no-fold: each row is
    its own work)."""
    ev = [
        _drow("d1", "A Study Alpha With A Long Enough Distinctive Title", "10.5/alpha", "https://a/1"),
        _drow("d2", "A Study Beta With A Long Enough Distinctive Title", "10.5/beta", "https://b/2"),
    ]
    alias = _build_alias_map([], ev)
    assert "d1" not in alias and "d2" not in alias  # no fold => empty alias map


def test_item4_doi_two_multi_member_url_groups_shared_doi_stay_separate() -> None:
    """item 4 (DOI false-merge REFUSAL, the ruling case): TWO distinct MULTI-member cp3 ``url:``
    groups that happen to share ONE DOI must NOT be merged. Each stamped member keeps its own
    ``url:`` key; only the UNCLAIMED (non-cp3) same-DOI row folds onto the ``doi:`` key. A
    member-level override would SPLIT a cp3 group, so the refusal is the correct conservative choice
    — and the observability tripwire records exactly ONE guard hit."""
    ev = [
        _drow("a1", "Alpha Work Randomized Wage Study Of Engineers One", "10.9/shared", "https://a/1"),
        _drow("a2", "Alpha Work Mirror Copy At A Second Host Two Here", "10.9/shared", "https://a/2"),
        _drow("b1", "Beta Work A Completely Different Paper Title Three", "10.9/shared", "https://b/1"),
        _drow("b2", "Beta Work Mirror Copy At Another Host Four Here", "10.9/shared", "https://b/2"),
        _drow("u1", "Unclaimed Blog Recap Sharing The Same DOI Five", "10.9/shared", "https://u/1"),
    ]
    swg = [
        {"member_evidence_ids": ["a1", "a2"], "canonical_index": 0, "same_work_id": "url:groupA"},
        {"member_evidence_ids": ["b1", "b2"], "canonical_index": 1, "same_work_id": "url:groupB"},
    ]
    stats: dict[str, int] = {}
    alias = _build_alias_map(swg, ev, stats=stats)
    assert alias["a1"] == alias["a2"] == "url:groupA"   # stamped members keep their cp3 url: key
    assert alias["b1"] == alias["b2"] == "url:groupB"   # the OTHER cp3 group keeps its own url: key
    assert alias["a1"] != alias["b1"]                   # the two MULTI-member cp3 works are NOT merged
    assert alias["u1"] == "doi:10.9/shared"             # only the UNCLAIMED same-DOI row folds to doi:
    assert stats["doi_false_merge_guard_hits"] == 1     # tripwire fired exactly once (never silent)


def test_item5_doi_fold_end_to_end_corroboration_and_tripwire() -> None:
    """item 5 END-TO-END: build_outline_digest on the 3-row same-DOI-different-URL fixture reports
    basket_work_corroboration == 1 (one work, not three), and corroboration_profile's
    digest_disagreement tripwire then reads False (the digest no longer overcounts)."""
    import asyncio  # noqa: PLC0415
    from src.polaris_graph.outline.outline_agent import OutlineWorkspace  # noqa: PLC0415
    from src.polaris_graph.outline.outline_toolkit import _tool_corroboration_profile  # noqa: PLC0415

    ev = [
        _drow("d1", "Wages and AI A Randomized Study of Software Engineers", "10.5/paper", "https://arxiv.org/abs/1"),
        _drow("d2", "Press Release on the Software Engineer Wage Experiment", "10.5/paper", "https://newswire.example/2"),
        _drow("d3", "Blog Recap of the Engineer Wage Experiment Findings", "10.5/paper", "https://blog.example/3"),
    ]
    menu = build_outline_digest(ev, [_cl(0, [0, 1, 2], 3)], sanitizer=_IDENTITY, same_work_groups=[])
    # the digest now consolidates the same-DOI copies to ONE distinct work
    assert menu.basket_work_corroboration["B00"] == 1

    ws = OutlineWorkspace(research_question="q", ev_store={r["evidence_id"]: r for r in ev})
    ws.basket_menu = menu
    r = asyncio.run(_tool_corroboration_profile(ws, basket_id="B00"))
    prof = r.statistics["profiles"][0]
    assert prof["digest_work_corroboration"] == 1
    assert prof["distinct_works"] == 1
    assert prof["digest_disagreement"] is False  # digest agrees with the row-level recompute


def test_item5_baskets_sort_by_work_not_rows() -> None:
    """item 5: a 4-row/1-work basket sinks BELOW a 2-row/2-work basket (distinct works lead)."""
    ev = [
        _row("a1", "Same Paper Title That Is Quite Long Enough Here", tier="T5"),
        _row("a2", "Same Paper Title That Is Quite Long Enough Here", tier="T5"),
        _row("a3", "Same Paper Title That Is Quite Long Enough Here", tier="T5"),
        _row("a4", "Same Paper Title That Is Quite Long Enough Here", tier="T5"),
        _row("b1", "First Distinct Work On Some Topic Alpha Here"),
        _row("b2", "Second Distinct Work On Some Topic Beta Here"),
    ]
    clusters = [_cl(0, [0, 1, 2, 3], 4), _cl(4, [4, 5], 2)]
    menu = build_outline_digest(ev, clusters, sanitizer=_IDENTITY, same_work_groups=[])
    assert "x2 works (2 rows)" in menu.basket_lines[0]   # the 2-work basket LEADS
    assert "x1 works (4 rows)" in menu.basket_lines[1]   # the 1-work/4-row basket SINKS


def test_item6c_chrome_basket_tagged_and_sinks() -> None:
    """item 6c: an all-'Just a moment...' basket is TAGGED [CHROME] and sinks below a real basket."""
    ev = [
        _row("c1", "Just a moment...", stmt="Real Paper About X", tier="T7"),
        _row("c2", "Just a moment...", stmt="Real Paper About X", tier="T7"),
        _row("r1", "A Real On Topic Source Title Here Enough", stmt="finding one"),
        _row("r2", "Another Real On Topic Source Title Here", stmt="finding two"),
    ]
    clusters = [_cl(0, [0, 1], 2), _cl(2, [2, 3], 2)]
    menu = build_outline_digest(ev, clusters, sanitizer=_IDENTITY, same_work_groups=[])
    assert "[CHROME — failed fetch, do not anchor]" in "\n".join(menu.basket_lines)
    assert "CHROME" not in menu.basket_lines[0]   # real basket leads
    assert "CHROME" in menu.basket_lines[1]       # chrome basket sinks
    # kept for disclosure — 100%-of-pool invariant still holds (never dropped)
    assert menu.covered_ev_ids() == {"c1", "c2", "r1", "r2"}


def test_item6c_chrome_singleton_tagged_kept() -> None:
    """item 6c: a chrome singleton ('Access Denied') is tagged but KEPT (disclosure), head parses."""
    ev = [_row("s1", "Access Denied", tier="T3")]
    menu = build_outline_digest(ev, [], sanitizer=_IDENTITY)
    assert "[CHROME — failed fetch, do not anchor]" in menu.singleton_lines[0]
    assert menu.singleton_lines[0].split(" ", 1)[0] == "s1"   # head token still the ev_id
    assert menu.covered_ev_ids() == {"s1"}


def test_item6c_interstitial_predicate_conservative() -> None:
    """item 6c: exact/known interstitials only; an unknown/real title is NOT tagged (fail-open)."""
    assert _is_chrome_interstitial("Just a moment...") is True
    assert _is_chrome_interstitial("Attention Required! | Cloudflare") is True
    assert _is_chrome_interstitial("404") is True
    assert _is_chrome_interstitial("Access Denied") is True
    assert _is_chrome_interstitial("GPTs are GPTs: Labor Market Impact") is False
    assert _is_chrome_interstitial("The Moment of Truth in Labor Economics") is False


def test_item10_is_title_like_unicode_ellipsis_and_url_source() -> None:
    """item 10: unicode '…' tails and 'url source:' prefixes are title-like (join the ascii cases)."""
    assert _is_title_like("Some truncated heading…", "T") is True     # unicode ellipsis tail
    assert _is_title_like("URL Source: http://example.org/x", "T") is True  # url source prefix
    assert _is_title_like("[PDF] A Working Paper", "T") is True       # existing case still holds
    assert _is_title_like("A real claim sentence with a finding of 12.3%.", "Diff title") is False
