"""Offline unit tests for the compose fast-loop harness leg-B oracle
(I-comp-fastloop-001 / Fable design 2026-07-09).

These are the ONLY offline part of the harness (the real compose subprocess is the
rest of the test). They exercise every HARNESS-OWNED leg-B rule — squash / body
extraction / the front-matter / chrome / markup / shell / truncated-number /
doubled-disclosure / confidence-clutter detectors / the ADVISORY quote-dump
tripwire / the gate-0 canary — against the REAL banked defect spans committed under
tests/fixtures/compose_harness/. No network, no mocks, no production predicate
(I-wire-013 independence).

The harness is loaded by file path (scripts/ is not a package); its heavy seam and
flag imports are lazy, so importing it here stays offline and cheap. Mirrors
tests/harness/test_fetch_harness_oracle.py.
"""
from __future__ import annotations

import importlib.util
import json
import threading
import time
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
_HARNESS_PATH = _REPO_ROOT / "scripts" / "compose_fastloop_harness.py"
_FIXTURE_DIR = _REPO_ROOT / "tests" / "fixtures" / "compose_harness"

_spec = importlib.util.spec_from_file_location("compose_fastloop_harness", _HARNESS_PATH)
h = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(h)


def _canary_pool() -> list[dict]:
    return json.loads((_FIXTURE_DIR / "canary_pool.json").read_text(encoding="utf-8"))


def _row(pool: list[dict], eid: str) -> dict:
    for r in pool:
        if r.get("evidence_id") == eid:
            return r
    raise AssertionError(f"{eid} not in canary pool fixture")


# ── squash: survives PDF hyphen-breaks, diacritics, case, whitespace ────────
def test_squash_survives_pdf_hyphen_break():
    assert h.squash("Gener-\native AI at Work") == "generativeaiatwork"
    assert h.squash("Generative AI at Work") == "generativeaiatwork"


def test_squash_strips_diacritics_and_is_idempotent():
    assert h.squash("Brynjólfsson") == "brynjolfsson"
    for token in ("crossref", "acknowledgements", "generativeaiatwork"):
        assert h.squash(token) == token


def test_squash_handles_empty_and_none():
    assert h.squash("") == ""
    assert h.squash(None) == ""


# ── provenance token stripping + body extraction ────────────────────────────
def test_strip_provenance_tokens():
    stripped = h.strip_provenance_tokens("worth 14% [#ev:ev_202:0-60] here")
    assert "[#ev" not in stripped and "14%" in stripped and "here" in stripped
    # No token => unchanged content.
    assert "automation" in h.strip_provenance_tokens("automation reshapes labor")


def test_body_paragraphs_skips_headers_tables_and_bibliography():
    report = (
        "# Verified Findings\n\n"
        "Automation reshapes labor demand across sectors and occupations.\n\n"
        "| col a | col b |\n| --- | --- |\n\n"
        "## References\n\n"
        "Crossref widget furniture that lives only in the bibliography.\n"
    )
    paras = h.body_paragraphs(report)
    joined = " ".join(paras).lower()
    assert "automation reshapes labor" in joined
    assert "crossref" not in joined            # bibliography section is cut
    assert "col a" not in joined               # table rows dropped


# ── front-matter: fires on real banked acknowledgements / suggested-citation ──
def test_front_matter_fires_on_real_thank_span():
    span = _row(_canary_pool(), "ev_019")["direct_quote"]
    assert "would like to thank" in span.lower()
    findings = h.front_matter_findings([span])
    assert findings and findings[0]["kind"] == "front_matter_weld"
    assert "thank" in findings[0]["detail"].lower()


def test_front_matter_fires_on_real_suggested_citation_span():
    span = _row(_canary_pool(), "ev_713")["direct_quote"]
    assert "suggested citation" in span.lower()
    assert h.front_matter_findings([span])


def test_front_matter_silent_on_clean_prose():
    clean = "Automation and new tasks reshape labor demand; robots displace routine work."
    assert h.front_matter_findings([clean]) == []


# ── chrome: fires on real banked Crossref widget + gov banner ───────────────
def test_chrome_fires_on_real_crossref_widget():
    span = _row(_canary_pool(), "ev_114")["direct_quote"]
    assert "crossref" in span.lower()
    findings = h.chrome_findings([span])
    assert findings and findings[0]["kind"] == "chrome_weld"


