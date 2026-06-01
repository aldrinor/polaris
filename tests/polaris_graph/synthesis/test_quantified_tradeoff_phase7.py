"""I-meta-005 Phase 7 (#991) smoke — quantified trade-off (gap 9, PAL rewire).

SPEND-FREE: ``build_quantified_spec`` takes a FAKE ``spec_llm`` (no LLM); the
deterministic ``render_script`` runs the FIXED Python via the existing sandbox
(``execute_analysis_script``) with NO network/live client. Regime C verification
is pure. Plain assertions, no unittest.mock.

P7-1 OFF byte-identity              P7-11 formula AST + dependency reject
P7-2 sandbox unchanged              P7-12 calc-token strip (no leak)
P7-3 deterministic Execute          P7-13 sourced-conflict telemetry
P7-4 Regime C PASS                  P7-14 audit replay (round-trip + stable hash)
P7-5 Regime C FAIL (number!=disp)   P7-15 modeled base+sweep+break-even
P7-6 sourced literal not in evid.   P7-16 scaled-literal recovery
P7-7 modeled unlabeled -> DROP      P7-17 exact-one-match duplicate reject
P7-8 modeled labeled -> VERIFIED    P7-18 cancellation/zero-effect reject
P7-9 input neither -> None          P7-19 run-scoped stale model reject
P7-10 sentence-level multi-number   P7-20 token adjacency
"""
from __future__ import annotations

import asyncio
import json
import os
import tempfile

from src.polaris_graph.generator import provenance_generator as pg
from src.polaris_graph.generator.quantified_analysis import (
    QuantifiedResult,
    bind_calc_tokens,
    detect_sourced_conflicts,
    execute_quantified_model,
    run_quantified_section,
)
from src.polaris_graph.tools.evidence_extractor import extract_numbers_from_evidence
from src.polaris_graph.synthesis.tradeoff_modeler import (
    _canonical_display,
    _locate_unique_literal,
    build_quantified_spec,
    render_script,
)
from src.polaris_graph.tools.code_executor import validate_script


# ── shared fixtures ──────────────────────────────────────────────────────────
def _evidence_rows():
    return {
        "ev_017": {
            "direct_quote": "The program cost was $1.548 billion in fiscal 2024.",
            "source_url": "https://example.org/a", "tier": "T1",
        },
        "ev_021": {
            "direct_quote": "Annual maintenance is $120 million per year.",
            "source_url": "https://example.org/b", "tier": "T1",
        },
    }


def _dp(ev_id, label, context, value, unit="USD"):
    return {
        "data_type": "cost", "label": label, "context": context,
        "value": str(value), "unit": unit, "year": "2024",
        "evidence_id": ev_id, "source_url": "", "source_title": "",
    }


_CAPEX = _dp("ev_017", "program cost",
             "program cost was $1.548 billion in fiscal", 1548000000.0)
_OPEX = _dp("ev_021", "annual maintenance",
            "Annual maintenance is $120 million per year", 120000000.0)


def _tco_raw_spec(_q, _s):
    return {
        "model_id": "tco", "title": "Total cost of ownership",
        "inputs": [
            {"name": "capex", "datapoint_ref": {
                "ev_id": "ev_017", "label": "program cost",
                "context": "program cost was $1.548 billion in fiscal",
                "value": "1548000000.0", "unit": "USD"}},
            {"name": "opex", "datapoint_ref": {
                "ev_id": "ev_021", "label": "annual maintenance",
                "context": "Annual maintenance is $120 million per year",
                "value": "120000000.0", "unit": "USD"}},
            {"name": "years", "base": 5.0, "unit": "years",
             "sweep": [1.0, 10.0, 1.0], "modeled": True},
        ],
        "outputs": [{"name": "tco", "unit": "USD", "display_kind": "currency",
                     "formula": "capex + opex * years"}],
        "sensitivity": [{"input": "years", "output": "tco"}],
    }


