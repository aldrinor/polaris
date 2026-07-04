"""I-deepfix-001 (#1344) WORKSTREAM H — CLEAN RENDER — behavioral tests for H1/H2/H3.

Each test proves the FIX EFFECT in real rendered output (not a flag-check / tautology): a
RED baseline with the fix OFF shows the defect, a GREEN run with the fix ON (default) shows
it repaired. Offline, $0 — no LLM, no network, no GPU.

H1 — ONE shared render chokepoint (``sanitize_rendered_report``) REPAIRS every claim unit by
     stripping leaked SOURCE-INTERNAL in-text citation markers (bare ``(1, 2)`` numeral groups
     that point at the source's OWN bibliography, not the report's ``[N]`` provenance).
H2 — the glued single-paragraph "Corroborated Weighted Findings" enrichment blob is SPLIT into
     one bullet per finding, each carrying ONLY its own ``[N]`` marker (no mis-attribution).
H3 — the per-claim corroboration HEADER's member-quote fallback is drawn ONLY from an
     ENTAILMENT_VERIFIED member; a basket with no verified member falls to the clean source
     TITLE instead of asserting an unverified member's sentence as a verified claim.

FAITHFULNESS: every H fix is render-text-only / suppress-or-reflow — no strict_verify / NLI /
4-role D8 / span-grounding / provenance verdict, source, or count is ever touched.
"""
from __future__ import annotations

import pytest

from src.polaris_graph.generator import weighted_enrichment as we


# ─────────────────────────────────────────────────────────────────────────────
# H1 — source-internal ref-marker strip at the single render chokepoint
# ─────────────────────────────────────────────────────────────────────────────
_H1_REPORT = (
    "# Research report: automation\n\n"
    "## Efficacy\n\n"
    "Automation raised manufacturing output by twelve percent (1, 2) [3]. "
    "Wage growth slowed in the most exposed occupations (4; 5; 6) [7].\n"
)


def test_h1_strips_leaked_source_internal_ref_markers_in_rendered_body(monkeypatch):
    monkeypatch.delenv(we._RENDER_SEAM_REF_STRIP_ENV, raising=False)
    clean, _ = we.sanitize_rendered_report(_H1_REPORT)
    # EFFECT: the leaked source-internal numeral groups are gone from the rendered body...
    assert "(1, 2)" not in clean, clean
    assert "(4; 5; 6)" not in clean, clean
    # ...while the report's OWN [N] provenance markers survive verbatim (never mis-stripped).
    assert "[3]" in clean and "[7]" in clean, clean
    # the claim prose itself is intact (repair-first, not a drop).
    assert "Automation raised manufacturing output by twelve percent" in clean
    assert "Wage growth slowed in the most exposed occupations" in clean


def test_h1_off_is_byte_identical_and_shows_the_defect(monkeypatch):
    """RED baseline: with the kill-switch OFF the leaked marker survives (the defect)."""
    monkeypatch.setenv(we._RENDER_SEAM_REF_STRIP_ENV, "0")
    clean, _ = we.sanitize_rendered_report(_H1_REPORT)
    assert "(1, 2)" in clean, clean  # defect present when the fix is disabled


def test_h1_does_not_touch_non_citation_parentheticals():
    """High-precision: a solitary numeral, a 4-digit year, and a numeral+word parenthetical stay."""
    assert we.strip_source_internal_refs("A single point (3) is kept.") == "A single point (3) is kept."
    assert we.strip_source_internal_refs("Published (2020) and cited.") == "Published (2020) and cited."
    assert (
        we.strip_source_internal_refs("Compared across (1, 2, or 3 doses).")
        == "Compared across (1, 2, or 3 doses)."
    )


# ─────────────────────────────────────────────────────────────────────────────
# H2 — split the glued Corroborated Weighted Findings blob
# ─────────────────────────────────────────────────────────────────────────────
_H2_REPORT = (
    "# Research report: automation\n\n"
    "## Corroborated Weighted Findings\n\n"
    "Automation raised output by twelve percent in manufacturing [3]. "
    "Wage growth slowed in exposed occupations [4]. "
    "Reskilling programs cut displacement risk substantially [5].\n"
)


def _cwf_bullets(md: str) -> list[str]:
    out: list[str] = []
    in_cwf = False
    for line in md.split("\n"):
        if line.startswith("#"):
            in_cwf = "corroborated weighted findings" in line.lower()
            continue
        if in_cwf and line.startswith("- "):
            out.append(line)
    return out


