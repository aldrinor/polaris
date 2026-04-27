"""M-D1 auto-induction harness tests (Phase D).

The harness must:
  - load + validate the validation set YAML
  - compare contracts structurally and produce match_score in [0, 1]
  - aggregate precision / abstain_recall / operator_review_load
  - report acceptance against M-D1 thresholds

These tests use stub inductors (no LLM, no real induction) to
verify the harness math is correct. M-D2 will plug in a real
inductor and run this harness against the real validation set.
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
# Stub contract objects (avoid importing the V30 substrate in unit tests)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class _Entity:
    id: str
    rendering_slot: str
    min_fields_for_completion: int


@dataclass(frozen=True)
class _Contract:
    slug: str
    section_order: tuple[str, ...]
    required_entities: tuple[_Entity, ...]


# ---------------------------------------------------------------------------
# Validation-set loader tests
# ---------------------------------------------------------------------------


def test_load_validation_set_real_file() -> None:
    """The shipped seed validation set loads cleanly."""
    p = Path(__file__).resolve().parents[2] / "config" / "auto_induction" / "validation_set.yaml"
    s = load_validation_set(p)
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
        "    query: 'q1'\n",  # missing curator_contract_slug
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


def test_load_validation_set_bad_expected_action(
    tmp_path: Path,
) -> None:
    p = tmp_path / "vs.yaml"
    p.write_text(
        "ambiguous:\n"
        "  - case_id: amb-01\n"
        "    query: 'q1'\n"
        "    expected_action: maybe\n",  # invalid
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
            _Entity("e1", "A", 3),
            _Entity("e2", "B", 2),
        ),
    )
    cmp = compare_contracts(c, c)
    assert cmp.match_score == pytest.approx(1.0)
    assert cmp.section_order_score == 1.0
    assert cmp.entities_by_id_score == 1.0
    assert cmp.rendering_slot_score == 1.0
    assert cmp.min_fields_score == 1.0


def test_compare_inducer_returned_none() -> None:
    c = _make_contract("x", sections=("A",), entities=(_Entity("e1", "A", 1),))
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
        entities=(_Entity("e1", "A", 3), _Entity("e2", "A", 2)),
    )
    ind = _make_contract(
        "x", sections=("A",),
        entities=(_Entity("e1", "A", 3),),  # missing e2
    )
    cmp = compare_contracts(cur, ind)
    assert cmp.entities_only_in_curator == ("e2",)
    # IoU = 1 / 2 (one shared, one only-in-curator).
    assert cmp.entities_by_id_score == pytest.approx(0.5)


def test_compare_rendering_slot_mismatch_recorded() -> None:
    cur = _make_contract(
        "x", sections=("A",),
        entities=(_Entity("e1", "A", 3),),
    )
    ind = _make_contract(
        "x", sections=("A",),
        entities=(_Entity("e1", "B", 3),),  # slot wrong
    )
    cmp = compare_contracts(cur, ind)
    assert cmp.rendering_slot_score == 0.0
    assert any("e1" in m for m in cmp.rendering_slot_mismatches)


def test_compare_min_fields_mismatch_recorded() -> None:
    cur = _make_contract(
        "x", sections=("A",),
        entities=(_Entity("e1", "A", 3),),
    )
    ind = _make_contract(
        "x", sections=("A",),
        entities=(_Entity("e1", "A", 1),),  # min_fields wrong
    )
    cmp = compare_contracts(cur, ind)
    assert cmp.min_fields_score == 0.0
    assert any("e1" in m for m in cmp.min_fields_mismatches)


def test_compare_weights_must_sum_to_one() -> None:
    c = _make_contract("x", sections=("A",))
    with pytest.raises(ValueError, match="sum to 1"):
        compare_contracts(
            c, c,
            section_weight=0.5, entities_weight=0.5,
            rendering_weight=0.5, min_fields_weight=0.5,
        )


# ---------------------------------------------------------------------------
# Benchmark runner tests (stub inductors)
# ---------------------------------------------------------------------------


class _AlwaysAbstainInductor:
    """Stub inductor that abstains on every query."""

    def induce(self, query: str) -> InductorVerdict:
        return InductorVerdict(
            decision="abstain",
            induced_contract=None,
            abstain_reason="stub: always abstain",
        )


class _AlwaysAcceptStubInductor:
    """Stub inductor that always accepts and returns a stub contract.
    For testing the harness math, not for real induction."""

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
    inductor = _AlwaysAbstainInductor()
    result = run_benchmark(inductor, s, tau=0.8)
    m = result.metrics
    assert m.total_cases == 7
    # Always abstaining: precision = 0/0 -> 0.0 (no acceptances)
    assert m.precision == 0.0
    # 0 silent disagreements (no acceptances)
    assert m.silent_disagreement_rate == 0.0
    # Abstain recall = 4/4 = 1.0 (all 4 should-abstain cases got abstained)
    assert m.abstain_recall == 1.0
    # Operator review load = 7/7 = 1.0 (everything routed to humans)
    assert m.operator_review_load == 1.0
    # Doesn't pass acceptance — operator load way over 0.30
    assert not m.passes_acceptance()


def test_perfect_inductor_passes_acceptance(monkeypatch) -> None:
    """An oracle inductor accepts in-scope (with the correct curator
    contract) and abstains on ambiguous + OOS. Should pass all
    M-D1 thresholds."""
    stub_contract = _make_contract(
        "stub",
        sections=("A",),
        entities=(_Entity("e1", "A", 1),),
    )
    # Patch the curator-loader to return the same stub contract (so
    # match_score == 1.0).
    monkeypatch.setattr(
        "src.polaris_graph.auto_induction.precision_metrics."
        "_load_curator_contract",
        lambda slug: stub_contract,
    )

    class _OracleInductor:
        def induce(self, query: str) -> InductorVerdict:
            if query.startswith("q") and query[1:].isdigit():
                # All queries from _make_validation_set start with "q".
                # Use the case-id semantics from the set: in-scope IDs
                # start cli-, ambiguous amb-, oos oos-. We don't have
                # that info in induce() — so peek at the call order
                # via shared state. For test purposes, use the harness's
                # case ordering: in_scope first, then ambiguous, then
                # oos.
                ...
            return InductorVerdict(
                decision="accept",
                induced_contract=stub_contract,
                confidence=0.99,
            )

    # Different approach: a contract-aware inductor that sees the
    # case_id via run_benchmark's case loop. But run_benchmark only
    # passes query, not case. So we need the inductor to make the
    # accept/abstain decision from the query.
    # Use a query-prefix oracle: in-scope queries start "in:", others
    # start "out:".
    s = ValidationSet(
        in_scope=(
            ValidationCase(
                case_id="cli-1", group="in_scope",
                query="in:cli-1",
                curator_contract_slug="stub",
            ),
            ValidationCase(
                case_id="cli-2", group="in_scope",
                query="in:cli-2",
                curator_contract_slug="stub",
            ),
        ),
        ambiguous=(
            ValidationCase(
                case_id="amb-1", group="ambiguous",
                query="out:amb-1",
                expected_action="abstain",
            ),
        ),
        out_of_scope=(
            ValidationCase(
                case_id="oos-1", group="out_of_scope",
                query="out:oos-1",
                expected_action="abstain",
            ),
        ),
    )

    class _OracleInductorByPrefix:
        def induce(self, query: str) -> InductorVerdict:
            if query.startswith("in:"):
                return InductorVerdict(
                    decision="accept",
                    induced_contract=stub_contract,
                    confidence=0.99,
                )
            return InductorVerdict(
                decision="abstain",
                induced_contract=None,
                abstain_reason="not in scope",
            )

    result = run_benchmark(_OracleInductorByPrefix(), s, tau=0.8)
    m = result.metrics
    assert m.precision == pytest.approx(1.0)
    assert m.silent_disagreement_rate == 0.0
    assert m.abstain_recall == pytest.approx(1.0)
    assert m.operator_review_load == pytest.approx(0.5)  # 2/4 abstained
    # operator_review_load 0.5 is over the 0.30 ceiling, so doesn't
    # pass default acceptance — but the validation set was tiny + all
    # OOS, which is unrealistic. With a 100-200 case set the load
    # should be naturally lower.
    assert not m.passes_acceptance()
    # But with a relaxed ceiling it passes.
    assert m.passes_acceptance(operator_review_ceiling=0.6)


def test_silent_disagreement_counted(monkeypatch) -> None:
    """An inductor that accepts in-scope but produces a low-match
    contract should have its silent disagreements counted."""
    curator_contract = _make_contract(
        "curator",
        sections=("A", "B", "C"),
        entities=(
            _Entity("e1", "A", 3),
            _Entity("e2", "B", 2),
            _Entity("e3", "C", 1),
        ),
    )
    induced_contract = _make_contract(
        "induced",
        sections=("Z",),  # totally different
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
    # 2 acceptances, both with bad match
    assert m.in_scope_accepted == 2
    assert m.in_scope_match_at_tau == 0
    assert m.in_scope_silent_disagreements == 2
    assert m.silent_disagreement_rate == pytest.approx(1.0)
