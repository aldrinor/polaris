#!/usr/bin/env python3
"""I-beatboth-011 b1 (#1289) — fail-loud harness for the Wiley login-nav + image-URL masthead chrome screen.

THE DEFECT (real, banked): the free-fetch readers leaked a publisher LOGIN-NAV run and IMAGE-URL MASTHEAD
into the answer BODY / Key-Findings. The banked v3 ``drb_72`` ``report.md`` carried, cited as a "verified
independent source", the literal run::

    library.wiley.com/pb-assets/hub-assets/pericles/logo-header-1690978619437.png) ## Change Password
    Old Password New Password Too Short.[13]...

plus ``![Image N: ...](blob:http://localhost/...)`` markdown images and ``/pb-assets/.../...pdf`` asset
URLs. The pre-existing screens (idx46/idx68 Scribd/FB/YouTube/ISSN) did NOT cover these classes.

THE FIX (input/render hygiene — faithfulness-safe, §-1.3 never drops a real claim): extend
``access_bypass._WEB_BOILERPLATE_LINE_RE`` (whole-line) + ``_INLINE_SOCIAL_CHROME_RE`` (inline, the form
these collapse to in the cited body) + ``weighted_enrichment._WEB_CHROME_MARKERS`` with HIGH-PRECISION,
MULTI-TOKEN / STRUCTURE-anchored patterns:
  (1) Wiley/publisher login-nav run "Change Password ... Old Password ... New Password" (3-token sequence);
  (2) image-URL masthead — ``![Image`` markdown images, ``/pb-assets/`` asset URLs, ``logo-header-<digits>
      .png)`` mastheads, and ``favicon.<ext>`` image files.

§-1.4 BEHAVIORAL ACCEPTANCE (non-zero exit on regression). This harness asserts:
  (A) STRIP/FLAG — the new chrome classes are removed by ``clean_fetch_body`` and the chrome-only unit is
      flagged by ``is_boilerplate_or_nonassertional``; the breadth-section screen ``_is_web_chrome`` also
      catches them.
  (B) PRECISION — real assertional prose carrying "password" / "image" / "change" / "logo" / "favicon"
      MID-SENTENCE is KEPT byte-for-byte: NOT stripped by ``clean_fetch_body``, NOT flagged by
      ``is_boilerplate_or_nonassertional``, NOT screened by ``_is_web_chrome``.

Run:  python scripts/iarch_beatboth011_wiley_imageurl_chrome_harness.py
"""
from __future__ import annotations

import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))


def _fail(msg: str) -> None:
    print(f"FAIL I-beatboth-011 b1 (Wiley/image-URL chrome): {msg}")
    sys.exit(1)


# --- Real leaked chrome (verbatim from the banked drb_72 report.md / corpus_snapshot) -----------------
# The exact masthead+login-nav run that leaked into the answer BODY, cited as a "verified source":
_LEAKED_MASTHEAD_NAV = (
    "library.wiley.com/pb-assets/hub-assets/pericles/logo-header-1690978619437.png) "
    "## Change Password Old Password New Password Too Short Weak Medium Strong Very Strong Too Long"
)
# Whole-unit chrome classes (each is essentially ONLY chrome → must be flagged non-assertional):
_CHROME_UNITS = [
    "Change Password Old Password New Password Too Short Weak Medium Strong Very Strong Too Long",
    "![Image 26: logo](blob:http://localhost/28fdf82b0ea1d030de7497b82108f166)",
    "![Image 1: Utrecht University Logo](https://www.uu.nl/assets/logo.png)",
]
# Inline-collapsed chrome fragments that must be REDUCED out of a mixed body:
_INLINE_CHROME = [
    "/pb-assets/assets/9781118989463/Editor_Contributors-1503415962000.pdf",
    "logo-header-1690978619437.png)",
    "logo-header.png)](https://burjcdigital.urjc.es/home)",
    "https://www.example.org/static/favicon-32x32.png",
]

# --- Real assertional prose carrying the trigger words MID-SENTENCE (PRECISION — must be KEPT) ---------
_REAL_PROSE = [
    "Users were prompted to change their password every ninety days, which reduced account breaches.",
    "The image of automation in manufacturing has changed considerably since 2015 across the sector.",
    "Change management practices improved adoption of the new logo across the firm's twelve offices.",
    "Old password policies were replaced; the new password requirements measurably raised entropy.",
    "The favicon image loaded fine, and the change to the company logo did not affect login throughput.",
    "Generative AI raised measured customer-support productivity by fourteen percent in the trial.",
]


