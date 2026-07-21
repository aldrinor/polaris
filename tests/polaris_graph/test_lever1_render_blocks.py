"""LEVER 1 (structure-preserving render, PG_RENDER_BLOCKS).

Two coordinated halves behind ONE flag, default OFF => byte-identical:
  * resolver half: preserve the writer's blank-line paragraph breaks instead of flattening a section
    to one `" ".join` blob (provenance_generator.resolve_provenance_to_citations_with_count).
  * writer half: flip section-prompt rule 7 to a paragraphs-only directive (multi_section_generator.
    _build_paragraph_variant).

The engine (strict_verify / provenance) is untouched — this is render + prompt only. These tests prove:
  1. OFF: the resolver output is byte-identical to the legacy `" ".join(findings_lines)`.
  2. ON: paragraph breaks appear, the paragraph COUNT matches the source blocks, and the set/order of
     rendered sentences (text + [N] markers) is identical to OFF — only the separators differ.
  3. The writer variant changes ONLY rule 7 (other rules byte-identical); OFF leaves the template as-is.
"""

from __future__ import annotations

from src.polaris_graph.generator.provenance_generator import (
    ProvenanceToken,
    SentenceVerification,
    resolve_provenance_to_citations_with_count,
    _paragraph_block_index_by_position,
    _render_block_norm_key,
)
from src.polaris_graph.generator.multi_section_generator import (
    SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC,
    _RENDER_BLOCKS_RULE_7,
    _build_paragraph_variant,
    _select_section_system_prompt,
)


def _pool() -> dict[str, dict[str, str]]:
    return {
        "ev_a": {"source_url": "https://example.com/a", "tier": "T1", "statement": "sa"},
        "ev_b": {"source_url": "https://example.com/b", "tier": "T4", "statement": "sb"},
    }


def _sv(sentence: str, ev_ids: list[str]) -> SentenceVerification:
    toks = [
        ProvenanceToken(evidence_id=e, start=0, end=40, raw=f"[#ev:{e}:0-40]")
        for e in ev_ids
    ]
    return SentenceVerification(
        sentence=sentence, tokens=toks, is_verified=True, failure_reasons=[], soft_warnings=[],
    )


# Two source paragraphs, two sentences each; every sentence carries a canonical [#ev:] token.
_P1 = "Alpha finding holds strongly.[#ev:ev_a:0-40] Beta result follows too.[#ev:ev_b:0-40]"
_P2 = "Gamma outcome diverges here.[#ev:ev_a:0-40] Delta confirms the trend.[#ev:ev_b:0-40]"
_SOURCE = _P1 + "\n\n" + _P2


def _kept() -> list[SentenceVerification]:
    return [
        _sv("Alpha finding holds strongly.[#ev:ev_a:0-40]", ["ev_a"]),
        _sv("Beta result follows too.[#ev:ev_b:0-40]", ["ev_b"]),
        _sv("Gamma outcome diverges here.[#ev:ev_a:0-40]", ["ev_a"]),
        _sv("Delta confirms the trend.[#ev:ev_b:0-40]", ["ev_b"]),
    ]


def test_off_is_byte_identical(monkeypatch):
    """Flag unset => flat `" ".join` render, byte-for-byte, whether or not a source draft is passed."""
    monkeypatch.delenv("PG_RENDER_BLOCKS", raising=False)
    text_no_src, _, _ = resolve_provenance_to_citations_with_count(_kept(), _pool())
    text_with_src, _, _ = resolve_provenance_to_citations_with_count(
        _kept(), _pool(), section_source_text=_SOURCE,
    )
    assert "\n\n" not in text_no_src
    assert text_no_src == text_with_src  # source text is inert when the flag is off
    # exactly four sentences, single-space joined
    assert text_no_src.count("[1]") + text_no_src.count("[2]") == 4


def test_on_preserves_paragraph_breaks(monkeypatch):
    monkeypatch.setenv("PG_RENDER_BLOCKS", "1")
    off_text, off_biblio, off_emitted = _off_render()
    on_text, on_biblio, on_emitted = resolve_provenance_to_citations_with_count(
        _kept(), _pool(), section_source_text=_SOURCE,
    )
    # a break appeared, and the number of rendered paragraphs equals the source block count (2)
    assert "\n\n" in on_text
    assert len([p for p in on_text.split("\n\n") if p.strip()]) == 2
    # content identity: strip the separators and the two renders are the same sentence sequence
    assert _norm_spaces(on_text) == _norm_spaces(off_text)
    # bibliography + honest emitted count are byte-identical — only the separators changed
    assert on_biblio == off_biblio
    assert on_emitted == off_emitted


def test_on_without_source_stays_flat(monkeypatch):
    """Flag ON but no draft threaded (e.g. a resolve site we left unwired) => flat, no spurious breaks."""
    monkeypatch.setenv("PG_RENDER_BLOCKS", "1")
    text, _, _ = resolve_provenance_to_citations_with_count(_kept(), _pool())
    assert "\n\n" not in text


