# -*- coding: utf-8 -*-
"""I-deepfix-004 PR-1 LANE-B (live path) — behavioral tests for F1 / F7 / F5.

These prove the three wrong-content FRONT-MATTER disposition fixes on the LIVE
retrieval path (``live_retriever``) and the A15 resume-recovery path
(``resume_refetch``). Each test drives the REAL code seam (not a flag-set check)
and is RED on the pre-fix branch:

  F1  A detected journal-issue FRONT-MATTER span (cover / TOC / masthead) must be
      stamped ``wrong_content_span`` + degraded + down-weighted + DISCLOSED and NOT
      admitted as normal citable evidence, under the DEFAULT flags (screen ON,
      redesign OFF, Zyte re-fetch OFF) — i.e. INDEPENDENT of the forced-Zyte flag.
      It is KEPT in the pool (never hard-dropped): a front-matter body is a CREDIBLE
      ON-TOPIC source (right journal, wrong article), only the wrong SPAN is unusable.
      Pre-fix ``_is_front_matter`` was consumed ONLY to enter the default-OFF Zyte
      re-fetch, so with that flag OFF the front-matter span sailed through as a normal
      full-weight, grounded row.

  F7  The live forced-Zyte adoption branch checked only ``is_content_starved`` +
      error-class, so a re-fetch that returned the SAME whole-issue / TOC / masthead
      body was LAUNDERED in as RECOVERED full text. A re-fetched body that is still
      front-matter must NOT be adopted; the row stays wrong_content_span + disclosed.

  F5  ``resume_refetch._DEGRADED_FLAGS`` must include ``wrong_content_span`` so an A15
      resume that genuinely re-fetches a wrong-content row to real full text CLEARS the
      flag, and ``is_row_genuinely_recovered`` refuses to propagate a row that still
      carries it.

REAL captured data: the front-matter span is the REAL ``issn_editorial_masthead``
captured span (ISSN + editorial-board masthead) from the committed fixture — chosen
because it is front-matter AND not content-starved, so ``_is_front_matter`` computes
True (the dot-leader TOC span is ALSO content-starved and would take the starved
disposition instead).
"""
from __future__ import annotations

import json
from pathlib import Path

from src.polaris_graph.nodes.corpus_adequacy_gate import count_grounded_rows
from src.polaris_graph.retrieval import live_retriever, resume_refetch
from src.tools.access_bypass import AccessBypass, AccessResult

# ── Real captured front-matter span (front-matter AND not content-starved) ────
_FIXTURE_PATH = (
    Path(__file__).resolve().parents[2]
    / "fixtures"
    / "i_deepfix_004"
    / "real_masthead_spans.json"
)


def _load_span(key: str) -> str:
    with open(_FIXTURE_PATH, encoding="utf-8") as fh:
        return json.load(fh)["spans"][key]


_FRONT_MATTER_MASTHEAD = _load_span("issn_editorial_masthead")
# A distinctive marker in the masthead used to prove it is NOT laundered into the
# grounding span on the F7 non-adoption path.
_MASTHEAD_MARKER = "ISSN: 2517-5718"

# A generic degraded stub (ok=False, thin real prose, NOT front-matter, NOT starved):
# the class whose ONLY degraded signal is the fetch layer's paywall-stub verdict. Used
# for F7 so the row enters the re-fetch via ``not ok`` and the RE-FETCH (not the original
# body) is what returns front-matter.
_DEGRADED_STUB = (
    "Summary of safety and effectiveness data. The device is indicated for the "
    "staging of disease in adult patients. Clinical studies demonstrated safety "
    "and effectiveness for the intended use across the enrolled study cohort."
)

_SEED_URL = "https://journals.example.org/vol9/reb-t-9-2-2026-frontmatter"


def _common_offline_env(monkeypatch) -> None:
    """Force the serial offline fetch path + no OpenAlex network (mirrors the
    I-arch-011 behavioral harness)."""
    monkeypatch.setenv("PG_USE_PARALLEL_FETCH", "0")
    monkeypatch.setenv("PG_ENABLE_LIVE_OA_RESOLVER", "0")
    # Front-matter screen is default-ON; pin it explicitly for determinism.
    monkeypatch.setenv("PG_SPAN_CITED_WORK_SCREEN", "1")
    monkeypatch.setattr(
        live_retriever, "_bounded_openalex_enrich", lambda *a, **k: {}
    )


def _run_seed_only(monkeypatch):
    return live_retriever.run_live_retrieval(
        research_question="automation and employment digitalization in education",
        seed_urls=[_SEED_URL],
        seed_only=True,
        enable_openalex_enrich=False,
        enable_prefetch_filter=False,
        anchor_seed=False,
    ).evidence_rows


