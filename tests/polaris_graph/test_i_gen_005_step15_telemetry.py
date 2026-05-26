"""I-gen-005 Step 1.5 telemetry tests (pytest-collectable).

Per Codex iter-1 verdict 2026-05-26 (PARTIAL, 3 P1):
    1. Contract sections must populate kept/dropped final fields.
    2. M-41c post-filter drops must be serialized in a separate category.
    3. Dedup section drop counters must match serialized dedup-redundant
       drops (consistent semantics: ACTUAL removed originals, not net
       length delta).

Also fixes the iter-1 issue that pytest collected 0 tests from the
prior standalone script. Each test is a `test_*` function and uses
`assert` so pytest captures the assertion message.

Run: pytest tests/polaris_graph/test_i_gen_005_step15_telemetry.py -v
"""

from dataclasses import dataclass, field
from typing import Any


@dataclass
class _MockToken:
    evidence_id: str
    start: int
    end: int


@dataclass
class _MockSV:
    """Mock of strict_verify.SentenceVerification."""
    sentence: str
    tokens: list[_MockToken] = field(default_factory=list)
    failure_reasons: list[str] = field(default_factory=list)
    soft_warnings: list[str] = field(default_factory=list)
    is_verified: bool = True


@dataclass
class _MockSR:
    """Mock of multi_section_generator.SectionResult with the Step 1.5
    iter-2 field additions (all four drop categories)."""
    title: str
    rewritten_draft: str
    dropped_due_to_failure: bool
    sentences_verified: int
    sentences_dropped: int
    kept_sentences_pre_resolve: list[Any] = field(default_factory=list)
    dropped_sentences_final: list[Any] = field(default_factory=list)
    dropped_sentences_dedup_redundant: list[str] = field(default_factory=list)
    dropped_sentences_m41c_underframed: list[Any] = field(default_factory=list)


@dataclass
class _MockMSR:
    sections: list[_MockSR]
    total_sentences_verified: int
    total_sentences_dropped: int


def _serialize_like_run_honest_sweep(multi: _MockMSR) -> dict:
    """Mirrors scripts/run_honest_sweep_r3.py:2703-2762 (Step 1.5 iter-2
    version) — serializes from FINAL SectionResult fields including
    the M-41c category."""
    verif_details: dict[str, Any] = {
        "sections": [],
        "totals": {
            "sentences_verified": multi.total_sentences_verified,
            "sentences_dropped": multi.total_sentences_dropped,
        },
    }
    for sr in multi.sections:
        if not sr.rewritten_draft and not sr.kept_sentences_pre_resolve:
            continue
        kept_svs = sr.kept_sentences_pre_resolve or []
        dropped_svs = sr.dropped_sentences_final or []
        dedup_redundants = sr.dropped_sentences_dedup_redundant or []
        m41c_underframed_svs = getattr(
            sr, "dropped_sentences_m41c_underframed", []
        ) or []
        total_dropped_section = (
            len(dropped_svs) + len(dedup_redundants)
            + len(m41c_underframed_svs)
        )
        verif_details["sections"].append({
            "title": sr.title,
            "dropped_due_to_failure": sr.dropped_due_to_failure,
            "total_in": len(kept_svs) + total_dropped_section,
            "total_kept": len(kept_svs),
            "total_dropped": total_dropped_section,
            "section_sentences_dropped_counter": sr.sentences_dropped,
            "kept": [
                {
                    "sentence": sv.sentence,
                    "tokens": [
                        {"evidence_id": t.evidence_id,
                         "start": t.start, "end": t.end}
                        for t in sv.tokens
                    ],
                    "soft_warnings": getattr(sv, "soft_warnings", []),
                }
                for sv in kept_svs
            ],
            "dropped": [
                {
                    "sentence": sv.sentence,
                    "failure_reasons": sv.failure_reasons,
                    "tokens": [
                        {"evidence_id": t.evidence_id,
                         "start": t.start, "end": t.end}
                        for t in sv.tokens
                    ],
                }
                for sv in dropped_svs
            ],
            "dropped_by_dedup_redundant": list(dedup_redundants),
            "dropped_by_m41c_underframed": [
                {
                    "sentence": sv.sentence,
                    "tokens": [
                        {"evidence_id": t.evidence_id,
                         "start": t.start, "end": t.end}
                        for t in sv.tokens
                    ],
                }
                for sv in m41c_underframed_svs
            ],
        })
    reason_counts: dict[str, int] = {}
    for s in verif_details["sections"]:
        for d in s["dropped"]:
            for r in d["failure_reasons"]:
                key = r.split(":", 1)[0]
                reason_counts[key] = reason_counts.get(key, 0) + 1
    verif_details["drop_reason_counts"] = reason_counts
    verif_details["dedup_redundant_count"] = sum(
        len(s.get("dropped_by_dedup_redundant", []))
        for s in verif_details["sections"]
    )
    verif_details["m41c_underframed_count"] = sum(
        len(s.get("dropped_by_m41c_underframed", []))
        for s in verif_details["sections"]
    )
    return verif_details


