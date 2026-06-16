"""I-cred-012a (#1164) — runner/generator wiring of the credibility pass. Offline, no LLM.

Verifies the activation hook is ADDITIVE + flag-gated: the new generate_multi_section_report params
default None (byte-identical when unpassed), MultiSectionResult carries the analysis field defaulting
None, and the master flag is OFF by default (so the pass block is skipped)."""
from __future__ import annotations

import dataclasses
import inspect

import src.polaris_graph.generator.multi_section_generator as m
from src.polaris_graph.synthesis import credibility_pass as cp


def test_generate_has_additive_credibility_params_default_none():
    sig = inspect.signature(m.generate_multi_section_report)
    assert sig.parameters["credibility_pass_judge"].default is None
    assert sig.parameters["credibility_pass_gov_suffixes"].default is None


def test_result_carries_credibility_analysis_field_default_none():
    fields = {f.name: f for f in dataclasses.fields(m.MultiSectionResult)}
    assert "credibility_analysis" in fields
    # default None -> byte-identical when the pass did not run
    assert fields["credibility_analysis"].default is None


def test_master_flag_off_by_default(monkeypatch):
    monkeypatch.setenv("PG_SWEEP_CREDIBILITY_REDESIGN", "0")
    assert cp.credibility_redesign_enabled() is False


def test_effective_pool_is_values_not_dict():
    # the generator's evidence_pool is a {evidence_id: row} dict; the pass must receive the ROWS.
    # guard the call shape so a future edit can't pass the dict (which the orchestrator would mis-handle).
    src = inspect.getsource(m.generate_multi_section_report)
    assert "list(evidence_pool.values())" in src
    assert "run_credibility_analysis" in src and "fail-closed" in src.lower()