def _build_tco():
    return build_quantified_spec(
        "q", [_CAPEX, _OPEX], _evidence_rows(), spec_llm=_tco_raw_spec,
    )


def _exec(spec, run_dir=None):
    return asyncio.run(
        execute_quantified_model(spec, _evidence_rows(), run_dir=run_dir)
    )


# ── P7-3 deterministic Execute ───────────────────────────────────────────────
def test_p7_3_deterministic_execute_no_live_client():
    spec = _build_tco()
    assert spec is not None
    result = _exec(spec)
    assert result is not None
    # capex + opex*years = 1.548e9 + 1.2e8*5 = 2.148e9
    assert abs(result.fields["tco"]["value"] - 2_148_000_000.0) < 1e-3
    assert result.fields["tco"]["display_value"] == "$2,148,000,000.00"


# ── P7-4 Regime C PASS ───────────────────────────────────────────────────────
def test_p7_4_regime_c_pass():
    spec = _build_tco()
    result = _exec(spec)
    prose = ("Total cost of ownership is {{calc:tco}} over a five-year horizon "
             "(modeled assumption).")
    bound = bind_calc_tokens(prose, result)
    assert "[#calc:tco:" in bound and "$2,148,000,000.00" in bound
    report = pg.strict_verify(
        bound, _evidence_rows(), quantified_models={result.key(): result},
    )
    assert report.total_kept == 1 and report.total_dropped == 0
    kept = report.kept_sentences[0]
    # the verified sentence cites the SOURCE inputs (ev_017, ev_021)
    cited = {t.evidence_id for t in kept.tokens}
    assert cited == {"ev_017", "ev_021"}


# ── P7-5 Regime C FAIL on number != display_value ────────────────────────────
def test_p7_5_regime_c_fail_wrong_number():
    spec = _build_tco()
    result = _exec(spec)
    token = result.calc_token("tco")
    bad = (f"Total cost of ownership is $999,999,999.00{token} over five years "
           f"(modeled assumption).")
    report = pg.strict_verify(
        bad, _evidence_rows(), quantified_models={result.key(): result},
    )
    assert report.total_kept == 0 and report.total_dropped == 1
    assert any("calc_number_mismatch" in r
               for r in report.dropped_sentences[0].failure_reasons)


# ── P7-6 sourced literal NOT numeric-verbatim in evidence -> None ────────────
def test_p7_6_sourced_literal_not_in_evidence():
    # datapoint whose value (7.77e9) passes exact-one-match in sourced_numbers
    # but is NOT present in ev_017's direct_quote ("$1.548 billion") nor context.
    tampered = _dp("ev_017", "program cost",
                   "program cost figure noted in the appendix", 7_770_000_000.0)

    def raw(_q, _s):
        spec = _tco_raw_spec(_q, _s)
        spec["inputs"][0]["datapoint_ref"] = {
            "ev_id": "ev_017", "label": "program cost",
            "context": "program cost figure noted in the appendix",
            "value": "7770000000.0", "unit": "USD"}
        return spec

    spec = build_quantified_spec("q", [tampered, _OPEX], _evidence_rows(),
                                 spec_llm=raw)
    assert spec is None


# ── P7-7 / P7-8 modeled-assumption label gate ────────────────────────────────
def test_p7_7_modeled_unlabeled_dropped():
    spec = _build_tco()
    result = _exec(spec)
    token = result.calc_token("tco")
    # tco's formula references the modeled input "years" -> label REQUIRED
    no_label = f"Total cost of ownership is $2,148,000,000.00{token} overall."
    report = pg.strict_verify(
        no_label, _evidence_rows(), quantified_models={result.key(): result},
    )
    assert report.total_kept == 0
    assert any("calc_modeled_assumption_unlabeled" in r
               for r in report.dropped_sentences[0].failure_reasons)


