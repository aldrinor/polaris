"""Lane C (#1179) — offline deterministic tests for the three presentation-hygiene
fixes BB5-P01/P02/P03 in ``scripts/run_honest_sweep_r3.py``.

No network, no spend: the helpers under test are pure string/list transforms that
take record-shaped objects (duck-typed via ``getattr``) and return markdown.

- BB5-P01: ``render_qualitative_disclosure`` — clinical-gate, dedup, review-flag
  collapse. Qualitative records are NOT passed to the PT08 evaluator gate, so the
  collapse is faithfulness-safe.
- BB5-P02: ``render_semantic_disclosure`` — strip scraped junk, trim quotes, cap
  inline, but KEEP subject+predicate of every record (PT08 contract).
- BB5-P03: ``dedup_identical_paragraphs`` — content-identity dedup of the
  drb_90 duplicate paragraph + removal of the header it orphans, while the
  distinct synthesized Limitations disclosure is preserved (no silent downgrade).
"""
from __future__ import annotations

from dataclasses import dataclass, field

import pytest

from scripts.run_honest_sweep_r3 import (
    dedup_identical_paragraphs,
    render_qualitative_disclosure,
    render_semantic_disclosure,
)


# ─────────────────────────────────────────────────────────────────────────────
# Record stand-ins (duck-typed; mirror the real dataclasses' fields)
# ─────────────────────────────────────────────────────────────────────────────
@dataclass
class _QualRecord:
    subject: str
    predicate: str
    severity: str
    claims: list = field(default_factory=list)
    conflict_reason: str = "present-vs-absent across sources"


@dataclass
class _SemRecord:
    subject: str
    predicate: str
    claims: list = field(default_factory=list)
    nli_confidence: float = 0.0


def _qual_claims(
    status_a: str,
    status_b: str,
    *,
    ev_a: str = "ev1",
    ev_b: str = "ev2",
) -> list:
    return [
        {"assertion_status": status_a, "evidence_id": ev_a, "source_tier": "T1"},
        {"assertion_status": status_b, "evidence_id": ev_b, "source_tier": "T2"},
    ]


# ─────────────────────────────────────────────────────────────────────────────
# BB5-P01 — qualitative
# ─────────────────────────────────────────────────────────────────────────────
def test_qualitative_non_clinical_renders_nothing() -> None:
    """Clinical-safety detector mis-fires on non-clinical Qs (drb_90 ADAS, drb_72
    labor) — the renderer must emit NOTHING for a non-clinical domain."""
    records = [_QualRecord("warfarin", "contraindication", "high", _qual_claims("PRESENT", "ABSENT"))]
    assert render_qualitative_disclosure(records, is_clinical=False) == ""


def test_qualitative_empty_renders_nothing() -> None:
    assert render_qualitative_disclosure([], is_clinical=True) == ""


def test_qualitative_dedups_identical_rows() -> None:
    """drb_75's 246 lines were duplicate (subject,predicate,status) rows — the
    renderer collapses identical signatures to one line."""
    dup = _QualRecord("probiotic", "contraindication", "high", _qual_claims("PRESENT", "ABSENT"))
    dup2 = _QualRecord("probiotic", "contraindication", "high", _qual_claims("PRESENT", "ABSENT"))
    unique = _QualRecord("iron", "warning", "high", _qual_claims("PRESENT", "ABSENT"))
    out = render_qualitative_disclosure([dup, dup2, unique], is_clinical=True)
    assert out.count("[CONFLICT]") == 2  # dup collapsed to one, plus unique
    assert "flagged 2 present-vs-absent" in out


def test_qualitative_review_flags_collapse_to_count_and_sidecar() -> None:
    """REVIEW flags are advisory, not adjudicated — by default they collapse to a
    one-line count + sidecar pointer (not a verbatim dump)."""
    reviews = [
        _QualRecord("a", "drug_interaction", "review", _qual_claims("PRESENT", "INDETERMINATE")),
        _QualRecord("b", "eligibility", "review", _qual_claims("ABSENT", "INDETERMINATE")),
    ]
    out = render_qualitative_disclosure(reviews, is_clinical=True)
    assert "[REVIEW]" not in out  # not dumped verbatim
    assert "2 review-flagged item(s) collapsed" in out
    assert "contradictions.json" in out  # sidecar pointer


