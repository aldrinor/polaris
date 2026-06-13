"""Blocker tests for fact_dedup span over-concentration cap — I-pipe-007 (#1232).

Forensic finding (dual Claude+Codex 2026-06-12, drb_72): a single ~800-char
evidence span (brynjolfsson:0-800 19x, acemoglu:0-800 18x) was cited as
near-redundant padding that fact_dedup's numeric+>=2-section grouping missed.
Fix: per-(evidence_id, start, end) citation cap gated behind the env
PG_SPAN_PER_SOURCE_CITE_CAP (int, default 0 == OFF == byte-identical).

These tests assert:
  (a) flag-OFF (cap=0 / unset / malformed) == current behavior (identity).
  (b) flag-ON cap=3 reduces a 6x-cited span to <= 3 citing sentences.
  (c) nothing unverified is introduced — every surviving sentence is a
      VERBATIM member of the input (the cap only DROPS, never rewrites).
  (d) a sentence still contributing an under-cap span is never dropped.
  (e) sentences with no provenance token are never dropped by the cap.
  (f) faithfulness gates (strict_verify / NLI / 4-role) are untouched — the
      module exposes no path that weakens them.

The cap is exercised both via the pure helper `apply_span_cite_cap` and via
the end-to-end `dedup_pass` (with a never-called LLM stub, since the padding
sentences form no numeric-dedup group).
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.polaris_graph.generator.fact_dedup import (
    SPAN_CITE_CAP_ENV,
    apply_span_cite_cap,
    dedup_pass,
)


# A single 800-char-style span cited 6x as padding. Each sentence carries a
# DISTINCT subject so it is NOT a numeric-dedup group (no shared signature),
# which is exactly why build_groups misses it. All cite the same span token.
_SPAN_TOKEN = "[#ev:brynjolfsson:0-800]"


def _six_padding_sentences() -> list[str]:
    return [
        f"Automation reshaped manufacturing labor markets {_SPAN_TOKEN}.",
        f"Automation reshaped service-sector employment {_SPAN_TOKEN}.",
        f"Automation reshaped regional wage dispersion {_SPAN_TOKEN}.",
        f"Automation reshaped firm-level productivity {_SPAN_TOKEN}.",
        f"Automation reshaped occupational mobility {_SPAN_TOKEN}.",
        f"Automation reshaped skill-premium dynamics {_SPAN_TOKEN}.",
    ]


# ─────────────────────────────────────────────────────────────────────────
# (a) flag-OFF identity
# ─────────────────────────────────────────────────────────────────────────


def test_cap_off_returns_same_object_identity() -> None:
    """cap <= 0 returns the SAME dict object — a true byte-identical no-op."""
    sections = {"Efficacy": _six_padding_sentences()}
    out, telem = apply_span_cite_cap(sections, cap=0)
    assert out is sections  # same object, nothing copied or mutated
    assert telem["n_span_cite_dropped"] == 0
    assert telem["n_spans_over_cap"] == 0


def test_cap_negative_is_off() -> None:
    sections = {"S": _six_padding_sentences()}
    out, telem = apply_span_cite_cap(sections, cap=-5)
    assert out is sections
    assert telem["n_span_cite_dropped"] == 0


def test_env_unset_keeps_all_via_dedup_pass(monkeypatch: Any) -> None:
    """Env unset => dedup_pass keeps every padding sentence (current behavior).

    These 6 sentences share a span but NOT a numeric signature, so build_groups
    forms no group and (env OFF) the section is returned with all 6.
    """
    monkeypatch.delenv(SPAN_CITE_CAP_ENV, raising=False)
    sections = {"Efficacy": _six_padding_sentences()}

    async def _never_called_llm(system: str, prompt: str) -> Any:  # pragma: no cover
        raise AssertionError("LLM must not be called for non-grouped padding")

    out, telem = asyncio.run(
        dedup_pass(sections, _never_called_llm, section_order=["Efficacy"])
    )
    assert out["Efficacy"] == _six_padding_sentences()
    assert telem["n_span_cite_dropped"] == 0


def test_env_zero_string_is_off(monkeypatch: Any) -> None:
    monkeypatch.setenv(SPAN_CITE_CAP_ENV, "0")
    sections = {"Efficacy": _six_padding_sentences()}

    async def _never(system: str, prompt: str) -> Any:  # pragma: no cover
        raise AssertionError("LLM must not be called")

    out, telem = asyncio.run(
        dedup_pass(sections, _never, section_order=["Efficacy"])
    )
    assert out["Efficacy"] == _six_padding_sentences()
    assert telem["n_span_cite_dropped"] == 0


def test_env_malformed_is_off(monkeypatch: Any) -> None:
    """A typo'd env value must NOT crash and must default to OFF."""
    monkeypatch.setenv(SPAN_CITE_CAP_ENV, "not-an-int")
    sections = {"Efficacy": _six_padding_sentences()}

    async def _never(system: str, prompt: str) -> Any:  # pragma: no cover
        raise AssertionError("LLM must not be called")

    out, telem = asyncio.run(
        dedup_pass(sections, _never, section_order=["Efficacy"])
    )
    assert out["Efficacy"] == _six_padding_sentences()
    assert telem["n_span_cite_dropped"] == 0


