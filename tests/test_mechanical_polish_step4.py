"""STEP 4 — Pillar-4 mechanical-polish regression tests.

Locks the five render-only, default-OFF polish behaviours added to the champion
render path:

  (1) citation_truncation_normalizer wired into the per-section render so the
      `].[` inline-glue artifact is collapsed to `][`
      (PG_CITATION_TRUNCATION_NORMALIZE).
  (2) bibliography deduped by WORK identity via same_work_groups
      (PG_BIBLIO_WORK_DEDUP) — one [N] per underlying work, no orphaned marker.
  (3) empty-URL references render with no dangling em-dash (PG_REFERENCE_POLISH).
  (4) the pipeline-internal "(tier T)" tag stripped from rendered references
      (PG_REFERENCE_POLISH).
  (5) the deterministic Limitations fallback humanized (PG_LIMITATIONS_HUMANIZE).

Every flag is default-OFF: each test also asserts the OFF path is byte-identical
to the legacy render. No live compose, no LLM — pure string/unit assertions.
"""
from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

from src.polaris_graph.generator.multi_section_generator import (
    _apply_citation_truncation_normalize,
    _build_ev_to_canonical,
    _merge_bibliographies,
    _remap_section_markers_to_global,
    SectionResult,
)

_ROOT = Path(__file__).resolve().parents[1]


