"""U20 (I-deepfix-001) — junk-span breadth screen.

Autopsy U20: captcha / cookie / empty ``direct_quote`` spans were counted as
evidence and inflated breadth; the junk screen only dropped YouTube hosts
(drb_75 real breadth ~730, not 893). This test pins the extended screen:

  * ``is_junk_source`` now drops CAPTCHA / cookie-consent / bot-challenge
    interstitial spans (via the canonical ``shell_detector.is_cited_span_shell``),
    while KEEPING real clinical prose — including the adversarial negatives the
    shell detector was hardened for (a long clinical body with an incidental
    cookie footer; a realistic-length span mentioning "access denied" once; a
    methods span mentioning "security verification").
  * The breadth seam ``_screen_junk_evidence`` additionally drops rows whose
    ACTUAL ``direct_quote`` is empty/whitespace (empty-quote), and its YouTube-host
    drop still works (regression guard).

Offline: no GPU, no network, no paid LLM — pure deterministic string predicates.
Faithfulness-neutral: strict_verify / NLI / 4-role / span-grounding untouched.
"""

from __future__ import annotations

import pytest

from src.tools.access_bypass import is_junk_source


# --------------------------------------------------------------------------- #
# Fixtures: real junk spans + real clinical prose (adversarial negatives).
# --------------------------------------------------------------------------- #

CAPTCHA_SPAN = (
    "Just a moment... Enable JavaScript and cookies to continue. This page is "
    "displayed while the website verifies you are not a bot. Performing security "
    "verification to protect against malicious bots. Cloudflare Ray ID: 8ab12cd."
)

COOKIE_CONSENT_SPAN = (
    "We use cookies to improve your experience on our site. By continuing to "
    "browse you agree to our cookie policy. Accept all cookies or manage your "
    "cookie preferences below. Accept."
)

# Real clinical prose — must be KEPT.
CLINICAL_SPAN = (
    "In a randomized controlled trial of 240 patients with type 2 diabetes, "
    "semaglutide 1.0 mg reduced HbA1c by 1.5 percent compared with placebo over "
    "26 weeks (p<0.001). Adverse events were mostly gastrointestinal."
)

# Adversarial negative 1 — a LONG real clinical article carrying an incidental
# cookie footer. The short-body chrome ceiling must protect it (drb_78 ev_694
# lesson). Must be KEPT.
LONG_CLINICAL_WITH_COOKIE_FOOTER = (
    "Deep brain stimulation of the subthalamic nucleus improved motor scores "
    "(UPDRS III) by 45 percent at 12 months in this cohort of 120 Parkinson "
    "disease patients. " * 8
    + " We use cookies to improve your experience. Accept all."
)

# Adversarial negative 2 — a realistic-length clinical span that mentions
# "access denied" once, with no second shell signal. Must be KEPT.
ACCESS_DENIED_ONCE = (
    "A qualitative study of 42 patients described how access denied to specialist "
    "neurology clinics delayed Parkinson disease diagnosis by a median of 8 "
    "months, with rural residents disproportionately affected and reporting "
    "greater symptom burden at first assessment."
)

# Adversarial negative 3 — a methods span mentioning "security verification".
# Must be KEPT.
SECURITY_VERIFICATION_METHODS = (
    "In the assay validation methods, a two-stage security verification of the "
    "laboratory results was performed before HbA1c and fasting glucose "
    "concentrations were entered into the mixed-effects model, ensuring "
    "transcription errors did not bias the estimated treatment effect over 26 weeks."
)


# --------------------------------------------------------------------------- #
# is_junk_source — the extended predicate.
# --------------------------------------------------------------------------- #

def test_captcha_span_is_junk():
    # Pre-fix RED: is_error_shell_text is length/co-token gated and returned False
    # on this span, so is_junk_source returned False. Post-fix GREEN via the
    # shell_detector delegation.
    assert is_junk_source("https://openalex.org/W1", CAPTCHA_SPAN) is True


def test_cookie_consent_span_is_junk():
    assert is_junk_source("https://openalex.org/W2", COOKIE_CONSENT_SPAN) is True


