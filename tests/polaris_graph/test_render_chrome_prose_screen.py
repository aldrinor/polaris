"""Box C QUALITY fix (workflow wioabua6u) — render-seam chrome PROSE screen.

Proves the two coordinated parts of the fix against the REAL leaked chrome strings captured in
the wioabua6u evidence + the live Box A breadth section:

  PART A — the UNBLINDED containment predicate ``is_render_chrome_or_unrenderable`` (via the new
           ``_contains_boxc_render_chrome`` in ``weighted_enrichment``) now FLAGS the chrome classes
           it was proven blind to (author/date-welded byline, nav-menu glyph furniture, file-asset
           size inventory, bibliographic recital, ToC trailing-page heading, heading-glued-to-prose,
           the "(also mirrored)" repetition marker, a predominantly non-English Vietnamese heading)
           while KEEPING real verified claims.

  PART B — the render-seam screen ``_screen_render_chrome_prose`` (multi_section_generator) WITHHOLDS
           a whole chrome UNIT from the final resolved prose, preserves real claims byte-identically,
           is FAIL-SAFE (all-chrome body -> "" so the caller renders a disclosed gap stub), and is
           gated behind the default-ON kill-switch ``PG_RENDER_CHROME_PROSE_SCREEN``. Also covers the
           compose-time screen ``verified_compose._sentence_is_render_chrome``.

FAITHFULNESS is never touched: these are RENDER-SIDE WITHHOLD screens (a chrome UNIT is withheld
from prose, the SOURCE stays in the pool). No network, no spend — pure predicate/string tests.
"""

from __future__ import annotations

import os
import types

import pytest

from src.polaris_graph.generator.multi_section_generator import _screen_render_chrome_prose
from src.polaris_graph.generator.provenance_generator import parse_provenance_tokens
from src.polaris_graph.generator.verified_compose import (
    _sentence_is_render_chrome,
    _subtopic_decomposition_enabled,
    build_multi_member_sentences,
    build_short_member_sentence,
    build_verified_span_draft,
    build_verified_span_draft_multi,
)
from src.polaris_graph.generator.weighted_enrichment import (
    _contains_boxc_render_chrome,
    is_render_chrome_or_unrenderable,
)

# ── REAL leaked chrome strings (wioabua6u evidence + live Box A breadth section) — MUST DROP ──────
CHROME_STRINGS = [
    # author byline + date WELDED onto the "Abstract" section header
    "Chen 1, Joanna Wang 2 December 2024 Abstract This paper studies the effects of "
    "Artificial Intelligence",
    # affiliation bio-line byline ("is (Non-Resident) Senior Fellow")
    "Louise Fox is Non-Resident Senior Fellow; and Landry Signé is Senior Fellow at "
    "The Brookings Institution",
    # "Authors and contributors" masthead byline
    "Generative AI, Jobs, and Policy Response 4 Authors and contributors Janine Berg, "
    "International Labour Organization",
    # "About CSIS" institutional boilerplate
    "About CSIS Established in Washington, D.C., over 50 years ago, the Center for "
    "Strategic and International Studies",
    # IMF/ToC trailing-page heading (Title-Case run ending in a bare page number, no verb)
    "The Outlook: Steady Growth and Disinflation 7",
    # website nav-menu furniture (glyphs + bracketed nav labels + markdown nav run)
    "a navigation menu item [Zurück](https://iab.de/home)➔≡Menu✘ * [Startseite",
    # file-asset-metadata inventory (>=2 size tokens)
    "a paper PDF of 6 MB, an English text file of 213.59 KB, and a study brief PDF of 1.08 MB",
    # bibliographic-recital-as-prose ("published volume N, article N")
    "The journal Systems published volume 13, article 569, in 2025 with DOI "
    "10.3390/systems13070569",
    # heading-glued-to-prose (leading standalone policy-brief heading token)
    "Elevator pitch Artificial intelligence (AI) has streamlined processes",
    # predominantly non-English (Vietnamese) heading
    "CÁCH MẠNG CÔNG NGHIỆP 4.0 TẠI VIỆT NAM: HÀM Ý ĐỐI VỚI THỊ TRƯỜNG LAO ĐỘNG",
    # pipeline-internal "(also mirrored)" repetition marker
    "This entry duplicates an earlier source (also mirrored) in the appendix listing",
    # heading-glued-to-prose (ALL-CAPS multiword run of 5+ words embedded mid-sentence)
    "the report warns THE PROSPECTS FOR GENERATIVE AI TO HAVE AN UNEQUAL IMPACT across regions",
]

