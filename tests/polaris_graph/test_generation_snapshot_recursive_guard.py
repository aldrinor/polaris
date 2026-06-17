"""ITEM 5a (I-arch-007 #1264) — RECURSIVE forbidden-verdict-key guard on the generation snapshot.

Codex P2-3: the ITEM-5a section/atom re-entry metadata is NESTED (section -> atom_catalog ->
atom dict), so a top-level-only verdict-key guard would let an ``is_verified`` / ``release_outcome``
leak through a nested structure. These tests prove a leaked verdict key at ANY nesting depth fails
LOUD on BOTH the save path (refuse to persist) and the load path (refuse to load), and that a clean
DATA-only snapshot round-trips and preserves the verdict-free section/atom metadata for lossless
verification re-entry.

FAITHFULNESS-NEUTRALITY: this module is a DATA-ONLY checkpoint. It stores NO strict_verify / NLI /
4-role / D8 verdict, no threshold, no cited-evidence set; the recursive guard only STRENGTHENS the
§-1.3 "a checkpoint stores DATA, NEVER A VERDICT" invariant by rejecting a leaked decision at any depth.
"""

from __future__ import annotations

import json

import pytest

from src.polaris_graph.generator.generation_snapshot import (
    GENERATION_SNAPSHOT_SCHEMA_VERSION,
    GenerationSnapshotError,
    generation_snapshot_path,
    load_generation_snapshot,
    save_generation_snapshot,
)


def _clean_save_kwargs() -> dict:
    """A minimal DATA-only save payload with verdict-free ITEM-5a section/atom metadata."""
    return dict(
        run_id="run_test",
        question="What is the efficacy of drug X?",
        slug="q_test",
        domain="clinical",
        outline=[],  # outline-less is fine for the guard tests (drafts carry the keys)
        section_raw_drafts={"Efficacy": "Drug X reduced HbA1c by 2.3 points [#ev:ev_017:0-40]."},
        had_contract_sections=False,
        section_plans={
            "sec_efficacy": {"title": "Efficacy", "atom_ids": ["atom_001", "atom_002"]},
        },
        section_atom_catalogs={
            "sec_efficacy": {
                "atom_001": {
                    "atom_id": "atom_001",
                    "evidence_id": "ev_017",
                    "span_start": 0,
                    "span_end": 40,
                    "literal_text": "reduced HbA1c by 2.3 percentage points",
                },
                "atom_002": {
                    "atom_id": "atom_002",
                    "evidence_id": "ev_018",
                    "span_start": 5,
                    "span_end": 33,
                    "literal_text": "vs semaglutide at 40 weeks",
                },
            },
        },
    )


def test_clean_data_only_snapshot_round_trips(tmp_path):
    """A verdict-free snapshot saves + loads and preserves the ITEM-5a section/atom metadata."""
    path = save_generation_snapshot(tmp_path, **_clean_save_kwargs())
    assert path.exists()
    payload = load_generation_snapshot(tmp_path)
    assert payload["schema_version"] == GENERATION_SNAPSHOT_SCHEMA_VERSION
    # ITEM 5a metadata survived as verdict-free DATA, ready for lossless re-entry.
    assert payload["section_plans"]["sec_efficacy"]["atom_ids"] == ["atom_001", "atom_002"]
    bindings = payload["section_atom_catalogs"]["sec_efficacy"]
    assert {b["atom_id"] for b in bindings} == {"atom_001", "atom_002"}
    assert all(
        set(b) == {"atom_id", "evidence_id", "span_start", "span_end", "literal_text"}
        for b in bindings
    )


def test_save_refuses_verdict_key_nested_in_atom_catalog(tmp_path):
    """A leaked ``is_verified`` DEEP inside an atom-catalog entry fails loud at SAVE time."""
    kwargs = _clean_save_kwargs()
    # Smuggle a verdict key at depth: section_atom_catalogs -> section -> atom -> is_verified.
    kwargs["section_atom_catalogs"]["sec_efficacy"]["atom_001"]["is_verified"] = True
    with pytest.raises(GenerationSnapshotError) as exc:
        save_generation_snapshot(tmp_path, **kwargs)
    assert "is_verified" in str(exc.value)
    # Nothing was persisted (fail BEFORE the write).
    assert not generation_snapshot_path(tmp_path).exists()


def test_save_refuses_verdict_key_nested_in_section_plan(tmp_path):
    """A leaked ``release_outcome`` inside a section_plans view fails loud at SAVE time."""
    kwargs = _clean_save_kwargs()
    kwargs["section_plans"]["sec_efficacy"]["release_outcome"] = "released"
    with pytest.raises(GenerationSnapshotError) as exc:
        save_generation_snapshot(tmp_path, **kwargs)
    assert "release_outcome" in str(exc.value)
    assert not generation_snapshot_path(tmp_path).exists()


def test_load_refuses_verdict_key_injected_at_depth(tmp_path):
    """A snapshot hand-edited to inject a verdict key DEEP in the nested metadata fails loud on LOAD.

    Proves the guard runs on the LOAD path too (not only save): an attacker / corrupt artifact that
    bypassed the save guard by editing the JSON on disk is still rejected at re-entry.
    """
    # Write a clean snapshot, then inject a nested verdict key directly into the JSON on disk.
    save_generation_snapshot(tmp_path, **_clean_save_kwargs())
    path = generation_snapshot_path(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    # Depth: section_atom_catalogs -> section -> [list] -> atom dict -> d8_decision.
    raw["section_atom_catalogs"]["sec_efficacy"][0]["d8_decision"] = "GROUNDED"
    path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(GenerationSnapshotError) as exc:
        load_generation_snapshot(tmp_path)
    assert "d8_decision" in str(exc.value)


def test_load_refuses_verdict_key_in_list_element(tmp_path):
    """A verdict key nested inside a LIST element (not just a dict value) is caught (list recursion)."""
    save_generation_snapshot(tmp_path, **_clean_save_kwargs())
    path = generation_snapshot_path(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    # The atom-binding list element gets a forbidden key via a nested dict inside a list-of-dicts.
    raw["section_atom_catalogs"]["sec_efficacy"].append(
        {"atom_id": "atom_x", "nested": [{"verified_text": "DRUG X verified prose"}]}
    )
    path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(GenerationSnapshotError) as exc:
        load_generation_snapshot(tmp_path)
    assert "verified_text" in str(exc.value)


def test_load_refuses_missing_item5a_metadata(tmp_path):
    """A payload missing the ITEM-5a section-metadata keys (malformed v2) fails loud on LOAD."""
    save_generation_snapshot(tmp_path, **_clean_save_kwargs())
    path = generation_snapshot_path(tmp_path)
    raw = json.loads(path.read_text(encoding="utf-8"))
    del raw["section_plans"]
    path.write_text(json.dumps(raw, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    with pytest.raises(GenerationSnapshotError) as exc:
        load_generation_snapshot(tmp_path)
    assert "section_plans" in str(exc.value)


def test_save_refuses_atom_missing_binding_field(tmp_path):
    """An atom lacking a required evidence-span binding field fails loud (no partial binding)."""
    kwargs = _clean_save_kwargs()
    del kwargs["section_atom_catalogs"]["sec_efficacy"]["atom_001"]["span_end"]
    with pytest.raises(GenerationSnapshotError) as exc:
        save_generation_snapshot(tmp_path, **kwargs)
    assert "span_end" in str(exc.value)
    assert not generation_snapshot_path(tmp_path).exists()
