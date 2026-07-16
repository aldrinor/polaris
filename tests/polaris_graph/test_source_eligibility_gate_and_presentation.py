"""feat/intake-contract — LANE A (source-eligibility gate) + LANE B (presentation depth).

Both lanes are ADDITIVE, each behind its OWN new default-OFF env flag.

LANE A — SOURCE-ELIGIBILITY GATE (``PG_CONTRACT_ENFORCE_SOURCE_RULES``):
    filters the per-section WRITER CITEABLE menu (``ev_subset``) BEFORE the writer runs.
    A HARD, exclusively-scoped source rule (allow_only/forbid at strength "hard") REMOVES
    non-qualifying rows from the WRITER PROMPT ONLY; a soft/prefer/include rule DOWN-RANKS
    (stable-sorts non-qualifying rows to the tail — still citable). RECALL VALVE: if
    hard-blocking would drop the menu below ``PG_CONTRACT_SOURCE_GATE_MIN_MENU`` it SOFTENS
    to demote+disclose so the section is never starved.

    FIREWALL proven here:
      * MENU-ONLY  -> the gate never mutates its input list and its ONLY data input is
        ``ev_subset`` (it is never handed ``evidence_pool``), so the verification pool
        cannot be touched;
      * PRE-WRITE  -> the gate runs strictly before the writer; the writer is offered only
        the gated menu and can never cite a blocked row (no orphaned-citation path);
      * POOL UNCHANGED -> after the gate runs inside ``_run_section``, ``evidence_pool`` AND
        ``section.ev_ids`` (bibliography + credibility disclosure) still carry every blocked
        row, so strict_verify keeps the blocked source fully available to GROUND prose.

LANE B — PRESENTATION DEPTH (``PG_CONTRACT_ENFORCE_PRESENTATION``):
    maps the contract's tone/audience/length/format/output_language ContractFields into
    DEEPER, imperative, reader-facing STYLE directives. STYLE-ONLY and downstream of
    strict_verify: it adds NO evidence and NO citation.

Fully offline/deterministic: the source classifier is monkeypatched to a fake, contracts are
hand-built, no generator run, no network, no LLM, no compose. NO faithfulness test is added.
"""
from __future__ import annotations

import asyncio
import inspect

import pytest

import src.polaris_graph.generator.multi_section_generator as msg
from src.polaris_graph.generator.multi_section_generator import (
    SectionPlan,
    _apply_source_eligibility_gate,
    _contract_enforce_presentation_enabled,
    _contract_presentation_guidance_deep,
    _source_eligibility_gate_enabled,
    _run_section,
    _source_gate_min_menu,
)
from src.polaris_graph.intake.contract_schema import ContractField, IntakeContract, SourceRule

_SR_FLAG = "PG_CONTRACT_ENFORCE_SOURCE_RULES"
_FLOOR_FLAG = "PG_CONTRACT_SOURCE_GATE_MIN_MENU"
_PRES_FLAG = "PG_CONTRACT_ENFORCE_PRESENTATION"


# ─────────────────────────────────────────────────────────────────────────────
# fixtures / fakes
# ─────────────────────────────────────────────────────────────────────────────
def _row(rid: str, kind: str) -> dict:
    """A minimal evidence row. ``kind`` drives the fake classifier."""
    return {"id": rid, "kind": kind, "statement": f"stmt {rid}", "direct_quote": f"quote {rid}"}


def _fake_classifier(monkeypatch):
    """Patch classify_source_facets so a row's facets are deterministic from row['kind']:
    'journal' -> {'peer_reviewed_journal'}, 'news' -> {'news'}, 'unknown' -> set() (unresolved)."""
    def fake(source, ontology=None):
        kind = (source.get("kind") if isinstance(source, dict) else "") or ""
        if kind == "journal":
            return ({"peer_reviewed_journal"}, "journal_classifier")
        if kind == "news":
            return ({"news"}, "host:news")
        return (set(), "unresolved")

    monkeypatch.setattr(
        "src.polaris_graph.retrieval.scope_facet_classifier.classify_source_facets", fake
    )


def _contract_with_rules(*rules: SourceRule) -> IntakeContract:
    c = IntakeContract()
    c.source_rules = list(rules)
    return c


_HARD_JOURNAL_ONLY = SourceRule(
    facet_id="peer_reviewed_journal", operator="allow_only", strength="hard",
    verbatim_span="only journal articles", origin="user_explicit",
)
_SOFT_PREFER_JOURNAL = SourceRule(
    facet_id="peer_reviewed_journal", operator="prefer", strength="soft",
    verbatim_span="focus on journals", origin="user_explicit",
)


