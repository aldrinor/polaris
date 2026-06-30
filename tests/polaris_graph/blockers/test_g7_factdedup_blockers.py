"""Regression tests: fact_dedup NO LONGER caps per-source citations — I-deepfix-001.

§-1.3 lock (WEIGHT-AND-CONSOLIDATE, never FILTER-AND-CAP): the per-source span
citation cap `PG_SPAN_PER_SOURCE_CITE_CAP` (the operator's EXACT named §-1.3
BANNED bolt-on, I-pipe-007 #1232) has been DELETED from
`src/polaris_graph/generator/fact_dedup.py` — the knob, its drop path
(`apply_span_cite_cap` / `_read_span_cite_cap` / `_sentence_spans`), and both
`dedup_pass` call sites are gone. Repetition of an already-verified span is
corroboration, never padding to drop.

These tests assert the post-deletion contract:
  (a) `dedup_pass` keeps EVERY padding sentence even when a stray
      `PG_SPAN_PER_SOURCE_CITE_CAP=N` is set in the environment (the env is now
      inert — there is no code that reads it).
  (b) the deleted symbols are truly gone from the module's public surface (a
      structural guard against a silent re-introduction).
"""
from __future__ import annotations

import asyncio
from typing import Any

import pytest

from src.polaris_graph.generator import fact_dedup
from src.polaris_graph.generator.fact_dedup import dedup_pass


# A single 800-char-style span cited 6x. Each sentence carries a DISTINCT
# subject so it is NOT a numeric-dedup group (no shared signature) — exactly the
# case the old cap targeted. §-1.3: all 6 are kept (corroboration, not padding).
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


async def _never_called_llm(system: str, prompt: str) -> Any:  # pragma: no cover
    raise AssertionError("LLM must not be called for non-grouped padding")


def test_env_unset_keeps_all_via_dedup_pass(monkeypatch: Any) -> None:
    """Env unset => dedup_pass keeps every padding sentence (no cap exists)."""
    monkeypatch.delenv("PG_SPAN_PER_SOURCE_CITE_CAP", raising=False)
    sections = {"Efficacy": _six_padding_sentences()}
    out, telem = asyncio.run(
        dedup_pass(sections, _never_called_llm, section_order=["Efficacy"])
    )
    assert out["Efficacy"] == _six_padding_sentences()
    # The deleted-cap telemetry keys are gone; the dedup telemetry remains.
    assert "n_span_cite_dropped" not in telem
    assert "n_spans_over_cap" not in telem


def test_stray_env_value_is_inert_no_cap(monkeypatch: Any) -> None:
    """A stray PG_SPAN_PER_SOURCE_CITE_CAP=3 can NO LONGER drop a citation.

    The bolt-on was deleted, so the env is inert: all 6 same-span sentences
    survive (§-1.3 keep-all — repetition is corroboration).
    """
    monkeypatch.setenv("PG_SPAN_PER_SOURCE_CITE_CAP", "3")
    sections = {"Efficacy": _six_padding_sentences()}
    out, _ = asyncio.run(
        dedup_pass(sections, _never_called_llm, section_order=["Efficacy"])
    )
    span_uses = sum(1 for s in out["Efficacy"] if _SPAN_TOKEN in s)
    assert span_uses == 6  # nothing dropped — the cap is gone


def test_cap_symbols_are_deleted() -> None:
    """Structural guard: the deleted bolt-on must not silently re-appear."""
    for removed in (
        "apply_span_cite_cap",
        "_read_span_cite_cap",
        "_sentence_spans",
        "SPAN_CITE_CAP_ENV",
    ):
        assert not hasattr(fact_dedup, removed), (
            f"the §-1.3 BANNED span-cite cap symbol {removed!r} was re-introduced"
        )


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-v"]))