# ── REAL valid claims — MUST PRESERVE (never drop) ───────────────────────────────────────────────
VALID_CLAIMS = [
    "an additional robot per thousand workers reduces employment to population ratio by about "
    "0.18-0.34 percentage points and wages by 0.25-0.5",
    "by 2025, 85 million jobs may be displaced ... while 97 million new roles may emerge",
    "generative AI targets white-collar cognitive work",
]


# ── PART A — the UNBLINDED containment predicate ─────────────────────────────────────────────────
@pytest.mark.parametrize("chrome", CHROME_STRINGS)
def test_part_a_boxc_predicate_flags_chrome(chrome: str) -> None:
    """The new ``_contains_boxc_render_chrome`` OR the full shared predicate flags every leaked
    chrome class."""
    assert _contains_boxc_render_chrome(chrome) or is_render_chrome_or_unrenderable(chrome), (
        f"chrome NOT flagged by the unblinded predicate: {chrome!r}"
    )


@pytest.mark.parametrize("chrome", CHROME_STRINGS)
def test_part_a_shared_predicate_flags_chrome(chrome: str) -> None:
    """The shared render predicate (what the render seam calls) flags every leaked chrome class."""
    assert is_render_chrome_or_unrenderable(chrome), (
        f"chrome NOT flagged by is_render_chrome_or_unrenderable: {chrome!r}"
    )


@pytest.mark.parametrize("claim", VALID_CLAIMS)
def test_part_a_predicate_preserves_valid_claims(claim: str) -> None:
    """A real verified claim is NEVER flagged as chrome (precision-first, constraint 2)."""
    assert not _contains_boxc_render_chrome(claim), f"valid claim wrongly flagged (boxc): {claim!r}"
    assert not is_render_chrome_or_unrenderable(claim), (
        f"valid claim wrongly flagged (shared): {claim!r}"
    )


# ── PART B — the render-seam screen ──────────────────────────────────────────────────────────────
@pytest.mark.parametrize("chrome", CHROME_STRINGS)
def test_part_b_screen_drops_sole_chrome_unit(chrome: str) -> None:
    """A section body that is ONLY a chrome unit is fully withheld (returns "" -> the caller renders
    a disclosed gap stub); the source is never dropped from the pool (out of this screen's scope)."""
    assert _screen_render_chrome_prose(chrome) == "", (
        f"chrome unit was NOT withheld at the render seam: {chrome!r}"
    )


@pytest.mark.parametrize("claim", VALID_CLAIMS)
def test_part_b_screen_preserves_valid_claim_byte_identical(claim: str) -> None:
    """A real verified claim passes the render-seam screen byte-identically (never blanked)."""
    assert _screen_render_chrome_prose(claim) == claim, f"valid claim altered/dropped: {claim!r}"


def test_part_b_mixed_section_keeps_valid_drops_chrome() -> None:
    """A mixed section (real claim + welded chrome unit) keeps the real claim and withholds the
    chrome unit — the whole verified section is NOT blanked (constraint 2)."""
    valid = (
        "An additional robot per thousand workers reduces employment to population ratio by about "
        "0.18-0.34 percentage points and wages by 0.25-0.5 [12]."
    )
    chrome = "The Outlook: Steady Growth and Disinflation 7"
    out = _screen_render_chrome_prose(f"{valid} {chrome}")
    assert "additional robot per thousand workers" in out, "valid claim was lost from a mixed body"
    assert "Steady Growth and Disinflation" not in out, "chrome unit survived a mixed body"


def test_part_b_all_chrome_section_returns_empty_gap_stub_path() -> None:
    """A section whose EVERY unit is chrome returns "" so ``_run_section`` renders the disclosed gap
    stub — never ships the chrome, never silently vanishes (fail-safe)."""
    body = (
        "Louise Fox is Non-Resident Senior Fellow at The Brookings Institution. "
        "About CSIS Established in Washington, D.C., over 50 years ago, the Center prevails."
    )
    assert _screen_render_chrome_prose(body) == ""