# ─────────────────────────────────────────────────────────────────────────────
# LANE A — flag defaults OFF
# ─────────────────────────────────────────────────────────────────────────────
def test_source_rules_flag_defaults_off(monkeypatch):
    monkeypatch.delenv(_SR_FLAG, raising=False)
    assert _source_eligibility_gate_enabled() is False


def test_source_gate_min_menu_default_is_3(monkeypatch):
    monkeypatch.delenv(_FLOOR_FLAG, raising=False)
    assert _source_gate_min_menu() == 3


# ─────────────────────────────────────────────────────────────────────────────
# LANE A — flag OFF => byte-identical (same object)
# ─────────────────────────────────────────────────────────────────────────────
def test_gate_flag_off_returns_same_object(monkeypatch):
    monkeypatch.delenv(_SR_FLAG, raising=False)
    ev = [_row("ev1", "journal"), _row("ev2", "news")]
    out = _apply_source_eligibility_gate(ev, _contract_with_rules(_HARD_JOURNAL_ONLY), {})
    assert out is ev  # identical object => byte-identical menu


def test_gate_none_contract_returns_same_object(monkeypatch):
    monkeypatch.setenv(_SR_FLAG, "1")
    ev = [_row("ev1", "journal")]
    assert _apply_source_eligibility_gate(ev, None, {}) is ev


def test_gate_empty_rules_returns_same_object(monkeypatch):
    monkeypatch.setenv(_SR_FLAG, "1")
    ev = [_row("ev1", "journal")]
    assert _apply_source_eligibility_gate(ev, _contract_with_rules(), {}) is ev


# ─────────────────────────────────────────────────────────────────────────────
# LANE A — HARD rule filters the citeable menu (and never mutates the input)
# ─────────────────────────────────────────────────────────────────────────────
def test_hard_allow_only_removes_nonqualifying_from_menu(monkeypatch):
    _fake_classifier(monkeypatch)
    monkeypatch.setenv(_SR_FLAG, "1")
    # 4 journal (qualify) + 1 news (does NOT qualify). Floor default 3 => kept 4 >= 3 => hard block bites.
    ev = [_row(f"j{i}", "journal") for i in range(4)] + [_row("n1", "news")]
    out = _apply_source_eligibility_gate(ev, _contract_with_rules(_HARD_JOURNAL_ONLY), {})
    ids = [r["id"] for r in out]
    assert "n1" not in ids  # the non-journal row is HARD-removed from the writer menu
    assert ids == ["j0", "j1", "j2", "j3"]
    # FIREWALL: the INPUT list is never mutated (menu-only, returns a new list).
    assert [r["id"] for r in ev] == ["j0", "j1", "j2", "j3", "n1"]


def test_hard_forbid_removes_carrying_rows(monkeypatch):
    _fake_classifier(monkeypatch)
    monkeypatch.setenv(_SR_FLAG, "1")
    forbid_news = SourceRule(
        facet_id="news", operator="forbid", strength="hard", verbatim_span="do not use news",
    )
    ev = [_row(f"j{i}", "journal") for i in range(3)] + [_row("n1", "news")]
    out = _apply_source_eligibility_gate(ev, _contract_with_rules(forbid_news), {})
    assert [r["id"] for r in out] == ["j0", "j1", "j2"]


# ─────────────────────────────────────────────────────────────────────────────
# LANE A — SOFT rule only REORDERS (no removal)
# ─────────────────────────────────────────────────────────────────────────────
def test_soft_prefer_only_reorders_never_removes(monkeypatch):
    _fake_classifier(monkeypatch)
    monkeypatch.setenv(_SR_FLAG, "1")
    ev = [_row("n1", "news"), _row("j1", "journal"), _row("n2", "news"), _row("j2", "journal")]
    out = _apply_source_eligibility_gate(ev, _contract_with_rules(_SOFT_PREFER_JOURNAL), {})
    ids = [r["id"] for r in out]
    # No row dropped; qualifying (journal) rows stable-sorted to the HEAD, non-qualifying to the tail.
    assert sorted(ids) == sorted(["n1", "j1", "n2", "j2"])
    assert ids == ["j1", "j2", "n1", "n2"]


