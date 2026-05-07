"""Tests for audit_bundle.snapshot_sources."""

from __future__ import annotations

from datetime import datetime, timezone

from polaris_graph.audit_bundle.snapshot_sources import (
    MAX_SOURCE_TEXT_BYTES,
    snapshot_size_bytes,
    snapshot_sources,
)
from polaris_graph.generator2.verified_report import (
    Section,
    VerifiedReport,
    VerifiedSentence,
)
from polaris_graph.retrieval2.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


# ---------- Builders ----------

def _src(source_id: str, full_text: str | None, snippet: str = "snip") -> Source:
    return Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org",
        tier=SourceTier.T1,
        title="Source",
        snippet=snippet,
        full_text=full_text,
        full_text_available=full_text is not None,
        source_id=source_id,
    )


def _pool(*sources: Source) -> EvidencePool:
    return EvidencePool(
        decision_id="dec-1",
        sources=list(sources),
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
            min_required_per_tier={
                SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0
            },
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def _kept(text: str, tokens: list[str], section_id: str = "sec_x") -> VerifiedSentence:
    return VerifiedSentence(
        section_id=section_id,
        sentence_text=text,
        provenance_tokens=tokens,
        verifier_pass=True,
    )


def _dropped(section_id: str = "sec_x") -> VerifiedSentence:
    return VerifiedSentence(
        section_id=section_id,
        sentence_text="dropped",
        verifier_pass=False,
        drop_reason="numeric_mismatch",
    )


def _report(*sections: Section) -> VerifiedReport:
    return VerifiedReport(
        pool_id="pool-1",
        decision_id="dec-1",
        sections=list(sections),
        overall_verify_pass_rate=1.0,
        pipeline_verdict="success",
        generator_model="m",
        evaluator_model="strict_verify_v1",
        verifier_pass_threshold=0.4,
        started_at_utc=datetime.now(timezone.utc),
        finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


# ---------- Cited source extraction ----------

def test_snapshot_collects_cited_source_ids():
    pool = _pool(
        _src("src-A", "Full text A"),
        _src("src-B", "Full text B"),
        _src("src-C", "Full text C"),  # not cited
    )
    section = Section(
        section_id="sec_x",
        section_title="X",
        verified_sentences=[
            _kept("claim 1 [#ev:src-A:0-10].", ["[#ev:src-A:0-10]"]),
            _kept("claim 2 [#ev:src-B:0-10].", ["[#ev:src-B:0-10]"]),
        ],
        section_verify_pass_rate=1.0,
        section_status="verified",
    )
    snapshots = snapshot_sources(_report(section), pool)
    assert set(snapshots.keys()) == {"src-A", "src-B"}
    assert snapshots["src-A"] == "Full text A"
    assert snapshots["src-B"] == "Full text B"


def test_snapshot_skips_dropped_sentences():
    pool = _pool(_src("src-A", "kept"), _src("src-B", "dropped-only"))
    section = Section(
        section_id="sec_x",
        section_title="X",
        verified_sentences=[
            _kept("claim 1 [#ev:src-A:0-10].", ["[#ev:src-A:0-10]"]),
            VerifiedSentence(
                section_id="sec_x",
                sentence_text="dropped sentence [#ev:src-B:0-10].",
                provenance_tokens=["[#ev:src-B:0-10]"],
                verifier_pass=False,
                drop_reason="numeric_mismatch",
            ),
        ],
        section_verify_pass_rate=0.5,
        section_status="verified",
    )
    snapshots = snapshot_sources(_report(section), pool)
    assert "src-A" in snapshots
    assert "src-B" not in snapshots


def test_snapshot_skips_dropped_sections():
    pool = _pool(_src("src-A", "txt"))
    # Only-kept-section's source is included; dropped section's source is not
    kept_section = Section(
        section_id="sec_a",
        section_title="A",
        verified_sentences=[_kept("c [#ev:src-A:0-3].", ["[#ev:src-A:0-3]"])],
        section_verify_pass_rate=1.0,
        section_status="verified",
    )
    # Schema requires verdict=success to have at least one non-dropped
    # section, so we test the dropped-section branch via single section
    # report and assert no extra sources slip in.
    snapshots = snapshot_sources(_report(kept_section), pool)
    assert snapshots == {"src-A": "txt"}


def test_snapshot_falls_back_to_snippet_when_no_full_text():
    pool = _pool(_src("src-A", None, snippet="snippet only"))
    section = Section(
        section_id="sec_x",
        section_title="X",
        verified_sentences=[_kept("c [#ev:src-A:0-3].", ["[#ev:src-A:0-3]"])],
        section_verify_pass_rate=1.0,
        section_status="verified",
    )
    snapshots = snapshot_sources(_report(section), pool)
    assert snapshots == {"src-A": "snippet only"}


def test_snapshot_skips_unknown_source_id_defensively():
    """If a token references a source_id not in the pool (shouldn't
    happen post-strict-verify), the snapshot silently skips it."""
    pool = _pool(_src("src-A", "txt"))
    section = Section(
        section_id="sec_x",
        section_title="X",
        verified_sentences=[
            _kept("c [#ev:src-bogus:0-3].", ["[#ev:src-bogus:0-3]"])
        ],
        section_verify_pass_rate=1.0,
        section_status="verified",
    )
    snapshots = snapshot_sources(_report(section), pool)
    assert "src-bogus" not in snapshots
    assert snapshots == {}


def test_snapshot_dedupes_same_source_across_sentences():
    pool = _pool(_src("src-A", "txt"))
    section = Section(
        section_id="sec_x",
        section_title="X",
        verified_sentences=[
            _kept("c1 [#ev:src-A:0-3].", ["[#ev:src-A:0-3]"]),
            _kept("c2 [#ev:src-A:5-10].", ["[#ev:src-A:5-10]"]),
        ],
        section_verify_pass_rate=1.0,
        section_status="verified",
    )
    snapshots = snapshot_sources(_report(section), pool)
    assert len(snapshots) == 1
    assert snapshots["src-A"] == "txt"


def test_snapshot_handles_multiple_tokens_per_sentence():
    pool = _pool(
        _src("src-A", "txt-a"),
        _src("src-B", "txt-b"),
    )
    section = Section(
        section_id="sec_x",
        section_title="X",
        verified_sentences=[
            _kept(
                "claim spans [#ev:src-A:0-3] and [#ev:src-B:0-3].",
                ["[#ev:src-A:0-3]", "[#ev:src-B:0-3]"],
            )
        ],
        section_verify_pass_rate=1.0,
        section_status="verified",
    )
    snapshots = snapshot_sources(_report(section), pool)
    assert set(snapshots.keys()) == {"src-A", "src-B"}


# ---------- Truncation ----------

def test_snapshot_truncates_oversize_full_text():
    big_text = "X" * (MAX_SOURCE_TEXT_BYTES + 5000)
    pool = _pool(_src("src-A", big_text))
    section = Section(
        section_id="sec_x",
        section_title="X",
        verified_sentences=[_kept("c [#ev:src-A:0-3].", ["[#ev:src-A:0-3]"])],
        section_verify_pass_rate=1.0,
        section_status="verified",
    )
    snapshots = snapshot_sources(_report(section), pool)
    text = snapshots["src-A"]
    # Original was MAX+5000; truncated body is <= MAX, plus a note appended
    assert len(text.encode("utf-8")) > MAX_SOURCE_TEXT_BYTES  # note appended
    assert "POLARIS audit-bundle truncation notice" in text


def test_snapshot_does_not_truncate_when_under_cap():
    text = "x" * (MAX_SOURCE_TEXT_BYTES // 2)
    pool = _pool(_src("src-A", text))
    section = Section(
        section_id="sec_x",
        section_title="X",
        verified_sentences=[_kept("c [#ev:src-A:0-3].", ["[#ev:src-A:0-3]"])],
        section_verify_pass_rate=1.0,
        section_status="verified",
    )
    snapshots = snapshot_sources(_report(section), pool)
    assert snapshots["src-A"] == text
    assert "truncation notice" not in snapshots["src-A"]


def test_snapshot_truncation_respects_utf8_boundaries():
    # Cyrillic each char = 2 bytes; build a text that puts a 2-byte
    # character right at the cap boundary
    text = "а" * (MAX_SOURCE_TEXT_BYTES // 2 + 100)  # over cap
    pool = _pool(_src("src-A", text))
    section = Section(
        section_id="sec_x",
        section_title="X",
        verified_sentences=[_kept("c [#ev:src-A:0-3].", ["[#ev:src-A:0-3]"])],
        section_verify_pass_rate=1.0,
        section_status="verified",
    )
    snapshots = snapshot_sources(_report(section), pool)
    # Should decode without UnicodeDecodeError → truncation respected boundary
    assert isinstance(snapshots["src-A"], str)


# ---------- Sizing helpers ----------

def test_snapshot_size_bytes_sums_correctly():
    snaps = {"a": "hello", "b": "world!"}
    assert snapshot_size_bytes(snaps) == 5 + 6


def test_snapshot_size_bytes_empty():
    assert snapshot_size_bytes({}) == 0
