"""Cited slide deck export (M-22 — Phase C).

Per FINAL_PLAN Phase C deliverable #5:
  Citation-bound slide deck (12-20 eng days):
    - 12-20 slides from verified report + structured data
    - Slide-level citations OR linked appendix slide for every
      substantive slide
    - Contradictions and limitations survive in main slide or
      speaker notes
    - Export PPTX + HTML/PDF without breaking references

Scope of v1:
  - Pure deterministic slide-content builder over a loaded
    `AuditIR`. NO LLM in the loop, NO fabrication. Every slide
    body line must back-link to a claim_id; every citation must
    resolve to a bibliography entry.
  - HTML rendering surface (lightweight). PPTX/PDF export hooks
    are a v2 (or operator-side: HTML → wkhtmltopdf is sufficient
    for pilot use).
  - Speaker notes carry the dropped-sentence + contradiction
    + limitations context so the deck is accurate even when
    visible content is condensed.

Out of scope for v1:
  - PPTX export. Customers asking for PPTX in v1 can run the
    HTML through PowerPoint's Save-as-pptx or a wkhtmltopptx
    pipeline; M-22 v2 ships a native python-pptx export with
    the same citation structure.
  - Charts. Charting requires structured-data extraction the
    audit IR doesn't surface in v1; deferred.

LAW II compliance: every slide body line must trace back to a
verified claim_id; the renderer does NOT produce free-form prose.
LAW VII compliance: stdlib + audit_ir/loader only.
"""

from __future__ import annotations

import html
from dataclasses import dataclass, field
from typing import Any

from src.polaris_graph.audit_ir.loader import (
    AuditIR,
    BibliographyEntry,
    ContradictionCluster,
    ReportSection,
    ReportSentence,
)


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SlideBullet:
    """One bullet on a slide, bound to a claim_id.

    `evidence_ids` carries the bibliography handles cited by the
    underlying verified sentence; the renderer can show them as
    `[1] [2]` style markers next to the bullet.

    `text` is the sentence text — NEVER paraphrased by the
    builder. v1 uses the verified text verbatim; future v2 may
    add a strict "shorten to N chars" pass that preserves
    citations.
    """

    text: str
    claim_id: str
    section: str
    evidence_ids: tuple[str, ...]


@dataclass(frozen=True)
class SlideCitation:
    """Metadata for one bibliography reference cited on a slide."""

    bib_num: int
    evidence_id: str
    statement: str
    tier: str
    url: str


@dataclass(frozen=True)
class Slide:
    """One slide in the deck.

    `bullets` are the visible body lines (audit-grounded).
    `notes` is speaker-notes prose; carries contradictions /
    limitations / dropped sentences that wouldn't fit on a
    visible slide but matter for accuracy.
    `citations` are the bibliography entries any bullet on this
    slide cited; rendered as a footer or appendix link.
    """

    slide_id: str
    title: str
    bullets: tuple[SlideBullet, ...]
    citations: tuple[SlideCitation, ...]
    notes: str
    layout: str  # "title" | "section_header" | "content" | "appendix"


@dataclass(frozen=True)
class SlideDeck:
    """The full deck — title slide first, then per-section content
    slides, then a contradictions slide, then an appendix."""

    deck_id: str
    run_slug: str
    run_id: str
    title: str
    slides: tuple[Slide, ...] = field(default_factory=tuple)


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class SlideDeckError(Exception):
    """Base error for slide-deck operations."""


class SlideDeckEmptyReportError(SlideDeckError):
    """The audit run has no verified sentences; no deck can be built."""


# ---------------------------------------------------------------------------
# Builder
# ---------------------------------------------------------------------------


# Per FINAL_PLAN: 12-20 slides total. Concretely:
#   1 title + 1 method/scope + N section + 1 contradictions
#   + 1 limitations + 1 appendix, where N = sections with at
#   least one verified sentence.
_DEFAULT_MAX_BULLETS_PER_SLIDE = 5
_DEFAULT_MAX_SLIDES = 20
_DEFAULT_MIN_SLIDES = 4  # title + scope + at least one content + appendix