def test_chrome_fires_on_real_gov_banner():
    span = _row(_canary_pool(), "ev_006")["direct_quote"]
    assert "an official website of the united states government" in span.lower()
    assert h.chrome_findings([span])


def test_chrome_silent_on_clean_prose():
    assert h.chrome_findings(["Generative AI raises worker productivity by fifteen percent."]) == []


# ── markup: fires on markdown-link / naked-URL debris, silent on clean prose ──
def test_markup_fires_on_link_and_url_debris():
    assert h.markup_findings(["See [the paper](https://doi.org/10.1000/x) for detail."])
    assert h.markup_findings(["Retrieved from https://example.org/report.pdf on access."])


def test_markup_silent_on_clean_prose():
    assert h.markup_findings(["Automation displaces routine tasks and reinstates new labor."]) == []


# ── shell: link-density rule + per-case must_not_render fingerprints ─────────
def test_shell_link_density_fires_on_nav_farm():
    nav = "[Home](/home) [Search](/search) [Login](/login) [Menu](/menu) [About](/about)"
    findings = h.shell_findings([nav], must_not_render=[])
    assert any(f["kind"] == "shell_narration" for f in findings)


def test_shell_must_not_render_fires_on_case_fingerprint():
    span = _row(_canary_pool(), "ev_249")["direct_quote"]
    findings = h.shell_findings([span], must_not_render=["Skip to Main Content"])
    assert any(f["kind"] == "must_not_render" for f in findings)


def test_shell_silent_on_clean_prose():
    assert h.shell_findings(["Robots reduce local employment and wages in exposed labor markets."],
                            must_not_render=["skip to main content"]) == []


# ── truncated number: decimal-continuation against the REAL banked 14.2% span ──
def test_truncated_number_fires_on_real_142_span():
    span = _row(_canary_pool(), "ev_202")["direct_quote"]
    assert "14.2%" in span
    report = "AI penetration can lead to a 14% increase in total factor productivity. [#ev:ev_202:0-60]\n"
    findings = h.truncated_number_findings(report, {"ev_202": {"evidence_id": "ev_202", "direct_quote": span}},
                                           must_render=[], must_not_render=[])
    trunc = [f for f in findings if f["kind"] == "truncated_number"]
    assert trunc, "14 -> 14.2 decimal truncation not caught"
    assert "14" in trunc[0]["span"]


def test_truncated_number_silent_when_full_form_present():
    span = _row(_canary_pool(), "ev_202")["direct_quote"]
    report = "AI penetration can lead to a 14.2% increase in total factor productivity. [#ev:ev_202:0-60]\n"
    findings = h.truncated_number_findings(report, {"ev_202": {"evidence_id": "ev_202", "direct_quote": span}},
                                           must_render=[], must_not_render=[])
    assert [f for f in findings if f["kind"] == "truncated_number"] == []


def test_truncated_number_left_boundary_guard_no_false_positive():
    # prose "5" must NOT match inside span "50" (left boundary is not a digit/dot there,
    # but "50" has no decimal continuation) — and prose "5" inside "5.0" WOULD, so use
    # a span where 5 is embedded in 50 (integer, no decimal) => no flag.
    report = "About 5 firms adopted the tool. [#ev:x:0-10]\n"
    pool = {"x": {"evidence_id": "x", "direct_quote": "some 50 workers were surveyed"}}
    findings = h.truncated_number_findings(report, pool, must_render=[], must_not_render=[])
    assert [f for f in findings if f["kind"] == "truncated_number"] == []


def test_truncated_number_missing_must_render_flagged():
    report = "The figure was roughly one hundred. [#ev:ev_202:0-10]\n"
    findings = h.truncated_number_findings(report, {}, must_render=["175.2"], must_not_render=[])
    assert any(f["kind"] == "missing_must_render" for f in findings)


# ── doubled disclosure: LOCAL literal head counted, never imported ──────────
def test_doubled_disclosure_fires_on_two_copies():
    disc = h._ANALYST_DISCLOSURE_HEAD + " rest of the sentence."
    report = f"# Analyst Synthesis\n\n{disc}\n\n{disc}\n"
    findings = h.doubled_disclosure_findings(report)
    assert findings and findings[0]["kind"] == "doubled_disclosure"


def test_single_disclosure_is_clean():
    report = f"# Analyst Synthesis\n\n{h._ANALYST_DISCLOSURE_HEAD} rest.\n"
    assert h.doubled_disclosure_findings(report) == []