def test_real_clinical_span_is_kept():
    assert is_junk_source("https://www.nature.com/articles/x", CLINICAL_SPAN) is False


def test_long_clinical_with_cookie_footer_is_kept():
    # The single most important negative: the short-body chrome ceiling must keep a
    # long real article that merely carries an incidental cookie footer.
    assert len(LONG_CLINICAL_WITH_COOKIE_FOOTER) > 800
    assert is_junk_source(
        "https://www.thelancet.com/journals/x", LONG_CLINICAL_WITH_COOKIE_FOOTER
    ) is False


def test_access_denied_once_realistic_span_is_kept():
    assert len(ACCESS_DENIED_ONCE) > 200
    assert is_junk_source("https://doi.org/10.1000/x", ACCESS_DENIED_ONCE) is False


def test_security_verification_methods_span_is_kept():
    assert len(SECURITY_VERIFICATION_METHODS) > 200
    assert is_junk_source(
        "https://pubmed.ncbi.nlm.nih.gov/12345/", SECURITY_VERIFICATION_METHODS
    ) is False


def test_youtube_host_still_dropped_regression():
    # The original screen dropped YouTube by HOST — must still hold.
    assert is_junk_source("https://www.youtube.com/watch?v=abc", CLINICAL_SPAN) is True


def test_empty_text_is_not_junk_by_predicate():
    # is_junk_source must NOT treat empty text as junk on its own (host-only callers
    # pass text=""). Empty-quote screening lives at the row seam instead.
    assert is_junk_source("https://www.nature.com/articles/x", "") is False


# --------------------------------------------------------------------------- #
# _screen_junk_evidence — the breadth seam (captcha/cookie drop + empty-quote).
# --------------------------------------------------------------------------- #

def _rows():
    return [
        {"source_url": "https://a.org/1", "direct_quote": CAPTCHA_SPAN,
         "statement": "captcha"},
        {"source_url": "https://a.org/2", "direct_quote": COOKIE_CONSENT_SPAN,
         "statement": "cookie"},
        # phantom row: no fetched span, only a model statement -> empty_quote drop.
        {"source_url": "https://a.org/3", "direct_quote": "   ",
         "statement": "some model claim without a grounding span"},
        # real clinical row -> KEPT.
        {"source_url": "https://www.nature.com/x", "direct_quote": CLINICAL_SPAN,
         "statement": "clinical finding"},
        # long real clinical row with incidental cookie footer -> KEPT.
        {"source_url": "https://www.thelancet.com/x",
         "direct_quote": LONG_CLINICAL_WITH_COOKIE_FOOTER, "statement": "dbs finding"},
    ]


def test_seam_drops_junk_and_empty_quote_keeps_clinical(monkeypatch):
    monkeypatch.delenv("PG_JUNK_SOURCE_SCREEN", raising=False)  # default ON
    from scripts.run_honest_sweep_r3 import _screen_junk_evidence

    kept_rows, _kept_srcs, excluded = _screen_junk_evidence(_rows(), None)

    kept_urls = {_r["source_url"] for _r in kept_rows}
    assert kept_urls == {"https://www.nature.com/x", "https://www.thelancet.com/x"}

    reasons = {(_e["reason"]) for _e in excluded["evidence_rows_excluded"]}
    assert "junk_source" in reasons  # captcha + cookie
    assert "empty_quote" in reasons  # phantom row
    assert len(excluded["evidence_rows_excluded"]) == 3


def test_seam_killswitch_is_noop(monkeypatch):
    monkeypatch.setenv("PG_JUNK_SOURCE_SCREEN", "0")
    from scripts.run_honest_sweep_r3 import _screen_junk_evidence

    rows = _rows()
    kept_rows, _kept_srcs, excluded = _screen_junk_evidence(rows, None)
    # Kill-switch: every row kept, nothing excluded (byte-identical legacy no-op).
    assert len(kept_rows) == len(rows)
    assert excluded["evidence_rows_excluded"] == []


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
