"""I-deepfix-001 (#1344) Wave-3a — fail-loud ACTIVATION canary (offline, no model / GPU / spend).

``scripts/dr_benchmark/run_gate_b.py`` gains a POST-RUN activation canary that guarantees, on a
RELEASED paid run, that every ACTIVATED new-core module ACTUALLY FIRED and no OLD/WRONG module
silently replaced it.

MARKER TRANSPORT (Fable P0): 10 of the 11 modules emit their ``[activation]`` marker via a Python
MODULE logger (``logger.info``) that streams to STDOUT only — it never reaches run_log.txt. So the
canary reads a ROOT-logger capture buffer (``_ActivationMarkerCaptureHandler``) COMBINED with
run_log.txt (which carries the one ``_log``-emitted marker, provenance_reanchor). This test proves the
LIVE module-logger transport reaches the capture handler (``test_live_plumbing_*``), so the
transport-blind class can never recur.

For each module whose flag is ON at call time the canary asserts: (a) the POSITIVE marker is PRESENT,
(b) honesty booleans are HEALTHY, (c) the inverted degrade counter is EXACTLY ZERO (provenance
``local_window==0`` — Fable P0 option-B routes the never-logged ``reanchored_local_window`` soft-warning
through a telemetry counter), (d) the OLD/degrade marker (anchor_equality) is ABSENT. Opt-in via
``PG_ACTIVATION_CANARY`` (default OFF => byte-identical, no handler, no record key). Self-scopes to the
activated slate using each producer's OWN truthy predicate (Fable P2). STRUCTURAL only, never a quality
count threshold (§-1.3). Telemetry stubbed as log strings — no pipeline run, no model, no network.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
# Offline: no judge calls, no network, deterministic behavior when importing the producer module.
os.environ.setdefault("PG_VERIFICATION_MODE", "off")

import scripts.dr_benchmark.run_gate_b as rg  # noqa: E402
from src.polaris_graph.generator import multi_section_generator as msg  # noqa: E402

_FLAG = "PG_ACTIVATION_CANARY"
_GATE_B = _REPO_ROOT / "scripts" / "dr_benchmark" / "run_gate_b.py"

# The 10 module activation flags the canary self-scopes on (span-resolver is folded into
# provenance_reanchor; PG_SPAN_RESOLVER is no longer a distinct spec). All default OFF; force-EXACT "1"
# on a released slate run.
_MODULE_FLAGS = (
    "PG_SYNTH_PRIMARY",
    "PG_FINDING_DEDUP_NLI",
    "PG_BASKET_CONSUME_FINDING_DEDUP",
    "PG_CROSS_SOURCE_BODY",
    "PG_NUMERIC_COMPARATOR",
    "PG_TWO_SIDED_DEBATE",
    "PG_MIN_CITE_SET",
    "PG_PROVENANCE_REANCHOR",
    "PG_EXPERT_FACET_PLANNER",
    "PG_SUBENTITY_QUERY_EXPANSION",
)

# A realistic run_log line prefix (level/logger/timestamp) — the canary regexes use .search/.finditer so
# they must match the marker MID-line, not only at column 0.
_PREFIX = "2026-07-06 12:00:00,123 INFO src.polaris_graph - "

# Healthy POSITIVE markers (bools all healthy, local_window==0, no anchor-equality), byte-shaped like the
# U2 producers.
_HEALTHY = {
    "synth_primary": "[activation] synth_primary: authored_prose kept=5",
    "finding_dedup_nli": (
        "[activation] finding_dedup_nli: invoked directional_merges=3 degraded=False wall_truncated=False"
    ),
    "basket_consume_finding_dedup": (
        "[activation] basket_consume_finding_dedup: regrouped old_to_new=12 noop=False"
    ),
    "cross_source_body": (
        "[activation] cross_source_body: plan_driven pairs=4 input_threaded=True degraded=False"
    ),
    "numeric_comparator": "[activation] numeric_comparator: upgraded=2 build_ok=True",
    "two_sided_debate": "[activation] two_sided_debate: leg2_inspected=7 con_disclosed=1",
    "min_cite_set": "[activation] min_cite_set: minimized=6 demoted_to_weight=2 build_ok=True",
    "provenance_reanchor": (
        "[activation] provenance_reanchor: accepted=9 reanchored_argmax=4 local_window=0 build_ok=True"
    ),
    "expert_facet_planner": "[activation] expert_facet_planner: facets=5",
    "subentity_query_expansion": "[activation] subentity_query_expansion: expanded_queries=8",
}

# The same markers but with EVERY count == 0 (bools healthy, local_window==0) — proves the §-1.3 rule:
# a POSITIVE marker present with count=0 is ALLOWED (eligible-yet-zero is the shallow canary's concern).
_HEALTHY_ZERO = {
    "synth_primary": "[activation] synth_primary: authored_prose kept=0",
    "finding_dedup_nli": (
        "[activation] finding_dedup_nli: invoked directional_merges=0 degraded=False wall_truncated=False"
    ),
    "basket_consume_finding_dedup": (
        "[activation] basket_consume_finding_dedup: regrouped old_to_new=0 noop=False"
    ),
    "cross_source_body": (
        "[activation] cross_source_body: plan_driven pairs=0 input_threaded=True degraded=False"
    ),
    "numeric_comparator": "[activation] numeric_comparator: upgraded=0 build_ok=True",
    "two_sided_debate": "[activation] two_sided_debate: leg2_inspected=0 con_disclosed=0",
    "min_cite_set": "[activation] min_cite_set: minimized=0 demoted_to_weight=0 build_ok=True",
    "provenance_reanchor": (
        "[activation] provenance_reanchor: accepted=0 reanchored_argmax=0 local_window=0 build_ok=True"
    ),
    "expert_facet_planner": "[activation] expert_facet_planner: facets=0",
    "subentity_query_expansion": "[activation] subentity_query_expansion: expanded_queries=0",
}

# The OLD/degrade signals (must be ABSENT / zero on a released run).
_ANCHOR_EQUALITY = "[activation] cross_source_body: anchor_equality pairs=3"
_PROV_LOCAL_WINDOW_FIRED = (
    "[activation] provenance_reanchor: accepted=9 reanchored_argmax=4 local_window=2 build_ok=True"
)


def _log(base=None, *, overrides=None, drop=(), extra=()):
    """Build a run_log text from ``base`` (default healthy), dropping ``drop`` modules, applying
    ``overrides`` (module -> replacement marker line), and appending raw ``extra`` lines. Each marker
    line is prefixed with a realistic logger prefix; a couple of unrelated noise lines are interleaved."""
    lines = dict(base if base is not None else _HEALTHY)
    for name in drop:
        lines.pop(name, None)
    if overrides:
        lines.update(overrides)
    body = ["2026-07-06 11:59:59,000 INFO retrieval - fetched 42 rows"]
    body += [_PREFIX + v for v in lines.values()]
    body += ["2026-07-06 12:00:01,000 INFO render - report.md written"]
    body += [_PREFIX + e for e in extra]
    return "\n".join(body) + "\n"


def _all_flags_on(monkeypatch, canary="1"):
    """Turn the canary opt-in + all 10 module flags ON (the released-slate condition)."""
    monkeypatch.setenv(_FLAG, canary)
    for flag in _MODULE_FLAGS:
        monkeypatch.setenv(flag, "1")
    # This harness scopes to the 10 wave-3a modules; the wave-6 summary_table flag is DEFAULT-ON
    # (its canary spec now carries flag_default_on=True), so opt it explicitly OFF here — its
    # fire-marker liveness is covered by its own test_summary_table_activation_canary.py, and these
    # synthetic wave-3a logs deliberately carry no summary_table marker.
    monkeypatch.setenv("PG_RENDER_SUMMARY_TABLE", "0")


def _wrapper(log_text, status="success", smoke_scale=False):
    return rg._run_activation_canary(
        log_text, status, smoke_scale=smoke_scale, domain="d", slug="s",
    )


def _debate_lines(caplog):
    prefix = "[activation] two_sided_debate:"
    return [r.getMessage() for r in caplog.records if r.getMessage().startswith(prefix)]


# ── (Fable P0) LIVE PLUMBING: a REAL module-logger marker reaches the capture handler ─────────────

def test_live_plumbing_module_logger_reaches_capture_handler(monkeypatch):
    """The transport-blind guard: emit an ``[activation]`` line via the REAL producer module-logger path
    (multi_section_generator._emit_two_sided_debate_marker) and assert it lands in the sink the canary now
    reads (the root-attached _ActivationMarkerCaptureHandler). Reading run_log.txt would MISS this line."""
    monkeypatch.setenv("PG_TWO_SIDED_DEBATE", "1")
    sink: list[str] = []
    root = logging.getLogger()
    prev_root_level = root.level
    prev_emit_level = msg.logger.level
    root.setLevel(logging.INFO)
    msg.logger.setLevel(logging.INFO)  # ensure the emitting logger passes INFO to its handlers
    handler = rg._ActivationMarkerCaptureHandler(sink)
    root.addHandler(handler)
    try:
        msg._emit_two_sided_debate_marker(3, 1)              # REAL module-logger emit (not a stub string)
        msg.logger.info("unrelated non-activation log line")  # must NOT be captured (bounded-memory filter)
    finally:
        root.removeHandler(handler)
        root.setLevel(prev_root_level)
        msg.logger.setLevel(prev_emit_level)
    assert sink == ["[activation] two_sided_debate: leg2_inspected=3 con_disclosed=1"]


def test_capture_handler_keeps_only_activation_records():
    sink: list[str] = []
    h = rg._ActivationMarkerCaptureHandler(sink)
    keep = logging.LogRecord(
        "m", logging.INFO, __file__, 1,
        "[activation] synth_primary: authored_prose kept=1", None, None,
    )
    drop = logging.LogRecord("m", logging.INFO, __file__, 1, "some other log line", None, None)
    h.emit(keep)
    h.emit(drop)
    assert sink == ["[activation] synth_primary: authored_prose kept=1"]


# ── (a) OFF => byte-identical: the canary NEVER runs (no raise even on a would-FAIL log) ───────────

def test_off_assert_is_noop_on_would_fail_log(monkeypatch):
    monkeypatch.delenv(_FLAG, raising=False)  # canary default OFF
    for flag in _MODULE_FLAGS:
        monkeypatch.setenv(flag, "1")  # modules ON, so an empty log WOULD FAIL if the canary ran
    assert not rg._activation_canary_enabled()
    rg.assert_activation_markers_fired("")            # no raise (canary self-gated OFF)
    rg.assert_activation_markers_fired(_log(drop=("synth_primary",)))  # would FAIL if ON — still no raise


def test_off_wrapper_returns_skip_disabled(monkeypatch):
    monkeypatch.delenv(_FLAG, raising=False)
    for flag in _MODULE_FLAGS:
        monkeypatch.setenv(flag, "1")
    assert _wrapper(_log(drop=("synth_primary",))) == "skip:disabled"


def test_off_explicit_zero_is_off(monkeypatch):
    monkeypatch.setenv(_FLAG, "0")
    assert not rg._activation_canary_enabled()
    rg.assert_activation_markers_fired("")  # no raise


def test_sweep_record_key_is_guarded_off_byte_identical():
    """OFF-purity (mirrors Wave-1d): the base ``_record`` dict must NOT contain an ``activation_canary``
    key; it is added ONLY inside ``if _activation_canary is not None:`` so a flag-OFF run's
    sweep_summary.json is byte-identical to the pre-Wave-3a baseline. The ``ok`` conjunct references the
    VARIABLE (None-safe: None != "FAILED"), never the key string, so it lives in the base literal."""
    src = _GATE_B.read_text(encoding="utf-8")
    assert "if _activation_canary is not None:" in src
    assert '_record["activation_canary"] = _activation_canary' in src
    start = src.index("_record = {")
    guard = src.index("if _shallow_canary is not None:", start)
    base_literal = src[start:guard]
    assert '"activation_canary"' not in base_literal, "the OFF path would emit a null activation_canary key"
    assert 'and _activation_canary != "FAILED"' in base_literal
    assert "_activation_canary = None" in src
    assert "if _activation_canary_enabled():" in src
    # OFF also attaches NO capture handler (byte-identical; the attach is behind the same gate).
    assert "_activation_handler = _ActivationMarkerCaptureHandler(" in src


# ── (b) healthy log => ok ─────────────────────────────────────────────────────────────────────────

def test_healthy_log_ok(monkeypatch):
    _all_flags_on(monkeypatch)
    rg.assert_activation_markers_fired(_log())  # no raise
    assert _wrapper(_log()) == "ok"


def test_healthy_log_ok_released_with_disclosed_gaps(monkeypatch):
    _all_flags_on(monkeypatch)
    assert _wrapper(_log(), status="released_with_disclosed_gaps") == "ok"


def test_zero_counts_are_allowed_structural_not_threshold(monkeypatch):
    """§-1.3: a POSITIVE marker present with count=0 is ALLOWED (the canary asserts RAN + not-degraded,
    NEVER count>=K). local_window stays 0 in _HEALTHY_ZERO (that field is an inverted degrade, must be 0)."""
    _all_flags_on(monkeypatch)
    rg.assert_activation_markers_fired(_log(base=_HEALTHY_ZERO))  # no raise
    assert _wrapper(_log(base=_HEALTHY_ZERO)) == "ok"


# ── (c) a module marker MISSING while its flag is ON => FAILED ─────────────────────────────────────

def test_missing_marker_fails(monkeypatch):
    _all_flags_on(monkeypatch)
    with pytest.raises(RuntimeError, match="SYNTH_PRIMARY MARKER ABSENT"):
        rg.assert_activation_markers_fired(_log(drop=("synth_primary",)))
    assert _wrapper(_log(drop=("synth_primary",))) == "FAILED"


def test_missing_marker_self_scoped_when_flag_off(monkeypatch):
    """Self-scoping: a module whose flag is OFF is NOT asserted — its absent marker does not FAIL."""
    _all_flags_on(monkeypatch)
    monkeypatch.setenv("PG_SYNTH_PRIMARY", "0")  # synth-primary NOT in the active slate
    rg.assert_activation_markers_fired(_log(drop=("synth_primary",)))  # no raise
    assert _wrapper(_log(drop=("synth_primary",))) == "ok"


@pytest.mark.parametrize("drop_module,token", [
    ("finding_dedup_nli", "FINDING_DEDUP_NLI MARKER ABSENT"),
    ("cross_source_body", "CROSS_SOURCE_BODY MARKER ABSENT"),
    ("min_cite_set", "MIN_CITE_SET MARKER ABSENT"),
    ("provenance_reanchor", "PROVENANCE_REANCHOR MARKER ABSENT"),
    ("expert_facet_planner", "EXPERT_FACET_PLANNER MARKER ABSENT"),
    ("subentity_query_expansion", "SUBENTITY_QUERY_EXPANSION MARKER ABSENT"),
])
def test_each_missing_marker_fails(monkeypatch, drop_module, token):
    _all_flags_on(monkeypatch)
    with pytest.raises(RuntimeError, match=token):
        rg.assert_activation_markers_fired(_log(drop=(drop_module,)))


# ── (d) an OLD/degrade signal PRESENT => FAILED ───────────────────────────────────────────────────

def test_anchor_equality_degrade_marker_fails(monkeypatch):
    _all_flags_on(monkeypatch)
    log = _log(extra=(_ANCHOR_EQUALITY,))  # plan_driven still present, but the OLD anchor path also fired
    with pytest.raises(RuntimeError, match="CROSS_SOURCE_BODY OLD/DEGRADE MARKER PRESENT"):
        rg.assert_activation_markers_fired(log)
    assert _wrapper(log) == "FAILED"


def test_provenance_local_window_nonzero_fails(monkeypatch):
    """Fable P0 option-B: the forbidden local-window fallback leg recovered N>0 spans (regression that
    re-opened the leg pinned OFF on gate-B) => the provenance marker's local_window field != 0 => FAIL."""
    _all_flags_on(monkeypatch)
    log = _log(overrides={"provenance_reanchor": _PROV_LOCAL_WINDOW_FIRED})
    with pytest.raises(RuntimeError, match="PROVENANCE_REANCHOR OLD/DEGRADE LEG FIRED"):
        rg.assert_activation_markers_fired(log)
    assert _wrapper(log) == "FAILED"


