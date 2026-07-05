"""P0-2 (I-deepfix-001) — RENDER-SEAM FAITHFULNESS GATE: drop non-VERIFIED, do NOT caveat.

The leak
--------
Under the always-release reframe the render seam KEPT every non-VERIFIED settled 4-role verdict and
appended a ``[confidence: low ...]`` caveat (``annotate_report_against_verdicts``). So a claim the
4-role engine settled UNSUPPORTED / FABRICATED / UNREACHABLE / PARTIAL still shipped as a low-
confidence line in the section body. Per §-1.3 the faithfulness engine is the ONE hard gate, so a
non-VERIFIED settled verdict reaching rendered prose is a LEAK.

The fix
-------
``apply_render_verdict_gate`` (the SAME function the runner wires at the render seam) DROPS every
non-VERIFIED settled verdict from prose instead of caveating it: ``reconcile_report_against_verdicts``
removes the sentence (-> the visible gap language), keeps every VERIFIED neighbour byte-for-byte, and
an emptied section falls to the TIER-4 section gap-stub (never blanked). PARTIAL is configurable:
default DROP; ``PG_RENDER_VERDICT_GATE_ADMIT_PARTIAL`` keeps + labels PARTIAL only. The gate is
faithfulness-STRENGTHENING — it drops MORE unfaithful text than the annotate path it replaces.

RED before the fix: ``apply_render_verdict_gate`` / ``partition_verdicts_for_render`` do not exist
(ImportError). GREEN after: the FABRICATED/UNSUPPORTED claims are dropped, the VERIFIED claim
survives, no ``[confidence:`` caveat is present, and an all-non-VERIFIED section shows the gap line.
"""

from __future__ import annotations

from src.polaris_graph.roles.report_redactor import (
    _GAP_REPLACEMENT,
    annotate_report_against_verdicts,
    apply_render_verdict_gate,
    partition_verdicts_for_render,
    render_verdict_gate_admit_partial,
    render_verdict_gate_enabled,
)

_CONFIDENCE_LEAK_MARKER = "[confidence:"


def _findings_body() -> str:
    """Two sections: A carries a VERIFIED sentence + a FABRICATED sentence on ONE line (so the
    VERIFIED neighbour must keep its [N] marker after the FABRICATED sibling is dropped); B carries
    ONLY an UNSUPPORTED sentence (so dropping it must leave the gap line, not a blank section)."""
    return (
        "# Findings\n"
        "\n"
        "## Section A\n"
        "The sky is blue in clear weather.[1] Ravens can count to eight reliably.[2]\n"
        "\n"
        "## Section B\n"
        "Aspirin cures every cancer overnight.[3]\n"
    )


def _audit_map() -> dict[str, dict]:
    return {
        "c_verified": {"sentence": "The sky is blue in clear weather.", "severity": "S1"},
        "c_fabricated": {"sentence": "Ravens can count to eight reliably.", "severity": "S1"},
        "c_unsupported": {"sentence": "Aspirin cures every cancer overnight.", "severity": "S0"},
    }


def _verdicts() -> dict[str, str]:
    return {
        "c_verified": "VERIFIED",
        "c_fabricated": "FABRICATED",
        "c_unsupported": "UNSUPPORTED",
    }


# ─────────────────────────────────────────────────────────────────
# The leak, documented: the legacy annotate path KEEPS + caveats the non-VERIFIED claims.
# ─────────────────────────────────────────────────────────────────
def test_legacy_annotate_leaks_nonverified_as_caveated_prose():
    """Baseline that pins the regression: annotate keeps the FABRICATED/UNSUPPORTED sentences and
    appends a ``[confidence:`` caveat — the exact leak the render gate closes."""
    annotated = annotate_report_against_verdicts(
        _findings_body(), _verdicts(), _audit_map(), marker_by_claim={},
    )
    body = annotated.report_text
    # The fabricated + unsupported prose is STILL present (kept, not dropped)...
    assert "Ravens can count to eight reliably" in body
    assert "Aspirin cures every cancer overnight" in body
    # ...and it is shipped as a caveated low-confidence line (the leak).
    assert _CONFIDENCE_LEAK_MARKER in body
    assert annotated.annotated_count == 2


# ─────────────────────────────────────────────────────────────────
# The fix: the render gate DROPS the non-VERIFIED claims (default), never caveats them.
# ─────────────────────────────────────────────────────────────────
def test_render_gate_drops_fabricated_and_unsupported_keeps_verified():
    result = apply_render_verdict_gate(
        _findings_body(), _verdicts(), _audit_map(), marker_by_claim={},
    )
    body = result.report_text

    assert result.outcome == "reconciled"
    # FABRICATED + UNSUPPORTED prose is GONE from the shipped body.
    assert "Ravens can count to eight reliably" not in body
    assert "Aspirin cures every cancer overnight" not in body
    # It is DROPPED, not caveated — NO confidence marker anywhere.
    assert _CONFIDENCE_LEAK_MARKER not in body
    # The VERIFIED neighbour survives byte-for-byte, keeping its [1] citation.
    assert "The sky is blue in clear weather.[1]" in body
    # Both non-VERIFIED claims are recorded as dropped; nothing labeled.
    assert set(result.dropped_claim_ids) == {"c_fabricated", "c_unsupported"}
    assert result.labeled_claim_ids == []


