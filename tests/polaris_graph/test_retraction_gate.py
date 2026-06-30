"""I-deepfix-001 (#1344) Bug B — retraction grounding gate. Pure-function unit tests.

No network, no model, no fixtures. The gate excludes retracted/withdrawn sources from
the GROUNDING pool (so a withdrawn RCT can never ground generated prose) while RETURNING
them for disclosure (§-1.3 weight-not-filter: recorded, never silently dropped). The
predicate REUSES authority.supersession._is_truthy (single source of truth), so a string
'false'/'0'/'no'/'' or a missing flag is NOT retracted (fail-open).
"""

from __future__ import annotations

import os

import pytest

from src.polaris_graph.generator import retraction_gate as rg


# ---- real evidence-row shapes (the keys live_retriever actually writes) -----------

def _groundable_row(ev_id: str, **extra) -> dict:
    """A normal groundable evidence row (the _row dict built in live_retriever)."""
    row = {
        "evidence_id": ev_id,
        "source_url": f"https://example.org/{ev_id}",
        "source_title": f"Real Study {ev_id}",
        "title": f"Real Study {ev_id}",
        "direct_quote": "The hazard ratio was 0.82 (95% CI 0.70-0.96).",
        "tier": "T1",
    }
    row.update(extra)
    return row


@pytest.fixture(autouse=True)
def _gate_on():
    """Default the kill-switch ON for each test (clinical-safety default)."""
    prev = os.environ.pop("PG_RETRACTION_GROUNDING_GATE", None)
    yield
    if prev is None:
        os.environ.pop("PG_RETRACTION_GROUNDING_GATE", None)
    else:
        os.environ["PG_RETRACTION_GROUNDING_GATE"] = prev


# ---- is_row_retracted: the predicate -----------------------------------------------

def test_string_false_is_not_retracted():
    # The exact bug guard: a string 'false'/'0'/'no'/'' must NOT strip the source.
    for val in ("false", "False", "FALSE", "0", "no", "off", ""):
        assert rg.is_row_retracted({"is_retracted": val}) is False, val


def test_missing_field_is_not_retracted_fail_open():
    assert rg.is_row_retracted({"evidence_id": "ev_001"}) is False


def test_bool_true_is_retracted():
    assert rg.is_row_retracted({"is_retracted": True}) is True


def test_string_truthy_variants_are_retracted():
    for val in ("1", "true", "yes", "retracted", "withdrawn"):
        assert rg.is_row_retracted({"is_retracted": val}) is True, val


def test_alternate_retraction_keys():
    assert rg.is_row_retracted({"retracted": True}) is True
    assert rg.is_row_retracted({"retraction_notice": "yes"}) is True
    assert rg.is_row_retracted({"withdrawn": True}) is True


def test_bool_false_is_not_retracted():
    # bool False (not just the string) must be groundable.
    assert rg.is_row_retracted({"is_retracted": False}) is False


# ---- partition_pool: the grounding exclusion ---------------------------------------

def test_retracted_excluded_real_retracted_disclosed():
    pool = {
        "ev_001": _groundable_row("ev_001"),
        "ev_002": _groundable_row("ev_002", is_retracted=True),  # a real retracted study
        "ev_003": _groundable_row("ev_003"),
    }
    groundable, retracted = rg.partition_pool(pool)
    # Excluded from grounding...
    assert set(groundable.keys()) == {"ev_001", "ev_003"}
    assert "ev_002" not in groundable
    # ...but RETURNED for disclosure (not silently dropped — §-1.3).
    assert len(retracted) == 1
    assert retracted[0]["evidence_id"] == "ev_002"
    # union == input: nothing vanished.
    assert len(groundable) + len(retracted) == len(pool)


def test_string_false_row_stays_groundable():
    pool = {
        "ev_001": _groundable_row("ev_001", is_retracted="false"),
        "ev_002": _groundable_row("ev_002", is_retracted="0"),
    }
    groundable, retracted = rg.partition_pool(pool)
    assert set(groundable.keys()) == {"ev_001", "ev_002"}
    assert retracted == []