def build_slide_deck(
    ir: AuditIR,
    *,
    max_bullets_per_slide: int = _DEFAULT_MAX_BULLETS_PER_SLIDE,
    max_slides: int = _DEFAULT_MAX_SLIDES,
) -> SlideDeck:
    """Build a deterministic deck from the loaded audit IR.

    Slide order:
      1. Title slide
      2. Scope + method slide
      3. One slide per verified section (capped at max_bullets
         visible bullets; remaining sentences land in speaker
         notes)
      4. Contradictions slide (if any)
      5. Limitations slide (drop reasons + tier mix)
      6. Appendix: bibliography
    """
    if max_bullets_per_slide < 1:
        raise SlideDeckError(
            f"max_bullets_per_slide must be >= 1; got {max_bullets_per_slide}"
        )
    if max_slides < _DEFAULT_MIN_SLIDES:
        raise SlideDeckError(
            f"max_slides must be >= {_DEFAULT_MIN_SLIDES}; got {max_slides}"
        )
    if ir.verified_report.sentences_verified == 0:
        raise SlideDeckEmptyReportError(
            "the audit run has no verified sentences; no deck can be built"
        )

    bib_index = {entry.evidence_id: entry for entry in ir.bibliography}

    slides: list[Slide] = []

    # Slide 1 — title
    slides.append(_build_title_slide(ir))
    # Slide 2 — scope + method
    slides.append(_build_scope_slide(ir))

    # Per-section content slides.
    section_slides_budget = max(
        0,
        max_slides - len(slides) - 3,  # contradictions + limitations + appendix
    )
    section_slides = _build_section_slides(
        ir, bib_index,
        max_bullets=max_bullets_per_slide,
        max_section_slides=section_slides_budget,
    )
    slides.extend(section_slides)

    # Contradictions, if any.
    if ir.contradictions:
        slides.append(_build_contradictions_slide(ir, bib_index))

    # Limitations.
    slides.append(_build_limitations_slide(ir))

    # Appendix bibliography.
    slides.append(_build_appendix_slide(ir))

    return SlideDeck(
        deck_id=f"deck_{ir.manifest.run_id}",
        run_slug=ir.manifest.slug,
        run_id=ir.manifest.run_id,
        title=ir.manifest.question or ir.manifest.slug,
        slides=tuple(slides),
    )


# ---------------------------------------------------------------------------
# Slide builders
# ---------------------------------------------------------------------------


def _build_title_slide(ir: AuditIR) -> Slide:
    notes = (
        f"Run ID: {ir.manifest.run_id}\n"
        f"Slug: {ir.manifest.slug}\n"
        f"Cost: ${ir.manifest.cost_usd:.4f} of "
        f"${ir.manifest.budget_cap_usd:.2f} cap\n"
        f"Word count: {ir.manifest.word_count}"
    )
    return Slide(
        slide_id="slide_title",
        title=(ir.manifest.question or ir.manifest.slug)[:120],
        bullets=(),
        citations=(),
        notes=notes,
        layout="title",
    )


def _build_scope_slide(ir: AuditIR) -> Slide:
    bullets: list[SlideBullet] = []
    if ir.adequacy is not None:
        bullets.append(
            SlideBullet(
                text=(
                    f"Corpus adequacy: {ir.adequacy.decision}; "
                    f"{ir.adequacy.findings_ok} of "
                    f"{ir.adequacy.findings_total} findings met."
                ),
                claim_id="scope:adequacy",
                section="Scope",
                evidence_ids=(),
            )
        )
    bullets.append(
        SlideBullet(
            text=(
                f"Verified sentences: "
                f"{ir.verified_report.sentences_verified} of "
                f"{ir.verified_report.sentences_verified + ir.verified_report.sentences_dropped}"
            ),
            claim_id="scope:verified_count",
            section="Scope",
            evidence_ids=(),
        )
    )
    bullets.append(
        SlideBullet(
            text=(
                f"Sources cited: {len(ir.bibliography)} unique "
                f"evidence IDs across "
                f"{len(set(e.tier for e in ir.bibliography))} tiers"
            ),
            claim_id="scope:source_count",
            section="Scope",
            evidence_ids=(),
        )
    )
    notes = (
        "This deck contains only verified sentences from the "
        "audit pipeline. Every body bullet on a content slide "
        "carries a back-link to its source evidence ID; see the "
        "appendix for the full bibliography."
    )
    return Slide(
        slide_id="slide_scope",
        title="Scope and Method",
        bullets=tuple(bullets),
        citations=(),
        notes=notes,
        layout="content",
    )