# ── confidence clutter ──────────────────────────────────────────────────────
def test_confidence_clutter_fires():
    assert h.confidence_clutter_findings(["Automation displaces tasks. [confidence: 0.72]"])


def test_confidence_clutter_silent_on_clean_prose():
    assert h.confidence_clutter_findings(["Automation displaces routine tasks."]) == []


# ── quote-dump advisory: never a FAIL, worst paragraph always quoted ────────
def test_quote_dump_advisory_is_advisory_only():
    pool = [{"evidence_id": "a", "direct_quote":
             "Automation and new tasks reshape labor demand across the whole modern economy today."}]
    report = ("# Verified Findings\n\n"
              "Automation and new tasks reshape labor demand across the whole modern economy today.\n")
    adv = h.quote_dump_advisory(report, pool)
    assert adv["binding"] is False
    assert 0.0 <= adv["worst_paragraph_frac"] <= 1.0
    assert "worst_paragraph" in adv


# ── run_leg_b_oracle aggregate + gate-0 canary against the committed fixtures ─
def test_run_leg_b_oracle_flags_known_bad_fixture():
    bad = (_FIXTURE_DIR / "known_bad_report.md").read_text(encoding="utf-8")
    res = h.run_leg_b_oracle(bad, _canary_pool(), {"must_not_render": []})
    kinds = {f["kind"] for f in res["findings"]}
    assert {"front_matter_weld", "chrome_weld", "truncated_number",
            "doubled_disclosure", "confidence_clutter"} <= kinds


def test_run_leg_b_oracle_clean_on_known_clean_fixture():
    clean = (_FIXTURE_DIR / "known_clean_report.md").read_text(encoding="utf-8")
    res = h.run_leg_b_oracle(clean, _canary_pool(), {"must_not_render": []})
    assert res["findings"] == []


def test_gate0_canary_is_green():
    ok, detail = h.gate0_canary()
    assert ok, detail
    assert detail["missing_required_kinds"] == []
    assert detail["known_clean_findings"] == []


# ── case file loads, is well-formed, names only real-id / requires markers ──
def test_case_file_loads_and_is_well_formed():
    cfg = h.load_cases()
    assert cfg["domain"] == "workforce"
    assert cfg["slug"] == "drb_72_ai_labor"
    names = {c["name"] for c in cfg["cases"]}
    assert {"clean_controls", "defect_frontmatter_weld", "defect_chrome_crossref",
            "defect_shell_narration", "defect_marketing_preamble",
            "defect_truncated_number", "synthesis_multi_source"} <= names
    for c in cfg["cases"]:
        assert c["expect"] in ("compose_clean", "defect_absent"), c["name"]


def test_requires_diag_snapshot_cases_have_empty_banked_ids():
    cfg = h.load_cases()
    by_name = {c["name"]: c for c in cfg["cases"]}
    for name in ("defect_marketing_preamble", "defect_truncated_number"):
        assert by_name[name].get("requires") == "diag_snapshot"
        assert by_name[name].get("evidence_ids") == []       # real ids not banked => no invented id


def test_named_evidence_ids_exist_in_banked_snapshot():
    cfg = h.load_cases()
    snap_path = _REPO_ROOT / cfg["snapshot"]
    if not snap_path.is_file():
        pytest.skip("banked snapshot is a gitignored artifact absent in this checkout "
                    "(verified present on the VM / main worktree at authoring time)")
    snap = json.loads(snap_path.read_text(encoding="utf-8"))
    banked = {r.get("evidence_id") for r in snap.get("evidence_for_gen", [])}
    for c in cfg["cases"]:
        for eid in c.get("evidence_ids", []):
            assert eid in banked, f"{c['name']} names non-banked id {eid}"


