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


@pytest.mark.parametrize("val", ["0", "false", "off", "no", ""])
def test_master_flag_off_values(monkeypatch, val):
    monkeypatch.setenv("PG_RESUME_REFETCH_DEGRADED", val)
    assert resume_refetch_enabled() is False