def _build_section_slides(
    ir: AuditIR,
    bib_index: dict[str, BibliographyEntry],
    *,
    max_bullets: int,
    max_section_slides: int,
) -> list[Slide]:
    """Per-section content slides. Each section with verified
    sentences becomes ONE slide; bullets > max_bullets land in
    speaker notes. Sections are ordered by their position in the
    verified report (preserves the runner's section ordering)."""
    slides: list[Slide] = []
    for section in ir.verified_report.sections:
        if max_section_slides <= 0:
            break
        verified_sentences = [
            s for s in section.sentences if s.is_verified
        ]
        if not verified_sentences:
            continue
        visible = verified_sentences[:max_bullets]
        overflow = verified_sentences[max_bullets:]

        bullets = tuple(
            _bullet_from_sentence(s, section.title) for s in visible
        )
        # Citations: union of bibliography entries cited by visible
        # bullets, in catalog order.
        citation_eids: list[str] = []
        seen_eids: set[str] = set()
        for s in visible:
            for tok in s.tokens:
                if tok.evidence_id in seen_eids:
                    continue
                seen_eids.add(tok.evidence_id)
                citation_eids.append(tok.evidence_id)
        citations = tuple(
            _citation_from_evidence_id(eid, bib_index)
            for eid in citation_eids
            if eid in bib_index
        )

        notes_lines = []
        if overflow:
            notes_lines.append(
                f"Additional verified sentences in this section "
                f"({len(overflow)}):"
            )
            for s in overflow:
                notes_lines.append(f"  • {s.text}")
        if section.dropped_count:
            notes_lines.append(
                f"\n{section.dropped_count} sentences in this "
                f"section dropped during strict-verify; see "
                f"appendix for drop-reason summary."
            )
        notes = "\n".join(notes_lines)

        slides.append(
            Slide(
                slide_id=f"slide_section_{len(slides):03d}",
                title=section.title or "Findings",
                bullets=bullets,
                citations=citations,
                notes=notes,
                layout="content",
            )
        )
        max_section_slides -= 1
    return slides


def _build_contradictions_slide(
    ir: AuditIR,
    bib_index: dict[str, BibliographyEntry],
) -> Slide:
    bullets: list[SlideBullet] = []
    citation_eids: list[str] = []
    seen: set[str] = set()
    notes_overflow: list[str] = []

    for i, cluster in enumerate(ir.contradictions):
        line = (
            f"{cluster.subject} / {cluster.predicate} — "
            f"{cluster.severity} severity"
        )
        if i < 5:
            bullets.append(
                SlideBullet(
                    text=line,
                    claim_id=f"contradiction:{cluster.cluster_id}",
                    section="Contradictions",
                    evidence_ids=tuple(
                        c.evidence_id for c in cluster.claims
                    ),
                )
            )
        else:
            notes_overflow.append(line)
        for c in cluster.claims:
            if c.evidence_id and c.evidence_id not in seen:
                seen.add(c.evidence_id)
                citation_eids.append(c.evidence_id)

    citations = tuple(
        _citation_from_evidence_id(eid, bib_index)
        for eid in citation_eids
        if eid in bib_index
    )
    notes_lines: list[str] = []
    if notes_overflow:
        notes_lines.append(
            f"Additional contradictions ({len(notes_overflow)}):"
        )
        notes_lines.extend(f"  • {l}" for l in notes_overflow)
    notes_lines.append(
        "\nEach disagreement is grounded in two or more cited "
        "sources; see the appendix for source URLs."
    )
    return Slide(
        slide_id="slide_contradictions",
        title="Disagreements Across Sources",
        bullets=tuple(bullets),
        citations=citations,
        notes="\n".join(notes_lines),
        layout="content",
    )


