"""I-bug-108 — verifier-driven sentence repair loop tests.

Codex iter-1 brief verdict required:
  1. Token-set preservation check on repaired output
  2. Drop accounting honest (recovered moved to kept, failed stay dropped)
  3. Deterministic repair order (input list order)

These tests pin those invariants + the standard wiring tests.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.generator import sentence_repair as sr
from src.polaris_graph.generator.provenance_generator import (
    SentenceVerification,
    parse_provenance_tokens,
)


@pytest.fixture(autouse=True)
def _enable_repair_loop(monkeypatch):
    """Most tests want the loop enabled; override per-test for off-mode test."""
    monkeypatch.setenv("PG_REPAIR_LOOP_ENABLED", "true")
    monkeypatch.setenv("PG_REPAIR_LOOP_MAX_PER_SECTION", "10")


# ---------- Repairable-reason classifier ----------

def test_is_repairable_entailment_failed():
    assert sr.is_repairable(["entailment_failed:ev_x:verdict=NEUTRAL:reason=foo"])


def test_is_repairable_number_mismatch():
    assert sr.is_repairable(["number_not_in_any_cited_span:ev_x:missing=['1.5']"])


def test_is_repairable_trial_name_mismatch():
    assert sr.is_repairable([
        "trial_name_mismatch:ev_x:sentence_trials=['SURPASS-1']:evidence_trials=[]"
    ])


def test_is_repairable_no_provenance_token_returns_false():
    """no_provenance_token has no anchor — repair won't help."""
    assert not sr.is_repairable(["no_provenance_token"])


def test_is_repairable_invalid_token_returns_false():
    assert not sr.is_repairable(["evidence_not_in_pool:ev_unknown"])


def test_is_repairable_span_out_of_bounds_returns_false():
    assert not sr.is_repairable(["span_out_of_bounds:ev_x:50>40"])


def test_is_repairable_mixed_failures_returns_false():
    """Mixed-failure sentences (one fixable + one not) are NOT repaired."""
    assert not sr.is_repairable([
        "entailment_failed:ev_x",
        "evidence_not_in_pool:ev_y",
    ])


def test_is_repairable_empty_returns_false():
    assert not sr.is_repairable([])


# ---------- Token signature extraction ----------

def test_token_signature_single_token():
    sig = sr._extract_token_signature(
        "Drug worked [#ev:ev_a:0-50]."
    )
    assert sig == ("[#ev:ev_a:0-50]",)


def test_token_signature_multiple_tokens_sorted():
    """Signature is sorted so order changes don't trigger violation."""
    sig1 = sr._extract_token_signature(
        "First [#ev:ev_a:0-10] then [#ev:ev_b:5-20]."
    )
    sig2 = sr._extract_token_signature(
        "Drug [#ev:ev_b:5-20] worked [#ev:ev_a:0-10]."
    )
    assert sig1 == sig2


def test_token_signature_change_detected():
    """If repair changes evidence_id, signature differs."""
    sig_orig = sr._extract_token_signature("Drug [#ev:ev_a:0-10].")
    sig_changed = sr._extract_token_signature("Drug [#ev:ev_b:0-10].")
    assert sig_orig != sig_changed


def test_token_signature_byte_range_change_detected():
    sig_orig = sr._extract_token_signature("Drug [#ev:ev_a:0-10].")
    sig_changed = sr._extract_token_signature("Drug [#ev:ev_a:0-20].")
    assert sig_orig != sig_changed


# ---------- Repair loop orchestrator (off-mode) ----------