def test_provenance_local_window_self_scoped_when_flag_off(monkeypatch):
    """Self-scoping: with PG_PROVENANCE_REANCHOR OFF the local_window inverted tripwire is not asserted."""
    _all_flags_on(monkeypatch)
    monkeypatch.setenv("PG_PROVENANCE_REANCHOR", "0")
    assert _wrapper(_log(overrides={"provenance_reanchor": _PROV_LOCAL_WINDOW_FIRED})) == "ok"


# ── (e) an honesty boolean is UNHEALTHY (degrade) => FAILED ───────────────────────────────────────

@pytest.mark.parametrize("module,bad_line,token", [
    (
        "finding_dedup_nli",
        "[activation] finding_dedup_nli: invoked directional_merges=3 degraded=True wall_truncated=False",
        "FINDING_DEDUP_NLI DEGRADED",
    ),
    (
        "finding_dedup_nli",
        "[activation] finding_dedup_nli: invoked directional_merges=3 degraded=False wall_truncated=True",
        "FINDING_DEDUP_NLI DEGRADED",
    ),
    (
        "basket_consume_finding_dedup",
        "[activation] basket_consume_finding_dedup: regrouped old_to_new=12 noop=True",
        "BASKET_CONSUME_FINDING_DEDUP DEGRADED",
    ),
    (
        "cross_source_body",
        "[activation] cross_source_body: plan_driven pairs=4 input_threaded=False degraded=True",
        "CROSS_SOURCE_BODY DEGRADED",
    ),
    (
        "numeric_comparator",
        "[activation] numeric_comparator: upgraded=2 build_ok=False",
        "NUMERIC_COMPARATOR DEGRADED",
    ),
    (
        "min_cite_set",
        "[activation] min_cite_set: minimized=6 demoted_to_weight=2 build_ok=False",
        "MIN_CITE_SET DEGRADED",
    ),
    (
        "provenance_reanchor",
        "[activation] provenance_reanchor: accepted=9 reanchored_argmax=4 local_window=0 build_ok=False",
        "PROVENANCE_REANCHOR DEGRADED",
    ),
])
def test_unhealthy_boolean_fails(monkeypatch, module, bad_line, token):
    _all_flags_on(monkeypatch)
    log = _log(overrides={module: bad_line})
    with pytest.raises(RuntimeError, match=token):
        rg.assert_activation_markers_fired(log)
    assert _wrapper(log) == "FAILED"


