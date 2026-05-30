"""Campaign KG reuse read-path, FAIL-CLOSED (I-meta-002-q1d #948). NO network / NO spend.

Asserts Codex brief-gate requirements: reuse is MECHANICALLY gated (a prior-VERIFIED claim is OMITTED
unless the CURRENT corpus independently supports it, by strict_verify's own content+decimal primitives),
matched claims are anchored to CURRENT evidence ids only (never prior ids), anti-poisoning (only VERIFIED
reusable) holds, default-OFF, and the analyst advisory block is empty when there is nothing to reuse.
"""

from __future__ import annotations

import pytest

from src.polaris_graph.generator.analyst_synthesis import _format_prior_verified_context
from src.polaris_graph.memory.kg_reuse_gate import (
    gather_reuse_context,
    kg_reuse_enabled,
    match_prior_claims_to_current_corpus,
)
from src.polaris_graph.memory.verified_claim_graph import VerifiedClaimGraphStore

_EV = [{"evidence_id": "ev_005",
        "direct_quote": "Tirzepatide reduced HbA1c by 2.1 percent in adults with type 2 diabetes."}]


# ── match-gate (mechanical, reuses strict_verify primitives) ──────────────────────────────────────
def test_match_supported_claim_anchored_to_current_ev():
    out = match_prior_claims_to_current_corpus(["tirzepatide reduced HbA1c by 2.1 percent"], _EV)
    assert out == [{"claim_text": "tirzepatide reduced HbA1c by 2.1 percent", "evidence_id": "ev_005"}]


def test_match_unsupported_claim_omitted():
    assert match_prior_claims_to_current_corpus(["semaglutide caused injection-site reactions"], _EV) == []


def test_match_decimal_mismatch_omitted():
    # 3.5 is not in the evidence (which says 2.1) → omitted (strict_verify decimal-subset rule)
    assert match_prior_claims_to_current_corpus(["tirzepatide reduced HbA1c by 3.5 percent"], _EV) == []


def test_match_low_overlap_omitted():
    # only one shared content word ("tirzepatide") < min threshold (2) → omitted
    assert match_prior_claims_to_current_corpus(["tirzepatide marketing authorisation timeline"], _EV) == []


def test_match_dedup_same_claim_once():
    ev2 = _EV + [{"evidence_id": "ev_009", "direct_quote": _EV[0]["direct_quote"]}]
    out = match_prior_claims_to_current_corpus(["tirzepatide reduced HbA1c by 2.1 percent"], ev2)
    assert len(out) == 1  # first current-corpus support is enough


# ── kill-switch ──────────────────────────────────────────────────────────────────────────────────
def test_kg_reuse_enabled_default_off(monkeypatch):
    monkeypatch.delenv("PG_SWEEP_KG_REUSE", raising=False)
    assert kg_reuse_enabled() is False
    monkeypatch.setenv("PG_SWEEP_KG_REUSE", "1")
    assert kg_reuse_enabled() is True


def test_kg_reuse_enabled_normalizes_case(monkeypatch):
    # Codex diff-gate iter-1 P2: FALSE/NO/OFF in any case must stay disabled.
    for off in ("FALSE", "False", "No", "OFF", "off", "0", ""):
        monkeypatch.setenv("PG_SWEEP_KG_REUSE", off)
        assert kg_reuse_enabled() is False, off
    for on in ("1", "true", "yes", "ON"):
        monkeypatch.setenv("PG_SWEEP_KG_REUSE", on)
        assert kg_reuse_enabled() is True, on


def test_gather_read_only_does_not_create_missing_db(tmp_path, monkeypatch):
    """Codex diff-gate iter-1 P1: an enabled read against a MISSING campaign db must fail-open to []
    WITHOUT creating the file (strictly read-only; no mutation)."""
    monkeypatch.setenv("PG_SWEEP_KG_REUSE", "1")
    missing = tmp_path / "nope" / "campaign.db"
    assert gather_reuse_context(str(missing), "tirzepatide HbA1c", _EV) == []
    assert not missing.exists()        # the read-only path created nothing
    assert not missing.parent.exists()  # and did not mkdir the parent


