"""Deterministic offline tests for the Layer-A block-page / stub detector.

D (I-extract-001 #1327): `src/tools/access_bypass.py` block-page detector. Pure,
offline, no network / no models / no live calls — exercises the classifier on
real-shaped block-page samples (Cloudflare challenge, Akamai/edgesuite Access
Denied, Google reCAPTCHA, ScienceDirect publisher error card, redirect stub,
JS/CAPTCHA walls) plus real-content controls (a long article that QUOTES
"access denied" / "please enable javascript" in prose; a short real abstract;
a short snippet quoting one block phrase without the other). Also exercises the
behavioral canary (`detected` / `re_fetched`) and the flag-gated `AccessBypass`
screen methods (called with a dummy `self` so no heavy constructor / fetch runs).

Runnable as a plain script (`python tests/polaris_graph/test_block_page_detector.py`)
or under pytest. Standalone run prints per-case results and exits non-zero on any
failure.
"""

import os
import sys
from types import SimpleNamespace

sys.path.insert(
    0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
)

from src.tools.access_bypass import (  # noqa: E402
    AccessBypass,
    block_page_detector_enabled,
    classify_block_page,
    get_block_page_canary,
    is_block_page_or_stub,
    reset_block_page_canary,
)

_ENV = "PG_BLOCK_PAGE_DETECTOR"

# --- Block-page / stub samples (real-shaped; one per failure class) ----------

SAMPLE_CLOUDFLARE = (
    "<!DOCTYPE html><html lang='en-US'><head><title>Just a moment...</title>"
    "</head><body><div class='main-content'><noscript>"
    "<span>Enable JavaScript and cookies to continue</span></noscript></div>"
    "<script>window._cf_chl_opt = {cRay:'a122426bd8822c5d'};"
    "var a=document.createElement('script');"
    "a.src='/cdn-cgi/challenge-platform/h/b/orchestrate/chl_page/v1';</script>"
    "</body></html>"
)

# Akamai/edgesuite "Access Denied" — entity-encoded host (exercises html.unescape).
SAMPLE_AKAMAI = (
    "<HTML><HEAD>\n<TITLE>Access Denied</TITLE>\n</HEAD><BODY>\n"
    "<H1>Access Denied</H1>\n "
    "You don't have permission to access "
    '"http&#58;&#47;&#47;www&#46;weforum&#46;org&#47;about&#47;" on this server.<P>\n'
    "Reference&#32;&#35;18&#46;52680117\n"
    "<P>https&#58;&#47;&#47;errors&#46;edgesuite&#46;net&#47;18&#46;52680117</P>\n"
    "</BODY></HTML>"
)

SAMPLE_RECAPTCHA = (
    "<!doctype html><html lang='en-US'><head>"
    "<base href='https://www.google.com/recaptcha/challengepage/'>"
    "</head><body><script>window['ppConfig']="
    "{productName:'RecaptchaChallengePageUi'};</script></body></html>"
)

SAMPLE_SCIENCEDIRECT = (
    "<!DOCTYPE html><html lang='en-us'><head><title>ScienceDirect</title></head>"
    "<body><div class='error-card'><div class='card-content'>"
    "<h1 class='u-h2'>There was a problem providing the content you requested</h1>"
    "<p>Please contact Customer Service.</p></div></div></body></html>"
)

# Elsevier/ScienceDirect redirect stub: meta-refresh + only hidden inputs (no
# visible text). Note the article name lives INSIDE a <script> (stripped), so the
# detection must come from the meta-refresh + negligible-visible-text rule.
SAMPLE_REDIRECT_STUB = (
    "<!DOCTYPE HTML><html><head>\n<meta charset='utf-8'>\n"
    "<meta HTTP-EQUIV='REFRESH' content=\"2; url='/retrieve/articleSelectSinglePerm'\"/>\n"
    "<title>Redirecting</title>\n"
    "<script type='text/javascript'>var pageName='Auto Article Locator';</script>\n"
    "</head>\n<body onload='autoRedirectToURL();'>\n"
    "<input type='hidden' name='key' value='101946e7b7d836287b25ff09'/>\n"
    "<input type='hidden' name='id' value='S0278612523001656'/>\n"
    "</body></html>"
)