def test_qualitative_review_inline_opt_in_renders_rows() -> None:
    reviews = [_QualRecord("a", "drug_interaction", "review", _qual_claims("PRESENT", "INDETERMINATE"))]
    out = render_qualitative_disclosure(reviews, is_clinical=True, review_inline=True)
    assert "[REVIEW] a / drug_interaction" in out


def test_qualitative_review_dedup_excludes_evidence_id() -> None:
    """BB5-P01 iter-2 (#1179, Codex P2): two [REVIEW] rows identical by
    (subject, predicate, assertion_status) but citing DIFFERENT evidence_ids must
    collapse to ONE row. The prior key included evidence_id, so these slipped past
    the dedup. ``review_inline=True`` makes the surviving rows visible to count."""
    dup_a = _QualRecord(
        "ssri", "drug_interaction", "review",
        _qual_claims("PRESENT", "INDETERMINATE", ev_a="ev1", ev_b="ev2"),
    )
    dup_b = _QualRecord(
        "ssri", "drug_interaction", "review",
        _qual_claims("PRESENT", "INDETERMINATE", ev_a="ev9", ev_b="ev7"),
    )
    unique = _QualRecord(
        "lithium", "drug_interaction", "review",
        _qual_claims("ABSENT", "INDETERMINATE", ev_a="ev3", ev_b="ev4"),
    )
    out = render_qualitative_disclosure(
        [dup_a, dup_b, unique], is_clinical=True, review_inline=True,
    )
    # The (ssri, drug_interaction, PRESENT/INDETERMINATE) signature collapses 2 -> 1.
    assert out.count("[REVIEW] ssri / drug_interaction") == 1
    assert out.count("[REVIEW] lithium / drug_interaction") == 1
    assert out.count("[REVIEW]") == 2  # 1 collapsed ssri + 1 lithium


def test_qualitative_hard_conflict_dedup_excludes_evidence_id() -> None:
    """The same evidence-id-independent signature collapse applies to the hard
    CONFLICT path: two CONFLICT rows identical by (subject, predicate, status) but
    citing different evidence collapse to one. Qualitative records are NOT
    PT08-gated, so this is faithfulness-safe (intentional, not a slip)."""
    dup_a = _QualRecord(
        "warfarin", "contraindication", "high",
        _qual_claims("PRESENT", "ABSENT", ev_a="ev1", ev_b="ev2"),
    )
    dup_b = _QualRecord(
        "warfarin", "contraindication", "high",
        _qual_claims("PRESENT", "ABSENT", ev_a="ev8", ev_b="ev5"),
    )
    out = render_qualitative_disclosure([dup_a, dup_b], is_clinical=True)
    assert out.count("[CONFLICT] warfarin / contraindication") == 1


def test_qualitative_keeps_hard_conflicts_inline() -> None:
    """Auto-fired adjudicated CONFLICT rows belong in prose and must survive."""
    hard = [_QualRecord("warfarin", "contraindication", "high", _qual_claims("PRESENT", "ABSENT"))]
    out = render_qualitative_disclosure(hard, is_clinical=True)
    assert "[CONFLICT] warfarin / contraindication" in out
    assert "PRESENT" in out and "ABSENT" in out


# ─────────────────────────────────────────────────────────────────────────────
# BB5-P02 — semantic (PT08 contract: subject+predicate of EVERY record inline)
# ─────────────────────────────────────────────────────────────────────────────
_PT08_PREDICATE = "cross-document directional disagreement"


def _sem_record(subject: str, text_a: str, text_b: str, conf: float = 0.91) -> _SemRecord:
    return _SemRecord(
        subject=subject,
        predicate=_PT08_PREDICATE,
        nli_confidence=conf,
        claims=[
            {"evidence_id": "evA", "text": text_a, "tier": "T1"},
            {"evidence_id": "evB", "text": text_b, "tier": "T2"},
        ],
    )


def test_semantic_empty_renders_nothing() -> None:
    assert render_semantic_disclosure([]) == ""


