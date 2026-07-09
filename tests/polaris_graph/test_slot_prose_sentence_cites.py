"""N5 (I-deepfix-001 wave-2) — slot-prose per-sub-sentence citations (FIX-1) and
the render-seam fragment-snap gate (FIX-2).

Offline, CPU-only, no network/LLM/GPU. The entailment judge is set OFF for the
e2e leg so verify_sentence_provenance runs its deterministic legs only.
"""
import os

import pytest

from src.polaris_graph.generator.slot_fill import (
    SlotFieldFill,
    SlotFillPayload,
    render_slot_prose,
)
from src.polaris_graph.generator.contract_section_runner import (
    _snap_fragment_kept_svs,
    _verify_one_stream,
)
from src.polaris_graph.generator.live_deepseek_generator import (
    _rewrite_draft_with_spans,
)
from src.polaris_graph.generator.provenance_generator import (
    ProvenanceToken,
    SentenceVerification,
    split_into_sentences,
    strict_verify,
    verify_sentence_provenance,
)

_FIXTURE = os.path.join(
    os.path.dirname(__file__), os.pardir, "fixtures", "eloundou_direct_quote.txt",
)
_BOUND = "eloundou_gpts_are_gpts"

# The two multi-sentence slot-field values copied from the drb_72 run — each welds
# a fragment cut MID source sentence.
_V_EXPOSURE = (
    "a framework for evaluating the potential impacts of large-language models "
    "(LLMs) and associated technologies on work by considering their relevance "
    "to the tasks workers perform in their jobs. By applying this framework "
    "(with both humans and using an LLM)"
)
_V_HEADLINE = (
    "roughly 1.8% of jobs could have over half their tasks affected by LLMs with "
    "simple interfaces and general training. When accounting for current and "
    "likely future software developments that complement LLM capabilities, this "
    "share jumps to just over 46% of jobs."
)


def _direct_quote() -> str:
    with open(_FIXTURE, encoding="utf-8") as fh:
        return fh.read().strip()


def _payload() -> SlotFillPayload:
    fields = (
        SlotFieldFill("exposure_method", "extracted", _V_EXPOSURE, _BOUND, _V_EXPOSURE),
        SlotFieldFill(
            "headline_exposure_estimate", "extracted", _V_HEADLINE, _BOUND, _V_HEADLINE,
        ),
    )
    return SlotFillPayload(
        slot_id="genai_slot",
        entity_id=_BOUND,
        subsection_title="Generative AI Evidence",
        bound_ev_id=_BOUND,
        fields=fields,
        provenance_class="FRAME_ANCHORED",
    )


# ── TEST A — flag OFF byte-identical (golden string) ───────────────────────
def test_a_flag_off_byte_identical(monkeypatch):
    monkeypatch.delenv("PG_SLOT_PROSE_SENTENCE_CITES", raising=False)
    golden = (
        f"Exposure method: {_V_EXPOSURE} [{_BOUND}]. "
        f"Headline exposure estimate: {_V_HEADLINE} [{_BOUND}]."
    )
    assert render_slot_prose(_payload()) == golden
    # Explicit "0" also byte-identical.
    monkeypatch.setenv("PG_SLOT_PROSE_SENTENCE_CITES", "0")
    assert render_slot_prose(_payload()) == golden


# ── TEST B — flag ON, unit shape ───────────────────────────────────────────
def test_b_flag_on_each_subsentence_cited(monkeypatch):
    monkeypatch.setenv("PG_SLOT_PROSE_SENTENCE_CITES", "1")
    rendered = render_slot_prose(_payload())
    parts = split_into_sentences(rendered)
    assert parts, "rendered prose split into >=1 sentence"
    marker = f"[{_BOUND}]"
    for part in parts:
        assert part.count(marker) == 1, f"exactly one marker per part: {part!r}"
        assert part != f"{marker}.", "no bare orphan marker fragment"
        # marker sits BEFORE terminal punctuation (…] . not . […])
        assert part.rstrip().endswith((f"{marker}.", f"{marker}!", f"{marker}?")), part
    # Each field label appears exactly once.
    assert rendered.count("Exposure method:") == 1
    assert rendered.count("Headline exposure estimate:") == 1