def test_no_retracted_is_byte_identical_pool():
    pool = {"ev_001": _groundable_row("ev_001"), "ev_002": _groundable_row("ev_002")}
    groundable, retracted = rg.partition_pool(pool)
    assert groundable == pool
    assert retracted == []


def test_input_not_mutated():
    pool = {"ev_001": _groundable_row("ev_001", is_retracted=True)}
    before = dict(pool)
    rg.partition_pool(pool)
    assert pool == before  # the input dict is untouched


def test_idempotent_on_clean_pool():
    pool = {
        "ev_001": _groundable_row("ev_001"),
        "ev_002": _groundable_row("ev_002", is_retracted=True),
    }
    groundable1, _ = rg.partition_pool(pool)
    groundable2, retracted2 = rg.partition_pool(groundable1)
    # Re-running on the already-clean pool changes nothing and finds no new retracted.
    assert groundable2 == groundable1
    assert retracted2 == []


def test_kill_switch_off_returns_everything():
    os.environ["PG_RETRACTION_GROUNDING_GATE"] = "0"
    pool = {
        "ev_001": _groundable_row("ev_001"),
        "ev_002": _groundable_row("ev_002", is_retracted=True),
    }
    groundable, retracted = rg.partition_pool(pool)
    assert groundable == pool  # OFF => byte-identical, no exclusion
    assert retracted == []


# ---- disclosure_records: the audit trail -------------------------------------------

def test_disclosure_records_shape():
    pool = {"ev_002": _groundable_row("ev_002", is_retracted=True)}
    _, retracted = rg.partition_pool(pool)
    recs = rg.disclosure_records(retracted)
    assert len(recs) == 1
    rec = recs[0]
    assert rec["evidence_id"] == "ev_002"
    assert rec["title"] == "Real Study ev_002"
    assert rec["url"] == "https://example.org/ev_002"
    assert rec["retraction_flag"] == "is_retracted"
    assert rec["excluded_from_grounding"] is True


def test_disclosure_flag_names_the_truthy_key():
    pool = {"ev_009": _groundable_row("ev_009", withdrawn=True)}
    _, retracted = rg.partition_pool(pool)
    recs = rg.disclosure_records(retracted)
    assert recs[0]["retraction_flag"] == "withdrawn"


# ---- partition_rows: the RUN-LEVEL (list) form (Codex iter-1 P0 fix) ----------------

def test_partition_rows_excludes_retracted_keeps_disclosed():
    rows = [
        _groundable_row("ev_001"),
        _groundable_row("ev_002", is_retracted=True),
        _groundable_row("ev_003"),
    ]
    groundable, retracted = rg.partition_rows(rows)
    assert [r["evidence_id"] for r in groundable] == ["ev_001", "ev_003"]
    assert [r["evidence_id"] for r in retracted] == ["ev_002"]
    # union == input (nothing vanished); order preserved.
    assert len(groundable) + len(retracted) == len(rows)


def test_partition_rows_string_false_stays_groundable():
    rows = [_groundable_row("ev_001", is_retracted="false")]
    groundable, retracted = rg.partition_rows(rows)
    assert [r["evidence_id"] for r in groundable] == ["ev_001"]
    assert retracted == []


def test_partition_rows_does_not_mutate_input():
    rows = [_groundable_row("ev_001", is_retracted=True)]
    before = [dict(r) for r in rows]
    rg.partition_rows(rows)
    assert rows == before


def test_partition_rows_kill_switch_off():
    os.environ["PG_RETRACTION_GROUNDING_GATE"] = "0"
    rows = [_groundable_row("ev_001", is_retracted=True), _groundable_row("ev_002")]
    groundable, retracted = rg.partition_rows(rows)
    assert [r["evidence_id"] for r in groundable] == ["ev_001", "ev_002"]
    assert retracted == []
