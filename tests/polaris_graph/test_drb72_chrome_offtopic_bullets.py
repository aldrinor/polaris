"""I-deepfix-001 (drb_72) UNIT-1 — chrome / off-topic-CITE / empty-bullet fixes.

Self-contained OFFLINE test (no paid API, no GPU, no banked artifact) for the four coherent
same-file fixes in ``src/polaris_graph/generator/weighted_enrichment.py`` (plus the ISSN boundary
in ``scripts/iwire013_sec11_forensic_audit.py``):

  FIX-A  ISSNe/ISSNp-aware masthead-recital chrome (co-signal gated; a bare substantive ISSN
         mention stays a finding).
  FIX-B  chart alt-text axis enumeration ("The chart has 1 X axis … 1 Y axis …") -> chrome; a real
         finding merely NAMING an axis stays a finding.
  FIX-C  off-topic single-origin CITE gate — a corroborated-by-nobody, >=6-word, zero-overlap span
         is ROUTED to ``disclosed_only`` (kept, never dropped); on-topic / corroborated / terse /
         gate-off all fail-open to promote.
  FIX-D  empty "- " / "- [12]" bullets (no claim text) are dropped at both the unit split and the
         render-seam belt; a real bullet is untouched.

All four are reached through the pre-existing PUBLIC entry points, so on UNPATCHED code the tests
fail on BEHAVIOUR (assertion failures) rather than import errors — a clean RED.

Direct run:  python tests/polaris_graph/test_drb72_chrome_offtopic_bullets.py
Pytest:      python -m pytest tests/polaris_graph/test_drb72_chrome_offtopic_bullets.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

# Make ``src`` importable when run directly (mirrors the pytest rootdir import).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

# Only PRE-EXISTING public entry points are imported so RED shows assertion failures, not
# ImportError, when the four fixes are absent.
from src.polaris_graph.generator.weighted_enrichment import (  # noqa: E402
    _split_enrichment_blob_line,
    diagnose_unbound_supports_selection,
    is_render_chrome_or_unrenderable,
    sanitize_rendered_report,
)


# ── env isolation ─────────────────────────────────────────────────────────────
class _Env:
    """Deterministic env scope: set the given vars, restore prior values on exit."""

    _KEYS = (
        "PG_CWF_PROMOTION_ELIGIBILITY",
        "PG_CWF_PROMOTION_MIN_WEIGHT",
        "PG_CWF_PROMOTION_MIN_CORROBORATION",
        "PG_CWF_PROMOTION_TOPICAL_GATE",
        "PG_CWF_PROMOTION_MIN_TOPICAL_OVERLAP",
        "PG_OFFTOPIC_CITE_SUPPRESS",
    )

    def __init__(self, **overrides):
        self._overrides = overrides

    def __enter__(self):
        self._saved = {k: os.environ.get(k) for k in self._KEYS}
        for k in self._KEYS:
            os.environ.pop(k, None)
        for k, v in self._overrides.items():
            os.environ[k] = v
        return self

    def __exit__(self, *exc):
        for k in self._KEYS:
            os.environ.pop(k, None)
            if self._saved.get(k) is not None:
                os.environ[k] = self._saved[k]
        return False


# ══════════════════════════════════════════════════════════════════════════════
# FIX-A + FIX-B — render-side chrome predicate
# ══════════════════════════════════════════════════════════════════════════════

_CHART_ALT_CHROME = (
    "The chart has 1 X axis displaying categories and 1 Y axis displaying "
    "Share of Generative AI Users Reporting Ho"
)
_ISSNE_MASTHEAD_CHROME = (
    "The publication identified by ISSNe 1972-4942 includes a section 2.2 titled "
    "Methods and Results."
)
# FP guards — MUST stay findings (not chrome).
_AXIS_FINDING = (
    "Employment on the y-axis rose as automation on the x-axis increased across the chart."
)
_ISSN_FINDING = "A 2021 study (ISSN 2049-3630) found 14% of jobs at risk."


def test_chart_alt_text_is_chrome():
    assert is_render_chrome_or_unrenderable(_CHART_ALT_CHROME) is True


def test_issne_masthead_recital_is_chrome():
    assert is_render_chrome_or_unrenderable(_ISSNE_MASTHEAD_CHROME) is True


def test_axis_naming_finding_stays_not_chrome():
    assert is_render_chrome_or_unrenderable(_AXIS_FINDING) is False


def test_substantive_issn_finding_stays_not_chrome():
    assert is_render_chrome_or_unrenderable(_ISSN_FINDING) is False


# ══════════════════════════════════════════════════════════════════════════════
# FIX-C — off-topic single-origin CITE gate (M5 promotion override)
# ══════════════════════════════════════════════════════════════════════════════

# A realistic drb_72-style GenAI-labor research question.
_RESEARCH_QUESTION = (
    "How is generative artificial intelligence reshaping employment tasks and "
    "workforce productivity in labor markets?"
)

# Off-topic spans: >=6 content words, ZERO overlap with the question, HIGH credibility weight
# (0.50) and a non-journal host + single origin — so ONLY the topical gate can demote them (the
# base weight/corroboration/journal partition would otherwise promote them). This isolates FIX-C.
_OFF_MWCNT = (
    "Multi-walled carbon nanotubes dispersed within graphene oxide sheets exhibited "
    "enhanced tensile mechanical strength."
)
_OFF_IPO = (
    "The founder previously led a ten billion dollar initial public offering on the "
    "New York Stock Exchange."
)
_OFF_CORRUPTION = (
    "Systemic corruption entrenched persistent rural poverty throughout several "
    "impoverished developing provinces."
)
# On-topic spans: share content words with the question -> overlap > 0 -> fail-open promote.
_ON_1 = (
    "Generative artificial intelligence reshaped employment tasks and boosted workforce "
    "productivity in several labor markets."
)
_ON_2 = (
    "Automation from generative intelligence displaced routine employment tasks while "
    "lifting aggregate productivity."
)
# Off-topic BUT corroborated (2 verified origins) -> corroboration rescues -> promote.
_OFF_CORROBORATED = (
    "Volcanic basalt formations eroded gradually beneath thick glacial ice sheets."
)
# Off-topic BUT terse (<6 content words) -> too terse to judge -> keep-neutral promote.
_OFF_TERSE = "Basalt eroded slowly."

_OFFTOPIC_IDS = {"ev_off_mwcnt", "ev_off_ipo", "ev_off_corruption"}


def _member(eid, url, quote, *, verdict="SUPPORTS", weight=0.50, tier="T6"):
    return SimpleNamespace(
        evidence_id=eid,
        source_url=url,
        source_tier=tier,
        credibility_weight=weight,
        span_verdict=verdict,
        member_tier="ENTAILMENT_VERIFIED",
    )


def _basket(ccid, weight_mass, voc, members):
    return SimpleNamespace(
        claim_cluster_id=ccid,
        weight_mass=weight_mass,
        verified_support_origin_count=voc,
        supporting_members=members,
    )


def _fixture():
    """Baskets + evidence_pool covering the seven FIX-C cases. The topical overlap reads the pool
    row's ``direct_quote`` (via ``_member_quote``), so each quote lives on the pool row."""
    specs = [
        # (eid, url, quote, weight, voc)
        ("ev_off_mwcnt", "https://materials.example.com/a", _OFF_MWCNT, 0.50, 1),
        ("ev_off_ipo", "https://careers.example.com/b", _OFF_IPO, 0.50, 1),
        ("ev_off_corruption", "https://govwatch.example.com/c", _OFF_CORRUPTION, 0.50, 1),
        ("ev_on_1", "https://labor.example.com/d", _ON_1, 0.50, 1),
        ("ev_on_2", "https://labor.example.com/e", _ON_2, 0.50, 1),
        ("ev_off_corroborated", "https://geology.example.com/f", _OFF_CORROBORATED, 0.02, 2),
        ("ev_off_terse", "https://geology.example.com/g", _OFF_TERSE, 0.50, 1),
    ]
    baskets = []
    pool = {}
    for eid, url, quote, weight, voc in specs:
        baskets.append(
            _basket(
                f"cluster_{eid}", weight, voc, [_member(eid, url, quote, weight=weight)]
            )
        )
        pool[eid] = {"source_url": url, "direct_quote": quote}
    return baskets, pool


