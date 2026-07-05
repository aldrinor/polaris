"""I-deepfix-001 tail-B1 (#1344) finding #7 — source-necessity reconciled with the four-role D8 gate.

RED/GREEN: a body-cited bibliography number that is D8-VERIFIED but span-basket-UNVERIFIED must stay
in the numbered bibliography (never quarantined -> no dangling [N] marker) and must count toward the
necessity ratio. Before the fix, ``zero_support_bib_nums`` had no D8 allowlist so such a number was
moved to the "supports no report claim" ledger. Offline, $0.
"""
from __future__ import annotations

import importlib

sn = importlib.import_module("src.polaris_graph.synthesis.source_necessity")


# The drb_72 case: [7] Eloundou is cited in the body and D8 settled its framework claim VERIFIED, but
# its isolated-span basket (46%) is span-unverified, so span-support says zero. [6] and [8] have real
# span support.
_SUPPORT_BY_NUM = {6: ["c06"], 8: ["c08"]}  # 7 has NO span support
_CITED = [6, 7, 8]


def test_zero_support_quarantines_span_unverified_cited_num_without_allowlist():
    """RED anchor: with NO D8 allowlist, a cited-but-span-unverified [7] IS a quarantine target."""
    zero = sn.zero_support_bib_nums(_SUPPORT_BY_NUM, _CITED)
    assert zero == {7}, f"pre-fix behaviour: [7] quarantined as zero-support; got {zero}"


def test_zero_support_never_quarantines_d8_verified_cited_num():
    """GREEN: [7] is D8-VERIFIED + body-cited, so it is NEVER a quarantine target."""
    zero = sn.zero_support_bib_nums(_SUPPORT_BY_NUM, _CITED, d8_verified_cited_nums={7})
    assert 7 not in zero, "a D8-VERIFIED cited number must never be quarantined (no dangling marker)"
    assert zero == set(), f"only [7] was span-unverified and it is protected; got {zero}"


def test_compute_necessity_counts_d8_verified_source():
    """GREEN: the D8-VERIFIED cited [7] counts as NECESSARY (load-bearing) and is not zero-support."""
    support_by_src = {6: ["c06"], 7: [], 8: ["c08"]}
    nec = sn.compute_source_necessity(support_by_src, _CITED, d8_verified_cited_nums={7})
    assert "7" in nec.necessary_ids, "D8-VERIFIED source must be credited necessary"
    assert "7" not in nec.zero_support_ids, "D8-VERIFIED source must not be reported zero-support"
    # 6, 7, 8 are each the SOLE supporter of a distinct claim -> all necessary; ratio 3/3.
    assert nec.necessary_sources == 3 and nec.listed_sources == 3
    assert nec.necessity_ratio == 1.0


def test_compute_necessity_without_allowlist_drops_span_unverified_source():
    """RED anchor: without the allowlist, [7] is zero-support and does NOT count toward necessity."""
    support_by_src = {6: ["c06"], 7: [], 8: ["c08"]}
    nec = sn.compute_source_necessity(support_by_src, _CITED)
    assert "7" in nec.zero_support_ids
    assert "7" not in nec.necessary_ids
    assert nec.necessary_sources == 2  # only 6 and 8


def test_retype_keeps_d8_verified_entry_in_bibliography():
    """GREEN: the [7] entry stays under ## Bibliography (not moved to the necessity ledger), so its
    in-text marker never dangles — even if a stale caller passes 7 in zero_support_nums."""
    biblio = (
        "## Bibliography\n"
        "[6] Source six. https://ex.org/6\n"
        "[7] Eloundou et al. GPTs are GPTs. https://ex.org/7\n"
        "[8] Source eight. https://ex.org/8\n"
    )
    nec = sn.compute_source_necessity(
        {6: ["c06"], 7: [], 8: ["c08"]}, _CITED, d8_verified_cited_nums={7}
    )
    # Belt-and-braces: even a stale zero_support_nums containing 7 must NOT move it.
    out = sn.retype_bibliography_by_source_necessity(
        biblio, {7}, nec, d8_verified_cited_nums={7}
    )
    # [7]'s entry line still sits under the Bibliography heading (kept block), never in a ledger.
    assert "[7] Eloundou" in out
    bib_header, _, ledger = out.partition(sn._LEDGER_HEADER)
    assert "[7] Eloundou" in bib_header, "[7] must remain in the numbered bibliography, not the ledger"
    assert "[7] Eloundou" not in ledger


def test_retype_still_quarantines_a_genuine_zero_support_entry():
    """A genuinely zero-support, NON-D8-verified cited entry is still quarantined (fix is targeted)."""
    biblio = (
        "## Bibliography\n"
        "[6] Source six. https://ex.org/6\n"
        "[7] Padding source. https://ex.org/7\n"
    )
    nec = sn.compute_source_necessity({6: ["c06"], 7: []}, [6, 7])
    out = sn.retype_bibliography_by_source_necessity(biblio, {7}, nec)
    _, _, ledger = out.partition(sn._LEDGER_HEADER)
    assert "[7] Padding source" in ledger, "a true zero-support entry is still quarantined"