# JS wall with NO decisive raw marker — must be caught by the visible-text rule.
SAMPLE_JS_WALL = (
    "<html><head><title>Attention Required</title></head><body>"
    "<p>We are sorry. Enable JavaScript and cookies to continue.</p>"
    "</body></html>"
)

SAMPLE_CAPTCHA_WALL = (
    "<html><body><div>Please verify you are human before continuing.</div>"
    "</body></html>"
)

BLOCK_SAMPLES = {
    "cloudflare_challenge": SAMPLE_CLOUDFLARE,
    "akamai_access_denied": SAMPLE_AKAMAI,
    "recaptcha_challenge": SAMPLE_RECAPTCHA,
    "publisher_error_stub": SAMPLE_SCIENCEDIRECT,
    "redirect_stub": SAMPLE_REDIRECT_STUB,
    "javascript_wall": SAMPLE_JS_WALL,
    "captcha_wall": SAMPLE_CAPTCHA_WALL,
}

# --- Real-content controls (must NOT be flagged) ----------------------------

# Long real article that QUOTES the block phrases in prose. The PRECISION
# control: a real body that merely mentions "access denied" / "please enable
# javascript" must survive (visible body far exceeds the short-body gate).
_PARA = (
    "Automation and the future of work has been studied across OECD economies. "
    "Researchers note that when a server returns access denied the crawler must "
    "re-route, and that some sites instruct users to please enable javascript to "
    "view interactive figures. The productivity literature finds measurable "
    "gains from task substitution while displacement risk concentrates in "
    "routine occupations, a pattern documented by Morgan Stanley economists. "
)
CONTROL_LONG_ARTICLE = (
    "<html><body><article><p>" + (_PARA * 12) + "</p></article></body></html>"
)

CONTROL_SHORT_ABSTRACT = (
    "<html><body><p>This study examines automation and labor markets across OECD "
    "economies, finding measurable productivity gains and concentrated "
    "displacement risk in routine occupations.</p></body></html>"
)

# Short real snippet quoting ONE block phrase ("access denied") but NOT the
# paired phrase — proves the visible rule needs the PAIR, not a single word.
CONTROL_PARTIAL_PHRASE = (
    "<html><body><p>The memoir \"Access Denied\" discusses barriers to "
    "healthcare access for rural patients.</p></body></html>"
)

CONTROL_SAMPLES = {
    "long_article_quoting_block_phrases": CONTROL_LONG_ARTICLE,
    "short_real_abstract": CONTROL_SHORT_ABSTRACT,
    "short_quotes_one_phrase_only": CONTROL_PARTIAL_PHRASE,
    "empty_body": "",
}

_URL = "https://example.com/article"
_DUMMY_SELF = SimpleNamespace()


def _clean_result(method: str = "direct") -> SimpleNamespace:
    return SimpleNamespace(access_method=method, url=_URL, success=True, content="ok")


# --- Tests ------------------------------------------------------------------

def test_block_samples_classified():
    """Every block sample classifies to its expected failure class."""
    for expected_class, body in BLOCK_SAMPLES.items():
        got = classify_block_page(body, _URL)
        assert got == expected_class, f"{expected_class}: got {got!r}"
        assert is_block_page_or_stub(body, _URL) is True


def test_controls_not_flagged():
    """Real content (incl. one quoting block phrases) is NEVER flagged."""
    for name, body in CONTROL_SAMPLES.items():
        got = classify_block_page(body, _URL)
        assert got == "", f"{name}: false-positive {got!r}"
        assert is_block_page_or_stub(body, _URL) is False


