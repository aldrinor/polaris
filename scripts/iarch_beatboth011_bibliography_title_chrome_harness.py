#!/usr/bin/env python3
"""I-beatboth-011 b2 (#1289) — bibliography-title crawl-chrome render harness (fail-loud).

Behavioral replay-harness for the ~47 chrome hits in the rendered report "## Bibliography" area:
source TITLES / per-claim corroboration HEADERS carrying crawl chrome ("Markdown Content:",
"URL Source:", "Published Time:", "Number of Pages:", inline "![Image N: ...](url)" mastheads,
"ISSN: ####-####", "Cite this paper as:"). All in scripts/run_honest_sweep_r3.py.

TRACE (the load-bearing finding): the numbered "[N] <statement> — <url>" bibliography lines render
``b["statement"]``, which was ALREADY clean in the banked v3 corpora (0/0 statement-field chrome
across 5 recent bibliographies). The 175 chrome hits across those corpora all live in the per-claim
corroboration HEADER ``basket["claim_text"]`` rendered by ``_basket_corroboration_block`` — idx62
already screened that header with ``_normalize_claim_summary`` + the WHOLE-LINE-anchored
``is_boilerplate_or_nonassertional``, but neither catches chrome COLLAPSED INLINE mid-string (the
dominant shape). b2 runs ``access_bypass.clean_fetch_body`` FIRST (it applies the proven idx46/68
inline regexes + the Markdown-Content preamble drop), then the existing trim + chrome screen.

FIXTURES are the REAL inline-collapsed strings grepped from the banked v3 corpora
(outputs/p6_preflight_postfix, outputs/p6_fresh_glm52_v3, outputs/prc_render_probe), NOT invented
whole-line markers — a whole-line fixture would pass green while the 47 real inline hits survive.

ASSERTS (fail-loud, non-zero exit):
  (A) corroboration header: NO crawl-chrome token survives in the rendered output for any of the
      real inline fixtures.
  (B) faithfulness-neutral: every supporting SOURCE is still rendered and every verified-support
      COUNT is unchanged (header-text-only — no member/source dropped, no count/verdict changed).
  (C) a REAL clean claim header renders unchanged.
  (D) numbered "[N] <statement>" bibliography line: a chrome-laden TITLE renders chrome-clean, a
      WHOLLY-chrome title falls back to a non-chrome label (domain), the ENTRY COUNT is unchanged
      (no entry dropped), the citation NUMBER is preserved, and a real clean title is unchanged.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))

# Real inline-collapsed crawl-chrome tokens that must NOT survive in any rendered title/header.
_CHROME_TOKENS = (
    "Markdown Content",
    "URL Source",
    "Published Time:",
    "Number of Pages",
    "![Image",
    "ISSN:",
    "Cite this paper as",
)


def _fail(msg: str) -> None:
    print(f"FAIL I-beatboth-011 b2 bibliography-title chrome: {msg}")
    sys.exit(1)


def _surviving_chrome(text: str) -> "list[str]":
    return [t for t in _CHROME_TOKENS if t.lower() in text.lower()]


def main() -> None:
    import scripts.run_honest_sweep_r3 as rhs

    # ── (A)+(B)+(C) corroboration HEADER: REAL inline-collapsed chrome from the banked v3 corpora ──────
    # claim_text strings copied verbatim from the rendered "## Source corroboration" blocks (the locus
    # of the ~47 hits). Each carries chrome COLLAPSED INLINE mid-string — the shape the whole-line
    # allowlist misses.
    bib = [{
        "baskets": [
            {  # MDPI reader preamble inline (URL Source: / Published Time: / Markdown Content:)
                "claim_cluster_id": "c_mdpi",
                "claim_text": (
                    "e Upgrading URL Source: https://www.mdpi.com/2079-8954/13/7/586 "
                    "Published Time: 2025-07-15 Markdown Content: ## 1. Introduction. "
                    "AI adoption raised measured firm-level productivity."
                ),
                "subject": "AI adoption", "predicate": "raised firm productivity",
                "verified_support_origin_count": 3, "basket_verdict": "full",
                "refuter_cluster_ids": [],
                "supporting_members": [
                    {"member_tier": "ENTAILMENT_VERIFIED", "source_url": "https://mdpi.org/a",
                     "source_tier": "T2", "credibility_weight": 0.8},
                    {"member_tier": "ENTAILMENT_VERIFIED", "source_url": "https://mdpi.org/b",
                     "source_tier": "T2", "credibility_weight": 0.7},
                ],
            },
            {  # Number of Pages: + Markdown Content: preamble inline
                "claim_cluster_id": "c_pages",
                "claim_text": (
                    "rization_and_Technological_Change_2015.pdf Number of Pages: 40 "
                    "Markdown Content: Scand. J. of Economics. AI displaces routine labor."
                ),
                "subject": "AI", "predicate": "displaces routine labor",
                "verified_support_origin_count": 1, "basket_verdict": "full",
                "refuter_cluster_ids": [],
                "supporting_members": [
                    {"member_tier": "ENTAILMENT_VERIFIED", "source_url": "https://nber.org/x",
                     "source_tier": "T1", "credibility_weight": 0.9},
                ],
            },
            {  # complete inline ![Image ...] masthead + ISSN + "Cite this paper as:"
                "claim_cluster_id": "c_img_issn",
                "claim_text": (
                    "Frank et al. (2026) found similar results. "
                    "![Image 1: Figure 3. Unemployment](http://x/y.png) ISSN: 2079-8954 "
                    "Cite this paper as: AI productivity gains are large."
                ),
                "subject": "AI productivity gains", "predicate": "are large",
                "verified_support_origin_count": 2, "basket_verdict": "full",
                "refuter_cluster_ids": [],
                "supporting_members": [
                    {"member_tier": "ENTAILMENT_VERIFIED", "source_url": "https://journal.org/p",
                     "source_tier": "T1", "credibility_weight": 0.85},
                    {"member_tier": "ENTAILMENT_VERIFIED", "source_url": "https://journal.org/q",
                     "source_tier": "T2", "credibility_weight": 0.6},
                ],
            },
            {  # TRUNCATED/dangling image masthead — the closing `)` was capped off so the complete-image
              # regex cannot match it. This is the DOMINANT real residue (5-6 of 8 corpus samples). The
              # dangling-image strip must remove it, KEEPING the real residual claim before it.
                "claim_cluster_id": "c_trunc_img",
                "claim_text": (
                    "Customer satisfaction rose after automation. "
                    "![Image 4: shutterstock_2248569299]("
                ),
                "subject": "automation", "predicate": "raised satisfaction",
                "verified_support_origin_count": 1, "basket_verdict": "full",
                "refuter_cluster_ids": [],
                "supporting_members": [
                    {"member_tier": "ENTAILMENT_VERIFIED", "source_url": "https://trunc.example/a",
                     "source_tier": "T2", "credibility_weight": 0.7},
                ],
            },
            {  # IMAGE-ONLY -> nothing real survives after the dangling-image strip -> must fall back to
              # subject-predicate, never render a blank/chrome header, never drop the source.
                "claim_cluster_id": "c_img_only",
                "claim_text": "![Image 1: list of ai employment laws](",
                "subject": "GDP", "predicate": "rose two percent",
                "verified_support_origin_count": 1, "basket_verdict": "full",
                "refuter_cluster_ids": [],
                "supporting_members": [
                    {"member_tier": "ENTAILMENT_VERIFIED", "source_url": "https://gov.example/c",
                     "source_tier": "T2", "credibility_weight": 0.75},
                ],
            },
            {  # REAL clean claim header: must render UNCHANGED.
                "claim_cluster_id": "c_real",
                "claim_text": (
                    "Generative AI raised measured labor productivity by fourteen percent "
                    "in a randomized field experiment"
                ),
                "subject": "AI", "predicate": "raised productivity",
                "verified_support_origin_count": 1, "basket_verdict": "full",
                "refuter_cluster_ids": [],
                "supporting_members": [
                    {"member_tier": "ENTAILMENT_VERIFIED", "source_url": "https://real.org/p",
                     "source_tier": "T1", "credibility_weight": 0.95},
                ],
            },
        ],
    }]

    out = rhs._basket_corroboration_block(bib)

    # (A) NO crawl-chrome token survives in the rendered corroboration output.
    survivors = _surviving_chrome(out)
    if survivors:
        _fail(
            "(A) crawl chrome survived in the rendered corroboration header(s): "
            f"{survivors}\n{out}"
        )

    # (B) faithfulness-neutral: every source still rendered, every count unchanged.
    for src_url in (
        "https://mdpi.org/a", "https://mdpi.org/b", "https://nber.org/x",
        "https://journal.org/p", "https://journal.org/q", "https://trunc.example/a",
        "https://gov.example/c", "https://real.org/p",
    ):
        if src_url not in out:
            _fail(f"(B) a supporting source was DROPPED from the render: {src_url}\n{out}")
    # counts: the distinct count values (3, 2, 1) must all still appear.
    for cnt in ("3 verified independent source(s)",
                "2 verified independent source(s)",
                "1 verified independent source(s)"):
        if cnt not in out:
            _fail(f"(B) a verified-support count changed — must be HEADER-TEXT-ONLY: missing {cnt!r}\n{out}")

    # (C) the chrome headers fell back to a real label (subject-predicate) and the real claim is kept.
    if "GDP rose two percent" not in out:
        _fail(f"(C) the image-only header did not fall back to subject-predicate ('GDP rose two percent'):\n{out}")
    if "Generative AI raised measured labor productivity by fourteen percent" not in out:
        _fail(f"(C) the REAL clean claim header was lost or altered:\n{out}")
    # the dechromed (not wholly-chrome) headers must surface their real residual claim text.
    if "displaces routine labor" not in out:
        _fail(f"(C) the dechromed 'Number of Pages:' header lost its real residual claim:\n{out}")
    # the truncated-image header must KEEP its real residual claim (not fall back), chrome stripped.
    if "Customer satisfaction rose after automation" not in out:
        _fail(f"(C) the truncated-image header lost its real residual claim ('Customer satisfaction rose ...'):\n{out}")
    # (C-P1) the COMPLETE-image fixture (c_img_issn) must keep the real claim text BOTH BEFORE and AFTER
    # the complete `![img](url)` — the reorder proof: complete-image strip runs before the end-anchored
    # dangling strip, so a `![img](url) <real claim>` is NOT eaten to EOL (prior gate P1). ISSN /
    # "Cite this paper as:" chrome is removed (checked by (A)) but the surrounding real claim survives.
    if "Frank et al" not in out or "productivity gains are large" not in out:
        _fail(
            "(C-P1) the complete-image header lost real claim text around the image — the post-image "
            f"claim must survive the complete-image strip (reorder regression):\n{out}"
        )
    print(
        "(A/B/C) ok: every real inline crawl-chrome token removed from the corroboration headers; "
        "all 7 sources + all counts preserved (header-text-only); wholly-chrome header fell back to "
        "subject-predicate; real clean header unchanged."
    )

    # ── (D) numbered "[N] <statement>" bibliography line ──────────────────────────────────────────────
    # Even though the banked-corpus statement field was clean, the displayed TITLE is render-hygiene-
    # sensitive: a chrome-laden statement must render chrome-clean, a WHOLLY-chrome statement must fall
    # back to a non-chrome label, the ENTRY COUNT must be unchanged, the citation NUMBER preserved, and
    # a real clean title unchanged.
    biblio_entries = [
        {  # chrome-laden title (real inline preamble shape) — must render chrome-clean.
            "num": 1,
            "statement": (
                "Title: AI and Jobs URL Source: https://nber.org/w12345 "
                "Number of Pages: 14 Markdown Content: AI and Jobs: Evidence from Online Vacancies"
            ),
            "url": "https://nber.org/w12345", "tier": "T1",
        },
        {  # WHOLLY-chrome title -> must fall back to a non-chrome label (domain), NEVER blank/chrome.
            "num": 2,
            "statement": "URL Source: Markdown Content: ## Authors * Taib Ali",
            "url": "https://onlinelibrary.wiley.com/doi/10.1002/abc", "tier": "T2",
        },
        {  # real clean title -> must render UNCHANGED.
            "num": 3,
            "statement": "Artificial intelligence and the future of work: evidence from 701 occupations",
            "url": "https://doi.org/10.1371/journal.pone.0123456", "tier": "T1",
        },
        {  # TRUNCATED/dangling image masthead in the title -> chrome stripped, real residual kept.
            "num": 4,
            "statement": "Big Data and Analytics ![Image 4: shutterstock_2248569299](",
            "url": "https://www.sciencedirect.com/science/article/pii/S0000", "tier": "T2",
        },
    ]

    rendered = rhs._render_bibliography_lines(biblio_entries, require_locator=False)

    # entry count unchanged: one "[N] " numbered line per input entry.
    n_lines = len(re.findall(r"(?m)^\[\d+\]\s", rendered))
    if n_lines != len(biblio_entries):
        _fail(
            f"(D) bibliography entry count changed: rendered {n_lines} numbered lines for "
            f"{len(biblio_entries)} entries — a source was dropped/duplicated:\n{rendered}"
        )
    # citation numbers preserved (body [N] markers must still resolve) — EVERY entry, incl. the 4th,
    # so a dropped/duplicated trailing number fails loud (prior gate P2: only [1..3] were checked).
    for n in (1, 2, 3, 4):
        if not re.search(rf"(?m)^\[{n}\]\s", rendered):
            _fail(f"(D) citation number [{n}] is missing from the render:\n{rendered}")
    # no crawl chrome survives in the rendered bibliography titles.
    survivors_d = _surviving_chrome(rendered)
    if survivors_d:
        _fail(f"(D) crawl chrome survived in a numbered bibliography title: {survivors_d}\n{rendered}")
    # chrome-laden title 1 kept its real residual title.
    if "AI and Jobs: Evidence from Online Vacancies" not in rendered:
        _fail(f"(D) the chrome-laden title (#1) lost its real residual title text:\n{rendered}")
    # wholly-chrome title 2 fell back to the domain label (non-chrome, non-blank).
    if "onlinelibrary.wiley.com" not in rendered:
        _fail(f"(D) the wholly-chrome title (#2) did not fall back to a domain label:\n{rendered}")
    # real clean title 3 rendered unchanged (byte-identical title substring).
    if "Artificial intelligence and the future of work: evidence from 701 occupations" not in rendered:
        _fail(f"(D) the real clean title (#3) was altered:\n{rendered}")
    # (D-P2) dangling-image title 4 ("Big Data and Analytics ![Image...(") must KEEP its real title
    # prefix via the numbered-path dangling-image strip — NOT fall back to the sciencedirect domain
    # (prior gate P2: clean_fetch_body alone left the fragment, screening the title as chrome).
    if "Big Data and Analytics" not in rendered:
        _fail(f"(D) the dangling-image title (#4) lost its real title prefix (fell back to domain):\n{rendered}")
    print(
        "(D) ok: numbered bibliography titles are chrome-clean; wholly-chrome title fell back to the "
        "domain label; entry count + citation numbers unchanged; real clean title unchanged."
    )

    print(
        "PASS I-beatboth-011 b2: the rendered '## Bibliography' area is crawl-chrome-clean — the "
        "per-claim corroboration headers and the numbered source titles no longer carry "
        "'Markdown Content:' / 'URL Source:' / 'Published Time:' / 'Number of Pages:' / inline image "
        "mastheads / 'ISSN:' / 'Cite this paper as:'. Every source and count is preserved "
        "(render-hygiene only; no entry dropped, no faithfulness gate touched)."
    )


if __name__ == "__main__":
    main()