def test_h2_splits_glued_blob_into_one_bullet_per_finding(monkeypatch):
    monkeypatch.delenv(we._CWF_SPLIT_FINDINGS_ENV, raising=False)
    clean, _ = we.sanitize_rendered_report(_H2_REPORT)
    bullets = _cwf_bullets(clean)
    # EFFECT: three glued findings become three separate bullets (de-blobbed).
    assert len(bullets) == 3, clean
    # Each bullet carries ONLY its OWN [N] marker — no welded mis-attribution.
    assert bullets[0].count("[") == 1 and "[3]" in bullets[0], bullets
    assert bullets[1].count("[") == 1 and "[4]" in bullets[1], bullets
    assert bullets[2].count("[") == 1 and "[5]" in bullets[2], bullets
    # No single line still concatenates all three findings' markers (the blob is gone).
    for line in clean.split("\n"):
        assert not ("[3]" in line and "[4]" in line and "[5]" in line), line


def test_h2_off_leaves_the_glued_paragraph_as_one_line(monkeypatch):
    """RED baseline: with the kill-switch OFF the enrichment body stays ONE glued paragraph line."""
    monkeypatch.setenv(we._CWF_SPLIT_FINDINGS_ENV, "0")
    clean, _ = we.sanitize_rendered_report(_H2_REPORT)
    assert not _cwf_bullets(clean), clean  # no per-finding bullets
    glued = [
        l for l in clean.split("\n")
        if "[3]" in l and "[4]" in l and "[5]" in l
    ]
    assert glued, clean  # the single glued line survives (the defect)


def test_h2_does_not_bulletise_a_non_enrichment_body(monkeypatch):
    monkeypatch.delenv(we._CWF_SPLIT_FINDINGS_ENV, raising=False)
    report = (
        "## Efficacy\n\n"
        "First finding about the effect [1]. Second finding about another outcome [2].\n"
    )
    clean, _ = we.sanitize_rendered_report(report)
    # Ordinary sections are NOT reflowed into bullets (over-split guard) — one line, both markers.
    body = [l for l in clean.split("\n") if "[1]" in l and "[2]" in l]
    assert body, clean


# ─────────────────────────────────────────────────────────────────────────────
# H3 — corroboration header from a VERIFIED member / clean title, never an unverified claim
# ─────────────────────────────────────────────────────────────────────────────
def _load_sweep():
    import scripts.run_honest_sweep_r3 as rs  # noqa: PLC0415 — heavy module, imported lazily
    return rs


def test_h3_header_falls_to_clean_title_not_an_unverified_member(monkeypatch):
    rs = _load_sweep()
    basket = {
        # representative claim_text is page-furniture chrome -> forces the member-quote fallback
        "claim_text": "ISSN: 1234-5678 Cite this paper as:",
        "supporting_members": [
            # the VERIFIED member's quote yields no complete sentence (truncated frag)...
            {"member_tier": "ENTAILMENT_VERIFIED", "direct_quote": "truncated frag ..."},
            # ...an UNVERIFIED member DOES carry a clean sentence.
            {
                "member_tier": "UNVERIFIED",
                "direct_quote": (
                    "Unverified source asserts productivity collapsed by ninety percent "
                    "overnight everywhere."
                ),
            },
        ],
    }
    title = "Automation And Factory Output: Evidence From Plants"
    monkeypatch.setenv("PG_CWF_HEADER_VERIFIED_ONLY", "1")
    header_on = rs._best_corroboration_header(basket, statement=title)
    # EFFECT: the header is the clean source TITLE — the unverified claim is NEVER asserted.
    assert header_on == title, header_on
    assert "Unverified source" not in header_on

    monkeypatch.setenv("PG_CWF_HEADER_VERIFIED_ONLY", "0")
    header_off = rs._best_corroboration_header(basket, statement=title)
    # RED baseline: pre-H3, the unverified member's sentence became the header (the defect).
    assert "Unverified source asserts productivity collapsed" in header_off, header_off


def test_h3_prefers_a_verified_member_sentence(monkeypatch):
    rs = _load_sweep()
    basket = {
        "claim_text": "ISSN: 1234-5678 Cite this paper as:",
        "supporting_members": [
            {"member_tier": "UNVERIFIED", "direct_quote": "Junk claim about a ninety percent drop overnight."},
            {
                "member_tier": "ENTAILMENT_VERIFIED",
                "direct_quote": "Automation increased factory output by twelve percent in the studied plants.",
            },
        ],
    }
    monkeypatch.setenv("PG_CWF_HEADER_VERIFIED_ONLY", "1")
    header = rs._best_corroboration_header(basket, statement="A Title")
    assert header == "Automation increased factory output by twelve percent in the studied plants.", header


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
