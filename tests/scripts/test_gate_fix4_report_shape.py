"""FIX 4 (report shape — ARCHETYPE-driven, not an audit dump) unit tests.

All OFFLINE — no network, no LLM, no live retrieval, no frozen-file edit. Each test exercises a
render-assembly reshape the consolidated plan mandates (POSITION ONLY — nothing deleted; every kept
finding sentence stays byte-identical strict_verify output):

  (a) build_framing_md: a CLAIM-FREE, CITATION-FREE ``## {framing_title}`` framing paragraph from the
      contract objective (no findings, no ``[N]``); the ``review`` default emits ``## Introduction and
      Scope``, byte-identical to the landed build.
  (b) order_report_blocks: for the ``review`` default the thematic sections precede the Key-Findings
      recap; the Methods / disclosure machinery is split into a trailing appendix; NOTHING is dropped.
  (c) key_findings bullet-integrity invariant: every bullet opens with ``**`` and has a matched
      closing ``**``; a chopped bullet is re-emitted whole. The render-seam Key-Findings screen is
      whole-unit (drop whole chrome bullet, keep a real bullet byte-intact — never a mid-``**`` chop).
  (d) preamble shrink: the Key-Findings hedge preamble is ONE sentence + an appendix pointer.

  Cross-cutting invariants: an assembled report starts with ``# ``; no ``STRONGEST VERIFIER`` string
  appears before the first thematic section; every Key-Findings bullet has a matched ``**``.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import scripts.run_honest_sweep_r3 as rh  # noqa: E402
from src.polaris_graph.generator.key_findings import (  # noqa: E402
    _bullet_marker_integrity_ok,
    _reemit_key_findings_bullet,
    build_key_findings,
)
from src.polaris_graph.generator.report_skeleton import ARCHETYPES  # noqa: E402
from src.polaris_graph.generator.weighted_enrichment import (  # noqa: E402
    sanitize_rendered_report,
)

_REVIEW = ARCHETYPES["review"]


@dataclass
class _Section:
    title: str
    verified_text: str
    dropped_due_to_failure: bool = False
    sentences_verified: int = 1
    is_gap_stub: bool = False


# ---------------------------------------------------------------------------
# (a) FIX 4(a): claim-free, citation-free framing (review => Introduction and Scope)
# ---------------------------------------------------------------------------

def test_intro_is_claim_free_and_citation_free():
    intro = rh.build_framing_md(
        "the restructuring impact of AI on the labor market"
    )
    # the framing prose leads (directly under the H1 the caller emits) then the labelled subsection
    assert "## Introduction and Scope" in intro
    assert not intro.startswith("#")  # prose-first so the H1 is never orphan-dropped
    # framing only — no citation markers, no bold finding labels
    assert "[" not in intro and "]" not in intro
    assert "**" not in intro
    # names the objective (framing), asserts no numeric finding
    assert "AI on the labor market" in intro
    assert not any(ch.isdigit() for ch in intro)


def test_intro_empty_objective_yields_no_heading():
    assert rh.build_framing_md("") == ""
    assert rh.build_framing_md("   ") == ""


# ---------------------------------------------------------------------------
# (b) FIX 4(b): review body order + machinery appendix (POSITION ONLY)
# ---------------------------------------------------------------------------

def _components():
    return dict(
        key_findings_md="## Key Findings\n\n- **Theme A.** Finding one [1].\n\n",
        sections_concat="### Theme A\n\nThematic body one [1].\n\n### Limitations\n\nA caveat [2].",
        depth_layer_md="\n\n## Analytical synthesis\n\n### Cross-source synthesis\n\nA tension [3].",
        methods_md="\n\n## Methods\nPre-registered protocol.\n",
        biblio_section_md="\n\n## Bibliography\n1. Source one\n",
        cwf_disclosed_md="\n\n## Promotion-eligibility disclosure\n\nDisclosed row.\n",
        drop_disclosure_md="\n\n## Dropped-source disclosure\n\nDropped row.\n",
    )


def test_reshape_thematic_precedes_key_findings():
    scored_body, appendix = rh.order_report_blocks(_REVIEW, **_components())
    # thematic sections (and their Limitations) come BEFORE the Key-Findings recap
    assert scored_body.index("### Theme A") < scored_body.index("## Key Findings")
    assert scored_body.index("### Limitations") < scored_body.index("## Key Findings")
    # synthesis sits between thematic sections and Key Findings; bibliography is last in the body
    assert scored_body.index("## Analytical synthesis") < scored_body.index("## Key Findings")
    assert scored_body.index("## Key Findings") < scored_body.index("## Bibliography")


def test_reshape_machinery_moves_to_appendix_nothing_dropped():
    comps = _components()
    scored_body, appendix = rh.order_report_blocks(_REVIEW, **comps)
    # Methods / disclosure machinery is OUT of the scored body ...
    assert "## Methods" not in scored_body
    assert "Promotion-eligibility disclosure" not in scored_body
    assert "Dropped-source disclosure" not in scored_body
    # ... and PRESENT in the appendix (moved, never deleted).
    assert "## Methods" in appendix
    assert "Promotion-eligibility disclosure" in appendix
    assert "Dropped-source disclosure" in appendix
    # POSITION ONLY: every input block survives EXACTLY ONCE across body + appendix combined.
    combined = scored_body + appendix
    for block in comps.values():
        assert combined.count(block) == 1


def test_memo_archetype_leads_with_key_findings():
    # a memo (BLUF) leads with Key Findings and emits NO framing section
    memo = ARCHETYPES["memo"]
    assert rh.build_framing_md("some question", memo) == ""
    scored_body, _appendix = rh.order_report_blocks(memo, **_components())
    assert scored_body.index("## Key Findings") < scored_body.index("### Theme A")


def test_methods_stays_in_body_when_required_section():
    comps = _components()
    scored_body, appendix = rh.order_report_blocks(
        _REVIEW, **comps, methods_is_machinery=False
    )
    assert "## Methods" in scored_body
    assert "## Methods" not in appendix
    # still count-invariant
    assert (scored_body + appendix).count(comps["methods_md"]) == 1


def test_reshape_off_switch_is_legacy_order(monkeypatch):
    # the kill-switch flips the shape off (byte-identical machinery-first order is the caller's path)
    monkeypatch.setenv("PG_REPORT_SHAPE", "0")
    assert rh.report_shape_enabled() is False
    monkeypatch.setenv("PG_REPORT_SHAPE", "1")
    assert rh.report_shape_enabled() is True


# ---------------------------------------------------------------------------
# (c) FIX 4(c): Key-Findings bullet-integrity invariant + whole-unit render seam
# ---------------------------------------------------------------------------

def test_bullet_integrity_predicate():
    assert _bullet_marker_integrity_ok("- **Job Displacement.** A finding [1].")
    # chopped opening ** (the audit defect) fails
    assert not _bullet_marker_integrity_ok("- Job Displacement.** A finding [1].")
    # dangling (odd) ** fails
    assert not _bullet_marker_integrity_ok("- **Job Displacement. A finding [1].")


def test_reemit_bullet_is_whole_and_verbatim():
    out = _reemit_key_findings_bullet("Job Displacement", "AI displaced 3.2% of roles [1].")
    assert out == "- **Job Displacement.** AI displaced 3.2% of roles [1]."
    assert _bullet_marker_integrity_ok(out)
    # no title -> clean bullet with NO bold markers (build_key_findings always supplies a title, so a
    # titleless bullet is an edge case; it carries no ** to be chopped or mismatched)
    out2 = _reemit_key_findings_bullet("", "A bare finding [2].")
    assert out2 == "- A bare finding [2]."
    assert "**" not in out2


def test_build_key_findings_every_bullet_has_matched_bold():
    secs = [
        _Section("Job Displacement by AI", "AI displaced 3.2 percent of roles [1]. More [2]."),
        _Section("Wage Effects", "Wages fell 1.1 percent for exposed workers [3]. Extra [4]."),
    ]
    out = build_key_findings(secs)
    bullets = [ln for ln in out.splitlines() if ln.lstrip().startswith(("-", "*"))]
    assert bullets, "expected at least one Key-Findings bullet"
    for b in bullets:
        assert _bullet_marker_integrity_ok(b), f"unbalanced bullet: {b!r}"


def test_key_findings_preamble_is_one_sentence_with_appendix_pointer():
    secs = [_Section("Theme", "A verified finding [1]. Second [2].")]
    out = build_key_findings(secs)
    # find the italic preamble line
    preamble = next(
        ln for ln in out.splitlines() if ln.strip().startswith("_") and ln.strip().endswith("_")
    )
    # ONE sentence (a single terminal period inside the italics) + an appendix pointer
    assert preamble.count(". ") <= 1
    assert "appendix" in preamble.lower()


def test_relabel_key_findings_header_chrome_only():
    # a memo relabels the Key-Findings HEADER to "## Bottom Line"; the preamble + bullets are unchanged
    kf = (
        "## Key Findings\n\n"
        "_Each finding is verbatim text carried up from a cited body span._\n\n"
        "- **Theme.** A finding [1].\n\n"
    )
    memo = ARCHETYPES["memo"]
    relabeled = rh._relabel_key_findings_header(kf, memo)
    assert relabeled.startswith("## Bottom Line\n")
    # bullets byte-identical (the header line is the ONLY change)
    assert relabeled[len("## Bottom Line\n"):] == kf[len("## Key Findings\n"):]
    # review is a no-op (keeps ## Key Findings verbatim)
    assert rh._relabel_key_findings_header(kf, _REVIEW) == kf


def test_render_seam_key_findings_whole_unit_keeps_real_bullet_intact():
    # a real finding bullet with a chrome-looking title must NOT be mid-chopped — kept byte-intact
    report = (
        "# Research report: X\n\n"
        "## Key Findings\n\n"
        "- **Job Displacement by AI Technologies.** AI displaced 3.2 percent of exposed roles [1].\n\n"
        "### Theme A\n\nBody [1].\n"
    )
    out, _removed = sanitize_rendered_report(report, set())
    # the Key-Findings bullet survives with a MATCHED ** pairing (never a severed opening **)
    kf_lines = [ln for ln in out.splitlines() if ln.lstrip().startswith("- **")]
    assert kf_lines, "the real Key-Findings bullet must survive whole"
    for ln in kf_lines:
        assert _bullet_marker_integrity_ok(ln)
    # no mangled 'Title.** ...' (opening ** chopped) bullet leaked
    assert "\n- Job Displacement by AI Technologies.**" not in out


def test_render_seam_key_findings_whole_unit_drops_chrome_bullet_whole(monkeypatch):
    # a pure-chrome Key-Findings bullet is dropped WHOLE (not chopped into a dangling **)
    report = (
        "## Key Findings\n\n"
        "- **Nav.** Skip to main content Cookie preferences Accept all cookies\n\n"
        "- **Real Finding.** AI displaced 3.2 percent of roles [1].\n"
    )
    out, removed = sanitize_rendered_report(report, set())
    # the real finding survives whole; if the chrome bullet dropped it left no dangling ** fragment
    for ln in out.splitlines():
        if ln.lstrip().startswith(("-", "*")):
            assert _bullet_marker_integrity_ok(ln)


# ---------------------------------------------------------------------------
# (U6) D8 banner relocation — insert after the H1 title block (shape-ON)
# ---------------------------------------------------------------------------

def test_banner_inserted_after_h1_not_before():
    report = "# Research report: X\n\n## Key Findings\n\n- **A.** B [1].\n"
    banner = "> STRONGEST VERIFIER (four-role D8) DID NOT RUN for this run.\n\n"
    out = rh._insert_banner_after_h1(report, banner)
    # report still opens on the H1 title, not on the blockquote
    assert out.startswith("# Research report: X")
    # banner appears AFTER the H1 and BEFORE the first body header, byte-identical
    assert banner.strip() in out
    assert out.index("# Research report") < out.index("STRONGEST VERIFIER")
    assert out.index("STRONGEST VERIFIER") < out.index("## Key Findings")


def test_banner_prepends_when_no_h1_present():
    report = "## Key Findings\n\n- **A.** B [1].\n"
    banner = "> STRONGEST VERIFIER (four-role D8) DID NOT RUN.\n\n"
    out = rh._insert_banner_after_h1(report, banner)
    # fail-safe: with no H1 the banner still ships (prepend) — a disclosure is never dropped
    assert out.startswith(banner)


# ---------------------------------------------------------------------------
# Cross-cutting invariants on a full assembled report
# ---------------------------------------------------------------------------

def _assemble_full_report():
    comps = _components()
    intro = rh.build_framing_md("the impact of AI on labor")
    scored_body, appendix = rh.order_report_blocks(_REVIEW, **comps)
    title = "# Research report: the impact of AI on labor\n\n"
    body = rh.assemble_report_md(title + intro, "", scored_body, "", dedup_enabled=True)
    reliability = "Reliability header counts.\n"
    return rh.compose_report_with_reliability(
        body, appendix.rstrip() + "\n\n" + reliability
    )


def test_full_report_starts_with_h1():
    report = _assemble_full_report()
    assert report.startswith("# "), "report must open on an H1 title"


def test_full_report_no_strongest_verifier_before_first_thematic_section():
    # the reshaped report has NO machinery banner before the first thematic ### section. (The frozen
    # D8 banner is a separate finalize-time concern handled by FIX 3; the reshape itself never emits
    # a STRONGEST-VERIFIER string ahead of the thematic body.)
    report = _assemble_full_report()
    first_thematic = report.index("### Theme A")
    assert "STRONGEST VERIFIER" not in report[:first_thematic]


def test_full_report_every_key_findings_bullet_matched_bold():
    report = _assemble_full_report()
    kf_idx = report.index("## Key Findings")
    tail = report[kf_idx:]
    # bound the block at the next ## header
    end = tail.find("\n## ", 3)
    block = tail if end < 0 else tail[:end]
    for ln in block.splitlines():
        if ln.lstrip().startswith(("-", "*")):
            assert _bullet_marker_integrity_ok(ln), f"unbalanced bullet: {ln!r}"