# ── (Fable P2-1) flag on-detection matches each producer's OWN truthy predicate ───────────────────

def test_flag_whitelist_yes_does_not_over_demand_expert(monkeypatch):
    """expert-facet producer accepts ONLY {"1","true","True"} — a slate value "yes" is OFF for it, so the
    canary must NOT demand the expert marker (no false-FAIL)."""
    _all_flags_on(monkeypatch)
    monkeypatch.setenv("PG_EXPERT_FACET_PLANNER", "yes")  # OFF for the strict-whitelist producer
    assert _wrapper(_log(drop=("expert_facet_planner",))) == "ok"


def test_flag_whitelist_one_still_demands_expert(monkeypatch):
    _all_flags_on(monkeypatch)  # sets PG_EXPERT_FACET_PLANNER="1"
    with pytest.raises(RuntimeError, match="EXPERT_FACET_PLANNER MARKER ABSENT"):
        rg.assert_activation_markers_fired(_log(drop=("expert_facet_planner",)))


def test_flag_blocklist_module_yes_is_on(monkeypatch):
    """A blocklist producer (two_sided_debate) treats "yes" as ON — the canary must still demand it."""
    _all_flags_on(monkeypatch)
    monkeypatch.setenv("PG_TWO_SIDED_DEBATE", "yes")
    with pytest.raises(RuntimeError, match="TWO_SIDED_DEBATE MARKER ABSENT"):
        rg.assert_activation_markers_fired(_log(drop=("two_sided_debate",)))


