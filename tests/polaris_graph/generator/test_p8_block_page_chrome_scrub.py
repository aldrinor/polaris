# -*- coding: utf-8 -*-
"""I-deepfix-001 P8_chrome_leak (#1344) — RED->GREEN offline proof for the render-seam block-page /
security-check / copyright-footer chrome STRIP.

Ground truth: the drb_72 workforce run
(``outputs/boxc_full/workforce/drb_72_ai_labor/``). The block page was captured as bibliography
source ``[27]`` (``ev_146``, ``source_title`` "Just a moment...", tier T7) and its two chrome
sentences rendered verbatim in the report.md body (line 84):

    To continue, complete the security check below.[27] Ray ID: a160331f3c7dd701 Client IP:
    2600:1900:0:2101::1100 (c) 2008-2026 ResearchGate GmbH.[27]

RED: the shared render-chrome predicate catches the JOINED block page but is blind to each split
sentence. GREEN: ``scrub_block_page_chrome`` withholds the two chrome sentences while preserving
every real finding, the disclosed-gap stubs, the bibliography row, the audit appendix, headers, and
tables.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.generator.block_page_chrome_scrub import (
    block_page_chrome_scrub_enabled,
    is_block_page_chrome_sentence,
    scrub_block_page_chrome,
)

# The two EXACT chrome sentences that leaked into the drb_72 report body (verbatim, with the
# U+00A9 copyright glyph as it appears in report.md).
CHROME_SECURITY = "To continue, complete the security check below."
CHROME_RAYID = (
    "Ray ID: a160331f3c7dd701 Client IP: 2600:1900:0:2101::1100 "
    "© 2008-2026 ResearchGate GmbH."
)

# The verbatim drb_72 report.md line 84 body paragraph (the leak in situ, welded with real findings
# and the two disclosed-gap stubs).
DRB72_BODY_LINE = (
    "Generative artificial intelligence represents a critical inflection point in the evolution of "
    "machine learning systems by enabling the autonomous synthesis of content.[21] Thus, Enterprise "
    "Intelligence 5.0 is more about strategic human-machine alignment than technological "
    "sophistication.[26] To continue, complete the security check below.[27] Ray ID: "
    "a160331f3c7dd701 Client IP: 2600:1900:0:2101::1100 © 2008-2026 ResearchGate GmbH.[27] Our "
    "analysis identifies nine major domains of AI misuse: (1) Adversarial Threats, (2) Privacy "
    "Violations, (3) Disinformation, Deception, and Propaganda, (4) Bias and Discrimination, (5) "
    "System Safety and Reliability Failures, (6) Socioeconomic Exploitation and Inequality, (7) "
    "Environmental and Ecological Misuse, (8) Autonomy and Weaponization, and (9) Human Interaction "
    "and Psychological Harm.[28] A claim previously stated here did not survive 4-role verification "
    "and was redacted; this is a curator-actionable gap."
)


# ─────────────────────────────────────────────────────────────────────────────
# RED — the shared render-chrome predicate is blind to the split sentences.
# ─────────────────────────────────────────────────────────────────────────────
def test_red_shared_predicate_blind_to_split_block_page_sentences():
    """The production containment predicate catches the JOINED block page but returns False on each
    split sentence — the exact blind spot that let the chrome survive the render-seam chokepoint."""
    from src.polaris_graph.generator.weighted_enrichment import (
        is_render_chrome_or_unrenderable,
    )

    joined_block_page = (
        "## Security check required We've detected unusual activity from your network. "
        "To continue, complete the security check below. Ray ID: a160331f3c7dd701 Client IP: "
        "2600:1900:0:2101::1100 © 2008-2026 ResearchGate GmbH."
    )
    # The joined page is caught by the shared predicate ...
    assert is_render_chrome_or_unrenderable(joined_block_page) is True
    # ... but the split sentences (as they reach the render seam) are NOT — this is the RED bug.
    assert is_render_chrome_or_unrenderable(CHROME_SECURITY) is False
    assert is_render_chrome_or_unrenderable(CHROME_RAYID) is False


# ─────────────────────────────────────────────────────────────────────────────
# GREEN — the new sentence-level detector fires on exactly the block-page chrome.
# ─────────────────────────────────────────────────────────────────────────────
def test_detector_fires_on_leaked_chrome_sentences():
    assert is_block_page_chrome_sentence(CHROME_SECURITY) is True
    assert is_block_page_chrome_sentence(CHROME_RAYID) is True


def test_detector_precision_keeps_real_findings_and_disclosure():
    """A real labor / economics / clinical finding and legitimate disclosure prose must NOT trip the
    detector (precision-first per §-1.3 — over-strip of a real finding is the harm)."""
    negatives = [
        "Generative artificial intelligence represents a critical inflection point in the "
        "evolution of machine learning systems by enabling the autonomous synthesis of content.",
        "Our analysis identifies nine major domains of AI misuse: (1) Adversarial Threats, (2) "
        "Privacy Violations, (5) System Safety and Reliability Failures.",
        "A claim previously stated here did not survive 4-role verification and was redacted; this "
        "is a curator-actionable gap.",
        # mentions 'security' and 'copyright' but is a real claim, not chrome:
        "The paper analyzes system safety, security risks, and copyright disputes raised by "
        "generative models in the 2024 labor market.",
        "The 2024 report published by Elsevier found productivity rose fourteen percent among "
        "customer-support agents.",
    ]
    for text in negatives:
        assert is_block_page_chrome_sentence(text) is False, text


def test_copyright_footer_soft_rule():
    """A DOMINANT standalone copyright footer is chrome; a real claim that cites a license is KEPT."""
    assert is_block_page_chrome_sentence(
        "Copyright © 2008-2026 ResearchGate GmbH. All rights reserved."
    ) is True
    assert is_block_page_chrome_sentence("© 2024 Elsevier B.V. All rights reserved.") is True
    # A real claim mentioning a copyright/publisher in passing carries real content -> KEPT.
    assert is_block_page_chrome_sentence(
        "The dataset released under the © 2024 Creative Commons license by the World Bank "
        "documents a fourteen percent productivity gain across surveyed occupations."
    ) is False


# ─────────────────────────────────────────────────────────────────────────────
# GREEN (end-to-end) — the scrub removes the two chrome sentences from the real report line and
# preserves every real finding + both disclosed-gap stubs.
# ─────────────────────────────────────────────────────────────────────────────
def test_scrub_removes_chrome_from_real_drb72_body_line():
    scrubbed, dropped = scrub_block_page_chrome(DRB72_BODY_LINE)

    # exactly the two chrome sentences dropped ...
    assert dropped == 2
    assert "complete the security check below" not in scrubbed
    assert "Ray ID:" not in scrubbed
    assert "ResearchGate GmbH" not in scrubbed
    assert "Client IP:" not in scrubbed
    assert "© 2008-2026" not in scrubbed

    # ... while every real finding + both disclosed-gap stubs survive untouched.
    assert "critical inflection point in the evolution of machine learning systems" in scrubbed
    assert "Enterprise Intelligence 5.0 is more about strategic human-machine alignment" in scrubbed
    assert "nine major domains of AI misuse" in scrubbed
    assert "System Safety and Reliability Failures" in scrubbed
    assert "did not survive 4-role verification and was redacted" in scrubbed
    # citations to real sources are preserved; the [27] block-page citation is gone from the prose.
    assert "[21]" in scrubbed
    assert "[26]" in scrubbed
    assert "[28]" in scrubbed
    assert "[27]" not in scrubbed
    # no double-space corruption at the drop joint.
    assert "  " not in scrubbed


def test_scrub_over_full_report_only_touches_the_leak():
    """The whole-report scrub, run over a realistic multi-section report, alters ONLY the body chrome
    and byte-preserves headers, tables, the clean bibliography row, the audit appendix, and the
    disclosure sections (they carry no block-page markers)."""
    report = "\n".join(
        [
            "# Research report: impact of Generative AI on the labor market",
            "",
            "## Ethical, Security, and Psychological Challenges",
            "",
            DRB72_BODY_LINE,
            "",
            "## Bibliography",
            "",
            "[27] Generative AI and Job Vulnerability: A Global Review — "
            "https://www.researchgate.net/publication/398053032 (tier T7) — [document type: preprint]",
            "",
            "## Industry-Specific Applications and Risk Summary",
            "",
            "| Research Literature | Country/Region | Application Area |",
            "| --- | --- | --- |",
            "| Brynjolfsson et al. | United States | Customer support |",
            "",
            "## Corpus ledger (audit appendix — not cited references)",
            "",
            "[23] (PDF) The Short-Term Effects of Generative Artificial Intelligence on ... — "
            "https://www.researchgate.net/publication/384306232 (tier T7) — [document type: preprint]",
        ]
    )
    scrubbed, dropped = scrub_block_page_chrome(report)
    assert dropped == 2

    # structural + disclosure lines are byte-preserved.
    assert "# Research report: impact of Generative AI on the labor market" in scrubbed
    assert "## Bibliography" in scrubbed
    assert (
        "[27] Generative AI and Job Vulnerability: A Global Review" in scrubbed
    )  # clean bibliography statement untouched (source NOT dropped)
    assert "| --- | --- | --- |" in scrubbed
    assert "| Brynjolfsson et al. | United States | Customer support |" in scrubbed
    assert "[23] (PDF) The Short-Term Effects of Generative Artificial Intelligence" in scrubbed

    # the body chrome is gone.
    assert "Ray ID:" not in scrubbed
    assert "complete the security check below" not in scrubbed
    # the report line-count is preserved (line-scoped; no lines added/removed).
    assert len(scrubbed.split("\n")) == len(report.split("\n"))


# ─────────────────────────────────────────────────────────────────────────────
# FAIL-SAFE + kill-switch.
# ─────────────────────────────────────────────────────────────────────────────
def test_no_flag_returns_byte_identical():
    clean = (
        "## Positive Views\n\nGenerative AI raised customer-support productivity by fourteen "
        "percent among 5,172 agents.[6] Autor argues automation has not wiped out most jobs.[1]"
    )
    scrubbed, dropped = scrub_block_page_chrome(clean)
    assert dropped == 0
    assert scrubbed == clean


def test_kill_switch_disables_scrub(monkeypatch):
    monkeypatch.setenv("PG_BLOCK_PAGE_CHROME_SCRUB", "0")
    assert block_page_chrome_scrub_enabled() is False
    scrubbed, dropped = scrub_block_page_chrome(DRB72_BODY_LINE)
    assert dropped == 0
    assert scrubbed == DRB72_BODY_LINE
    # explicit enabled=True overrides the env for a targeted call.
    scrubbed2, dropped2 = scrub_block_page_chrome(DRB72_BODY_LINE, enabled=True)
    assert dropped2 == 2


def test_empty_and_whitespace_inputs():
    assert scrub_block_page_chrome("") == ("", 0)
    assert scrub_block_page_chrome("   \n  \n") == ("   \n  \n", 0)


def test_pure_chrome_bullet_keeps_marker_skeleton():
    """A Key-Findings bullet whose entire text is block-page chrome keeps its bullet prefix (so the
    list is not left dangling) with the chrome text removed."""
    line = "- To continue, complete the security check below.[27]"
    scrubbed, dropped = scrub_block_page_chrome(line)
    assert dropped == 1
    assert "security check" not in scrubbed
    assert scrubbed.strip() in ("-", "")


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