# ─────────────────────────────────────────────────────────────────────────────
# LANE A — RECALL VALVE softens hard-removal when too few qualify
# ─────────────────────────────────────────────────────────────────────────────
def test_recall_valve_softens_below_floor(monkeypatch):
    _fake_classifier(monkeypatch)
    monkeypatch.setenv(_SR_FLAG, "1")
    monkeypatch.setenv(_FLOOR_FLAG, "3")
    # Only 1 journal qualifies under HARD allow_only => kept(1) < floor(3) => SOFTEN: keep all,
    # demote the 3 non-journal rows to the tail instead of starving the section.
    ev = [_row("n1", "news"), _row("j1", "journal"), _row("n2", "news"), _row("n3", "news")]
    out = _apply_source_eligibility_gate(ev, _contract_with_rules(_HARD_JOURNAL_ONLY), {})
    ids = [r["id"] for r in out]
    assert len(out) == 4  # nothing removed — valve softened to demote+disclose
    assert ids[0] == "j1"  # the qualifying row leads
    assert set(ids[1:]) == {"n1", "n2", "n3"}  # non-qualifying demoted to the tail, still citable


def test_recall_valve_disabled_by_zero_floor_still_hard_blocks(monkeypatch):
    _fake_classifier(monkeypatch)
    monkeypatch.setenv(_SR_FLAG, "1")
    monkeypatch.setenv(_FLOOR_FLAG, "0")
    ev = [_row("n1", "news"), _row("j1", "journal"), _row("n2", "news")]
    out = _apply_source_eligibility_gate(ev, _contract_with_rules(_HARD_JOURNAL_ONLY), {})
    assert [r["id"] for r in out] == ["j1"]  # floor 0 => valve never trips => hard block applies


# ─────────────────────────────────────────────────────────────────────────────
# LANE A — FAIL-OPEN: an unresolved row is demoted, never hard-dropped
# ─────────────────────────────────────────────────────────────────────────────
def test_unresolved_row_is_demoted_not_dropped_under_hard_rule(monkeypatch):
    _fake_classifier(monkeypatch)
    monkeypatch.setenv(_SR_FLAG, "1")
    monkeypatch.setenv(_FLOOR_FLAG, "0")  # keep the valve out of the way to isolate fail-open
    # 3 journals qualify; 'u1' is unresolved (empty facet set) => cannot be PROVEN ineligible =>
    # SOFT-demote to the tail, NEVER hard-dropped.
    ev = [_row("j1", "journal"), _row("u1", "unknown"), _row("j2", "journal"), _row("j3", "journal")]
    out = _apply_source_eligibility_gate(ev, _contract_with_rules(_HARD_JOURNAL_ONLY), {})
    ids = [r["id"] for r in out]
    assert "u1" in ids  # unresolved never starved
    assert ids[-1] == "u1"  # but demoted to the tail
    assert ids[:3] == ["j1", "j2", "j3"]


# ─────────────────────────────────────────────────────────────────────────────
# LANE A — FIREWALL: the gate's only data input is ev_subset (never evidence_pool)
# ─────────────────────────────────────────────────────────────────────────────
def test_gate_signature_never_receives_evidence_pool():
    params = list(inspect.signature(_apply_source_eligibility_gate).parameters)
    # ev_subset + contract + ontology only — the verification pool is structurally unreachable.
    assert params[:3] == ["ev_subset", "contract", "ontology"]
    assert "evidence_pool" not in params


# ─────────────────────────────────────────────────────────────────────────────
# LANE A — PRE-WRITE INTEGRATION: the writer is offered only the gated menu, and
# evidence_pool + section.ev_ids still carry the blocked row for verification.
# ─────────────────────────────────────────────────────────────────────────────
class _StopBeforeWriter(Exception):
    pass


def test_gate_is_pre_write_and_pool_unchanged(monkeypatch):
    _fake_classifier(monkeypatch)
    monkeypatch.setenv(_SR_FLAG, "1")

    evidence_pool = {
        "j0": _row("j0", "journal"), "j1": _row("j1", "journal"),
        "j2": _row("j2", "journal"), "j3": _row("j3", "journal"),
        "n1": _row("n1", "news"),
    }
    ev_ids = ["j0", "j1", "j2", "j3", "n1"]
    section = SectionPlan(title="Findings", focus="f", ev_ids=list(ev_ids))

    captured = {}

    def _capture_menu(ev_subset, *, section_title="", total_assigned=0):
        # This is the FIRST post-gate touch of the menu — capture what the gate produced,
        # then abort BEFORE any _call_section / writer / strict_verify call.
        captured["menu_ids"] = [r["id"] for r in ev_subset]
        raise _StopBeforeWriter

    monkeypatch.setattr(msg, "_apply_writer_menu_cap", _capture_menu)

    with pytest.raises(_StopBeforeWriter):
        asyncio.run(_run_section(
            section, evidence_pool,
            model="fake-model", temperature=0.0,
            max_tokens_per_section=100, min_kept_fraction=0.0,
            source_gate_contract=_contract_with_rules(_HARD_JOURNAL_ONLY),
            source_gate_ontology={},
        ))

    # PRE-WRITE: the writer menu offered to the (aborted) writer excludes the blocked news row.
    assert "n1" not in captured["menu_ids"]
    assert captured["menu_ids"] == ["j0", "j1", "j2", "j3"]
    # FIREWALL: the verification pool is UNCHANGED — the blocked row is still fully present so
    # strict_verify can ground any sentence against it.
    assert "n1" in evidence_pool
    assert set(evidence_pool) == set(ev_ids)
    # section.ev_ids (bibliography + credibility disclosure) still lists the blocked row.
    assert section.ev_ids == ev_ids