# ─────────────────────────────────────────────────────────────────────────
# (b) flag-ON: cap=3 reduces a 6x-cited span to <= 3
# ─────────────────────────────────────────────────────────────────────────


def test_cap_three_reduces_six_cited_span_to_three() -> None:
    sections = {"Efficacy": _six_padding_sentences()}
    out, telem = apply_span_cite_cap(
        sections, cap=3, section_order=["Efficacy"]
    )
    kept = out["Efficacy"]
    # The span appears in at most 3 surviving sentences.
    span_uses = sum(1 for s in kept if _SPAN_TOKEN in s)
    assert span_uses <= 3
    assert span_uses == 3  # exactly the first 3 (deterministic FIFO)
    assert telem["n_span_cite_dropped"] == 3
    assert telem["n_spans_over_cap"] == 1
    # The kept three are the FIRST three in section/index order.
    assert kept == _six_padding_sentences()[:3]


def test_cap_three_via_dedup_pass_env(monkeypatch: Any) -> None:
    monkeypatch.setenv(SPAN_CITE_CAP_ENV, "3")
    sections = {"Efficacy": _six_padding_sentences()}

    async def _never(system: str, prompt: str) -> Any:  # pragma: no cover
        raise AssertionError("LLM must not be called for non-grouped padding")

    out, telem = asyncio.run(
        dedup_pass(sections, _never, section_order=["Efficacy"])
    )
    assert sum(1 for s in out["Efficacy"] if _SPAN_TOKEN in s) == 3
    assert telem["n_span_cite_dropped"] == 3


def test_cap_one_keeps_single_citation() -> None:
    sections = {"Efficacy": _six_padding_sentences()}
    out, _ = apply_span_cite_cap(sections, cap=1, section_order=["Efficacy"])
    assert sum(1 for s in out["Efficacy"] if _SPAN_TOKEN in s) == 1


def test_cap_counts_span_across_multiple_sections() -> None:
    """The cap is GLOBAL across sections, not per-section."""
    s = _six_padding_sentences()
    sections = {"Efficacy": s[:3], "Safety": s[3:]}
    out, telem = apply_span_cite_cap(
        sections, cap=3, section_order=["Efficacy", "Safety"]
    )
    total = sum(
        1 for sec in out.values() for x in sec if _SPAN_TOKEN in x
    )
    assert total == 3
    # First section fills the cap; second section's 3 are all dropped.
    assert out["Efficacy"] == s[:3]
    assert out["Safety"] == []
    assert telem["n_span_cite_dropped"] == 3


# ─────────────────────────────────────────────────────────────────────────
# (c) nothing unverified introduced
# ─────────────────────────────────────────────────────────────────────────


def test_cap_introduces_nothing_unverified() -> None:
    """Every surviving sentence is a VERBATIM member of the input.

    The cap only DROPS; it never rewrites, paraphrases, or fabricates. So the
    survivor set is a strict subset of the original sentences — no new (and
    thus possibly unverified) text can appear.
    """
    sections = {"Efficacy": _six_padding_sentences()}
    original = set(_six_padding_sentences())
    out, _ = apply_span_cite_cap(sections, cap=3, section_order=["Efficacy"])
    for s in out["Efficacy"]:
        assert s in original, f"cap introduced a non-original sentence: {s!r}"


# ─────────────────────────────────────────────────────────────────────────
# (d) a sentence still contributing an under-cap span is never dropped
# ─────────────────────────────────────────────────────────────────────────


