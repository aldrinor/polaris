"""PATCH-C: FDA/EMA regulatory label dedup by setid.

Closes the PG_LB_SA_01 defect where four WEGOVY FDA label revisions
(2021 s000, 2023 s007, 2025 s024, 2026 s033) shipped as four separate
bibliography entries [26][27][28][29] despite being the same document.

Source pattern: FDA accessdata.fda.gov URL structure. The <NDC>s<REV>
pair in /drugsatfda_docs/label/<YEAR>/<NDC>s<REV>lbl.pdf shares the
application number (NDC) across revisions.
"""
from __future__ import annotations

from src.polaris_graph.wiki.wiki_builder import _build_bibliography


def _claim(url: str, ev_id: str, doi: str = "", year: int = 2024, title: str = "Doc") -> dict:
    return {
        "source_url": url,
        "source_title": title,
        "doi": doi,
        "year": year,
        "relevance_score": 0.8,
        "evidence_id": ev_id,
        "authors": [],
        "source_type": "regulatory",
    }


# ── Test 1: Four WEGOVY revisions collapse to one entry ───────────

def test_four_wegovy_revisions_collapse_to_one_entry():
    """NDC 215256 across revisions s000/s007/s024/s033 = one WEGOVY drug."""
    section_claims = {
        "s01": [
            _claim(
                "https://www.accessdata.fda.gov/drugsatfda_docs/label/2021/215256s000lbl.pdf",
                "ev_a", year=2021, title="WEGOVY 2021 label",
            ),
            _claim(
                "https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/215256s007lbl.pdf",
                "ev_b", year=2023, title="WEGOVY 2023 label",
            ),
            _claim(
                "https://www.accessdata.fda.gov/drugsatfda_docs/label/2025/215256s024lbl.pdf",
                "ev_c", year=2025, title="WEGOVY 2025 label",
            ),
            _claim(
                "https://www.accessdata.fda.gov/drugsatfda_docs/label/2026/215256s033lbl.pdf",
                "ev_d", year=2026, title="WEGOVY 2026 label",
            ),
        ],
    }
    bib = _build_bibliography(section_claims)

    assert len(bib) == 1, (
        f"PATCH-C failed: expected 1 entry after setid dedup, got {len(bib)}. "
        f"URLs: {[b['url'] for b in bib]}"
    )
    # All four evidence IDs preserved in the merged entry.
    assert set(bib[0]["evidence_ids"]) == {"ev_a", "ev_b", "ev_c", "ev_d"}


# ── Test 2: Different NDCs = different entries ────────────────────

def test_different_ndc_produces_distinct_entries():
    """WEGOVY (215256) and Ozempic (209637) are different drugs."""
    section_claims = {
        "s01": [
            _claim(
                "https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/215256s007lbl.pdf",
                "ev_a", year=2023, title="WEGOVY",
            ),
            _claim(
                "https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/209637s021lbl.pdf",
                "ev_b", year=2023, title="Ozempic",
            ),
        ],
    }
    bib = _build_bibliography(section_claims)
    assert len(bib) == 2


# ── Test 3: EMA product info revisions collapse ──────────────────

def test_ema_product_information_collapses_by_product_slug():
    """Same EMA product at different revision paths collapses."""
    section_claims = {
        "s01": [
            _claim(
                "https://www.ema.europa.eu/en/documents/product-information/ozempic-epar-product-information_en.pdf",
                "ev_a", title="Ozempic EMA 2024",
            ),
            _claim(
                "https://www.ema.europa.eu/en/documents/product-information/ozempic-epar-product-information_fr.pdf",
                "ev_b", title="Ozempic EMA 2024 (FR)",
            ),
        ],
    }
    bib = _build_bibliography(section_claims)
    assert len(bib) == 1
    assert set(bib[0]["evidence_ids"]) == {"ev_a", "ev_b"}


# ── Test 4: Non-regulatory URLs unaffected ───────────────────────

def test_regulatory_id_does_not_collide_with_academic_doi():
    """An FDA label and a peer-reviewed paper about the same drug
    must remain two distinct bibliography entries — setid and DOI
    live in different keyspaces."""
    section_claims = {
        "s01": [
            _claim(
                "https://www.accessdata.fda.gov/drugsatfda_docs/label/2023/215256s007lbl.pdf",
                "ev_a", year=2023, title="WEGOVY label",
            ),
            _claim(
                "https://www.nejm.org/doi/full/10.1056/NEJMoa2307563",
                "ev_b", doi="10.1056/NEJMoa2307563", year=2023,
                title="SELECT NEJM paper",
            ),
        ],
    }
    bib = _build_bibliography(section_claims)
    assert len(bib) == 2


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
