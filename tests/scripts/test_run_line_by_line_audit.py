"""Tests for I-bakeoff-A-001 — line-by-line audit harness."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from scripts.run_line_by_line_audit import (  # noqa: E402
    audit_sentence,
    run_line_by_line_audit,
)


def _pool(direct_quote: str, ev_id: str = "ev_x") -> dict:
    return {ev_id: {"evidence_id": ev_id, "direct_quote": direct_quote}}


def test_unsupported_when_no_token():
    s = "Tirzepatide reduced HbA1c by 1.5%."
    r = audit_sentence(s, _pool("ignored"))
    assert r["verdict"] == "UNSUPPORTED"
    assert r["reason"] == "no_provenance_token"


def test_unreachable_on_unknown_source():
    s = "Tirzepatide reduced HbA1c by 1.5% [#ev:nonexistent:0-50]."
    r = audit_sentence(s, _pool("ignored"))
    assert r["verdict"] == "UNREACHABLE"
    assert "unknown_evidence_id" in r["reason"]


def test_unreachable_on_span_out_of_range():
    span_text = "short"
    pool = _pool(span_text, "ev_x")
    s = f"Claim [#ev:ev_x:0-9999]."
    r = audit_sentence(s, pool)
    assert r["verdict"] == "UNREACHABLE"
    assert "span_out_of_range" in r["reason"]


def test_verified_when_decimals_match_and_overlap_ok():
    span_text = "Tirzepatide reduced HbA1c by 1.5% in adult patients with T2DM."
    pool = _pool(span_text, "ev_a")
    s = f"Tirzepatide reduced HbA1c by 1.5% in adult patients [#ev:ev_a:0-{len(span_text)}]."
    r = audit_sentence(s, pool)
    assert r["verdict"] == "VERIFIED"
    assert r["decimals_match"] is True


def test_fabricated_when_numeric_mismatch_and_low_overlap():
    span_text = "GLP-1 RAs commonly studied in T2DM."
    pool = _pool(span_text, "ev_b")
    # Sentence asserts a number not in span, with minimal lexical overlap
    s = f"Tirzepatide cut weight by 22.5% in obese adults [#ev:ev_b:0-{len(span_text)}]."
    r = audit_sentence(s, pool)
    assert r["verdict"] == "FABRICATED"
    assert "numeric_mismatch_AND_low_overlap" in r["reason"]


def test_partial_when_numeric_match_but_low_overlap():
    """Span contains only the matching decimal; sentence has the
    same decimal but additional content words not in the span.
    decimals_match=True, overlap=0 (span has no content words) → PARTIAL.
    """
    span_text = "1.5"  # just the number; no content words in span
    pool = _pool(span_text, "ev_c")
    # Sentence uses ONLY the matching decimal "1.5", no other numbers
    s = f"Tirzepatide reduction was 1.5 percent in patients [#ev:ev_c:0-{len(span_text)}]."
    r = audit_sentence(s, pool)
    assert r["verdict"] == "PARTIAL", f"expected PARTIAL, got {r}"
    assert "low_content_overlap" in r["reason"]


def test_partial_when_overlap_ok_but_numeric_mismatch():
    span_text = "Tirzepatide reduced HbA1c in adult patients with T2DM."
    pool = _pool(span_text, "ev_d")
    # Sentence adds a decimal not in span
    s = f"Tirzepatide reduced HbA1c by 1.5% in adult patients [#ev:ev_d:0-{len(span_text)}]."
    r = audit_sentence(s, pool)
    assert r["verdict"] == "PARTIAL"
    assert "numeric_mismatch" in r["reason"]


def test_run_audit_aggregates_summary():
    span_a = "Drug A reduced X by 1.5%."
    span_b = "Drug B reduced Y by 2.3%."
    pool = {
        "a": {"evidence_id": "a", "direct_quote": span_a},
        "b": {"evidence_id": "b", "direct_quote": span_b},
    }
    report = (
        f"Drug A reduced X by 1.5% [#ev:a:0-{len(span_a)}]. "
        f"Drug B reduced Y by 2.3% [#ev:b:0-{len(span_b)}]. "
        "Drug C cured everything."  # no token → UNSUPPORTED
    )
    result = run_line_by_line_audit(report, pool)
    s = result["summary"]
    assert s["total_sentences"] == 3
    assert s["verdict_counts"]["VERIFIED"] == 2
    assert s["verdict_counts"]["UNSUPPORTED"] == 1
    assert s["verified_rate"] == pytest.approx(2 / 3, abs=0.01)
    assert s["alert"] is False  # no FABRICATED, no UNREACHABLE


def test_alert_fires_on_fabricated():
    span = "Drug A studied"
    pool = _pool(span, "a")
    report = f"Drug X cured 99.9% of patients [#ev:a:0-{len(span)}]."
    result = run_line_by_line_audit(report, pool)
    assert result["summary"]["verdict_counts"]["FABRICATED"] == 1
    assert result["summary"]["alert"] is True


def test_alert_fires_on_unreachable():
    pool = {}
    report = "Drug X did the thing [#ev:missing:0-5]."
    result = run_line_by_line_audit(report, pool)
    assert result["summary"]["verdict_counts"]["UNREACHABLE"] == 1
    assert result["summary"]["alert"] is True


def test_audit_md_render_includes_per_claim_table():
    """The {model}/audit.md format contains per-claim verdict rows
    + summary + recommendation per acceptance criterion.
    """
    from scripts.run_line_by_line_audit import _render_audit_md

    span = "Drug A reduced X by 1.5%."
    pool = _pool(span, "a")
    report = f"Drug A reduced X by 1.5% [#ev:a:0-{len(span)}]."
    result = run_line_by_line_audit(report, pool)
    md = _render_audit_md(result)
    assert "# Line-by-line audit" in md
    assert "## Summary" in md
    assert "## Per-claim verdicts" in md
    assert "## Recommendation" in md
    assert "VERIFIED" in md


def test_audit_md_recommends_reject_on_fabricated():
    from scripts.run_line_by_line_audit import _render_audit_md

    span = "Drug A studied"
    pool = _pool(span, "a")
    report = f"Drug X cured 99.9% of patients [#ev:a:0-{len(span)}]."
    result = run_line_by_line_audit(report, pool)
    md = _render_audit_md(result)
    assert "REJECT" in md.upper()


def test_audit_md_recommends_accept_on_high_verified():
    from scripts.run_line_by_line_audit import _render_audit_md

    span = "Drug A reduced X by 1.5%"
    pool = _pool(span, "a")
    # 4 VERIFIED sentences → 100%
    report = "\n".join(
        f"Drug A reduced X by 1.5% [#ev:a:0-{len(span)}]." for _ in range(4)
    )
    result = run_line_by_line_audit(report, pool)
    md = _render_audit_md(result)
    assert "ACCEPT" in md.upper()


def test_canonical_evidencepool_source_id_schema():
    """I-bakeoff-A-001 iter-1 diff P1 fix: pool loader normalizes
    canonical retrieval2.EvidencePool schema (source_id + full_text)
    in addition to legacy {evidence_id + direct_quote}.
    """
    from scripts.run_line_by_line_audit import _normalize_pool

    canonical = {
        "sources": [
            {
                "source_id": "src-1",
                "full_text": "Drug A reduced X by 1.5%",
                "snippet": "fallback snippet",
            },
        ],
    }
    normalized = _normalize_pool(canonical)
    assert "src-1" in normalized
    assert normalized["src-1"]["direct_quote"] == "Drug A reduced X by 1.5%"

    # An audit on canonical-format pool should NOT produce UNREACHABLE
    span = "Drug A reduced X by 1.5%"
    sentence = f"Drug A reduced X by 1.5% [#ev:src-1:0-{len(span)}]."
    r = audit_sentence(sentence, normalized)
    assert r["verdict"] == "VERIFIED", (
        f"canonical schema not normalized correctly; got {r}"
    )


def test_canonical_verified_sentence_field_normalization():
    """I-bakeoff-A-001 iter-1 diff P1 fix: sentence loader accepts
    canonical VerifiedSentence schema (sentence_text field) in
    addition to {sentence: ...}.
    """
    from scripts.run_line_by_line_audit import _normalize_sentence

    assert _normalize_sentence({"sentence": "S1"}) == "S1"
    assert _normalize_sentence({"sentence_text": "S2"}) == "S2"
    assert _normalize_sentence("S3 raw") == "S3 raw"
    assert _normalize_sentence({}) == ""
    assert _normalize_sentence({"unrelated": "x"}) == ""


def test_audit_md_includes_cited_span_quote():
    """I-bakeoff-A-001 iter-1 diff P2 fix: per CLAUDE.md §-1.1 the audit
    table includes the cited span quote that supports each verdict.
    """
    from scripts.run_line_by_line_audit import _render_audit_md

    span = "Drug A reduced X by 1.5%"
    pool = _pool(span, "a")
    report = f"Drug A reduced X by 1.5% [#ev:a:0-{len(span)}]."
    result = run_line_by_line_audit(report, pool)
    md = _render_audit_md(result)
    # The cited span must appear in the rendered markdown
    assert "Drug A reduced X by 1.5%" in md
    assert "Cited span quote" in md  # column header


def test_per_sentence_output_truncates_long_sentences():
    """The per-sentence dump caps sentence preview at 200 chars to
    keep the audit manifest readable.
    """
    long_sentence = "a " * 200
    span = "a a a a a"
    pool = _pool(span, "a")
    s = f"{long_sentence}[#ev:a:0-{len(span)}]."
    r = audit_sentence(s, pool)
    assert len(r["sentence"]) <= 200


# ─────────────────────────────────────────────────────────────────────
# I-audit-001 — resolved-report mode tests
# ─────────────────────────────────────────────────────────────────────


def _write_bibliography(tmp_path, entries):
    import json as _json
    p = tmp_path / "bibliography.json"
    p.write_text(_json.dumps(entries), encoding="utf-8")
    return p


def _write_pool(tmp_path, entries):
    import json as _json
    p = tmp_path / "pool.json"
    p.write_text(_json.dumps(entries), encoding="utf-8")
    return p


def test_resolved_n_resolves_to_valid_ev_id(tmp_path):
    """[N] markers in delivered report.md resolve to VERIFIED via
    bibliography lookup + pool fetch.
    """
    from scripts.run_line_by_line_audit import (
        _load_sentences_with_resolved_citations,
        _normalize_pool,
        run_line_by_line_audit_records,
    )

    report = (
        "# Research report: Tirzepatide efficacy\n"
        "\n"
        "### Efficacy\n"
        "\n"
        "Tirzepatide reduced HbA1c by 1.5% in adult patients.[1]"
    )
    report_path = tmp_path / "report.md"
    report_path.write_text(report, encoding="utf-8")
    bib_path = _write_bibliography(tmp_path, [
        {"num": 1, "evidence_id": "ev_a", "url": "u", "tier": "T1",
         "statement": "..."},
    ])
    span = "Tirzepatide reduced HbA1c by 1.5% in adult patients."
    pool = _normalize_pool(
        [{"evidence_id": "ev_a", "direct_quote": span}]
    )
    sentences, meta = _load_sentences_with_resolved_citations(
        report_path, bib_path, pool,
    )
    r = run_line_by_line_audit_records(sentences, pool)
    assert r["summary"]["total_sentences"] == 1
    assert r["summary"]["verdict_counts"]["VERIFIED"] == 1
    assert meta["excluded_synthesis_sections"] == []
    assert meta["terminal_h2_boundary_hit"] is False


def test_resolved_unknown_citation_num_yields_unreachable(tmp_path):
    """[N] where N is not in bibliography → UNREACHABLE with the
    canonical user-visible reason.
    """
    from scripts.run_line_by_line_audit import (
        _load_sentences_with_resolved_citations,
        _normalize_pool,
        run_line_by_line_audit_records,
    )

    report = "### Efficacy\n\nClaim text here.[7]"
    report_path = tmp_path / "report.md"
    report_path.write_text(report, encoding="utf-8")
    bib_path = _write_bibliography(tmp_path, [
        {"num": 1, "evidence_id": "ev_a"},
    ])
    pool = _normalize_pool(
        [{"evidence_id": "ev_a", "direct_quote": "anything"}]
    )
    sentences, _ = _load_sentences_with_resolved_citations(
        report_path, bib_path, pool,
    )
    r = run_line_by_line_audit_records(sentences, pool)
    assert r["summary"]["verdict_counts"]["UNREACHABLE"] == 1
    assert (
        "unknown_evidence_id:__unresolved_7__"
        == r["per_sentence"][0]["reason"]
    )


def test_resolved_ev_id_present_but_empty_text_yields_unreachable(tmp_path):
    """I-audit-001 diff iter-1 P1 fix: pool entry exists but its
    normalized evidence text is empty (broken substrate) must fail
    loudly as UNREACHABLE, not silently degrade to PARTIAL via the
    empty-span content-check path. LAW II — no silent fallbacks.
    """
    from scripts.run_line_by_line_audit import (
        _load_sentences_with_resolved_citations,
        _normalize_pool,
        run_line_by_line_audit_records,
    )

    report_path = tmp_path / "report.md"
    report_path.write_text(
        "### Efficacy\n\nDrug A reduced X by 1.5% across the cohort.[1]",
        encoding="utf-8",
    )
    bib_path = _write_bibliography(tmp_path, [
        {"num": 1, "evidence_id": "ev_a"},
    ])
    # ev_a IS in pool but its direct_quote is empty string.
    pool = _normalize_pool([
        {"evidence_id": "ev_a", "direct_quote": ""},
    ])
    sentences, _ = _load_sentences_with_resolved_citations(
        report_path, bib_path, pool,
    )
    r = run_line_by_line_audit_records(sentences, pool)
    assert r["summary"]["verdict_counts"]["UNREACHABLE"] == 1
    assert r["summary"]["verdict_counts"]["PARTIAL"] == 0
    assert r["summary"]["alert"] is True
    assert "__empty_text_ev_a__" in r["per_sentence"][0]["reason"]


def test_resolved_ev_id_not_in_pool_yields_unreachable(tmp_path):
    """[N] resolves to ev_id but ev_id is absent from pool → UNREACHABLE
    with the canonical `unknown_evidence_id:<ev_id>` diagnostic
    (iter-2 P2-1 fix: distinct from the empty-text case)."""
    from scripts.run_line_by_line_audit import (
        _load_sentences_with_resolved_citations,
        _normalize_pool,
        run_line_by_line_audit_records,
    )

    report_path = tmp_path / "report.md"
    report_path.write_text("### Efficacy\n\nA body claim.[1]", encoding="utf-8")
    bib_path = _write_bibliography(tmp_path, [
        {"num": 1, "evidence_id": "ev_missing"},
    ])
    pool = _normalize_pool([])  # empty pool
    sentences, _ = _load_sentences_with_resolved_citations(
        report_path, bib_path, pool,
    )
    r = run_line_by_line_audit_records(sentences, pool)
    assert r["summary"]["verdict_counts"]["UNREACHABLE"] == 1
    # Diagnostic must name the actual missing ev_id, not the empty-text
    # sentinel (iter-2 P2-1: distinct cases get distinct reasons).
    assert r["per_sentence"][0]["reason"] == "unknown_evidence_id:ev_missing"


def test_resolved_production_order_limitations_after_synthesis(tmp_path):
    """iter-2 diff P2-2 fix: production assembly places ### Limitations
    AFTER ## Analyst Synthesis (per scripts/run_honest_sweep_r3.py:2157-2163).
    The walker must re-enter body mode on H3 so Limitations is kept.
    """
    from scripts.run_line_by_line_audit import (
        _load_sentences_with_resolved_citations,
        _normalize_pool,
        run_line_by_line_audit_records,
    )

    report = (
        "# Research report: Drug A\n"
        "\n"
        "### Efficacy\n"
        "\n"
        "Drug A reduced X by 1.5% in adult patients.[1]\n"
        "\n"
        "## Analyst Synthesis\n"
        "\n"
        "*Synthesis disclosure.*\n"
        "\n"
        "Synthesis prose that must be excluded.[1]\n"
        "\n"
        "### Limitations\n"
        "\n"
        "The corpus is dominated by tertiary sources.\n"
        "\n"
        "## Methods\n"
        "Methods prose.\n"
        "\n"
        "## Bibliography\n"
        "[1] Source 1 — https://example.com/1\n"
    )
    report_path = tmp_path / "report.md"
    report_path.write_text(report, encoding="utf-8")
    bib_path = _write_bibliography(tmp_path, [
        {"num": 1, "evidence_id": "ev_a"},
    ])
    pool = _normalize_pool([
        {"evidence_id": "ev_a",
         "direct_quote": "Drug A reduced X by 1.5% in adult patients."},
    ])
    sentences, meta = _load_sentences_with_resolved_citations(
        report_path, bib_path, pool,
    )
    r = run_line_by_line_audit_records(sentences, pool)

    # Body should contain the Efficacy claim (VERIFIED) + the
    # Limitations claim (UNSUPPORTED, no [N]) but NOT the synthesis
    # claim.
    assert r["summary"]["total_sentences"] == 2
    assert r["summary"]["verdict_counts"]["VERIFIED"] == 1
    assert r["summary"]["verdict_counts"]["UNSUPPORTED"] == 1
    sentences_dump = " ".join(p["sentence"] for p in r["per_sentence"])
    assert "Synthesis prose" not in sentences_dump
    assert "corpus is dominated" in sentences_dump
    assert meta["excluded_synthesis_sections"] == ["analyst synthesis"]


def test_resolved_multiple_citations_in_same_sentence(tmp_path):
    """Multiple [N1][N2] in the same sentence synthesize multiple tokens."""
    from scripts.run_line_by_line_audit import (
        _load_sentences_with_resolved_citations,
        _normalize_pool,
        run_line_by_line_audit_records,
    )

    report_path = tmp_path / "report.md"
    report_path.write_text(
        "### Efficacy\n\nDrug A and Drug B both helped patients.[1][2]",
        encoding="utf-8",
    )
    bib_path = _write_bibliography(tmp_path, [
        {"num": 1, "evidence_id": "ev_a"},
        {"num": 2, "evidence_id": "ev_b"},
    ])
    span_a = "Drug A helped patients in a study"
    span_b = "Drug B helped patients in another study"
    pool = _normalize_pool([
        {"evidence_id": "ev_a", "direct_quote": span_a},
        {"evidence_id": "ev_b", "direct_quote": span_b},
    ])
    sentences, _ = _load_sentences_with_resolved_citations(
        report_path, bib_path, pool,
    )
    r = run_line_by_line_audit_records(sentences, pool)
    assert r["summary"]["total_sentences"] == 1
    tokens = r["per_sentence"][0]["tokens"]
    assert len(tokens) == 2
    assert {t["evidence_id"] for t in tokens} == {"ev_a", "ev_b"}


def test_resolved_pool_with_only_snippet_key(tmp_path):
    """iter-1 P2-1 fix: pool entries with only `snippet` (no
    `direct_quote` or `full_text`) are auditable via _normalize_pool's
    fallback chain.
    """
    from scripts.run_line_by_line_audit import (
        _load_sentences_with_resolved_citations,
        _normalize_pool,
        run_line_by_line_audit_records,
    )

    report_path = tmp_path / "report.md"
    report_path.write_text(
        "### Efficacy\n\nDrug A reduced X by 1.5% across the cohort.[1]",
        encoding="utf-8",
    )
    bib_path = _write_bibliography(tmp_path, [
        {"num": 1, "evidence_id": "ev_a"},
    ])
    pool = _normalize_pool([
        {"evidence_id": "ev_a", "snippet": "Drug A reduced X by 1.5% in adult cohort."},
    ])
    sentences, _ = _load_sentences_with_resolved_citations(
        report_path, bib_path, pool,
    )
    r = run_line_by_line_audit_records(sentences, pool)
    assert r["summary"]["verdict_counts"]["VERIFIED"] == 1


def test_resolved_realistic_production_report_fixture(tmp_path):
    """iter-3 P2-1 fixture: realistic delivered report with title +
    level-3 claim subsections + synthesis layers + appended substrate
    sections + bibliography reference list.

    Per brief assertions (a)–(d).
    """
    from scripts.run_line_by_line_audit import (
        _load_sentences_with_resolved_citations,
        _normalize_pool,
        run_line_by_line_audit_records,
    )

    report = (
        "# Research report: efficacy of Drug A\n"
        "\n"
        "### Efficacy\n"
        "\n"
        "Drug A reduced X by 1.5% in adult patients.[1] "
        "Drug A also improved Y by 2.3% across trials.[2]\n"
        "\n"
        "### Limitations\n"
        "\n"
        "The corpus is dominated by tertiary sources.\n"
        "\n"
        "## Per-Trial Summaries\n"
        "\n"
        "Synthesis-layer prose that must NOT be audited.[1]\n"
        "\n"
        "## Methods\n"
        "\n"
        "Pre-registered protocol. Generator: model.\n"
        "\n"
        "## Contradiction disclosures\n"
        "\n"
        "Claims made in the body of this report are individually bound.\n"
        "\n"
        "## Bibliography\n"
        "[1] Source 1 — https://example.com/1 (tier T1)\n"
        "[2] Source 2 — https://example.com/2 (tier T1)\n"
        "\n"
        "## V30 Phase-1 Retrieval Coverage Disclosure\n"
        "\n"
        "Frame coverage substrate prose.\n"
    )
    report_path = tmp_path / "report.md"
    report_path.write_text(report, encoding="utf-8")
    bib_path = _write_bibliography(tmp_path, [
        {"num": 1, "evidence_id": "ev_a"},
        {"num": 2, "evidence_id": "ev_b"},
    ])
    span_a = "Drug A reduced X by 1.5% in adult patients."
    span_b = "Drug A improved Y by 2.3% across multiple trials."
    pool = _normalize_pool([
        {"evidence_id": "ev_a", "direct_quote": span_a},
        {"evidence_id": "ev_b", "direct_quote": span_b},
    ])
    sentences, meta = _load_sentences_with_resolved_citations(
        report_path, bib_path, pool,
    )
    r = run_line_by_line_audit_records(sentences, pool)

    # (a) exactly 3 verdicts: 2 VERIFIED body claims + 1 UNSUPPORTED
    # limitations sentence (no [N] marker).
    assert r["summary"]["total_sentences"] == 3, r["per_sentence"]
    assert r["summary"]["verdict_counts"]["VERIFIED"] == 2
    assert r["summary"]["verdict_counts"]["UNSUPPORTED"] == 1

    # (b) bibliography ref-list lines must not appear in any verdict.
    sentences_dump = " ".join(p["sentence"] for p in r["per_sentence"])
    assert "Source 1" not in sentences_dump
    assert "Source 2" not in sentences_dump
    assert "https://example.com" not in sentences_dump

    # (c) Per-Trial-Summaries synthesis sentence must NOT be audited.
    assert "Synthesis-layer prose" not in sentences_dump

    # (d) metadata records the excluded synthesis section.
    assert meta["excluded_synthesis_sections"] == ["per-trial summaries"]
    assert meta["terminal_h2_boundary_hit"] is True


def test_resolved_no_citation_marker_yields_unsupported(tmp_path):
    """Body sentence without any [N] → UNSUPPORTED (correct visibility,
    not silent filter)."""
    from scripts.run_line_by_line_audit import (
        _load_sentences_with_resolved_citations,
        _normalize_pool,
        run_line_by_line_audit_records,
    )

    report_path = tmp_path / "report.md"
    report_path.write_text(
        "### Efficacy\n\nA plain claim with no citation.",
        encoding="utf-8",
    )
    bib_path = _write_bibliography(tmp_path, [])
    pool = _normalize_pool([])
    sentences, _ = _load_sentences_with_resolved_citations(
        report_path, bib_path, pool,
    )
    r = run_line_by_line_audit_records(sentences, pool)
    assert r["summary"]["verdict_counts"]["UNSUPPORTED"] == 1


def test_resolved_cli_arg_validation_bibliography_without_resolved(tmp_path):
    """--bibliography without --resolved-report errors with exit 1."""
    import subprocess
    import sys as _sys

    pool_path = tmp_path / "pool.json"
    pool_path.write_text("[]", encoding="utf-8")
    bib_path = tmp_path / "bib.json"
    bib_path.write_text("[]", encoding="utf-8")
    report_path = tmp_path / "report.md"
    report_path.write_text("anything", encoding="utf-8")
    out = tmp_path / "out.json"

    proc = subprocess.run(
        [
            _sys.executable, str(REPO_ROOT / "scripts" / "run_line_by_line_audit.py"),
            "--report", str(report_path),
            "--pool", str(pool_path),
            "--bibliography", str(bib_path),
            "--output", str(out),
        ],
        capture_output=True, text=True,
    )
    assert proc.returncode == 1
    assert "--bibliography is only valid with --resolved-report" in proc.stderr


def test_resolved_cli_arg_validation_resolved_without_bibliography(tmp_path):
    """--resolved-report without --bibliography errors with exit 1."""
    import subprocess
    import sys as _sys

    pool_path = tmp_path / "pool.json"
    pool_path.write_text("[]", encoding="utf-8")
    report_path = tmp_path / "report.md"
    report_path.write_text("anything", encoding="utf-8")
    out = tmp_path / "out.json"

    proc = subprocess.run(
        [
            _sys.executable, str(REPO_ROOT / "scripts" / "run_line_by_line_audit.py"),
            "--resolved-report", str(report_path),
            "--pool", str(pool_path),
            "--output", str(out),
        ],
        capture_output=True, text=True,
    )
    assert proc.returncode == 1
    assert "--resolved-report requires --bibliography" in proc.stderr


def test_resolved_cli_writes_manifest_with_semantics_note(tmp_path):
    """End-to-end CLI run: manifest carries verdict_semantics_note_resolved
    + scope metadata."""
    import json as _json
    import subprocess
    import sys as _sys

    report = "### Efficacy\n\nDrug A reduced X by 1.5%.[1]"
    report_path = tmp_path / "report.md"
    report_path.write_text(report, encoding="utf-8")
    bib_path = _write_bibliography(tmp_path, [
        {"num": 1, "evidence_id": "ev_a"},
    ])
    pool_path = tmp_path / "pool.json"
    pool_path.write_text(
        _json.dumps([
            {"evidence_id": "ev_a", "direct_quote": "Drug A reduced X by 1.5%."},
        ]),
        encoding="utf-8",
    )
    out_path = tmp_path / "audit.json"

    proc = subprocess.run(
        [
            _sys.executable, str(REPO_ROOT / "scripts" / "run_line_by_line_audit.py"),
            "--resolved-report", str(report_path),
            "--bibliography", str(bib_path),
            "--pool", str(pool_path),
            "--output", str(out_path),
        ],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    manifest = _json.loads(out_path.read_text(encoding="utf-8"))
    assert manifest["resolved_mode"] is True
    assert "verdict_semantics_note_resolved" in manifest
    assert "direct_quote or full_text or snippet" in (
        manifest["verdict_semantics_note_resolved"]
    )
    assert "excluded_synthesis_sections" in manifest
    assert "unrecognized_h2_sections" in manifest
