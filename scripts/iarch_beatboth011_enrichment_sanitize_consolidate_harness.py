#!/usr/bin/env python3
"""I-beatboth-011 #4 + #7 (#1289) — behavioral replay harness for the weighted-
enrichment sanitize + same-work consolidate fix.

§-1.4 acceptance gate: this proves the EFFECT FIRES in the REAL output of the REAL
``build_verified_span_draft`` function (not a reimplementation, not a config check):

  (a) #4 RENDER SAFETY: a span carrying a literal NUL byte + a ~75K raw-metadata blob,
      after the real draft build, emits ZERO NUL/C0 control bytes and the oversized
      blob is screened/bounded out (never reaches the render).
  (b) #7 SAME-WORK CONSOLIDATION: 4 members that are the SAME WORK (same DOI,
      different URLs) collapse to ONE multi-citation unit-set that STILL retains all 4
      URLs as grounding corroborator markers (multi-URL corroboration, ONE source).
  (b2) #4 OVER-MERGE NEGATIVE CONTROL: two records with the SAME folded title but
      DIFFERENT year AND different first author (no DOI) are DIFFERENT works and must
      NOT consolidate — each surfaces as its OWN distinct single-marker unit.
  (c) #7 CAPTCHA DROP: a member whose fetched text is a CAPTCHA / security stub
      ("Just a moment... Performing security verification") is dropped entirely.

FAIL LOUD: sys.exit(1) with a diagnostic on ANY regression; sys.exit(0) only if all
three checks pass. No network, no LLM, no faithfulness-gate touch — pure offline replay.
"""

from __future__ import annotations

import os
import re
import sys

# Ensure repo root on path when run from anywhere.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _REPO_ROOT not in sys.path:
    sys.path.insert(0, _REPO_ROOT)

from src.polaris_graph.generator.weighted_enrichment import (  # noqa: E402
    build_verified_span_draft,
)

# Legacy [ev_id] marker form the production rewriter consumes (live_deepseek_generator.py:64).
_EV_MARKER_RE = re.compile(r"\[([A-Za-z_][A-Za-z0-9_]*)\]")

_FAILURES: list[str] = []


def _fail(check: str, msg: str) -> None:
    _FAILURES.append(f"[{check}] {msg}")


# A clean clinical claim sentence used as the shared verbatim quote for the same-work
# group. Long enough to clear _MIN_UNIT_CHARS (40) and short enough to clear the render
# char bound (default 600).
_CLEAN_SENTENCE = (
    "Automation displaced roughly 12 percent of routine clerical tasks across the "
    "surveyed labor markets between 2020 and 2024"
)


def _check_a_render_safety() -> None:
    """#4: NUL + 75K blob span must never reach the render."""
    blob = "x9 = sum over j of qj " * 4000  # ~88K chars of raw-extraction salad
    assert len(blob) > 75_000, "test blob must exceed 75K chars"
    # The clean sentence ITSELF carries an embedded NUL + C0/DEL bytes, so this check
    # exercises the control-byte STRIP on an IN-BOUND, surviving unit (not only the
    # char-bound drop of the blob) — the strip is independently load-bearing.
    clean_with_ctrl = (
        "Automation displaced roughly 12\x00 percent of routine\x01 clerical tasks "
        "across the surveyed\x7f labor markets between 2020 and 2024"
    )
    poisoned_quote = (
        f"{clean_with_ctrl}.\nKD = sum_j Rk \x00 wj(h) \x00 Rk equilibrium dump "
        f"{blob}\x01\x02end."
    )
    pool = {
        "ev_poison": {
            "evidence_id": "ev_poison",
            "direct_quote": poisoned_quote,
            "doi": "10.1234/poison",
            "title": "Equilibrium properties of automated labor markets",
            "source_url": "https://example.org/poison",
        },
    }
    draft = build_verified_span_draft(["ev_poison"], pool)

    if "\x00" in draft:
        _fail("a", "draft STILL contains a NUL byte (\\x00) — binary corruption not fixed")
    for cp in range(0x20):
        ch = chr(cp)
        if ch in ("\n", "\t"):
            continue
        if ch in draft:
            _fail("a", f"draft contains C0 control byte U+{cp:04X} — control bytes not stripped")
    if "\x7f" in draft:
        _fail("a", "draft contains DEL (0x7F) — control bytes not stripped")
    # The clean sentence (under the bound) SHOULD still surface; the blob must NOT.
    if "Automation displaced roughly 12 percent" not in draft:
        _fail("a", "the clean in-bound clinical sentence was lost (over-screening)")
    if "sum over j of qj" in draft or len(draft) > 5_000:
        _fail(
            "a",
            f"the oversized raw-extraction blob leaked into the render (draft_chars={len(draft)})",
        )


