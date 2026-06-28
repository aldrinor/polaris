"""I-deepfix B08 (#1352): disclosure-to-render gap behavioral tests.

These assert the render/disclosure-layer fixes through the PRODUCTION code paths:

  1. ``build_d8_unadjudicated_banner`` emits the run-specific banner ONLY when the
     serialized ``release_disclosure.adjudicated`` is False (and stays silent on a
     genuinely-judged release / missing flag).
  2. ``render_full_drop_disclosure_md`` surfaces the FULL drop accounting
     (support-failed + un-provenanced + dedup-redundant + claim-frame) so the report's
     "Evidence-support disclosure" total is no longer an undercount of the partial subset.
  3. The full disclosure is built over the SAME drop-classification path the run uses
     (``build_drop_disclosure`` over real ``SentenceVerification`` objects), so the
     numbers in the report match ``verification_details.json``.

Faithfulness engine is NOT exercised or relaxed here — these are pure disclosure helpers
that only convert a silent / partial disclosure into a complete, honest one.

Run single-threaded:
    PYTHONPATH=<worktree> python -m pytest tests/polaris_graph/test_b08_disclosure_render_gap.py -q
"""

from src.polaris_graph.generator.provenance_generator import (
    ProvenanceToken,
    SentenceVerification,
    build_d8_unadjudicated_banner,
    build_drop_disclosure,
    render_full_drop_disclosure_md,
)

_BANNER_MARKER = "STRONGEST VERIFIER (four-role D8) DID NOT RUN"


def _sv(sentence: str, reasons: list[str], *, provenanced: bool = True) -> SentenceVerification:
    """Construct a DROPPED SentenceVerification with the given failure reasons."""
    tokens = (
        [ProvenanceToken("ev_001", 0, 10, "[#ev:ev_001:0-10]")] if provenanced else []
    )
    return SentenceVerification(
        sentence=sentence,
        tokens=tokens,
        is_verified=False,
        failure_reasons=list(reasons),
    )


# ── Fix #1: D8-unadjudicated banner ─────────────────────────────────────────────


def test_banner_emitted_when_adjudicated_false():
    banner = build_d8_unadjudicated_banner({"adjudicated": False})
    assert banner != ""
    assert _BANNER_MARKER in banner
    assert "UNVERIFIED-by-D8" in banner


def test_banner_silent_when_adjudicated_true():
    assert build_d8_unadjudicated_banner({"adjudicated": True}) == ""


def test_banner_silent_when_flag_missing_or_malformed():
    # No adjudicated key -> cannot assert the verifier was skipped -> no banner.
    assert build_d8_unadjudicated_banner({"disclosed_gaps": ["x"]}) == ""
    assert build_d8_unadjudicated_banner(None) == ""
    assert build_d8_unadjudicated_banner("not-a-dict") == ""
    # I-deepfix-001 Codex P2 (iter 3): a MALFORMED falsey value is NOT an explicit
    # adjudicated==False — strict identity, so None/0/"" must stay banner-free.
    assert build_d8_unadjudicated_banner({"adjudicated": None}) == ""
    assert build_d8_unadjudicated_banner({"adjudicated": 0}) == ""
    assert build_d8_unadjudicated_banner({"adjudicated": ""}) == ""


def test_banner_is_a_top_of_report_blockquote_not_a_finding():
    # The banner is a markdown blockquote disclosure; it must not look like a cited finding
    # (no provenance token, no "[N]" citation marker spliced in).
    banner = build_d8_unadjudicated_banner({"adjudicated": False})
    assert banner.lstrip().startswith(">")
    assert "[#ev:" not in banner


# ── Fix #2: full-count evidence-support disclosure ──────────────────────────────


def test_full_disclosure_counts_ALL_categories_not_just_support_failed():
    # 2 support-failed (provenanced, real verification failures) + 1 un-provenanced.
    dropped = [
        _sv("Unsupported claim one.", ["numeric_mismatch"]),
        _sv("Unsupported claim two.", ["overlap_too_low"]),
        _sv("No token here.", ["no_provenance_token"], provenanced=False),
    ]
    summary = build_drop_disclosure(dropped)
    assert summary["support_failed_count"] == 2
    assert summary["unprovenanced_count"] == 1

    md = render_full_drop_disclosure_md(
        summary, dedup_redundant_count=6, m41c_underframed_count=1,
    )
    # True total = 2 + 1 + 6 + 1 = 10. The PARTIAL (support-failed-only) render would have
    # said "2 removed" — the gap B08 fixes.
    assert "## Evidence-support disclosure" in md
    assert "10 generated sentence(s) were REMOVED" in md
    # Each category is named with its own count.
    assert "Support-failed (2)" in md
    assert "Un-provenanced (1)" in md
    assert "Dedup-redundant (6)" in md
    assert "Claim-frame policy (1)" in md


def test_full_disclosure_undercount_is_fixed_vs_support_failed_subset():
    # Reproduce the member-finding shape: support-failed alone would understate the total.
    dropped = [_sv("bad.", ["entailment_failed"])]  # 1 support-failed only
    summary = build_drop_disclosure(dropped)
    md = render_full_drop_disclosure_md(
        summary, dedup_redundant_count=6, m41c_underframed_count=1,
    )
    # Honest total includes the consolidation + policy drops the old block ignored.
    assert "8 generated sentence(s) were REMOVED" in md
    assert "Dedup-redundant (6)" in md


def test_full_disclosure_empty_when_nothing_dropped():
    summary = build_drop_disclosure([])
    assert render_full_drop_disclosure_md(summary) == ""


def test_full_disclosure_never_renders_raw_dropped_sentence_text():
    # Faithfulness invariant: a hallucinated/unsupported dropped sentence must NEVER ship as
    # prose — only COUNTS + reason keys are disclosed.
    secret = "Tirzepatide cures everything at 0.1mg."
    dropped = [_sv(secret, ["numeric_mismatch"])]
    summary = build_drop_disclosure(dropped)
    md = render_full_drop_disclosure_md(summary)
    assert secret not in md
    # The reason KEY is allowed (it is metadata, not the claim).
    assert "numeric_mismatch" in md


def test_full_disclosure_reason_keys_collapse_parameterized_detail():
    dropped = [_sv("x.", ["numeric_mismatch:42 not in span"])]
    summary = build_drop_disclosure(dropped)
    md = render_full_drop_disclosure_md(summary)
    # Parameterized "reason:detail" collapses to the bare key.
    assert "numeric_mismatch" in md
    assert "42 not in span" not in md