# ── flag registry: exactly the 14 I-deepfix-006 fix flags ───────────────────
def test_flag_registry_has_the_14_deepfix006_flags():
    envs = {env for env, _, _ in h._FLAG_READERS}
    assert len(h._FLAG_READERS) == 14
    assert {"PG_SYNTH_ENTAILMENT_VERIFY", "PG_SYNTH_SINGLE_SOURCE", "PG_SYNTH_D8_PROMOTE",
            "PG_SYNTH_BODY_LEAD", "PG_COMPOSE_NUMERIC_CITE_GUARANTEE", "PG_SYNTH_RENDER_CLEAN",
            "PG_INLINE_FURNITURE_STRIP", "PG_INLINE_MARKUP_STRIP", "PG_SHELL_SOURCE_INPUT_SCREEN",
            "PG_EVIDENCE_BASE_FINDING_PREFERENCE", "PG_UNCOVERED_DISCLOSURE_REFORMAT",
            "PG_FULL_QUOTE_WINDOW_SNAP", "PG_SENTENCE_SPLIT_SYMBOL_BOUNDARY",
            "PG_PT13_LEXICON_V2"} == envs


# ── bridge: a MIXED PASS+FAIL bridge must VOID (never compose on partly-stale content) ─
def test_apply_bridge_records_stale_rows_on_mixed_input():
    rows = [{"evidence_id": "a", "direct_quote": "banked A", "source_url": "http://a"},
            {"evidence_id": "b", "direct_quote": "banked B", "source_url": "http://b"}]
    bridge = {"ev:a": {"ev": "a", "verdict": "PASS", "quote": "full recovered body for A row"},
              "ev:b": {"ev": "b", "verdict": "FAIL", "quote": ""}}
    new_rows, stats = h.apply_bridge(rows, bridge, {})
    assert stats["bridged"] == 1
    assert stats["offered_but_not_bridged"] == 1
    assert "b" in stats["stale_evidence_ids"]
    # PASS row content replaced; FAIL row keeps its banked content.
    by_id = {r["evidence_id"]: r for r in new_rows}
    assert by_id["a"]["direct_quote"].startswith("full recovered body")
    assert by_id["b"]["direct_quote"] == "banked B"


def test_run_case_voids_on_mixed_bridge_without_allow_unbridged(tmp_path):
    snap = {"evidence_for_gen": [
        {"evidence_id": "a", "direct_quote": "banked A", "source_url": "http://a"},
        {"evidence_id": "b", "direct_quote": "banked B", "source_url": "http://b"}]}
    snap_path = tmp_path / "snap.json"
    snap_path.write_text(json.dumps(snap), encoding="utf-8")
    cfg = {"slug": "s", "domain": "d", "snapshot": str(snap_path), "diag_snapshot": ""}
    case = {"name": "mixed", "expect": "defect_absent", "evidence_ids": ["a", "b"]}
    bridge = {"ev:a": {"ev": "a", "verdict": "PASS", "quote": "full recovered body for A row"},
              "ev:b": {"ev": "b", "verdict": "FAIL", "quote": ""}}
    res = h.run_case(case, cfg, tmp_path / "run", "pipeline", bridge,
                     allow_unbridged=False, case_timeout=1, registry=h._ChildRegistry())
    assert res["verdict"] == h.VOID, res
    assert "b" in res["note"]              # the stale row id is disclosed in the VOID note


# ── pipeline_verdict: leg B alone must NOT decide the verdict ────────────────
def _leg_a(status=None, verification=None, rule_checks=None):
    manifest = {"status": status, "verification": verification} if status is not None else "SKIPPED (absent)"
    return {"manifest": manifest, "rule_checks": rule_checks if rule_checks is not None else "SKIPPED (absent)"}


def test_pipeline_verdict_abort_status_binds_fail_even_with_empty_leg_b():
    # abort_no_verified_sections still writes report.md (§9.1 invariant 4); a leg-B-only
    # verdict would false-PASS. The abort status must bind FAIL with the status quoted.
    verdict, findings, note = h.pipeline_verdict(
        _leg_a(status="abort_no_verified_sections"), 0, "tail", report_exists=True, leg_b_findings=[])
    assert verdict == h.FAIL
    assert any(f["kind"] == "manifest_abort_status" and f["span"] == "abort_no_verified_sections"
               for f in findings)
    assert "abort_no_verified_sections" in note


def test_pipeline_verdict_nonzero_exit_binds_fail():
    verdict, findings, _ = h.pipeline_verdict(
        _leg_a(status="success", rule_checks={"x": 1}), 7, "boom traceback", True, [])
    assert verdict == h.FAIL
    assert any(f["kind"] == "pipeline_subprocess_fail" for f in findings)


def test_pipeline_verdict_pass_requires_success_manifest_and_readable_leg_a():
    verdict, _, _ = h.pipeline_verdict(
        _leg_a(status="success", rule_checks={"pt11": True}), 0, "", True, [])
    assert verdict == h.PASS