def _check_b_same_work_consolidation() -> None:
    """#7: 4 same-work members (same DOI, 4 URLs) collapse to ONE multi-citation unit."""
    quote = f"{_CLEAN_SENTENCE}."
    shared_doi = "10.1000/labor.2024.001"
    member_ids = ["ev_w1", "ev_w2", "ev_w3", "ev_w4"]
    urls = [
        "https://journal.example.org/full",
        "https://mirror.example.net/pdf",
        "https://repo.example.edu/preprint",
        "https://aggregator.example.com/view",
    ]
    pool = {
        eid: {
            "evidence_id": eid,
            # SAME verbatim quote on each fetch (multi-URL corroboration of one work).
            "direct_quote": quote,
            "doi": shared_doi,
            "title": "Automation and the clerical labor market",
            "source_url": url,
        }
        for eid, url in zip(member_ids, urls)
    }
    # Per-source budget of 1 so we deterministically get exactly one unit for the work.
    os.environ["PG_BREADTH_ENRICHMENT_SPANS_PER_SOURCE"] = "1"
    try:
        draft = build_verified_span_draft(member_ids, pool)
    finally:
        os.environ.pop("PG_BREADTH_ENRICHMENT_SPANS_PER_SOURCE", None)

    # The clean sentence must appear exactly ONCE (consolidated to one unit), not 4x.
    occurrences = draft.count("Automation displaced roughly 12 percent")
    if occurrences != 1:
        _fail(
            "b",
            f"same-work members did NOT consolidate to ONE unit "
            f"(clean sentence appears {occurrences}x, expected 1)",
        )
    # All 4 URLs are retained as grounding corroborator markers on the one unit.
    markers = _EV_MARKER_RE.findall(draft)
    missing = [m for m in member_ids if m not in markers]
    if missing:
        _fail(
            "b",
            f"consolidated unit dropped corroborator URL(s) {missing} "
            f"(markers found={markers}) — must KEEP ALL same-work URLs",
        )
    if len(markers) != 4:
        _fail(
            "b",
            f"expected exactly 4 co-citation markers on the one work, got {len(markers)}: {markers}",
        )


def _check_b2_over_merge_negative_control() -> None:
    """#4 OVER-MERGE NEGATIVE CONTROL (#1289): two records with the SAME folded title
    but DIFFERENT year AND different first author (no DOI) are DIFFERENT works and must
    NOT consolidate — title-alone never merges (§-1.3: under-merge safe, over-merge
    corrupts attribution). Each must surface as its OWN unit with its OWN single marker.
    """
    # Two distinct works sharing a generic title; distinct year + author, no DOI.
    sentence_one = (
        "Deep learning models reached 94 percent accuracy on the held-out vision "
        "benchmark in the first reported evaluation"
    )
    sentence_two = (
        "Transformer architectures reached 97 percent accuracy on the held-out vision "
        "benchmark in the later reported evaluation"
    )
    pool = {
        "ev_d1": {
            "evidence_id": "ev_d1",
            "direct_quote": f"{sentence_one}.",
            "title": "Deep Learning Methods for Computer Vision",
            "year": 2019,
            "authors": ["Smith J", "Lee K"],
            "source_url": "https://venue-a.org/dl",
        },
        "ev_d2": {
            "evidence_id": "ev_d2",
            "direct_quote": f"{sentence_two}.",
            "title": "deep learning methods for computer vision",
            "year": 2023,
            "authors": ["Garcia R", "Patel S"],
            "source_url": "https://venue-b.net/dl",
        },
    }
    os.environ["PG_BREADTH_ENRICHMENT_SPANS_PER_SOURCE"] = "1"
    try:
        draft = build_verified_span_draft(["ev_d1", "ev_d2"], pool)
    finally:
        os.environ.pop("PG_BREADTH_ENRICHMENT_SPANS_PER_SOURCE", None)

    markers = _EV_MARKER_RE.findall(draft)
    # Both works must surface as DISTINCT units, each carrying ONLY its own marker.
    if "ev_d1" not in markers or "ev_d2" not in markers:
        _fail(
            "b2",
            f"a distinct same-title work was lost — both ev_d1 AND ev_d2 must surface "
            f"(markers found={markers})",
        )
    # NOT consolidated => they are NOT co-cited on one unit. Each unit's own marker
    # appears exactly once, and the two distinct sentences both render.
    if markers.count("ev_d1") != 1 or markers.count("ev_d2") != 1:
        _fail(
            "b2",
            f"same-title-different-discriminator works were WRONGLY co-cited / merged "
            f"(markers={markers}); they must stay TWO distinct single-marker units",
        )
    if "Deep learning models reached 94 percent" not in draft or \
            "Transformer architectures reached 97 percent" not in draft:
        _fail("b2", "a distinct work's own sentence was dropped (over-merge collapsed it)")