def test_render_gate_does_not_blank_a_section_that_keeps_a_verified_claim():
    """Section A still has a VERIFIED claim after the drop -> it must NOT be blanked; the VERIFIED
    sentence must remain and its heading survive."""
    result = apply_render_verdict_gate(
        _findings_body(), _verdicts(), _audit_map(), marker_by_claim={},
    )
    body = result.report_text
    assert "## Section A" in body
    assert "The sky is blue in clear weather" in body


def test_render_gate_emptied_section_falls_to_gap_stub_not_blank():
    """Section B's only claim is UNSUPPORTED -> after the drop the section shows the explicit gap
    statement (fail-safe to the gap stub), never a blank/removed section."""
    result = apply_render_verdict_gate(
        _findings_body(), _verdicts(), _audit_map(), marker_by_claim={},
    )
    body = result.report_text
    assert "## Section B" in body
    assert _GAP_REPLACEMENT in body


# ─────────────────────────────────────────────────────────────────
# The deterministic partition rule (pure).
# ─────────────────────────────────────────────────────────────────
def test_partition_default_drops_all_nonverified():
    verdicts = {
        "v": "VERIFIED",
        "f": "FABRICATED",
        "u": "UNSUPPORTED",
        "r": "UNREACHABLE",
        "p": "PARTIAL",
    }
    drop, label = partition_verdicts_for_render(verdicts)
    assert set(drop) == {"f", "u", "r", "p"}
    assert label == {}


def test_partition_admit_partial_keeps_partial_as_label_drops_the_rest():
    verdicts = {"v": "VERIFIED", "f": "FABRICATED", "p": "PARTIAL"}
    drop, label = partition_verdicts_for_render(verdicts, admit_partial=True)
    # FABRICATED still drops; PARTIAL is admitted (kept + labeled); VERIFIED untouched.
    assert set(drop) == {"f"}
    assert set(label) == {"p"}


def test_partition_kill_switch_routes_everything_to_label():
    verdicts = {"v": "VERIFIED", "f": "FABRICATED", "u": "UNSUPPORTED", "p": "PARTIAL"}
    drop, label = partition_verdicts_for_render(verdicts, drop_nonverified=False)
    assert drop == {}
    assert set(label) == {"f", "u", "p"}


# ─────────────────────────────────────────────────────────────────
# admit_partial gate: PARTIAL kept + caveated, FABRICATED still dropped.
# ─────────────────────────────────────────────────────────────────
def test_render_gate_admit_partial_labels_partial_drops_fabricated():
    body = (
        "# Findings\n"
        "\n"
        "## Section A\n"
        "The moon orbits the earth.[1] Coffee reverses ageing in humans.[2]\n"
        "\n"
        "## Section B\n"
        "Vitamin C may shorten a cold slightly.[3]\n"
    )
    audit = {
        "c_verified": {"sentence": "The moon orbits the earth.", "severity": "S1"},
        "c_fabricated": {"sentence": "Coffee reverses ageing in humans.", "severity": "S1"},
        "c_partial": {"sentence": "Vitamin C may shorten a cold slightly.", "severity": "S1"},
    }
    verdicts = {
        "c_verified": "VERIFIED",
        "c_fabricated": "FABRICATED",
        "c_partial": "PARTIAL",
    }
    result = apply_render_verdict_gate(
        body, verdicts, audit, marker_by_claim={}, admit_partial=True,
    )
    out = result.report_text
    assert result.outcome == "reconciled"
    # FABRICATED dropped, no caveat on it.
    assert "Coffee reverses ageing in humans" not in out
    # VERIFIED survives.
    assert "The moon orbits the earth.[1]" in out
    # PARTIAL is KEPT and caveated (admitted).
    assert "Vitamin C may shorten a cold slightly" in out
    assert _CONFIDENCE_LEAK_MARKER in out
    assert "c_fabricated" in result.dropped_claim_ids
    assert "c_partial" in result.labeled_claim_ids


# ─────────────────────────────────────────────────────────────────
# Kill-switch: drop_nonverified=False reproduces the legacy keep+label.
# ─────────────────────────────────────────────────────────────────
def test_render_gate_kill_switch_reverts_to_keep_and_label():
    result = apply_render_verdict_gate(
        _findings_body(), _verdicts(), _audit_map(), marker_by_claim={}, drop_nonverified=False,
    )
    body = result.report_text
    # Legacy behaviour: the non-VERIFIED claims are KEPT + caveated (not dropped).
    assert "Ravens can count to eight reliably" in body
    assert _CONFIDENCE_LEAK_MARKER in body
    assert result.annotation is not None
    assert set(result.labeled_claim_ids) == {"c_fabricated", "c_unsupported"}
    assert result.dropped_claim_ids == []


# ─────────────────────────────────────────────────────────────────
# Gate defaults.
# ─────────────────────────────────────────────────────────────────
def test_gate_defaults(monkeypatch):
    monkeypatch.delenv("PG_RENDER_VERDICT_GATE", raising=False)
    monkeypatch.delenv("PG_RENDER_VERDICT_GATE_ADMIT_PARTIAL", raising=False)
    assert render_verdict_gate_enabled() is True
    assert render_verdict_gate_admit_partial() is False
    # Explicit off-tokens flip each flag.
    monkeypatch.setenv("PG_RENDER_VERDICT_GATE", "0")
    monkeypatch.setenv("PG_RENDER_VERDICT_GATE_ADMIT_PARTIAL", "1")
    assert render_verdict_gate_enabled() is False
    assert render_verdict_gate_admit_partial() is True