def _load_driver():
    """Import the champion compose driver as a module (it's a script)."""
    spec = importlib.util.spec_from_file_location(
        "compose_driver_step4",
        _ROOT / "scripts" / "compose_agentic_report_s3gear329.py",
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


# ─────────────────────────────────────────────────────────────────────────────
# Target 1: `].[` -> `][`
# ─────────────────────────────────────────────────────────────────────────────

_GLUE_TEXT = "The effect held across studies [3].[4] and remained robust.[5]"


def test_truncation_normalize_off_is_byte_identical(monkeypatch):
    monkeypatch.delenv("PG_CITATION_TRUNCATION_NORMALIZE", raising=False)
    assert _apply_citation_truncation_normalize(_GLUE_TEXT) == _GLUE_TEXT
    assert "].[" in _apply_citation_truncation_normalize(_GLUE_TEXT)


def test_truncation_normalize_on_collapses_glue(monkeypatch):
    monkeypatch.setenv("PG_CITATION_TRUNCATION_NORMALIZE", "1")
    out = _apply_citation_truncation_normalize(_GLUE_TEXT)
    assert "].[" not in out, f"the ].[ glue artifact survived: {out!r}"
    assert "][" in out  # collapsed, markers preserved
    # markers themselves byte-preserved
    assert set(re.findall(r"\[(\d+)\]", out)) == {"3", "4", "5"}


def test_truncation_normalize_empty_input_is_noop(monkeypatch):
    monkeypatch.setenv("PG_CITATION_TRUNCATION_NORMALIZE", "1")
    assert _apply_citation_truncation_normalize("") == ""


# ─────────────────────────────────────────────────────────────────────────────
# Target 2: bibliography dedup by work identity
# ─────────────────────────────────────────────────────────────────────────────

# Two evidence rows that are the SAME underlying work (a preprint + its published
# copy), plus one distinct work.
_SLICE = [
    [
        {"num": 1, "evidence_id": "ev_a", "url": "http://a", "tier": "T1", "statement": "same work A"},
        {"num": 2, "evidence_id": "ev_b", "url": "http://b", "tier": "T2", "statement": "same work A (dup)"},
        {"num": 3, "evidence_id": "ev_c", "url": "http://c", "tier": "T1", "statement": "distinct work C"},
    ]
]

_SAME_WORK_GROUPS = [
    {
        "member_evidence_ids": ["ev_a", "ev_b"],
        "canonical_index": 0,
        "same_work_id": "doi:10.1/xyz",
    }
]


def test_build_ev_to_canonical_folds_members():
    m = _build_ev_to_canonical(_SAME_WORK_GROUPS)
    assert m == {"ev_a": "ev_a", "ev_b": "ev_a"}


def test_build_ev_to_canonical_skips_singletons_and_malformed():
    groups = [
        {"member_evidence_ids": ["ev_x"]},          # <2 members -> no fold
        {"member_evidence_ids": []},                 # empty
        {"not_a_group_key": 1},                       # malformed
        "junk",                                       # non-mapping
    ]
    assert _build_ev_to_canonical(groups) == {}


def test_biblio_dedup_off_keeps_both_work_rows(monkeypatch):
    monkeypatch.delenv("PG_BIBLIO_WORK_DEDUP", raising=False)
    # even with a payload, flag OFF => legacy evidence_id-only dedup => 3 rows
    merged = _merge_bibliographies(_SLICE, _SAME_WORK_GROUPS)
    assert [b["evidence_id"] for b in merged] == ["ev_a", "ev_b", "ev_c"]
    assert [b["num"] for b in merged] == [1, 2, 3]
    # no internal key leaks on the OFF path
    assert all("_member_evidence_ids" not in b for b in merged)


def test_biblio_dedup_no_payload_is_byte_identical(monkeypatch):
    monkeypatch.setenv("PG_BIBLIO_WORK_DEDUP", "1")
    # flag ON but no same_work_groups => byte-identical legacy behaviour
    merged = _merge_bibliographies(_SLICE, None)
    assert [b["evidence_id"] for b in merged] == ["ev_a", "ev_b", "ev_c"]
    assert all("_member_evidence_ids" not in b for b in merged)


def test_biblio_dedup_on_folds_same_work(monkeypatch):
    monkeypatch.setenv("PG_BIBLIO_WORK_DEDUP", "1")
    merged = _merge_bibliographies(_SLICE, _SAME_WORK_GROUPS)
    # ev_a and ev_b fold to ONE entry; ev_c stays distinct => 2 entries
    ev_ids = [b["evidence_id"] for b in merged]
    assert ev_ids == ["ev_a", "ev_c"], f"expected work-dedup, got {ev_ids}"
    assert [b["num"] for b in merged] == [1, 2]
    # the surviving canonical entry carries its folded members for the remap
    canon = merged[0]
    assert canon["_member_evidence_ids"] == ["ev_a", "ev_b"]
    # NO duplicate-work statements remain in the bibliography
    statements = [b["statement"] for b in merged]
    assert "same work A (dup)" not in statements


def test_biblio_dedup_remap_resolves_folded_member_marker(monkeypatch):
    """The whole point: a section that cited the NON-canonical member (ev_b -> [2])
    must still resolve to the single surviving [N], never an orphan."""
    monkeypatch.setenv("PG_BIBLIO_WORK_DEDUP", "1")
    global_biblio = _merge_bibliographies(_SLICE, _SAME_WORK_GROUPS)
    # section prose cites section-local [1] (ev_a), [2] (ev_b), [3] (ev_c)
    sect = SectionResult(
        title="S",
        focus="",
        ev_ids_assigned=[],
        raw_draft="",
        rewritten_draft="",
        verified_text="Claim one [1]. Claim two [2]. Claim three [3].",
        biblio_slice=_SLICE[0],
        sentences_verified=3,
        sentences_dropped=0,
        regen_attempted=False,
        dropped_due_to_failure=False,
    )
    remapped = _remap_section_markers_to_global([sect], global_biblio)
    text = remapped[0]
    # ev_a -> global 1, ev_b (folded) -> global 1, ev_c -> global 2
    assert text == "Claim one [1]. Claim two [1]. Claim three [2].", text
    # every marker resolves to a real bibliography num (no orphan)
    markers = {int(m) for m in re.findall(r"\[(\d+)\]", text)}
    nums = {b["num"] for b in global_biblio}
    assert markers <= nums


# ─────────────────────────────────────────────────────────────────────────────
# Targets 3 + 4: reference render cleanup (driver-side)
# ─────────────────────────────────────────────────────────────────────────────

_REF_WITH_URL = {"num": 5, "statement": "A finding", "url": "http://example.com", "tier": "T1"}
_REF_NO_URL = {"num": 6, "statement": "A urlless finding", "url": "", "tier": "T4"}


def test_reference_polish_off_is_byte_identical(monkeypatch):
    drv = _load_driver()
    monkeypatch.delenv("PG_REFERENCE_POLISH", raising=False)
    line = drv._render_reference_line(_REF_WITH_URL)
    assert line == "[5] A finding — http://example.com (tier T1)\n"
    # legacy dangling-dash + tier leak preserved on OFF path for the no-url case
    line2 = drv._render_reference_line(_REF_NO_URL)
    assert line2 == "[6] A urlless finding —  (tier T4)\n"


def test_reference_polish_on_strips_tier(monkeypatch):
    drv = _load_driver()
    monkeypatch.setenv("PG_REFERENCE_POLISH", "1")
    line = drv._render_reference_line(_REF_WITH_URL)
    assert "(tier" not in line, f"tier leak survived: {line!r}"
    assert line == "[5] A finding — http://example.com\n"


def test_reference_polish_on_drops_empty_url_tail(monkeypatch):
    drv = _load_driver()
    monkeypatch.setenv("PG_REFERENCE_POLISH", "1")
    line = drv._render_reference_line(_REF_NO_URL)
    # no dangling em-dash, no blank url, no tier
    assert "(tier" not in line
    assert " —  " not in line
    assert line == "[6] A urlless finding\n"


def test_reference_block_on_has_no_leaks(monkeypatch):
    """Render a whole References block and assert no (tier and no dangling dash."""
    drv = _load_driver()
    monkeypatch.setenv("PG_REFERENCE_POLISH", "1")
    biblio = [_REF_WITH_URL, _REF_NO_URL]
    block = "\n\n## References\n" + "".join(drv._render_reference_line(b) for b in biblio)
    assert "(tier" not in block
    assert "—  " not in block  # em-dash followed by empty url


# ─────────────────────────────────────────────────────────────────────────────
# Target 5: Limitations humanization
# ─────────────────────────────────────────────────────────────────────────────


class _EmptyResponse:
    """A generate() result with empty content -> forces the deterministic fallback."""

    content = ""
    input_tokens = 0
    output_tokens = 0


class _StubClient:
    """Records the `system` prompt it was handed, returns empty content (no network)."""

    last_system = None

    def __init__(self, *a, **k):
        pass

    async def generate(self, *, system=None, **kwargs):
        _StubClient.last_system = system
        return _EmptyResponse()

    async def close(self):
        pass


def _patch_limitations_llm(monkeypatch):
    """Patch the lazily-imported OpenRouter seam so _call_limitations makes NO
    network call and always drops to the deterministic fallback."""
    import src.polaris_graph.llm.openrouter_client as orc

    _StubClient.last_system = None
    monkeypatch.setattr(orc, "OpenRouterClient", _StubClient)
    monkeypatch.setattr(orc, "set_reasoning_call_context", lambda **k: None)


@pytest.mark.asyncio
async def test_limitations_fallback_off_is_telemetry_speak(monkeypatch):
    from src.polaris_graph.generator import multi_section_generator as msg

    monkeypatch.delenv("PG_LIMITATIONS_HUMANIZE", raising=False)
    _patch_limitations_llm(monkeypatch)
    text, _, _ = await msg._call_limitations(
        tier_fractions={"T1": 0.09},
        contradictions=[{"subject": "effect size", "predicate": "magnitude"}],
        date_range={"start": "2015"},
        model="x",
        temperature=0.3,
        max_tokens=400,
    )
    # legacy telemetry-speak strings present (byte-identical OFF path)
    assert "Only 9% of the corpus is T1 peer-reviewed primary research." in text
    assert "Sources disagree on effect size / magnitude" in text
    assert "Evidence horizon begins 2015" in text
    # OFF path handed the LLM the legacy system prompt
    assert _StubClient.last_system == msg.LIMITATIONS_SYSTEM_PROMPT


@pytest.mark.asyncio
async def test_limitations_fallback_on_is_humanized(monkeypatch):
    from src.polaris_graph.generator import multi_section_generator as msg

    monkeypatch.setenv("PG_LIMITATIONS_HUMANIZE", "1")
    _patch_limitations_llm(monkeypatch)
    text, _, _ = await msg._call_limitations(
        tier_fractions={"T1": 0.09},
        contradictions=[{"subject": "effect size", "predicate": "magnitude"}],
        date_range={"start": "2015"},
        model="x",
        temperature=0.3,
        max_tokens=400,
    )
    # telemetry jargon gone from the fallback prose
    assert "corpus" not in text.lower()
    assert "evidence horizon" not in text.lower()
    assert "T1 peer-reviewed" not in text
    # numbers + facts preserved, in reader-facing prose
    assert "9%" in text
    assert "effect size" in text
    assert "2015" in text
    assert text.startswith("Limitations:")
    # ON path handed the LLM the humanized system prompt
    assert _StubClient.last_system == msg.LIMITATIONS_SYSTEM_PROMPT_HUMANIZED
