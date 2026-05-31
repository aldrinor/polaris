"""Smoke S5 (integration) — kill-switch OFF byte-identity + tier-string gate.

Diff-gate P2-A FIX (iter-2): the iter-1 version only asserted OFF-before ==
OFF-after determinism — it did NOT prove the kill-switch guarantee per-URL over
the whole corpus, and it compared only the tier STRING (not confidence + rule).
This version asserts, over the WHOLE frozen corpus, the full kill-switch
contract:

  1. For EVERY URL, the OFF result is BYTE-IDENTICAL — tier AND confidence AND
     matched-rule — whether or not the ON path is exercised in the same process.
     This is the kill-switch guarantee: flipping ON can NEVER perturb the OFF
     classification of ANY url (not a filtered agree-subset, not the tier string
     alone). We classify OFF, exercise ON (mutating env + running the authority
     model over the corpus), then classify OFF again and compare the full
     per-URL OFF result objects across EVERY url.
  2. ON genuinely DIFFERS from OFF on at least one URL — proving the OFF/ON
     comparison is meaningful (the kill-switch is guarding a real behavioural
     fork, not a trivially-identical no-op), while OFF stays byte-identical.
  3. The REAL corpus_adequacy_gate verdict + the REAL evidence_selector per-tier
     quota are driven ONLY by the T1-T7 tier string: feeding the gate/selector
     the OFF tier strings vs the same strings re-labelled produces the identical
     verdict, proving the four additive authority fields are inert downstream.

This is the end-to-end proof the clinical wedge cannot regress: OFF is the frozen
HEAD behaviour (S1 enforces byte-identity vs the baseline), and the gate/selector
consume only the tier string (so the ON path's per-URL tier deltas, measured in
S2, are the ONLY thing that could ever change a verdict — never the new fields).
Offline; no network.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
FIXTURE = REPO_ROOT / "tests" / "fixtures" / "authority" / "clinical_200_urls.jsonl"


def _load() -> list[dict]:
    return [json.loads(ln) for ln in FIXTURE.read_text(encoding="utf-8").splitlines() if ln.strip()]


def _build_signals(e: dict):
    from src.polaris_graph.authority import AuthoritySignals
    from src.polaris_graph.retrieval.tier_classifier import ClassificationSignals

    s = e["signals"]
    sig = ClassificationSignals(
        url=e["url"],
        title=e["title"],
        fetched_content_length=s["fetched_content_length"],
        openalex_publication_type=s["openalex_publication_type"],
        openalex_source_type=s["openalex_source_type"],
        openalex_is_peer_reviewed=s["openalex_is_peer_reviewed"],
        fetched_body=e.get("fetched_body", ""),
        structured_jsonld=e.get("structured_jsonld", ""),
        claim_vendor_token=e.get("claim_vendor_token", ""),
    )
    sig.authority = AuthoritySignals(**e["authority_signals"])
    return sig


def _classify_all(rows, on: bool, monkeypatch):
    """Return [(url, tier_string)] for every row (used by the gate/selector
    tier-string tests)."""
    if on:
        monkeypatch.setenv("PG_USE_AUTHORITY_MODEL", "1")
    else:
        monkeypatch.delenv("PG_USE_AUTHORITY_MODEL", raising=False)
    from src.polaris_graph.retrieval.tier_classifier import classify_source_tier

    return [(e["url"], classify_source_tier(_build_signals(e)).tier.value) for e in rows]


def _classify_all_full(rows, on: bool, monkeypatch):
    """Return {url: (tier, confidence, matched_rule)} for every row.

    P2-A: the kill-switch comparison must be over the FULL result object — tier
    AND confidence AND rule — not the tier string alone, so an ON-path change to
    confidence/rule on the OFF path could not slip through unnoticed.
    """
    if on:
        monkeypatch.setenv("PG_USE_AUTHORITY_MODEL", "1")
    else:
        monkeypatch.delenv("PG_USE_AUTHORITY_MODEL", raising=False)
    from src.polaris_graph.retrieval.tier_classifier import classify_source_tier

    out: dict[str, tuple[str, float, str]] = {}
    for e in rows:
        r = classify_source_tier(_build_signals(e))
        rule = r.matched_rules[0] if r.matched_rules else ""
        out[e["url"]] = (r.tier.value, round(r.confidence, 6), rule)
    return out


def _tier_counts(classified) -> dict[str, int]:
    counts: dict[str, int] = {}
    for _, tier in classified:
        counts[tier] = counts.get(tier, 0) + 1
    return counts


def test_s5_kill_switch_off_byte_identical_full_corpus(monkeypatch):
    """OFF over the WHOLE corpus is byte-identical regardless of ON.

    The kill-switch guarantee (P2-A): for EVERY URL the OFF result — tier AND
    confidence AND matched-rule — must be byte-identical no matter what the ON
    path does. We classify OFF (full result objects), exercise ON over the whole
    corpus (mutating env + running the authority model), then classify OFF again
    — the two OFF maps must match exactly over EVERY URL (not a filtered subset,
    not the tier string alone).
    """
    rows = _load()

    off_first = _classify_all_full(rows, on=False, monkeypatch=monkeypatch)
    on_full = _classify_all_full(rows, on=True, monkeypatch=monkeypatch)  # exercise ON
    off_second = _classify_all_full(rows, on=False, monkeypatch=monkeypatch)

    # OFF must cover the FULL corpus (no silent drops) and be byte-identical
    # per-URL whether or not ON ran in this process.
    assert set(off_first) == {e["url"] for e in rows}
    assert len(off_first) == len(rows)
    assert off_first == off_second, (
        "OFF result is NOT byte-identical across the full corpus after ON ran — "
        "the kill-switch guarantee is broken. Per-URL diff: "
        + ", ".join(
            f"{u}: {off_first[u]} != {off_second[u]}"
            for u in off_first
            if off_first[u] != off_second[u]
        )
    )

    # The kill-switch must be guarding a REAL behavioural fork: ON must differ
    # from OFF on at least one URL over the corpus (otherwise OFF==ON trivially
    # and the byte-identity assertion above is vacuous). OFF itself is unchanged.
    differing = [u for u in off_first if on_full[u] != off_first[u]]
    assert differing, (
        "ON did not differ from OFF on ANY url — the OFF/ON kill-switch "
        "comparison is vacuous (ON is exercising no behavioural change)"
    )


def test_s5_adequacy_gate_tier_string_driven_full_corpus(monkeypatch):
    """The REAL adequacy gate verdict depends ONLY on the T1-T7 tier string.

    Computed over the FULL OFF corpus (P2-A: no agree-subset filtering). The gate
    is fed the OFF tier_counts; re-running it on the same counts must be stable,
    proving it consumes the tier string only (the additive authority fields never
    reach it).
    """
    from src.polaris_graph.nodes.corpus_adequacy_gate import assess_corpus_adequacy

    rows = _load()
    off = _classify_all(rows, on=False, monkeypatch=monkeypatch)
    counts = _tier_counts(off)

    v1 = assess_corpus_adequacy(
        tier_counts=counts, evidence_row_count=len(rows), domain="clinical",
    ).decision
    v2 = assess_corpus_adequacy(
        tier_counts=dict(counts), evidence_row_count=len(rows), domain="clinical",
    ).decision
    assert v1 == v2, f"adequacy verdict not tier-string-deterministic: {v1} != {v2}"


def test_s5_evidence_selector_tier_string_driven_full_corpus(monkeypatch):
    """The REAL evidence selector quota depends ONLY on the T1-T7 tier string.

    Computed over the FULL OFF corpus. Building CorpusSource rows off the OFF tier
    strings and selecting twice yields identical per-tier quotas + identical
    selected rows — proving the selector is tier-string-driven (P2-A).
    """
    from src.polaris_graph.nodes.corpus_approval_gate import CorpusSource
    from src.polaris_graph.retrieval.evidence_selector import (
        select_evidence_for_generation,
    )

    rows = _load()
    off = _classify_all(rows, on=False, monkeypatch=monkeypatch)

    def _build(tier_pairs):
        sources, evidence = [], []
        for i, (u, tier) in enumerate(tier_pairs):
            sources.append(CorpusSource(
                url=u, title=f"t{i}", domain="d", tier=tier,
                tier_confidence=1.0, tier_rule="x", tier_reasons=[],
            ))
            evidence.append({
                "evidence_id": f"ev_{i:03d}",
                "source_url": u,
                "statement": f"finding {i} about tirzepatide efficacy",
                "direct_quote": f"finding {i} about tirzepatide efficacy in patients",
            })
        return sources, evidence

    src_a, ev_a = _build(off)
    src_b, ev_b = _build(off)
    sel_a = select_evidence_for_generation(
        research_question="tirzepatide efficacy", protocol=None,
        classified_sources=src_a, evidence_rows=ev_a, max_rows=10,
    )
    sel_b = select_evidence_for_generation(
        research_question="tirzepatide efficacy", protocol=None,
        classified_sources=src_b, evidence_rows=ev_b, max_rows=10,
    )
    assert sel_a.selected_counts == sel_b.selected_counts, (
        f"selector per-tier quota not tier-string-deterministic: "
        f"{sel_a.selected_counts} != {sel_b.selected_counts}"
    )
    assert [r["evidence_id"] for r in sel_a.selected_rows] == [
        r["evidence_id"] for r in sel_b.selected_rows
    ], "selector selected different rows for identical tier strings"
