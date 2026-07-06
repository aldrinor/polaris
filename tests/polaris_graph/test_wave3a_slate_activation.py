"""Wave-3a U4 (I-deepfix-001 #1344) — the QUAD activation of the deep-research CORE path on Gate-B.

This unit flips the 14 deep-research capability/dependency/canary flags ON in the full-capability
benchmark slate (+ a log-level observability pin). BEHAVIORAL, OFFLINE (no model / GPU / network /
spend): every assertion is over the slate CONSTANTS + the ``apply_full_capability_benchmark_slate``
env-force semantics. Importing ``run_gate_b`` is safe offline — its heavy imports (torch /
sentence-transformers / live_retriever) are lazy, inside function bodies.

Proves:
  (a) after ``apply_full_capability_benchmark_slate`` every one of the 14 flags is truthy in os.environ;
  (b) each is in ``_WINNER_FLAG_ALLOWLIST`` so the SLATE-PURITY gate does NOT RuntimeError — verified by
      replicating the gate's EXACT ``_force_on_to_check`` computation (run_gate_b.py ~4321-4343) over the
      whole slate. (The full ``preflight_full_capability`` cannot run in a hermetic unit: it asserts
      import-time module constants that are cached at their defaults before the slate is applied — an
      import-ORDER precondition a unit test cannot satisfy. The purity gate's logic is config-only and is
      reproduced here byte-for-byte.)
  (c) PG_SUBENTITY_QUERY_EXPANSION is now FORCE-on — a pre-set operator ``=0`` is overridden to ``1``
      (the conscious LAW VI policy flip; the ad-hoc setdefault was removed from the applier);
  (d) PG_PRESENTATION_TABLES is NOT forced on anywhere (2c-wiring deferred);
  (e) the FORCE is confined to the applier — merely importing / referencing the module does NOT mutate
      the env, so a non-benchmark invocation is byte-identical;
  plus the log-level pin, the QUAD structural membership, and the M6 dead-assertion literal fix.

§-1.3: every activated flag is a WEIGHT-and-CONSOLIDATE surface (cross-source body / numeric comparator /
provenance re-anchor / synth-primary / finding-dedup-NLI / min-cite-set keep-all / two-sided debate) or
its dependency / fail-loud detector / observability pin. NONE drops a source or adds a cap/target/thinner.
The FROZEN faithfulness engine (strict_verify / NLI / 4-role D8 / provenance / span-grounding) is untouched
— every surfaced / re-anchored / synthesized claim re-passes the UNCHANGED chokepoint.
"""

from __future__ import annotations

import inspect
from pathlib import Path

import pytest

import scripts.dr_benchmark.run_gate_b as gate_b

# The 14 boolean capability/dependency/canary flags this unit adds to ALL FOUR QUAD lists.
_QUAD14 = (
    # 7 dark capability modules
    "PG_CROSS_SOURCE_BODY",
    "PG_NUMERIC_COMPARATOR",
    "PG_PROVENANCE_REANCHOR",
    "PG_SYNTH_PRIMARY",
    "PG_FINDING_DEDUP_NLI",
    "PG_MIN_CITE_SET",
    "PG_TWO_SIDED_DEBATE",
    # promoted (was ad-hoc setdefault)
    "PG_SUBENTITY_QUERY_EXPANSION",
    # dependency flags (default-ON in code; forced so the parent never silently no-ops)
    "PG_CORROBORATION_LAYER2_CITE",
    "PG_CITATION_TWO_LAYER_POLICY",
    "PG_FINDING_DEDUP_QUALITATIVE",
    "PG_CONSOLIDATION_NLI_QUALITATIVE",
    # fail-loud detector canaries
    "PG_SHALLOW_REPORT_CANARY",
    "PG_ACTIVATION_CANARY",
)

# The log-level observability pin (force-EXACT "INFO" + allowlist, NOT force-on / NOT preflight-required).
_LOG_LEVEL_FLAG = "PG_LOG_LEVEL"

# Deferred — must NOT be forced on (2c-wiring not built).
_DEFERRED_FLAG = "PG_PRESENTATION_TABLES"


@pytest.fixture
def clean_env(monkeypatch):
    """Snapshot + fully restore os.environ so a test's ``apply_slate`` mutation never leaks.

    ``apply_full_capability_benchmark_slate`` writes ``os.environ[...]`` directly (not via monkeypatch),
    so monkeypatch alone would not revert it — snapshot the whole mapping and restore it verbatim.
    """
    import os

    saved = dict(os.environ)
    try:
        yield os.environ
    finally:
        os.environ.clear()
        os.environ.update(saved)


# ── (a) after apply_slate every QUAD-14 flag is truthy ────────────────────────────────────────────