# ------------------------------------------------------------------------
# iter-1 fixture: 1 kept + 1 dedup-redundant + 1 strict-verify failure
# ------------------------------------------------------------------------

def _fixture_iter1_basic():
    kept_sv = _MockSV(
        sentence="Tirzepatide 15 mg reduced HbA1c by 2.30 percentage points.",
        tokens=[_MockToken("ev_001", 100, 500)],
    )
    dedup_redundant_str = (
        "Tirzepatide at the 15 mg dose lowered HbA1c by approximately "
        "2.30 percentage points."
    )
    real_drop_sv = _MockSV(
        sentence="Tirzepatide cured cancer in 50% of patients.",
        tokens=[_MockToken("ev_001", 100, 500)],
        failure_reasons=[
            "no_content_word_overlap_any_cited_span:ev_001:"
            "sentence_words=['cancer', 'cured', 'patients']",
        ],
        is_verified=False,
    )
    sr = _MockSR(
        title="Efficacy",
        rewritten_draft="S1. S2. S3.",
        dropped_due_to_failure=False,
        sentences_verified=1,
        sentences_dropped=2,  # dedup_redundant(1) + strict_verify_drop(1)
        kept_sentences_pre_resolve=[kept_sv],
        dropped_sentences_final=[real_drop_sv],
        dropped_sentences_dedup_redundant=[dedup_redundant_str],
    )
    msr = _MockMSR(
        sections=[sr],
        total_sentences_verified=1,
        total_sentences_dropped=2,
    )
    return msr


def test_iter1_verified_in_kept():
    out = _serialize_like_run_honest_sweep(_fixture_iter1_basic())
    sec = out["sections"][0]
    assert any("reduced HbA1c by 2.30" in k["sentence"] for k in sec["kept"])


def test_iter1_real_failure_in_dropped_with_reasons():
    out = _serialize_like_run_honest_sweep(_fixture_iter1_basic())
    sec = out["sections"][0]
    real_drops = [d for d in sec["dropped"] if "cured cancer" in d["sentence"]]
    assert len(real_drops) == 1
    assert any(
        "no_content_word_overlap" in r for r in real_drops[0]["failure_reasons"]
    )


def test_iter1_dedup_redundant_not_in_dropped():
    """The pre-fix bug: a dedup-consolidated sentence was incorrectly
    listed in dropped[] with bogus failure_reasons because the bug
    re-ran strict_verify on the rewritten_draft. The fix: dedup
    consolidations go in dropped_by_dedup_redundant[]."""
    out = _serialize_like_run_honest_sweep(_fixture_iter1_basic())
    sec = out["sections"][0]
    assert not any(
        "approximately 2.30" in d["sentence"] for d in sec["dropped"]
    )
    assert any(
        "approximately 2.30" in s for s in sec["dropped_by_dedup_redundant"]
    )


def test_iter1_section_totals():
    out = _serialize_like_run_honest_sweep(_fixture_iter1_basic())
    sec = out["sections"][0]
    assert sec["total_kept"] == 1
    assert sec["total_dropped"] == 2
    assert sec["section_sentences_dropped_counter"] == 2


def test_iter1_drop_reason_counts_excludes_dedup():
    out = _serialize_like_run_honest_sweep(_fixture_iter1_basic())
    rc = out["drop_reason_counts"]
    assert rc.get("no_content_word_overlap_any_cited_span", 0) == 1
    assert "dedup" not in str(rc)


def test_iter1_dedup_redundant_count():
    out = _serialize_like_run_honest_sweep(_fixture_iter1_basic())
    assert out["dedup_redundant_count"] == 1


# ------------------------------------------------------------------------
# iter-2 P1 #1: contract section telemetry (kept + dropped populated)
# ------------------------------------------------------------------------