def test_single_block_source_has_no_breaks(monkeypatch):
    """A one-paragraph source (writer emitted no breaks) => <2 blocks => flat, byte-identical to OFF."""
    monkeypatch.setenv("PG_RENDER_BLOCKS", "1")
    one_para = _P1 + " " + _P2  # no blank line
    on_text, _, _ = resolve_provenance_to_citations_with_count(
        _kept(), _pool(), section_source_text=one_para,
    )
    off_text, _, _ = _off_render()
    assert on_text == off_text


def _off_render():
    import os
    prev = os.environ.pop("PG_RENDER_BLOCKS", None)
    try:
        return resolve_provenance_to_citations_with_count(_kept(), _pool())
    finally:
        if prev is not None:
            os.environ["PG_RENDER_BLOCKS"] = prev


def _norm_spaces(t: str) -> str:
    return " ".join(t.split())


# ── writer half ──────────────────────────────────────────────────────────────

def test_paragraph_variant_changes_only_rule_7():
    tmpl = SECTION_SYSTEM_PROMPT_TEMPLATE_FIELD_AGNOSTIC
    anchor = ("7. Do not write a section heading, section title, or preamble. "
              "Just the paragraph body.")
    variant = _build_paragraph_variant(tmpl)
    assert variant != tmpl
    assert _RENDER_BLOCKS_RULE_7 in variant
    assert "Just the paragraph body." not in variant
    # the change is EXACTLY the rule-7 substitution — everything else byte-identical
    assert variant == tmpl.replace(anchor, _RENDER_BLOCKS_RULE_7)
    # paragraphs-only intent: asks for blank-line-separated paragraphs and PROHIBITS structure markup
    assert "blank" in _RENDER_BLOCKS_RULE_7.lower() and "paragraphs only" in _RENDER_BLOCKS_RULE_7.lower()
    assert "Do NOT use headings, bullet lists, or tables" in _RENDER_BLOCKS_RULE_7


def test_select_prompt_flat_when_off(monkeypatch):
    monkeypatch.delenv("PG_RENDER_BLOCKS", raising=False)
    monkeypatch.delenv("PG_SECTION_STRUCTURE", raising=False)
    monkeypatch.delenv("PG_ANTI_VERBOSITY", raising=False)
    base = _select_section_system_prompt(use_field_agnostic=True, anti_verbosity=False)
    assert "Just the paragraph body." in base
    assert _RENDER_BLOCKS_RULE_7 not in base


def test_select_prompt_paragraph_when_on(monkeypatch):
    monkeypatch.setenv("PG_RENDER_BLOCKS", "1")
    monkeypatch.delenv("PG_SECTION_STRUCTURE", raising=False)
    monkeypatch.delenv("PG_ANTI_VERBOSITY", raising=False)
    base = _select_section_system_prompt(use_field_agnostic=True, anti_verbosity=False)
    assert _RENDER_BLOCKS_RULE_7 in base


# ── FIX 1: matcher safety (exact-key, ambiguity/unmatched => None, latch flattens) ─────────────

def test_norm_key_is_full_and_nfkc_casefold():
    # NFKC folds the "ﬁ" ligature to "fi"; casefold folds German ß -> ss; keys must be EQUAL.
    assert _render_block_norm_key("The ﬁle result.[#ev:ev_a:0-5]") == _render_block_norm_key("The file result.")
    assert _render_block_norm_key("Straße data.") == _render_block_norm_key("STRASSE data.")
    # no truncation — a long sentence yields a key far longer than the old 28-char cap
    assert len(_render_block_norm_key("word " * 40)) > 28


def test_collision_prefix_no_longer_matches():
    """Two source sentences share a long prefix but differ at the end; the kept one (other dropped)
    must map to its OWN block via exact full-key match, not collide onto the first (old prefix bug)."""
    p0 = "The result was strong and positive overall here.[#ev:ev_a:0-40]"
    p1 = "The result was strong and positive overall today.[#ev:ev_b:0-40]"
    src = p0 + "\n\n" + p1
    kept = [_sv("The result was strong and positive overall today.[#ev:ev_b:0-40]", ["ev_b"])]
    assert _paragraph_block_index_by_position(src, kept) == [1]