def test_activation_flag_on_predicate():
    # strict whitelist (expert/subentity/provenance) vs blocklist default.
    assert rg._activation_flag_on("PG_UNSET_X", ("1", "true")) is False  # unset default "0"
    assert rg._activation_flag_on("PG_UNSET_X", None) is False           # blocklist unset => OFF


# ── (f) missing run_log => skip:no-run-log (not a false ok, not a false FAIL) ─────────────────────

def test_no_data_path_records_skip_not_ok():
    """When run_log.txt is missing/unreadable, provenance_reanchor's ``_log``-emitted marker is unreadable;
    asserting over the buffer alone would false-FAIL it. The sweep records ``skip:no-run-log`` instead."""
    src = _GATE_B.read_text(encoding="utf-8")
    assert '_activation_canary = "skip:no-run-log"' in src
    assert "if _ac_log_text is None:" in src
    # the canary reads the capture buffer COMBINED with run_log.txt.
    assert "_ac_combined =" in src
    assert "_activation_log_lines" in src


def test_empty_text_with_flags_on_would_fail_hence_skip_is_needed(monkeypatch):
    """Demonstrates WHY the no-run-log skip exists: calling the wrapper with "" while modules are ON FAILS
    (markers absent), so the sweep records skip:no-run-log instead of running the canary on no data."""
    _all_flags_on(monkeypatch)
    assert _wrapper("") == "FAILED"


