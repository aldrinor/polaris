"""Unit tests for verdict_gate substrate_prep traversal.

Regression test for the gate fix landed at 4eaa628: verdict_gate's
_changed_files_to_task_ids must traverse `substrate_prep[]` entries
inside each phase task, not just the task-level `changed_files_glob`.

Before the fix, substrate_prep edits (1.8_prep_briefing_pack,
4_5_prep_drafts, etc.) fell through the gate as "no task implicated"
and required infrastructure-only justification — defeating per-task
verdict enforcement on prep skeletons.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

POLARIS_ROOT = Path(__file__).resolve().parents[2]
GATE_PATH = POLARIS_ROOT / "scripts" / "autoloop" / "verdict_gate.py"


@pytest.fixture(scope="module")
def gate_module():
    spec = importlib.util.spec_from_file_location("verdict_gate_under_test", GATE_PATH)
    module = importlib.util.module_from_spec(spec)
    sys.modules["verdict_gate_under_test"] = module
    spec.loader.exec_module(module)
    return module


def test_substrate_prep_entry_is_implicated_when_glob_matches(gate_module):
    matrix = {
        "phase_4": {
            "task_4_5": {
                "title": "Handover package",
                "substrate_prep": [
                    {
                        "id": "4_5_prep_drafts",
                        "changed_files_glob": ["docs/carney_handover/**"],
                    }
                ],
            }
        }
    }
    files = ["docs/carney_handover/one_pager.md"]
    implicated = gate_module._changed_files_to_task_ids(files, matrix)
    assert implicated == {"4_5_prep_drafts"}, (
        f"substrate_prep entry should be picked up; got {implicated}"
    )


def test_task_level_glob_still_works_alongside_substrate_prep(gate_module):
    matrix = {
        "phase_1": {
            "task_1_1": {
                "changed_files_glob": ["src/polaris_v6/scope/**"],
                "substrate_prep": [
                    {
                        "id": "1_1_prep",
                        "changed_files_glob": ["docs/walkthroughs/1.1/**"],
                    }
                ],
            }
        }
    }
    # Task-level glob match
    impl_a = gate_module._changed_files_to_task_ids(
        ["src/polaris_v6/scope/decision.py"], matrix
    )
    assert "1.1" in impl_a
    # Substrate-prep glob match
    impl_b = gate_module._changed_files_to_task_ids(
        ["docs/walkthroughs/1.1/briefing.md"], matrix
    )
    assert "1_1_prep" in impl_b
    # Both at once
    impl_c = gate_module._changed_files_to_task_ids(
        ["src/polaris_v6/scope/decision.py", "docs/walkthroughs/1.1/briefing.md"], matrix
    )
    assert impl_c == {"1.1", "1_1_prep"}


def test_substrate_prep_without_id_is_skipped(gate_module):
    matrix = {
        "phase_2": {
            "task_2_1": {
                "substrate_prep": [
                    {
                        # No id field — gate must not crash, must not implicate ""
                        "changed_files_glob": ["docs/anywhere/**"],
                    }
                ],
            }
        }
    }
    implicated = gate_module._changed_files_to_task_ids(
        ["docs/anywhere/x.md"], matrix
    )
    assert implicated == set(), f"id-less substrate_prep should not implicate; got {implicated}"


def test_substrate_prep_prefers_task_id_field_over_id(gate_module):
    matrix = {
        "phase_3": {
            "task_3_1": {
                "substrate_prep": [
                    {
                        "id": "3_1_prep",
                        "task_id": "3_1_prep_canonical",
                        "changed_files_glob": ["src/foo.py"],
                    }
                ],
            }
        }
    }
    implicated = gate_module._changed_files_to_task_ids(["src/foo.py"], matrix)
    assert implicated == {"3_1_prep_canonical"}, (
        f"task_id should override id field; got {implicated}"
    )


def test_real_matrix_substrate_prep_entries_match_canonical_globs(gate_module):
    """End-to-end: load the actual canonical matrix from HEAD and verify
    substrate_prep entries (4_5_prep_drafts, walkthrough packs) resolve.
    """
    matrix = gate_module._load_matrix()

    # 4_5_prep_drafts: docs/carney_handover/**
    impl_4_5 = gate_module._changed_files_to_task_ids(
        ["docs/carney_handover/one_pager.md"], matrix
    )
    assert "4_5_prep_drafts" in impl_4_5

    # 1.8_prep_briefing_pack: docs/walkthroughs/1.8/**
    impl_1_8 = gate_module._changed_files_to_task_ids(
        ["docs/walkthroughs/1.8/briefing.md"], matrix
    )
    assert "1.8_prep_briefing_pack" in impl_1_8

    # 2A.7 walkthrough
    impl_2a = gate_module._changed_files_to_task_ids(
        ["docs/walkthroughs/2A.7/briefing.md"], matrix
    )
    assert "2a_7_prep_briefing_pack" in impl_2a


def test_unrelated_files_implicate_no_task(gate_module):
    matrix = {
        "phase_1": {
            "task_1_1": {
                "changed_files_glob": ["src/specific_module/**"],
                "substrate_prep": [
                    {
                        "id": "1_1_prep",
                        "changed_files_glob": ["docs/walkthroughs/1.1/**"],
                    }
                ],
            }
        }
    }
    implicated = gate_module._changed_files_to_task_ids(["unrelated/path.txt"], matrix)
    assert implicated == set()
