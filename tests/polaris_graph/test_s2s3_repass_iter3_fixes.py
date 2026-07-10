"""S2/S3 re-pass iter-3: _body_is_chrome_dominant garble / nav-shell / link-dump guards.

These three additive branches stop chrome / garbled-byte-stream / fetch-nav-shell rows that
survived S2 from SEEDING or JOINING a qualitative corroboration basket (the false corrob=10 /
corrob=7 / corrob=11 baskets seen on the drb_72 AI-labor cp3). The guard excludes from
CLUSTERING only — it never drops the row — so a real prose source (even off-topic) is untouched.
"""
from __future__ import annotations

from src.polaris_graph.synthesis.finding_dedup import _body_is_chrome_dominant


def test_garbled_byte_stream_body_is_chrome_dominant():
    # A mangled PDF / flate stream rendered as text whose %pdf/endobj markers were lost:
    # almost no word-like tokens, low alphabetic fraction, >= 20 whitespace tokens.
    garble = (
        "f5 0ndaI~9 FYb A2Qd 9JF* L3H >:% 2 Z~q K!l `J&\"~ 1 w1 H3?[ hF1>K,iA4mB6uHk(U "
        "QO;M^$Rt.UE29 #w?.AF }OMJZ9 9P>I[ Vt;4f ,4j $LN`wx*v Xdxy%ej >:p /8A kN Vp>e@/ "
        "0sDsvzP1pqhO ? , Dz&4ah P9( r6m5 ! -_W=^V3bR Brg=x6l]+FJ+ kM*=B8o(v#d Ss"
    )
    assert _body_is_chrome_dominant(garble) is True


def test_fetch_navigation_shell_is_chrome_dominant():
    shell = (
        "Navigated to Research: How Gen AI Is Already Impacting the Labor Market | "
        "Harvard Business Impact Education page (https://hbsp.harvard.edu/product/H08G0M-PDF-ENG)"
    )
    assert _body_is_chrome_dominant(shell) is True


def test_markdown_link_nav_dump_is_chrome_dominant():
    # A site-menu / tab-bar nav dump: most chars are inside links, few prose words per link.
    nav = " ".join(
        f"* [{label}](https://www.bls.gov/ooh/x.htm#tab-{i})"
        for i, label in enumerate(
            ["Summary", "What They Do", "Work Environment", "How to Become One",
             "Pay", "Job Outlook", "State Area Data", "Similar Occupations", "More Info"]
        )
    )
    assert _body_is_chrome_dominant(nav) is True


def test_real_prose_claim_is_not_chrome_dominant():
    prose = (
        "We investigate the potential implications of large language models on the US labor "
        "market. Our findings indicate that around 80 percent of the US workforce could have "
        "at least ten percent of their work tasks affected by the introduction of LLMs, while "
        "roughly nineteen percent of workers may see at least half of their tasks impacted. "
        "The influence spans all wage levels, with higher-income jobs potentially facing "
        "greater exposure. These effects are not confined to industries with recent "
        "productivity growth."
    )
    assert _body_is_chrome_dominant(prose) is False


def test_real_off_topic_prose_is_not_chrome_dominant():
    # Off-topic is NOT the chrome guard's job: a real off-topic paper stays clusterable prose.
    off_topic = (
        "Regona, Massimo and Yigitcanlar, Tan and Xia, Bo and Li, R.Y.M. (2022). Opportunities "
        "and adoption challenges of AI in the construction industry: a PRISMA review. The study "
        "examines how construction firms perceive digital technologies and identifies barriers "
        "to adoption across project delivery, safety management, and workforce training."
    )
    assert _body_is_chrome_dominant(off_topic) is False


def test_empty_body_fail_open():
    assert _body_is_chrome_dominant("") is False