def test_p7_8_modeled_labeled_verified():
    spec = _build_tco()
    result = _exec(spec)
    token = result.calc_token("tco")
    ok = (f"Total cost of ownership is $2,148,000,000.00{token} over five years "
          f"(modeled assumption).")
    report = pg.strict_verify(
        ok, _evidence_rows(), quantified_models={result.key(): result},
    )
    assert report.total_kept == 1


# ── P7-9 input neither sourced nor modeled -> None ───────────────────────────
def test_p7_9_input_neither_sourced_nor_modeled():
    def raw(_q, _s):
        spec = _tco_raw_spec(_q, _s)
        spec["inputs"].append({"name": "ghost", "unit": "USD"})  # no ref, no modeled
        return spec

    assert build_quantified_spec("q", [_CAPEX, _OPEX], _evidence_rows(),
                                 spec_llm=raw) is None


# ── P7-10 sentence-level multi-number ────────────────────────────────────────
def test_p7_10_sentence_level_one_wrong_drops_only_its_sentence():
    spec = _build_tco()
    result = _exec(spec)
    token = result.calc_token("tco")
    good = (f"Total cost of ownership is $2,148,000,000.00{token} over five years "
            f"(modeled assumption).")
    bad = (f"A revised figure is $7.00{token} over five years "
           f"(modeled assumption).")
    report = pg.strict_verify(
        good + " " + bad, _evidence_rows(),
        quantified_models={result.key(): result},
    )
    assert report.total_kept == 1 and report.total_dropped == 1


# ── P7-11 formula AST + dependency reject ────────────────────────────────────
def test_p7_11_formula_ast_reject_disallowed_call():
    def raw(_q, _s):
        spec = _tco_raw_spec(_q, _s)
        spec["outputs"][0]["formula"] = "capex + __import__('os').getpid()"
        return spec
    assert build_quantified_spec("q", [_CAPEX, _OPEX], _evidence_rows(),
                                 spec_llm=raw) is None


def test_p7_11_dependency_unused_input_reject():
    # declare an extra sourced input that no output formula references -> the
    # numeric perturb gate rejects it (does not materially affect any output).
    def raw(_q, _s):
        spec = _tco_raw_spec(_q, _s)
        spec["inputs"].append({"name": "unused", "datapoint_ref": {
            "ev_id": "ev_021", "label": "annual maintenance",
            "context": "Annual maintenance is $120 million per year",
            "value": "120000000.0", "unit": "USD"}})
        return spec
    assert build_quantified_spec("q", [_CAPEX, _OPEX], _evidence_rows(),
                                 spec_llm=raw) is None


# ── P7-12 calc-token strip (no leak) ─────────────────────────────────────────
def test_p7_12_calc_token_stripped_in_rendered_text():
    spec = _build_tco()
    result = _exec(spec)
    token = result.calc_token("tco")
    ok = (f"Total cost of ownership is $2,148,000,000.00{token} over five years "
          f"(modeled assumption).")
    report = pg.strict_verify(
        ok, _evidence_rows(), quantified_models={result.key(): result},
    )
    rendered, biblio = pg.resolve_provenance_to_citations(
        report.kept_sentences, _evidence_rows(),
    )
    assert "[#calc:" not in rendered
    assert "$2,148,000,000.00" in rendered           # the number survives
    assert any(b["evidence_id"] in {"ev_017", "ev_021"} for b in biblio)


# ── P7-13 sourced-conflict telemetry ─────────────────────────────────────────
def test_p7_13_sourced_conflict_flagged():
    a = _dp("ev_017", "program cost", "ctx a", 1_548_000_000.0)
    b = _dp("ev_099", "program cost", "ctx b", 2_000_000_000.0)  # same label, +29%
    conflicts = detect_sourced_conflicts([a, b])
    assert len(conflicts) == 1
    assert conflicts[0]["label"] == "program cost"
    # near-identical values do NOT flag
    assert detect_sourced_conflicts(
        [a, _dp("ev_098", "program cost", "ctx c", 1_548_000_001.0)]
    ) == []