@pytest.mark.asyncio
async def test_repair_loop_disabled_by_env_skips_calls(monkeypatch):
    """ENV=false → loop returns inputs unchanged, no LLM call."""
    monkeypatch.setenv("PG_REPAIR_LOOP_ENABLED", "false")

    kept = [_mk_sv("kept", verified=True)]
    dropped = [_mk_sv(
        "drop [#ev:ev_x:0-10].",
        verified=False,
        reasons=["entailment_failed:ev_x:verdict=NEUTRAL"],
    )]

    new_kept, new_dropped, tel = await sr.repair_dropped_section_sentences(
        kept=kept, dropped=dropped, evidence_pool={},
    )
    assert new_kept == kept
    assert new_dropped == dropped
    assert tel.attempts == 0


# ---------- Repair loop orchestrator (on-mode with fakes) ----------

class _FakeRepairLLM:
    """Returns canned repaired text per call. Drives the verify
    re-run via the patched verify_sentence_provenance.
    """

    def __init__(self, responses: list[str | None]):
        self.responses = list(responses)
        self.calls: list[SentenceVerification] = []


@pytest.mark.asyncio
async def test_repair_loop_skips_unrepairable_reasons(monkeypatch):
    """Sentences with no_provenance_token / invalid_token → not attempted."""
    kept: list[SentenceVerification] = []
    dropped = [
        _mk_sv("no anchor", verified=False, reasons=["no_provenance_token"]),
        _mk_sv(
            "bad ev [#ev:ev_z:0-10].",
            verified=False,
            reasons=["evidence_not_in_pool:ev_z"],
        ),
    ]

    # Patch repair_sentence to assert it's never called
    called = []
    async def _fake_repair(**kwargs):
        called.append(kwargs)
        return "skipped", None, 0, 0
    monkeypatch.setattr(sr, "repair_sentence", _fake_repair)

    new_kept, new_dropped, tel = await sr.repair_dropped_section_sentences(
        kept=kept, dropped=dropped, evidence_pool={},
    )
    assert new_kept == kept
    assert new_dropped == dropped
    assert tel.attempts == 0
    assert called == []


@pytest.mark.asyncio
async def test_repair_loop_recovery_path(monkeypatch):
    """Repair returns text → re-verify passes → sentence MOVES from
    dropped to kept (Codex iter-1 P0 #2 drop accounting).
    """
    full_text = "Drug reduced HbA1c by 1.5% in adults with diabetes."
    pool = {
        "ev_a": {"evidence_id": "ev_a", "direct_quote": full_text},
    }
    # PT12 safety filter: dropped sentence must cite ev_id that IS in kept
    kept: list[SentenceVerification] = [
        _mk_sv("Existing kept [#ev:ev_a:0-50].", verified=True),
    ]
    dropped = [
        _mk_sv(
            "Drug reduced HbA1c by 9.9% [#ev:ev_a:0-50].",
            verified=False,
            reasons=["number_not_in_any_cited_span:ev_a:missing=['9.9']"],
        ),
    ]

    repaired = "Drug reduced HbA1c [#ev:ev_a:0-50]."
    async def _fake_repair(**kwargs):
        return "text", repaired, 100, 50
    monkeypatch.setattr(sr, "repair_sentence", _fake_repair)

    # Use real verify_sentence_provenance (the repaired text should
    # pass — number_not_in_any_cited_span no longer triggers since the
    # rewrite has no number).
    new_kept, new_dropped, tel = await sr.repair_dropped_section_sentences(
        kept=kept, dropped=dropped, evidence_pool=pool,
    )
    assert tel.attempts == 1
    assert tel.successes == 1
    # kept[0] is the pre-existing seed; kept[1] is the recovered
    assert len(new_kept) == 2
    assert "9.9" not in new_kept[1].sentence
    assert new_dropped == []  # No double-counting