# ── wrapper status/smoke gating (reuses the breadth/M6/shallow released-status universe) ──────────

def test_wrapper_skip_on_non_released_status(monkeypatch):
    _all_flags_on(monkeypatch)
    out = _wrapper(_log(drop=("synth_primary",)), status="abort_scope_rejected")  # would FAIL if released
    assert out.startswith("skip:status=")


def test_wrapper_skip_on_smoke_scale(monkeypatch):
    _all_flags_on(monkeypatch)
    assert _wrapper(_log(drop=("synth_primary",)), smoke_scale=True) == "skip:smoke_scale"


def test_wrapper_released_status_universe_is_reused():
    assert "success" in rg._BREADTH_CANARY_RELEASED_STATUSES
    assert "released_with_disclosed_gaps" in rg._BREADTH_CANARY_RELEASED_STATUSES
    assert "abort_scope_rejected" not in rg._BREADTH_CANARY_RELEASED_STATUSES


# ── (Fable P1) producer: the two-sided-debate summary marker is emitted exactly once per run ──────

def test_two_sided_debate_summary_once_per_run(monkeypatch, caplog):
    monkeypatch.setenv("PG_TWO_SIDED_DEBATE", "1")
    with caplog.at_level(logging.INFO, logger=msg.logger.name):
        msg._reset_two_sided_debate_telemetry()
        msg._accumulate_two_sided_debate(3, 1)
        msg._accumulate_two_sided_debate(2, 0)
        msg._emit_two_sided_debate_run_summary()
    assert _debate_lines(caplog) == ["[activation] two_sided_debate: leg2_inspected=5 con_disclosed=1"]