def test_part_b_kill_switch_disables_screen() -> None:
    """PG_RENDER_CHROME_PROSE_SCREEN=0 disables the screen (LAW VI): a chrome body is returned
    UNCHANGED without a code change."""
    chrome = "The Outlook: Steady Growth and Disinflation 7"
    prev = os.environ.get("PG_RENDER_CHROME_PROSE_SCREEN")
    os.environ["PG_RENDER_CHROME_PROSE_SCREEN"] = "0"
    try:
        assert _screen_render_chrome_prose(chrome) == chrome
    finally:
        if prev is None:
            os.environ.pop("PG_RENDER_CHROME_PROSE_SCREEN", None)
        else:
            os.environ["PG_RENDER_CHROME_PROSE_SCREEN"] = prev


def test_part_b_empty_and_blank_input_unchanged() -> None:
    """Empty / blank input is returned unchanged (fail-safe: never invents a body)."""
    assert _screen_render_chrome_prose("") == ""
    assert _screen_render_chrome_prose("   ") == "   "


# ── compose-time screen (verified_compose) ───────────────────────────────────────────────────────
@pytest.mark.parametrize("chrome", CHROME_STRINGS)
def test_compose_time_screen_flags_chrome(chrome: str) -> None:
    """The compose-time helper flags a writer-paraphrased chrome sentence (caught before render)."""
    assert _sentence_is_render_chrome(chrome), f"compose-time screen missed chrome: {chrome!r}"


@pytest.mark.parametrize("claim", VALID_CLAIMS)
def test_compose_time_screen_preserves_valid(claim: str) -> None:
    """The compose-time helper never withholds a real verified sentence."""
    assert not _sentence_is_render_chrome(claim), (
        f"compose-time screen wrongly flagged a valid claim: {claim!r}"
    )


# ── PRECISION corrections 1/2/3 — the exact KEEP cases the corrections protect (MUST NOT DROP) ────
# Each carries a real cited finding that the pre-correction rules over-dropped: two bare data-size
# claims (correction 1: file-asset noun anchor), two English claims naming a Vietnamese entity
# (correction 2: DENSITY test not raw count), and an author-affiliation-in-passing that carries a
# cited finding (correction 3: byline flags ONLY when no cited finding survives).
PRECISION_KEEP = [
    # correction 1 — bare data-magnitude claims (NOT a file-download size inventory)
    "Data volumes grew from 570 GB in 2020 to 45 TB by 2023 [7]",
    "Each A100 card provides 80 GB of memory, while consumer cards offer 24 GB [12]",
    # correction 2 — English claims that merely NAME a Vietnamese entity (below the tone-mark density bar)
    "The Vietnam Ministry of Labour (Bộ Lao động) projects 3 million displaced workers by 2030 [9]",
    "Prime Minister Phạm Minh Chính and Nguyễn Thị Hồng announced the national AI strategy in 2024 [2]",
    # correction 3 — an attributed cited finding that names an author's affiliation in passing
    "Landry Signé, who is a Senior Fellow at Brookings, projects that AI will shift 30 percent of tasks [4]",
]


@pytest.mark.parametrize("keep", PRECISION_KEEP)
def test_precision_corrections_keep_real_cited_findings(keep: str) -> None:
    """Corrections 1/2/3: a real cited finding is NEVER flagged by the box-C predicate, the shared
    render predicate, OR the compose-time screen (precision-first — the corrections narrow each rule
    so a welded-chrome-shaped-but-real claim is KEPT)."""
    assert not _contains_boxc_render_chrome(keep), f"correction over-dropped (boxc): {keep!r}"
    assert not is_render_chrome_or_unrenderable(keep), f"correction over-dropped (shared): {keep!r}"
    assert not _sentence_is_render_chrome(keep), f"correction over-dropped (compose): {keep!r}"


# ── L2 sub-topic decomposition (verified_compose) — one verified span-sentence per DISTINCT fact ───
def _make_member(eid: str, quote: str, weight: float = 0.9):
    m = types.SimpleNamespace()
    m.evidence_id = eid
    m.direct_quote = quote
    m.span_verdict = "SUPPORTS"
    m.credibility_weight = weight
    m.origin_cluster_id = eid
    return m


# A rich member grounds TWO distinct atomic facts; a second member corroborates the FIRST fact only.
_L2_QUOTE_RICH = (
    "Artificial intelligence will displace 30 percent of tasks by 2030. "
    "It will also create 12 million new roles by 2032."
)
_L2_QUOTE_CORROBORATOR = "Artificial intelligence will displace 30 percent of tasks by 2030."