def test_run_section_flag_off_offers_full_menu(monkeypatch):
    _fake_classifier(monkeypatch)
    monkeypatch.delenv(_SR_FLAG, raising=False)  # LANE A OFF

    evidence_pool = {"j0": _row("j0", "journal"), "n1": _row("n1", "news")}
    section = SectionPlan(title="Findings", focus="f", ev_ids=["j0", "n1"])
    captured = {}

    def _capture_menu(ev_subset, *, section_title="", total_assigned=0):
        captured["menu_ids"] = [r["id"] for r in ev_subset]
        raise _StopBeforeWriter

    monkeypatch.setattr(msg, "_apply_writer_menu_cap", _capture_menu)
    with pytest.raises(_StopBeforeWriter):
        asyncio.run(_run_section(
            section, evidence_pool,
            model="fake-model", temperature=0.0,
            max_tokens_per_section=100, min_kept_fraction=0.0,
            source_gate_contract=_contract_with_rules(_HARD_JOURNAL_ONLY),
            source_gate_ontology={},
        ))
    # Flag OFF => the gate is a no-op => the writer is offered the FULL unfiltered menu.
    assert captured["menu_ids"] == ["j0", "n1"]


# ─────────────────────────────────────────────────────────────────────────────
# LANE B — flag defaults OFF
# ─────────────────────────────────────────────────────────────────────────────
def test_presentation_flag_defaults_off(monkeypatch):
    monkeypatch.delenv(_PRES_FLAG, raising=False)
    assert _contract_enforce_presentation_enabled() is False


# ─────────────────────────────────────────────────────────────────────────────
# LANE B — deep renderer returns "" on None / empty (byte-identical no-op)
# ─────────────────────────────────────────────────────────────────────────────
def test_deep_presentation_empty_on_none():
    assert _contract_presentation_guidance_deep(None) == ""


def test_deep_presentation_empty_on_unset_contract():
    assert _contract_presentation_guidance_deep(IntakeContract()) == ""


# ─────────────────────────────────────────────────────────────────────────────
# LANE B — deep renderer emits imperative reader-facing directives
# ─────────────────────────────────────────────────────────────────────────────
def _set(field_value: str) -> ContractField:
    return ContractField(value=field_value, origin="user_explicit", strength="soft")


def test_deep_presentation_emits_imperative_directives():
    c = IntakeContract()
    c.tone = _set("formal")
    c.audience = _set("policymakers")
    c.length = _set("brief")
    c.format = _set("narrative")
    c.output_language = _set("French")
    out = _contract_presentation_guidance_deep(c)
    assert out  # non-empty
    assert "NON-BINDING" in out
    # imperative, reader-facing phrasing (not a bare "- Tone: formal" label)
    assert "formal register" in out
    assert "reader is policymakers" in out
    assert "do NOT pad" in out  # length stays soft
    assert "narrative presentation" in out
    # output_language scoped to NARRATION and forbids translating quoted spans/citations
    assert "NARRATION in French" in out
    assert "do NOT translate" in out


def test_deep_presentation_is_style_only_no_evidence_or_citation():
    c = IntakeContract()
    c.tone = _set("technical")
    out = _contract_presentation_guidance_deep(c)
    # style-only: it must add no citation/evidence token and must reaffirm nothing unsupported is added
    assert "[CITE:" not in out and "[#ev:" not in out
    assert "NEVER add a claim, number, or citation" in out


def test_deep_renderer_differs_from_shallow():
    c = IntakeContract()
    c.tone = _set("formal")
    shallow = msg._contract_presentation_guidance(c)
    deep = _contract_presentation_guidance_deep(c)
    assert shallow != deep
    assert "- Tone: formal" in shallow  # shallow is a bare label
    assert "formal register" in deep    # deep is an imperative directive