def test_unmatched_first_in_block_flattens_not_shifts(monkeypatch):
    """The [0,0,1] repro: the first sentence of the new block fails to match => boundary must be
    FLATTENED (no break), never delayed onto the 3rd sentence."""
    src = ("Sentence one alpha here.[#ev:ev_a:0-40]\n\n"
           "Sentence two beta here.[#ev:ev_b:0-40] Sentence three gamma here.[#ev:ev_a:0-40]")
    kept = [
        _sv("Sentence one alpha here.[#ev:ev_a:0-40]", ["ev_a"]),
        _sv("A totally different unmatched middle line.[#ev:ev_b:0-40]", ["ev_b"]),  # no source match
        _sv("Sentence three gamma here.[#ev:ev_a:0-40]", ["ev_a"]),
    ]
    idx = _paragraph_block_index_by_position(src, kept)
    assert idx[0] == 0 and idx[1] is None and idx[2] == 1  # middle unmatched
    monkeypatch.setenv("PG_RENDER_BLOCKS", "1")
    on_text, _, _ = resolve_provenance_to_citations_with_count(
        kept, _pool(), section_source_text=src,
    )
    assert "\n\n" not in on_text  # boundary flattened, NOT shifted before sentence three


def test_ambiguous_duplicate_source_key_is_none():
    """A sentence whose normalized key appears twice in the source is ambiguous => None (flatten)."""
    dup = "Identical restated finding here.[#ev:ev_a:0-40]"
    src = dup + "\n\n" + dup  # same sentence in two blocks
    kept = [_sv(dup, ["ev_a"])]
    assert _paragraph_block_index_by_position(src, kept) == [None]


def test_dropped_sentence_mid_block_no_spurious_break(monkeypatch):
    # sentences kept long enough to clear the resolver's degenerate-fragment floor (F10)
    s1 = "Alpha displacement rose sharply this year.[#ev:ev_a:0-40]"
    s2 = "Bravo adoption climbed steadily across firms.[#ev:ev_b:0-40]"
    s3 = "Charlie wages fell modestly in exposed roles.[#ev:ev_a:0-40]"
    s4 = "Delta productivity gains concentrated among novice workers.[#ev:ev_b:0-40]"
    s5 = "Echo employment held roughly flat overall this period.[#ev:ev_a:0-40]"
    src = f"{s1} {s2} {s3}\n\n{s4} {s5}"
    # middle sentence of block 0 (s2) dropped by strict_verify
    kept = [_sv(s1, ["ev_a"]), _sv(s3, ["ev_a"]), _sv(s4, ["ev_b"]), _sv(s5, ["ev_a"])]
    monkeypatch.setenv("PG_RENDER_BLOCKS", "1")
    on_text, _, _ = resolve_provenance_to_citations_with_count(
        kept, _pool(), section_source_text=src,
    )
    paras = [p for p in on_text.split("\n\n") if p.strip()]
    assert len(paras) == 2                    # exactly one break, at the real block boundary
    assert "Alpha displacement" in paras[0] and "Charlie wages" in paras[0]
    assert "Delta productivity" in paras[1] and "Echo employment" in paras[1]


def test_calc_tail_append_no_spurious_break(monkeypatch):
    h1 = "Alpha exposure increased across many industry sectors.[#ev:ev_a:0-40]"
    h2 = "Bravo automation displaced routine cognitive task work.[#ev:ev_b:0-40]"
    t1 = "Charlie reskilling programs expanded widely in response.[#ev:ev_a:0-40]"
    t2 = "Delta wage premiums shifted toward technical skills.[#ev:ev_b:0-40]"
    calc = "Echo computed aggregate effect reached twelve percent overall.[#ev:ev_a:0-40]"
    src = f"{h1} {h2}\n\n{t1} {t2}"  # calc sentence is NOT in the source draft
    kept = [_sv(h1, ["ev_a"]), _sv(h2, ["ev_b"]), _sv(t1, ["ev_a"]), _sv(t2, ["ev_b"]), _sv(calc, ["ev_a"])]
    monkeypatch.setenv("PG_RENDER_BLOCKS", "1")
    on_text, _, _ = resolve_provenance_to_citations_with_count(
        kept, _pool(), section_source_text=src,
    )
    paras = [p for p in on_text.split("\n\n") if p.strip()]
    assert len(paras) == 2  # one real break; the unmatched calc tail rides the last block, no new break
    assert "Echo computed aggregate" in paras[1]


def test_reordered_recovered_sentence_never_shifts_break(monkeypatch):
    """FIX 4: a recovered sentence appended out of source order must not shift the break into a block."""
    s1 = "Ess task restructuring accelerated across finance.[#ev:ev_a:0-40]"
    s2 = "Bee clerical roles contracted most quickly overall.[#ev:ev_b:0-40]"
    s3 = "Cee new roles emerged in oversight functions.[#ev:ev_a:0-40]"
    s4 = "Dee demand grew for scarce data skills.[#ev:ev_b:0-40]"
    src = f"{s1} {s2}\n\n{s3} {s4}"
    # kept has block-1 sentences swapped (s4 before s3) — recovered out of order
    kept = [_sv(s1, ["ev_a"]), _sv(s2, ["ev_b"]), _sv(s4, ["ev_b"]), _sv(s3, ["ev_a"])]
    monkeypatch.setenv("PG_RENDER_BLOCKS", "1")
    on_text, _, _ = resolve_provenance_to_citations_with_count(
        kept, _pool(), section_source_text=src,
    )
    paras = [p for p in on_text.split("\n\n") if p.strip()]
    # the single break sits at the true block-0/block-1 boundary; block-0 content never trails a break
    assert len(paras) <= 2
    assert "Ess task restructuring" in paras[0] and "Bee clerical" in paras[0]
    if len(paras) == 2:
        assert "Ess task restructuring" not in paras[1] and "Bee clerical" not in paras[1]


