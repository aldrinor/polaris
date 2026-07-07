"""I-deepfix-001 FIX 4 (#1344, audit c026) — false-gap K-span retention.

UNIT 3 of the deepfix wire+activate wave. The contract-slot emit loop in
``contract_section_runner.run_contract_section`` discloses a "curator-actionable
gap" whenever strict_verify kept ZERO composed sentences for a slot. Audit c026
proved this DELETES real findings: the bound entity (Brynjolfsson [6]) carried a
real, strict_verify-passing span ("5,172 customer-support agents ... by 15%")
that was dropped under a FALSE gap label — coverage loss + §-1.3 filter
violation.

FIX 4 (``PG_CONTRACT_FALSE_GAP_KSPAN``, DEFAULT ON): BEFORE emitting the gap,
check whether the bound entity has ANY strict_verify-passing span; if so, render
a body reconstructed from ONLY those passing sentences — markers stripped and
LEADING page chrome (nav bullets / masthead residue) excluded — instead of the
pre-fix behaviour that dumped the raw full span (chrome and all) verbatim. Emit
the gap ONLY when NO usable verified span survives cleaning.

Faithfulness engine is NOT exercised or relaxed here — each rendered sentence
individually passed the SAME strict_verify path; the fix only reconstructs the
RENDER body from those passing sentences and drops leading page furniture (the
one legit hard-drop per §-1.3). Every check runs fully OFFLINE (the real
``_rewrite_draft_with_spans`` + ``strict_verify`` are deterministic pure-python
for these inputs — no GPU / model / network).

Run single-threaded:
    PYTHONPATH=<worktree> python -m pytest \
        tests/polaris_graph/test_deepfix_fix4_false_gap_kspan.py -q
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from src.polaris_graph.generator.contract_section_runner import (
    _false_gap_kspan_enabled,
    _kspan_fallback_body,
)
from src.polaris_graph.generator.live_deepseek_generator import (
    _rewrite_draft_with_spans,
)
from src.polaris_graph.generator.provenance_generator import strict_verify

_GAP_MARKER = "did not survive strict verification"
_FLAG = "PG_CONTRACT_FALSE_GAP_KSPAN"

# The live audit case (audit c026): a real verified span buried under leading
# page chrome (a "Split View" nav rail + soft-hyphen) — the pre-fix render
# dumped the whole thing; the fix retains ONLY the numeric claim.
_CHROME_SPAN = (
    "- Split View\n-\n\n-\n\n\xadAt one company, generative AI assistance "
    "rolled out to 5,172 customer-support agents raised issues resolved per "
    "hour by 15%."
)


def _run_kspan(span: str, *, ev: str = "E1", marker_num: int = 7) -> str | None:
    """Drive ``_kspan_fallback_body`` with the REAL rewrite + strict_verify path
    over a single-entity pool whose ``direct_quote`` is ``span``."""
    pool = {ev: {"evidence_id": ev, "direct_quote": span, "v30_frame_row": True}}
    return _kspan_fallback_body(
        primary_ev=ev,
        evidence_pool=pool,
        marker_num=marker_num,
        rewrite_fn=_rewrite_draft_with_spans,
        strict_verify_fn=strict_verify,
    )


# ─────────────────────────────────────────────────────────────────────
# (1) leading chrome excluded; the verified numeric sentence renders with [N]
# ─────────────────────────────────────────────────────────────────────
def test_leading_chrome_excluded_numeric_sentence_rendered() -> None:
    """A chrome-led span renders the 5,172 / 15% sentence with its ``[N]``
    citation, NOT a gap marker, and the leading chrome line is ABSENT."""
    body = _run_kspan(_CHROME_SPAN, marker_num=7)

    assert body is not None, "expected a rendered K-span body, not None (gap)"
    assert "5,172" in body and "15%" in body   # real verified claim retained
    assert "[7]" in body                        # cited with the human marker
    assert "Split View" not in body             # leading page chrome excluded
    assert "[#ev:" not in body                  # no raw provenance token leaks
    assert "curator-actionable gap" not in body  # not a false gap


# ─────────────────────────────────────────────────────────────────────
# (2) the flag DEFAULT is ON (fires without any extra env)
# ─────────────────────────────────────────────────────────────────────
def test_flag_default_on_when_env_unset(monkeypatch: pytest.MonkeyPatch) -> None:
    """With ``PG_CONTRACT_FALSE_GAP_KSPAN`` unset the fallback is ENABLED
    (default flipped ON per the I-deepfix-001 wire+activate wave)."""
    monkeypatch.delenv(_FLAG, raising=False)
    assert _false_gap_kspan_enabled() is True


# ─────────────────────────────────────────────────────────────────────
# (3) multi-sentence span: pure-chrome sentence excluded, numeric kept;
#     ALL-chrome span returns None
# ─────────────────────────────────────────────────────────────────────
def test_multi_sentence_chrome_dropped_numeric_kept() -> None:
    """A span with a pure-chrome sentence AND a numeric sentence renders only
    the numeric claim (with ``[N]``) and excludes the chrome."""
    span = (
        "- Nav Menu Home.\n\nRevenue rose to 5,172 units, up by 15% year over "
        "year."
    )
    body = _run_kspan(span, marker_num=3)

    assert body is not None
    assert "5,172" in body and "15%" in body
    assert "[3]" in body
    assert "Nav Menu" not in body


def test_all_chrome_span_returns_none() -> None:
    """A span that is ALL page furniture (each line a short nav bullet, >= the
    50-char verifiable-span floor) leaves no usable prose after cleaning → the
    fallback returns None so the caller renders its (unchanged) gap. Proves the
    fix never fabricates prose where none exists."""
    span = (
        "- Split View\n- Skip Navigation\n- Menu Home\n- Back Top\n"
        "- Print Page Now"
    )
    assert len(span) >= 50  # exercises the chrome logic, not the length shortcut
    assert _run_kspan(span, marker_num=5) is None


# ─────────────────────────────────────────────────────────────────────
# (4) OFF-path byte-identity: the gate is the ONLY switch. When OFF the emit
#     branch never invokes the fallback, so the legacy gap-disclosure render is
#     byte-identical. The shared falsey/truthy vocabulary is honoured (LAW VI
#     parse; Codex iarch007 P1 #3 regression guard).
# ─────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("off_value", ["0", "false", "off", "no", "", "  Off  "])
def test_off_path_gate_disables_fallback(
    monkeypatch: pytest.MonkeyPatch, off_value: str,
) -> None:
    monkeypatch.setenv(_FLAG, off_value)
    assert _false_gap_kspan_enabled() is False


@pytest.mark.parametrize("on_value", ["1", "true", "on", "yes"])
def test_on_values_enable_fallback(
    monkeypatch: pytest.MonkeyPatch, on_value: str,
) -> None:
    monkeypatch.setenv(_FLAG, on_value)
    assert _false_gap_kspan_enabled() is True


def test_helper_returns_none_when_no_usable_span() -> None:
    """A bound entity with NO usable span (empty / too-short shell / absent)
    still gap-discloses: the helper returns None so the caller falls through."""
    pool = {
        "empty_ent": {
            "evidence_id": "empty_ent",
            "direct_quote": "",
            "v30_frame_row": True,
        },
        "shell_ent": {
            "evidence_id": "shell_ent",
            "direct_quote": "[BibTeX] [EndNote]",  # < 50-char shell
            "v30_frame_row": True,
        },
    }
    for eid in ("empty_ent", "shell_ent", "absent_ent"):
        assert _kspan_fallback_body(
            primary_ev=eid,
            evidence_pool=pool,
            marker_num=3,
            rewrite_fn=_rewrite_draft_with_spans,
            strict_verify_fn=strict_verify,
        ) is None


# ─────────────────────────────────────────────────────────────────────
# Render-level proof: the production path (run_contract_section) exercises the
# activated fix end-to-end. ON => the chrome-led span renders (chrome excluded);
# OFF => byte-identical gap disclosure.
# ─────────────────────────────────────────────────────────────────────
@pytest.fixture()
def clinical_template() -> dict:
    with Path("config/scope_templates/clinical.yaml").open(
        "r", encoding="utf-8",
    ) as f:
        return yaml.safe_load(f)


def _stub_fetch_rows(compiled):
    """Every bound entity fetches the chrome-led audit span (real fetched prose,
    >= the verifiable-span floor). The fake LLM below extracts only a terse
    ``N=1879`` field that FLOOR-DROPS at resolution, so every slot composes 0
    substantive sentences — the exact false-gap trigger — while the bound entity
    still carries this strict_verify-passing (chrome-led) span."""
    from src.polaris_graph.retrieval.frame_fetcher import (
        FrameRow, ProvenanceClass,
    )
    return tuple(
        FrameRow(
            entity_id=b.entity_id,
            entity_type=b.entity_type,
            rendering_slot=b.rendering_slot,
            provenance_class=ProvenanceClass.ABSTRACT_ONLY,
            direct_quote=_CHROME_SPAN,
            quote_source="crossref_abstract",
            doi="10.1056/NEJMoa2107519" if "surpass_2" in b.entity_id
                else "10.1/stub",
            pmid=None,
            oa_pdf_url=None,
            url=None,
            title=f"Title {b.entity_id}",
            authors=("Smith J",),
            journal="Lancet",
            year=2021,
            failure_reason=None,
            retrieval_attempts=(),
            retrieval_timings=(),
        )
        for b in compiled.evidence_bindings
    )


async def _fake_llm(prompt: str):
    """Contract-aware fake LLM: extracts only the terse ``N=1879`` field and
    not_extractable for the rest. That terse field FLOOR-DROPS at resolution, so
    EVERY slot composes 0 substantive sentences (the false-gap trigger)."""
    m = re.search(
        r"=== REQUIRED FIELDS ===\n.*?\n((?:  - \w+\n)+)",
        prompt, re.DOTALL,
    )
    if not m:
        return json.dumps({"fields": []}), 500, 200
    required_fields = [
        line.strip("- ").strip()
        for line in m.group(1).strip().splitlines()
        if line.strip().startswith("-")
    ]
    fields = []
    for fname in required_fields:
        if fname == "N":
            fields.append({
                "field_name": "N",
                "status": "extracted",
                "value": "N=1879",
                "source_span": "N=1879",
            })
        else:
            fields.append({
                "field_name": fname,
                "status": "not_extractable",
                "value": None,
                "source_span": None,
            })
    return json.dumps({"fields": fields}), 500, 200


async def _run_efficacy_section(clinical_template: dict):
    from src.polaris_graph.generator.contract_section_runner import (
        ContractSectionPlanExt,
        register_frame_rows_into_evidence_pool,
        run_contract_section,
    )
    from src.polaris_graph.nodes.contract_outline import (
        compose_outline_from_contract,
    )
    from src.polaris_graph.nodes.frame_compiler import compile_frame

    class _SR:
        def __init__(self, **kwargs):
            self.__dict__.update(kwargs)

    cf = compile_frame(
        "tirzepatide evidence", clinical_template,
        "clinical_tirzepatide_t2dm",
    )
    rows = _stub_fetch_rows(cf)
    outline = compose_outline_from_contract(cf, rows)
    section = next(s for s in outline.sections if s.section == "Efficacy")
    plan = ContractSectionPlanExt(
        title=section.section,
        focus=section.focus,
        ev_ids=[eid for s in section.slots for eid in s.entity_ids],
        slots=section.slots,
        frame_rows_by_entity={r.entity_id: r for r in rows},
        contract_entities_by_id=cf.contract.entities_by_id(),
        research_question="tirzepatide evidence",
    )
    evidence_pool: dict[str, dict[str, Any]] = {}
    register_frame_rows_into_evidence_pool(evidence_pool, rows)
    result, _payloads = await run_contract_section(
        plan, evidence_pool,
        llm_call=_fake_llm,
        section_result_cls=_SR,
        strict_verify_fn=strict_verify,
        rewrite_fn=_rewrite_draft_with_spans,
    )
    return result


@pytest.mark.asyncio
async def test_render_on_retains_span_excludes_chrome(
    clinical_template: dict, monkeypatch,
) -> None:
    """ON (default): the bound entity has a strict_verify-passing chrome-led
    span, so the slot renders the retained numeric claim (with its [N]
    citation) — leading chrome excluded — instead of the false gap."""
    monkeypatch.setenv(_FLAG, "1")
    result = await _run_efficacy_section(clinical_template)
    assert "5,172" in result.verified_text and "15%" in result.verified_text, (
        f"ON path must render the retained verified span; "
        f"got: {result.verified_text!r}"
    )
    assert "Split View" not in result.verified_text  # leading chrome excluded
    assert _GAP_MARKER not in result.verified_text    # false gap replaced
    assert re.search(r"\[\d+\]", result.verified_text)  # numbered citation
    assert "[#ev:" not in result.verified_text          # no raw token leak


# ─────────────────────────────────────────────────────────────────────
# I-deepfix-001 (#1369) FIX 2 — substantive bracketed qualifiers survive the
# marker strip. The prior `\[[^\]]+\]` alternative removed ANY bracket, so a
# verified qualifier ([95% CI ...], [p=0.04], [not adjusted], [NCT id]) was
# stripped AFTER strict_verify passed — silently altering a verified claim.
# The narrowed regex strips ONLY [#ev:...] / [entity_id] / [N], so a qualifier
# bracket (spaces / '%' / '=' / uppercase) is preserved. RED before / GREEN now.
# ─────────────────────────────────────────────────────────────────────
def test_substantive_ci_bracket_survives_marker_strip() -> None:
    span = (
        "The hazard ratio for major adverse cardiovascular events was 0.72 "
        "[95% CI 1.2 to 3.4] favoring the treatment group over placebo."
    )
    body = _run_kspan(span, marker_num=7)
    assert body is not None, "expected a rendered K-span body, not None (gap)"
    assert "[95% CI 1.2 to 3.4]" in body, (
        f"substantive CI qualifier must survive the marker strip; got: {body!r}"
    )
    assert "0.72" in body                 # verified point estimate retained
    assert "[7]" in body                  # human citation marker appended
    assert "[#ev:" not in body            # provenance token still stripped


def test_pvalue_and_qualifier_brackets_survive_marker_strip() -> None:
    span = (
        "Treatment reduced mortality by 15 percent relative to control "
        "[p=0.04] in the primary analysis [not adjusted for multiplicity]."
    )
    body = _run_kspan(span, marker_num=4)
    assert body is not None
    assert "[p=0.04]" in body                       # '=' bracket preserved
    assert "[not adjusted for multiplicity]" in body  # spaced bracket preserved
    assert "[4]" in body
    assert "[#ev:" not in body


@pytest.mark.asyncio
async def test_render_off_is_byte_identical_gap_disclosure(
    clinical_template: dict, monkeypatch,
) -> None:
    """OFF: the fallback is never invoked, so the slot renders the pre-fix gap
    disclosure and the span is NOT rendered — byte-identical legacy behaviour."""
    monkeypatch.setenv(_FLAG, "0")
    result = await _run_efficacy_section(clinical_template)
    assert _GAP_MARKER in result.verified_text, (
        f"OFF path must emit the gap disclosure (byte-identical); "
        f"got: {result.verified_text!r}"
    )
    assert "5,172" not in result.verified_text  # span not rendered on OFF path