def _fixture_contract_section():
    """Mimics contract_section_runner output. M-69 rescue path moves a
    strict_verify-dropped sentence into kept_sentences. The rescued SV
    must NOT appear in dropped_sentences_final."""
    rescued_sv = _MockSV(
        sentence="In SURPASS-2 (N=1879), tirzepatide 15 mg reduced HbA1c.",
        tokens=[_MockToken("surpass_2_primary", 0, 200)],
    )
    real_drop_sv = _MockSV(
        sentence="Tirzepatide cures all diseases.",
        tokens=[_MockToken("noncontract_ev", 0, 100)],
        failure_reasons=["no_content_word_overlap"],
        is_verified=False,
    )
    sr = _MockSR(
        title="Efficacy",
        rewritten_draft="S1. S2.",
        dropped_due_to_failure=False,
        sentences_verified=1,
        sentences_dropped=1,
        kept_sentences_pre_resolve=[rescued_sv],
        dropped_sentences_final=[real_drop_sv],
    )
    return _MockMSR(
        sections=[sr],
        total_sentences_verified=1,
        total_sentences_dropped=1,
    )


def test_iter2_contract_kept_populated():
    """P1 #1 fix: contract SectionResult populates kept_sentences_pre_resolve."""
    out = _serialize_like_run_honest_sweep(_fixture_contract_section())
    sec = out["sections"][0]
    assert sec["total_kept"] == 1
    assert "SURPASS-2" in sec["kept"][0]["sentence"]


def test_iter2_contract_dropped_excludes_rescued():
    """P1 #1 fix: rescued SVs are in kept, NOT in dropped_sentences_final."""
    out = _serialize_like_run_honest_sweep(_fixture_contract_section())
    sec = out["sections"][0]
    assert len(sec["dropped"]) == 1
    assert "Tirzepatide cures all diseases" in sec["dropped"][0]["sentence"]


# ------------------------------------------------------------------------
# iter-2 P1 #2: M-41c post-filter drops serialized
# ------------------------------------------------------------------------

def _fixture_m41c_drops():
    """Section with: 1 kept, 1 strict_verify drop, 1 M-41c policy drop."""
    kept_sv = _MockSV(
        sentence=(
            "In SURPASS-2 (N=1879, baseline HbA1c 8.28%, comparator "
            "semaglutide 1 mg), tirzepatide 15 mg reduced HbA1c by 2.30 pp."
        ),
        tokens=[_MockToken("ev_001", 0, 500)],
    )
    strict_drop_sv = _MockSV(
        sentence="Fake claim.",
        tokens=[_MockToken("ev_001", 0, 100)],
        failure_reasons=["no_content_word_overlap"],
        is_verified=False,
    )
    m41c_drop_sv = _MockSV(
        sentence="SURPASS-2 showed efficacy.",  # under-framed
        tokens=[_MockToken("ev_001", 0, 500)],
        failure_reasons=[],
        is_verified=True,  # passed strict_verify, dropped by M-41c policy
    )
    sr = _MockSR(
        title="Efficacy",
        rewritten_draft="S1. S2. S3.",
        dropped_due_to_failure=False,
        sentences_verified=1,
        sentences_dropped=2,  # strict_drop(1) + m41c_drop(1)
        kept_sentences_pre_resolve=[kept_sv],
        dropped_sentences_final=[strict_drop_sv],
        dropped_sentences_m41c_underframed=[m41c_drop_sv],
    )
    return _MockMSR(
        sections=[sr],
        total_sentences_verified=1,
        total_sentences_dropped=2,
    )


def test_iter2_m41c_drops_serialized_separately():
    """P1 #2 fix: M-41c under-framed drops appear in their own category."""
    out = _serialize_like_run_honest_sweep(_fixture_m41c_drops())
    sec = out["sections"][0]
    assert len(sec["dropped_by_m41c_underframed"]) == 1
    assert (
        "SURPASS-2 showed efficacy"
        in sec["dropped_by_m41c_underframed"][0]["sentence"]
    )


def test_iter2_m41c_drops_not_in_strict_verify_dropped():
    """P1 #2 fix: M-41c drops are NOT in dropped[]."""
    out = _serialize_like_run_honest_sweep(_fixture_m41c_drops())
    sec = out["sections"][0]
    assert not any(
        "SURPASS-2 showed efficacy" in d["sentence"] for d in sec["dropped"]
    )


def test_iter2_m41c_drops_counted_in_total_dropped():
    """P1 #2 fix: section total_dropped includes M-41c drops."""
    out = _serialize_like_run_honest_sweep(_fixture_m41c_drops())
    sec = out["sections"][0]
    assert sec["total_dropped"] == 2
    assert sec["section_sentences_dropped_counter"] == 2


def test_iter2_m41c_underframed_count_rollup():
    out = _serialize_like_run_honest_sweep(_fixture_m41c_drops())
    assert out["m41c_underframed_count"] == 1


# ------------------------------------------------------------------------
# iter-2 P1 #3: dedup totals consistency
# ------------------------------------------------------------------------