def _run(baskets, pool):
    fake_cred = SimpleNamespace(baskets=baskets)
    return diagnose_unbound_supports_selection(
        evidence_pool=pool,
        credibility_analysis=fake_cred,
        contract_plans=[],
        research_question=_RESEARCH_QUESTION,
    )


def test_offtopic_single_origin_routed_to_disclosed_only():
    baskets, pool = _fixture()
    with _Env():  # defaults: all gates ON, W=0.10, K=2, topical overlap=0.0
        res = _run(baskets, pool)
    disclosed_ids = {d["evidence_id"] for d in res.disclosed_only}
    # The 3 zero-overlap, high-weight, single-origin off-topic spans demote — and ONLY those.
    assert disclosed_ids == _OFFTOPIC_IDS, (
        f"expected exactly {_OFFTOPIC_IDS} routed to disclosed_only, got {disclosed_ids}"
    )
    for eid in _OFFTOPIC_IDS:
        assert eid not in res.ev_ids, f"{eid} must NOT be a promoted (cited) finding"
    # Each demoted record carries the FIX-C reason.
    for d in res.disclosed_only:
        assert d["reason"] == "off_topic_single_origin", (
            f"{d['evidence_id']} demoted for wrong reason {d['reason']!r}"
        )


def test_ontopic_and_rescued_spans_promote():
    baskets, pool = _fixture()
    with _Env():
        res = _run(baskets, pool)
    for eid in ("ev_on_1", "ev_on_2"):
        assert eid in res.ev_ids, f"on-topic {eid} must promote (overlap > 0)"
    # corroboration (>=2 verified origins) rescues an otherwise off-topic span.
    assert "ev_off_corroborated" in res.ev_ids, "corroboration>=2 must rescue an off-topic span"
    # a terse (<6 content-word) off-topic span is too terse to judge -> keep-neutral promote.
    assert "ev_off_terse" in res.ev_ids, "terse (<6 words) off-topic span must promote"