@pytest.mark.asyncio
async def test_repair_loop_null_drop_keeps_original(monkeypatch):
    """Repair returns None (NULL_DROP/error) → original drop preserved."""
    pool = {"ev_a": {"evidence_id": "ev_a", "direct_quote": "Drug data."}}
    dropped_sv = _mk_sv(
        "Drug worked perfectly [#ev:ev_a:0-10].",
        verified=False,
        reasons=["entailment_failed:ev_a:verdict=NEUTRAL"],
    )

    async def _fake_repair(**kwargs):
        return "null_drop", None, 100, 5  # NULL_DROP path
    monkeypatch.setattr(sr, "repair_sentence", _fake_repair)

    # PT12 safety: seed kept with same ev_id so dropped is eligible for repair
    seed_kept = [_mk_sv(
        "Pre-existing seed [#ev:ev_a:0-10].", verified=True,
    )]
    new_kept, new_dropped, tel = await sr.repair_dropped_section_sentences(
        kept=seed_kept, dropped=[dropped_sv], evidence_pool=pool,
    )
    assert tel.attempts == 1
    assert tel.successes == 0
    assert tel.null_drops == 1
    assert len(new_dropped) == 1
    assert new_dropped[0] == dropped_sv  # Original preserved


@pytest.mark.asyncio
async def test_repair_loop_token_set_violation_detected(monkeypatch):
    """Repaired output that ADDS a new [#ev:...] marker → repair fails
    (Codex iter-1 P0 #1 token-set preservation).
    """
    pool = {
        "ev_a": {"evidence_id": "ev_a", "direct_quote": "Drug A worked."},
        "ev_b": {"evidence_id": "ev_b", "direct_quote": "Drug B worked."},
    }
    dropped_sv = _mk_sv(
        "Drug A worked [#ev:ev_a:0-10].",
        verified=False,
        reasons=["entailment_failed:ev_a:verdict=NEUTRAL"],
    )

    # Repair adds a NEW marker [#ev:ev_b:...] not in the original
    async def _fake_repair(**kwargs):
        return "text", "Drug A worked [#ev:ev_a:0-10][#ev:ev_b:0-10].", 100, 50
    monkeypatch.setattr(sr, "repair_sentence", _fake_repair)

    # PT12 safety: seed kept with same ev_id so dropped is eligible for repair
    seed_kept = [_mk_sv(
        "Pre-existing seed [#ev:ev_a:0-10].", verified=True,
    )]
    new_kept, new_dropped, tel = await sr.repair_dropped_section_sentences(
        kept=seed_kept, dropped=[dropped_sv], evidence_pool=pool,
    )
    assert tel.attempts == 1
    assert tel.successes == 0
    assert tel.token_set_violations == 1
    assert new_dropped == [dropped_sv]


@pytest.mark.asyncio
async def test_repair_loop_max_per_section_caps_attempts(monkeypatch):
    """MAX_PER_SECTION=2 → only first 2 repairable drops attempted."""
    monkeypatch.setenv("PG_REPAIR_LOOP_MAX_PER_SECTION", "2")
    pool = {"ev_a": {"evidence_id": "ev_a", "direct_quote": "data"}}

    dropped = [
        _mk_sv(
            f"Drop {i} [#ev:ev_a:0-4].",
            verified=False,
            reasons=["entailment_failed:ev_a:verdict=NEUTRAL"],
        )
        for i in range(5)
    ]

    async def _fake_repair(**kwargs):
        return "null_drop", None, 100, 5  # always NULL_DROP
    monkeypatch.setattr(sr, "repair_sentence", _fake_repair)

    seed_kept = [_mk_sv(
        "Pre-existing [#ev:ev_a:0-4].", verified=True,
    )]
    new_kept, new_dropped, tel = await sr.repair_dropped_section_sentences(
        kept=seed_kept, dropped=dropped, evidence_pool=pool,
    )
    assert tel.attempts == 2
    assert len(new_dropped) == 5  # all stay dropped