def _build_limitations_slide(ir: AuditIR) -> Slide:
    drop_summary_lines = [
        f"{reason}: {count}"
        for reason, count in sorted(
            ir.verified_report.drop_reason_counts.items(),
            key=lambda x: -x[1],
        )
    ]
    bullets: list[SlideBullet] = []
    if ir.verified_report.sentences_dropped:
        bullets.append(
            SlideBullet(
                text=(
                    f"{ir.verified_report.sentences_dropped} sentences "
                    f"dropped during strict-verify; only verified "
                    f"prose appears on prior slides"
                ),
                claim_id="limitations:dropped_total",
                section="Limitations",
                evidence_ids=(),
            )
        )
    if ir.tier_mix.fractions:
        tier_summary = ", ".join(
            f"{k}={v*100:.0f}%"
            for k, v in sorted(
                ir.tier_mix.fractions.items(), key=lambda x: x[0],
            )
        )
        bullets.append(
            SlideBullet(
                text=f"Source tier mix: {tier_summary}",
                claim_id="limitations:tier_mix",
                section="Limitations",
                evidence_ids=(),
            )
        )
    if ir.adequacy is not None and ir.adequacy.critical_count:
        bullets.append(
            SlideBullet(
                text=(
                    f"{ir.adequacy.critical_count} critical adequacy "
                    f"warnings flagged at corpus stage"
                ),
                claim_id="limitations:adequacy_critical",
                section="Limitations",
                evidence_ids=(),
            )
        )
    notes_lines = []
    if drop_summary_lines:
        notes_lines.append("Per-reason drop counts:")
        notes_lines.extend(f"  • {l}" for l in drop_summary_lines)
    return Slide(
        slide_id="slide_limitations",
        title="Limitations",
        bullets=tuple(bullets),
        citations=(),
        notes="\n".join(notes_lines),
        layout="content",
    )


def _build_appendix_slide(ir: AuditIR) -> Slide:
    bullets: list[SlideBullet] = []
    citations: list[SlideCitation] = []
    for entry in ir.bibliography:
        citations.append(
            SlideCitation(
                bib_num=entry.num, evidence_id=entry.evidence_id,
                statement=entry.statement, tier=entry.tier,
                url=entry.url,
            )
        )
    notes = (
        f"Full bibliography ({len(ir.bibliography)} entries). "
        "Every claim on the body slides back-links to one or more "
        "of these source IDs; verify by clicking through to the "
        "source URL."
    )
    return Slide(
        slide_id="slide_appendix",
        title="Bibliography",
        bullets=tuple(bullets),
        citations=tuple(citations),
        notes=notes,
        layout="appendix",
    )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _bullet_from_sentence(
    sentence: ReportSentence, section_title: str,
) -> SlideBullet:
    return SlideBullet(
        text=sentence.text,
        claim_id=sentence.claim_id,
        section=section_title,
        evidence_ids=tuple(t.evidence_id for t in sentence.tokens),
    )


def _citation_from_evidence_id(
    evidence_id: str,
    bib_index: dict[str, BibliographyEntry],
) -> SlideCitation:
    entry = bib_index[evidence_id]
    return SlideCitation(
        bib_num=entry.num, evidence_id=entry.evidence_id,
        statement=entry.statement, tier=entry.tier, url=entry.url,
    )


# ---------------------------------------------------------------------------
# Serialization
# ---------------------------------------------------------------------------


def slide_bullet_to_dict(b: SlideBullet) -> dict[str, Any]:
    return {
        "text": b.text, "claim_id": b.claim_id,
        "section": b.section,
        "evidence_ids": list(b.evidence_ids),
    }


def slide_citation_to_dict(c: SlideCitation) -> dict[str, Any]:
    return {
        "bib_num": c.bib_num, "evidence_id": c.evidence_id,
        "statement": c.statement, "tier": c.tier, "url": c.url,
    }


def slide_to_dict(s: Slide) -> dict[str, Any]:
    return {
        "slide_id": s.slide_id,
        "title": s.title,
        "layout": s.layout,
        "bullets": [slide_bullet_to_dict(b) for b in s.bullets],
        "citations": [slide_citation_to_dict(c) for c in s.citations],
        "notes": s.notes,
    }


def deck_to_dict(deck: SlideDeck) -> dict[str, Any]:
    return {
        "deck_id": deck.deck_id,
        "run_slug": deck.run_slug,
        "run_id": deck.run_id,
        "title": deck.title,
        "slide_count": len(deck.slides),
        "slides": [slide_to_dict(s) for s in deck.slides],
    }


# ---------------------------------------------------------------------------
# HTML render
# ---------------------------------------------------------------------------


