"""I-wire-001 (Codex iter-2 P1 #1) — the bare-DOI venue-corroboration split.

The U10 length-floor widening made ``_is_known_scholarly_venue`` accept a bare ``doi`` "10."
prefix (and a lone ``openalex_is_peer_reviewed`` flag) so a real journal fetched from a BARE-PDF
URL keeps its venue WEIGHT at the T7 length floor (a §-1.3 WEIGHT restoration, correct there).

But that SAME helper was ALSO the B2 LLM-tiering venue-corroboration predicate
(``credibility_llm_tiering._cap_uncorroborated_top_tier``), whose entire job is to CAP an
uncorroborated top-tier (T1/T2) LLM verdict resting on nothing but a bare DOI + a scholarly-
sounding title (the off-topic Russian-cosmetics ev_061 mis-tiered T1/0.95). Reusing the widened
helper there re-opened the cap: a bare-DOI-only row would satisfy corroboration and slip its
T1/T2 verdict past the cap.

The fix SPLITS the predicate: the B2 cap uses the STRICTER venue-only ``_is_corroborated_scholarly_venue``
(requires an actual recognized venue — host / peer-reviewed DOI prefix / OpenAlex JOURNAL venue —
EXCLUDING bare DOI and a lone peer-reviewed flag), WHILE the tier_classifier length-floor exemption
keeps the WIDENED ``_is_known_scholarly_venue``.

RED before the split: ``_is_corroborated_scholarly_venue`` does not exist (ImportError at collection)
AND ``_cap_uncorroborated_top_tier`` used the widened helper, so a bare-DOI-only row's T1 verdict
was NOT capped. GREEN after the split.

Offline + spend-free: no model / network / paid LLM. Faithfulness-NEUTRAL — the B2 cap is a
credibility WEIGHT (T1-T7); it never touches strict_verify / NLI / 4-role D8 / provenance /
span-grounding. NO ``unittest.mock`` (CLAUDE.md §9.4).
"""
from __future__ import annotations

import contextlib
import os

from src.polaris_graph.retrieval.credibility_llm_tiering import (
    _cap_uncorroborated_top_tier,
)
from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationResult,
    ClassificationSignals,
    TierLevel,
    _is_corroborated_scholarly_venue,
    _is_known_scholarly_venue,
)


@contextlib.contextmanager
def _env(**overrides: str):
    """Set env vars for the block, restoring prior values on exit (hermetic under pytest AND a
    direct ``python file.py`` run)."""
    saved: dict[str, str | None] = {k: os.environ.get(k) for k in overrides}
    try:
        for k, v in overrides.items():
            os.environ[k] = v
        yield
    finally:
        for k, prior in saved.items():
            if prior is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = prior


def _bare_doi_only_row() -> ClassificationSignals:
    """A scholarly-TITLED row whose ONLY scholarly signal is a bare ``doi`` "10." prefix: the URL is
    a bare-PDF host (NOT on PEER_REVIEWED_JOURNAL_DOMAINS, NOT a doi.org canonical DOI), there is NO
    OpenAlex venue / journal source_type, and OpenAlex did NOT resolve it peer-reviewed. This is the
    ev_061 shape a scholarly-looking scam page can also present."""
    return ClassificationSignals(
        url="https://cdn.files.example.org/uploads/paper.pdf",
        title="A Randomized Controlled Trial of a Clinical Intervention in Adults",
        doi="10.1234/foo.bar",
        openalex_source_type="",
        openalex_venue="",
        openalex_is_peer_reviewed=None,
        fetched_content_length=200,  # short stub (would hit the T7 length floor)
    )


def _real_openalex_journal_row() -> ClassificationSignals:
    """A GENUINELY corroborated venue: OpenAlex resolved a JOURNAL source_type WITH a venue name."""
    return ClassificationSignals(
        url="https://example.com/article/123",
        title="A Randomized Controlled Trial of a Clinical Intervention in Adults",
        openalex_source_type="journal",
        openalex_venue="The Lancet",
        fetched_content_length=5000,
    )


def _t1_llm() -> ClassificationResult:
    return ClassificationResult(
        tier=TierLevel.T1, confidence=0.95, matched_rules=["llm_tiering"],
    )


def _rules_floor(tier: TierLevel = TierLevel.T6) -> ClassificationResult:
    return ClassificationResult(tier=tier, confidence=1.0, matched_rules=["rules_floor"])


