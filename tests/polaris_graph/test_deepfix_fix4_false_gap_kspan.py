"""I-deepfix-001 FIX 4 (#1344, audit c026) — false-gap K-span fallback.

The contract-slot emit loop in ``contract_section_runner.run_contract_section``
discloses a "curator-actionable gap" whenever strict_verify kept ZERO composed
sentences for a slot. Audit c026 proved this DELETES real findings: the bound
entity carried a real, strict_verify-passing span (Brynjolfsson [6]:
"+15% worker productivity"; "5,172 support agents") that was dropped under a
FALSE gap label — coverage loss + honesty defect + §-1.3 filter violation.

FIX 4 (env-gated ``PG_CONTRACT_FALSE_GAP_KSPAN``): BEFORE emitting the gap,
check whether the bound entity has ANY strict_verify-passing span in
evidence_pool; if so, render that span VERBATIM (K-span fallback, same
grounded-by-construction idiom as ``abstractive_writer``) with its citation,
RETAINING the finding. Emit the gap ONLY when NO usable verified span exists.

Faithfulness engine is NOT exercised or relaxed here — the emitted span is
re-verified via the SAME strict_verify path; a verbatim span passes by
construction. These tests drive the PRODUCTION path (``run_contract_section``)
in the exact 0-verified-sentences scenario the fix targets, plus the helper's
"genuinely no usable span" branch.

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

_GAP_MARKER = "did not survive strict verification"
_SPAN_TEXT = "SURPASS-2 enrolled N=1879 patients"
_FLAG = "PG_CONTRACT_FALSE_GAP_KSPAN"


@pytest.fixture()
def clinical_template() -> dict:
    with Path("config/scope_templates/clinical.yaml").open(
        "r", encoding="utf-8",
    ) as f:
        return yaml.safe_load(f)


def _stub_fetch_rows(compiled):
    """Every bound entity fetches a RICH abstract span (real fetched prose,
    >= _MIN_VERIFIABLE_SPAN_CHARS). The fake LLM below extracts only a terse
    ``N=1879`` field that FLOOR-DROPS at resolution, so every slot composes 0
    substantive sentences — the exact false-gap trigger — while the bound
    entity still carries this strict_verify-passing span."""
    from src.polaris_graph.retrieval.frame_fetcher import (
        FrameRow, ProvenanceClass,
    )
    return tuple(
        FrameRow(
            entity_id=b.entity_id,
            entity_type=b.entity_type,
            rendering_slot=b.rendering_slot,
            provenance_class=ProvenanceClass.ABSTRACT_ONLY,
            direct_quote=(
                "SURPASS-2 enrolled N=1879 patients. Primary "
                "endpoint: change in HbA1c at 40 weeks. ETD "
                "-0.47% (95% CI -0.59 to -0.35)."
            ),
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
    not_extractable for the rest. That terse field FLOOR-DROPS at resolution,
    so EVERY slot composes 0 substantive sentences (the false-gap trigger).
    Narrative / non-field prompts return an empty field list."""
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
    from src.polaris_graph.generator.live_deepseek_generator import (
        _rewrite_draft_with_spans,
    )
    from src.polaris_graph.generator.provenance_generator import strict_verify
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
async def test_flag_off_default_discloses_false_gap(
    clinical_template: dict, monkeypatch,
) -> None:
    """OFF (default): the emit loop is byte-identical to pre-fix — every slot
    whose compose yielded 0 verified sentences renders the gap disclosure and
    the real span is NOT rendered. This is the RED baseline the fix corrects."""
    monkeypatch.delenv(_FLAG, raising=False)
    result = await _run_efficacy_section(clinical_template)
    assert _GAP_MARKER in result.verified_text, (
        "OFF path must still emit the gap disclosure (byte-identical); "
        f"got: {result.verified_text!r}"
    )
    assert _SPAN_TEXT not in result.verified_text, (
        "OFF path must NOT render the verbatim span (byte-identical pre-fix)"
    )


@pytest.mark.asyncio
async def test_flag_on_renders_verbatim_span_not_false_gap(
    clinical_template: dict, monkeypatch,
) -> None:
    """ON: the bound entity has a strict_verify-passing span, so the slot
    renders that span VERBATIM (with its [N] citation) instead of the false
    gap. GREEN — the finding is RETAINED, not deleted."""
    monkeypatch.setenv(_FLAG, "1")
    result = await _run_efficacy_section(clinical_template)
    assert _SPAN_TEXT in result.verified_text, (
        "ON path must render the verbatim strict_verify-passing span; "
        f"got: {result.verified_text!r}"
    )
    assert _GAP_MARKER not in result.verified_text, (
        "ON path must REPLACE the false gap with the retained span "
        "(no slot in this fixture has an unusable span)"
    )
    # The rendered K-span carries a numbered [N] citation, never a raw token.
    assert re.search(r"\[\d+\]", result.verified_text)
    assert "[#ev:" not in result.verified_text


def test_helper_returns_none_when_no_usable_span() -> None:
    """A slot whose bound entity has NO usable span (empty / too-short quote)
    still gap-discloses: the helper returns None so the caller falls through
    to the gap. Proves the fix does NOT fabricate a span where none exists."""
    from src.polaris_graph.generator.contract_section_runner import (
        _kspan_fallback_body,
    )
    from src.polaris_graph.generator.live_deepseek_generator import (
        _rewrite_draft_with_spans,
    )
    from src.polaris_graph.generator.provenance_generator import strict_verify

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


def test_helper_returns_verbatim_span_when_usable() -> None:
    """The positive helper case at unit granularity: a real fetched span with
    a citable claim returns ``"{span}[N]"`` verbatim."""
    from src.polaris_graph.generator.contract_section_runner import (
        _kspan_fallback_body,
    )
    from src.polaris_graph.generator.live_deepseek_generator import (
        _rewrite_draft_with_spans,
    )
    from src.polaris_graph.generator.provenance_generator import strict_verify

    span = (
        "SURPASS-2 enrolled N=1879 patients. Primary endpoint: change in "
        "HbA1c at 40 weeks. ETD -0.47% (95% CI -0.59 to -0.35)."
    )
    pool = {
        "surpass_2_primary": {
            "evidence_id": "surpass_2_primary",
            "direct_quote": span,
            "v30_frame_row": True,
        },
    }
    body = _kspan_fallback_body(
        primary_ev="surpass_2_primary",
        evidence_pool=pool,
        marker_num=6,
        rewrite_fn=_rewrite_draft_with_spans,
        strict_verify_fn=strict_verify,
    )
    assert body is not None
    assert body.startswith(span)
    assert body.endswith("[6]")


def test_flag_default_off_and_falsey_vocabulary() -> None:
    """OFF-byte-identical default + the shared falsey vocabulary (Codex
    iarch007 P1 #3 regression guard)."""
    import importlib
    import os
    from src.polaris_graph.generator import contract_section_runner as csr

    saved = os.environ.get(_FLAG)
    try:
        os.environ.pop(_FLAG, None)
        importlib.reload(csr)
        assert csr._false_gap_kspan_enabled() is False
        for off in ("0", "false", "off", "no", ""):
            os.environ[_FLAG] = off
            assert csr._false_gap_kspan_enabled() is False, off
        for on in ("1", "true", "on", "yes"):
            os.environ[_FLAG] = on
            assert csr._false_gap_kspan_enabled() is True, on
    finally:
        if saved is None:
            os.environ.pop(_FLAG, None)
        else:
            os.environ[_FLAG] = saved
