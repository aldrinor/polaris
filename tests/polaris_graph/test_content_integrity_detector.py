"""Deterministic offline tests for the content-integrity junk detector.

Exercises `detect_content_integrity_junk(...)` in `src/tools/access_bypass.py`
(the pure LEAF chrome-non-source screen: no network, no models, no faithfulness
gate). Verifies each junk class (block_page / empty / not_found / cookie_error /
login_wall / nonarticle_stub), the new cookie-error visible-body rule, the
genuine-article negative control, and the FAIL-OPEN contract (a bug inside the
screen must never flag a real source as junk).

Runnable as a plain script (`python tests/polaris_graph/test_content_integrity_detector.py`)
or under pytest.
"""

import os
import sys

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from src.tools.access_bypass import (  # noqa: E402
    detect_content_integrity_junk,
    is_block_page_or_stub,
)

_URL = "https://example.org/some/article"

# --- Real-shaped anti-bot block-page body ------------------------------------
# Carries the decisive Cloudflare challenge marker (`window._cf_chl_opt`, length-
# ungated) AND the short visible "verify you are human" captcha phrase, so the
# block-page classifier fires regardless of the PG_BLOCK_PAGE_DETECTOR flag.
BOT_BLOCK_PAGE_BODY = (
    "<!DOCTYPE html><html lang='en-US'><head><title>Just a moment...</title>"
    "</head><body><div class='main'><h1>Verify you are human</h1>"
    "<p>Please complete the security check to access this site.</p></div>"
    "<script>window._cf_chl_opt = {cRay:'a122426bd8822c5d'};</script>"
    "</body></html>"
)

# --- Real-shaped cookie-error interstitial body (new visible rule) -----------
COOKIE_INTERSTITIAL_BODY = (
    "<!DOCTYPE html><html><head><title>Error - Cookies Turned Off</title></head>"
    "<body><h1>Cookies Turned Off</h1>"
    "<p>Cookies are disabled for your browser. Please enable cookies and try "
    "again.</p></body></html>"
)

# --- Genuine article: real title + real abstract body (negative control) -----
GENUINE_TITLE = (
    "Semaglutide and Cardiovascular Outcomes in Patients with Overweight or "
    "Obesity"
)
GENUINE_BODY = (
    "<html><head><title>Semaglutide and Cardiovascular Outcomes</title></head>"
    "<body><article><h1>Semaglutide and Cardiovascular Outcomes in Patients "
    "with Overweight or Obesity</h1>"
    "<section class='abstract'><p>In this randomized, double-blind, "
    "placebo-controlled trial, we enrolled patients who were 45 years of age or "
    "older, had preexisting cardiovascular disease, and had a body-mass index of "
    "27 or greater but no history of diabetes. Participants received once-weekly "
    "subcutaneous semaglutide at a dose of 2.4 mg or placebo. The primary "
    "cardiovascular end point was a composite of death from cardiovascular "
    "causes, nonfatal myocardial infarction, or nonfatal stroke. A primary "
    "cardiovascular end-point event occurred in 6.5% of the semaglutide group "
    "and in 8.0% of the placebo group (hazard ratio, 0.80; 95% confidence "
    "interval, 0.72 to 0.90).</p></section></article></body></html>"
)


def test_bot_block_page_body_is_block_page():
    flag, klass = detect_content_integrity_junk(
        BOT_BLOCK_PAGE_BODY, _URL, title="Just a moment..."
    )
    assert (flag, klass) == (True, "block_page")
    # Sanity: the underlying classifier agrees the body is a block page.
    assert is_block_page_or_stub(BOT_BLOCK_PAGE_BODY, _URL) is True


def test_cookie_error_title():
    flag, klass = detect_content_integrity_junk(
        "", _URL, title="Error - Cookies Turned Off"
    )
    assert (flag, klass) == (True, "cookie_error")


def test_not_found_title():
    flag, klass = detect_content_integrity_junk("", _URL, title="404: Not found")
    assert (flag, klass) == (True, "not_found")


def test_empty_title():
    flag, klass = detect_content_integrity_junk("", _URL, title="   ")
    assert (flag, klass) == (True, "empty")


def test_login_wall_title():
    flag, klass = detect_content_integrity_junk(
        "", _URL, title="Login | Transactions on Engineering"
    )
    assert (flag, klass) == (True, "login_wall")


def test_genuine_article_is_not_junk():
    flag, klass = detect_content_integrity_junk(GENUINE_BODY, _URL, title=GENUINE_TITLE)
    assert (flag, klass) == (False, "")


# --- Extra coverage (still only exercising the same detector) ----------------

def test_cookie_error_interstitial_body_flags_block_page():
    # A short cookie-error interstitial body trips the new visible rule, so the
    # body path (block_page) fires before the title path is even consulted.
    flag, klass = detect_content_integrity_junk(
        COOKIE_INTERSTITIAL_BODY, _URL, title="Error - Cookies Turned Off"
    )
    assert flag is True
    assert klass == "block_page"
    assert is_block_page_or_stub(COOKIE_INTERSTITIAL_BODY, _URL) is True


def test_nonarticle_stub_titles():
    for stub in ("fulltext01", "download_pub", "conference program", "book of abstracts"):
        flag, klass = detect_content_integrity_junk("", _URL, title=stub.upper())
        assert (flag, klass) == (True, "nonarticle_stub"), stub


def test_login_exact_title():
    flag, klass = detect_content_integrity_junk("", _URL, title="Login")
    assert (flag, klass) == (True, "login_wall")


def test_fail_open_on_non_string_title():
    # A non-string title would raise inside .strip()/.lower(); the FAIL-OPEN
    # wrapper must swallow it and return (False, "") — never flag a real source
    # as junk on an internal bug.
    flag, klass = detect_content_integrity_junk("", _URL, title=object())  # type: ignore[arg-type]
    assert (flag, klass) == (False, "")


if __name__ == "__main__":
    _tests = [
        test_bot_block_page_body_is_block_page,
        test_cookie_error_title,
        test_not_found_title,
        test_empty_title,
        test_login_wall_title,
        test_genuine_article_is_not_junk,
        test_cookie_error_interstitial_body_flags_block_page,
        test_nonarticle_stub_titles,
        test_login_exact_title,
        test_fail_open_on_non_string_title,
    ]
    _failures = 0
    for _t in _tests:
        try:
            _t()
            print(f"PASS  {_t.__name__}")
        except AssertionError as exc:  # noqa: PERF203
            _failures += 1
            print(f"FAIL  {_t.__name__}: {exc}")
    print(f"\n{len(_tests) - _failures}/{len(_tests)} passed")
    sys.exit(1 if _failures else 0)