def test_semantic_strips_bibliography_and_image_urls() -> None:
    """The drb_76 dump printed a full numbered bibliography + image markdown +
    bare URLs. Those must be stripped from the rendered summary."""
    junk = (
        "Probiotics reduced inflammation in the colon.\n"
        "1. Smith J. Gut microbiota. doi:10.1/x\n"
        "2. Doe A. CRC review. doi:10.2/y\n"
        "![figure 1](https://img.example.com/fig1.png)\n"
        "See https://example.com/full-text for details."
    )
    rec = _sem_record("probiotics", junk, "No effect on inflammation was observed.")
    out = render_semantic_disclosure([rec], quote_trim=200)
    assert "doi:10.1/x" not in out
    assert "https://img.example.com" not in out
    assert "https://example.com/full-text" not in out
    assert "![figure" not in out
    assert "Probiotics reduced inflammation" in out


def test_semantic_trims_quote_to_cap() -> None:
    long_text = "word " * 200  # 1000 chars
    rec = _sem_record("subjectx", long_text, "short opposing claim")
    out = render_semantic_disclosure([rec], quote_trim=50)
    # The trimmed quote must be short; the ellipsis marks truncation.
    assert "…" in out
    # No single rendered quote should approach the raw 1000-char length.
    assert len(out) < 1200


def test_semantic_keeps_subject_predicate_for_every_record_pt08() -> None:
    """PT08 contract: even beyond the inline cap, subject+predicate of EVERY record
    must appear in the report text so the evaluator gate passes."""
    records = [_sem_record(f"subject{i}", f"claim {i} up", f"claim {i} down") for i in range(15)]
    out = render_semantic_disclosure(records, inline_cap=3, quote_trim=80)
    for i in range(15):
        assert f"subject{i}" in out  # subject present for all 15
    assert out.count(_PT08_PREDICATE) == 15  # predicate present for all 15
    # Only the first 3 carry the trimmed quote payload; the rest are pointer lines.
    assert out.count("full pair in") == 12


def test_semantic_inline_cap_zero_still_emits_subject_predicate() -> None:
    records = [_sem_record("alpha", "x up", "x down")]
    out = render_semantic_disclosure(records, inline_cap=0)
    assert "alpha" in out
    assert _PT08_PREDICATE in out


# ─────────────────────────────────────────────────────────────────────────────
# BB5-P03 — content-identity dedup + orphan-header removal
# ─────────────────────────────────────────────────────────────────────────────
def test_dedup_drops_verbatim_duplicate_and_orphaned_header() -> None:
    """drb_90: Implications body == first Limitations body (byte-identical after
    stripping citation markers, citation NUMBERS differ). The duplicate body AND the
    now-empty '### Limitations' header it left behind are both removed; the distinct
    synthesized Limitations disclosure that follows is KEPT (no silent downgrade)."""
    para = "This finding implies a material liability shift toward the manufacturer"
    report = (
        f"### Implications\n\n{para} [8][10].\n\n"
        f"### Limitations\n\n{para} [1][2].\n\n"
        f"### Limitations\n\nLimitations: the corpus is 84% UNKNOWN and 2% T1."
    )
    out = dedup_identical_paragraphs(report)
    # Duplicate body appears once (kept under Implications).
    assert out.count("material liability shift toward the manufacturer") == 1
    # The orphaned (now-empty) Limitations header is dropped → exactly one remains.
    assert out.count("### Limitations") == 1
    # The unique synthesized disclosure SURVIVES (the silent-downgrade guard).
    assert "84% UNKNOWN" in out
    # The single remaining Limitations header is immediately followed by its real body.
    idx = out.index("### Limitations")
    assert "Limitations: the corpus is 84% UNKNOWN" in out[idx:idx + 120]