@pytest.mark.asyncio
async def test_repair_loop_processes_in_order(monkeypatch):
    """Codex iter-1 P0 #3: deterministic order. First N items repaired
    in input-list order, not random.
    """
    monkeypatch.setenv("PG_REPAIR_LOOP_MAX_PER_SECTION", "3")
    pool = {"ev_a": {"evidence_id": "ev_a", "direct_quote": "data"}}

    dropped = [
        _mk_sv(
            f"Sentence_{i} [#ev:ev_a:0-4].",
            verified=False,
            reasons=["entailment_failed:ev_a:verdict=NEUTRAL"],
        )
        for i in range(5)
    ]

    seen_order = []
    async def _fake_repair(**kwargs):
        seen_order.append(kwargs["dropped"].sentence)
        return "null_drop", None, 50, 10
    monkeypatch.setattr(sr, "repair_sentence", _fake_repair)

    # PT12 safety: seed kept with same ev_id so all dropped are eligible
    seed_kept = [_mk_sv(
        "Pre-existing [#ev:ev_a:0-4].", verified=True,
    )]
    await sr.repair_dropped_section_sentences(
        kept=seed_kept, dropped=dropped, evidence_pool=pool,
    )
    assert seen_order == [
        "Sentence_0 [#ev:ev_a:0-4].",
        "Sentence_1 [#ev:ev_a:0-4].",
        "Sentence_2 [#ev:ev_a:0-4].",
    ]


@pytest.mark.asyncio
async def test_repair_loop_telemetry_records_all_outcomes(monkeypatch):
    """Mixed run: 1 success + 1 null_drop + 1 token_violation + 1 not-attempted."""
    pool = {
        "ev_a": {"evidence_id": "ev_a", "direct_quote": "Drug A data."},
    }
    dropped = [
        _mk_sv(
            "Drug claim 1 [#ev:ev_a:0-10].",
            verified=False,
            reasons=["entailment_failed:ev_a"],
        ),
        _mk_sv(
            "Drug claim 2 [#ev:ev_a:0-10].",
            verified=False,
            reasons=["entailment_failed:ev_a"],
        ),
        _mk_sv(
            "Drug claim 3 [#ev:ev_a:0-10].",
            verified=False,
            reasons=["entailment_failed:ev_a"],
        ),
        _mk_sv(
            "no anchor",
            verified=False,
            reasons=["no_provenance_token"],
        ),
    ]

    # Drug claim 1 → recovered (real verify will pass with simple text)
    # Drug claim 2 → null_drop
    # Drug claim 3 → token violation (adds new marker)
    responses = iter([
        ("text", "Drug A data [#ev:ev_a:0-10].", 100, 50),
        ("null_drop", None, 50, 10),
        ("text", "Drug claim 3 [#ev:ev_a:0-10][#ev:ev_b:0-5].", 100, 50),
    ])
    async def _fake_repair(**kwargs):
        return next(responses)
    monkeypatch.setattr(sr, "repair_sentence", _fake_repair)

    seed_kept = [_mk_sv(
        "Pre-existing [#ev:ev_a:0-4].", verified=True,
    )]
    new_kept, new_dropped, tel = await sr.repair_dropped_section_sentences(
        kept=seed_kept, dropped=dropped, evidence_pool=pool,
    )
    assert tel.attempts == 3  # last item not_repairable, skipped
    assert tel.null_drops == 1
    assert tel.token_set_violations == 1
    assert tel.input_tokens > 0
    assert tel.output_tokens > 0


@pytest.mark.asyncio
async def test_repair_loop_pt12_safety_skips_unkept_evidence_id(monkeypatch):
    """PT12 safety: a dropped sentence whose evidence_id is NOT cited
    by any kept sentence MUST NOT be attempted (would otherwise expand
    the bibliography and trigger rule_pt12_invalid_citation_marker).
    """
    pool = {
        "ev_a": {"evidence_id": "ev_a", "direct_quote": "Drug A worked."},
        "ev_b": {"evidence_id": "ev_b", "direct_quote": "Drug B worked."},
    }
    # Kept sentence cites ev_a only
    kept = [_mk_sv("Kept sentence [#ev:ev_a:0-10].", verified=True)]
    # Dropped sentence cites ev_b which is NOT in kept's citations
    dropped = [
        _mk_sv(
            "Drug B claim [#ev:ev_b:0-10].",
            verified=False,
            reasons=["entailment_failed:ev_b:verdict=NEUTRAL"],
        ),
    ]

    called = []
    async def _fake_repair(**kwargs):
        called.append(kwargs)
        return "skipped", None, 0, 0
    monkeypatch.setattr(sr, "repair_sentence", _fake_repair)

    new_kept, new_dropped, tel = await sr.repair_dropped_section_sentences(
        kept=kept, dropped=dropped, evidence_pool=pool,
    )
    assert tel.attempts == 0, "PT12 safety: ev_b not in kept set, must skip"
    assert called == []
    assert new_dropped == dropped