def test_apply_slate_forces_all_14_flags_truthy(clean_env):
    import os

    for f in _QUAD14:
        os.environ.pop(f, None)  # start from unset
    gate_b.apply_full_capability_benchmark_slate(smoke_scale=False)
    for f in _QUAD14:
        assert os.environ.get(f) == "1", f"{f} not force-set to '1' by the slate (got {os.environ.get(f)!r})"


def test_apply_slate_pins_log_level_info(clean_env):
    import os

    os.environ[_LOG_LEVEL_FLAG] = "WARNING"  # hostile: operator raised the level (would suppress markers)
    gate_b.apply_full_capability_benchmark_slate(smoke_scale=False)
    assert os.environ[_LOG_LEVEL_FLAG] == "INFO", (
        "PG_LOG_LEVEL must be force-EXACT 'INFO' so the [activation] INFO markers the activation canary "
        "parses are never suppressed on the benchmark run"
    )


# ── (b) SLATE-PURITY: no un-allowlisted force flag → the gate does not RuntimeError ────────────────

def _slate_purity_force_flags_to_check() -> set[str]:
    """Reproduce EXACTLY the SLATE-PURITY gate's ``_force_on_to_check`` set (run_gate_b.py ~4321-4343):
    every FORCE_ON flag + every force-EXACT flag whose slate value is an ON-token or a non-empty,
    non-falsy, NON-NUMERIC string. Falsy ("0"/"") and numeric-string force-EXACT values are not
    winner-checked. Any member NOT in ``_WINNER_FLAG_ALLOWLIST`` makes the gate raise RuntimeError."""
    on_tokens = ("1", "true", "yes", "on")

    def is_off(v: str) -> bool:
        return v.strip().lower() in ("", "0", "false", "no", "off")

    slate = gate_b._FULL_CAPABILITY_BENCHMARK_SLATE
    check = set(gate_b._BENCHMARK_FORCE_ON_FLAGS)
    for fe in gate_b._BENCHMARK_FORCE_EXACT_FLAGS:
        val = str(slate.get(fe, "")).strip()
        if is_off(val):
            continue
        if val.lower() in on_tokens:
            check.add(fe)
            continue
        try:
            float(val)
            continue
        except ValueError:
            check.add(fe)
    return check


def test_slate_purity_gate_passes_no_unallowlisted_force_flag():
    unallowlisted = sorted(
        f for f in _slate_purity_force_flags_to_check() if f not in gate_b._WINNER_FLAG_ALLOWLIST
    )
    assert not unallowlisted, (
        "SLATE-PURITY would RuntimeError: these force-on / force-EXACT flags map to no allowlist entry: "
        f"{unallowlisted}"
    )


def test_all_14_and_log_level_are_allowlisted():
    for f in _QUAD14 + (_LOG_LEVEL_FLAG,):
        assert f in gate_b._WINNER_FLAG_ALLOWLIST, f"{f} missing from _WINNER_FLAG_ALLOWLIST (SLATE-PURITY)"


# ── QUAD structural membership (the four-list activation contract) ─────────────────────────────────

def test_14_flags_are_full_quad_members():
    slate = gate_b._FULL_CAPABILITY_BENCHMARK_SLATE
    req = set(gate_b._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS)
    for f in _QUAD14:
        assert slate.get(f) == "1", f"{f} not slate '1'"
        assert f in gate_b._BENCHMARK_FORCE_ON_FLAGS, f"{f} not in _BENCHMARK_FORCE_ON_FLAGS"
        assert f in req, f"{f} not in _BENCHMARK_PREFLIGHT_REQUIRED_FLAGS"
        assert f in gate_b._WINNER_FLAG_ALLOWLIST, f"{f} not in _WINNER_FLAG_ALLOWLIST"
        assert f not in gate_b._BENCHMARK_FORCE_EXACT_FLAGS, f"{f} should not be force-EXACT"


def test_log_level_is_force_exact_slate_allowlist_only():
    slate = gate_b._FULL_CAPABILITY_BENCHMARK_SLATE
    assert slate.get(_LOG_LEVEL_FLAG) == "INFO"
    assert _LOG_LEVEL_FLAG in gate_b._BENCHMARK_FORCE_EXACT_FLAGS
    assert _LOG_LEVEL_FLAG in gate_b._WINNER_FLAG_ALLOWLIST
    # NOT a capability enable: not force-on, not preflight-required-truthy.
    assert _LOG_LEVEL_FLAG not in gate_b._BENCHMARK_FORCE_ON_FLAGS
    assert _LOG_LEVEL_FLAG not in set(gate_b._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS)


