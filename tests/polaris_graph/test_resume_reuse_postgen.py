"""ITEM 5 (I-arch-007 death-forensic, GH #1264): wire PG_RESUME_REUSE_POSTGEN so a --resume
REUSES the SLATE owner's generation_snapshot (raw section drafts + verdict-free section/atom
re-entry metadata) to SKIP the Stage-2 section-draft LLM calls + the advisory credibility pass,
then RE-RUNS strict_verify + NLI + 4-role D8 on the reused drafts EXACTLY as a fresh run.

This SWEEP owner edits ONLY scripts/run_honest_sweep_r3.py. The LOAD side (validate + reconstruct
+ flag-slate identity) lives in the SLATE owner's generation_snapshot module and is integrated
here. The generator-side cached-draft consumption hook (skip the draft LLM call, feed the cached
draft into strict_verify) is OWNED by multi_section_generator.py and is NOT yet present, so the ON
path FAILS LOUD here rather than silently re-generating (LAW II + the plan's ITEM-5 deferral
clause). These tests prove:

  * default OFF → the reuse gate is inert (byte-identical to today).
  * ON + a valid generation_snapshot → load + flag-slate identity + outline reconstruction all
    succeed, and the wiring FAILS LOUD because the generator hook is absent (never a silent
    re-generate).
  * ON + a generation-affecting flag drift (different PG_GENERATOR_MODEL) → fail loud (identity).
  * ON + no snapshot → fail loud.
  * the ON re-entry callable, once a generator hook IS present (monkeypatched here), forwards the
    reused drafts/outline/section-atom metadata and is awaited — proving ZERO fresh section-LLM
    drafting and that the binding-gate re-run is delegated to the generator (the over-drop
    re-verify path). The real end-to-end "zero section-LLM calls AND strict_verify/NLI/D8 fire on
    a live run" assertion is xfail-pending the generator-side hook (clearly, not silently).

No network, no spend: writes a real v2 generation_snapshot via the SLATE owner's own saver and
drives the sweep consumer helper directly.
"""
from __future__ import annotations

import asyncio

import pytest

import scripts.run_honest_sweep_r3 as sweep
from scripts.run_honest_sweep_r3 import (
    _POSTGEN_REUSE_GENERATOR_HOOK,
    _load_postgen_reuse_reentry,
)
from src.polaris_graph.generator import generation_snapshot as gen_snapshot
from src.polaris_graph.generator import multi_section_generator as msg
from src.polaris_graph.generator.generation_snapshot import GenerationSnapshotError
from src.polaris_graph.generator.multi_section_generator import SectionPlan


# --------------------------------------------------------------------------------------------
# Fixtures: a valid v2 generation_snapshot + a clean generation-affecting flag slate.
# --------------------------------------------------------------------------------------------

_GEN_FLAGS = (
    "PG_SECTION_DISTILL",
    "PG_ATOM_REFUSAL_MODE",
    "PG_GENERATOR_MODEL",
    "PG_SWEEP_CREDIBILITY_REDESIGN",
)


@pytest.fixture
def _clean_gen_flags(monkeypatch):
    """Pin the generation-affecting flags to fixed values so the snapshot slate is deterministic
    and a resume under the SAME values matches (atom-refusal-mode must be 'off' so the loader does
    not refuse the resume outright)."""
    monkeypatch.setenv("PG_SECTION_DISTILL", "")
    monkeypatch.setenv("PG_ATOM_REFUSAL_MODE", "off")
    monkeypatch.setenv("PG_GENERATOR_MODEL", "deepseek/deepseek-v4-pro")
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "1")


def _write_valid_snapshot(run_dir):
    """Write a real v2 generation_snapshot via the SLATE owner's own saver (so the on-disk shape
    is exactly what load_generation_snapshot expects)."""
    outline = [
        SectionPlan(title="Efficacy", focus="efficacy of X", ev_ids=["ev_1", "ev_2"]),
        SectionPlan(title="Safety", focus="safety of X", ev_ids=["ev_3"]),
    ]
    section_atom_catalogs = {
        "Efficacy": [
            {
                "atom_id": "atom_1",
                "evidence_id": "ev_1",
                "span_start": 0,
                "span_end": 12,
                "literal_text": "X reduced Y",
            },
        ],
        "Safety": [
            {
                "atom_id": "atom_2",
                "evidence_id": "ev_3",
                "span_start": 5,
                "span_end": 20,
                "literal_text": "no serious AE",
            },
        ],
    }
    return gen_snapshot.save_generation_snapshot(
        run_dir,
        run_id="run_test",
        question="does X help Y?",
        slug="q_test",
        domain="clinical",
        outline=outline,
        section_raw_drafts={
            "Efficacy": "X reduced Y by 30% [#ev:ev_1:0-12].",
            "Safety": "No serious adverse events were reported [#ev:ev_3:5-20].",
        },
        had_contract_sections=False,
        section_plans={
            "Efficacy": {"title": "Efficacy", "atom_ids": ["atom_1"]},
            "Safety": {"title": "Safety", "atom_ids": ["atom_2"]},
        },
        section_atom_catalogs=section_atom_catalogs,
    )