def test_dedup_merges_distinct_limitations_into_single_header() -> None:
    """BB5-P03 iter-2 (#1179, Codex P1): when the outline Limitations and the
    synthesized Limitations have DIFFERENT bodies, the report must STILL render only
    ONE '### Limitations' header. The distinct synthesized body is relocated (merged)
    under the first header — kept, never dropped (no silent downgrade)."""
    report = (
        "### Limitations\n\nThe corpus skews toward reviews.\n\n"
        "### Limitations\n\nA different appended limitation note about UNKNOWN tiers."
    )
    out = dedup_identical_paragraphs(report)
    # Exactly one Limitations header even though the two bodies differ.
    assert out.count("### Limitations") == 1
    # BOTH distinct bodies survive (merged under the single header).
    assert "The corpus skews toward reviews." in out
    assert "A different appended limitation note about UNKNOWN tiers." in out
    # The merged bodies both sit under the single Limitations header.
    idx = out.index("### Limitations")
    assert "The corpus skews toward reviews." in out[idx:]
    assert "A different appended limitation note about UNKNOWN tiers." in out[idx:]


def test_dedup_merges_distinct_limitations_when_not_adjacent() -> None:
    """Defensive: the two '### Limitations' headers can be NON-adjacent in production
    (an intervening section — e.g. Analyst Synthesis — may sit between the outline
    Limitations and the appended synthesized one). The duplicate header is still
    dropped and its body relocated under the FIRST Limitations header, leaving the
    intervening section's own header intact."""
    report = (
        "### Limitations\n\nThe corpus skews toward reviews.\n\n"
        "## Analyst Synthesis\n\nA synthesis paragraph that must keep its own header.\n\n"
        "### Limitations\n\nAppended corpus-skew disclosure about UNKNOWN tiers."
    )
    out = dedup_identical_paragraphs(report)
    assert out.count("### Limitations") == 1
    assert "## Analyst Synthesis" in out  # intervening header untouched
    assert "A synthesis paragraph that must keep its own header." in out
    # The relocated body is filed under the first Limitations header, BEFORE the
    # Analyst Synthesis header (merge-to-first), and survives.
    assert "Appended corpus-skew disclosure about UNKNOWN tiers." in out
    lim_idx = out.index("### Limitations")
    syn_idx = out.index("## Analyst Synthesis")
    assert lim_idx < syn_idx
    assert "Appended corpus-skew disclosure about UNKNOWN tiers." in out[lim_idx:syn_idx]


def test_dedup_keeps_distinct_paragraphs() -> None:
    report = (
        "First distinct paragraph about iron.\n\n"
        "Second distinct paragraph about copper.\n\n"
        "Third distinct paragraph about zinc."
    )
    out = dedup_identical_paragraphs(report)
    assert "iron" in out and "copper" in out and "zinc" in out
    assert out == report  # nothing dropped


def test_dedup_preserves_repeated_headers_with_distinct_bodies() -> None:
    """A header followed by a real (non-duplicate) body is never treated as orphaned."""
    report = "## Methods\n\nProtocol pinned.\n\n## Bibliography\n\n[1] Source — url"
    out = dedup_identical_paragraphs(report)
    assert "## Methods" in out and "## Bibliography" in out


def test_dedup_empty_report_is_noop() -> None:
    assert dedup_identical_paragraphs("") == ""


def test_dedup_real_drb90_artifact_is_clean() -> None:
    """§-1.1 real-output acceptance: run the helper on the actual beatboth5 drb_90
    report and assert the duplicate + orphaned header are gone while the unique
    corpus-skew disclosure survives. Skips if the artifact is absent."""
    import re
    from pathlib import Path

    artifact = Path(__file__).resolve().parents[2] / "outputs" / "audits" / "beatboth5" / "drb_90_polaris.md"
    if not artifact.exists():
        pytest.skip("real drb_90 artifact not present")
    raw = artifact.read_text(encoding="utf-8")
    out = dedup_identical_paragraphs(raw)
    headers_before = re.findall(r"^#{1,3} (Limitations|Implications)", raw, re.MULTILINE)
    headers_after = re.findall(r"^#{1,3} (Limitations|Implications)", out, re.MULTILINE)
    assert headers_before == ["Implications", "Limitations", "Limitations"]
    assert headers_after == ["Implications", "Limitations"]  # one duplicate dropped
    # Unique synthesized disclosure survives.
    assert "84% of the corpus classified as UNKNOWN" in out
    # Duplicate Implications/Limitations body collapses 2 -> 1.
    needle = "Empirical safety data for higher levels of automation"
    assert raw.count(needle) == 2 and out.count(needle) == 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