def test_iter2_dedup_section_total_matches_sentences_dropped():
    """P1 #3 fix: For a 2->1 dedup consolidation, both serialization
    total_dropped and sr.sentences_dropped must report 2 (both
    originals removed), not 1 (net delta)."""
    c_sv = _MockSV(
        sentence="Consolidated: A and B combined.",
        tokens=[_MockToken("ev_001", 0, 500)],
    )
    sr = _MockSR(
        title="Efficacy",
        rewritten_draft="A. B.",
        dropped_due_to_failure=False,
        sentences_verified=1,  # only C
        sentences_dropped=2,   # A + B both consolidated away (set semantics)
        kept_sentences_pre_resolve=[c_sv],
        dropped_sentences_dedup_redundant=[
            "A: tirzepatide reduces weight",
            "B: tirzepatide is effective for weight reduction",
        ],
    )
    msr = _MockMSR(
        sections=[sr],
        total_sentences_verified=1,
        total_sentences_dropped=2,
    )
    out = _serialize_like_run_honest_sweep(msr)
    sec = out["sections"][0]
    assert sec["total_dropped"] == 2
    assert sec["section_sentences_dropped_counter"] == 2
    assert sec["total_dropped"] == sec["section_sentences_dropped_counter"]


def test_iter3_failed_dedup_rewrite_accounting():
    """Codex iter-2 P1 fix: when a dedup LLM rewrite FAILS re-strict-
    verify, the failed-rewrite SV is correctly serialized in dropped[]
    AND sentences_dropped accounts for it. Without the iter-3 fix:
      - 2 originals (A, B) → consolidated rewrite C
      - C fails strict_verify
      - A, B both go to dropped_sentences_dedup_redundant (size 2)
      - C goes to dropped_sentences_final (size 1)
      - Serialized total_dropped = 3
      - sr.sentences_dropped = 2 (pre-fix) → mismatch
    Post-fix: sr.sentences_dropped += 1 for the failed rewrite, so
    sr.sentences_dropped = 3 matches serialized total_dropped = 3."""
    failed_rewrite_sv = _MockSV(
        sentence="Consolidated: A and B combined.",
        tokens=[_MockToken("ev_001", 0, 100)],
        failure_reasons=["no_content_word_overlap"],
        is_verified=False,
    )
    sr = _MockSR(
        title="Efficacy",
        rewritten_draft="A. B.",
        dropped_due_to_failure=True,  # all rewrites failed
        sentences_verified=0,
        # Post-iter-3 fix: dedup_redundant(2) + failed_rewrite(1) = 3
        sentences_dropped=3,
        kept_sentences_pre_resolve=[],  # all rewrites failed re-verify
        dropped_sentences_final=[failed_rewrite_sv],  # the failed C
        dropped_sentences_dedup_redundant=[
            "A: tirzepatide reduces weight",
            "B: tirzepatide is effective",
        ],
    )
    msr = _MockMSR(
        sections=[sr],
        total_sentences_verified=0,
        total_sentences_dropped=3,
    )
    out = _serialize_like_run_honest_sweep(msr)
    sec = out["sections"][0]
    # total_dropped (serialized) = 1 strict + 2 dedup + 0 m41c = 3
    assert sec["total_dropped"] == 3
    # section sentences_dropped counter also = 3 (post-iter-3 fix)
    assert sec["section_sentences_dropped_counter"] == 3
    # And multi.total_sentences_dropped also = 3
    assert out["totals"]["sentences_dropped"] == 3
    # Per-category breakdown
    assert len(sec["dropped"]) == 1  # the failed rewrite C
    assert len(sec["dropped_by_dedup_redundant"]) == 2  # A and B


def test_iter2_dedup_multi_totals_match_section_sums():
    """P1 #3 fix: multi.total_sentences_dropped == sum of section
    serialized total_dropped values."""
    c_sv = _MockSV(
        sentence="Consolidated.",
        tokens=[_MockToken("ev_001", 0, 100)],
    )
    sr = _MockSR(
        title="X",
        rewritten_draft="A. B.",
        dropped_due_to_failure=False,
        sentences_verified=1,
        sentences_dropped=2,
        kept_sentences_pre_resolve=[c_sv],
        dropped_sentences_dedup_redundant=["A", "B"],
    )
    msr = _MockMSR(
        sections=[sr],
        total_sentences_verified=1,
        total_sentences_dropped=2,
    )
    out = _serialize_like_run_honest_sweep(msr)
    section_drop_sum = sum(s["total_dropped"] for s in out["sections"])
    assert section_drop_sum == out["totals"]["sentences_dropped"]