def test_pipeline_verdict_skipped_leg_a_is_degraded_ok_not_pass():
    # Clean report + leg B empty, but manifest / rule_checks skipped => DEGRADED_OK.
    verdict, _, note = h.pipeline_verdict(_leg_a(), 0, "", True, [])
    assert verdict == h.DEGRADED_OK
    assert "not authorized" in note


def test_pipeline_verdict_leg_b_findings_bind_fail():
    verdict, _, _ = h.pipeline_verdict(
        _leg_a(status="success", rule_checks={"pt11": True}), 0, "", True,
        [{"kind": "chrome_weld", "span": "Crossref widget", "detail": "x"}])
    assert verdict == h.FAIL


def test_pipeline_verdict_no_report_is_unreachable():
    verdict, _, _ = h.pipeline_verdict(_leg_a(status="success"), 0, "", report_exists=False, leg_b_findings=[])
    assert verdict == h.UNREACHABLE


# ── leg A binds gate RESULTS, not file presence (I-comp-fastloop gate P1) ────
def _leg_a_checks(status="success", failed=None, gate_reasons=None,
                  checks=None, verification=None, release_allowed=None):
    """Build a leg_a dict in the shape _read_leg_a now emits (parsed rule_checks +
    manifest evaluator_gate.reasons), so pipeline_verdict is exercised against gate
    RESULTS rather than mere file presence."""
    return {
        "rule_checks": {"checks": checks or [], "failed": failed or [],
                        "pt11_present": True, "pt13_present": True, "raw_keys": ["rule_checks"]},
        "manifest": {"status": status, "verification": verification,
                     "release_allowed": release_allowed, "gate_reasons": gate_reasons or []},
    }


def test_pipeline_verdict_failed_pt11_rule_check_cannot_pass_on_success_manifest():
    # The exact Codex probe: manifest.status='success', PT11 passed=false, leg B clean.
    # A presence-only leg A false-PASSed this. It MUST now FAIL with the detail QUOTED.
    leg_a = _leg_a_checks(status="success", failed=[
        {"item_id": "PT11", "passed": False, "waived": False,
         "details": "2 uncited numeric claims: '14% increase', '9.1M jobs'"}])
    verdict, findings, note = h.pipeline_verdict(leg_a, 0, "", report_exists=True, leg_b_findings=[])
    assert verdict == h.FAIL
    rc = [f for f in findings if f["kind"] == "leg_a_rule_check_failed"]
    assert rc and "uncited numeric" in rc[0]["span"]        # failing detail is quoted, not a count
    assert "PT11" in note


def test_pipeline_verdict_advisory_pt13_trip_cannot_pass():
    # PT13 is ADVISORY in production → a trip keeps manifest.status=='success'. The
    # harness must still FAIL (never PASS) with the example strings quoted.
    leg_a = _leg_a_checks(status="success", failed=[
        {"item_id": "PT13", "passed": False, "waived": False,
         "details": "2 unhedged: [\"'largest' in: 'AI is the largest driver of job loss'\"]"}])
    verdict, findings, _ = h.pipeline_verdict(leg_a, 0, "", report_exists=True, leg_b_findings=[])
    assert verdict == h.FAIL
    rc = [f for f in findings if f["kind"] == "leg_a_rule_check_failed"]
    assert rc and "largest" in rc[0]["span"]                # example string quoted


def test_pipeline_verdict_manifest_gate_reason_binds_fail_independently():
    # Second independent artifact (I-wire-013): even with an all-pass rule_checks list,
    # a manifest evaluator_gate.reasons advisory_pt13 trip binds FAIL.
    leg_a = _leg_a_checks(status="success", failed=[],
                          gate_reasons=["advisory_pt13_unhedged_superlatives"])
    verdict, findings, _ = h.pipeline_verdict(leg_a, 0, "", report_exists=True, leg_b_findings=[])
    assert verdict == h.FAIL
    assert any("advisory_pt13" in f["span"] for f in findings if f["kind"] == "leg_a_rule_check_failed")


def test_leg_a_rule_findings_dedup_across_both_artifacts():
    # PT11 present in BOTH the failed list and the manifest reason must produce ONE finding.
    leg_a = _leg_a_checks(status="success",
                          failed=[{"item_id": "PT11", "passed": False, "waived": False,
                                   "details": "1 uncited numeric claim"}],
                          gate_reasons=["rule_pt11_uncited_numeric_claims"])
    findings = h._leg_a_rule_findings(leg_a)
    assert len(findings) == 1, findings