def test_sentence_with_under_cap_span_is_kept() -> None:
    """A sentence citing BOTH a saturated span AND a fresh span is KEPT.

    The cap drops a sentence ONLY when EVERY span it cites is already at cap.
    A sentence that still brings an under-cap span carries real,
    not-yet-over-concentrated evidence and must survive.
    """
    other = "[#ev:acemoglu:0-800]"
    sentences = _six_padding_sentences()[:3]  # fills brynjolfsson:0-800 at cap=3
    # 4th sentence: over-cap brynjolfsson span PLUS a brand-new acemoglu span.
    sentences.append(
        f"Institutions also mediated the effect {_SPAN_TOKEN}{other}."
    )
    sections = {"Efficacy": sentences}
    out, telem = apply_span_cite_cap(
        sections, cap=3, section_order=["Efficacy"]
    )
    kept = out["Efficacy"]
    # The mixed sentence survives (it brings the fresh acemoglu span).
    assert any(other in s for s in kept)
    assert len(kept) == 4  # nothing dropped: 3 + the mixed one
    assert telem["n_span_cite_dropped"] == 0


def test_pure_over_cap_sentence_is_dropped_but_mixed_survives() -> None:
    """Distinguish a pure-padding excess sentence from a mixed one."""
    other = "[#ev:acemoglu:0-800]"
    sentences = _six_padding_sentences()[:3]
    sentences.append(f"Pure padding restated again {_SPAN_TOKEN}.")  # all-over-cap
    sentences.append(f"Brings a fresh span {_SPAN_TOKEN}{other}.")   # mixed -> keep
    sections = {"Efficacy": sentences}
    out, telem = apply_span_cite_cap(
        sections, cap=3, section_order=["Efficacy"]
    )
    kept = out["Efficacy"]
    assert telem["n_span_cite_dropped"] == 1  # only the pure-padding one
    assert any(other in s for s in kept)
    assert "Pure padding restated again" not in " ".join(kept)


# ─────────────────────────────────────────────────────────────────────────
# (e) sentences without provenance tokens are never dropped
# ─────────────────────────────────────────────────────────────────────────


def test_sentences_without_tokens_never_dropped() -> None:
    sections = {
        "Efficacy": _six_padding_sentences() + [
            "This bare sentence has no provenance token and stays.",
            "Neither does this transitional sentence.",
        ]
    }
    out, _ = apply_span_cite_cap(sections, cap=3, section_order=["Efficacy"])
    kept = out["Efficacy"]
    assert "This bare sentence has no provenance token and stays." in kept
    assert "Neither does this transitional sentence." in kept


def test_distinct_spans_not_conflated() -> None:
    """Two DIFFERENT spans are counted independently — capping one leaves the
    other fully intact."""
    a = "[#ev:brynjolfsson:0-800]"
    b = "[#ev:brynjolfsson:801-1600]"  # different span of same source
    sections = {
        "Efficacy": [
            f"Claim a1 {a}.", f"Claim a2 {a}.", f"Claim a3 {a}.",
            f"Claim a4 {a}.",  # 4th of span a -> dropped at cap=3
            f"Claim b1 {b}.", f"Claim b2 {b}.",  # span b only 2x -> all kept
        ]
    }
    out, telem = apply_span_cite_cap(
        sections, cap=3, section_order=["Efficacy"]
    )
    kept = out["Efficacy"]
    assert sum(1 for s in kept if a in s) == 3
    assert sum(1 for s in kept if b in s) == 2  # untouched
    assert telem["n_span_cite_dropped"] == 1
    assert telem["n_spans_over_cap"] == 1  # only span a saturated


# ─────────────────────────────────────────────────────────────────────────
# (f) faithfulness lock — the module exposes no gate-weakening path
# ─────────────────────────────────────────────────────────────────────────


def test_module_does_not_touch_verify_gates() -> None:
    """The cap module must not import or reference strict_verify / NLI / 4-role.

    A guard that the I-pipe-007 change stayed in its lane: selection only.
    """
    import inspect

    from src.polaris_graph.generator import fact_dedup

    src = inspect.getsource(fact_dedup.apply_span_cite_cap)
    for forbidden in ("strict_verify", "entailment", "nli", "four_role", "4-role"):
        assert forbidden not in src.lower(), (
            f"span-cite cap unexpectedly references {forbidden!r}"
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
