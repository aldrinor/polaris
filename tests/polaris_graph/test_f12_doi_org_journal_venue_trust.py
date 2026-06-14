"""F12 (GH #1245 / D12) — doi.org-hosted canonical-DOI journals must NOT be
demoted to T4 just because the host is `doi.org`.

THE RUN-KILLER (observed on the workforce corpus, forensic ledger D12):
    R9's unverified-host guard demoted ~50 canonical-DOI journal articles
    (e.g. JEP 10.1257, JPE 10.1086) to T4 because `doi.org` is not on
    PEER_REVIEWED_JOURNAL_DOMAINS and those DOI prefixes are not in the
    hard-coded PEER_REVIEWED_DOI_PREFIXES allowlist. `weight_basis=tier_prior`
    for 803/803 sources, so the misclassification IS a credibility bug. On a
    clinical question whose pivotal trials resolve via doi.org, the resolved-
    venue T1 tier collapses and the strict clinical corpus-adequacy floor
    (min_t1_count=3) deterministically false-fires abort_corpus_inadequate,
    killing the mandatory clinical cert question.

THE FIX (surgical, weight-layer only — NO faithfulness gate touched):
    Trust the OpenAlex venue. A doi.org host with OpenAlex source_type=="journal"
    AND a non-empty venue is a peer-reviewed journal: widen R9's unverified-host
    EXEMPTION (never relaxing any verify gate). Scoped strictly to doi.org so the
    BUG-M-11 trade-content guard on non-DOI hosts is untouched, and placed so the
    SR/MA / narrative / guideline / conference-abstract / low-quality-OA branches
    still win.

The negative cases below are the faithfulness proof: the exemption fires ONLY
for (doi.org host) AND (OpenAlex journal) AND (non-empty venue), and the
demotion/secondary-tier behaviour is preserved everywhere else.
"""

from __future__ import annotations

from src.polaris_graph.retrieval.tier_classifier import (
    ClassificationSignals,
    TierLevel,
    _is_doi_org_journal_with_venue,
    classify_source_tier,
)


def _classify(
    url: str,
    title: str = "Generic study of X in Y",
    *,
    source_type: str = "journal",
    venue: str = "Journal of Economic Perspectives",
    pub_type: str = "article",
    is_peer_reviewed: bool = True,
    content_length: int = 8000,
) -> ClassificationSignals:
    sig = ClassificationSignals(
        url=url,
        title=title,
        publisher="",
        fetched_content_length=content_length,
        openalex_publication_type=pub_type,
        openalex_source_type=source_type,
        openalex_venue=venue,
        openalex_is_peer_reviewed=is_peer_reviewed,
        source_type_hint="",
    )
    return classify_source_tier(sig)


# ── The ACCEPT case (domain-independent): JEP / JPE on doi.org → T1 ──────────

def test_jep_doi_org_journal_with_venue_is_t1() -> None:
    """JEP (10.1257) canonical DOI on doi.org with an OpenAlex journal venue.
    Previously demoted to T4 by R9's unverified-host guard; must now be T1."""
    r = _classify(
        url="https://doi.org/10.1257/jep.29.3.3",
        title="Why Are There Still So Many Jobs? Automation and the Labor Market",
        venue="Journal of Economic Perspectives",
    )
    assert r.tier == TierLevel.T1, (r.tier, r.reasons)
    assert "R9_openalex_primary_study" in r.matched_rules
    assert "R9_openalex_unverified_host_demoted_to_t4" not in r.matched_rules


def test_jpe_doi_org_journal_with_venue_is_t1() -> None:
    """JPE (10.1086) canonical DOI on doi.org with an OpenAlex journal venue."""
    r = _classify(
        url="https://doi.org/10.1086/682386",
        title="The Race between Machine and Man in the Labor Market",
        venue="Journal of Political Economy",
    )
    assert r.tier == TierLevel.T1, (r.tier, r.reasons)
    assert "R9_openalex_unverified_host_demoted_to_t4" not in r.matched_rules


def test_dx_doi_org_host_variant_is_t1() -> None:
    """dx.doi.org is also a doi.org host (substring match) — same exemption."""
    r = _classify(
        url="https://dx.doi.org/10.1257/jep.29.3.3",
        title="Automation and the labor market cohort study",
        venue="Journal of Economic Perspectives",
    )
    assert r.tier == TierLevel.T1, (r.tier, r.reasons)


# ── Faithfulness-preservation negatives: the exemption never relaxes a gate ──

def test_doi_org_journal_venue_sr_ma_title_still_t2() -> None:
    """SR/MA branch fires BEFORE the unverified-host guard: stays T2, not T1."""
    r = _classify(
        url="https://doi.org/10.1257/aer.20200001",
        title="The Effect of AI on Wages: A Systematic Review and Meta-Analysis",
        venue="American Economic Review",
    )
    assert r.tier == TierLevel.T2, (r.tier, r.reasons)
    assert "R9_openalex_sr_or_ma" in r.matched_rules