def main() -> None:
    from src.tools.access_bypass import (
        clean_fetch_body,
        is_boilerplate_or_nonassertional,
    )
    from src.polaris_graph.generator.weighted_enrichment import _is_web_chrome

    # (A) STRIP/FLAG -----------------------------------------------------------------------------------

    # (A1) The literal leaked masthead+login-nav run: after clean_fetch_body the chrome tokens are gone.
    cleaned = clean_fetch_body(_LEAKED_MASTHEAD_NAV).cleaned_text
    low = cleaned.lower()
    # the masthead URL + 3-token login-nav AND the trailing password-strength meter must ALL be gone —
    # not just the login-nav (prior gate P1: the meter tail "Too Short Weak Medium Strong ..." survived).
    for bad in (
        "logo-header", "/pb-assets/", "wiley.com",
        "change password old password new password",
        "too short", "very strong", "medium strong",
    ):
        if bad in low:
            _fail(f"(A1) chrome token {bad!r} survived clean_fetch_body: cleaned={cleaned!r}")
    # and the residual must carry NO assertional content (empty / pure markdown punctuation / flagged
    # non-assertional) — a chrome-only unit must never leave a citable remainder.
    residual = cleaned.strip().lstrip("#").strip()
    if residual and not is_boilerplate_or_nonassertional(cleaned):
        _fail(f"(A1) chrome-only unit left a non-empty assertional residual: {cleaned!r}")
    print("(A1) ok: leaked Wiley masthead+login-nav run + password-strength meter tail fully stripped; "
          "no assertional residual.")

    # (A2) Each whole-unit chrome class is flagged non-assertional (so the evidence path routes it to the
    #      existing fetch-shell / gap branch — NOT surfaced as a finding).
    for unit in _CHROME_UNITS:
        cf = clean_fetch_body(unit)
        chrome_gone = not cf.cleaned_text.strip() or is_boilerplate_or_nonassertional(cf.cleaned_text)
        flagged_raw = is_boilerplate_or_nonassertional(unit)
        if not (chrome_gone or flagged_raw):
            _fail(
                f"(A2) chrome unit NOT stripped/flagged: unit={unit!r} "
                f"cleaned={cf.cleaned_text!r} shell_reason={cf.shell_reason!r}"
            )
    print("(A2) ok: every whole-unit chrome class stripped-to-empty or flagged non-assertional.")

    # (A3) Inline-collapsed chrome fragments embedded in a MIXED body are reduced out, real prose kept.
    real_tail = "Robots raised manufacturing output by twelve percent in the surveyed plants."
    for frag in _INLINE_CHROME:
        mixed = f"{frag} {real_tail}"
        cleaned = clean_fetch_body(mixed).cleaned_text
        low = cleaned.lower()
        for bad in ("logo-header", "/pb-assets/", "favicon-32x32.png"):
            if bad in low:
                _fail(f"(A3) inline chrome {bad!r} survived in mixed body: {cleaned!r}")
        if "raised manufacturing output by twelve percent" not in cleaned:
            _fail(f"(A3) the real claim was wrongly dropped from the mixed body: {cleaned!r}")
    print("(A3) ok: inline masthead/asset/favicon chrome reduced; real claim in the same body preserved.")

    # (A4) The breadth-section sentence-form screen also catches the login-nav run + masthead tokens.
    for chrome in (
        "Change Password Old Password New Password Too Short Weak Medium Strong",
        "https://library.wiley.com/pb-assets/hub-assets/pericles/logo-header-1690978619437.png)",
        "![Image 26: logo](blob:http://localhost/abc)",
        "https://www.example.org/static/favicon-32x32.png",   # favicon.<ext> via the production-path screen
        "https://cdn.example.com/favicon.ico",                # bare favicon.ico asset
    ):
        if not _is_web_chrome(chrome):
            _fail(f"(A4) weighted_enrichment._is_web_chrome did NOT flag chrome: {chrome!r}")
    print("(A4) ok: weighted_enrichment._is_web_chrome flags the login-nav run + masthead/image/favicon chrome.")

    # (B) PRECISION — real prose with trigger words mid-sentence is KEPT everywhere -----------------------
    for prose in _REAL_PROSE:
        cf = clean_fetch_body(prose)
        if cf.cleaned_text != prose:
            _fail(f"(B) clean_fetch_body altered real prose (precision break): "
                  f"in={prose!r} out={cf.cleaned_text!r}")
        if cf.shell_reason is not None:
            _fail(f"(B) clean_fetch_body flagged real prose as a shell: {prose!r} -> {cf.shell_reason!r}")
        if is_boilerplate_or_nonassertional(prose):
            _fail(f"(B) is_boilerplate_or_nonassertional WRONGLY flagged real prose: {prose!r}")
        if _is_web_chrome(prose):
            _fail(f"(B) weighted_enrichment._is_web_chrome WRONGLY flagged real prose: {prose!r}")
    print("(B) ok: real prose carrying password/image/change/logo/favicon mid-sentence is KEPT untouched.")

    print(
        "PASS I-beatboth-011 b1: the Wiley login-nav run + image-URL masthead chrome "
        "(![Image, /pb-assets/, logo-header-<digits>.png, favicon) are stripped by clean_fetch_body / "
        "flagged non-assertional / screened by _is_web_chrome (A), and real prose carrying the trigger "
        "words mid-sentence is preserved byte-for-byte (B). Faithfulness engine untouched; input-hygiene only."
    )


if __name__ == "__main__":
    main()