# ─────────────────────────────────────────────────────────────────────────────
# 1) THE regression: a bare-DOI-only row's uncorroborated T1 verdict is STILL CAPPED.
# ─────────────────────────────────────────────────────────────────────────────

def test_bare_doi_only_top_tier_verdict_is_still_capped() -> None:
    """The B2 cap MUST still fire for a bare-DOI-only row: its T1 LLM verdict is capped to the
    deterministic rules-floor. RED before the split (the cap used the widened helper, which
    treats a bare DOI as a venue -> NOT capped)."""
    signals = _bare_doi_only_row()
    llm_res = _t1_llm()
    floor_res = _rules_floor(TierLevel.T6)
    with _env(PG_TIER_REQUIRE_VENUE_CORROBORATION="1"):
        capped = _cap_uncorroborated_top_tier(llm_res, signals, floor_res)
    # The uncorroborated top-tier verdict is REPLACED by the rules-floor (cap applied).
    assert capped is floor_res, (capped.tier if capped else None)


# ─────────────────────────────────────────────────────────────────────────────
# 2) The two predicates are correctly SPLIT for the bare-DOI row.
# ─────────────────────────────────────────────────────────────────────────────

def test_bare_doi_split_keeps_length_floor_weight_but_denies_corroboration() -> None:
    """The tier_classifier length-floor exemption keeps a real journal's WEIGHT (widened helper is
    True), WHILE the B2 corroboration predicate denies a bare DOI (strict helper is False)."""
    signals = _bare_doi_only_row()
    # Length-floor venue-authority exemption is PRESERVED (widened definition) — a bare-PDF real
    # journal still keeps its venue weight rather than being demoted to the T7 length floor.
    assert _is_known_scholarly_venue(signals) is True
    # B2 corroboration is DENIED (strict definition) — a bare DOI is not a recognized venue.
    assert _is_corroborated_scholarly_venue(signals) is False


# ─────────────────────────────────────────────────────────────────────────────
# 3) A GENUINELY corroborated venue is NOT capped (the cap only lowers uncorroborated top tiers).
# ─────────────────────────────────────────────────────────────────────────────

def test_real_openalex_journal_top_tier_is_not_capped() -> None:
    """A resolved OpenAlex JOURNAL-with-venue corroborates, so its T1 LLM verdict is KEPT (§-1.3:
    the cap only ever LOWERS an uncorroborated top tier — never a genuine venue)."""
    signals = _real_openalex_journal_row()
    assert _is_corroborated_scholarly_venue(signals) is True
    llm_res = _t1_llm()
    floor_res = _rules_floor(TierLevel.T6)
    with _env(PG_TIER_REQUIRE_VENUE_CORROBORATION="1"):
        kept = _cap_uncorroborated_top_tier(llm_res, signals, floor_res)
    assert kept is llm_res
    assert kept.tier == TierLevel.T1


# ─────────────────────────────────────────────────────────────────────────────
# 4) Kill-switch OFF => byte-identical legacy: even the bare-DOI row is NOT capped.
# ─────────────────────────────────────────────────────────────────────────────

def test_killswitch_off_does_not_cap_bare_doi_row() -> None:
    """PG_TIER_REQUIRE_VENUE_CORROBORATION=0 reverts to legacy: no cap is applied at all."""
    signals = _bare_doi_only_row()
    llm_res = _t1_llm()
    floor_res = _rules_floor(TierLevel.T6)
    with _env(PG_TIER_REQUIRE_VENUE_CORROBORATION="0"):
        kept = _cap_uncorroborated_top_tier(llm_res, signals, floor_res)
    assert kept is llm_res


if __name__ == "__main__":
    test_bare_doi_only_top_tier_verdict_is_still_capped()
    print("[1] bare-DOI T1 verdict STILL capped: PASS")
    test_bare_doi_split_keeps_length_floor_weight_but_denies_corroboration()
    print("[2] split: length-floor weight kept, corroboration denied: PASS")
    test_real_openalex_journal_top_tier_is_not_capped()
    print("[3] genuine OpenAlex journal NOT capped: PASS")
    test_killswitch_off_does_not_cap_bare_doi_row()
    print("[4] kill-switch OFF => no cap (legacy): PASS")
    print("ALL BARE-DOI CORROBORATION-CAP TESTS PASSED")
