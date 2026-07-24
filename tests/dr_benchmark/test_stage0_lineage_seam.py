"""STAGE-0 LINEAGE SEAM — deterministic ship-decision tests (NO generation / scoring spend).

Covers the ~9 seams of the ``PG_BENCHMARK_QUESTION_LINEAGE`` selector:
  * default off-state GOLDEN identity: with the selector unset / ``drb_ii_idx`` the resolver,
    output-contract, snapshot, manifest, and coverage-gate severity are byte/behavior identical to
    HEAD (and the default path never reads the legacy ``query.jsonl``);
  * legacy: the answered question resolves to ``query.jsonl`` id=72 at every seam; the output
    contract is ``None``; the coverage gate is non-fatal; the snapshot carries the lineage field;
  * the split-brain guard still FAILS LOUD on a deliberate packed/answered mismatch (raw + sha256);
  * unregistered-slug + legacy/slug-with-no-mapping FAIL LOUD.

All hermetic: synthetic tasks files, no network, no LLM. The selector is a keyword/env value only.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.dr_benchmark import gate0_lineage as g

# The real legacy tasks file (query.jsonl) resolved through the third_party symlink. Used to assert
# the legacy resolver returns the SAME record score_report_race.py --task-id 72 scores against.
_REAL_LEGACY_QUERY_JSONL = g.DEFAULT_LEGACY_TASKS_PATH


def _write_jsonl(path: Path, records: list[dict]) -> str:
    path.write_text("".join(json.dumps(r) + "\n" for r in records), encoding="utf-8")
    return str(path)


@pytest.fixture(autouse=True)
def _clear_selector(monkeypatch):
    """Every test starts with the selector UNSET (the default off-state)."""
    monkeypatch.delenv(g.LINEAGE_SELECTOR_ENV, raising=False)
    yield


# ─────────────────────────────────────────────────────────────────────────────
# resolve_lineage / lineage_from_env
# ─────────────────────────────────────────────────────────────────────────────
def test_resolve_lineage_default_and_allowlist():
    assert g.resolve_lineage(None) == g.LINEAGE_DRB_II_IDX
    assert g.resolve_lineage("") == g.LINEAGE_DRB_II_IDX
    assert g.resolve_lineage("  ") == g.LINEAGE_DRB_II_IDX
    assert g.resolve_lineage(g.LINEAGE_LEGACY_RACE_TASK) == g.LINEAGE_LEGACY_RACE_TASK


def test_resolve_lineage_unknown_fails_loud():
    with pytest.raises(g.GateZeroLineageError):
        g.resolve_lineage("legacy")  # near-miss typo must NOT silently pass


def test_lineage_from_env_default_and_legacy(monkeypatch):
    assert g.lineage_from_env() == g.LINEAGE_DRB_II_IDX  # unset default
    monkeypatch.setenv(g.LINEAGE_SELECTOR_ENV, g.LINEAGE_LEGACY_RACE_TASK)
    assert g.lineage_from_env() == g.LINEAGE_LEGACY_RACE_TASK
    monkeypatch.setenv(g.LINEAGE_SELECTOR_ENV, "bogus")
    with pytest.raises(g.GateZeroLineageError):
        g.lineage_from_env()


# ─────────────────────────────────────────────────────────────────────────────
# Seam 1: canonical resolver — default vs legacy; NO legacy read on default
# ─────────────────────────────────────────────────────────────────────────────
def test_legacy_resolver_returns_query_jsonl_id72():
    """Legacy resolves the drb_72_ai_labor slug to the query.jsonl id=72 prompt (the RACE task)."""
    q = g.canonical_question_for_slug(
        "drb_72_ai_labor", lineage=g.LINEAGE_LEGACY_RACE_TASK
    )
    # Independently read query.jsonl id=72 and compare sha (the score_report_race.py contract).
    with open(_REAL_LEGACY_QUERY_JSONL, encoding="utf-8") as fh:
        want = next(
            json.loads(l)["prompt"]
            for l in fh
            if l.strip() and json.loads(l).get("id") == 72
        )
    assert g.sha256_text(q) == g.sha256_text(want)


def test_default_path_does_not_read_legacy_query_jsonl(tmp_path, monkeypatch):
    """GOLDEN: on the default lineage the resolver reads the DRB-II tasks file, NEVER query.jsonl."""
    drb = _write_jsonl(tmp_path / "drb.jsonl", [{"idx": 56, "prompt": "DRB-II canonical"}])
    reads: list[str] = []
    real_open = open

    def _tracking_open(file, *a, **k):  # record every path opened
        reads.append(str(file))
        return real_open(file, *a, **k)

    monkeypatch.setattr("builtins.open", _tracking_open)
    out = g.canonical_question_for_slug("drb_72_ai_labor", tasks_path=drb)
    assert out == "DRB-II canonical"
    assert drb in reads
    assert not any("query.jsonl" in r for r in reads), "default path must not read query.jsonl"


def test_legacy_slug_with_no_mapping_fails_loud():
    """A legacy/slug pair with no SLUG_TO_LEGACY_TASK entry FAILS LOUD (never a guessed id)."""
    with pytest.raises(g.GateZeroLineageError):
        g.canonical_question_for_slug(
            "drb_75_metal_ions_cvd", lineage=g.LINEAGE_LEGACY_RACE_TASK
        )


def test_legacy_missing_file_and_missing_id_fail_loud(tmp_path):
    with pytest.raises(g.GateZeroLineageError):
        g.load_legacy_task_question(72, legacy_tasks_path=str(tmp_path / "absent.jsonl"))
    present = _write_jsonl(tmp_path / "leg.jsonl", [{"id": 99, "prompt": "other"}])
    with pytest.raises(g.GateZeroLineageError):
        g.load_legacy_task_question(72, legacy_tasks_path=present)


def test_positional_signature_still_valid(tmp_path):
    """Positional (slug, tasks_path) must remain a valid default-lineage call (back-compat)."""
    drb = _write_jsonl(tmp_path / "drb.jsonl", [{"idx": 56, "prompt": "DRB-II canonical"}])
    assert g.canonical_question_for_slug("drb_72_ai_labor", drb) == "DRB-II canonical"


# ─────────────────────────────────────────────────────────────────────────────
# Seam 1: manifest — default byte-identity + legacy label (never canonical_idx=56)
# ─────────────────────────────────────────────────────────────────────────────
def _manifest(tmp_path, *, lineage, question):
    drb = _write_jsonl(tmp_path / "drb.jsonl", [{"idx": 56, "prompt": "DRB-II Q"}])
    leg = _write_jsonl(tmp_path / "leg.jsonl", [{"id": 72, "prompt": "LEGACY Q"}])
    return g.build_lineage_manifest(
        slug="drb_72_ai_labor",
        launched_question=question,
        packed_question=question,
        answered_question=question,
        rendered_report="report",
        judge_input="judge",
        score_row={"overall": 0.5},
        backbone_model="m",
        decoding_params={"temperature": 0},
        prompt_template_id="pt",
        retrieval_snapshot_id="rs",
        judge_model_version="jv",
        scorer_config_id="sc",
        execution_seed=0,
        tasks_path=drb,
        legacy_tasks_path=leg,
        lineage=lineage,
    )


def test_manifest_default_is_head_shape(tmp_path):
    m = _manifest(tmp_path, lineage=g.LINEAGE_DRB_II_IDX, question="DRB-II Q")
    # HEAD shape: slug, canonical_idx, canonical_question_sha, ... — NO lineage key on default.
    assert list(m)[:3] == ["slug", "canonical_idx", "canonical_question_sha"]
    assert "lineage" not in m
    assert m["canonical_idx"] == 56


def test_manifest_legacy_never_labels_canonical_idx_56(tmp_path):
    m = _manifest(tmp_path, lineage=g.LINEAGE_LEGACY_RACE_TASK, question="LEGACY Q")
    assert m["lineage"] == g.LINEAGE_LEGACY_RACE_TASK
    assert m["legacy_task_id"] == 72
    assert "canonical_idx" not in m  # a legacy run is NEVER labelled the DRB-II idx


# ─────────────────────────────────────────────────────────────────────────────
# Split-brain guard — still FAILS LOUD on a deliberate mismatch (raw + sha256)
# ─────────────────────────────────────────────────────────────────────────────
def test_split_brain_guard_fails_loud_default(tmp_path):
    drb = _write_jsonl(tmp_path / "drb.jsonl", [{"idx": 56, "prompt": "DRB-II Q"}])
    # packed matches, answered drifts -> loud fail (sha inequality)
    with pytest.raises(g.GateZeroLineageError):
        g.assert_no_split_brain(
            "drb_72_ai_labor", "DRB-II Q", "a DIFFERENT answer", tasks_path=drb
        )
    # both match -> passes
    g.assert_no_split_brain("drb_72_ai_labor", "DRB-II Q", "DRB-II Q", tasks_path=drb)


def test_split_brain_guard_fails_loud_legacy(tmp_path):
    leg = _write_jsonl(tmp_path / "leg.jsonl", [{"id": 72, "prompt": "LEGACY Q"}])
    with pytest.raises(g.GateZeroLineageError):
        g.assert_no_split_brain(
            "drb_72_ai_labor",
            "LEGACY Q",
            "wrong answer",
            lineage=g.LINEAGE_LEGACY_RACE_TASK,
            legacy_tasks_path=leg,
        )
    g.assert_no_split_brain(
        "drb_72_ai_labor",
        "LEGACY Q",
        "LEGACY Q",
        lineage=g.LINEAGE_LEGACY_RACE_TASK,
        legacy_tasks_path=leg,
    )


def test_questions_raw_and_sha_equal_requires_both(tmp_path):
    """The strict RAW gate: raw-byte identity AND normalized-SHA equality — BOTH required.

    A SHA-only check accepts whitespace drift; ``questions_raw_and_sha_equal`` must NOT. Identical
    bytes pass; any whitespace difference (even one the normalized SHA would call equal) fails.
    """
    # RAW-equal (same bytes) => True, and the sha necessarily matches too.
    assert g.questions_raw_and_sha_equal("LEGACY Q", "LEGACY Q") is True
    assert g.sha256_text("LEGACY Q") == g.sha256_text("LEGACY Q")  # sha half holds on identity
    # SHA-equal-but-raw-DIFFERENT (whitespace drift) => the strict gate REJECTS it.
    assert g.sha256_text("LEGACY   Q") == g.sha256_text("LEGACY Q")  # sha alone would pass
    assert g.questions_raw_and_sha_equal("LEGACY   Q", "LEGACY Q") is False  # raw gate refuses
    assert g.questions_raw_and_sha_equal("LEGACY\nQ", "LEGACY Q") is False


def test_split_brain_guard_rejects_whitespace_drift(tmp_path):
    """v2 raw-byte gate: layout-only whitespace drift IS now a split brain (raw AND sha required).

    Replaces the prior test that ACCEPTED "LEGACY   Q"/"LEGACY Q"/"LEGACY\\nQ" as equal — Sol item
    3: the split-brain guard must assert RAW-byte equality, not just the whitespace-normalized SHA.
    """
    leg = _write_jsonl(tmp_path / "leg.jsonl", [{"id": 72, "prompt": "LEGACY   Q"}])
    # packed/answered differ from the canonical only by whitespace -> raw gate FAILS LOUD.
    with pytest.raises(g.GateZeroLineageError):
        g.assert_no_split_brain(
            "drb_72_ai_labor",
            "LEGACY Q",
            "LEGACY\nQ",
            lineage=g.LINEAGE_LEGACY_RACE_TASK,
            legacy_tasks_path=leg,
        )
    # RAW-byte-identical to the canonical -> passes (raw AND sha both hold).
    g.assert_no_split_brain(
        "drb_72_ai_labor",
        "LEGACY   Q",
        "LEGACY   Q",
        lineage=g.LINEAGE_LEGACY_RACE_TASK,
        legacy_tasks_path=leg,
    )


# ─────────────────────────────────────────────────────────────────────────────
# Seam 5: output-contract lineage gate (single gate, all 3 consumers)
# ─────────────────────────────────────────────────────────────────────────────
def test_output_contract_legacy_is_none_default_unchanged(monkeypatch):
    from scripts.dr_benchmark import run_validity_gate as v

    monkeypatch.delenv(g.LINEAGE_SELECTOR_ENV, raising=False)
    default = v.load_task_output_contract("drb_72_ai_labor")
    # default resolves the real contract (present in task_output_contracts.yaml for this slug)
    assert default is not None
    monkeypatch.setenv(g.LINEAGE_SELECTOR_ENV, g.LINEAGE_LEGACY_RACE_TASK)
    assert v.load_task_output_contract("drb_72_ai_labor") is None


# ─────────────────────────────────────────────────────────────────────────────
# Seam 6: corpus_snapshot lineage field + resume rejection
# ─────────────────────────────────────────────────────────────────────────────
class _StubRetrieval:
    classified_sources: list = []
    evidence_rows: list = []
    notes: list = []
    api_calls: dict = {}


def _save(tmp_path, *, lineage):
    from src.polaris_graph.generator import corpus_snapshot as cs

    return cs.save_corpus_snapshot(
        tmp_path,
        run_id="r",
        question="Q",
        slug="drb_72_ai_labor",
        domain="dom",
        evidence_for_gen=[{"id": "e1", "text": "x"}],
        retrieval=_StubRetrieval(),
        lineage=lineage,
    )


def test_snapshot_default_omits_lineage_field(tmp_path):
    _save(tmp_path, lineage=None)
    payload = json.loads((tmp_path / "corpus_snapshot.json").read_text())
    assert "lineage" not in payload  # default JSON byte-identical to HEAD


def test_snapshot_legacy_stores_lineage_field(tmp_path):
    _save(tmp_path, lineage=g.LINEAGE_LEGACY_RACE_TASK)
    payload = json.loads((tmp_path / "corpus_snapshot.json").read_text())
    assert payload["lineage"] == g.LINEAGE_LEGACY_RACE_TASK


def test_snapshot_resume_rejects_mismatched_lineage(tmp_path):
    from src.polaris_graph.generator import corpus_snapshot as cs

    # default (no-check) resume of any snapshot always loads
    _save(tmp_path, lineage=None)
    cs.load_corpus_snapshot(tmp_path)  # no expected -> byte-identical no-op
    cs.load_corpus_snapshot(tmp_path, expected_lineage=None)
    # a default snapshot under an expected LEGACY resume is rejected (missing field => drb_ii_idx)
    with pytest.raises(cs.CorpusSnapshotError):
        cs.load_corpus_snapshot(tmp_path, expected_lineage=g.LINEAGE_LEGACY_RACE_TASK)


def test_snapshot_resume_legacy_matches_and_cross_rejects(tmp_path):
    from src.polaris_graph.generator import corpus_snapshot as cs

    _save(tmp_path, lineage=g.LINEAGE_LEGACY_RACE_TASK)
    cs.load_corpus_snapshot(tmp_path, expected_lineage=g.LINEAGE_LEGACY_RACE_TASK)  # match OK
    with pytest.raises(cs.CorpusSnapshotError):
        cs.load_corpus_snapshot(tmp_path, expected_lineage=g.LINEAGE_DRB_II_IDX)


# FIX 4 / FIX D: the PRODUCTION resume seam resolves an ABSENT q marker to the effective drb_ii_idx
# lineage so BOTH mismatch directions are enforced. Sol §4: the earlier caller-level tests defined a
# LOCAL mirror of the resolution and never exercised production, so a regression to a bare q.get()
# would leave them green. These tests now drive the SAME production helper the resume caller calls
# (`run_honest_sweep_r3._resume_effective_lineage`) — a regression to bare q.get() breaks them.
def _seam_expected_lineage(q_marker):
    """Drive the PRODUCTION resume-caller helper on a q built from the marker (NOT a local mirror)."""
    from scripts.run_honest_sweep_r3 import _resume_effective_lineage

    q = {} if q_marker is None else {"question_lineage": q_marker}
    return _resume_effective_lineage(q)


def test_resume_effective_lineage_production_helper_resolves():
    """FIX D: the production helper resolves an absent marker to drb_ii_idx and a legacy marker to
    legacy_race_task (and fails loud on a bogus marker, never a silent default)."""
    from scripts.run_honest_sweep_r3 import _resume_effective_lineage

    assert _resume_effective_lineage({}) == g.LINEAGE_DRB_II_IDX  # no marker => default
    assert _resume_effective_lineage(None) == g.LINEAGE_DRB_II_IDX  # non-dict q => default
    assert (
        _resume_effective_lineage({"question_lineage": g.LINEAGE_LEGACY_RACE_TASK})
        == g.LINEAGE_LEGACY_RACE_TASK
    )
    with pytest.raises(g.GateZeroLineageError):
        _resume_effective_lineage({"question_lineage": "bogus"})


def test_resume_seam_default_run_rejects_stored_legacy(tmp_path):
    """legacy-stored -> DEFAULT-run (the direction the bare q.get() missed): the PRODUCTION helper
    resolves the absent marker to drb_ii_idx and the loader REJECTS a stored legacy snapshot."""
    from src.polaris_graph.generator import corpus_snapshot as cs

    _save(tmp_path, lineage=g.LINEAGE_LEGACY_RACE_TASK)  # a LEGACY snapshot on disk
    # A DEFAULT run has NO question_lineage marker on q -> resolve to drb_ii_idx -> mismatch.
    expected = _seam_expected_lineage(None)
    assert expected == g.LINEAGE_DRB_II_IDX
    with pytest.raises(cs.CorpusSnapshotError):
        cs.load_corpus_snapshot(tmp_path, expected_lineage=expected)


def test_resume_seam_legacy_run_rejects_stored_default(tmp_path):
    """default-stored -> LEGACY-run: the PRODUCTION helper resolves the legacy marker and the loader
    REJECTS a stored default snapshot (missing field => drb_ii_idx)."""
    from src.polaris_graph.generator import corpus_snapshot as cs

    _save(tmp_path, lineage=None)  # a DEFAULT snapshot on disk (no lineage field)
    expected = _seam_expected_lineage(g.LINEAGE_LEGACY_RACE_TASK)
    assert expected == g.LINEAGE_LEGACY_RACE_TASK
    with pytest.raises(cs.CorpusSnapshotError):
        cs.load_corpus_snapshot(tmp_path, expected_lineage=expected)


def test_resume_seam_matching_lineages_load(tmp_path):
    """Both matching directions load: default-stored+default-run, legacy-stored+legacy-run — through
    the PRODUCTION helper."""
    from src.polaris_graph.generator import corpus_snapshot as cs

    _save(tmp_path, lineage=None)
    cs.load_corpus_snapshot(tmp_path, expected_lineage=_seam_expected_lineage(None))
    _save(tmp_path, lineage=g.LINEAGE_LEGACY_RACE_TASK)
    cs.load_corpus_snapshot(
        tmp_path, expected_lineage=_seam_expected_lineage(g.LINEAGE_LEGACY_RACE_TASK)
    )


def test_run_one_query_resume_load_uses_effective_lineage_helper():
    """FIX D caller-coupling (Sol re-gate #2 §5): the resume tests above drive the production helper
    directly, but a regression in ``run_one_query`` from
    ``expected_lineage=_resume_effective_lineage(q)`` back to a bare ``expected_lineage=q.get(...)``
    would leave them green. Behavioral coverage would require running the async producer path (not
    hermetic without generation spend), so this is Sol's "at minimum" focused STRUCTURAL assertion on
    the real call site: the ``run_one_query`` corpus-snapshot load passes ``_resume_effective_lineage``
    (applied to the loop var ``q``) as ``expected_lineage`` — and NOT a bare ``q.get(...)``."""
    import ast
    import inspect

    from scripts import run_honest_sweep_r3 as sweep

    tree = ast.parse(inspect.getsource(sweep))
    fn = next(
        (
            n
            for n in ast.walk(tree)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
            and n.name == "run_one_query"
        ),
        None,
    )
    assert fn is not None, "run_one_query not found in run_honest_sweep_r3"

    # Every call inside run_one_query loading a corpus snapshot must supply expected_lineage via the
    # production resolver, never a raw q.get(). (Import is aliased to _load_corpus_snapshot.)
    loader_names = {"_load_corpus_snapshot", "load_corpus_snapshot"}
    checked = 0
    for call in (n for n in ast.walk(fn) if isinstance(n, ast.Call)):
        callee = call.func.id if isinstance(call.func, ast.Name) else None
        if callee not in loader_names:
            continue
        kw = next((k for k in call.keywords if k.arg == "expected_lineage"), None)
        assert kw is not None, f"{callee} call missing expected_lineage keyword"
        val = kw.value
        # It must be _resume_effective_lineage(q) — the ONE production resolver, applied to q.
        assert isinstance(val, ast.Call) and isinstance(val.func, ast.Name), (
            "expected_lineage must be a direct call to the production resolver"
        )
        assert val.func.id == "_resume_effective_lineage", (
            "expected_lineage must call _resume_effective_lineage, not a bare q.get() "
            f"(found {ast.dump(val.func)})"
        )
        assert (
            len(val.args) == 1
            and isinstance(val.args[0], ast.Name)
            and val.args[0].id == "q"
        ), "expected_lineage must be _resume_effective_lineage(q)"
        checked += 1
    assert checked >= 1, "no corpus-snapshot load found in run_one_query resume path"


# ─────────────────────────────────────────────────────────────────────────────
# Seam 9 (FIX 3): the RIGHT predicate. A RequiredEntityLedger IMPLEMENTATION failure stays
# FAIL-LOUD under EVERY lineage (F27, lineage-INDEPENDENT); ONLY the native coverage-SHORTFALL
# blocker is report-only for legacy at the outer disposition seam.
# ─────────────────────────────────────────────────────────────────────────────
def test_required_entity_ledger_failure_is_lineage_independent(monkeypatch):
    """F27: a ledger IMPLEMENTATION exception (build/render/write) must FAIL LOUD under legacy too —
    it is NOT the coverage-shortfall decision. Reverting the prior wrong legacy early-return: this
    predicate is byte-identical to HEAD (lineage-independent)."""
    from scripts.run_honest_sweep_r3 import _required_entity_ledger_failed_under_strict as f

    monkeypatch.delenv(g.LINEAGE_SELECTOR_ENV, raising=False)
    # DEFAULT: strict + forced-on + failed => HOLD fires (byte-identical to HEAD)
    assert f(True, True, True) is True
    assert f(False, True, True) is False  # off => no hold (unchanged)
    assert f(True, True, False) is False  # ledger succeeded => no hold
    # LEGACY: the ledger-IMPLEMENTATION-failure HOLD STILL fires (must stay fail-loud/disclosed).
    monkeypatch.setenv(g.LINEAGE_SELECTOR_ENV, g.LINEAGE_LEGACY_RACE_TASK)
    assert f(True, True, True) is True


def test_legacy_coverage_shortfall_only_downgrade_predicate():
    """FIX 3 disposition predicate: ONLY a coverage-shortfall-ONLY hold is report-only for legacy.

    Set-EQUALITY (not "contains"): a fabrication / S0 / pending-rewrite hold, alone OR combined with
    coverage, is NEVER downgraded; a latched fabrication is never downgraded regardless of reasons.
    Behavioral proof that the default fixed-denominator BLOCK is preserved and legacy retains the
    coverage telemetry but does not abort for that reason alone.
    """
    from scripts.run_honest_sweep_r3 import _legacy_coverage_shortfall_report_only as dg
    from src.polaris_graph.roles.release_policy import (
        _REASON_FABRICATED_OCCURRENCE as R_FAB,
        _REASON_PENDING_REWRITE as R_REWRITE,
        _REASON_UNSUPPORTED_RESIDUAL_BELOW_COVERAGE as R_COV,
    )

    # coverage-shortfall ALONE, no fabrication => downgradeable (report-only for legacy).
    assert dg([R_COV], False) is True
    # coverage + ANY other blocker => NOT downgradeable (the other blocker still holds).
    assert dg([R_COV, R_REWRITE], False) is False
    assert dg([R_COV, "d8_s0_must_cover_missing:safety"], False) is False
    assert dg([R_COV, R_FAB], False) is False
    # non-coverage hold alone => NOT downgradeable.
    assert dg([R_REWRITE], False) is False
    assert dg(["d8_s0_must_cover_missing:safety"], False) is False
    # a latched FABRICATED occurrence is NEVER downgraded, even if held_reasons look coverage-only.
    assert dg([R_COV], True) is False
    # empty / no hold => nothing to downgrade.
    assert dg([], False) is False
    assert dg(None, False) is False


# ─────────────────────────────────────────────────────────────────────────────
# Seam 9 (FIX A + FIX B): DISPOSITION-LEVEL behavioral test. Drives ACTUAL native
# `compute_release_outcome` results (real zero-grounding hard_block / safety terminals) through the
# PRODUCTION outer disposition helper `_legacy_coverage_downgrade_applies` — proving:
#   (i)   DEFAULT lineage never downgrades (blocks as before);
#   (ii)  a MARKED-legacy coverage-shortfall-ONLY, non-hard-blocked HOLD downgrades to
#         released_with_disclosed_gaps with the coverage telemetry PRESERVED;
#   (iii) fabrication-latch, S0-must-cover, pending-rewrite, ZERO-GROUNDING (hard_block), and
#         safety/insufficient terminals NEVER downgrade (stay blocked / keep their own status);
#   (iv)  a NON-legacy-marked query with the selector set does NOT downgrade.
# These call the REAL release_policy to produce outcomes and the REAL production disposition, so the
# zero-grounding release bug (predicate-only test could not see it) is now covered.
# ─────────────────────────────────────────────────────────────────────────────
def _native_outcome(
    *,
    held_reasons,
    fabricated_latched=False,
    zero_verified=False,
    zero_usable_evidence=False,
    safety_floor_insufficient=False,
    release_allowed=False,
    always_release=False,
):
    """Produce an ACTUAL ReleaseOutcome via the real compute_release_outcome. Default is the
    always-release-OFF (legacy Gate-B) path the FIX-3 downgrade closes; the insufficient-safety
    RELEASED terminal only exists on the ON path, so that sub-case drives always_release=True. No
    stubbing of the outcome fields."""
    from src.polaris_graph.roles.release_policy import (
        ReleaseDecision,
        compute_release_outcome,
    )

    decision = ReleaseDecision(
        release_allowed=release_allowed,
        held_reasons=list(held_reasons),
        gaps=[],
        needs_rewrite=[],
        fabricated_occurrence_latched=fabricated_latched,
    )
    return compute_release_outcome(
        decision,
        zero_verified=zero_verified,
        zero_usable_evidence=zero_usable_evidence,
        safety_floor_insufficient=safety_floor_insufficient,
        coverage_fraction=0.4,
        always_release=always_release,
        redaction_active=False,  # keep a fabricated latch a HARD block (worst case for the guard)
    )


def _seam_disposition(outcome, marker, held_reasons, fabricated_latched):
    """Drive the ACTUAL production mutation ``_apply_legacy_coverage_downgrade`` (the ONE helper
    ``run_one_query`` calls at this seam) — NOT a test-side replay. Sol re-gate #2 §4 FIX C: a
    regression in the real caller (wrong helper arg, omitted manifest["release_allowed"], lost
    telemetry) now fails these tests because they exercise the same production code. Returns
    (release_allowed, summary_status, manifest) so telemetry preservation can be asserted."""
    from scripts.run_honest_sweep_r3 import _apply_legacy_coverage_downgrade

    # The caller's always-release-OFF status derivation feeds the SAME arguments run_one_query passes.
    summary_status = outcome.status
    manifest = {"release_allowed": outcome.released}
    summary_status = _apply_legacy_coverage_downgrade(
        manifest,
        summary_status,
        marker,
        bool(getattr(outcome, "released", False)),
        bool(getattr(outcome, "hard_block", False)),
        list(getattr(outcome, "hard_block_reasons", []) or []),
        held_reasons,
        fabricated_latched,
        log=None,
    )
    # Coverage telemetry (written unchanged AFTER the downgrade at the real seam) — preservation check.
    manifest["four_role_evaluation"] = {
        "coverage_fraction": round(outcome.release_quality_score, 3),
        "held_reasons": list(held_reasons),
    }
    return manifest["release_allowed"], summary_status, manifest


def test_disposition_coverage_only_default_blocks_legacy_downgrades(monkeypatch):
    from src.polaris_graph.roles.release_policy import (
        _REASON_UNSUPPORTED_RESIDUAL_BELOW_COVERAGE as R_COV,
        STATUS_ABORT_FOUR_ROLE_HELD,
    )

    held = [R_COV]
    outcome = _native_outcome(held_reasons=held)  # a real coverage-only HOLD
    assert outcome.released is False and outcome.hard_block is False
    assert outcome.status == STATUS_ABORT_FOUR_ROLE_HELD

    # (i) DEFAULT lineage (no marker) BLOCKS as before — release stays False.
    allowed, status, _ = _seam_disposition(outcome, None, held, False)
    assert allowed is False
    assert status == STATUS_ABORT_FOUR_ROLE_HELD

    # (ii) MARKED-legacy coverage-only hold DOWNGRADES with telemetry PRESERVED.
    allowed, status, manifest = _seam_disposition(
        outcome, g.LINEAGE_LEGACY_RACE_TASK, held, False
    )
    assert allowed is True
    assert status == "released_with_disclosed_gaps"
    assert manifest["legacy_coverage_shortfall_report_only"] is True
    assert R_COV in manifest["disclosed_gaps"]
    # coverage fraction + held_reasons telemetry preserved exactly (severity-only, no content edit).
    assert manifest["four_role_evaluation"]["coverage_fraction"] == 0.4
    assert manifest["four_role_evaluation"]["held_reasons"] == [R_COV]


def test_disposition_zero_grounding_hard_block_never_downgrades():
    """THE blocking bug (Sol §3 / Fable item 2): a true zero-grounding hard block whose held_reasons
    are coverage-ONLY must NEVER be released, even under legacy. hard_block rides on separate fields
    the set-equality predicate cannot see; the disposition guard refuses on ANY hard block."""
    from src.polaris_graph.roles.release_policy import (
        _REASON_UNSUPPORTED_RESIDUAL_BELOW_COVERAGE as R_COV,
    )

    held = [R_COV]
    outcome = _native_outcome(
        held_reasons=held, zero_verified=True, zero_usable_evidence=True
    )
    assert outcome.hard_block is True
    assert "zero_grounding" in outcome.hard_block_reasons
    # Even MARKED legacy + coverage-only held_reasons: NOT downgraded (hard block refuses release).
    allowed, status, manifest = _seam_disposition(
        outcome, g.LINEAGE_LEGACY_RACE_TASK, held, False
    )
    assert allowed is False, "zero-grounding must never be released_with_disclosed_gaps"
    assert status != "released_with_disclosed_gaps"
    assert "legacy_coverage_shortfall_report_only" not in manifest


def test_disposition_fabrication_s0_rewrite_safety_never_downgrade():
    """fabrication-latch, S0-must-cover, pending-rewrite, and safety/insufficient terminals NEVER
    downgrade under legacy (each holds / keeps its own terminal)."""
    from src.polaris_graph.roles.release_policy import (
        _REASON_FABRICATED_OCCURRENCE as R_FAB,
        _REASON_PENDING_REWRITE as R_REWRITE,
        _REASON_UNSUPPORTED_RESIDUAL_BELOW_COVERAGE as R_COV,
        STATUS_RELEASED_INSUFFICIENT_SAFETY,
    )

    leg = g.LINEAGE_LEGACY_RACE_TASK
    # fabrication latched (hard block, redaction off) + coverage held_reason => NOT downgraded.
    held = [R_COV, R_FAB]
    o = _native_outcome(held_reasons=held, fabricated_latched=True)
    assert o.hard_block is True
    allowed, status, _ = _seam_disposition(o, leg, held, True)
    assert allowed is False and status != "released_with_disclosed_gaps"

    # S0-must-cover mixed with coverage => set-equality breaks => NOT downgraded.
    held = [R_COV, "d8_s0_must_cover_missing:safety"]
    o = _native_outcome(held_reasons=held)
    allowed, status, _ = _seam_disposition(o, leg, held, False)
    assert allowed is False and status != "released_with_disclosed_gaps"

    # pending-rewrite mixed with coverage => NOT downgraded.
    held = [R_COV, R_REWRITE]
    o = _native_outcome(held_reasons=held)
    allowed, status, _ = _seam_disposition(o, leg, held, False)
    assert allowed is False and status != "released_with_disclosed_gaps"

    # insufficient-safety terminal (already RELEASED, exists on the always-release-ON path) is never
    # re-labelled to disclosed-gaps even when held_reasons look coverage-only.
    held = [R_COV]
    o = _native_outcome(
        held_reasons=held, safety_floor_insufficient=True, always_release=True
    )
    assert o.released is True and o.status == STATUS_RELEASED_INSUFFICIENT_SAFETY
    allowed, status, _ = _seam_disposition(o, leg, held, False)
    assert allowed is True  # it already ships
    assert status == STATUS_RELEASED_INSUFFICIENT_SAFETY  # label PRESERVED, not overwritten


def test_disposition_non_legacy_marked_query_with_selector_set_does_not_downgrade(
    monkeypatch,
):
    """FIX B scope leak: the GLOBAL selector is set to legacy, but THIS query was never legacy-bound
    (no per-query marker). It must NOT be downgraded — the disposition gates on the per-query marker,
    not the process-wide selector."""
    from src.polaris_graph.roles.release_policy import (
        _REASON_UNSUPPORTED_RESIDUAL_BELOW_COVERAGE as R_COV,
        STATUS_ABORT_FOUR_ROLE_HELD,
    )

    monkeypatch.setenv(g.LINEAGE_SELECTOR_ENV, g.LINEAGE_LEGACY_RACE_TASK)  # selector ON
    held = [R_COV]
    outcome = _native_outcome(held_reasons=held)
    # marker=None (this query was not rebound legacy) => NOT downgraded despite the global selector.
    allowed, status, manifest = _seam_disposition(outcome, None, held, False)
    assert allowed is False
    assert status == STATUS_ABORT_FOUR_ROLE_HELD
    assert "legacy_coverage_shortfall_report_only" not in manifest


# ─────────────────────────────────────────────────────────────────────────────
# FIX E (Sol §1 note): explicitly lock the drb_90_adas_liability no-gold case FAILS LOUD under legacy
# ─────────────────────────────────────────────────────────────────────────────
def test_no_gold_drb_90_adas_liability_fails_loud_under_legacy():
    """drb_90_adas_liability is a benchmark slug with NO canonical gold and NO legacy mapping. Under
    the legacy selector it must FAIL LOUD through the shared helper (never slip past both override
    branches and silently launch its DRB-II idx question = split brain)."""
    # it IS classified as a registered benchmark (no-gold set), so registration alone passes...
    g.assert_drb_slug_registered("drb_90_adas_liability")
    # ...but the shared legacy-support helper REJECTS it (no SLUG_TO_LEGACY_TASK mapping).
    with pytest.raises(g.GateZeroLineageError):
        g.assert_legacy_slug_supported("drb_90_adas_liability")
    # and the canonical resolver refuses a legacy resolution for it (never guesses an id).
    with pytest.raises(g.GateZeroLineageError):
        g.canonical_question_for_slug(
            "drb_90_adas_liability", lineage=g.LINEAGE_LEGACY_RACE_TASK
        )