def _check_b3_weak_signal_over_merge_negatives() -> None:
    """#4 P2 over-merge negatives (#1289): a SINGLE weak shared signal must NOT merge
    two distinct same-title works.

    (a) SAME title + SAME year + DIFFERENT first-author surname, no DOI -> the year
        agrees but the author disagrees, so the strong-path token differs -> NOT merged.
        (The OLD first-available rule keyed on year FIRST and would have wrongly merged.)
    (b) SAME title + SAME host + DIFFERENT year, no DOI, no strong signal -> the two
        weak signals do NOT both agree (year differs), so NOT merged. (host alone is
        never enough; year alone is never enough.)
    """
    # (a) same title + same year (2020) + DIFFERENT author surname.
    sent_a1 = (
        "Robotic process automation cut routine ledger postings by 31 percent in the "
        "first audited rollout across the surveyed firms"
    )
    sent_a2 = (
        "Robotic process automation cut routine ledger postings by 18 percent in the "
        "second audited rollout across the surveyed firms"
    )
    pool_a = {
        "ev_y1": {
            "evidence_id": "ev_y1",
            "direct_quote": f"{sent_a1}.",
            "title": "Robotic Process Automation in Financial Operations",
            "year": 2020,
            "authors": ["Nguyen T", "Park J"],
            "source_url": "https://venue-x.org/rpa",
        },
        "ev_y2": {
            "evidence_id": "ev_y2",
            "direct_quote": f"{sent_a2}.",
            "title": "robotic process automation in financial operations",
            "year": 2020,
            "authors": ["Ibrahim A", "Costa L"],
            "source_url": "https://venue-y.net/rpa",
        },
    }
    os.environ["PG_BREADTH_ENRICHMENT_SPANS_PER_SOURCE"] = "1"
    try:
        draft_a = build_verified_span_draft(["ev_y1", "ev_y2"], pool_a)
    finally:
        os.environ.pop("PG_BREADTH_ENRICHMENT_SPANS_PER_SOURCE", None)
    markers_a = _EV_MARKER_RE.findall(draft_a)
    if markers_a.count("ev_y1") != 1 or markers_a.count("ev_y2") != 1:
        _fail(
            "b3a",
            f"same title + same year + DIFFERENT author was WRONGLY merged/co-cited "
            f"(markers={markers_a}); a single matching weak signal (year) must NOT merge "
            f"two distinct works",
        )
    if "31 percent" not in draft_a or "18 percent" not in draft_a:
        _fail("b3a", "a distinct same-title work's own sentence was dropped (over-merge)")

    # (b) same title + same host + DIFFERENT year, no strong signal.
    sent_b1 = (
        "Clerical employment in the region contracted by 9 percent during the earlier "
        "measurement window of the longitudinal study"
    )
    sent_b2 = (
        "Clerical employment in the region contracted by 14 percent during the later "
        "measurement window of the longitudinal study"
    )
    pool_b = {
        "ev_h1": {
            "evidence_id": "ev_h1",
            "direct_quote": f"{sent_b1}.",
            "title": "Clerical Employment Trends in the Mountain Region",
            "year": 2018,
            "source_url": "https://shared-host.example.org/clerical-2018",
        },
        "ev_h2": {
            "evidence_id": "ev_h2",
            "direct_quote": f"{sent_b2}.",
            "title": "clerical employment trends in the mountain region",
            "year": 2022,
            "source_url": "https://shared-host.example.org/clerical-2022",
        },
    }
    os.environ["PG_BREADTH_ENRICHMENT_SPANS_PER_SOURCE"] = "1"
    try:
        draft_b = build_verified_span_draft(["ev_h1", "ev_h2"], pool_b)
    finally:
        os.environ.pop("PG_BREADTH_ENRICHMENT_SPANS_PER_SOURCE", None)
    markers_b = _EV_MARKER_RE.findall(draft_b)
    if markers_b.count("ev_h1") != 1 or markers_b.count("ev_h2") != 1:
        _fail(
            "b3b",
            f"same title + same host + DIFFERENT year was WRONGLY merged/co-cited "
            f"(markers={markers_b}); host alone is never a merge key and year differs",
        )
    if "9 percent" not in draft_b or "14 percent" not in draft_b:
        _fail("b3b", "a distinct same-title work's own sentence was dropped (over-merge)")


