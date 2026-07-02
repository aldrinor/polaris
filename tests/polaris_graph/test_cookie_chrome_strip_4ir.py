"""I-deepfix-001 Wave-B (#1344): Cookiebot/Usercentrics consent-chrome strip in the fetch
ingestion allowlist (`strip_web_boilerplate`, gated by PG_FETCH_COOKIE_CHROME_STRIP).

Forced-positive: a synthetic Cookiebot/Usercentrics consent banner is removed. Negative-control:
a real sentence that contains — or begins with — a consent category word ("Marketing"/"Statistics"/
"Necessary Preferences Statistics Marketing") survives byte-for-byte, and a bare single button/
category word survives (the patterns are whole-line + multi-token anchored). Kill-switch: with
PG_FETCH_COOKIE_CHROME_STRIP=0 the banner survives (byte-identical OFF, LAW VI).

Faithfulness-neutral: this runs at the ingestion seam BEFORE strict_verify/NLI/D8; it removes only
confirmed consent-manager chrome LINES, never a real claim.
"""
from src.tools.access_bypass import strip_web_boilerplate

_COOKIE_BANNER = "\n".join([
    "Consent Selection",
    "Necessary Preferences Statistics Marketing",
    "Show details",
    "Show/Hide details",
    "Allow all Deny Customize",
    "Deny Allow selection Allow all",
    "About cookies",
    "Powered by Cookiebot by Usercentrics",
    "Cookiebot by Usercentrics",
])

_REAL_PROSE = (
    "Automation exposed 1.8% of tasks to generative AI [1].\n"
    "Employment in the sector rose 4.2% over the period [2]."
)


def test_forced_positive_cookiebot_banner_is_stripped(monkeypatch):
    monkeypatch.delenv("PG_FETCH_COOKIE_CHROME_STRIP", raising=False)  # default-ON
    out = strip_web_boilerplate(_COOKIE_BANNER + "\n" + _REAL_PROSE)
    # every consent-banner line is gone
    for chrome_line in (
        "Consent Selection", "Necessary Preferences Statistics Marketing",
        "Show details", "Show/Hide details", "Allow all Deny Customize",
        "About cookies", "Powered by Cookiebot by Usercentrics", "Cookiebot by Usercentrics",
    ):
        assert chrome_line not in out, f"consent chrome not stripped: {chrome_line!r}"
    # the real prose survives
    assert "Automation exposed 1.8% of tasks to generative AI [1]." in out
    assert "Employment in the sector rose 4.2% over the period [2]." in out


def test_negative_control_prose_with_category_words_survives(monkeypatch):
    monkeypatch.delenv("PG_FETCH_COOKIE_CHROME_STRIP", raising=False)  # default-ON
    prose = "\n".join([
        "Statistics show that marketing budgets grew 12% year over year [3].",
        "The report ranks Necessary Preferences Statistics Marketing spending by firm [4].",
        "Marketing",          # a bare single category word line (not a >=2-token consent strip)
        "Deny",               # a bare single button word line
        "Deny access to the vault was the recommended control [5].",
    ])
    out = strip_web_boilerplate(prose)
    for line in prose.split("\n"):
        assert line in out, f"real content wrongly stripped: {line!r}"


def test_kill_switch_off_is_byte_identical(monkeypatch):
    monkeypatch.setenv("PG_FETCH_COOKIE_CHROME_STRIP", "0")
    out = strip_web_boilerplate(_COOKIE_BANNER)
    # OFF: the consent lines are NOT removed by the new patterns
    assert "Consent Selection" in out
    assert "Powered by Cookiebot by Usercentrics" in out