def test_two_sided_debate_summary_zero_when_no_debate_section(monkeypatch, caplog):
    """The healthy common case: PG_TWO_SIDED_DEBATE ON but the plan had NO debate section — one summary
    marker with leg2_inspected=0 (not zero markers, which false-FAILED the canary before Fable P1)."""
    monkeypatch.setenv("PG_TWO_SIDED_DEBATE", "1")
    with caplog.at_level(logging.INFO, logger=msg.logger.name):
        msg._reset_two_sided_debate_telemetry()
        # no accumulation (no debate section)
        msg._emit_two_sided_debate_run_summary()
    assert _debate_lines(caplog) == ["[activation] two_sided_debate: leg2_inspected=0 con_disclosed=0"]


def test_two_sided_debate_summary_off_no_emit(monkeypatch, caplog):
    monkeypatch.delenv("PG_TWO_SIDED_DEBATE", raising=False)
    with caplog.at_level(logging.INFO, logger=msg.logger.name):
        msg._reset_two_sided_debate_telemetry()
        msg._accumulate_two_sided_debate(3, 1)      # no-op when flag off (OFF byte-identical)
        msg._emit_two_sided_debate_run_summary()    # no-op when flag off
    assert _debate_lines(caplog) == []


# ── producer/canary drift guard + spec structure ─────────────────────────────────────────────────

