"""Lever 3 (coverage spine, PG_COVERAGE_SPINE) — gated, additive, faithfulness-safe.

The lever adds ONE directive to the outline self-review prompt when the flag is on. Off => the
directive is the empty string => the assembled prompt is byte-identical to today. The directive is
RQ-general (names no concept itself), additive-only (never drop/rename/invent a section), and never
permits an uncited assertion.
"""
import os

import pytest

from src.polaris_graph.outline.outline_agent import (
    _coverage_spine_block,
    _coverage_spine_enabled,
)


@pytest.fixture(autouse=True)
def _clear_flag():
    prev = os.environ.pop("PG_COVERAGE_SPINE", None)
    yield
    if prev is None:
        os.environ.pop("PG_COVERAGE_SPINE", None)
    else:
        os.environ["PG_COVERAGE_SPINE"] = prev


def test_off_is_empty_string_byte_identical():
    # Default (unset) => off => the injection point receives "" => prompt byte-identical to today.
    assert _coverage_spine_enabled() is False
    assert _coverage_spine_block() == ""


def test_explicit_off_values_stay_empty():
    for v in ("0", "false", "off", "no", ""):
        os.environ["PG_COVERAGE_SPINE"] = v
        assert _coverage_spine_block() == "", f"{v!r} should be off"


def test_on_emits_directive():
    os.environ["PG_COVERAGE_SPINE"] = "1"
    assert _coverage_spine_enabled() is True
    block = _coverage_spine_block()
    assert block, "directive must be non-empty when on"
    # role taxonomy + threading intent present
    for phrase in ("COVERAGE SPINE", "distinct analytical role",
                   "framing", "mechanism", "cross-context comparison",
                   "synthesis", "implication"):
        assert phrase in block, f"missing {phrase!r}"
    # ends with a paragraph break so it slots cleanly before QUESTION:
    assert block.endswith("\n\n")


def test_additive_only_and_faithfulness_safe():
    os.environ["PG_COVERAGE_SPINE"] = "1"
    block = _coverage_spine_block()
    # never drops/renames/invents a section
    assert "NEVER removes, renames, or invents" in block
    assert "do NOT create a new section" in block
    assert "EXISTING section" in block
    # routes only as cited synthesis, never an uncited assertion
    assert "CITED synthesis" in block
    assert "do NOT add any uncited assertion" in block
    # relies on the existing verbatim-quote grounding machinery
    assert "verbatim QUESTION quote" in block


def test_general_no_task_specific_literals():
    os.environ["PG_COVERAGE_SPINE"] = "1"
    low = _coverage_spine_block().lower()
    # the directive names NO concept itself — it threads whatever the QUESTION names.
    for banned in ("labor", "artificial intelligence", "fourth industrial",
                   "generative ai", "4ir", "occupation", "task 72"):
        assert banned not in low, f"task-specific literal leaked: {banned!r}"
    # it must refer to the QUESTION generically
    assert "the QUESTION" in _coverage_spine_block()


def test_toggle_changes_output():
    os.environ["PG_COVERAGE_SPINE"] = "1"
    on = _coverage_spine_block()
    os.environ["PG_COVERAGE_SPINE"] = "0"
    off = _coverage_spine_block()
    assert on != off
    assert off == ""