# ── P7-14 audit replay ───────────────────────────────────────────────────────
def test_p7_14_audit_replay_roundtrip_and_stable_hash():
    spec1 = _build_tco()
    spec2 = _build_tco()
    assert spec1.spec_hash == spec2.spec_hash and spec1.spec_hash  # stable, nonempty
    with tempfile.TemporaryDirectory() as td:
        result = _exec(spec1, run_dir=td)
        path = os.path.join(td, "quantified_model.json")
        assert os.path.exists(path)
        with open(path, encoding="utf-8") as fh:
            bundle = json.load(fh)
        assert bundle["spec_hash"] == spec1.spec_hash
        assert bundle["fields"]["tco"]["display_value"] == "$2,148,000,000.00"


# ── P7-15 modeled base + sweep + break-even ──────────────────────────────────
def _profit_spec(price_sweep):
    capex = _dp("ev_017", "capex outlay",
                "Capital outlay was $1,200 for the unit", 1200.0)
    rows = {"ev_017": {"direct_quote": "Capital outlay was $1,200 for the unit."}}

    def raw(_q, _s):
        return {
            "model_id": "profit", "title": "Profit",
            "inputs": [
                {"name": "capex", "datapoint_ref": {
                    "ev_id": "ev_017", "label": "capex outlay",
                    "context": "Capital outlay was $1,200 for the unit",
                    "value": "1200.0", "unit": "USD"}},
                {"name": "price", "base": 10.0, "unit": "USD",
                 "sweep": price_sweep, "modeled": True},
            ],
            "outputs": [{"name": "profit", "unit": "USD", "display_kind": "number",
                         "formula": "price * 100 - capex"}],
            "sensitivity": [{"input": "price", "output": "profit"}],
            "solve_for": {"var": "price", "output": "profit"},
        }
    spec = build_quantified_spec("q", [capex], rows, spec_llm=raw)
    return spec, rows


def test_p7_15_modeled_base_sweep_breakeven():
    spec, rows = _profit_spec([5.0, 20.0, 1.0])           # bracket spans the root
    assert spec is not None
    result = asyncio.run(execute_quantified_model(spec, rows))
    # base profit at price=10: 10*100 - 1200 = -200
    assert abs(result.fields["profit"]["value"] - (-200.0)) < 1e-6
    # sensitivity grid present
    assert any(k.startswith("profit@price=") for k in result.fields)
    # break-even at price=12 (1200/100)
    assert "profit.break_even" in result.fields
    assert abs(result.fields["profit.break_even"]["value"] - 12.0) < 1e-6


def test_p7_15_no_breakeven_when_no_sign_change():
    spec, rows = _profit_spec([13.0, 20.0, 1.0])          # both endpoints positive
    result = asyncio.run(execute_quantified_model(spec, rows))
    assert "profit.break_even" not in result.fields


# ── P7-16 scaled-literal recovery ────────────────────────────────────────────
def test_p7_16_scaled_literal_recovery_and_span():
    spec = _build_tco()
    capex = next(s for s in spec.sourced_inputs if s.name == "capex")
    assert capex.value == 1_548_000_000.0
    assert "billion" in capex.raw_literal.lower()
    quote = _evidence_rows()["ev_017"]["direct_quote"]
    assert quote[capex.literal_start:capex.literal_end] == capex.raw_literal
    # a value absent from the evidence has no unique literal
    assert _locate_unique_literal(quote, 42.0) is None


# ── P7-17 exact-one-match (duplicate quantity) -> reject ─────────────────────
def test_p7_17_exact_one_match_duplicate_rejected():
    dup = _dp("ev_017", "program cost",
              "program cost was $1.548 billion in fiscal", 1548000000.0)
    # sourced_numbers now has TWO identical datapoints -> ref matches >=2 -> reject
    spec = build_quantified_spec(
        "q", [_CAPEX, dup, _OPEX], _evidence_rows(), spec_llm=_tco_raw_spec,
    )
    assert spec is None