def test_structure_wins_when_both_on(monkeypatch):
    """PG_SECTION_STRUCTURE supersedes PG_RENDER_BLOCKS when both are set."""
    monkeypatch.setenv("PG_RENDER_BLOCKS", "1")
    monkeypatch.setenv("PG_SECTION_STRUCTURE", "1")
    monkeypatch.delenv("PG_ANTI_VERBOSITY", raising=False)
    base = _select_section_system_prompt(use_field_agnostic=True, anti_verbosity=False)
    assert _RENDER_BLOCKS_RULE_7 not in base  # structure variant took the rule-7 slot
    assert "###" in base


# ── REPLAY under the champion recipe (PG_STRICT_VERIFY_OFF=1) ───────────────────────────────────
# No banked pre-resolve fixture (kept_sentences + raw draft) exists from the live k3_b1_run — outputs/
# hold only the final report.md — so this is the closest SYNTHETIC multi-paragraph section replay under
# the exact champion flag (strict-verify OFF => no F10/F31 drops). It asserts OFF byte-identical baseline,
# ON identical ordered sentences + markers + bibliography + emitted_count, and that paragraph breaks
# survive the two render screens on the champion path (they short-circuit under strict-verify-off).

_REPLAY_SRC = (
    "Generative AI raised measured worker productivity by roughly fourteen to fifty-six "
    "percent across randomized experiments.[#ev:ev_a:0-40] The largest gains accrued to "
    "lower-ability and less-experienced workers overall.[#ev:ev_b:0-40]\n\n"
    "Across multiple data sources aggregate employment showed no detectable net decline so "
    "far.[#ev:ev_a:0-40] The disruption instead materialized as distributional reallocation "
    "across skill groups.[#ev:ev_b:0-40]"
)


def _replay_kept():
    return [
        _sv("Generative AI raised measured worker productivity by roughly fourteen to fifty-six "
            "percent across randomized experiments.[#ev:ev_a:0-40]", ["ev_a"]),
        _sv("The largest gains accrued to lower-ability and less-experienced workers overall."
            "[#ev:ev_b:0-40]", ["ev_b"]),
        _sv("Across multiple data sources aggregate employment showed no detectable net decline so "
            "far.[#ev:ev_a:0-40]", ["ev_a"]),
        _sv("The disruption instead materialized as distributional reallocation across skill groups."
            "[#ev:ev_b:0-40]", ["ev_b"]),
    ]


def test_replay_champion_off_vs_on(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_OFF", "1")  # champion recipe: no drops
    monkeypatch.delenv("PG_RENDER_BLOCKS", raising=False)
    off_text, off_biblio, off_emitted = resolve_provenance_to_citations_with_count(
        _replay_kept(), _pool(), section_source_text=_REPLAY_SRC,
    )
    assert "\n\n" not in off_text
    assert off_emitted == 4
    monkeypatch.setenv("PG_RENDER_BLOCKS", "1")
    on_text, on_biblio, on_emitted = resolve_provenance_to_citations_with_count(
        _replay_kept(), _pool(), section_source_text=_REPLAY_SRC,
    )
    assert on_text.count("\n\n") == 1                       # exactly the one source break
    assert len([p for p in on_text.split("\n\n") if p.strip()]) == 2
    assert _norm_spaces(on_text) == _norm_spaces(off_text)  # identical ordered sentences + markers
    assert on_biblio == off_biblio                          # bibliography unchanged
    assert on_emitted == off_emitted                        # honest emitted count unchanged


def test_replay_breaks_survive_screens_on_champion(monkeypatch):
    """On the champion path the two render screens short-circuit (strict-verify-off) => breaks survive."""
    from src.polaris_graph.generator.multi_section_generator import (
        _screen_uncited_numeric_sentences,
        _screen_render_chrome_prose,
    )
    monkeypatch.setenv("PG_STRICT_VERIFY_OFF", "1")
    monkeypatch.setenv("PG_RENDER_BLOCKS", "1")
    text = "First paragraph sentence with value 12.5 percent [1].\n\nSecond paragraph sentence here [2]."
    assert "\n\n" in _screen_uncited_numeric_sentences(text)
    assert "\n\n" in _screen_render_chrome_prose(text)
