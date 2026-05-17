"""Tests for src/polaris_graph/audit_ir/slide_deck.py (M-22)."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.polaris_graph.audit_ir.loader import (
    AdequacyGate,
    AuditIR,
    BibliographyEntry,
    ContradictionClaim,
    ContradictionCluster,
    EvaluatorGate,
    EvidenceSpanToken,
    FrameCoverageReport,
    IR_SCHEMA_VERSION,
    ReportSection,
    ReportSentence,
    RunManifest,
    TierMix,
    VerifiedReport,
    load_audit_ir,
)
from src.polaris_graph.audit_ir.slide_deck import (
    Slide,
    SlideBullet,
    SlideCitation,
    SlideDeck,
    SlideDeckEmptyReportError,
    SlideDeckError,
    build_slide_deck,
    deck_to_dict,
    render_deck_html,
)


# ---------------------------------------------------------------------------
# Synthetic IR builder (mirrors run_diff/citation_health pattern)
# ---------------------------------------------------------------------------


def _sentence(
    claim_id: str,
    text: str,
    section: str = "Findings",
    is_verified: bool = True,
    tokens: tuple[EvidenceSpanToken, ...] = (),
) -> ReportSentence:
    if not tokens and is_verified:
        tokens = (EvidenceSpanToken(evidence_id="ev_a", start=0, end=10),)
    return ReportSentence(
        claim_id=claim_id, section=section, text=text, tokens=tokens,
        is_verified=is_verified, failure_reasons=(),
    )


def _bib(num: int, eid: str, statement: str = "ok",
         tier: str = "T1", url: str = "https://x.example") -> BibliographyEntry:
    return BibliographyEntry(
        num=num, evidence_id=eid, statement=statement,
        tier=tier, url=url,
    )


def _make_ir(
    *,
    sections: tuple[tuple[str, list[ReportSentence]], ...] = (
        ("Findings", []),
    ),
    bibliography: tuple[BibliographyEntry, ...] = (),
    contradictions: tuple[ContradictionCluster, ...] = (),
    question: str = "Tirzepatide for type 2 diabetes",
) -> AuditIR:
    sect_objs = []
    n_kept_total = 0
    n_dropped_total = 0
    for title, sentences in sections:
        n_kept = sum(1 for s in sentences if s.is_verified)
        n_dropped = sum(1 for s in sentences if not s.is_verified)
        n_kept_total += n_kept
        n_dropped_total += n_dropped
        sect_objs.append(
            ReportSection(
                title=title, kept_count=n_kept, dropped_count=n_dropped,
                total_in=len(sentences), dropped_due_to_failure=n_dropped,
                sentences=tuple(sentences),
            )
        )
    verified = VerifiedReport(
        sections=tuple(sect_objs),
        sentences_verified=n_kept_total,
        sentences_dropped=n_dropped_total,
        drop_reason_counts={"strict_verify": n_dropped_total} if n_dropped_total else {},
    )
    tier_mix = TierMix(
        fractions={"T1": 0.6, "T2": 0.3, "T3": 0.1},
        corpus_count=len(bibliography),
        approved=True, material_deviation=False,
    )
    eg = EvaluatorGate(
        gate_class="pass", release_allowed=True, reasons=(),
        rule_blockers=(), judge_critical_axes=(), judge_parse_ok=True,
    )
    manifest = RunManifest(
        run_id="run_test_1", slug="x_drug_y", status="success",
        question=question,
        protocol_sha256="0" * 64, cost_usd=0.10, budget_cap_usd=1.00,
        word_count=500, sentences_verified=n_kept_total,
        sentences_dropped=n_dropped_total,
        contradictions_found=len(contradictions),
        completeness_percent=100.0, evaluator_gate=eg,
        release_allowed=True, v30_enabled=True, v30_warnings=(),
        retrieval_stats=None,
    )
    fc = FrameCoverageReport(
        pass_count=0, partial_count=0, frame_gap_count=0,
        pipeline_fault_count=0, total_entities=0, total_slots=0,
        research_question="q", schema_version="1.0",
        semantics_warning=None, entries=(),
    )
    adequacy = AdequacyGate(
        decision="proceed", findings_ok=10, findings_total=10,
        critical_count=0,
    )
    return AuditIR(
        ir_schema_version=IR_SCHEMA_VERSION, run_id="run_test_1",
        artifact_dir=Path("/tmp"), report_md="", manifest=manifest,
        bibliography=bibliography, contradictions=contradictions,
        frame_coverage=fc, tier_mix=tier_mix, verified_report=verified,
        model_provenance=None, protocol=None, adequacy=adequacy,
        corpus_approval=None,
    )


# ---------------------------------------------------------------------------
# Empty / error paths
# ---------------------------------------------------------------------------


def test_empty_report_raises() -> None:
    ir = _make_ir(sections=(("Findings", []),))
    with pytest.raises(SlideDeckEmptyReportError):
        build_slide_deck(ir)


def test_max_bullets_must_be_positive() -> None:
    ir = _make_ir(
        sections=(("Findings", [_sentence("c1", "x")]),),
        bibliography=(_bib(1, "ev_a"),),
    )
    with pytest.raises(SlideDeckError, match="max_bullets"):
        build_slide_deck(ir, max_bullets_per_slide=0)


def test_max_slides_must_meet_minimum() -> None:
    ir = _make_ir(
        sections=(("Findings", [_sentence("c1", "x")]),),
        bibliography=(_bib(1, "ev_a"),),
    )
    with pytest.raises(SlideDeckError, match="max_slides"):
        build_slide_deck(ir, max_slides=2)


# ---------------------------------------------------------------------------
# Slide ordering + structure
# ---------------------------------------------------------------------------


def test_deck_starts_with_title_and_scope() -> None:
    ir = _make_ir(
        sections=(("Findings", [_sentence("c1", "claim a")]),),
        bibliography=(_bib(1, "ev_a"),),
    )
    deck = build_slide_deck(ir)
    assert len(deck.slides) >= 4
    assert deck.slides[0].layout == "title"
    assert deck.slides[0].slide_id == "slide_title"
    assert deck.slides[1].slide_id == "slide_scope"


def test_deck_ends_with_appendix() -> None:
    ir = _make_ir(
        sections=(("Findings", [_sentence("c1", "claim a")]),),
        bibliography=(_bib(1, "ev_a"), _bib(2, "ev_b")),
    )
    deck = build_slide_deck(ir)
    assert deck.slides[-1].slide_id == "slide_appendix"
    assert deck.slides[-1].layout == "appendix"
    # Appendix carries every bibliography entry as a citation.
    assert len(deck.slides[-1].citations) == 2


# ---------------------------------------------------------------------------
# LAW II: every body bullet traces back to claim_id
# ---------------------------------------------------------------------------


def test_every_visible_bullet_carries_claim_id() -> None:
    """LAW II: every body bullet must be back-linkable to a
    verified claim_id; the renderer cannot produce free-form prose."""
    ir = _make_ir(
        sections=(
            ("Efficacy", [
                _sentence("c1", "primary endpoint met"),
                _sentence("c2", "secondary endpoint met"),
            ]),
            ("Safety", [
                _sentence("c3", "no Grade 4 events"),
            ]),
        ),
        bibliography=(_bib(1, "ev_a"),),
    )
    deck = build_slide_deck(ir)
    for slide in deck.slides:
        for bullet in slide.bullets:
            assert bullet.claim_id, (
                f"slide {slide.slide_id} bullet has empty claim_id"
            )


def test_visible_bullet_text_is_verbatim() -> None:
    """LAW II: bullet text is the verified sentence verbatim —
    NOT paraphrased by the builder."""
    text = "Primary endpoint achieved at week 26 (95% CI 1.0-2.0)."
    ir = _make_ir(
        sections=(("Findings", [_sentence("c1", text)]),),
        bibliography=(_bib(1, "ev_a"),),
    )
    deck = build_slide_deck(ir)
    section_slides = [
        s for s in deck.slides
        if s.layout == "content" and s.slide_id.startswith("slide_section_")
    ]
    assert len(section_slides) == 1
    assert any(b.text == text for b in section_slides[0].bullets)


# ---------------------------------------------------------------------------
# Per-section slide budget + overflow
# ---------------------------------------------------------------------------


def test_overflow_sentences_land_in_speaker_notes() -> None:
    """When a section has more sentences than max_bullets, the
    overflow appears in speaker notes — visible bullets are
    capped, NOT silently dropped."""
    sentences = [_sentence(f"c{i}", f"claim {i}") for i in range(10)]
    ir = _make_ir(
        sections=(("Findings", sentences),),
        bibliography=(_bib(1, "ev_a"),),
    )
    deck = build_slide_deck(ir, max_bullets_per_slide=3)
    section = next(
        s for s in deck.slides
        if s.slide_id.startswith("slide_section_")
    )
    assert len(section.bullets) == 3
    # Notes must mention all 7 overflow sentences.
    for i in range(3, 10):
        assert f"claim {i}" in section.notes


def test_dropped_sentences_summarized_in_section_notes() -> None:
    sentences = [
        _sentence("c1", "kept claim", is_verified=True),
        _sentence("c2", "dropped claim", is_verified=False),
        _sentence("c3", "another dropped", is_verified=False),
    ]
    ir = _make_ir(
        sections=(("Findings", sentences),),
        bibliography=(_bib(1, "ev_a"),),
    )
    deck = build_slide_deck(ir)
    section = next(
        s for s in deck.slides
        if s.slide_id.startswith("slide_section_")
    )
    # Notes call out the two dropped sentences.
    assert "2 sentences" in section.notes


def test_sections_with_no_verified_sentences_are_skipped() -> None:
    sentences_kept = [_sentence("c1", "kept", is_verified=True)]
    sentences_dropped = [_sentence("c2", "dropped", is_verified=False)]
    ir = _make_ir(
        sections=(
            ("KeptSection", sentences_kept),
            ("DroppedSection", sentences_dropped),
        ),
        bibliography=(_bib(1, "ev_a"),),
    )
    deck = build_slide_deck(ir)
    section_titles = [
        s.title for s in deck.slides
        if s.slide_id.startswith("slide_section_")
    ]
    assert "KeptSection" in section_titles
    assert "DroppedSection" not in section_titles


# ---------------------------------------------------------------------------
# Citations resolve into bibliography entries
# ---------------------------------------------------------------------------


def test_citations_match_bibliography_entries() -> None:
    """Every SlideCitation in a content slide must back-link to a
    real bibliography entry — no orphan citations."""
    ir = _make_ir(
        sections=(("Findings", [
            _sentence("c1", "x", tokens=(
                EvidenceSpanToken("ev_a", 0, 10),
                EvidenceSpanToken("ev_b", 0, 10),
            )),
        ]),),
        bibliography=(_bib(1, "ev_a"), _bib(2, "ev_b")),
    )
    deck = build_slide_deck(ir)
    bib_ids = {e.evidence_id for e in ir.bibliography}
    for slide in deck.slides:
        for citation in slide.citations:
            assert citation.evidence_id in bib_ids, (
                f"slide {slide.slide_id} cites unknown evidence_id "
                f"{citation.evidence_id!r}"
            )


def test_citations_dedupe_within_slide() -> None:
    """Two bullets citing the same evidence must produce ONE
    citation entry on the slide footer."""
    ir = _make_ir(
        sections=(("Findings", [
            _sentence("c1", "x", tokens=(
                EvidenceSpanToken("ev_a", 0, 10),
            )),
            _sentence("c2", "y", tokens=(
                EvidenceSpanToken("ev_a", 11, 20),
            )),
        ]),),
        bibliography=(_bib(1, "ev_a"),),
    )
    deck = build_slide_deck(ir)
    section = next(
        s for s in deck.slides
        if s.slide_id.startswith("slide_section_")
    )
    eids = [c.evidence_id for c in section.citations]
    assert eids == ["ev_a"]


# ---------------------------------------------------------------------------
# Contradictions + limitations slides
# ---------------------------------------------------------------------------


def _cluster(
    cluster_id: int, subject: str, predicate: str,
    severity: str = "medium",
) -> ContradictionCluster:
    return ContradictionCluster(
        cluster_id=cluster_id, subject=subject, predicate=predicate,
        severity=severity, absolute_difference=0.0,
        relative_difference=0.0, recommended_action="",
        claims=(
            ContradictionClaim(
                evidence_id="ev_a", subject=subject, predicate=predicate,
                arm="", dose="", value=0.0, unit="",
                source_tier="T1", source_url="", context_snippet="",
                endpoint_phrase="",
            ),
        ),
    )


def test_contradictions_slide_appears_when_clusters_present() -> None:
    ir = _make_ir(
        sections=(("Findings", [_sentence("c1", "claim a")]),),
        bibliography=(_bib(1, "ev_a"),),
        contradictions=(
            _cluster(1, "dose", "endpoint"),
            _cluster(2, "duration", "outcome"),
        ),
    )
    deck = build_slide_deck(ir)
    contra_slides = [
        s for s in deck.slides
        if s.slide_id == "slide_contradictions"
    ]
    assert len(contra_slides) == 1


def test_no_contradictions_slide_when_clusters_absent() -> None:
    ir = _make_ir(
        sections=(("Findings", [_sentence("c1", "claim a")]),),
        bibliography=(_bib(1, "ev_a"),),
        contradictions=(),
    )
    deck = build_slide_deck(ir)
    contra_slides = [
        s for s in deck.slides
        if s.slide_id == "slide_contradictions"
    ]
    assert contra_slides == []


def test_limitations_slide_always_appears() -> None:
    ir = _make_ir(
        sections=(("Findings", [_sentence("c1", "claim a")]),),
        bibliography=(_bib(1, "ev_a"),),
    )
    deck = build_slide_deck(ir)
    assert any(
        s.slide_id == "slide_limitations" for s in deck.slides
    )


# ---------------------------------------------------------------------------
# Slide cap (FINAL_PLAN: 12-20 slides)
# ---------------------------------------------------------------------------


def test_slide_count_does_not_exceed_max() -> None:
    """With many sections, the deck must respect max_slides — extra
    sections are NOT rendered to keep the deck within the
    FINAL_PLAN 12-20 slide budget."""
    sections = tuple(
        (f"Section{i}", [_sentence(f"c{i}", f"claim {i}")])
        for i in range(30)
    )
    ir = _make_ir(
        sections=sections,
        bibliography=(_bib(1, "ev_a"),),
    )
    deck = build_slide_deck(ir, max_slides=20)
    assert len(deck.slides) <= 20


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def test_deck_to_dict_round_trips() -> None:
    ir = _make_ir(
        sections=(("Findings", [_sentence("c1", "claim a")]),),
        bibliography=(_bib(1, "ev_a"),),
    )
    deck = build_slide_deck(ir)
    payload = deck_to_dict(deck)
    assert payload["deck_id"].startswith("deck_")
    assert payload["slide_count"] == len(deck.slides)
    assert payload["slides"][0]["slide_id"] == "slide_title"


# ---------------------------------------------------------------------------
# HTML render
# ---------------------------------------------------------------------------


def test_html_render_includes_claim_id_attributes() -> None:
    """LAW II + UI moat: the rendered HTML must include
    data-claim-id attributes on every body bullet so the
    Inspector can wire click handlers back to the audit IR."""
    ir = _make_ir(
        sections=(("Findings", [
            _sentence("c1", "claim with citation"),
        ]),),
        bibliography=(_bib(1, "ev_a", "real source statement"),),
    )
    deck = build_slide_deck(ir)
    html_doc = render_deck_html(deck)
    assert "data-claim-id" in html_doc
    assert "claim with citation" in html_doc


def test_html_render_escapes_html_in_user_content() -> None:
    """Defense in depth: a sentence containing HTML must NOT
    inject raw markup into the rendered deck."""
    malicious = '<script>alert("xss")</script>'
    ir = _make_ir(
        sections=(("Findings", [_sentence("c1", malicious)]),),
        bibliography=(_bib(1, "ev_a"),),
    )
    deck = build_slide_deck(ir)
    html_doc = render_deck_html(deck)
    assert "<script>" not in html_doc
    assert "&lt;script&gt;" in html_doc


def test_html_render_includes_appendix_citations() -> None:
    ir = _make_ir(
        sections=(("Findings", [_sentence("c1", "claim a")]),),
        bibliography=(
            _bib(1, "ev_a", "First source", url="https://first.example"),
            _bib(2, "ev_b", "Second source", url="https://second.example"),
        ),
    )
    deck = build_slide_deck(ir)
    html_doc = render_deck_html(deck)
    assert "First source" in html_doc
    assert "Second source" in html_doc
    assert "https://first.example" in html_doc


# ---------------------------------------------------------------------------
# Real-data smoke test
# ---------------------------------------------------------------------------


def _run14_artifact_dir() -> Path:
    repo_root = Path(__file__).resolve().parents[2]
    return (
        repo_root / "outputs" / "full_scale_v30_phase2_run14"
        / "clinical" / "clinical_tirzepatide_t2dm"
    )


# ---------------------------------------------------------------------------
# Codex M-22 v1 review fixes
# ---------------------------------------------------------------------------


def test_speaker_notes_not_rendered_as_visible_html() -> None:
    """Codex M-22 v1 fix: speaker notes were rendered as visible
    `<aside><pre>...</pre></aside>` content. v2 stores them as a
    `data-notes` attribute on the slide container only — NOT
    visible HTML body content."""
    sentences = [
        _sentence(f"c{i}", f"verified claim {i}") for i in range(8)
    ]
    ir = _make_ir(
        sections=(("Findings", sentences),),
        bibliography=(_bib(1, "ev_a"),),
    )
    deck = build_slide_deck(ir, max_bullets_per_slide=3)
    html_doc = render_deck_html(deck)

    # No <aside> element rendering visible speaker notes.
    assert "<aside" not in html_doc
    assert "Speaker notes</h2>" not in html_doc
    # And no <pre> blocks either (the v1 visible notes wrapper).
    assert "<pre>" not in html_doc and "<pre " not in html_doc
    # But the notes ARE serialized as data-notes for PPTX export.
    assert "data-notes=" in html_doc

    # The visible body bullets (3 verified claims) appear in <li>
    # tags. The OVERFLOW sentences (4-7) appear ONLY inside the
    # data-notes attribute, never inside a <li> or other body element.
    import re
    body_bullet_re = re.compile(r"<li [^>]*>([^<]*)</li>", re.DOTALL)
    body_bullet_texts = body_bullet_re.findall(html_doc)
    body_text = " ".join(body_bullet_texts)
    for i in range(3, 8):
        assert f"verified claim {i}" not in body_text, (
            f"overflow sentence 'verified claim {i}' appeared in a "
            f"<li> body bullet — must only be in data-notes"
        )


def test_synthetic_bullets_carry_disclosure_attribute() -> None:
    """Codex M-22 v1: scope/contradictions/limitations bullets are
    deterministic metadata projections, not verified-sentence
    prose. v2 marks them is_synthetic=True so the renderer can
    add a `data-synthetic="true"` attribute (and a [meta] badge)
    so customers cannot mistake them for verified findings."""
    ir = _make_ir(
        sections=(("Findings", [_sentence("c1", "verified claim a")]),),
        bibliography=(_bib(1, "ev_a"),),
        contradictions=(_cluster(1, "dose", "endpoint"),),
    )
    deck = build_slide_deck(ir)
    # Scope, contradictions, limitations bullets must be synthetic.
    for slide in deck.slides:
        if slide.slide_id in (
            "slide_scope", "slide_contradictions", "slide_limitations",
        ):
            for b in slide.bullets:
                assert b.is_synthetic is True, (
                    f"meta-slide {slide.slide_id} bullet "
                    f"{b.text!r} must be marked is_synthetic"
                )
        elif slide.slide_id.startswith("slide_section_"):
            for b in slide.bullets:
                assert b.is_synthetic is False, (
                    f"section bullet {b.text!r} must NOT be "
                    f"marked is_synthetic — it's verified prose"
                )

    html_doc = render_deck_html(deck)
    # Synthetic disclosure markup is present.
    assert 'data-synthetic="true"' in html_doc
    assert "[meta]" in html_doc


def test_javascript_url_is_not_rendered_as_link() -> None:
    """Codex M-22 v1 fix: source URLs were html-escaped but not
    scheme-checked, so a javascript: URL survived into href and
    would execute in a browser. v2 restricts hrefs to
    http/https/mailto."""
    ir = _make_ir(
        sections=(("Findings", [_sentence("c1", "x")]),),
        bibliography=(
            _bib(1, "ev_a", url="javascript:alert(1)"),
            _bib(2, "ev_b", url="https://safe.example/paper"),
        ),
    )
    deck = build_slide_deck(ir)
    html_doc = render_deck_html(deck)
    # The unsafe scheme MUST NOT appear in an href attribute.
    assert 'href="javascript:' not in html_doc
    assert "javascript:alert" not in html_doc or (
        "(unsafe scheme; link disabled)" in html_doc
    )
    # The safe URL still becomes a link.
    assert 'href="https://safe.example/paper"' in html_doc


def test_data_url_is_not_rendered_as_link() -> None:
    ir = _make_ir(
        sections=(("Findings", [_sentence("c1", "x")]),),
        bibliography=(
            _bib(1, "ev_a", url="data:text/html,<script>alert(1)</script>"),
        ),
    )
    deck = build_slide_deck(ir)
    html_doc = render_deck_html(deck)
    assert 'href="data:' not in html_doc


def test_unresolved_evidence_id_dropped_from_inline_markers() -> None:
    """Codex M-22 v1 fix: a verified sentence cited an evidence_id
    that wasn't in the bibliography (e.g. a stale link). The
    inline marker showed `[ev_missing]` next to the bullet but the
    citations footer silently omitted it — visible/footer drift.
    v2 filters out unresolved evidence_ids from the inline
    markers."""
    ir = _make_ir(
        sections=(("Findings", [
            _sentence("c1", "claim a", tokens=(
                EvidenceSpanToken("ev_real", 0, 10),
                EvidenceSpanToken("ev_missing", 0, 10),
            )),
        ]),),
        bibliography=(_bib(1, "ev_real", "Real source"),),
    )
    deck = build_slide_deck(ir)
    html_doc = render_deck_html(deck)
    # ev_real renders inline; ev_missing must be filtered out.
    assert "[ev_real]" in html_doc
    assert "[ev_missing]" not in html_doc


def test_appendix_budget_reservation_with_no_contradictions() -> None:
    """Codex M-22 v1 fix: the section-budget reservation always
    subtracted 3 (contradictions + limitations + appendix), so a
    deck with no contradictions underfilled by 1 slide. v2
    reserves 2 when no contradictions, 3 otherwise."""
    sections = tuple(
        (f"Section{i}", [_sentence(f"c{i}", f"claim {i}")])
        for i in range(25)
    )
    ir = _make_ir(
        sections=sections,
        bibliography=(_bib(1, "ev_a"),),
        # No contradictions on this run.
    )
    deck = build_slide_deck(ir, max_slides=20)
    # Should hit exactly 20 (1 title + 1 scope + 17 sections + 1
    # limitations + 1 appendix = 20). Without the fix it'd be 19.
    assert len(deck.slides) == 20


def test_real_run14_builds_a_deck() -> None:
    """Real V30 run loads + builds a deck without errors. Sanity
    check that the synthetic-fixture coverage doesn't drift from
    production-shape data."""
    artifact_dir = _run14_artifact_dir()
    if not (artifact_dir / "manifest.json").exists():
        pytest.skip("run-14 artifacts not available")
    ir = load_audit_ir(artifact_dir)
    if ir.verified_report.sentences_verified == 0:
        pytest.skip("run-14 has no verified sentences")
    deck = build_slide_deck(ir)
    assert isinstance(deck, SlideDeck)
    assert len(deck.slides) >= 4
    assert deck.run_slug == ir.manifest.slug
    # Real deck: HTML render produces a valid-looking string.
    html_doc = render_deck_html(deck)
    assert html_doc.startswith("<!DOCTYPE html>")
    assert "</html>" in html_doc