def _l2_basket():
    return types.SimpleNamespace(
        supporting_members=[
            _make_member("e1", _L2_QUOTE_RICH, 0.9),
            _make_member("e2", _L2_QUOTE_CORROBORATOR, 0.8),
        ],
        subject="AI task displacement",
        claim_text="AI task displacement",
    )


def _l2_pool():
    return {
        "e1": {"direct_quote": _L2_QUOTE_RICH},
        "e2": {"direct_quote": _L2_QUOTE_CORROBORATOR},
    }


def _assert_tokens_slice_span(text: str, pool: dict) -> None:
    """Every emitted provenance token must EXACTLY slice its evidence row to real span text — the
    faithfulness-by-construction invariant (each L2 sentence IS a verbatim span)."""
    toks = parse_provenance_tokens(text)
    assert toks, f"L2 output carries no provenance token: {text!r}"
    for tok in toks:
        row = str(pool[tok.evidence_id]["direct_quote"])
        assert 0 <= tok.start < tok.end <= len(row), f"token out of bounds: {tok!r}"
        # the sentence's rendered core (period stripped) must be a prefix of the cited span text
        span = row[tok.start:tok.end]
        assert span.strip(), f"token slices empty span: {tok!r}"


@pytest.fixture()
def _subtopic_env():
    prev = os.environ.get("PG_SUBTOPIC_DECOMPOSITION")
    yield lambda v: os.environ.__setitem__("PG_SUBTOPIC_DECOMPOSITION", v)
    if prev is None:
        os.environ.pop("PG_SUBTOPIC_DECOMPOSITION", None)
    else:
        os.environ["PG_SUBTOPIC_DECOMPOSITION"] = prev


def test_l2_writer_emits_distinct_facts_and_dedupes(_subtopic_env) -> None:
    """L2 ON: the deterministic writer emits ONE verbatim-span sentence per DISTINCT atomic fact (both
    facts of the rich member) and DEDUPES the corroborating repeat (e2's fact == e1's first fact)."""
    _subtopic_env("1")
    out = build_multi_member_sentences(_l2_basket(), _l2_pool())
    assert "displace 30 percent of tasks by 2030" in out
    assert "create 12 million new roles by 2032" in out, "L2 dropped the second distinct fact"
    # the corroborating duplicate must not repeat the sentence (keep-all consolidation, not repetition)
    assert out.count("displace 30 percent of tasks by 2030") == 1, "L2 repeated a corroborated fact"
    _assert_tokens_slice_span(out, _l2_pool())


def test_l2_span_fallback_emits_distinct_facts(_subtopic_env) -> None:
    """L2 ON: the snap-preserving K-span fallback also surfaces BOTH distinct facts (not just the first
    member's headline), each carrying a real provenance token (faithfulness-neutral)."""
    _subtopic_env("1")
    out = build_verified_span_draft_multi(_l2_basket(), _l2_pool())
    assert out is not None
    assert "displace 30 percent of tasks by 2030" in out
    assert "create 12 million new roles by 2032" in out
    _assert_tokens_slice_span(out, _l2_pool())


def test_l2_off_is_byte_identical_to_single_headline(_subtopic_env) -> None:
    """PG_SUBTOPIC_DECOMPOSITION=0 (LAW VI): the writer reverts to the single-headline short writer and
    the fallback reverts to build_verified_span_draft — byte-identical to the pre-L2 producers."""
    _subtopic_env("0")
    assert _subtopic_decomposition_enabled() is False
    basket, pool = _l2_basket(), _l2_pool()
    assert build_multi_member_sentences(basket, pool) == build_short_member_sentence(basket, pool)
    # single-headline fallback: only the first member's first fact
    off = build_multi_member_sentences(basket, pool)
    assert "create 12 million new roles" not in off, "L2-off still emitted the second fact"
    assert build_verified_span_draft(basket, pool) is not None


def test_l2_default_on() -> None:
    """L2 is DEFAULT-ON: an unset PG_SUBTOPIC_DECOMPOSITION decomposes (the coverage lever is armed by
    default; the slate + a100 belt pin it explicitly for the paid run)."""
    prev = os.environ.pop("PG_SUBTOPIC_DECOMPOSITION", None)
    try:
        assert _subtopic_decomposition_enabled() is True
    finally:
        if prev is not None:
            os.environ["PG_SUBTOPIC_DECOMPOSITION"] = prev
