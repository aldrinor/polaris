"""I-deepfix-001 — Codex e2e-gate iter-1 P1 fixes (regression guards).

Two P1s the Codex gate caught on the comprehensive wall-audit diff:

P1 #1 — the paid Gate-B entrypoint (scripts/dr_benchmark/run_gate_b.py) set only the
sweep run-wall context, NOT multi_section_generator.set_run_wall_deadline, so the new
per-section wall-clock gap-stub guard was INACTIVE on the paid path -> a wedged section
could consume the run wall and emit a timeout artifact with NO rendered report.

P1 #2 — strict_verify.verify_sentence_to_record passed the judge-error always-release
label (verify_sentence returns (True, '<label>')) as ``drop_reason``, but the
VerifiedSentence schema FORBIDS a non-None drop_reason when verifier_pass=True, so the
intended ship-with-label conversion RAISED (aborted) instead of preserving the label.

These tests are offline/structural — no GPU, no network, no LLM.
"""

import pathlib

import pytest

from src.polaris_graph.clinical_generator.verified_report import VerifiedSentence

_REPO = pathlib.Path(__file__).resolve().parents[2]


def test_p1_2_ship_with_label_does_not_abort():
    """verifier_pass=True + a kept_disclosure_label + drop_reason=None must construct."""
    vs = VerifiedSentence(
        section_id="s1",
        sentence_text="x",
        provenance_tokens=["[#ev:a:0-1]"],
        verifier_pass=True,
        drop_reason=None,
        kept_disclosure_label="entailment_unverified_judge_error",
        evaluator_agrees=True,
    )
    assert vs.verifier_pass is True
    assert vs.drop_reason is None
    assert vs.kept_disclosure_label == "entailment_unverified_judge_error"


def test_p1_2_schema_invariant_still_rejects_pass_with_drop_reason():
    """The faithfulness invariant must hold: verifier_pass=True + drop_reason != None raises."""
    with pytest.raises(Exception):
        VerifiedSentence(
            section_id="s1",
            sentence_text="x",
            provenance_tokens=["[#ev:a:0-1]"],
            verifier_pass=True,
            drop_reason="entailment_failed",
            evaluator_agrees=True,
        )


def test_p1_2_dropped_sentence_unchanged():
    """Genuine drop (verifier_pass=False) still carries drop_reason, no kept label."""
    vs = VerifiedSentence(
        section_id="s1",
        sentence_text="x",
        provenance_tokens=[],
        verifier_pass=False,
        drop_reason="entailment_failed",
        evaluator_agrees=False,
    )
    assert vs.verifier_pass is False
    assert vs.drop_reason == "entailment_failed"
    assert vs.kept_disclosure_label is None


def test_p1_2_verify_sentence_to_record_routes_label_to_kept_disclosure(monkeypatch):
    """When verify_sentence returns (True, <label>), the record keeps the label off drop_reason."""
    import src.polaris_graph.clinical_generator.strict_verify as sv

    monkeypatch.setattr(
        sv, "verify_sentence",
        lambda *a, **k: (True, "entailment_unverified_judge_error"),
    )
    # sentence MUST carry a provenance token (a kept non-synthesis sentence requires >=1).
    rec = sv.verify_sentence_to_record(
        "AI restructures the labor market [#ev:a:0-30]", "sec1", pool=None,
    )
    assert rec.verifier_pass is True
    assert rec.drop_reason is None
    assert rec.kept_disclosure_label == "entailment_unverified_judge_error"


def test_p1_1_gate_b_installs_generator_run_wall_deadline():
    """The paid Gate-B path must install + reset the multi_section_generator run-wall deadline."""
    src = (_REPO / "scripts" / "dr_benchmark" / "run_gate_b.py").read_text(encoding="utf-8")
    assert "set_run_wall_deadline as _msg_set_run_wall_deadline" in src
    assert "reset_run_wall_deadline as _msg_reset_run_wall_deadline" in src
    assert "_msg_set_run_wall_deadline(_run_wall_deadline)" in src
    assert "_msg_reset_run_wall_deadline(_msg_deadline_token)" in src


def test_p1_3_w12_release_policy_import_resolves():
    """W12 excessive-gap disclose-and-ship: always_release_enabled imports from roles, not generator."""
    # the real module resolves:
    from src.polaris_graph.roles.release_policy import always_release_enabled  # noqa: F401
    # the wrong (nonexistent) import must be gone from the sweep:
    src = (_REPO / "scripts" / "run_honest_sweep_r3.py").read_text(encoding="utf-8")
    assert "from src.polaris_graph.generator.release_policy import" not in src
    assert "from src.polaris_graph.roles.release_policy import" in src


def test_p1_4_w13_executor_does_not_block_on_timeout():
    """W13 intent-frame: no `with ThreadPoolExecutor` (blocking shutdown); use shutdown(wait=False)."""
    src = (_REPO / "scripts" / "run_honest_sweep_r3.py").read_text(encoding="utf-8")
    # the blocking context-manager pattern around the .result() timeout must be gone:
    assert "with _intent_frame_futures.ThreadPoolExecutor(" not in src
    # the non-blocking shutdown must be present:
    assert "_ex.shutdown(wait=False, cancel_futures=True)" in src