def test_specs_match_runtime_marker_shape():
    by_name = {s.name: s for s in rg._ACTIVATION_MARKER_SPECS}
    for name, line in _HEALTHY.items():
        spec = by_name[name]
        assert spec.positive_re is not None
        assert spec.positive_re.search(_PREFIX + line) is not None, f"{name} positive_re does not match"
    # provenance_reanchor now carries the span-resolver signals: reanchored_argmax (positive) + the
    # local_window inverted degrade tripwire (must be exactly 0). span_resolver is no longer a separate spec.
    prov = by_name["provenance_reanchor"]
    assert prov.exact_fields == (("local_window", "0"),)
    assert prov.flag_whitelist == ("1", "true", "yes", "on", "enabled")
    assert "span_resolver" not in by_name
    # cross_source_body keeps the anchor-equality degrade literal.
    assert by_name["cross_source_body"].absent_markers == ("[activation] cross_source_body: anchor_equality",)
    # strict-whitelist producers.
    assert by_name["expert_facet_planner"].flag_whitelist == ("1", "true")
    assert by_name["subentity_query_expansion"].flag_whitelist == ("1", "true")


def test_producer_literals_exist_in_source():
    """Guard against producer/canary drift: the exact positive-marker literals live in the U2 producers."""
    def _src(rel):
        return (_REPO_ROOT / rel).read_text(encoding="utf-8")
    assert "[activation] synth_primary: authored_prose kept=" in _src("src/polaris_graph/generator/verified_compose.py")
    assert "[activation] finding_dedup_nli: invoked directional_merges=" in _src("src/polaris_graph/synthesis/finding_dedup.py")
    assert "[activation] basket_consume_finding_dedup: regrouped old_to_new=" in _src("src/polaris_graph/synthesis/credibility_pass.py")
    cs = _src("src/polaris_graph/generator/cross_source_synthesis.py")
    assert "[activation] cross_source_body: plan_driven pairs=" in cs
    assert "[activation] cross_source_body: anchor_equality pairs=" in cs
    assert "[activation] numeric_comparator: upgraded=" in cs
    assert "[activation] two_sided_debate: leg2_inspected=" in _src("src/polaris_graph/generator/multi_section_generator.py")
    fs = _src("src/polaris_graph/retrieval/fs_researcher_query_gen.py")
    assert "[activation] expert_facet_planner: facets=" in fs
    assert "[activation] subentity_query_expansion: expanded_queries=" in fs
    launcher = _src("scripts/run_honest_sweep_r3.py")
    assert "[activation] min_cite_set: minimized=" in launcher
    # provenance_reanchor marker now carries local_window (Fable P0 option-B).
    assert "[activation] provenance_reanchor: accepted=" in launcher
    assert "local_window=%d" in launcher
    prov = _src("src/polaris_graph/generator/provenance_generator.py")
    assert '"reanchor_local_window_recovered"' in prov  # the option-B telemetry counter
    assert '_REANCHOR_TELEMETRY["reanchor_local_window_recovered"] += 1' in prov  # incremented at the leg


# ── smoke: the module + symbols import offline ───────────────────────────────────────────────────

def test_smoke_symbols_present():
    for name in (
        "_activation_canary_enabled",
        "_activation_flag_on",
        "assert_activation_markers_fired",
        "_run_activation_canary",
        "_ActivationMarkerCaptureHandler",
        "_ACTIVATION_CANARY_ENV",
        "_ACTIVATION_MARKER_PREFIX",
        "_ACTIVATION_MARKER_SPECS",
        "_ActivationMarkerSpec",
    ):
        assert hasattr(rg, name), f"run_gate_b is missing {name}"
    assert rg._ACTIVATION_CANARY_ENV == _FLAG
    # 10 specs (span-resolver folded into provenance_reanchor) == 10 self-scoping module flags.
    assert len(rg._ACTIVATION_MARKER_SPECS) == len(_MODULE_FLAGS) == 10
    # producer P1 helpers exist.
    for name in ("_reset_two_sided_debate_telemetry", "_accumulate_two_sided_debate", "_emit_two_sided_debate_run_summary"):
        assert hasattr(msg, name), f"multi_section_generator is missing {name}"