# ─────────────────────────────────────────────────────────────────────────────
# F1 — front-matter span degrades + discloses under DEFAULT flags, no hard-drop
# ─────────────────────────────────────────────────────────────────────────────


def test_f1_front_matter_degrades_and_discloses_under_default_flags(monkeypatch):
    """DEFAULT flags: screen ON, redesign OFF (unset), Zyte re-fetch OFF (unset).

    A front-matter masthead body (ok=True, non-starved) must be KEPT as a
    wrong_content_span + degraded + down-weighted DISCLOSED row — never admitted as
    normal grounded evidence and never hard-dropped. RED pre-fix: the row is a normal
    grounded full-weight row (no wrong_content_span, counts as grounded).
    """
    _common_offline_env(monkeypatch)
    # The two escalation flags stay OFF — this is the crux: the disposition must fire
    # INDEPENDENT of the forced-Zyte re-fetch flag and the redesign flag.
    monkeypatch.delenv("PG_REFETCH_DEGRADED_VIA_ZYTE", raising=False)
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)

    def _stub_fetch_content(url, max_chars, *a, **k):
        # A journal-issue masthead fetches 200 OK — ok=True; it is real content, not a
        # paywall stub. The ONLY thing wrong is that it is the WRONG span (front-matter).
        return (_FRONT_MATTER_MASTHEAD, True, "Issue front matter", "full_text", "")

    monkeypatch.setattr(live_retriever, "_fetch_content", _stub_fetch_content)

    rows = _run_seed_only(monkeypatch)

    assert len(rows) == 1, (
        f"the front-matter source must be KEPT (degrade+disclose, never hard-dropped); "
        f"got {len(rows)} rows"
    )
    row = rows[0]
    assert row.get("wrong_content_span") is True, (
        "front-matter span must be stamped wrong_content_span (RED pre-fix: absent — "
        "the span sailed through as normal evidence because the Zyte flag was OFF)"
    )
    assert row.get("full_text_capable") is False, (
        "a cover/TOC/masthead cannot ground a claim — full_text_capable must be False"
    )
    assert row.get("down_weighted") is True, (
        "the wrong-content span must be down-weighted (kept at low weight, disclosed)"
    )
    assert isinstance(row.get("retrieval_weight"), float) and row["retrieval_weight"] > 0.0, (
        "a down-weighted row carries a small positive retrieval weight (never zero)"
    )
    # NOT admitted as normal evidence: excluded from the real adequacy grounded count.
    assert count_grounded_rows(rows) == 0, (
        "a wrong-content front-matter span must NOT count as a grounded source "
        "(RED pre-fix: it counted as 1)"
    )


def test_f1_screen_off_is_byte_identical_normal_row(monkeypatch):
    """Screen OFF => ``_is_front_matter`` is always False => the new consumer never
    fires => the masthead body is a NORMAL grounded row (byte-identical to pre-fix).

    Proves the OFF path carries no behavior change (the fix is gated on the default-ON
    ``PG_SPAN_CITED_WORK_SCREEN`` and fail-open)."""
    _common_offline_env(monkeypatch)
    monkeypatch.setenv("PG_SPAN_CITED_WORK_SCREEN", "0")  # override the default-ON pin
    monkeypatch.delenv("PG_REFETCH_DEGRADED_VIA_ZYTE", raising=False)
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)

    def _stub_fetch_content(url, max_chars, *a, **k):
        return (_FRONT_MATTER_MASTHEAD, True, "Issue front matter", "full_text", "")

    monkeypatch.setattr(live_retriever, "_fetch_content", _stub_fetch_content)

    rows = _run_seed_only(monkeypatch)

    assert len(rows) == 1
    row = rows[0]
    assert row.get("wrong_content_span") is not True, (
        "screen OFF must NOT stamp wrong_content_span (byte-identical OFF path)"
    )
    assert count_grounded_rows(rows) == 1, (
        "screen OFF => the row grounds normally, exactly as before the fix"
    )


# ─────────────────────────────────────────────────────────────────────────────
# F7 — a re-fetched front-matter body is NOT adopted as recovered full text
# ─────────────────────────────────────────────────────────────────────────────