@pytest.mark.asyncio
async def test_repair_loop_pt12_safety_allows_kept_evidence_id(monkeypatch):
    """The flip side: if the dropped sentence cites only ev_ids that
    ARE in the kept set, it IS eligible for repair.
    """
    pool = {
        "ev_a": {"evidence_id": "ev_a", "direct_quote": "Drug A worked."},
    }
    kept = [_mk_sv("Kept [#ev:ev_a:0-10].", verified=True)]
    dropped = [
        _mk_sv(
            "Drug A also caused things [#ev:ev_a:0-10].",
            verified=False,
            reasons=["entailment_failed:ev_a:verdict=NEUTRAL"],
        ),
    ]

    called = []
    async def _fake_repair(**kwargs):
        called.append(kwargs)
        return "null_drop", None, 50, 10
    monkeypatch.setattr(sr, "repair_sentence", _fake_repair)

    new_kept, new_dropped, tel = await sr.repair_dropped_section_sentences(
        kept=kept, dropped=dropped, evidence_pool=pool,
    )
    assert tel.attempts == 1, "ev_a IS in kept set, should attempt"
    assert len(called) == 1


@pytest.mark.asyncio
async def test_repair_loop_telemetry_distinguishes_api_failure_from_null_drop(monkeypatch):
    """Codex iter-1 P1 fix: outcome is explicit, not inferred from token counts.
    A null_drop with token counts (in=50,out=10) is correctly classified as
    null_drop, NOT api_failure, even though token counts > 0.
    Conversely, an api_failure with token counts (e.g. partial response) is
    correctly classified as api_failure, NOT null_drop.
    """
    pool = {"ev_a": {"evidence_id": "ev_a", "direct_quote": "Drug A data."}}
    seed = [_mk_sv("Pre [#ev:ev_a:0-10].", verified=True)]
    dropped_a = _mk_sv(
        "Claim a [#ev:ev_a:0-10].", verified=False,
        reasons=["entailment_failed:ev_a"],
    )
    dropped_b = _mk_sv(
        "Claim b [#ev:ev_a:0-10].", verified=False,
        reasons=["entailment_failed:ev_a"],
    )

    responses = iter([
        ("null_drop", None, 50, 10),       # nonzero tokens but null_drop
        ("api_failure", None, 200, 50),    # nonzero tokens but api_failure
    ])
    async def _fake_repair(**kwargs):
        return next(responses)
    monkeypatch.setattr(sr, "repair_sentence", _fake_repair)

    new_kept, new_dropped, tel = await sr.repair_dropped_section_sentences(
        kept=seed, dropped=[dropped_a, dropped_b], evidence_pool=pool,
    )
    assert tel.null_drops == 1, (
        "explicit outcome must classify by signal, not inferred from tokens"
    )
    assert tel.api_failures == 1


# ---------- Helpers ----------

def _mk_sv(
    sentence: str,
    *,
    verified: bool = False,
    reasons: list[str] | None = None,
) -> SentenceVerification:
    return SentenceVerification(
        sentence=sentence,
        tokens=parse_provenance_tokens(sentence),
        is_verified=verified,
        failure_reasons=reasons or [],
    )