def test_leg_a_rule_findings_waived_check_is_not_a_fail():
    # An HONEST WAIVER (passed True carried through _read_leg_a's failed filter) never
    # reaches the failed list; a waived entry passed straight in must also not FAIL.
    leg_a = _leg_a_checks(status="success", failed=[])   # waived checks never enter 'failed'
    assert h._leg_a_rule_findings(leg_a) == []


def test_read_leg_a_parses_failed_pt11_end_to_end_and_pipeline_verdict_fails(tmp_path):
    """END-TO-END: a real evaluator_rule_checks.json (PT11 passed=false) + a
    manifest.json (status='success') on disk → _read_leg_a parses the CONTENT →
    pipeline_verdict FAILs with PT11's detail quoted. Reproduces the Codex probe and
    guards the exact half r1 missed (the parse discarding passed/details)."""
    query_dir = tmp_path / "workforce" / "drb_72_ai_labor"
    query_dir.mkdir(parents=True)
    (query_dir / "evaluator_rule_checks.json").write_text(json.dumps({
        "generator_model": "deepseek/deepseek-v4-pro",
        "evaluator_model": "qwen/qwen3.6-35b-a3b",
        "rule_checks": [
            {"item_id": "PT08", "name": "Contradiction disclosure", "passed": True, "details": ""},
            {"item_id": "PT11", "name": "Numeric claims have citation markers",
             "passed": False, "details": "2 uncited: '14% increase', '9.1M jobs'"},
            {"item_id": "PT13", "name": "Superlatives hedged", "passed": True, "details": ""},
        ],
    }), encoding="utf-8")
    (query_dir / "manifest.json").write_text(json.dumps({
        "status": "success", "release_allowed": True,
        "evaluator_gate": {"gate_class": "abort", "reasons": ["rule_pt11_uncited_numeric_claims"]},
    }), encoding="utf-8")

    leg_a = h._read_leg_a(query_dir)
    assert isinstance(leg_a["rule_checks"], dict)
    assert [c["item_id"] for c in leg_a["rule_checks"]["failed"]] == ["PT11"]

    verdict, findings, note = h.pipeline_verdict(leg_a, 0, "", report_exists=True, leg_b_findings=[])
    assert verdict == h.FAIL, (verdict, note)
    rc = [f for f in findings if f["kind"] == "leg_a_rule_check_failed"]
    assert rc and "uncited" in rc[0]["span"]
    assert "PT11" in note


def test_summarize_degraded_ok_blocks_authorize():
    ok = h._summarize([{"name": "clean_controls", "verdict": h.PASS}, {"name": "x", "verdict": h.PASS}])
    assert ok["authorize_full_pipeline"] is True
    degraded = h._summarize([{"name": "clean_controls", "verdict": h.PASS}, {"name": "x", "verdict": h.DEGRADED_OK}])
    assert degraded["authorize_full_pipeline"] is False


# ── run_all: a wedged case CANNOT hold the harness past the total deadline ────
def test_run_all_returns_at_total_deadline_when_case_wedges(monkeypatch):
    """With a 1s total timeout and a run_case that wedges ~3s, run_all must return at
    ~1s, recording the case UNREACHABLE and abandoning the daemon worker — never
    blocking on the wedged child (§8.4)."""
    release = threading.Event()

    def _wedged(case, *a, **k):
        release.wait(timeout=3.0)
        return {"name": case["name"], "verdict": h.PASS}

    monkeypatch.setattr(h, "run_case", _wedged)
    cfg = {"domain": "workforce", "slug": "drb_72_ai_labor", "snapshot": "", "diag_snapshot": ""}
    case = {"name": "wedged", "expect": "compose_clean", "evidence_ids": []}
    start = time.monotonic()
    results = h.run_all([case], cfg, Path("."), "pipeline", None, False,
                        max_parallel=1, case_timeout=10, total_timeout=1)
    elapsed = time.monotonic() - start
    release.set()
    assert elapsed < 3.0, f"run_all ignored the total deadline: {elapsed:.2f}s"
    assert len(results) == 1 and results[0]["verdict"] == h.UNREACHABLE