def test_doi_org_journal_venue_narrative_title_still_t4() -> None:
    """Narrative-flavor branch fires BEFORE the unverified-host guard → T4."""
    r = _classify(
        url="https://doi.org/10.1257/jep.30.2.3",
        title="A Review of Automation: Perspectives for Clinicians",
        venue="Journal of Economic Perspectives",
    )
    assert r.tier == TierLevel.T4, (r.tier, r.reasons)
    assert "R9_openalex_narrative_review" in r.matched_rules


def test_doi_org_low_quality_oa_still_demoted_to_t4() -> None:
    """A doi.org/10.3390 (MDPI) work passes the venue exemption but then hits
    _is_low_quality_oa (which runs AFTER) → still T4. The low-quality-OA
    discriminator is preserved."""
    r = _classify(
        url="https://doi.org/10.3390/jcm14228079",
        title="Anticoagulation strategies in atrial fibrillation",
        venue="Journal of Clinical Medicine",
    )
    assert r.tier == TierLevel.T4, (r.tier, r.reasons)
    assert "R9_low_quality_oa_primary_demoted" in r.matched_rules


def test_doi_org_empty_venue_is_demoted_to_t4() -> None:
    """No resolved venue → no trust → R9 unverified-host demotion preserved."""
    r = _classify(
        url="https://doi.org/10.1257/jep.29.3.3",
        title="Automation and the labor market cohort study",
        venue="",
    )
    assert r.tier == TierLevel.T4, (r.tier, r.reasons)
    assert "R9_openalex_unverified_host_demoted_to_t4" in r.matched_rules


def test_doi_org_non_journal_source_type_is_demoted_to_t4() -> None:
    """source_type != 'journal' (e.g. repository) on doi.org → no exemption.
    Note: src_type != 'journal' also fails the is_peer_reviewed_hint, so this
    routes through R11 to T4 — the point is it is NOT granted T1."""
    r = _classify(
        url="https://doi.org/10.1257/wp.2024.001",
        title="Working paper on automation and the labor market",
        source_type="repository",
        venue="SSRN Working Papers",
        is_peer_reviewed=False,
    )
    assert r.tier == TierLevel.T4, (r.tier, r.reasons)
    assert "R9_openalex_primary_study" not in r.matched_rules


def test_non_doi_org_unverified_host_with_venue_still_t4() -> None:
    """SCOPE GUARD: the exemption is doi.org-only. A non-doi.org host that is
    NOT on the journal allowlist, even with an OpenAlex journal venue, must
    still be demoted (BUG-M-11 trade-content guard preserved)."""
    r = _classify(
        url="https://delveinsight-research.example.org/article/12345",
        title="Automation and the labor market: a primary analysis",
        venue="Some Indexed Venue",
    )
    assert r.tier == TierLevel.T4, (r.tier, r.reasons)
    assert "R9_openalex_unverified_host_demoted_to_t4" in r.matched_rules


def test_doi_org_in_path_of_other_host_still_t4() -> None:
    """SCOPE GUARD (Codex diff-gate iter-1 P1): a NON-doi.org host that embeds
    `doi.org/` in its PATH or QUERY (e.g. an open redirect) must NOT pass the
    parsed-host check — host parsing, not substring matching. Demotion preserved.
    """
    r = _classify(
        url="https://trade.example.com/redirect?u=https://doi.org/10.1257/jep.29.3.3",
        title="Automation and the labor market: a primary analysis",
        venue="Journal of Economic Perspectives",
    )
    assert r.tier == TierLevel.T4, (r.tier, r.reasons)
    assert "R9_openalex_unverified_host_demoted_to_t4" in r.matched_rules


# ── Helper unit tests (the precondition logic in isolation) ──────────────────

def test_helper_true_only_for_doi_org_journal_with_venue() -> None:
    def _sig(url: str, source_type: str, venue: str) -> ClassificationSignals:
        return ClassificationSignals(
            url=url, openalex_source_type=source_type, openalex_venue=venue,
        )

    assert _is_doi_org_journal_with_venue(
        _sig("https://doi.org/10.1086/682386", "journal", "JPE")) is True
    # dx.doi.org subdomain host also passes
    assert _is_doi_org_journal_with_venue(
        _sig("https://dx.doi.org/10.1086/682386", "journal", "JPE")) is True
    # missing each precondition individually -> False
    assert _is_doi_org_journal_with_venue(
        _sig("https://www.jacc.org/doi/10.1016/x", "journal", "JACC")) is False
    # doi.org embedded in PATH/QUERY of another host -> host parse rejects it
    assert _is_doi_org_journal_with_venue(
        _sig("https://t.example/r?u=https://doi.org/10.1/x", "journal", "JPE")) is False
    assert _is_doi_org_journal_with_venue(
        _sig("https://doi.org/10.1086/682386", "repository", "JPE")) is False
    assert _is_doi_org_journal_with_venue(
        _sig("https://doi.org/10.1086/682386", "journal", "")) is False
    assert _is_doi_org_journal_with_venue(
        _sig("", "journal", "JPE")) is False