def render_deck_html(deck: SlideDeck) -> str:
    """Render the deck to a self-contained HTML page.

    LAW II: every body line carries its claim_id as a data
    attribute so a customer can click any bullet and verify the
    back-link to the audit IR. Citations are rendered with
    visible bib_num markers and a footer link to the appendix.
    """
    parts: list[str] = []
    parts.append("<!DOCTYPE html>")
    parts.append('<html lang="en"><head>')
    parts.append('<meta charset="utf-8">')
    parts.append(f"<title>{html.escape(deck.title)}</title>")
    parts.append("<style>")
    parts.append(_DECK_CSS)
    parts.append("</style></head><body>")
    parts.append('<div class="deck">')
    for slide in deck.slides:
        parts.append(_render_slide_html(slide))
    parts.append("</div></body></html>")
    return "\n".join(parts)


def _render_slide_html(slide: Slide) -> str:
    parts = []
    parts.append(
        f'<section class="slide layout-{html.escape(slide.layout)}" '
        f'data-slide-id="{html.escape(slide.slide_id)}">'
    )
    parts.append(f"<h1>{html.escape(slide.title)}</h1>")
    if slide.bullets:
        parts.append("<ul>")
        for b in slide.bullets:
            citations_inline = ""
            if b.evidence_ids:
                citations_inline = (
                    " "
                    + " ".join(
                        f'<sup class="cite">[{html.escape(eid)}]</sup>'
                        for eid in b.evidence_ids
                    )
                )
            parts.append(
                f'<li data-claim-id="{html.escape(b.claim_id)}">'
                f"{html.escape(b.text)}{citations_inline}"
                f"</li>"
            )
        parts.append("</ul>")
    if slide.citations:
        parts.append('<div class="citations">')
        parts.append("<h2>Sources cited</h2>")
        parts.append("<ol>")
        for c in slide.citations:
            url_html = (
                f'<a href="{html.escape(c.url)}">{html.escape(c.url)}</a>'
                if c.url else "no url"
            )
            parts.append(
                f'<li data-evidence-id="{html.escape(c.evidence_id)}">'
                f"<strong>[{c.bib_num}]</strong> "
                f"{html.escape(c.statement)} "
                f'<span class="tier">({html.escape(c.tier)})</span> '
                f"{url_html}"
                f"</li>"
            )
        parts.append("</ol></div>")
    if slide.notes:
        parts.append('<aside class="notes">')
        parts.append("<h2>Speaker notes</h2>")
        parts.append(f"<pre>{html.escape(slide.notes)}</pre>")
        parts.append("</aside>")
    parts.append("</section>")
    return "\n".join(parts)


_DECK_CSS = """
body {
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
        Roboto, sans-serif;
    margin: 0;
    color: #1a1a1a;
    background: #f5f5f5;
}
.deck { max-width: 960px; margin: 0 auto; padding: 24px; }
.slide {
    background: white;
    margin: 24px 0;
    padding: 32px 40px;
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(0,0,0,0.06);
    page-break-after: always;
}
.slide h1 {
    font-size: 28px;
    margin: 0 0 24px 0;
    border-bottom: 2px solid #1a1a1a;
    padding-bottom: 8px;
}
.slide ul { font-size: 18px; line-height: 1.6; padding-left: 24px; }
.slide li { margin-bottom: 12px; }
.cite {
    color: #555;
    font-weight: 500;
    font-size: 11px;
    margin-left: 4px;
}
.citations {
    margin-top: 32px;
    padding-top: 16px;
    border-top: 1px solid #ddd;
    font-size: 13px;
}
.citations h2 { font-size: 14px; margin: 0 0 12px 0; color: #555; }
.citations ol { padding-left: 24px; }
.citations li { margin-bottom: 8px; }
.tier { color: #888; font-size: 11px; }
.notes {
    margin-top: 24px;
    padding: 16px;
    background: #f9f9f9;
    border-left: 3px solid #aaa;
    font-size: 13px;
}
.notes h2 { font-size: 13px; margin: 0 0 8px 0; }
.notes pre { white-space: pre-wrap; margin: 0; font-family: inherit; }
.layout-title h1 { font-size: 36px; border-bottom: none; }
.layout-appendix { font-size: 13px; }
"""