def test_read_only_store_cannot_write(tmp_path):
    """A read_only store opens existing data but rejects writes (mechanical read-only)."""
    import sqlite3
    db = str(tmp_path / "campaign.db")
    _seed_campaign_store(db)
    ro = VerifiedClaimGraphStore(db_path=db, read_only=True)
    try:
        assert ro.query_related_claims("tirzepatide HbA1c")  # reads fine
        with pytest.raises(sqlite3.OperationalError):
            ro.write_claim(claim_text="x written via ro", claim_id="z",
                           verdict="VERIFIED", role_verdicts={}, timestamp="t")
    finally:
        ro.close()


def test_gather_flag_off_returns_empty(tmp_path, monkeypatch):
    monkeypatch.delenv("PG_SWEEP_KG_REUSE", raising=False)
    db = str(tmp_path / "campaign.db")
    assert gather_reuse_context(db, "tirzepatide HbA1c", _EV) == []


# ── campaign store: anti-poisoning + Codex required #2 (omit unsupported) + #3 (current id only) ────
def _seed_campaign_store(db_path: str) -> None:
    store = VerifiedClaimGraphStore(db_path=db_path)
    try:
        store.write_claim(claim_text="tirzepatide reduced HbA1c by 2.1 percent",
                          claim_id="c1", verdict="VERIFIED", role_verdicts={}, timestamp="t0")
        # an UNSUPPORTED-verdict prior claim (anti-poisoning: must never be reusable)
        store.write_claim(claim_text="tirzepatide reduced HbA1c by 9.9 percent",
                          claim_id="c2", verdict="UNSUPPORTED", role_verdicts={}, timestamp="t0")
        # a VERIFIED prior claim NOT present in the current corpus (must be omitted by the match-gate)
        store.write_claim(claim_text="tirzepatide increased cardiovascular mortality risk",
                          claim_id="c3", verdict="VERIFIED", role_verdicts={}, timestamp="t0")
    finally:
        store.close()


def test_gather_anti_poisoning_and_unsupported_omitted(tmp_path, monkeypatch):
    monkeypatch.setenv("PG_SWEEP_KG_REUSE", "1")
    db = str(tmp_path / "campaign.db")
    _seed_campaign_store(db)
    out = gather_reuse_context(db, "What is the effect of tirzepatide on HbA1c?", _EV)
    texts = {c["claim_text"] for c in out}
    # VERIFIED + current-corpus-supported → present, anchored to the CURRENT ev id
    assert "tirzepatide reduced HbA1c by 2.1 percent" in texts
    assert all(c["evidence_id"] == "ev_005" for c in out)  # CURRENT id only, never a prior id
    # UNSUPPORTED-verdict prior (c2) → anti-poisoning excludes it
    assert "tirzepatide reduced HbA1c by 9.9 percent" not in texts
    # VERIFIED but NOT in current corpus (c3) → mechanically omitted (Codex required #2)
    assert "tirzepatide increased cardiovascular mortality risk" not in texts


# ── analyst advisory block rendering ───────────────────────────────────────────────────────────────
def test_format_prior_verified_context_empty_is_blank():
    assert _format_prior_verified_context(None) == ""
    assert _format_prior_verified_context([]) == ""


def test_format_prior_verified_context_renders_claim_and_current_ev():
    block = _format_prior_verified_context(
        [{"claim_text": "tirzepatide reduced HbA1c by 2.1 percent", "evidence_id": "ev_005"}]
    )
    assert "CROSS-QUESTION CONSISTENCY" in block
    assert "tirzepatide reduced HbA1c by 2.1 percent" in block
    assert "ev_005" in block
    assert "[N]" in block  # instructs current-bibliography citation only