# ── (c) PG_SUBENTITY_QUERY_EXPANSION promoted from setdefault to FORCE-on ──────────────────────────

def test_subentity_is_force_on_overriding_operator_zero(clean_env):
    import os

    os.environ["PG_SUBENTITY_QUERY_EXPANSION"] = "0"  # operator tried to disable it (LAW VI old behavior)
    gate_b.apply_full_capability_benchmark_slate(smoke_scale=False)
    assert os.environ["PG_SUBENTITY_QUERY_EXPANSION"] == "1", (
        "PG_SUBENTITY_QUERY_EXPANSION must be FORCE-on now (promoted from setdefault): a pre-set "
        "operator =0 must be overridden to 1"
    )


def test_subentity_setdefault_removed_from_applier():
    """The ad-hoc ``os.environ.setdefault("PG_SUBENTITY_QUERY_EXPANSION", ...)`` executable statement is
    GONE from the applier (the flag is a QUAD winner now). A comment may still reference the old call."""
    src = inspect.getsource(gate_b.apply_full_capability_benchmark_slate)
    exec_setdefaults = [
        ln for ln in src.splitlines()
        if ln.lstrip().startswith('os.environ.setdefault("PG_SUBENTITY_QUERY_EXPANSION"')
    ]
    assert not exec_setdefaults, f"executable setdefault still present: {exec_setdefaults}"
    # The unrelated setdefaults (mineru / deepener / subtopic) are untouched by this unit.
    assert 'os.environ.setdefault("PG_SWEEP_EVIDENCE_DEEPENER"' in src
    assert 'os.environ.setdefault("PG_SUBTOPIC_ADDITIVE_FACTS"' in src


# ── (d) PG_PRESENTATION_TABLES is NOT forced on (deferred) ─────────────────────────────────────────

def test_presentation_tables_not_forced_anywhere():
    for coll in (
        gate_b._FULL_CAPABILITY_BENCHMARK_SLATE,
        gate_b._BENCHMARK_FORCE_ON_FLAGS,
        set(gate_b._BENCHMARK_PREFLIGHT_REQUIRED_FLAGS),
        gate_b._BENCHMARK_FORCE_EXACT_FLAGS,
        gate_b._WINNER_FLAG_ALLOWLIST,
    ):
        assert _DEFERRED_FLAG not in coll, f"{_DEFERRED_FLAG} must stay deferred (2c-wiring not built)"


# ── (e) the FORCE is confined to the applier — non-benchmark invocation is byte-identical ──────────

def test_force_is_confined_to_applier_not_module_import(clean_env):
    """Merely referencing the module (never calling the applier) does NOT mutate os.environ, so a
    non-benchmark / unit-test invocation is byte-identical. The hostile operator values SURVIVE until
    the applier is explicitly invoked."""
    import os

    for f in _QUAD14:
        os.environ.pop(f, None)
    os.environ["PG_CROSS_SOURCE_BODY"] = "0"   # operator OFF must survive when the applier is not run
    before = dict(os.environ)
    # Touch the module constants (the QUAD lists) — pure reads must not force anything.
    _ = gate_b._FULL_CAPABILITY_BENCHMARK_SLATE, gate_b._BENCHMARK_FORCE_ON_FLAGS
    _ = gate_b._WINNER_FLAG_ALLOWLIST, gate_b._BENCHMARK_FORCE_EXACT_FLAGS
    assert dict(os.environ) == before, "referencing the slate constants mutated os.environ (should be inert)"
    assert os.environ["PG_CROSS_SOURCE_BODY"] == "0", "operator OFF was forced without invoking the applier"
    assert "PG_SYNTH_PRIMARY" not in os.environ, "an unset flag became set without invoking the applier"


# ── M6 dead-assertion literal fix (marker now matches the producer's emitted text) ────────────────

def test_m6_silent_noop_marker_matches_producer_text():
    """The M6 silent-no-op marker literal was 'anchored ...' but the producer emits 'candidate ...'
    (cross_source_synthesis.py:802), so the assertion never fired. It is now 'candidate ...' — a genuine
    substring of the producer's format string, so ``assert_cross_source_synthesis_fired`` can fire."""
    assert gate_b._CROSS_SOURCE_SILENT_NOOP_MARKER == (
        "candidate cross-source pair(s) but 0 analytical units survived"
    )
    producer = (
        Path(__file__).resolve().parents[2]
        / "src" / "polaris_graph" / "generator" / "cross_source_synthesis.py"
    ).read_text(encoding="utf-8")
    assert gate_b._CROSS_SOURCE_SILENT_NOOP_MARKER in producer, (
        "the M6 marker must be a substring of the producer's emitted log line so the silent-no-op "
        "assertion can actually match"
    )
