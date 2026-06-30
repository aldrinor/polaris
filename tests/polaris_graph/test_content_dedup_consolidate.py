"""I-deepfix-001 (#1344) W9 — content-dedup CONSOLIDATE-KEEP-ALL. Pure-function tests.

The W9 stage groups near-identical-BODY syndicated sources into keep-all corroboration
baskets: ANNOTATE only, never drop, never merge. Tests assert the §-1.3 invariants on
real evidence-row shapes (direct_quote / statement / title), including the false-green
guard the workflow draft hit (reading the empty 'content' key would collapse every row
into ONE cluster).
"""

from __future__ import annotations

import os

import pytest

from src.polaris_graph.synthesis import content_dedup_consolidate as cdc


_BODY_A = (
    "The randomized controlled trial enrolled 1240 adults with type 2 diabetes across "
    "37 centres. After 52 weeks the treatment arm showed a mean HbA1c reduction of 1.8 "
    "percentage points versus 0.4 in placebo, with the hazard ratio for the composite "
    "cardiovascular endpoint at 0.79 (95% CI 0.66 to 0.94). Adverse events were balanced "
    "between arms and no new safety signals emerged over the follow-up period."
)
_BODY_A_SYNDICATED = (
    "The randomized controlled trial enrolled 1240 adults with type 2 diabetes across "
    "37 centres. After 52 weeks the treatment arm showed a mean HbA1c reduction of 1.8 "
    "percentage points versus 0.4 in placebo, with the hazard ratio for the composite "
    "cardiovascular endpoint at 0.79 (95% CI 0.66 to 0.94). Adverse events were balanced "
    "between the arms and no new safety signals emerged over the follow-up period."  # tiny edit
)
_BODY_B = (
    "A separate cohort study of 8800 participants examined ambient air pollution and "
    "incident asthma in children. Each 10 microgram per cubic metre increase in PM2.5 "
    "was associated with a 12 percent higher incidence over a ten year window, after "
    "adjustment for socioeconomic status, parental smoking, and urban density gradients."
)


def _row(ev_id: str, **extra) -> dict:
    row = {
        "evidence_id": ev_id,
        "source_url": f"https://example.org/{ev_id}",
        "tier": "T1",
    }
    row.update(extra)
    return row


@pytest.fixture(autouse=True)
def _gate_on():
    prev = os.environ.pop("PG_CONTENT_DEDUP_CONSOLIDATE", None)
    prevc = os.environ.pop("PG_W9_MIN_BODY_CHARS", None)
    yield
    for k, v in (("PG_CONTENT_DEDUP_CONSOLIDATE", prev), ("PG_W9_MIN_BODY_CHARS", prevc)):
        if v is None:
            os.environ.pop(k, None)
        else:
            os.environ[k] = v


def test_exact_syndication_groups_keep_all():
    rows = [
        _row("ev_001", direct_quote=_BODY_A),
        _row("ev_002", direct_quote=_BODY_A),            # exact body twin (other URL)
        _row("ev_003", direct_quote=_BODY_B),            # unrelated
    ]
    out, tel = cdc.consolidate_body_syndication(rows)
    # KEEP-ALL: nothing dropped.
    assert len(out) == 3
    assert tel["rows_dropped"] == 0
    assert tel["baskets"] == 1
    # The two twins share one basket carrying BOTH ev_ids.
    assert out[0]["body_syndication_cluster_id"] == out[1]["body_syndication_cluster_id"]
    assert out[0]["body_syndication_count"] == 2
    assert out[0]["body_syndication_ev_ids"] == ["ev_001", "ev_002"]
    # The unrelated source stays a singleton (NOT annotated).
    assert "body_syndication_cluster_id" not in out[2]


def test_near_identical_body_groups():
    rows = [
        _row("ev_001", direct_quote=_BODY_A),
        _row("ev_002", direct_quote=_BODY_A_SYNDICATED),  # one-word edit -> near-dup
        _row("ev_003", direct_quote=_BODY_B),
    ]
    out, tel = cdc.consolidate_body_syndication(rows)
    assert tel["baskets"] == 1
    assert out[0]["body_syndication_count"] == 2
    assert "body_syndication_cluster_id" not in out[2]


def test_unrelated_sources_stay_singletons():
    rows = [
        _row("ev_001", direct_quote=_BODY_A),
        _row("ev_002", direct_quote=_BODY_B),
    ]
    out, tel = cdc.consolidate_body_syndication(rows)
    assert tel["baskets"] == 0
    assert tel["rows_grouped"] == 0
    for r in out:
        assert "body_syndication_cluster_id" not in r


def test_empty_content_key_does_not_collapse_all():
    # The false-green guard: every row has an EMPTY 'content' key but DIFFERENT bodies
    # in direct_quote. Reading 'content' would fold all into one cluster; reading
    # direct_quote keeps them apart.
    rows = [
        _row("ev_001", content="", direct_quote=_BODY_A),
        _row("ev_002", content="", direct_quote=_BODY_B),
    ]
    out, tel = cdc.consolidate_body_syndication(rows)
    assert tel["baskets"] == 0
    for r in out:
        assert "body_syndication_cluster_id" not in r


def test_statement_and_title_fallbacks():
    # No direct_quote: falls back to statement, then title. Two rows with the same long
    # statement still group.
    rows = [
        _row("ev_001", statement=_BODY_A),
        _row("ev_002", statement=_BODY_A),
        _row("ev_003", title=_BODY_B),  # unrelated, via title fallback
    ]
    out, tel = cdc.consolidate_body_syndication(rows)
    assert tel["baskets"] == 1
    assert out[0]["body_syndication_count"] == 2
    assert "body_syndication_cluster_id" not in out[2]


def test_short_body_rows_stay_singletons():
    # Bodies below the min-char floor are too small to call syndication -> singletons.
    rows = [
        _row("ev_001", direct_quote="HbA1c fell 1.8 points."),
        _row("ev_002", direct_quote="HbA1c fell 1.8 points."),
    ]
    out, tel = cdc.consolidate_body_syndication(rows)
    assert tel["baskets"] == 0
    assert tel["eligible"] == 0
    for r in out:
        assert "body_syndication_cluster_id" not in r


def test_kill_switch_off_no_annotation():
    os.environ["PG_CONTENT_DEDUP_CONSOLIDATE"] = "0"
    rows = [
        _row("ev_001", direct_quote=_BODY_A),
        _row("ev_002", direct_quote=_BODY_A),
    ]
    out, tel = cdc.consolidate_body_syndication(rows)
    assert tel["enabled"] is False
    assert tel["baskets"] == 0
    for r in out:
        assert "body_syndication_cluster_id" not in r


def test_zero_dropped_invariant_large():
    # 20 rows, 2 syndication pairs; assert length is exactly preserved.
    rows = []
    for i in range(16):
        rows.append(_row(f"ev_{i:03d}", direct_quote=_BODY_B + f" Variant note {i}."))
    rows.append(_row("ev_900", direct_quote=_BODY_A))
    rows.append(_row("ev_901", direct_quote=_BODY_A))
    n_in = len(rows)
    out, tel = cdc.consolidate_body_syndication(rows)
    assert len(out) == n_in
    assert tel["rows_dropped"] == 0
    # The A-twins group; assert they share a basket.
    a_rows = [r for r in out if r["evidence_id"] in ("ev_900", "ev_901")]
    assert a_rows[0].get("body_syndication_count") == 2