# ── P7-18 cancellation / zero-effect dependency -> reject ────────────────────
def test_p7_18_cancellation_dependency_rejected():
    def raw(_q, _s):
        spec = _tco_raw_spec(_q, _s)
        # capex cancels out -> perturbing capex changes nothing -> reject
        spec["outputs"][0]["formula"] = "capex - capex + opex * years"
        return spec
    assert build_quantified_spec("q", [_CAPEX, _OPEX], _evidence_rows(),
                                 spec_llm=raw) is None


# ── P7-19 run-scoped stale model reject ──────────────────────────────────────
def test_p7_19_stale_model_id_rejected():
    spec = _build_tco()
    result = _exec(spec)
    stale = "[#calc:tco:deadbeefdeadbeef:tco]"
    sent = (f"Total cost of ownership is $2,148,000,000.00{stale} over five years "
            f"(modeled assumption).")
    report = pg.strict_verify(
        sent, _evidence_rows(), quantified_models={result.key(): result},
    )
    assert report.total_kept == 0
    assert any("calc_model_not_in_registry" in r
               for r in report.dropped_sentences[0].failure_reasons)


# ── P7-20 token adjacency ────────────────────────────────────────────────────
def test_p7_20_token_binds_to_adjacent_number():
    spec = _build_tco()
    result = _exec(spec)
    token = result.calc_token("tco")
    # the CORRECT value appears earlier, but a WRONG number is adjacent to the
    # token -> adjacency binds to $1.00 -> mismatch -> dropped.
    adversarial = (f"The figure $2,148,000,000.00 was noted, yet we claim "
                   f"$1.00{token} over five years (modeled assumption).")
    report = pg.strict_verify(
        adversarial, _evidence_rows(), quantified_models={result.key(): result},
    )
    assert report.total_kept == 0
    assert any("calc_number_mismatch" in r
               for r in report.dropped_sentences[0].failure_reasons)


# ── P7-21 / P7-22 fail-closed sentence-shape (wedge hardening) ───────────────
def test_p7_21_multiple_calc_tokens_dropped():
    spec = _build_tco()
    result = _exec(spec)
    t = result.calc_token("tco")
    # two calc tokens in one sentence -> only the 1st would verify -> drop whole
    sent = (f"TCO is $2,148,000,000.00{t} and again $2,148,000,000.00{t} "
            f"(modeled assumption).")
    report = pg.strict_verify(
        sent, _evidence_rows(), quantified_models={result.key(): result},
    )
    assert report.total_kept == 0
    assert any("calc_multiple_tokens_in_sentence" in r
               for r in report.dropped_sentences[0].failure_reasons)


def test_p7_22_mixed_calc_and_ev_token_dropped():
    spec = _build_tco()
    result = _exec(spec)
    t = result.calc_token("tco")
    # a [#calc:] sentence that ALSO carries an [#ev:] token would launder the
    # unverified Regime-A claim through the calc path -> fail-closed drop.
    sent = (f"Cost rose 14.9% [#ev:ev_017:0-20] to $2,148,000,000.00{t} "
            f"(modeled assumption).")
    report = pg.strict_verify(
        sent, _evidence_rows(), quantified_models={result.key(): result},
    )
    assert report.total_kept == 0
    assert any("calc_mixed_with_ev_token" in r
               for r in report.dropped_sentences[0].failure_reasons)


# ── P7-1 OFF byte-identity ───────────────────────────────────────────────────
def test_p7_1_off_byte_identity():
    rows = _evidence_rows()
    text = ("Semaglutide achieved a 14.9% reduction [#ev:ev_017:0-52]. "
            "Maintenance was noted [#ev:ev_021:0-44].")
    # absent param vs explicit None must produce identical reports
    r_absent = pg.strict_verify(text, rows)
    r_none = pg.strict_verify(text, rows, quantified_models=None)
    assert (r_absent.total_in, r_absent.total_kept, r_absent.total_dropped) == \
           (r_none.total_in, r_none.total_kept, r_none.total_dropped)
    # a registry present but NO calc token in the sentence -> Regime A unchanged
    r_reg = pg.strict_verify(text, rows, quantified_models={("x", "y"): object()})
    assert (r_reg.total_kept, r_reg.total_dropped) == \
           (r_absent.total_kept, r_absent.total_dropped)


