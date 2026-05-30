"""Verified-claim graph store tests (I-meta-002 sub-PR-5). Temp SQLite, offline, NO network.

Asserts write+read, the anti-snowball-poisoning VERIFIED-only reuse filter, and the
cross-time contradiction flag. The store opens a temp SQLite path; no datetime.now() is used
(the timestamp is passed in).
"""

from __future__ import annotations

from pathlib import Path

from src.polaris_graph.memory.verified_claim_graph import VerifiedClaimGraphStore

_TS = "2026-05-29T00:00:00Z"
_ROLE_VERDICTS = {"mirror": "supported", "sentinel": "grounded", "judge": "VERIFIED"}


def _open(tmp_path: Path) -> VerifiedClaimGraphStore:
    return VerifiedClaimGraphStore(db_path=tmp_path / "graph.sqlite")


# --- write + read back a VERIFIED claim via the reuse pool ---
def test_write_and_query_verified_claim(tmp_path: Path) -> None:
    with _open(tmp_path) as store:
        store.write_claim(
            claim_text="Tirzepatide 5 mg reduced HbA1c.",
            claim_id="c1",
            verdict="VERIFIED",
            role_verdicts=_ROLE_VERDICTS,
            timestamp=_TS,
        )
        related = store.query_related_claims("Tirzepatide HbA1c outcome data")
    assert len(related) == 1
    assert related[0].claim_id == "c1"
    assert related[0].verdict == "VERIFIED"
    assert related[0].reusable is True
    assert related[0].role_verdicts == _ROLE_VERDICTS
    assert related[0].timestamp == _TS


# --- Codex sub-PR-5 diff P2: empty/content-free query returns nothing (not the whole pool) ---
def test_empty_query_returns_nothing(tmp_path: Path) -> None:
    with _open(tmp_path) as store:
        store.write_claim(
            claim_text="Tirzepatide 5 mg reduced HbA1c.",
            claim_id="c1",
            verdict="VERIFIED",
            role_verdicts=_ROLE_VERDICTS,
            timestamp=_TS,
        )
        # An empty string would substring-match every row ("" in x) without the guard.
        assert store.query_related_claims("") == []
        assert store.query_related_claims("   ") == []


# --- anti-poisoning: a non-VERIFIED claim is persisted but NOT returned for reuse ---
def test_non_verified_claim_excluded_from_reuse(tmp_path: Path) -> None:
    with _open(tmp_path) as store:
        store.write_claim(
            claim_text="Tirzepatide caused no adverse events.",
            claim_id="bad-1",
            verdict="FABRICATED",
            role_verdicts={"judge": "FABRICATED"},
            timestamp=_TS,
        )
        store.write_claim(
            claim_text="Tirzepatide reduced body weight.",
            claim_id="ok-1",
            verdict="VERIFIED",
            role_verdicts=_ROLE_VERDICTS,
            timestamp=_TS,
        )
        related = store.query_related_claims("Tirzepatide effects")
    returned_ids = {r.claim_id for r in related}
    assert "bad-1" not in returned_ids  # FABRICATED can never be reused
    assert "ok-1" in returned_ids


def test_all_non_verified_verdicts_excluded(tmp_path: Path) -> None:
    with _open(tmp_path) as store:
        for verdict in ("FABRICATED", "UNSUPPORTED", "PARTIAL", "UNREACHABLE"):
            store.write_claim(
                claim_text=f"Tirzepatide claim {verdict}.",
                claim_id=f"id-{verdict}",
                verdict=verdict,
                role_verdicts={"judge": verdict},
                timestamp=_TS,
            )
        related = store.query_related_claims("Tirzepatide claim")
    assert related == []  # none of the four non-VERIFIED verdicts is reusable


# --- contradiction flag: a negation-polarity mismatch over shared keywords is flagged ---
def test_contradiction_flag_negation_mismatch(tmp_path: Path) -> None:
    with _open(tmp_path) as store:
        store.write_claim(
            claim_text="Constipation led to treatment discontinuation.",
            claim_id="prior-1",
            verdict="VERIFIED",
            role_verdicts=_ROLE_VERDICTS,
            timestamp=_TS,
        )
        flags = store.find_contradictions(
            "Constipation did not lead to treatment discontinuation."
        )
    assert len(flags) == 1
    assert flags[0].prior_claim_id == "prior-1"
    assert "negation" in flags[0].reason


# --- contradiction flag: divergent numeric tokens over shared keywords is flagged ---
def test_contradiction_flag_numeric_mismatch(tmp_path: Path) -> None:
    with _open(tmp_path) as store:
        store.write_claim(
            claim_text="The recommended maintenance dose is 5.0 mg weekly.",
            claim_id="prior-dose",
            verdict="VERIFIED",
            role_verdicts=_ROLE_VERDICTS,
            timestamp=_TS,
        )
        flags = store.find_contradictions(
            "The recommended maintenance dose is 15.0 mg weekly."
        )
    assert len(flags) == 1
    assert flags[0].prior_claim_id == "prior-dose"
    assert "numeric" in flags[0].reason


# --- contradiction flag does NOT fire on an agreeing claim (same polarity, same numbers) ---
def test_no_contradiction_on_agreement(tmp_path: Path) -> None:
    with _open(tmp_path) as store:
        store.write_claim(
            claim_text="The maintenance dose is 5.0 mg weekly.",
            claim_id="prior-dose",
            verdict="VERIFIED",
            role_verdicts=_ROLE_VERDICTS,
            timestamp=_TS,
        )
        flags = store.find_contradictions("The maintenance dose is 5.0 mg weekly.")
    assert flags == []


# --- contradiction hook only considers the VERIFIED reuse pool (never a poisoned prior) ---
def test_contradiction_ignores_non_verified_prior(tmp_path: Path) -> None:
    with _open(tmp_path) as store:
        store.write_claim(
            claim_text="Constipation led to treatment discontinuation.",
            claim_id="poison-1",
            verdict="UNSUPPORTED",  # not reusable -> not a contradiction source
            role_verdicts={"judge": "UNSUPPORTED"},
            timestamp=_TS,
        )
        flags = store.find_contradictions(
            "Constipation did not lead to treatment discontinuation."
        )
    assert flags == []  # the non-VERIFIED prior is invisible to the contradiction hook


# --- run_dir constructor variant creates the default-named DB under the run dir ---
def test_run_dir_default_path(tmp_path: Path) -> None:
    run_dir = tmp_path / "run123"
    with VerifiedClaimGraphStore(run_dir=run_dir) as store:
        store.write_claim(
            claim_text="A verified claim.",
            claim_id="c1",
            verdict="VERIFIED",
            role_verdicts=_ROLE_VERDICTS,
            timestamp=_TS,
        )
    assert (run_dir / "verified_claim_graph.sqlite").is_file()
