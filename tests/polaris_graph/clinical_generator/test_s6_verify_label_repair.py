"""S6 VERIFY — DROP -> LABEL + REPAIR contract tests (operator UNFREEZE 2026-07-10).

Proves the section contract on a FIXTURE evidence pool (NOT the live corpus — that is
the later VM hamster). Covers:

  1. OFF (default) => byte-identical silent DROP.
  2. ON + LABEL-ELIGIBLE reason => KEEP with a confidence label; provenance preserved.
  3. ON + hedge repair on binding_qualifier_dropped => repaired text + "_repaired" label.
  4. ON + FATAL reason (fabricated / unsupported-number / ungrounded) => STILL DROPS
     (faithfulness NOT relaxed — the clinical-safety boundary).
  5. LAW VI: the LABEL-ELIGIBLE set is env-overridable.
  6. Repair fail-open: a raising repair_fn degrades to label-only, never crash/drop.
  7. cp6 checkpoint: DATA-only accounting, rollup counts, recursive forbidden-verdict-key
     guard, atomic write round-trip.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from polaris_graph.clinical_generator import verify_label_repair as lr
from polaris_graph.clinical_generator.strict_verify import verify_sentence_to_record
from polaris_graph.clinical_retrieval.evidence_pool import (
    AdequacyVerdict,
    EvidencePool,
    Source,
    SourceTier,
)


# --------------------------------------------------------------------------- #
# Fixture pool builders (mirror tests/.../test_strict_verify.py)
# --------------------------------------------------------------------------- #

def _src(source_id: str, full_text: str) -> Source:
    return Source(
        url="https://www.cochrane.org/CD001",
        domain="cochrane.org",
        tier=SourceTier.T1,
        title="Source",
        snippet="snippet",
        full_text=full_text,
        full_text_available=True,
        source_id=source_id,
    )


def _pool(*sources: Source) -> EvidencePool:
    return EvidencePool(
        decision_id="dec-1",
        sources=list(sources),
        adequacy=AdequacyVerdict(
            is_adequate=True,
            sources_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
            min_required_per_tier={SourceTier.T1: 0, SourceTier.T2: 0, SourceTier.T3: 0},
        ),
        retrieval_started_at_utc=datetime.now(timezone.utc),
        retrieval_finished_at_utc=datetime.now(timezone.utc),
        latency_ms=0,
        cost_usd=0.0,
    )


def _tok(source_id: str, text: str) -> str:
    """A full-span provenance token for `text` under `source_id`."""
    return f"[#ev:{source_id}:0-{len(text)}]"


# Overlap-too-low fixture: valid token, in-bounds span, NO decimals, zero shared content
# words -> drop_reason "overlap_too_low" (a LABEL-ELIGIBLE grounded-but-weak reason).
_OVERLAP_SPAN = "Xylophone zenith orbit."
_OVERLAP_SENTENCE = f"Aspirin helps patients. {_tok('src-ovl', _OVERLAP_SPAN)}"

# Binding-qualifier-dropped fixture: span hedges 46.5 percent ("suggest"/"estimates"),
# sentence restates it flat with no marker -> "binding_qualifier_dropped" (LABEL-ELIGIBLE
# + repairable). Numbers + overlap both pass, so the qualifier gate is the failing check.
_QUAL_SPAN = "Some estimates suggest 46.5 percent of tasks are affected."
_QUAL_SENTENCE = f"Affected tasks reach 46.5 percent. {_tok('src-qual', _QUAL_SPAN)}"

# Numeric-mismatch fixture: a decimal in the sentence absent from the span -> FATAL.
_NUM_SPAN = "Aspirin reduced cardiovascular events in adults overall."
_NUM_SENTENCE = f"Aspirin reduced events by 12.7 percent in adults. {_tok('src-num', _NUM_SPAN)}"


@pytest.fixture(autouse=True)
def _entailment_off(monkeypatch):
    """Keep the semantic judge OFF so every test is hermetic (no network). The
    LABEL-ELIGIBLE fixtures fail BEFORE the entailment step anyway; this is belt-and-braces."""
    monkeypatch.setenv("PG_STRICT_VERIFY_ENTAILMENT", "off")


# --------------------------------------------------------------------------- #
# strict_verify seam — end-to-end record behavior
# --------------------------------------------------------------------------- #

def test_off_is_byte_identical_drop(monkeypatch):
    monkeypatch.delenv("PG_STRICT_VERIFY_LABEL_REPAIR", raising=False)
    pool = _pool(_src("src-ovl", _OVERLAP_SPAN))
    rec = verify_sentence_to_record(_OVERLAP_SENTENCE, "sec-1", pool)
    assert rec.verifier_pass is False
    assert rec.drop_reason == "overlap_too_low"
    assert rec.kept_disclosure_label is None


def test_label_eligible_kept_with_label_when_on(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_LABEL_REPAIR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_REPAIR_MODE", "off")
    pool = _pool(_src("src-ovl", _OVERLAP_SPAN))
    rec = verify_sentence_to_record(_OVERLAP_SENTENCE, "sec-1", pool)
    assert rec.verifier_pass is True
    assert rec.drop_reason is None
    assert rec.kept_disclosure_label == "unverified_overlap_too_low"
    # provenance SIGNAL preserved: the [#ev:...] token is still on the kept sentence.
    assert rec.provenance_tokens == [_tok("src-ovl", _OVERLAP_SPAN)]
    # repair mode off -> text unchanged.
    assert rec.sentence_text == _OVERLAP_SENTENCE
    # evaluator agreement stays pending (a weak label-kept sentence is NOT evaluator-confirmed).
    assert rec.evaluator_agrees is None


def test_binding_qualifier_repaired_when_on(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_LABEL_REPAIR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_REPAIR_MODE", "hedge")
    pool = _pool(_src("src-qual", _QUAL_SPAN))
    rec = verify_sentence_to_record(_QUAL_SENTENCE, "sec-1", pool)
    assert rec.verifier_pass is True
    assert rec.drop_reason is None
    assert rec.kept_disclosure_label == "unverified_binding_qualifier_dropped_repaired"
    # hedge repair prepends the source-attribution lead-in AND keeps the token.
    assert rec.sentence_text.startswith("According to the cited evidence,")
    assert _tok("src-qual", _QUAL_SPAN) in rec.sentence_text


@pytest.mark.parametrize(
    "sentence, pool, expected_reason",
    [
        (_NUM_SENTENCE, _pool(_src("src-num", _NUM_SPAN)), "numeric_mismatch"),
        ("Aspirin works in adults.", _pool(_src("src-x", "x" * 50)), "no_provenance_token"),
        ("Aspirin works [#ev:ghost:0-3].", _pool(_src("src-x", "x" * 50)), "invalid_token"),
    ],
)
def test_fatal_reasons_still_drop_when_on(monkeypatch, sentence, pool, expected_reason):
    monkeypatch.setenv("PG_STRICT_VERIFY_LABEL_REPAIR", "1")
    rec = verify_sentence_to_record(sentence, "sec-1", pool)
    assert rec.verifier_pass is False, f"{expected_reason} must NOT be label-kept"
    assert rec.drop_reason == expected_reason
    assert rec.kept_disclosure_label is None


def test_synthesis_claim_unaffected_by_flag(monkeypatch):
    # A no-token synthesis claim passes as before; the label path never touches it.
    monkeypatch.setenv("PG_STRICT_VERIFY_LABEL_REPAIR", "1")
    pool = _pool(_src("src-x", "Aspirin reduced events."))
    rec = verify_sentence_to_record(
        "Across trials the effect is moderate.", "sec-1", pool, is_synthesis_claim=True
    )
    assert rec.verifier_pass is True
    assert rec.kept_disclosure_label is None


# --------------------------------------------------------------------------- #
# Policy unit tests (no pool required)
# --------------------------------------------------------------------------- #

def test_policy_off_drops(monkeypatch):
    monkeypatch.delenv("PG_STRICT_VERIFY_LABEL_REPAIR", raising=False)
    d = lr.apply_label_repair_policy("Aspirin helps. [#ev:a:0-3]", "overlap_too_low", [])
    assert d.outcome == "drop"
    assert d.kept is False


def test_policy_fatal_reason_drops(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_LABEL_REPAIR", "1")
    d = lr.apply_label_repair_policy("x [#ev:a:0-3]", "numeric_mismatch", [])
    assert d.outcome == "drop"
    assert d.kept is False


def test_policy_label_only(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_LABEL_REPAIR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_REPAIR_MODE", "off")
    d = lr.apply_label_repair_policy("x [#ev:a:0-3]", "overlap_too_low", [])
    assert d.outcome == "label"
    assert d.kept is True
    assert d.repaired is False
    assert d.disclosure_label == "unverified_overlap_too_low"


def test_policy_hedge_repair_reattaches_marker(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_LABEL_REPAIR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_REPAIR_MODE", "hedge")
    d = lr.apply_label_repair_policy(
        "Affected tasks reach 46.5 percent. [#ev:a:0-3]",
        "binding_qualifier_dropped",
        [_QUAL_SPAN],
    )
    assert d.outcome == "repair"
    assert d.repaired is True
    assert d.sentence_text.startswith("According to the cited evidence,")
    assert d.disclosure_label == "unverified_binding_qualifier_dropped_repaired"
    # the span marker the composer dropped is recorded for disclosure.
    assert d.repair_note is not None and "span_marker=" in d.repair_note


def test_policy_nli_repair_fn_used(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_LABEL_REPAIR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_REPAIR_MODE", "nli")

    def _fake_regrounder(sentence, spans, reason):
        # A real re-grounder rewrites the claim; it MUST keep the provenance token.
        return "Reportedly, aspirin helps. [#ev:a:0-3]"

    d = lr.apply_label_repair_policy(
        "Aspirin helps. [#ev:a:0-3]", "overlap_too_low", [], repair_fn=_fake_regrounder
    )
    assert d.repaired is True
    assert d.repair_note == "nli_regrounded"
    assert d.sentence_text == "Reportedly, aspirin helps. [#ev:a:0-3]"


def test_policy_nli_rejects_token_dropping_repair(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_LABEL_REPAIR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_REPAIR_MODE", "nli")

    def _drops_token(sentence, spans, reason):
        return "Aspirin helps."  # dropped the [#ev] token -> must be rejected

    d = lr.apply_label_repair_policy(
        "Aspirin helps. [#ev:a:0-3]", "overlap_too_low", [], repair_fn=_drops_token
    )
    assert d.repaired is False
    assert d.repair_note == "nli_noop"
    assert d.kept is True  # still label-kept


def test_policy_nli_without_fn_falls_back_to_hedge(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_LABEL_REPAIR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_REPAIR_MODE", "nli")
    d = lr.apply_label_repair_policy("x [#ev:a:0-3]", "overlap_too_low", [])
    assert d.repaired is True
    assert d.repair_note.startswith("hedge")


def test_policy_reasons_env_override(monkeypatch):
    # LAW VI: widen the eligible set to include numeric_mismatch; overlap becomes FATAL.
    monkeypatch.setenv("PG_STRICT_VERIFY_LABEL_REPAIR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_REPAIR_MODE", "off")
    monkeypatch.setenv("PG_STRICT_VERIFY_LABEL_REPAIR_REASONS", "numeric_mismatch")
    d_num = lr.apply_label_repair_policy("x [#ev:a:0-3]", "numeric_mismatch", [])
    d_ovl = lr.apply_label_repair_policy("x [#ev:a:0-3]", "overlap_too_low", [])
    assert d_num.kept is True
    assert d_ovl.kept is False  # no longer eligible under the override


def test_repair_failopen(monkeypatch):
    monkeypatch.setenv("PG_STRICT_VERIFY_LABEL_REPAIR", "1")
    monkeypatch.setenv("PG_STRICT_VERIFY_REPAIR_MODE", "nli")

    def _boom(sentence, spans, reason):
        raise RuntimeError("regrounder exploded")

    d = lr.apply_label_repair_policy(
        "x [#ev:a:0-3]", "overlap_too_low", [], repair_fn=_boom
    )
    assert d.kept is True          # NEVER dropped on a repair fault
    assert d.repaired is False     # label-only
    assert d.repair_note.startswith("repair_error:")


# --------------------------------------------------------------------------- #
# cp6 checkpoint — DATA-only accounting
# --------------------------------------------------------------------------- #

def test_cp6_payload_rollup_and_guard():
    records = [
        lr.Cp6SentenceRecord("s1", "kept ok [#ev:a:0-3]", kept=True),
        lr.Cp6SentenceRecord(
            "s1", "weak [#ev:a:0-3]", kept=True,
            disclosure_label="unverified_overlap_too_low",
        ),
        lr.Cp6SentenceRecord(
            "s1", "According to... [#ev:a:0-3]", kept=True,
            disclosure_label="unverified_binding_qualifier_dropped_repaired", repaired=True,
        ),
        lr.Cp6SentenceRecord("s2", "bad number", kept=False, drop_reason="numeric_mismatch"),
    ]
    payload = lr.build_cp6_postverify_payload(
        run_id="run-1", question="Q?", records=records, evidence_ids=["a", "b"]
    )
    assert payload["stage"] == lr.CP6_STAGE
    assert payload["rollup"] == {
        "total": 4, "kept": 3, "dropped": 1, "labeled": 2, "repaired": 1
    }
    # round-trips as JSON (DATA only).
    json.loads(json.dumps(payload, sort_keys=True, default=str))


def test_cp6_recursive_guard_catches_nested_key():
    poisoned = {
        "stage": lr.CP6_STAGE,
        "sentences": [{"section_id": "s", "d8_decision": "release"}],
    }
    with pytest.raises(ValueError, match="FORBIDDEN verdict key"):
        lr.write_cp6_postverify_checkpoint(".", poisoned)


def test_cp6_write_roundtrip(tmp_path):
    records = [
        lr.Cp6SentenceRecord("s1", "weak [#ev:a:0-3]", kept=True,
                             disclosure_label="unverified_overlap_too_low"),
        lr.Cp6SentenceRecord("s2", "bad", kept=False, drop_reason="numeric_mismatch"),
    ]
    payload = lr.build_cp6_postverify_payload(
        run_id="run-1", question="Q?", records=records, evidence_ids=["a"]
    )
    out = lr.write_cp6_postverify_checkpoint(tmp_path, payload)
    assert out is not None
    assert out.name == "cp6_postverify_checkpoint.json"
    reloaded = json.loads(out.read_text(encoding="utf-8"))
    assert reloaded["rollup"]["kept"] == 1
    assert reloaded["rollup"]["dropped"] == 1
    assert reloaded["rollup"]["labeled"] == 1


def test_cp6_records_from_verif_details():
    verif_details = {
        "sections": [
            {
                "section_id": "sec-1",
                "verified_sentences": [
                    {"sentence_text": "ok [#ev:a:0-3]", "verifier_pass": True,
                     "provenance_tokens": ["[#ev:a:0-3]"]},
                    {"sentence_text": "weak [#ev:a:0-3]", "verifier_pass": True,
                     "kept_disclosure_label": "unverified_overlap_too_low_repaired"},
                    {"sentence_text": "bad", "verifier_pass": False,
                     "drop_reason": "numeric_mismatch"},
                ],
            }
        ]
    }
    records = lr.build_cp6_records_from_verif_details(verif_details)
    assert len(records) == 3
    assert records[1].disclosure_label == "unverified_overlap_too_low_repaired"
    assert records[1].repaired is True
    assert records[2].kept is False