# ── P7-2 sandbox unchanged ───────────────────────────────────────────────────
def test_p7_2_sandbox_rejects_dangerous_and_accepts_rendered():
    ok_os, _ = validate_script("import os\nprint(os.getpid())")
    ok_sock, _ = validate_script("import socket\nprint(1)")
    ok_sub, _ = validate_script("import subprocess\nprint(1)")
    assert not ok_os and not ok_sock and not ok_sub
    # the deterministic rendered script passes the UNCHANGED validator
    spec = _build_tco()
    ok_render, reason = validate_script(render_script(spec))
    assert ok_render, reason


# ── sweep-facing orchestrator (Extract -> ... -> verified section) ───────────
def test_p7_sweep_orchestrator_end_to_end():
    rows = {
        "ev_1": {
            "statement": "The total program cost was $2.0 billion in fiscal 2024.",
            "direct_quote": "The total program cost was $2.0 billion in fiscal 2024.",
            "source_url": "https://example.org/x", "tier": "T1",
        },
    }
    # discover the extractor's own datapoint, then reference it exactly
    dps = extract_numbers_from_evidence(rows)
    cost_dp = next(d for d in dps if abs(float(d["value"]) - 2_000_000_000.0) < 1)

    async def spec_provider(_q, sourced):
        dp = next(d for d in sourced
                  if abs(float(d["value"]) - 2_000_000_000.0) < 1)
        return {
            "model_id": "tco", "title": "TCO",
            "inputs": [
                {"name": "cost", "datapoint_ref": {
                    "ev_id": dp["evidence_id"], "label": dp["label"],
                    "context": dp["context"], "value": dp["value"],
                    "unit": dp["unit"]}},
                {"name": "years", "base": 3.0, "unit": "years",
                 "sweep": [1.0, 5.0, 1.0], "modeled": True},
            ],
            "outputs": [{"name": "tco", "unit": "USD", "display_kind": "currency",
                         "formula": "cost * years"}],
            "sensitivity": [{"input": "years", "output": "tco"}],
        }

    section, telem = asyncio.run(
        run_quantified_section("q", rows, spec_provider=spec_provider)
    )
    assert telem["spec_produced"] and telem["execution_success"]
    assert telem["verified_sentences"] >= 1
    assert section is not None
    assert "Quantified Trade-off" in section
    assert "[#calc:" not in section                       # token stripped
    assert "(modeled assumption)" in section              # years is modeled
    assert "$6,000,000,000.00" in section                 # 2e9 * 3
    # cost_dp sanity (the extractor really produced the $2.0B datapoint)
    assert cost_dp["evidence_id"] == "ev_1"


def test_p7_sweep_orchestrator_no_spec_returns_none():
    rows = {"ev_1": {"statement": "Qualitative finding with no usable numbers here.",
                     "direct_quote": "Qualitative finding with no usable numbers here."}}

    async def spec_provider(_q, _sourced):
        return None  # Writer declines to model -> graceful skip

    section, telem = asyncio.run(
        run_quantified_section("q", rows, spec_provider=spec_provider)
    )
    assert section is None and telem["spec_produced"] is False


# ── canonical display formatter sanity ───────────────────────────────────────
def test_canonical_display_formats():
    assert _canonical_display(2_148_000_000.0, "USD", "currency") == "$2,148,000,000.00"
    assert _canonical_display(23.4, "%", "percent") == "23.40%"
    assert _canonical_display(1.85, "", "ratio") == "1.8500"
    assert _canonical_display(1548, "", "count") == "1,548"
    assert _canonical_display(-200.0, "", "number") == "-200"
