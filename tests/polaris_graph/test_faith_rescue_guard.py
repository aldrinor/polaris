"""I-faith-001 regression: rescue drop-reason guard (Fix A) + integer SUBSET (Fix D).

Locks the two localized fixes that close the run-9 Brynjolfsson faithfulness
leak (fabricated "14 percent" / "35 percent" cited against a 15%-only span):

  Fix A — ``contract_section_runner._drop_is_numeric`` / the M-69 Fix #4 rescue
          loop. The rescue laundered ANY contract-entity sentence back into
          ``kept`` keyed only on the entity id, ignoring WHY it dropped. A
          sentence dropped for a NUMERIC reason
          (``number_not_in_any_cited_span`` / ``no_integer_overlap_any_cited_span``)
          must NEVER be rescued. Legitimate content-overlap drops (the honest
          "not extractable" slot gap-disclosures, which drop for
          ``no_content_word_overlap_any_cited_span``) MUST still be rescued.

  Fix D — ``provenance_generator.verify_sentence_provenance`` integer check is
          now SUBSET, not intersection: EVERY sentence integer must be present
          in the cited spans (keeping the local-window fallback for the
          missing integers). "15 percent over 35 weeks" against a 15-only span
          drops on the missing 35 (previously passed on the 15 alone).

  Fix B — ``contract_section_runner._verify_one_stream`` STREAM SEPARATION.
          The deterministic (M-58 / M-70 verbatim-guarded) prose and the
          free-form narrative LLM paragraph are now verified in SEPARATE
          passes. The M-69 contract-entity rescue is applied ONLY to the
          deterministic stream (``allow_rescue=True``); the narrative stream
          is rescue-INELIGIBLE (``allow_rescue=False``), so a narrative
          sentence that fails ``verify_sentence_provenance`` is never
          laundered back into ``kept`` — closing the qualitative-fabrication
          leak (attrition / CSAT / partial-equilibrium) that Fix A alone could
          not catch (those carry no fabricated integer).

Design (CLAUDE.md §9.4 — no mocked evidence DB, no unittest.mock):
  * The dropped ``SentenceVerification`` objects are produced by the REAL
    production verifier ``verify_sentence_provenance`` so the
    ``failure_reasons`` strings are real, not hand-typed.
  * The guard predicate under test is the REAL module-level
    ``_drop_is_numeric`` imported from ``contract_section_runner`` (the same
    function the rescue loop calls), not a reimplementation.
  * Evidence pools are plain ``dict`` rows with a ``direct_quote`` field — the
    exact shape the production verifier consumes.
  * The entailment judge is forced OFF so the tests run OFFLINE (no GPU / no
    OpenRouter call) and isolate the MECHANICAL numeric + content-overlap
    checks that the two fixes touch.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure repo root on sys.path (mirrors the sibling verifier tests).
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from src.polaris_graph.clinical_generator import strict_verify as _clinical_sv  # noqa: E402
from src.polaris_graph.generator.contract_section_runner import (  # noqa: E402
    _NUMERIC_DROP_PREFIXES,
    _drop_is_numeric,
    _verify_one_stream,
)
from src.polaris_graph.generator.live_deepseek_generator import (  # noqa: E402
    _rewrite_draft_with_spans,
)
from src.polaris_graph.generator.provenance_generator import (  # noqa: E402
    strict_verify,
    verify_sentence_provenance,
)

# The contract entity id used across these cases (Brynjolfsson run-9). It is a
# contract entity, so absent the Fix A drop-reason guard the rescue would
# launder every dropped sentence carrying its token back into ``kept``.
_CONTRACT_EV_ID = "brynjolfsson_genai_at_work"

# The real cited span both report sentences cite: productivity rose 15% on
# average across 5,172 agents. It contains "15" / "5172" / "172" but NOT "14"
# or "35".
_BRYNJOLFSSON_SPAN = (
    "Abstract We study the staggered introduction of a generative AI based "
    "conversational assistant using data from 5,172 customer-support agents. "
    "Access to AI assistance increases worker productivity, as measured by "
    "issues resolved per hour, by 15% on average, with substantial "
    "heterogeneity across workers."
)


@pytest.fixture(autouse=True)
def _offline_entailment(monkeypatch):
    """Force the entailment judge + verification-mode deltas OFF.

    Isolates the mechanical numeric + content-overlap checks and guarantees no
    network/GPU call is attempted during the regression.
    """
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_VERIFICATION_MODE", "off")


def _brynjolfsson_pool() -> dict[str, dict[str, str]]:
    return {_CONTRACT_EV_ID: {"direct_quote": _BRYNJOLFSSON_SPAN}}


# ─────────────────────────────────────────────────────────────────────────────
# (1) Fix A — a NUMERIC-dropped contract sentence is NOT rescued.
# ─────────────────────────────────────────────────────────────────────────────
def test_numeric_dropped_contract_sentence_is_not_rescued():
    """The fabricated "14 percent" sentence drops for a numeric reason and the
    REAL ``_drop_is_numeric`` guard marks it rescue-INELIGIBLE."""
    pool = _brynjolfsson_pool()
    span_len = len(_BRYNJOLFSSON_SPAN)
    sentence = (
        "The primary finding revealed that access to the conversational "
        "assistant raised agent productivity, as measured by resolved customer "
        "issues per hour, by approximately 14 percent on average across the "
        f"sample [#ev:{_CONTRACT_EV_ID}:0-{span_len}]."
    )

    sv = verify_sentence_provenance(sentence, pool)

    # The production verifier must drop it (14 is not in the cited span).
    assert sv.is_verified is False
    # It drops for a NUMERIC reason — the leak class the guard targets.
    assert any(
        str(r).split(":", 1)[0] in _NUMERIC_DROP_PREFIXES
        for r in sv.failure_reasons
    ), sv.failure_reasons
    # The REAL rescue guard excludes it from rescue.
    assert _drop_is_numeric(sv) is True


# ─────────────────────────────────────────────────────────────────────────────
# (2) Fix A — a content-overlap-dropped "not extractable" disclosure IS still
#     rescue-eligible (the guard does NOT over-drop honest gap disclosures).
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.skip(reason=(
    "The writer-side no_content_word_overlap_any_cited_span drop this rescue guard targets was REMOVED per 2026-07-10 UNFREEZE (fix 2, GH I-arch-s5-001): with the content-word-overlap floor deleted the sentence is no longer dropped for that reason, so there is nothing to rescue. The NLI entailment judge is now the semantic bar (live-judge surface, not offline)."
))
def test_content_overlap_dropped_not_extractable_sentence_is_rescued():
    """The honest "not extractable" slot gap-disclosure drops for a NON-numeric
    (content-overlap) reason, so the REAL guard keeps it rescue-eligible."""
    # An evidence span sharing essentially no content words with the
    # deterministic gap-disclosure prose, so the verifier drops it on the
    # content-word overlap floor — NOT on a numeric check (the sentence has no
    # numbers at all).
    unrelated_span = (
        "The provincial electricity supply is dominated by hydroelectric "
        "generation across the northern grid corridor."
    )
    pool = {_CONTRACT_EV_ID: {"direct_quote": unrelated_span}}
    span_len = len(unrelated_span)
    # The exact deterministic "not extractable" disclosure shape emitted by
    # render_slot_prose for a not_extractable field (no numbers).
    sentence = (
        "Comparator arm: not extractable from available primary content "
        f"[#ev:{_CONTRACT_EV_ID}:0-{span_len}]."
    )

    sv = verify_sentence_provenance(sentence, pool)

    # The verifier drops it (content-word overlap floor) ...
    assert sv.is_verified is False
    # ... for a NON-numeric reason. Guard against a vacuous assertion: confirm
    # it did not drop for a numeric reason before asserting rescue-eligibility.
    assert not any(
        str(r).split(":", 1)[0] in _NUMERIC_DROP_PREFIXES
        for r in sv.failure_reasons
    ), sv.failure_reasons
    # Therefore the REAL guard keeps it rescue-eligible.
    assert _drop_is_numeric(sv) is False


def test_not_extractable_disclosure_with_embedded_label_digit_is_rescued():
    """Codex gate P1: a gap-disclosure whose field LABEL has an embedded digit
    (e.g. "Baseline HbA1c") drops for a NUMERIC reason (the verifier reads the
    '1' in 'hba1c') — but it is an HONEST disclosure, NOT a numeric claim, so
    the guard must keep it rescue-eligible. Without the exemption, clinical
    gap-disclosures would vanish from partially-rendered slots."""
    unrelated_span = (
        "The provincial electricity supply is dominated by hydroelectric "
        "generation across the northern grid corridor."
    )
    pool = {_CONTRACT_EV_ID: {"direct_quote": unrelated_span}}
    span_len = len(unrelated_span)
    # Embedded digit in the field label "HbA1c" -> the verifier extracts '1'.
    sentence = (
        "Baseline HbA1c: not extractable from available primary content "
        f"[#ev:{_CONTRACT_EV_ID}:0-{span_len}]."
    )

    sv = verify_sentence_provenance(sentence, pool)

    assert sv.is_verified is False
    # It DID drop for a numeric reason (the embedded '1') — guard against a
    # vacuous test: if it didn't, this test isn't exercising the exemption.
    assert any(
        str(r).split(":", 1)[0] in _NUMERIC_DROP_PREFIXES
        for r in sv.failure_reasons
    ), sv.failure_reasons
    # ...yet the gap-disclosure exemption keeps it rescue-ELIGIBLE.
    assert _drop_is_numeric(sv) is False


# ─────────────────────────────────────────────────────────────────────────────
# (3) Fix D — integer SUBSET: "15 percent over 35 weeks" FAILS against a span
#     containing only 15 (the 35 is missing).
# ─────────────────────────────────────────────────────────────────────────────
def test_integer_subset_fails_when_one_integer_missing_from_span():
    """A mixed supported+fabricated integer claim must FAIL on the missing
    integer — the intersection→subset fix (Fix D). Previously this passed on
    the 15 alone, smuggling the unsupported 35."""
    # A span that contains 15 but NOT 35, with content words ("productivity")
    # that overlap the sentence so only the integer check decides the verdict.
    span = "Worker productivity rose by 15 percent on average across the sample."
    pool = {_CONTRACT_EV_ID: {"direct_quote": span}}
    span_len = len(span)
    sentence = (
        "Worker productivity improved 15 percent over 35 weeks of sustained "
        f"assistant use [#ev:{_CONTRACT_EV_ID}:0-{span_len}]."
    )

    sv = verify_sentence_provenance(sentence, pool)

    # Subset semantics: every sentence integer must be in the span. 35 is not,
    # so the sentence must drop ...
    assert sv.is_verified is False, sv.failure_reasons
    # ... on the integer check, and the missing-integer detail must name 35.
    assert any(
        str(r).startswith("no_integer_overlap_any_cited_span") and "35" in str(r)
        for r in sv.failure_reasons
    ), sv.failure_reasons


# ─────────────────────────────────────────────────────────────────────────────
# (4) Fix B — STREAM SEPARATION. The SAME content-overlap-dropped contract
#     sentence is RESCUED in the deterministic stream but NOT in the narrative
#     stream. The drop reason is NON-numeric for BOTH, so the ONLY thing that
#     can explain the difference is the rescue-eligibility of the stream —
#     isolating Fix B from Fix A (a numeric drop would already be caught by
#     Fix A regardless of stream).
# ─────────────────────────────────────────────────────────────────────────────
def _content_overlap_drop_setup() -> tuple[str, dict[str, dict[str, str]]]:
    """A contract-entity sentence with NO numbers, cited against a span that
    shares essentially no content words → drops on the content-overlap floor
    (a NON-numeric reason), through the REAL rewrite + verify path.

    The bare ``[entity_id]`` marker is converted by the REAL
    ``_rewrite_draft_with_spans`` into a ``[#ev:...]`` span token, so the
    rescue's ``toks[0].evidence_id in contract_entity_ids`` check fires
    exactly as it would in production.
    """
    unrelated_span = (
        "The provincial electricity supply is dominated by hydroelectric "
        "generation across the northern grid corridor."
    )
    pool = {_CONTRACT_EV_ID: {
        "evidence_id": _CONTRACT_EV_ID,
        "direct_quote": unrelated_span,
    }}
    raw_draft = (
        "Comparator arm: not extractable from available primary content "
        f"[{_CONTRACT_EV_ID}]."
    )
    return raw_draft, pool


@pytest.mark.skip(reason=(
    "The writer-side no_content_word_overlap_any_cited_span drop this rescue guard targets was REMOVED per 2026-07-10 UNFREEZE (fix 2, GH I-arch-s5-001): with the content-word-overlap floor deleted the sentence is no longer dropped for that reason, so there is nothing to rescue. The NLI entailment judge is now the semantic bar (live-judge surface, not offline)."
))
def test_fix_b_deterministic_stream_rescues_content_overlap_drop():
    """Deterministic stream (allow_rescue=True): the content-overlap-dropped
    contract sentence IS rescued — preserving the legitimate "not extractable"
    gap-disclosure behavior (the SURPASS-5 25K-char regression fix)."""
    raw_draft, pool = _content_overlap_drop_setup()

    kept, rescued, dropped, total_in, _rw = _verify_one_stream(
        raw_draft=raw_draft,
        evidence_pool=pool,
        contract_entity_ids={_CONTRACT_EV_ID},
        rewrite_fn=_rewrite_draft_with_spans,
        strict_verify_fn=strict_verify,
        allow_rescue=True,
        stream_label="deterministic",
    )

    # Confirm the sentence really dropped at verify (the rescue, not a pass,
    # is what keeps it) AND that it dropped for a NON-numeric reason — so the
    # discriminator vs the narrative case is the stream, not Fix A.
    sv = verify_sentence_provenance(
        f"Comparator arm: not extractable from available primary content "
        f"[#ev:{_CONTRACT_EV_ID}:0-{len(pool[_CONTRACT_EV_ID]['direct_quote'])}].",
        pool,
    )
    assert sv.is_verified is False, sv.failure_reasons
    assert _drop_is_numeric(sv) is False, sv.failure_reasons

    # Deterministic stream rescues it: kept includes the rescued sentence,
    # nothing remains in the final dropped list.
    assert total_in == 1
    assert len(rescued) == 1
    assert len(kept) == 1
    assert len(dropped) == 0


@pytest.mark.skip(reason=(
    "The writer-side no_content_word_overlap_any_cited_span drop this rescue guard targets was REMOVED per 2026-07-10 UNFREEZE (fix 2, GH I-arch-s5-001): with the content-word-overlap floor deleted the sentence is no longer dropped for that reason, so there is nothing to rescue. The NLI entailment judge is now the semantic bar (live-judge surface, not offline)."
))
def test_fix_b_narrative_stream_does_not_rescue_content_overlap_drop():
    """Narrative stream (allow_rescue=False): the IDENTICAL content-overlap-
    dropped contract sentence is NOT rescued — it stays dropped. This is the
    Fix B guarantee: narrative-origin sentences must pass verify on their own,
    so qualitative fabrications can no longer be laundered back by the M-69
    rescue."""
    raw_draft, pool = _content_overlap_drop_setup()

    kept, rescued, dropped, total_in, _rw = _verify_one_stream(
        raw_draft=raw_draft,
        evidence_pool=pool,
        contract_entity_ids={_CONTRACT_EV_ID},
        rewrite_fn=_rewrite_draft_with_spans,
        strict_verify_fn=strict_verify,
        allow_rescue=False,
        stream_label="narrative",
    )

    # Same input, same (non-numeric) drop — but NO rescue in the narrative
    # stream: kept is empty, the sentence stays dropped.
    assert total_in == 1
    assert len(rescued) == 0
    assert len(kept) == 0
    assert len(dropped) == 1
    # And it is the EXACT sentence that the deterministic stream rescued —
    # proving the only difference is stream rescue-eligibility (Fix B), not a
    # different drop class (Fix A).
    assert dropped[0].is_verified is False
    assert _drop_is_numeric(dropped[0]) is False, dropped[0].failure_reasons


# ─────────────────────────────────────────────────────────────────────────────
# (5) Fix C — the QUALITATIVE narrative fabrication (run-9: attrition / CSAT /
#     partial-equilibrium). NO numbers, SHARES content words with the span (so
#     it clears the mechanical content-overlap floor), but is NOT entailed by
#     the span — it can ONLY be caught by the entailment judge. This is the
#     exact leak class Fix A could not close (the drop is NON-numeric). The
#     test proves the narrative stream's rescue-INELIGIBILITY is what closes
#     it: the deterministic stream RESCUES the entailment-dropped sentence
#     (the laundering bug), while the narrative stream keeps it dropped.
#
#     The entailment judge is a plain deterministic stub installed via the
#     established ``_get_judge`` seam (the same surface test_verification_mode_
#     phase0b.py uses — NOT a unittest.mock of the evidence DB, §9.4). It runs
#     OFFLINE (no GPU / OpenRouter) and returns NEUTRAL so the entailment gate
#     fires under PG_STRICT_VERIFY_ENTAILMENT=enforce.
# ─────────────────────────────────────────────────────────────────────────────
class _NeutralJudge:
    """Deterministic offline judge: every cited claim is NEUTRAL (not entailed).

    Plain class, no unittest.mock (§9.4). Models the run-9 qualitative
    fabrication where the narrative claim shares content words with the span
    but is not actually supported by it — only the entailment judge can catch
    this, the mechanical numeric + content-overlap checks pass.
    """

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    def judge(self, sentence: str, span: str) -> tuple[str, str]:
        self.calls.append((sentence, span))
        return "NEUTRAL", "narrative claim not entailed by span"


# A span that SHARES content words ("assistant", "productivity", "agent") with
# the qualitative fabrication and carries NO numbers — so the only check that
# can drop the fabrication is the entailment judge.
_ENTAILMENT_SPAN = (
    "Access to the generative AI assistant increased agent productivity, as "
    "measured by issues resolved per hour, with substantial heterogeneity "
    "across the workforce."
)
# A qualitative fabrication: "reduced attrition" / "improved satisfaction" are
# NOT in the span (run-9 exactly invented attrition + CSAT). No numbers; shares
# enough content words to clear the mechanical content-overlap floor.
_QUALITATIVE_FABRICATION = (
    "The assistant also reduced agent attrition and improved customer "
    "satisfaction across the productivity cohort"
)


def _entailment_pool() -> dict[str, dict[str, str]]:
    return {_CONTRACT_EV_ID: {
        "evidence_id": _CONTRACT_EV_ID,
        "direct_quote": _ENTAILMENT_SPAN,
    }}


def test_qualitative_fabrication_drops_on_entailment_not_numeric(monkeypatch):
    """Baseline for Fix C: the qualitative fabrication is dropped by the REAL
    verifier on the ENTAILMENT check (NOT a numeric or content-overlap reason),
    and the Fix A guard does NOT classify it as a numeric drop — so Fix A alone
    would leave it rescue-eligible. This is the precise gap Fix B/C closes."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    monkeypatch.setenv("PG_VERIFICATION_MODE", "off")
    monkeypatch.setattr(_clinical_sv, "_get_judge", lambda: _NeutralJudge())

    pool = _entailment_pool()
    span_len = len(_ENTAILMENT_SPAN)
    sentence = (
        f"{_QUALITATIVE_FABRICATION} [#ev:{_CONTRACT_EV_ID}:0-{span_len}]."
    )

    sv = verify_sentence_provenance(sentence, pool)

    # Dropped — but on the ENTAILMENT check, not numeric / content-overlap.
    assert sv.is_verified is False, sv.failure_reasons
    assert any(
        str(r).startswith("entailment_failed") for r in sv.failure_reasons
    ), sv.failure_reasons
    # Fix A's numeric guard does NOT catch it (no fabricated integer) — so
    # absent stream separation it would be rescue-eligible. THIS is why Fix A
    # alone is insufficient and Fix B/C is required.
    assert _drop_is_numeric(sv) is False, sv.failure_reasons


def test_fix_c_narrative_stream_drops_entailment_fabrication_not_rescued(
    monkeypatch,
):
    """Fix C guarantee: a qualitative narrative fabrication that fails the
    ENTAILMENT judge is DROPPED in the narrative stream and NOT rescued.

    Run end-to-end through the REAL ``_verify_one_stream`` with the REAL
    rewrite + verify path. The discriminator vs the deterministic stream is
    ONLY rescue-eligibility — the SAME sentence with the SAME (non-numeric,
    entailment) drop reason is RESCUED in the deterministic stream and DROPPED
    in the narrative stream. That isolates the run-9 qualitative leak
    (attrition / CSAT / partial-equilibrium) to the stream's rescue policy, the
    exact closure Fix A could not provide."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "enforce")
    monkeypatch.setenv("PG_VERIFICATION_MODE", "off")
    monkeypatch.setattr(_clinical_sv, "_get_judge", lambda: _NeutralJudge())

    pool = _entailment_pool()
    # Bare-bracket marker → the REAL rewrite converts it to a span token, so the
    # rescue's ``toks[0].evidence_id in contract_entity_ids`` check fires as in
    # production.
    raw_draft = f"{_QUALITATIVE_FABRICATION} [{_CONTRACT_EV_ID}]."

    # Deterministic stream (allow_rescue=True): the entailment-dropped sentence
    # is RESCUED — this is precisely the laundering bug (the rescue cannot tell
    # an entailment fabrication from a legitimate verbatim false-drop).
    det_kept, det_rescued, det_dropped, det_total, _ = _verify_one_stream(
        raw_draft=raw_draft,
        evidence_pool=pool,
        contract_entity_ids={_CONTRACT_EV_ID},
        rewrite_fn=_rewrite_draft_with_spans,
        strict_verify_fn=strict_verify,
        allow_rescue=True,
        stream_label="deterministic",
    )
    assert det_total == 1
    assert len(det_rescued) == 1, (
        "the deterministic stream must rescue the entailment-dropped sentence "
        "(demonstrating the laundering the narrative stream must NOT do)"
    )
    assert len(det_kept) == 1
    assert len(det_dropped) == 0

    # Narrative stream (allow_rescue=False): the IDENTICAL sentence with the
    # IDENTICAL (entailment) drop stays DROPPED — never rescued.
    narr_kept, narr_rescued, narr_dropped, narr_total, _ = _verify_one_stream(
        raw_draft=raw_draft,
        evidence_pool=pool,
        contract_entity_ids={_CONTRACT_EV_ID},
        rewrite_fn=_rewrite_draft_with_spans,
        strict_verify_fn=strict_verify,
        allow_rescue=False,
        stream_label="narrative",
    )
    assert narr_total == 1
    assert len(narr_rescued) == 0
    assert len(narr_kept) == 0
    assert len(narr_dropped) == 1
    # Confirm it dropped on ENTAILMENT (not numeric / content-overlap) — so the
    # ONLY thing that kept it out of the report is the narrative stream's
    # rescue-ineligibility (Fix B/C), NOT the Fix A numeric guard.
    assert any(
        str(r).startswith("entailment_failed")
        for r in narr_dropped[0].failure_reasons
    ), narr_dropped[0].failure_reasons
    assert _drop_is_numeric(narr_dropped[0]) is False, (
        narr_dropped[0].failure_reasons
    )


# ─────────────────────────────────────────────────────────────────────────────
# (6) Regulatory classification — the M-70 ``render_regulatory_prose`` stream is
#     rescue-INELIGIBLE. Its parser verbatim-checks ONLY the one ``source_span``
#     phrase, not the LLM-synthesized prose ``value``, so it has the SAME
#     fabrication shape as the narrative stream. A regulatory sentence that
#     fails verify must NOT be laundered back by the M-69 rescue. The regulatory
#     stream is wired with ``allow_rescue=False`` (same as narrative); this test
#     locks that a content-overlap-dropped regulatory-shaped sentence stays
#     dropped, where the deterministic stream would rescue the identical input.
# ─────────────────────────────────────────────────────────────────────────────
@pytest.mark.skip(reason=(
    "The writer-side no_content_word_overlap_any_cited_span drop this rescue guard targets was REMOVED per 2026-07-10 UNFREEZE (fix 2, GH I-arch-s5-001): with the content-word-overlap floor deleted the sentence is no longer dropped for that reason, so there is nothing to rescue. The NLI entailment judge is now the semantic bar (live-judge surface, not offline)."
))
def test_regulatory_stream_is_rescue_ineligible(monkeypatch):
    """The regulatory stream (allow_rescue=False) does NOT rescue a dropped
    contract sentence, mirroring the narrative stream — so an LLM-synthesized
    regulatory paragraph that fails verify is never laundered back into the
    report.

    Uses the SAME content-overlap-drop input the deterministic stream rescues
    (test #4), driven through the REAL rewrite + verify path. The ONLY
    difference is the stream's rescue policy, isolating the regulatory
    classification."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")
    monkeypatch.setenv("PG_VERIFICATION_MODE", "off")
    raw_draft, pool = _content_overlap_drop_setup()

    # Regulatory stream is wired exactly like the narrative stream:
    # allow_rescue=False. The identical input that the deterministic stream
    # rescues (test #4) must stay dropped here.
    kept, rescued, dropped, total_in, _rw = _verify_one_stream(
        raw_draft=raw_draft,
        evidence_pool=pool,
        contract_entity_ids={_CONTRACT_EV_ID},
        rewrite_fn=_rewrite_draft_with_spans,
        strict_verify_fn=strict_verify,
        allow_rescue=False,
        stream_label="regulatory",
    )

    assert total_in == 1
    assert len(rescued) == 0
    assert len(kept) == 0
    assert len(dropped) == 1
    assert dropped[0].is_verified is False
    # Non-numeric drop — so the rescue-ineligibility (not Fix A) is what keeps
    # it dropped, exactly as for the narrative stream.
    assert _drop_is_numeric(dropped[0]) is False, dropped[0].failure_reasons
