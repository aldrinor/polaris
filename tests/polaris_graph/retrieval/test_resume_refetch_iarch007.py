"""I-arch-007 ITEM 6 (#1264) — A15 resume FETCH-SHELL re-fetch (over-drop INPUT fix).

The Q90 ``abort_excessive_gap`` 96% over-drop was caused by a --resume reloading the crashed run's
EMPTY-SHELL anchor rows untouched: empty cited spans => the generator's claims have nothing to ground
=> the UNCHANGED ``strict_verify`` CORRECTLY drops them => over-drop abort. The fix turns the A15
*detection-only* flag into an actual RE-FETCH that re-grounds the row's ``direct_quote`` with fresh
content (via the AccessBypass+Zyte cascade) so the gate has a REAL span — it NEVER relaxes the gate.

This suite proves the re-fetch INPUT-fix, faithfulness-SAFE (offline; no network, no model spend):
  (a) a degraded row whose re-fetch returns usable content is RECOVERED — ``direct_quote`` is
      repopulated with the fresh span and the degraded flags are cleared, so strict_verify now has a
      real span to verify;
  (b) a degraded row whose re-fetch is STILL a shell (empty / content-starved) is LEFT FLAGGED — no
      fabricated span is written; the UNCHANGED strict_verify will honestly drop any ungrounded claim;
  (c) the master flag defaults OFF (=> no re-fetch => byte-identical resume), and the re-fetch never
      mutates a faithfulness threshold — it only re-grounds the INPUT row.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.retrieval.resume_refetch import (
    refetch_degraded_resume_rows,
    resume_refetch_enabled,
)

# A real fetched provenance quote is >= 100 chars and prose-dense (passes is_content_starved).
_REAL_QUOTE = (
    "SAE J3016 defines six levels of driving automation (0-5). At Level 3 (conditional driving "
    "automation) the automated driving system performs the entire dynamic driving task within its "
    "operational design domain while a fallback-ready user remains receptive to a request to "
    "intervene. The standard was first published in 2014 and most recently revised in 2021."
)

# A shell: a login/landing stub that an AccessBypass cascade could not get past.
_SHELL_QUOTE = "Please log in. Subscribe for full text. 403 Forbidden."


def _starved(text: str) -> bool:
    """Offline stand-in for live_retriever.is_content_starved: starved iff short or login-stub."""
    if not text or len(text.strip()) < 200:
        return True
    low = text.lower()
    return any(s in low for s in ("please log in", "subscribe for full text", "403 forbidden"))


def _degraded_row(eid: str, url: str = "") -> dict:
    return {
        "evidence_id": eid,
        "source_url": url or f"https://standards.example/{eid}",
        "direct_quote": "",          # empty cited span — the over-drop cause
        "content_starved": True,
        "fetch_failed": True,
        "resume_refresh_pending": True,
    }


# ── (a) a usable re-fetch RECOVERS the row: direct_quote repopulated + flags cleared ──────────────


def test_recovered_row_repopulates_direct_quote_and_clears_flags():
    row = _degraded_row("ev_j3016")

    def _refetch(url):  # the live cascade returns a fresh, real quote
        return _REAL_QUOTE, {"eligible": True, "method": "zyte"}

    result = refetch_degraded_resume_rows(
        [row], refetch_fn=_refetch, is_content_starved_fn=_starved,
    )
    # The INPUT row now carries a REAL span for strict_verify to verify against.
    assert row["direct_quote"] == _REAL_QUOTE
    assert len(row["direct_quote"]) >= 100
    # The degraded flags are cleared (the row is no longer a shell).
    assert row["content_starved"] is False
    assert row["fetch_failed"] is False
    assert row["resume_refresh_pending"] is False
    assert result["recovered"] == ["ev_j3016"]
    assert result["still_shell"] == []


# ── (b) a still-shell re-fetch LEAVES the row flagged — NO fabricated span ────────────────────────


def test_still_shell_row_left_flagged_no_fabrication():
    row = _degraded_row("ev_paywalled")

    def _refetch(url):  # the cascade (incl. Zyte) still could not get past the paywall
        return _SHELL_QUOTE, {"eligible": False, "failure_mode": "paywall_shell"}

    result = refetch_degraded_resume_rows(
        [row], refetch_fn=_refetch, is_content_starved_fn=_starved,
    )
    # NO fabricated span: direct_quote stays empty; the row stays flagged so strict_verify will
    # honestly drop any ungrounded claim (the gate is NEVER relaxed).
    assert row["direct_quote"] == ""
    assert row["resume_refresh_pending"] is True
    assert row["content_starved"] is True
    assert result["recovered"] == []
    assert result["still_shell"] == ["ev_paywalled"]


def test_empty_refetch_is_treated_as_still_shell():
    """A cascade that returns nothing usable (empty quote) leaves the row flagged, not recovered."""
    row = _degraded_row("ev_dead")
    result = refetch_degraded_resume_rows(
        [row], refetch_fn=lambda u: ("", {}), is_content_starved_fn=_starved,
    )
    assert row["direct_quote"] == ""
    assert result["still_shell"] == ["ev_dead"]


def test_content_starved_quote_is_not_accepted_as_recovery():
    """Even a >=100-char re-fetch that is content-starved (login stub padded out) is NOT a recovery —
    the starvation guard runs on the re-fetched span so a shell can never masquerade as a real span."""
    starved_long = "Please log in. " * 30  # >100 chars but is_content_starved -> True
    row = _degraded_row("ev_stub")
    result = refetch_degraded_resume_rows(
        [row], refetch_fn=lambda u: (starved_long, {}), is_content_starved_fn=_starved,
    )
    assert row["direct_quote"] == ""
    assert result["still_shell"] == ["ev_stub"]


# ── fail-open: a missing URL or a re-fetch exception never aborts the resume ──────────────────────


def test_row_with_no_url_is_recorded_not_refetched():
    row = {"evidence_id": "ev_nourl", "direct_quote": "", "content_starved": True}
    result = refetch_degraded_resume_rows(
        [row], refetch_fn=lambda u: (_REAL_QUOTE, {}), is_content_starved_fn=_starved,
    )
    assert result["no_url"] == ["ev_nourl"]
    assert result["recovered"] == []


def test_refetch_exception_is_failopen_and_row_left_flagged():
    row = _degraded_row("ev_boom")

    def _refetch(url):
        raise RuntimeError("transient 503")

    result = refetch_degraded_resume_rows(
        [row], refetch_fn=_refetch, is_content_starved_fn=_starved,
    )
    # The exception is swallowed (resume continues); the row stays flagged for honest gate drop.
    assert result["errors"] == ["ev_boom"]
    assert row["resume_refresh_pending"] is True
    assert row["direct_quote"] == ""


def test_mixed_batch_recovers_some_leaves_others():
    good = _degraded_row("ev_good")
    bad = _degraded_row("ev_bad")

    def _refetch(url):
        return (_REAL_QUOTE, {}) if "ev_good" in url else (_SHELL_QUOTE, {})

    result = refetch_degraded_resume_rows(
        [good, bad], refetch_fn=_refetch, is_content_starved_fn=_starved,
    )
    assert good["direct_quote"] == _REAL_QUOTE
    assert bad["direct_quote"] == ""
    assert result["recovered"] == ["ev_good"]
    assert result["still_shell"] == ["ev_bad"]


# ── (c) the master flag defaults OFF => byte-identical resume ─────────────────────────────────────


def test_master_flag_defaults_off(monkeypatch):
    monkeypatch.delenv("PG_RESUME_REFETCH_DEGRADED", raising=False)
    assert resume_refetch_enabled() is False


@pytest.mark.parametrize("val", ["1", "true", "on", "yes", "TRUE", "On"])
def test_master_flag_on_values(monkeypatch, val):
    monkeypatch.setenv("PG_RESUME_REFETCH_DEGRADED", val)
    assert resume_refetch_enabled() is True


# ── Codex P1 (iter-2): a NON-STARVED registry/error page must NOT clear the degraded flags ────────
#
# The iter-1/2 length-only recovery path cleared every degraded flag on
# ``quote and not is_content_starved_fn(quote)``. A ~821-char doi.org "DOI Not Found" registry page
# is REAL English prose well above the starvation floor, so is_content_starved -> False and the flags
# were cleared — then ``is_row_genuinely_recovered`` accepted the row and
# ``propagate_recovered_spans_to_frame_rows`` could relabel a HOLLOW FrameRow to OPEN_ACCESS (a fetch
# FAILURE rendered as a real anchor). The fix injects the SAME registry/error/block-page screen the
# live forced-Zyte adoption path uses (``live_retriever._recovered_content_error_class``) so the resume
# recovery rejects the error page BEFORE clearing flags. §-1.3: refusing to adopt a fetch FAILURE as
# grounding is faithfulness-STRENGTHENING, not a source DROP — the row stays disclosed.

from src.polaris_graph.retrieval.live_retriever import (  # noqa: E402
    _recovered_content_error_class,
    is_content_starved as _live_is_content_starved,
)

# A realistic ~800-char doi.org "DOI Not Found" registry page: real prose (NON-starved) but a fetch
# FAILURE. Contains the registry signatures ``_recovered_content_error_class`` screens against.
_DOI_REGISTRY_ERROR_PAGE = (
    "DOI Not Found. 10.1086/705716. This DOI cannot be found in the DOI System. Possible reasons "
    "are that the DOI is incorrect in your source, that the DOI was copied incorrectly (check that "
    "the string includes all the characters before and after the slash and no sentence punctuation "
    "marks), or that the DOI has not been activated yet — please try again later and report the "
    "problem if the error continues. DOI name not found. Report errors to the responsible DOI "
    "registration agency. The International DOI Foundation (IDF) is a not-for-profit membership "
    "organization that is the governance and management body for the federation of Registration "
    "Agencies providing Digital Object Identifier services and registration, and is the registration "
    "authority for the ISO standard (ISO 26324) for the DOI system. Home. Handbook. Factsheets. FAQs."
)


def test_registry_error_page_is_nonstarved_but_a_real_page_is_recovered():
    """Precondition: the registry page is genuinely NON-starved (so the length-only guard would adopt
    it), while a real re-fetched span IS a recovery — the screen must be what separates them."""
    assert _live_is_content_starved(_DOI_REGISTRY_ERROR_PAGE) is False
    assert _live_is_content_starved(_REAL_QUOTE) is False
    # And the production screen classifies the registry page as an error, the real span as content.
    assert _recovered_content_error_class(_DOI_REGISTRY_ERROR_PAGE) != ""
    assert _recovered_content_error_class(_REAL_QUOTE) == ""


def test_registry_error_page_refetch_stays_flagged_not_recovered():
    """GREEN target (Codex P1): with the error-class screen wired, a re-fetch that returns a
    non-starved DOI-registry error page is NOT adopted — direct_quote is NOT repopulated, the degraded
    flags are KEPT, and the row lands in the ``error_page`` bucket (never ``recovered``)."""
    row = _degraded_row("ev_doi_registry")

    def _refetch(url):  # the cascade reached a doi.org "not found" registry page (a fetch FAILURE)
        return _DOI_REGISTRY_ERROR_PAGE, {"eligible": True, "method": "zyte"}

    result = refetch_degraded_resume_rows(
        [row],
        refetch_fn=_refetch,
        is_content_starved_fn=_live_is_content_starved,
        recovered_error_class_fn=_recovered_content_error_class,
    )
    # NO adoption: the registry page never becomes grounding; the row stays a disclosed shell.
    assert row["direct_quote"] == ""
    assert row["content_starved"] is True
    assert row["fetch_failed"] is True
    assert row["resume_refresh_pending"] is True
    assert result["recovered"] == []
    assert result["error_page"] == ["ev_doi_registry"]
    assert result["still_shell"] == []


def test_legacy_length_only_path_would_adopt_registry_page_documents_bug():
    """Contrast (documents the exact Codex-flagged bug): WITHOUT the screen (legacy None default), the
    same non-starved registry page IS wrongly adopted as a recovery and its flags cleared. This is the
    behaviour the injected screen closes; the production caller always wires the screen."""
    row = _degraded_row("ev_doi_registry_legacy")
    result = refetch_degraded_resume_rows(
        [row],
        refetch_fn=lambda u: (_DOI_REGISTRY_ERROR_PAGE, {}),
        is_content_starved_fn=_live_is_content_starved,
        # recovered_error_class_fn omitted => legacy length-only path.
    )
    assert row["direct_quote"] == _DOI_REGISTRY_ERROR_PAGE  # the bug: error page adopted as grounding
    assert result["recovered"] == ["ev_doi_registry_legacy"]
    assert result.get("error_page", []) == []


def test_registry_error_page_does_not_propagate_to_frame_row():
    """End-to-end (Codex P1): a reloaded contract row whose re-fetch hit a registry error page stays
    flagged, so ``recovered_spans_from_reloaded_rows`` excludes it and the hollow V30 FrameRow can NOT
    be relabelled OPEN_ACCESS — the anchor stays a disclosed gap (NO fabrication)."""
    from src.polaris_graph.retrieval.frame_fetcher import FrameRow, ProvenanceClass
    from src.polaris_graph.retrieval.resume_refetch import (
        propagate_recovered_spans_to_frame_rows,
        recovered_spans_from_reloaded_rows,
    )

    entity_id = "robots_jobs"
    # A reloaded CONTRACT row that A15 tried to re-fetch and hit a registry error page: the recovery
    # left its degraded flags set and did NOT repopulate its span.
    reloaded_row = {
        "evidence_id": entity_id,
        "v30_entity_id": entity_id,
        "v30_frame_row": True,
        "direct_quote": "",
        "content_starved": True,   # residual flag => the re-fetch did NOT recover it
        "fetch_failed": True,
        "resume_refresh_pending": True,
        "source_url": "https://doi.org/10.1086/705716",
    }

    def _refetch(url):
        return _DOI_REGISTRY_ERROR_PAGE, {"eligible": True, "method": "zyte"}

    refetch_degraded_resume_rows(
        [reloaded_row],
        refetch_fn=_refetch,
        is_content_starved_fn=_live_is_content_starved,
        recovered_error_class_fn=_recovered_content_error_class,
    )
    # The guarded builder must NOT admit the still-flagged row => empty propagation map.
    recovered = recovered_spans_from_reloaded_rows([reloaded_row])
    assert recovered == {}

    hollow = FrameRow(
        entity_id=entity_id,
        entity_type="economic_report",
        rendering_slot="empirical_displacement",
        provenance_class=ProvenanceClass.FRAME_GAP_UNRECOVERABLE,
        direct_quote="",
        quote_source="none",
        doi="10.1086/705716",
        pmid=None,
        oa_pdf_url=None,
        url="https://doi.org/10.1086/705716",
        title="Robots and Jobs: Evidence from US Labor Markets",
        authors=("Acemoglu D", "Restrepo P"),
        journal="Journal of Political Economy",
        year=2020,
        failure_reason="fetch_shell",
    )
    new_rows, telemetry = propagate_recovered_spans_to_frame_rows(
        (hollow,), recovered_span_by_entity=recovered,
    )
    assert telemetry["propagated"] == []
    (still_hollow,) = new_rows
    assert still_hollow.direct_quote == ""
    assert still_hollow.provenance_class == ProvenanceClass.FRAME_GAP_UNRECOVERABLE


@pytest.mark.parametrize("val", ["0", "false", "off", "no", ""])
def test_master_flag_off_values(monkeypatch, val):
    monkeypatch.setenv("PG_RESUME_REFETCH_DEGRADED", val)
    assert resume_refetch_enabled() is False
