# -*- coding: utf-8 -*-
"""I-deepfix-004 (#1375) PR-1 — OFFLINE tests for the wrong-content citable-span fix
(steps A + B + C + D).

Covers, per the Fable root-cause plan (.codex/I-deepfix-004/fable_root_cause_plan.md):

  D  shell_detector.is_issue_front_matter — TRUE on a REAL masthead/TOC span (dot-leader
     density) + a REAL ISSN+editorial-board masthead + a real-shaped Cyrillic dgpu
     masthead; FALSE on a real article head, a real ISSN-bearing non-masthead span, and a
     real incidental "contents" mention. Fail-open on a short stub. OFF flag byte-identical.
  D  shell_detector.identical_span_collision — 2 rows identical span + DIFFERENT works =>
     both flagged; identical span + SAME work => not flagged; unique spans => none;
     fetched_blob_sha key path.
  A  live_retriever.refetch_for_extraction_with_diagnostics — PG_REFETCH_FULL_BODY ON =>
     the fetch cap passed to _fetch_content is the large body cap (DEFAULT_CONTENT_MAX_CHARS)
     and the quote is still capped at max_chars (a deep decimal is recovered); OFF => the
     old max_chars fetch cap (byte-identical, deep decimal lost).
  B  access_bypass._parse_pdf_page_fragment / _parse_doi_page_range (pure);
     _resolve_doi_pdf_target captures the final URL + #page=N anchor from a redirect
     Location header (mocked aiohttp); a fitz page-slice on a real-shaped multi-article PDF
     returns the target article and NOT the ISSN/TOC page. OFF flag byte-identical.
  D wiring A15 recovery rejects a masthead span as wrong_content_front_matter (screen ON);
     OFF => the screen never fires (byte-identical).

REAL captured data: front-matter spans are pulled verbatim from banked corpus_snapshot.json
files (gitignored outputs/.codex) and copied into
tests/fixtures/i_deepfix_004/real_masthead_spans.json so the test is self-contained + CI-
runnable. Provenance per span is recorded in that fixture's _provenance block (LAW II).
The dgpu Cyrillic masthead was NOT on disk (all drb_* snapshots carry masthead-vocab count
0), so signal-2 is proven with a REAL captured ISSN+editorial masthead and the Cyrillic
СОДЕРЖАНИЕ/РЕДАКЦИОННАЯ КОЛЛЕГИЯ path is exercised with a real-shaped inline fixture
(DGPU_CYRILLIC_MASTHEAD_REAL_SHAPED). identical_span_collision reuses real masthead span
text with constructed DOIs because no banked rows share an identical blob across DOIs (the
on-disk snapshots predate B4 fetched_blob_sha stamping).
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path

import aiohttp

from src.polaris_graph.retrieval import shell_detector
import src.polaris_graph.retrieval.live_retriever as lr
from src.tools import access_bypass as ab


# ─────────────────────────────────────────────────────────────────────────────
# Real captured spans (banked into a committed fixture from gitignored snapshots).
# ─────────────────────────────────────────────────────────────────────────────

_FIXTURE_PATH = (
    Path(__file__).resolve().parents[1]
    / "fixtures"
    / "i_deepfix_004"
    / "real_masthead_spans.json"
)


def _load_spans() -> dict:
    with open(_FIXTURE_PATH, encoding="utf-8") as fh:
        data = json.load(fh)
    return data["spans"]


SPANS = _load_spans()

# A real-shaped Cyrillic dgpu-class journal masthead (822 chars). Built to match the
# dgpu reb-t-9-2-2026.pdf masthead described in the root-cause plan because that exact
# span was not present in any banked snapshot on disk. Exercises signal-2's Cyrillic
# vocabulary (СОДЕРЖАНИЕ = contents, РЕДАКЦИОННАЯ КОЛЛЕГИЯ = editorial board) + ISSN.
DGPU_CYRILLIC_MASTHEAD_REAL_SHAPED = (
    "Дагестанский государственный педагогический университет имени Р. Гамзатова\n"
    "Известия ДГПУ. Психолого-педагогические науки. Том 9. № 2. 2026\n"
    "ISSN 2500-2953 (Print)  ISSN 2687-0770 (Online)\n"
    "DOI: 10.31161/1995-0659-2026-9-2\n"
    "\n"
    "РЕДАКЦИОННАЯ КОЛЛЕГИЯ\n"
    "Главный редактор: доктор педагогических наук, профессор.\n"
    "Заместитель главного редактора. Ответственный секретарь.\n"
    "Члены редакционной коллегии: доктор психологических наук; "
    "доктор педагогических наук; кандидат философских наук.\n"
    "\n"
    "СОДЕРЖАНИЕ\n"
    "Раздел 1. Общая педагогика, история педагогики и образования\n"
    "Цифровизация и искусственный интеллект в образовании\n"
    "Раздел 2. Теория и методика обучения и воспитания\n"
    "Раздел 3. Коррекционная педагогика\n"
    "Учредитель: ФГБОУ ВО «Дагестанский государственный педагогический университет».\n"
    "Адрес редакции: издательство, редакционно-издательский отдел.\n"
)


# ─────────────────────────────────────────────────────────────────────────────
# D — is_issue_front_matter
# ─────────────────────────────────────────────────────────────────────────────


def test_front_matter_true_on_real_dot_leader_toc():
    """Signal 1: a REAL captured issue TOC head (77 dot-leader runs) is front-matter."""
    span = SPANS["toc_dot_leader_masthead"]
    assert shell_detector.is_issue_front_matter(span) is True


def test_front_matter_true_on_real_issn_editorial_masthead():
    """Signal 2: a REAL captured masthead (ISSN + editorial-board vocab) is front-matter."""
    span = SPANS["issn_editorial_masthead"]
    assert shell_detector.is_issue_front_matter(span) is True


def test_front_matter_true_on_real_shaped_cyrillic_dgpu_masthead():
    """Signal 2, Cyrillic path: ISSN + СОДЕРЖАНИЕ/РЕДАКЦИОННАЯ КОЛЛЕГИЯ is front-matter."""
    assert shell_detector.is_issue_front_matter(DGPU_CYRILLIC_MASTHEAD_REAL_SHAPED) is True


def test_front_matter_false_on_real_article_head():
    """FALSE: a real T1 article head carries zero front-matter signals (fail-open KEEP)."""
    span = SPANS["article_head_false"]
    assert shell_detector.is_issue_front_matter(span) is False


def test_front_matter_false_on_real_issn_bearing_non_masthead():
    """FALSE: a real span with an ISSN but NO contents/editorial vocab — proves signal 2
    requires BOTH the ISSN marker AND the contents vocabulary (a reference-list / prose
    ISSN citation must never trip the masthead screen)."""
    span = SPANS["issn_in_prose_false"]
    # Precondition on the real span: ISSN present, contents-vocab absent.
    assert shell_detector._FRONT_MATTER_ISSN_RE.search(span)
    assert shell_detector.is_issue_front_matter(span) is False


def test_front_matter_false_on_real_incidental_contents_mention():
    """FALSE: a real article span that mentions the word "contents" incidentally (no ISSN,
    no masthead vocabulary) — the co-occurrence requirement holds the other way too."""
    span = SPANS["incidental_contents_false"]
    assert "contents" in span.lower()
    assert shell_detector.is_issue_front_matter(span) is False


def test_front_matter_fail_open_on_short_stub():
    """A body below the min-body floor is too short to read a structural verdict => KEEP."""
    assert shell_detector.is_issue_front_matter("ISSN 2500-2953 СОДЕРЖАНИЕ") is False
    assert shell_detector.is_issue_front_matter("") is False


def test_front_matter_screen_flag_off_is_byte_identical(monkeypatch):
    """The default-ON gate: OFF => the screen wrapper never fires => byte-identical KEEP,
    even on the real dot-leader masthead. The pure detector itself is flag-agnostic (still
    reports the structural truth); only the live wrapper honours the flag."""
    span = SPANS["toc_dot_leader_masthead"]
    monkeypatch.setenv("PG_SPAN_CITED_WORK_SCREEN", "0")
    assert shell_detector.span_cited_work_screen_enabled() is False
    # The live fail-open wrapper must skip the screen when OFF.
    assert lr._span_is_issue_front_matter(span) is False
    monkeypatch.setenv("PG_SPAN_CITED_WORK_SCREEN", "1")
    assert shell_detector.span_cited_work_screen_enabled() is True
    assert lr._span_is_issue_front_matter(span) is True


# ─────────────────────────────────────────────────────────────────────────────
# D — identical_span_collision
# ─────────────────────────────────────────────────────────────────────────────


def _row(eid: str, span: str, doi: str = "", url: str = "", blob_sha: str = "") -> dict:
    r = {"evidence_id": eid, "direct_quote": span}
    if doi:
        r["doi"] = doi
    if url:
        r["source_url"] = url
    if blob_sha:
        r["fetched_blob_sha"] = blob_sha
    return r


def test_collision_identical_span_different_dois_both_flagged():
    """The 31x-dgpu shape reproduced with REAL masthead span text: two rows carry the
    IDENTICAL span but DIFFERENT DOIs => a multi-work container => BOTH flagged."""
    masthead = SPANS["toc_dot_leader_masthead"]
    rows = [
        _row("ev_a", masthead, doi="10.34142/x-2026-9-2-203-210"),
        _row("ev_b", masthead, doi="10.34142/x-2026-9-2-211-219"),
    ]
    flagged = shell_detector.identical_span_collision(rows)
    assert flagged == {"ev_a", "ev_b"}


def test_collision_identical_span_same_doi_not_flagged():
    """Identical span + SAME cited work is a legitimate duplicate (CONSOLIDATE, step E) —
    NOT a container collision => not flagged."""
    masthead = SPANS["toc_dot_leader_masthead"]
    rows = [
        _row("ev_a", masthead, doi="10.34142/x-2026-9-2-203-210"),
        _row("ev_b", masthead, doi="10.34142/x-2026-9-2-203-210"),
    ]
    assert shell_detector.identical_span_collision(rows) == set()


def test_collision_unique_spans_none_flagged():
    """Distinct spans can never be a container collision."""
    rows = [
        _row("ev_a", SPANS["article_head_false"], doi="10.1/aaa"),
        _row("ev_b", SPANS["issn_in_prose_false"], doi="10.2/bbb"),
    ]
    assert shell_detector.identical_span_collision(rows) == set()


def test_collision_blob_sha_key_different_dois_flagged():
    """The content-identity key prefers fetched_blob_sha (B4 stamp): two rows sharing one
    blob sha but citing different works => container => both flagged, even if the stored
    direct_quote strings differ (a windowed slice of the same blob)."""
    rows = [
        _row("ev_a", "windowed slice one", doi="10.1/aaa", blob_sha="deadbeef" * 8),
        _row("ev_b", "a different window", doi="10.2/bbb", blob_sha="deadbeef" * 8),
    ]
    assert shell_detector.identical_span_collision(rows) == {"ev_a", "ev_b"}


# ─────────────────────────────────────────────────────────────────────────────
# A — full-body refetch (fetch cap separated from quote cap)
# ─────────────────────────────────────────────────────────────────────────────


def _install_truncating_fetch(monkeypatch, body: str, recorder: dict):
    """Stub _fetch_content that emulates the real `content = _stripped_body[:max_chars]`
    truncation and records the fetch cap it was called with."""

    def _stub(url, cap):  # signature: (url, max_chars) -> (content, ok, title, body_type, jsonld)
        recorder["cap"] = cap
        return (body[:cap], True, "", "full_text", None)

    monkeypatch.setattr(lr, "_fetch_content", _stub)
    lr.reset_refetch_cache()


def _build_deep_decimal_body() -> tuple[str, str]:
    head = "Employment and wage prose sentence. " * 40         # ~1480 chars head
    mid = "neutral filler body content here. " * 80            # push the decimal past 3000
    decimal = " the measured coefficient was 42.577 across cohorts. "
    tail = "tail prose here. " * 300
    body = head + mid + decimal + tail
    return body, "42.577"


def test_step_a_full_body_on_uses_large_fetch_cap_quote_capped(monkeypatch):
    """PG_REFETCH_FULL_BODY ON => _fetch_content is called with the large body cap
    (DEFAULT_CONTENT_MAX_CHARS), the quote stays capped at max_chars, and a decimal DEEP
    in the body (beyond max_chars) is recovered into the quote."""
    body, decimal = _build_deep_decimal_body()
    assert body.find(decimal) > 3000  # the decimal lives beyond the OFF fetch cap
    rec: dict = {}
    _install_truncating_fetch(monkeypatch, body, rec)
    monkeypatch.setenv("PG_REFETCH_FULL_BODY", "1")

    quote, diag = lr.refetch_for_extraction_with_diagnostics(
        "http://combined.test/on", max_chars=3000
    )

    assert rec["cap"] == lr.DEFAULT_CONTENT_MAX_CHARS  # full body fetched, not 3000
    assert diag["eligible"] is True
    assert len(quote) <= 3000  # quote still capped at max_chars
    assert decimal in quote     # deep decimal recovered by the decimal-window design


def test_step_a_full_body_off_is_byte_identical_head_truncated(monkeypatch):
    """PG_REFETCH_FULL_BODY OFF => _fetch_content is called with the OLD max_chars fetch
    cap (byte-identical to the prior head-truncating path); the deep decimal is thrown
    away with the truncated body."""
    body, decimal = _build_deep_decimal_body()
    rec: dict = {}
    _install_truncating_fetch(monkeypatch, body, rec)
    monkeypatch.setenv("PG_REFETCH_FULL_BODY", "0")

    quote, diag = lr.refetch_for_extraction_with_diagnostics(
        "http://combined.test/off", max_chars=3000
    )

    assert rec["cap"] == 3000     # old behaviour: fetch capped at max_chars
    assert diag["eligible"] is True
    assert len(quote) <= 3000
    assert decimal not in quote   # truncated away before the quote was built


# ─────────────────────────────────────────────────────────────────────────────
# B — page-anchor parsing (pure)
# ─────────────────────────────────────────────────────────────────────────────


def test_parse_pdf_page_fragment_hash_form():
    assert ab._parse_pdf_page_fragment("https://x/y.pdf#page=207") == 207
    assert ab._parse_pdf_page_fragment("#page=1") == 1


def test_parse_pdf_page_fragment_query_form_and_misses():
    assert ab._parse_pdf_page_fragment("https://x/y.pdf?page=42") == 42
    assert ab._parse_pdf_page_fragment("https://x/y.pdf") is None
    assert ab._parse_pdf_page_fragment("") is None
    assert ab._parse_pdf_page_fragment("#page=0") is None  # 1-indexed; 0 rejected


def test_parse_doi_page_range_from_suffix():
    assert ab._parse_doi_page_range("10.34142/2312-2919-2026-9-2-203-210") == (203, 210)


def test_parse_doi_page_range_rejects_inconsistent_and_missing():
    assert ab._parse_doi_page_range("10.34142/2312-2919-2026-9-2-210-203") == (None, None)
    assert ab._parse_doi_page_range("10.1000/plainjournal") == (None, None)
    assert ab._parse_doi_page_range(None) == (None, None)


# ─────────────────────────────────────────────────────────────────────────────
# B — doi.org -> .pdf#page=N redirect resolution (mocked aiohttp)
# ─────────────────────────────────────────────────────────────────────────────


class _FakeHeaders(dict):
    def get(self, key, default=None):
        for k, v in self.items():
            if k.lower() == key.lower():
                return v
        return default


class _FakeHist:
    def __init__(self, location: str):
        self.headers = _FakeHeaders({"Location": location})


class _FakeResp:
    def __init__(self, final_url: str, content_type: str, history: list):
        self.url = final_url
        self.headers = _FakeHeaders({"Content-Type": content_type})
        self.history = history

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    def __init__(self, resp: _FakeResp):
        self._resp = resp

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def get(self, url, allow_redirects=True):
        return self._resp


def test_resolve_doi_pdf_target_captures_final_url_and_location_anchor(monkeypatch):
    """STEP B1: a doi.org URL redirects to a publisher .pdf; the #page=207 anchor lives
    ONLY on a redirect Location header (deliberately absent from the final url, which the
    code comments say resp.url frequently drops). The resolver must still capture the final
    resolved url AND page_anchor=207, plus page_end=210 from the DOI suffix."""
    orig = "https://doi.org/10.34142/2312-2919-2026-9-2-203-210"
    final = "https://journals.example.org/vol9/reb-t-9-2-2026.pdf"  # no fragment here
    history = [
        _FakeHist("https://journals.example.org/redirect?to=reb-t-9-2-2026.pdf#page=207")
    ]
    resp = _FakeResp(final, "application/pdf", history)
    # _resolve_doi_pdf_target does a local `import aiohttp; aiohttp.ClientSession(...)`,
    # so patching the real module's ClientSession intercepts the fetch offline.
    monkeypatch.setattr(aiohttp, "ClientSession", lambda *a, **k: _FakeSession(resp))

    result = asyncio.run(ab.AccessBypass()._resolve_doi_pdf_target(orig))

    assert result is not None
    assert result["final_url"] == final
    assert result["is_pdf"] is True
    assert result["page_anchor"] == 207   # captured from the redirect Location header
    assert result["page_end"] == 210      # from the DOI suffix -203-210


# ─────────────────────────────────────────────────────────────────────────────
# B — fitz page-slice on a real-shaped multi-article combined PDF
# ─────────────────────────────────────────────────────────────────────────────

_PAGE_TEXTS = [
    # page 1: journal-issue cover / ISSN masthead / table of contents (front matter)
    "ISSN 2500-2953  СОДЕРЖАНИЕ  РЕДАКЦИОННАЯ КОЛЛЕГИЯ  Table of Contents  "
    "cover page 1 masthead front matter of the whole combined issue.",
    # pages 2-3: the CITED article (alpha)
    "ARTICLE_ALPHA_MARKER Automation and employment: an alpha study. "
    "Abstract methods results the measured effect was 42.577 percent.",
    "ARTICLE_ALPHA_MARKER continued: alpha discussion, conclusion and references.",
    # pages 4-5: a DIFFERENT article (beta) in the same combined PDF
    "ARTICLE_BETA_MARKER A second unrelated article beta. Introduction to a different topic.",
    "ARTICLE_BETA_MARKER continued: beta results, discussion and references.",
]


def _build_multi_article_pdf() -> bytes:
    import fitz

    doc = fitz.open()
    for text in _PAGE_TEXTS:
        page = doc.new_page()
        page.insert_text((72, 100), text, fontsize=11)
    data = doc.tobytes()
    doc.close()
    return data


def _extract_impl(pdf_bytes: bytes, **kwargs) -> str:
    inst = ab.AccessBypass()
    # Belt-and-suspenders with the env skip below: never let docling win the tiny fixture
    # (docling returns the WHOLE doc and early-returns before the PyMuPDF slice path).
    inst._docling_extract = lambda _b: ""
    return asyncio.run(
        inst._extract_pdf_text_from_bytes_impl("http://x/combined.pdf", pdf_bytes, **kwargs)
    )


def test_fitz_page_slice_returns_cited_article_not_toc(monkeypatch):
    """STEP B2: with page_anchor=2, page_end=3 the fitz path extracts ONLY the cited
    article (pages 2-3), NOT the page-1 ISSN/TOC masthead and NOT the other article
    (pages 4-5) that shares the combined PDF."""
    # Force the PyMuPDF slice path (docling is skipped for docs > 1 page); the slice logic
    # lives only in the PyMuPDF fallback.
    monkeypatch.setenv("PG_MAX_DOCLING_PDF_PAGES", "1")
    pdf = _build_multi_article_pdf()

    sliced = _extract_impl(pdf, page_anchor=2, page_end=3)

    assert "ARTICLE_ALPHA_MARKER" in sliced
    assert "ISSN 2500-2953" not in sliced
    assert "СОДЕРЖАНИЕ" not in sliced
    assert "ARTICLE_BETA_MARKER" not in sliced


def test_fitz_no_anchor_off_path_extracts_whole_doc(monkeypatch):
    """STEP B OFF / no anchor (page_anchor=None) => byte-identical whole-doc extraction,
    which includes the masthead AND both articles."""
    monkeypatch.setenv("PG_MAX_DOCLING_PDF_PAGES", "1")
    pdf = _build_multi_article_pdf()

    whole = _extract_impl(pdf)  # no page kwargs => old 2-arg path

    assert "ISSN 2500-2953" in whole
    assert "ARTICLE_ALPHA_MARKER" in whole
    assert "ARTICLE_BETA_MARKER" in whole


def test_pdf_cited_work_slice_flag_default_on_and_off():
    """The default-ON gate + its explicit-OFF values."""
    orig = os.environ.pop("PG_PDF_CITED_WORK_SLICE", None)
    try:
        assert ab.pdf_cited_work_slice_enabled() is True  # unset => default ON
        for off in ("0", "false", "no", "off"):
            os.environ["PG_PDF_CITED_WORK_SLICE"] = off
            assert ab.pdf_cited_work_slice_enabled() is False
        for on in ("1", "true", "yes", "on"):
            os.environ["PG_PDF_CITED_WORK_SLICE"] = on
            assert ab.pdf_cited_work_slice_enabled() is True
    finally:
        os.environ.pop("PG_PDF_CITED_WORK_SLICE", None)
        if orig is not None:
            os.environ["PG_PDF_CITED_WORK_SLICE"] = orig


# ─────────────────────────────────────────────────────────────────────────────
# D wiring — A15 recovery refetch rejects a masthead span as wrong_content_front_matter
# ─────────────────────────────────────────────────────────────────────────────


def test_refetch_rejects_masthead_span_wrong_content_front_matter(monkeypatch):
    """Screen ON (default): when the re-fetch returns a REAL journal-issue masthead body,
    the A15 recovery must route it to the not-extractable branch with
    failure_mode == 'wrong_content_front_matter' (never adopt a cover/TOC span as the
    cited article; recover->degrade->disclose, source kept)."""
    masthead = SPANS["toc_dot_leader_masthead"]
    rec: dict = {}
    _install_truncating_fetch(monkeypatch, masthead, rec)
    monkeypatch.setenv("PG_SPAN_CITED_WORK_SCREEN", "1")

    quote, diag = lr.refetch_for_extraction_with_diagnostics(
        "http://combined.test/masthead-on", max_chars=4000
    )

    assert quote == ""
    assert diag["failure_mode"] == "wrong_content_front_matter"


def test_refetch_masthead_screen_off_is_byte_identical(monkeypatch):
    """Screen OFF => the front-matter screen never fires (byte-identical); the masthead
    body is NOT rejected as wrong_content_front_matter (the OFF path adopts whatever the
    pre-existing gates allow, exactly as before this fix)."""
    masthead = SPANS["toc_dot_leader_masthead"]
    rec: dict = {}
    _install_truncating_fetch(monkeypatch, masthead, rec)
    monkeypatch.setenv("PG_SPAN_CITED_WORK_SCREEN", "0")

    _quote, diag = lr.refetch_for_extraction_with_diagnostics(
        "http://combined.test/masthead-off", max_chars=4000
    )

    assert diag["failure_mode"] != "wrong_content_front_matter"