def test_f7_refetched_front_matter_body_not_adopted(monkeypatch):
    """A degraded stub forces a Zyte re-fetch that returns the SAME whole-issue
    FRONT-MATTER body. The re-screen must REFUSE to adopt it as recovered full text; the
    row stays wrong_content_span + disclosed and the masthead is never laundered into the
    grounding span. RED pre-fix: the non-starved, non-error masthead was adopted as
    RECOVERED full text (counts as grounded, marker present in direct_quote).
    """
    _common_offline_env(monkeypatch)
    # Enable the forced-Zyte re-fetch + present a key. Redesign stays OFF to ALSO prove
    # the wrong-content row is kept (never hard-dropped) on the legacy-disposition path.
    monkeypatch.setenv("PG_REFETCH_DEGRADED_VIA_ZYTE", "1")
    monkeypatch.setenv("ZYTE_API_KEY", "test-zyte-key-not-real")
    monkeypatch.delenv("PG_SWEEP_CREDIBILITY_REDESIGN", raising=False)

    def _stub_fetch_content(url, max_chars, *a, **k):
        # ok=False paywall-stub verdict => the row enters the re-fetch via ``not ok``.
        return (_DEGRADED_STUB, False, "Degraded stub", "paywall_shell", "")

    monkeypatch.setattr(live_retriever, "_fetch_content", _stub_fetch_content)

    zyte_calls: list[str] = []

    async def _fake_try_zyte(self, url):
        zyte_calls.append(url)
        # The forced Zyte re-fetch returns the whole-issue FRONT-MATTER (wrong content).
        return AccessResult(
            url=url, content=_FRONT_MATTER_MASTHEAD, access_method="zyte",
            legal_alternative=None, success=True, metadata={"mode": "browserHtml"},
        )

    monkeypatch.setattr(AccessBypass, "_try_zyte", _fake_try_zyte, raising=True)

    rows = _run_seed_only(monkeypatch)

    assert zyte_calls == [_SEED_URL], (
        f"the forced Zyte re-fetch must have been attempted; got {zyte_calls!r}"
    )
    assert len(rows) == 1, "the wrong-content source is KEPT (never hard-dropped)"
    row = rows[0]
    assert row.get("wrong_content_span") is True, (
        "the re-fetched front-matter body must be REFUSED and the row stamped "
        "wrong_content_span (RED pre-fix: it was adopted as recovered full text)"
    )
    assert _MASTHEAD_MARKER not in row.get("direct_quote", ""), (
        "the front-matter masthead must NOT be laundered into the grounding span "
        "(RED pre-fix: the masthead body was adopted as direct_quote)"
    )
    assert count_grounded_rows(rows) == 0, (
        "a non-adopted wrong-content row must NOT count as a grounded source"
    )


# ─────────────────────────────────────────────────────────────────────────────
# F5 — A15 resume recovery clears wrong_content_span on a genuine re-fetch
# ─────────────────────────────────────────────────────────────────────────────


def test_f5_wrong_content_span_is_a_degraded_flag():
    """wrong_content_span is registered as an A15 degraded flag (RED pre-fix: absent)."""
    assert "wrong_content_span" in resume_refetch._DEGRADED_FLAGS


def test_f5_recovered_row_clears_wrong_content_span():
    """A reloaded row stamped wrong_content_span, re-fetched to real full text, has the
    flag CLEARED and is reported recovered. RED pre-fix: the flag stays True (it was not
    in _DEGRADED_FLAGS, so refetch_degraded_resume_rows never cleared it)."""
    row = {
        "evidence_id": "ev_000",
        "source_url": "https://journals.example.org/reb-t-9-2-2026",
        "direct_quote": "front matter stub",
        "wrong_content_span": True,
    }
    real_full_text = (
        "The measured coefficient across cohorts was 42.577 percent, with a "
        "confidence interval reported across thirty-two enrolled sites. " * 6
    )

    res = resume_refetch.refetch_degraded_resume_rows(
        [row],
        refetch_fn=lambda _u: (real_full_text, {}),
        is_content_starved_fn=lambda t: len(t) < 200,
    )

    assert "ev_000" in res["recovered"]
    assert row["direct_quote"] == real_full_text
    assert row["wrong_content_span"] is False, (
        "a genuine re-fetch must CLEAR wrong_content_span (RED pre-fix: stays True)"
    )


def test_f5_still_wrong_content_span_is_not_genuinely_recovered():
    """is_row_genuinely_recovered treats a row that still carries wrong_content_span as
    NOT recovered — so a still-front-matter row can never be propagated into a hollow
    contract FrameRow. RED pre-fix: the flag is ignored => returns True."""
    row = {
        "evidence_id": "ev_000",
        "v30_entity_id": "e1",
        "direct_quote": "front matter masthead span text long enough to clear the floor",
        "wrong_content_span": True,
    }
    assert resume_refetch.is_row_genuinely_recovered(row) is False
    row["wrong_content_span"] = False
    assert resume_refetch.is_row_genuinely_recovered(row) is True