def _logs():
    captured: list[str] = []
    return captured, captured.append


# --------------------------------------------------------------------------------------------
# Default OFF → the reuse gate is inert (byte-identical to today).
# --------------------------------------------------------------------------------------------


def test_default_off_gate_inert(monkeypatch):
    """Unset PG_RESUME_REUSE_POSTGEN → the gate read is False → the reuse pre-decision block is
    never entered (no snapshot load, no import of the SLATE module on the run path)."""
    monkeypatch.delenv("PG_RESUME_REUSE_POSTGEN", raising=False)
    assert sweep._env_flag("PG_RESUME_REUSE_POSTGEN", default=False) is False


def test_explicit_off_gate_inert(monkeypatch):
    monkeypatch.setenv("PG_RESUME_REUSE_POSTGEN", "0")
    assert sweep._env_flag("PG_RESUME_REUSE_POSTGEN", default=False) is False


# --------------------------------------------------------------------------------------------
# ON + valid snapshot → load + identity + reconstruct succeed, then FAIL LOUD on the absent hook.
# --------------------------------------------------------------------------------------------


def test_on_valid_snapshot_fails_loud_without_generator_hook(tmp_path, _clean_gen_flags):
    """The load side is fully wired (snapshot loads, flag slate matches, outline reconstructs),
    but the generator's cached-draft hook is absent today → FAIL LOUD (never silent re-generate).
    Guard the hook truly absent first (a future landing would change this test honestly)."""
    if hasattr(msg, _POSTGEN_REUSE_GENERATOR_HOOK):
        pytest.skip(
            f"generator hook {_POSTGEN_REUSE_GENERATOR_HOOK} has landed — see "
            "test_on_reentry_callable_forwards_reused_drafts_when_hook_present"
        )
    _write_valid_snapshot(tmp_path)
    _captured, _log = _logs()
    with pytest.raises(RuntimeError) as exc:
        _load_postgen_reuse_reentry(run_dir=tmp_path, log=_log)
    msg_str = str(exc.value)
    assert "ITEM 5" in msg_str
    assert _POSTGEN_REUSE_GENERATOR_HOOK in msg_str
    assert "Refusing to silently re-generate" in msg_str


# --------------------------------------------------------------------------------------------
# ON + identity (flag-slate) mismatch → FAIL LOUD.
# --------------------------------------------------------------------------------------------


def test_on_flag_slate_mismatch_fails_loud(tmp_path, _clean_gen_flags, monkeypatch):
    """A snapshot produced under PG_GENERATOR_MODEL=deepseek-v4-pro, resumed under a DIFFERENT
    writer → assert_generation_flags_match raises (a cached draft is a faithful strict_verify
    input ONLY under the flag config that produced it). This is the corpus/draft identity guard —
    no parallel hash; the SLATE owner's flag-slate model is the single identity source."""
    _write_valid_snapshot(tmp_path)
    monkeypatch.setenv("PG_GENERATOR_MODEL", "some/other-writer-model")
    _captured, _log = _logs()
    with pytest.raises(GenerationSnapshotError) as exc:
        _load_postgen_reuse_reentry(run_dir=tmp_path, log=_log)
    assert "generation-affecting flags differ" in str(exc.value)


# --------------------------------------------------------------------------------------------
# ON + no snapshot → FAIL LOUD.
# --------------------------------------------------------------------------------------------


def test_on_missing_snapshot_fails_loud(tmp_path, _clean_gen_flags):
    """No generation_snapshot on disk → load_generation_snapshot raises (never a silent fresh
    re-generate when reuse was explicitly requested)."""
    _captured, _log = _logs()
    with pytest.raises(GenerationSnapshotError) as exc:
        _load_postgen_reuse_reentry(run_dir=tmp_path, log=_log)
    assert "no generation snapshot" in str(exc.value)