def test_conservation_promoted_union_disclosed_is_full_set():
    baskets, pool = _fixture()
    with _Env():
        res = _run(baskets, pool)
    promoted = set(res.ev_ids)
    disclosed = {d["evidence_id"] for d in res.disclosed_only}
    all_seven = {
        "ev_off_mwcnt", "ev_off_ipo", "ev_off_corruption",
        "ev_on_1", "ev_on_2", "ev_off_corroborated", "ev_off_terse",
    }
    assert promoted.isdisjoint(disclosed), "promoted and disclosed_only must be DISJOINT"
    assert promoted | disclosed == all_seven, (
        f"conservation broken: {promoted | disclosed} != {all_seven}"
    )


def test_topical_gate_off_is_byte_identical_promote_all():
    baskets, pool = _fixture()
    with _Env(PG_CWF_PROMOTION_TOPICAL_GATE="0"):
        res = _run(baskets, pool)
    # With the topical gate OFF, the 3 high-weight off-topic spans clear the base WEIGHT leg and
    # promote; NO record may carry the off-topic reason.
    for eid in _OFFTOPIC_IDS:
        assert eid in res.ev_ids, f"gate OFF must promote {eid} (weight 0.50 >= 0.10)"
    assert not any(
        d["reason"] == "off_topic_single_origin" for d in res.disclosed_only
    ), "gate OFF must never emit the off_topic_single_origin reason"


def test_malformed_topical_overlap_env_raises_value_error():
    baskets, pool = _fixture()
    with _Env(PG_CWF_PROMOTION_MIN_TOPICAL_OVERLAP="not_a_float"):
        with pytest.raises(ValueError):
            _run(baskets, pool)


# ══════════════════════════════════════════════════════════════════════════════
# FIX-D — empty "- " / "- [12]" bullets dropped; real bullets untouched
# ══════════════════════════════════════════════════════════════════════════════

def test_empty_bullet_unit_split_drops_marker_only_bullet():
    bullets, _ = _split_enrichment_blob_line("- ", None)
    assert bullets == [], "bare '- ' bullet must drop at the unit split"


def test_orphan_citation_bullet_unit_split_drops():
    bullets, _ = _split_enrichment_blob_line("- [12]", None)
    assert bullets == [], "citation-marker-only '- [12]' bullet must drop at the unit split"


def test_real_bullet_unit_split_untouched():
    line = "- Employment rose sharply among displaced workers [3]."
    bullets, _ = _split_enrichment_blob_line(line, None)
    assert len(bullets) == 1 and "Employment rose sharply" in bullets[0], (
        f"a real bullet must survive the unit split, got {bullets!r}"
    )


def test_render_seam_belt_drops_empty_bullets_keeps_real():
    report = (
        "## Findings\n"
        "\n"
        "- Employment rose sharply among displaced workers [3].\n"
        "- \n"
        "- [12]\n"
    )
    with _Env():
        clean, removed = sanitize_rendered_report(report, None)
    assert "Employment rose sharply among displaced workers [3]." in clean, (
        "the real bullet must be preserved by the render seam"
    )
    # Neither empty bullet may survive.
    assert "\n- \n" not in clean and "- [12]" not in clean, (
        f"empty bullets survived the render-seam belt:\n{clean}"
    )
    assert removed >= 2, f"expected >=2 empty bullets removed, got {removed}"


# ── direct-run harness (mirrors the file's pytest run) ────────────────────────
def main():
    fns = [
        test_chart_alt_text_is_chrome,
        test_issne_masthead_recital_is_chrome,
        test_axis_naming_finding_stays_not_chrome,
        test_substantive_issn_finding_stays_not_chrome,
        test_offtopic_single_origin_routed_to_disclosed_only,
        test_ontopic_and_rescued_spans_promote,
        test_conservation_promoted_union_disclosed_is_full_set,
        test_topical_gate_off_is_byte_identical_promote_all,
        test_malformed_topical_overlap_env_raises_value_error,
        test_empty_bullet_unit_split_drops_marker_only_bullet,
        test_orphan_citation_bullet_unit_split_drops,
        test_real_bullet_unit_split_untouched,
        test_render_seam_belt_drops_empty_bullets_keeps_real,
    ]
    for fn in fns:
        fn()
        print(f"PASS {fn.__name__}")
    print(f"\nALL {len(fns)} UNIT-1 ASSERTIONS PASS")


if __name__ == "__main__":
    main()