# ── TEST C — e2e through the REAL verify machinery ─────────────────────────
def _run_stream(raw_draft, evidence_pool):
    return _verify_one_stream(
        raw_draft=raw_draft,
        evidence_pool=evidence_pool,
        contract_entity_ids={_BOUND},
        rewrite_fn=_rewrite_draft_with_spans,
        strict_verify_fn=strict_verify,
        allow_rescue=True,
        stream_label="test",
    )


def test_c_flag_on_1p8pct_antecedent_survives_in_order(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    evidence_pool = {_BOUND: {"evidence_id": _BOUND, "direct_quote": _direct_quote()}}

    # Flag ON — every sub-sentence carries its own citation.
    monkeypatch.setenv("PG_SLOT_PROSE_SENTENCE_CITES", "1")
    kept, _resc, dropped, _tot, _rw = _run_stream(
        render_slot_prose(_payload()), evidence_pool,
    )
    dropped_no_tok_18 = [
        sv for sv in dropped
        if "1.8%" in getattr(sv, "sentence", "")
        and getattr(sv, "failure_reasons", []) == ["no_provenance_token"]
    ]
    assert not dropped_no_tok_18, "1.8% antecedent must NOT drop for no_provenance_token"
    kept_texts = [getattr(sv, "sentence", "") for sv in kept]
    idx_18 = next((i for i, s in enumerate(kept_texts) if "roughly 1.8%" in s), None)
    idx_share = next(
        (i for i, s in enumerate(kept_texts) if "this share jumps" in s), None,
    )
    assert idx_18 is not None, "a kept sentence carries 'roughly 1.8%'"
    assert idx_share is not None, "a kept sentence carries 'this share jumps'"
    assert idx_18 < idx_share, "1.8% antecedent renders BEFORE 'this share jumps'"


def test_c_flag_off_reproduces_the_bug(monkeypatch):
    # LAW II Definition-of-Fixed: the reproducible failing baseline.
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.delenv("PG_SLOT_PROSE_SENTENCE_CITES", raising=False)
    evidence_pool = {_BOUND: {"evidence_id": _BOUND, "direct_quote": _direct_quote()}}
    _kept, _resc, dropped, _tot, _rw = _run_stream(
        render_slot_prose(_payload()), evidence_pool,
    )
    dropped_no_tok_18 = [
        sv for sv in dropped
        if "1.8%" in getattr(sv, "sentence", "")
        and getattr(sv, "failure_reasons", []) == ["no_provenance_token"]
    ]
    assert dropped_no_tok_18, "flag OFF reproduces the 1.8% no_provenance_token drop"


# ── TEST D — FIX 2 fragment-snap gate ──────────────────────────────────────
def _mk_sv(sentence, start, end):
    tok = ProvenanceToken(_BOUND, start, end, f"[#ev:{_BOUND}:{start}-{end}]")
    return SentenceVerification(sentence=sentence, tokens=[tok], is_verified=True)


def test_d_snap_expands_fragment_flag_on(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_SLOT_FRAGMENT_SNAP", "1")
    evidence_pool = {_BOUND: {"evidence_id": _BOUND, "direct_quote": _direct_quote()}}
    frag = _mk_sv(
        f"By applying this framework (with both humans and using an LLM) "
        f"[#ev:{_BOUND}:0-800].", 0, 800,
    )
    control = _mk_sv(
        f"When accounting for current and likely future software developments "
        f"that complement LLM capabilities, this share jumps to just over 46% of "
        f"jobs [#ev:{_BOUND}:0-800].", 0, 800,
    )
    out = _snap_fragment_kept_svs([frag, control], evidence_pool)
    assert len(out) == 2, "snap never drops — count unchanged"
    assert "we estimate that roughly 1.8%" in getattr(out[0], "sentence", ""), (
        "fragment expanded to its full covering source sentence"
    )
    # The control (already a complete source sentence) passes through untouched.
    assert out[1] is control, "complete-sentence SV passes through byte-identical"


def test_d_snap_flag_off_untouched(monkeypatch):
    monkeypatch.delenv("PG_SLOT_FRAGMENT_SNAP", raising=False)
    evidence_pool = {_BOUND: {"evidence_id": _BOUND, "direct_quote": _direct_quote()}}
    frag = _mk_sv(f"By applying this framework [#ev:{_BOUND}:0-40].", 0, 40)
    svs = [frag]
    out = _snap_fragment_kept_svs(svs, evidence_pool)
    assert out is svs, "flag OFF returns the same list object (byte-identical)"


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(pytest.main([__file__, "-q"]))