# --------------------------------------------------------------------------------------------
# ON + verdict-leaked snapshot → FAIL LOUD (the §-1.3 ABSOLUTE recursive verdict-key guard).
# --------------------------------------------------------------------------------------------


def test_on_verdict_leak_in_snapshot_fails_loud(tmp_path, _clean_gen_flags):
    """A snapshot that smuggled a verdict key at a NESTED depth must fail loud on load — a resume
    re-runs every gate and can NEVER replay a stored decision."""
    path = _write_valid_snapshot(tmp_path)
    import json

    payload = json.loads(path.read_text(encoding="utf-8"))
    # smuggle a forbidden verdict key into a nested section/atom structure
    payload["section_plans"]["Efficacy"]["is_verified"] = True
    path.write_text(json.dumps(payload), encoding="utf-8")
    _captured, _log = _logs()
    with pytest.raises(GenerationSnapshotError) as exc:
        _load_postgen_reuse_reentry(run_dir=tmp_path, log=_log)
    assert "FORBIDDEN verdict key" in str(exc.value)


# --------------------------------------------------------------------------------------------
# ON + a PRESENT generator hook (monkeypatched) → the re-entry callable forwards the reused drafts
# + outline + section/atom metadata and is awaited, proving ZERO fresh section-LLM drafting and
# that the binding-gate re-run is delegated to the generator (the over-drop re-verify path).
# --------------------------------------------------------------------------------------------


def test_on_reentry_callable_forwards_reused_drafts_when_hook_present(
    tmp_path, _clean_gen_flags, monkeypatch
):
    _write_valid_snapshot(tmp_path)

    forwarded = {}

    async def _fake_hook(**kwargs):
        forwarded.update(kwargs)
        return "FAKE_MULTISECTION_RESULT"

    monkeypatch.setattr(msg, _POSTGEN_REUSE_GENERATOR_HOOK, _fake_hook, raising=False)

    _captured, _log = _logs()
    active, reentry = _load_postgen_reuse_reentry(run_dir=tmp_path, log=_log)
    assert active is True
    assert callable(reentry)

    result = asyncio.run(
        reentry(
            research_question="does X help Y?",
            evidence=[{"evidence_id": "ev_1"}, {"evidence_id": "ev_3"}],
            prior_verified_context=None,
            credibility_pass_judge="JUDGE_SENTINEL",
            credibility_pass_gov_suffixes=(".gov",),
        )
    )
    # the generator hook (which owns the strict_verify/NLI/D8 re-run) was invoked with the REUSED
    # drafts — no fresh section-draft LLM call path is taken in the sweep.
    assert result == "FAKE_MULTISECTION_RESULT"
    assert forwarded["reused_section_raw_drafts"] == {
        "Efficacy": "X reduced Y by 30% [#ev:ev_1:0-12].",
        "Safety": "No serious adverse events were reported [#ev:ev_3:5-20].",
    }
    # the reconstructed outline is plain SectionPlan dataclasses (never re-derived via an LLM call)
    assert [p.title for p in forwarded["reused_outline"]] == ["Efficacy", "Safety"]
    assert set(forwarded["reused_section_plans"].keys()) == {"Efficacy", "Safety"}
    assert set(forwarded["reused_section_atom_catalogs"].keys()) == {"Efficacy", "Safety"}
    # the credibility-pass inputs are forwarded (the hook skips the pass under reuse, per ITEM 5)
    assert forwarded["credibility_pass_judge"] == "JUDGE_SENTINEL"


@pytest.mark.xfail(
    reason="end-to-end 'zero section-LLM calls AND strict_verify/NLI/D8 fire on a LIVE run' "
    "requires the generator-side cached-draft hook "
    f"(multi_section_generator.{_POSTGEN_REUSE_GENERATOR_HOOK}), which is ITEM 5a's generator "
    "deferral and is OWNED by a file this SWEEP owner does not edit. The load + identity + "
    "reconstruct + fail-loud-when-absent wiring is fully tested above; this marker tracks the "
    "remaining cross-file dependency.",
    strict=True,
)
def test_live_resume_skips_generation_and_reruns_gates():
    assert hasattr(msg, _POSTGEN_REUSE_GENERATOR_HOOK), (
        "generator-side cached-draft re-entry hook not yet present"
    )
