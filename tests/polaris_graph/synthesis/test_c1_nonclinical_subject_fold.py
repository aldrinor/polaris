"""I-deepfix-001 C1 (#1344) — non-clinical numeric-finding subject SIGNATURE.

FAIL-LOUD behavioral proof of the C1 EFFECT in real ``dedup_by_finding`` output:
NON-clinical numeric rows that assert the SAME claim with a SURFACE-varied subject
("e-commerce" / "ecommerce" / "E-Commerce") now CONSOLIDATE into ONE multi-origin
corroboration basket, while a genuinely DISTINCT subject ("biotech") never merges
and the CLINICAL key stays byte-identical (surface variants kept SEPARATE).

RED→GREEN: with ``PG_FINDING_DEDUP_NONCLINICAL_SUBJECT_FOLD=0`` (pre-C1 raw-surface
key) the hyphen variants stay split (max basket = 2, no 3-member basket); with the
fold ON they form one 3-member basket (corroboration_count = 3 independent hosts).

Uses the REAL B9 domain-agnostic extractor end-to-end (no mock). SPEND-FREE / offline.
Serialized per CLAUDE.md §8.4 (pure-python, no network, no LLM, no GPU).
"""
from __future__ import annotations

from types import SimpleNamespace

from src.polaris_graph.authority.data_loader import load_authority_data
from src.polaris_graph.synthesis.finding_dedup import (
    _finding_key,
    dedup_by_finding,
)

_GOV = load_authority_data()["psl_gov_suffixes"]


def _row(eid: str, url: str, quote: str) -> dict:
    return {
        "evidence_id": eid,
        "source_url": url,
        "url": url,
        "direct_quote": quote,
        "statement": quote,
        "tier": "T1",
        "authority_score": 0.6,
    }


# Same real-world claim, three SURFACE-varied subjects (hyphen / no-hyphen / case),
# each fetched from a DISTINCT host so a real basket earns corroboration_count 3.
_ECOM = [
    _row("e0", "https://alpha.com/a", "E-commerce growth reached 12 percent last year."),
    _row("e1", "https://beta.org/b", "Ecommerce growth reached 12 percent last year."),
    _row("e2", "https://gamma.net/c", "E-Commerce growth reached 12 percent last year."),
]
# A genuinely DIFFERENT subject that merely shares the number (12 percent growth).
_DISTINCT = _row("e3", "https://delta.io/d", "Biotech growth reached 12 percent last year.")


def _cluster_by_subject(res, subject_signature: str):
    """The finding cluster whose numeric finding_key subject slot == ``subject_signature``."""
    for c in res.clusters:
        k = c.finding_key
        if isinstance(k, tuple) and k and k[0] == subject_signature:
            return c
    return None


def test_c1_surface_varied_subjects_consolidate_into_one_basket(monkeypatch):
    """GREEN: the three surface variants fold to one 'ecommerce' signature and form a
    single 3-source corroboration basket; the distinct 'biotech' subject stays alone."""
    monkeypatch.setenv("PG_FINDING_DEDUP_NONCLINICAL_SUBJECT_FOLD", "1")
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    res = dedup_by_finding(_ECOM + [_DISTINCT], gov_suffixes=_GOV, domain="economics")

    ecom = _cluster_by_subject(res, "ecommerce")
    assert ecom is not None, "C1 fold did not form the 'ecommerce' basket"
    assert len(ecom.member_indices) == 3, (
        "C1 must consolidate ALL three surface variants (got "
        f"{len(ecom.member_indices)})"
    )
    assert ecom.corroboration_count == 3, (
        "the merged basket must carry 3 independent hosts as corroboration WEIGHT "
        f"(got {ecom.corroboration_count})"
    )

    # DISTINCT-fact guard: a different subject sharing the number never over-merges.
    biotech = _cluster_by_subject(res, "biotech")
    assert biotech is not None and len(biotech.member_indices) == 1, (
        "a genuinely distinct subject that merely shares a number must NOT merge"
    )


def test_c1_flag_off_restores_raw_surface_key_split(monkeypatch):
    """RED (pre-C1): with the fold OFF the raw-surface key keeps 'e-commerce' and
    'ecommerce' SEPARATE — no 3-member basket forms (the measured collapsed=0 seam)."""
    monkeypatch.setenv("PG_FINDING_DEDUP_NONCLINICAL_SUBJECT_FOLD", "0")
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")
    res = dedup_by_finding(_ECOM + [_DISTINCT], gov_suffixes=_GOV, domain="economics")

    sizes = sorted(len(c.member_indices) for c in res.clusters)
    assert 3 not in sizes, (
        "without the C1 fold the surface variants must NOT consolidate into a "
        f"3-member basket (cluster sizes {sizes})"
    )
    assert 2 in sizes, (
        "the two identical-surface 'e-commerce' rows still cluster on the raw key "
        f"(cluster sizes {sizes})"
    )


def test_c1_finding_key_clinical_verbatim_nonclinical_folds():
    """Contract: the CLINICAL key is byte-identical (raw surface => surface variants
    stay DISTINCT — the conservative-singleton guard kept verbatim); the NON-clinical
    key folds surface variants to one signature but never merges a different subject."""
    a = SimpleNamespace(
        subject="E-Commerce", predicate="growth", value=12.0, unit="percent",
        dose="", arm="treatment", endpoint_phrase="",
    )
    b = SimpleNamespace(
        subject="ecommerce", predicate="growth", value=12.0, unit="percent",
        dose="", arm="treatment", endpoint_phrase="",
    )
    d = SimpleNamespace(
        subject="biotech", predicate="growth", value=12.0, unit="percent",
        dose="", arm="treatment", endpoint_phrase="",
    )

    # CLINICAL (default): raw surface => the two surface variants are DIFFERENT keys.
    assert _finding_key(a, "x", 0, clinical=True) != _finding_key(b, "x", 0, clinical=True)
    # NON-clinical: folded signature => the two surface variants are the SAME key.
    assert _finding_key(a, "x", 0, clinical=False) == _finding_key(b, "x", 0, clinical=False)
    # NON-clinical distinct subject: never collides on a shared number.
    assert _finding_key(a, "x", 0, clinical=False) != _finding_key(d, "x", 0, clinical=False)
