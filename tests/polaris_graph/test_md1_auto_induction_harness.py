"""M-D1 auto-induction harness tests (Phase D).

The harness must:
  - load + validate the validation set YAML (with strict
    expected_action='abstain' for negative groups)
  - compare contracts structurally on 6 dimensions including type
    + required_fields, producing match_score in [0, 1]
  - validate InductorVerdict shape (decision is closed enum,
    accept↔induced_contract invariant, confidence in [0,1])
  - aggregate precision / abstain_recall / abstain_precision /
    operator_review_load + silent_disagreement_rate
  - report acceptance against M-D1 thresholds
  - support confidence-threshold sweeping for M-D2 calibration

These tests use stub inductors (no LLM, no real induction) PLUS
an end-to-end run on the shipped seed validation set, exercising
the real curator-contract loader path.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest

from src.polaris_graph.auto_induction import (
    BenchmarkResult,
    InductorProtocol,
    InductorVerdict,
    InductorVerdictError,
    PrecisionMetrics,
    ValidationCase,
    ValidationSet,
    compare_contracts,
    load_validation_set,
    run_benchmark,
)
from src.polaris_graph.auto_induction.benchmark_loader import (
    ValidationSetError,
)


# ---------------------------------------------------------------------------
# Stub contract objects (avoid importing the V30 substrate for unit tests)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Entity:
    id: str
    type: str
    rendering_slot: str
    min_fields_for_completion: int
    required_fields: tuple[str, ...] = ()


@dataclass(frozen=True)
class _Contract:
    slug: str
    section_order: tuple[str, ...]
    required_entities: tuple[_Entity, ...]


# ---------------------------------------------------------------------------
# Validation-set loader tests
# ---------------------------------------------------------------------------


SEED_VS_PATH = (
    Path(__file__).resolve().parents[2]
    / "config" / "auto_induction" / "validation_set.yaml"
)


def test_load_validation_set_real_file() -> None:
    """The shipped seed validation set loads cleanly."""
    s = load_validation_set(SEED_VS_PATH)
    assert isinstance(s, ValidationSet)
    assert s.total >= 5
    assert len(s.in_scope) >= 1
    assert len(s.ambiguous) >= 1
    assert len(s.out_of_scope) >= 1


def test_load_validation_set_missing_file_raises(tmp_path: Path) -> None:
    with pytest.raises(ValidationSetError, match="not found"):
        load_validation_set(tmp_path / "missing.yaml")


def test_load_validation_set_missing_curator_slug_raises(
    tmp_path: Path,
) -> None:
    p = tmp_path / "vs.yaml"
    p.write_text(
        "in_scope:\n"
        "  - case_id: cli-01\n"
        "    query: 'q1'\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationSetError, match="curator_contract_slug"):
        load_validation_set(p)


def test_load_validation_set_duplicate_case_id_raises(
    tmp_path: Path,
) -> None:
    p = tmp_path / "vs.yaml"
    p.write_text(
        "in_scope:\n"
        "  - case_id: dup\n"
        "    query: 'q1'\n"
        "    curator_contract_slug: x\n"
        "ambiguous:\n"
        "  - case_id: dup\n"
        "    query: 'q2'\n",
        encoding="utf-8",
    )
    with pytest.raises(ValidationSetError, match="duplicate"):
        load_validation_set(p)


def test_load_validation_set_rejects_accept_in_negative_group(
    tmp_path: Path,
) -> None:
    """Codex round-1 fix: ambiguous + out_of_scope groups MUST
    declare expected_action='abstain'. By definition a negative-set
    case is one the inductor must abstain on."""
    p = tmp_path / "vs.yaml"
    p.write_text(
        "ambiguous:\n"
        "  - case_id: amb-01\n"
        "    query: 'q1'\n"
        "    expected_action: accept\n",  # invalid for ambiguous
        encoding="utf-8",
    )
    with pytest.raises(ValidationSetError, match="expected_action"):
        load_validation_set(p)


# ---------------------------------------------------------------------------
# Contract comparison tests
# ---------------------------------------------------------------------------


def _make_contract(slug: str, *, sections=None, entities=None) -> _Contract:
    return _Contract(
        slug=slug,
        section_order=tuple(sections or ()),
        required_entities=tuple(entities or ()),
    )


def test_compare_identical_contracts_score_one() -> None:
    c = _make_contract(
        "x",
        sections=("A", "B"),
        entities=(
            _Entity("e1", "pivotal_trial", "A", 3, ("doi", "n", "endpoint")),
            _Entity("e2", "regulatory", "B", 2, ("url", "agency")),
        ),
    )
    cmp = compare_contracts(c, c)
    assert cmp.match_score == pytest.approx(1.0)
    assert cmp.section_order_score == 1.0
    assert cmp.entities_by_id_score == 1.0
    assert cmp.rendering_slot_score == 1.0
    assert cmp.min_fields_score == 1.0
    assert cmp.type_score == 1.0
    assert cmp.required_fields_score == 1.0


def test_compare_inducer_returned_none() -> None:
    c = _make_contract(
        "x", sections=("A",),
        entities=(_Entity("e1", "t", "A", 1, ("f",)),),
    )
    cmp = compare_contracts(c, None)
    assert cmp.match_score == 0.0
    assert cmp.induced_slug is None


def test_compare_extra_section_in_induced() -> None:
    cur = _make_contract("x", sections=("A", "B"), entities=())
    ind = _make_contract("x", sections=("A", "B", "C"), entities=())
    cmp = compare_contracts(cur, ind)
    # IoU(2/3) for sections, full match elsewhere (no entities).
    assert cmp.section_order_score == pytest.approx(2 / 3)
    assert cmp.sections_only_in_induced == ("C",)
    assert cmp.sections_only_in_curator == ()


def test_compare_missing_entity() -> None:
    cur = _make_contract(
        "x", sections=("A",),
        entities=(
            _Entity("e1", "t", "A", 3),
            _Entity("e2", "t", "A", 2),
        ),
    )
    ind = _make_contract(
        "x", sections=("A",),
        entities=(_Entity("e1", "t", "A", 3),),  # missing e2
    )
    cmp = compare_contracts(cur, ind)
    assert cmp.entities_only_in_curator == ("e2",)
    assert cmp.entities_by_id_score == pytest.approx(0.5)


def test_compare_type_mismatch_penalized() -> None:
    """Codex round-1 fix: type mismatches must be penalized.
    Previously an inducer producing the right ids but wrong types
    scored full marks on rendering_slot etc."""
    cur = _make_contract(
        "x", sections=("A",),
        entities=(_Entity("e1", "pivotal_trial", "A", 3, ("doi",)),),
    )
    ind = _make_contract(
        "x", sections=("A",),
        entities=(_Entity("e1", "regulatory", "A", 3, ("doi",)),),
    )
    cmp = compare_contracts(cur, ind)
    assert cmp.type_score == 0.0
    assert any("e1" in m for m in cmp.type_mismatches)
    assert cmp.match_score < 1.0


def test_compare_required_fields_mismatch_penalized() -> None:
    """Codex round-1 fix: required_fields mismatches must be
    penalized. Previously an inducer that omitted required_fields
    entirely scored 0.8 trivially."""
    cur = _make_contract(
        "x", sections=("A",),
        entities=(
            _Entity("e1", "t", "A", 3, ("doi", "endpoint", "n")),
        ),
    )
    ind = _make_contract(
        "x", sections=("A",),
        entities=(
            _Entity("e1", "t", "A", 3, ()),  # required_fields empty
        ),
    )
    cmp = compare_contracts(cur, ind)
    assert cmp.required_fields_score == 0.0
    assert any("e1" in m for m in cmp.required_fields_mismatches)
    assert cmp.match_score < 1.0


def test_compare_partial_pseudocontract_does_not_hit_tau() -> None:
    """Codex round-1 fix: previously a partial pseudo-contract
    (right ids + sections + slots, but no type/required_fields)
    could hit match_score=0.8. With v2 weights (15% each for type
    and required_fields), missing both drops score below 0.80."""
    cur = _make_contract(
        "x", sections=("A", "B"),
        entities=(
            _Entity("e1", "pivotal_trial", "A", 3, ("doi", "n")),
            _Entity("e2", "regulatory", "B", 2, ("url",)),
        ),
    )
    # Pseudo-contract: same ids + sections + slots + min_fields,
    # but wrong type and empty required_fields.
    ind = _make_contract(
        "x", sections=("A", "B"),
        entities=(
            _Entity("e1", "wrong_type", "A", 3, ()),
            _Entity("e2", "wrong_type", "B", 2, ()),
        ),
    )
    cmp = compare_contracts(cur, ind)
    # 4/6 dimensions perfect (15+25+15+15 = 70%), 2/6 zero.
    assert cmp.match_score == pytest.approx(0.70)
    assert cmp.match_score < 0.80  # below tau


def test_compare_weights_must_sum_to_one() -> None:
    c = _make_contract("x", sections=("A",))
    with pytest.raises(ValueError, match="sum to 1"):
        compare_contracts(
            c, c,
            section_weight=0.5, entities_weight=0.5,
            rendering_weight=0.5, min_fields_weight=0.5,
            type_weight=0.5, required_fields_weight=0.5,
        )


# ---------------------------------------------------------------------------
# InductorVerdict validation tests (Codex round-1 fix)
# ---------------------------------------------------------------------------


def test_verdict_rejects_unknown_decision() -> None:
    with pytest.raises(InductorVerdictError, match="must be 'accept' or 'abstain'"):
        InductorVerdict(decision="maybe")


def test_verdict_accept_requires_contract() -> None:
    with pytest.raises(InductorVerdictError, match="requires non-None"):
        InductorVerdict(decision="accept", induced_contract=None)


def test_verdict_abstain_requires_no_contract() -> None:
    with pytest.raises(InductorVerdictError, match="must have None"):
        InductorVerdict(
            decision="abstain", induced_contract=object(),
        )


def test_verdict_confidence_must_be_in_unit_interval() -> None:
    with pytest.raises(InductorVerdictError, match="must be in"):
        InductorVerdict(
            decision="accept", induced_contract=object(), confidence=1.5,
        )
    with pytest.raises(InductorVerdictError, match="must be in"):
        InductorVerdict(
            decision="abstain", confidence=-0.1,
        )


# ---------------------------------------------------------------------------
# Benchmark runner tests (stub inductors)
# ---------------------------------------------------------------------------


class _AlwaysAbstainInductor:
    def induce(self, query: str) -> InductorVerdict:
        return InductorVerdict(
            decision="abstain",
            abstain_reason="stub: always abstain",
        )


class _AlwaysAcceptStubInductor:
    def __init__(self, contract: Any) -> None:
        self._contract = contract

    def induce(self, query: str) -> InductorVerdict:
        return InductorVerdict(
            decision="accept",
            induced_contract=self._contract,
            confidence=0.99,
        )


def _make_validation_set(*, in_scope: int, ambiguous: int, oos: int) -> ValidationSet:
    return ValidationSet(
        in_scope=tuple(
            ValidationCase(
                case_id=f"cli-{i}", group="in_scope",
                query=f"q{i}",
                curator_contract_slug="stub",
                domain="clinical",
            )
            for i in range(in_scope)
        ),
        ambiguous=tuple(
            ValidationCase(
                case_id=f"amb-{i}", group="ambiguous",
                query=f"q{i}",
                expected_action="abstain",
            )
            for i in range(ambiguous)
        ),
        out_of_scope=tuple(
            ValidationCase(
                case_id=f"oos-{i}", group="out_of_scope",
                query=f"q{i}",
                expected_action="abstain",
            )
            for i in range(oos)
        ),
    )


def test_always_abstain_inductor_metrics() -> None:
    s = _make_validation_set(in_scope=3, ambiguous=2, oos=2)
    result = run_benchmark(_AlwaysAbstainInductor(), s, tau=0.8)
    m = result.metrics
    assert m.total_cases == 7
    assert m.precision == 0.0
    assert m.silent_disagreement_rate == 0.0
    assert m.abstain_recall == 1.0
    # Codex round-1 fix: abstain_precision = correct/total = 4/7
    assert m.abstain_precision == pytest.approx(4 / 7)
    assert m.operator_review_load == 1.0
    assert not m.passes_acceptance()


def test_silent_disagreement_counted(monkeypatch) -> None:
    """An inductor that accepts in-scope but produces a low-match
    contract should have its silent disagreements counted."""
    curator_contract = _make_contract(
        "curator",
        sections=("A", "B", "C"),
        entities=(
            _Entity("e1", "pivotal_trial", "A", 3, ("doi",)),
            _Entity("e2", "regulatory", "B", 2, ("url",)),
            _Entity("e3", "mechanism", "C", 1, ("doi",)),
        ),
    )
    induced_contract = _make_contract(
        "induced",
        sections=("Z",),
        entities=(),
    )
    monkeypatch.setattr(
        "src.polaris_graph.auto_induction.precision_metrics."
        "_load_curator_contract",
        lambda slug: curator_contract,
    )

    s = _make_validation_set(in_scope=2, ambiguous=0, oos=0)
    result = run_benchmark(
        _AlwaysAcceptStubInductor(induced_contract), s, tau=0.8,
    )
    m = result.metrics
    assert m.in_scope_accepted == 2
    assert m.in_scope_match_at_tau == 0
    assert m.in_scope_silent_disagreements == 2
    assert m.silent_disagreement_rate == pytest.approx(1.0)


def test_confidence_threshold_downgrades_accept_to_abstain(monkeypatch) -> None:
    """Codex round-1 fix: confidence is now actionable. With
    confidence_threshold set, low-confidence accepts become abstains."""
    contract = _make_contract(
        "stub", sections=("A",),
        entities=(_Entity("e1", "t", "A", 1, ("f",)),),
    )

    class _LowConfidenceInductor:
        def induce(self, query: str) -> InductorVerdict:
            return InductorVerdict(
                decision="accept",
                induced_contract=contract,
                confidence=0.5,  # low
            )

    monkeypatch.setattr(
        "src.polaris_graph.auto_induction.precision_metrics."
        "_load_curator_contract",
        lambda slug: contract,
    )

    s = _make_validation_set(in_scope=2, ambiguous=0, oos=2)
    # Without threshold: accepts in-scope, accepts oos (incorrectly).
    result = run_benchmark(_LowConfidenceInductor(), s, tau=0.8)
    assert result.metrics.in_scope_accepted == 2
    assert result.metrics.abstain_total == 0

    # With threshold=0.7: confidence 0.5 < 0.7 → all accepts become
    # abstains. Now abstain_recall=1.0 on oos cases.
    result_th = run_benchmark(
        _LowConfidenceInductor(), s, tau=0.8, confidence_threshold=0.7,
    )
    assert result_th.metrics.abstain_total == 4
    assert result_th.metrics.abstain_correct == 2  # the oos cases
    assert result_th.metrics.abstain_recall == 1.0
    assert result_th.metrics.in_scope_accepted == 0


# ---------------------------------------------------------------------------
# End-to-end test on the shipped seed validation set (Codex round-1 fix)
# ---------------------------------------------------------------------------


def test_seed_validation_set_loads_curator_contracts() -> None:
    """Codex round-1 fix: the shipped seed set must actually be
    benchmarkable. Round-1 found policy_eu_ai_act slug didn't exist
    and the loader was passing a Path where a dict was expected.
    Both fixed in v2; this test catches regression."""
    s = load_validation_set(SEED_VS_PATH)
    # Stub inductor: abstain on everything. Expected behavior:
    # - all in-scope routed to operator (counts as silent failure
    #   from the metric POV but no crash)
    # - all ambiguous + oos correctly abstained
    # The KEY assertion is that this does not crash on the
    # _load_curator_contract path. Round-1 v1 would have crashed
    # on any in_scope acceptance. Use an inductor that ALSO accepts
    # in-scope cases to actually exercise the loader.
    from src.polaris_graph.nodes.report_contract import (
        load_report_contract_for_slug,
    )
    import yaml as _yaml

    # Pre-flight: confirm the seed set's slugs exist in the actual
    # template files. This is the regression test for the
    # policy_eu_ai_act bug.
    config_root = (
        Path(__file__).resolve().parents[2] / "config" / "scope_templates"
    )
    seen_slugs: set[str] = set()
    for yaml_path in config_root.glob("*.yaml"):
        with yaml_path.open("r", encoding="utf-8") as fp:
            tdict = _yaml.safe_load(fp)
        if isinstance(tdict, dict):
            by_slug = tdict.get("per_query_report_contract") or {}
            seen_slugs |= set(by_slug.keys())

    for case in s.in_scope:
        assert case.curator_contract_slug in seen_slugs, (
            f"seed validation set references unknown slug "
            f"{case.curator_contract_slug!r}; available slugs in "
            f"config/scope_templates: {sorted(seen_slugs)}"
        )


def test_end_to_end_benchmark_on_seed_set_with_oracle() -> None:
    """Run the full benchmark pipeline on the shipped seed set
    using a query-prefix oracle. Exercises:
      - load_validation_set on real YAML
      - _load_curator_contract on real templates (the round-1 bug fix)
      - compare_contracts on real ReportContract objects
      - PrecisionMetrics aggregation
    """
    s = load_validation_set(SEED_VS_PATH)

    # Oracle: accept any in-scope query (whose curator_contract_slug
    # we can look up); abstain otherwise.
    in_scope_queries = {c.query for c in s.in_scope}
    in_scope_slugs = {c.query: c.curator_contract_slug for c in s.in_scope}

    class _OracleInductor:
        def induce(self, query: str) -> InductorVerdict:
            if query in in_scope_queries:
                slug = in_scope_slugs[query]
                # Look up the curator contract and return it as the
                # induced contract — perfect oracle.
                from src.polaris_graph.auto_induction.precision_metrics import (
                    _load_curator_contract,
                )
                contract = _load_curator_contract(slug)
                return InductorVerdict(
                    decision="accept",
                    induced_contract=contract,
                    confidence=1.0,
                )
            return InductorVerdict(
                decision="abstain",
                abstain_reason="not in scope",
            )

    result = run_benchmark(_OracleInductor(), s, tau=0.8)
    m = result.metrics
    # Perfect oracle: accepts all in-scope, abstains correctly on all
    # ambiguous + oos. Match score = 1.0 for all in-scope cases.
    assert m.in_scope_accepted == len(s.in_scope)
    assert m.in_scope_match_at_tau == len(s.in_scope)
    assert m.silent_disagreement_rate == 0.0
    assert m.abstain_correct == m.abstain_should_abstain_total
    assert m.abstain_recall == 1.0
    assert m.precision == 1.0
    # operator_review_load = abstains / total = (ambig + oos) / total.
    # The validation set is intentionally negative-heavy (more
    # abstain-expected cases than in-scope) to stress-test
    # abstain-recall, which means operator_review_load is naturally
    # > 0.30. Passes acceptance with a relaxed operator-review
    # ceiling that matches the validation set's negative-tilt.
    expected_load = m.abstain_should_abstain_total / m.total_cases
    assert m.operator_review_load == pytest.approx(expected_load)
    assert m.passes_acceptance(operator_review_ceiling=expected_load + 0.01)