def test_detector_default_off_is_noop():
    """With the flag unset/OFF, the AccessBypass screen is a pure no-op."""
    os.environ.pop(_ENV, None)
    reset_block_page_canary()
    assert block_page_detector_enabled() is False
    state = {"seen": False}
    flagged = AccessBypass._is_block_page(
        _DUMMY_SELF, _URL, SAMPLE_CLOUDFLARE, state
    )
    assert flagged is False
    assert state["seen"] is False
    assert get_block_page_canary() == {"detected": 0, "re_fetched": 0}


def test_canary_detects_and_recovers():
    """Flag ON: a detection bumps `detected`; a clean fetch after a detection
    bumps `re_fetched` (the successful re-fetch / recovery)."""
    os.environ[_ENV] = "1"
    try:
        reset_block_page_canary()
        assert block_page_detector_enabled() is True
        state = {"seen": False}
        # 1) direct backend returns a block page -> detected, seen.
        assert AccessBypass._is_block_page(
            _DUMMY_SELF, _URL, SAMPLE_CLOUDFLARE, state
        ) is True
        assert state["seen"] is True
        assert get_block_page_canary()["detected"] == 1
        assert get_block_page_canary()["re_fetched"] == 0
        # 2) a later backend returns CLEAN content for this URL -> re_fetched.
        AccessBypass._finalize_clean_fetch(_DUMMY_SELF, _clean_result(), state)
        assert get_block_page_canary()["re_fetched"] == 1
    finally:
        os.environ.pop(_ENV, None)


def test_canary_all_blocked_marks_failed():
    """Flag ON: a URL blocked on every backend (no clean finalize) keeps
    re_fetched < detected — the mark-failed case (drops at strict_verify)."""
    os.environ[_ENV] = "1"
    try:
        reset_block_page_canary()
        state = {"seen": False}
        assert AccessBypass._is_block_page(
            _DUMMY_SELF, _URL, SAMPLE_AKAMAI, state
        ) is True
        assert AccessBypass._is_block_page(
            _DUMMY_SELF, _URL, SAMPLE_RECAPTCHA, state
        ) is True
        canary = get_block_page_canary()
        assert canary["detected"] == 2
        assert canary["re_fetched"] == 0  # never recovered -> marked failed
    finally:
        os.environ.pop(_ENV, None)


def test_control_not_flagged_when_enabled():
    """Flag ON: a real article is not flagged and does not bump `detected`."""
    os.environ[_ENV] = "1"
    try:
        reset_block_page_canary()
        state = {"seen": False}
        assert AccessBypass._is_block_page(
            _DUMMY_SELF, _URL, CONTROL_LONG_ARTICLE, state
        ) is False
        assert state["seen"] is False
        assert get_block_page_canary()["detected"] == 0
    finally:
        os.environ.pop(_ENV, None)


_ALL_TESTS = [
    test_block_samples_classified,
    test_controls_not_flagged,
    test_detector_default_off_is_noop,
    test_canary_detects_and_recovers,
    test_canary_all_blocked_marks_failed,
    test_control_not_flagged_when_enabled,
]


def _main() -> int:
    failures = 0
    for fn in _ALL_TESTS:
        try:
            fn()
            print(f"[PASS] {fn.__name__}")
        except AssertionError as exc:
            failures += 1
            print(f"[FAIL] {fn.__name__}: {exc}")
        except Exception as exc:  # noqa: BLE001 — report, don't abort the suite
            failures += 1
            print(f"[ERROR] {fn.__name__}: {type(exc).__name__}: {exc}")
    # Show the per-class verdicts for human inspection.
    print("\n-- classify_block_page verdicts --")
    for expected, body in BLOCK_SAMPLES.items():
        print(f"  block   {expected:24s} -> {classify_block_page(body, _URL)!r}")
    for name, body in CONTROL_SAMPLES.items():
        print(f"  control {name:34s} -> {classify_block_page(body, _URL)!r}")
    print(f"\n{'ALL PASS' if failures == 0 else f'{failures} FAILURE(S)'}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(_main())