def _check_c_captcha_stub_dropped() -> None:
    """#7: a CAPTCHA / security-stub member is dropped; a clean member survives.

    I-beatboth-011 #7 P1 (#1289): the drop requires the trigger phrase "just a moment"
    AND a strong WAF/security co-token. A bare "just a moment" in otherwise-substantive
    prose must NOT be dropped (§-1.3 keep-all).

    POSITIVE: "Just a moment... Performing security verification... Cloudflare Ray ID"
    carries trigger + co-tokens => DROPPED.
    NEGATIVE CONTROL: "Just a moment, the unemployment rate fell to 3.5% in 2023 according
    to BLS" carries the bare trigger but NO security co-token => real prose => KEPT.
    """
    bare_sentence = (
        "Just a moment, the unemployment rate fell to 3.5 percent in 2023 according to "
        "the Bureau of Labor Statistics surveyed establishment data"
    )
    pool = {
        "ev_captcha": {
            "evidence_id": "ev_captcha",
            "direct_quote": (
                "Just a moment... www.example.org needs to review the security of your "
                "connection before proceeding. Performing security verification. "
                "Cloudflare Ray ID: abc123."
            ),
            "doi": "10.9999/captcha",
            "title": "Cloudflare interstitial stub page",
            "source_url": "https://blocked.example.org",
        },
        "ev_bare": {
            "evidence_id": "ev_bare",
            "direct_quote": f"{bare_sentence}.",
            "doi": "10.3000/bare",
            "title": "Bureau of Labor Statistics employment update",
            "source_url": "https://realnews.example.org",
        },
        "ev_clean": {
            "evidence_id": "ev_clean",
            "direct_quote": f"{_CLEAN_SENTENCE}.",
            "doi": "10.2000/clean",
            "title": "A genuine labor-market finding",
            "source_url": "https://good.example.org",
        },
    }
    draft = build_verified_span_draft(["ev_captcha", "ev_bare", "ev_clean"], pool)
    markers = _EV_MARKER_RE.findall(draft)
    if "ev_captcha" in markers:
        _fail("c", "CAPTCHA-stub member ev_captcha was NOT dropped (its marker leaked)")
    if "security verification" in draft.lower() or "cloudflare ray id" in draft.lower():
        _fail("c", "CAPTCHA-stub text leaked into the render")
    if "ev_bare" not in markers:
        _fail(
            "c",
            "NEGATIVE CONTROL: bare 'just a moment' real prose (no security co-token) was "
            "WRONGLY dropped — §-1.3 keep-all violated",
        )
    if "unemployment rate fell to 3.5 percent" not in draft:
        _fail("c", "NEGATIVE CONTROL: the bare-trigger real sentence was lost (over-drop)")
    if "ev_clean" not in markers:
        _fail("c", "the clean member was wrongly dropped alongside the CAPTCHA stub")


def main() -> int:
    _check_a_render_safety()
    _check_b_same_work_consolidation()
    _check_b2_over_merge_negative_control()
    _check_b3_weak_signal_over_merge_negatives()
    _check_c_captcha_stub_dropped()

    if _FAILURES:
        print("HARNESS FAILED — regressions detected:", file=sys.stderr)
        for f in _FAILURES:
            print(f"  FAIL {f}", file=sys.stderr)
        return 1
    print("HARNESS PASSED: (a) render-safe (no NUL/C0, blob bounded) "
          "(b) same-work consolidated to ONE multi-URL unit "
          "(c) CAPTCHA stub dropped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
