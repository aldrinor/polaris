"""M-D11 phase 2 pin-replay tests."""

from __future__ import annotations

import os

import pytest

from src.polaris_graph.audit_ir.model_pin import (
    capture_env_snapshot,
    capture_pin,
)
from src.polaris_graph.audit_ir.pin_replay import (
    EnvMutation,
    MissingPromptTextError,
    PinReplayError,
    ReplayMismatch,
    ReplayPlan,
    apply_replay_plan,
    build_replay_plan,
    replay_pin,
    verify_replay,
)


# ---------------------------------------------------------------------------
# build_replay_plan: pure plan derivation
# ---------------------------------------------------------------------------


def test_build_replay_plan_unset_var_emits_delete() -> None:
    """v4 None semantics: env_snapshot[key] = None means
    "var was unset at capture time". Replay must DELETE the
    env var (not set it to "")."""
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        env_snapshot={"PG_FOO": None},
    )
    plan = build_replay_plan(pin)
    assert len(plan.env_mutations) == 1
    mut = plan.env_mutations[0]
    assert mut.name == "PG_FOO"
    assert mut.op == "delete"
    assert mut.value is None


def test_build_replay_plan_empty_str_emits_set() -> None:
    """v4 None vs '' distinction: '' means "var was set to
    empty"; replay SETS the var to "". int('') would crash
    a downstream consumer if we conflated this with unset."""
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        env_snapshot={"PG_FOO": ""},
    )
    plan = build_replay_plan(pin)
    assert len(plan.env_mutations) == 1
    mut = plan.env_mutations[0]
    assert mut.op == "set"
    assert mut.value == ""


def test_build_replay_plan_str_value_emits_set() -> None:
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        env_snapshot={"PG_FOO": "1024"},
    )
    plan = build_replay_plan(pin)
    assert plan.env_mutations[0] == EnvMutation(
        name="PG_FOO", op="set", value="1024"
    )


def test_build_replay_plan_multiple_vars() -> None:
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        env_snapshot={
            "PG_A": "alpha",
            "PG_B": None,
            "PG_C": "",
        },
    )
    plan = build_replay_plan(pin)
    by_name = {m.name: m for m in plan.env_mutations}
    assert by_name["PG_A"].op == "set" and by_name["PG_A"].value == "alpha"
    assert by_name["PG_B"].op == "delete"
    assert by_name["PG_C"].op == "set" and by_name["PG_C"].value == ""


def test_build_replay_plan_rejects_non_pin() -> None:
    with pytest.raises(PinReplayError, match="ModelPin"):
        build_replay_plan({"pin": "fake"})  # type: ignore[arg-type]


def test_build_replay_plan_no_side_effects(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Plan derivation must not mutate os.environ."""
    monkeypatch.setenv("PG_OBSERVE", "before")
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        env_snapshot={"PG_OBSERVE": "after", "PG_NEW": "x"},
    )
    build_replay_plan(pin)
    # env unchanged.
    assert os.environ["PG_OBSERVE"] == "before"
    assert "PG_NEW" not in os.environ


# ---------------------------------------------------------------------------
# apply_replay_plan: reversibility + None/'' fidelity
# ---------------------------------------------------------------------------


def test_apply_replay_plan_sets_and_restores_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The core reversibility contract. Inside `with`, env
    matches the pin. Outside, env is restored."""
    monkeypatch.setenv("PG_TEST_ORIGINAL", "before")
    monkeypatch.delenv("PG_TEST_NEW", raising=False)
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        env_snapshot={
            "PG_TEST_ORIGINAL": "after",
            "PG_TEST_NEW": "freshly-set",
        },
    )
    plan = build_replay_plan(pin)
    with apply_replay_plan(plan):
        assert os.environ["PG_TEST_ORIGINAL"] == "after"
        assert os.environ["PG_TEST_NEW"] == "freshly-set"
    # After exit: original restored, new var deleted.
    assert os.environ["PG_TEST_ORIGINAL"] == "before"
    assert "PG_TEST_NEW" not in os.environ


def test_apply_replay_plan_deletes_var_during_block(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If pin captured the var as None (unset), replay must
    actually pop it during the block — not set it to ""."""
    monkeypatch.setenv("PG_TEST_DELETEME", "had-value")
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        env_snapshot={"PG_TEST_DELETEME": None},
    )
    plan = build_replay_plan(pin)
    with apply_replay_plan(plan):
        assert "PG_TEST_DELETEME" not in os.environ
    # Restored to "had-value".
    assert os.environ["PG_TEST_DELETEME"] == "had-value"


def test_apply_replay_plan_empty_string_distinct_from_unset(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The None-vs-'' distinction must survive replay.
    set-to-'' produces os.environ[name] = '', which is
    distinguishable from 'name not in os.environ'."""
    monkeypatch.delenv("PG_TEST_EMPTYSET", raising=False)
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        env_snapshot={"PG_TEST_EMPTYSET": ""},
    )
    plan = build_replay_plan(pin)
    with apply_replay_plan(plan):
        assert "PG_TEST_EMPTYSET" in os.environ
        assert os.environ["PG_TEST_EMPTYSET"] == ""
    assert "PG_TEST_EMPTYSET" not in os.environ


def test_apply_replay_plan_restores_on_exception(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Exception inside the `with` block must NOT leave env
    polluted."""
    monkeypatch.setenv("PG_TEST_EXC", "before")
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        env_snapshot={"PG_TEST_EXC": "during"},
    )
    plan = build_replay_plan(pin)
    with pytest.raises(RuntimeError, match="boom"):
        with apply_replay_plan(plan):
            assert os.environ["PG_TEST_EXC"] == "during"
            raise RuntimeError("boom")
    assert os.environ["PG_TEST_EXC"] == "before"


def test_apply_replay_plan_rejects_non_plan() -> None:
    with pytest.raises(PinReplayError, match="ReplayPlan"):
        with apply_replay_plan({"plan": "fake"}):  # type: ignore[arg-type]
            pass


def test_apply_replay_plan_rejects_unknown_op() -> None:
    """Defense-in-depth: a malformed plan with op !=
    set|delete must fail loudly when applied."""
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        env_snapshot={"PG_X": "1"},
    )
    plan = ReplayPlan(
        pin=pin,
        env_mutations=(
            EnvMutation(name="PG_X", op="invalid_op", value="1"),
        ),
    )
    with pytest.raises(PinReplayError, match="unknown mutation op"):
        with apply_replay_plan(plan):
            pass


def test_apply_replay_plan_rejects_set_with_none_value() -> None:
    """Defense-in-depth: malformed `set` mutation with
    value=None must fail loudly."""
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        env_snapshot={"PG_X": "1"},
    )
    plan = ReplayPlan(
        pin=pin,
        env_mutations=(
            EnvMutation(name="PG_X", op="set", value=None),
        ),
    )
    with pytest.raises(PinReplayError, match="value=None"):
        with apply_replay_plan(plan):
            pass


# ---------------------------------------------------------------------------
# verify_replay: empirical schema-fidelity test
# ---------------------------------------------------------------------------


def test_verify_replay_returns_empty_on_match(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The empirical test: round-trip a pin's env_snapshot and
    confirm pins_equivalent_for_replay agrees."""
    monkeypatch.delenv("PG_TEST_VERIFY_A", raising=False)
    monkeypatch.delenv("PG_TEST_VERIFY_B", raising=False)
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        env_snapshot={
            "PG_TEST_VERIFY_A": "alpha",
            "PG_TEST_VERIFY_B": None,
        },
    )
    plan = build_replay_plan(pin)
    with apply_replay_plan(plan):
        mismatches = verify_replay(pin)
    assert mismatches == ()


def test_verify_replay_detects_env_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the env doesn't match the pin (operator override, or
    a missing env mutation in the plan), verify_replay reports
    the drifted key."""
    monkeypatch.setenv("PG_TEST_DRIFT", "wrong-value")
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        env_snapshot={"PG_TEST_DRIFT": "expected-value"},
    )
    # Verify WITHOUT applying the plan first — env still has
    # the wrong value.
    mismatches = verify_replay(pin)
    keys = {m.field_name for m in mismatches}
    assert "env_snapshot[PG_TEST_DRIFT]" in keys


def test_verify_replay_rejects_non_pin() -> None:
    with pytest.raises(PinReplayError, match="ModelPin"):
        verify_replay("not a pin")  # type: ignore[arg-type]


# ---------------------------------------------------------------------------
# replay_pin: validation wrapper + prompt-text contract
# ---------------------------------------------------------------------------


def test_replay_pin_returns_plan() -> None:
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        env_snapshot={"PG_X": "1"},
    )
    plan = replay_pin(pin)
    assert isinstance(plan, ReplayPlan)
    assert plan.pin is pin


def test_replay_pin_require_prompt_text_missing_raises() -> None:
    """Phase 2 v1 boundary 2: prompt hashes are
    verification-only. If operator passes
    require_prompt_text=True without supplying text for every
    role with a prompt hash, raise MissingPromptTextError."""
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m", "evaluator": "n"},
        role_prompts={
            "generator": "system: be a researcher",
            "evaluator": "system: judge faithfulness",
        },
    )
    # Both roles have prompt hashes; operator supplied no text.
    with pytest.raises(MissingPromptTextError) as exc:
        replay_pin(pin, require_prompt_text=True, prompt_text={})
    assert "generator" in str(exc.value)
    assert "evaluator" in str(exc.value)


def test_replay_pin_require_prompt_text_partial_raises() -> None:
    """Partial prompt-text dict: only roles missing should be
    listed in the error."""
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m", "evaluator": "n"},
        role_prompts={
            "generator": "p1",
            "evaluator": "p2",
        },
    )
    with pytest.raises(MissingPromptTextError) as exc:
        replay_pin(
            pin,
            require_prompt_text=True,
            prompt_text={"generator": "p1"},  # evaluator missing
        )
    assert "evaluator" in str(exc.value)
    assert "generator" not in str(exc.value)


def test_replay_pin_whitespace_prompt_text_treated_as_missing() -> None:
    """Empty / whitespace prompt text counts as missing — a
    prompt of all whitespace can't restore anything
    meaningful."""
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        role_prompts={"generator": "p1"},
    )
    with pytest.raises(MissingPromptTextError, match="generator"):
        replay_pin(
            pin,
            require_prompt_text=True,
            prompt_text={"generator": "   "},
        )


def test_replay_pin_no_prompt_hashes_no_text_required() -> None:
    """If the pin has no prompt hashes, require_prompt_text=True
    is trivially satisfied."""
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
    )
    plan = replay_pin(pin, require_prompt_text=True)
    assert isinstance(plan, ReplayPlan)


def test_replay_pin_default_does_not_require_prompt_text() -> None:
    """Default behavior: pins with prompt hashes can build a
    plan without operator-supplied text. The returned plan
    just won't restore the prompts — the env mutations alone
    are still applicable."""
    pin = capture_pin(
        run_id="r",
        llm_models={"generator": "m"},
        role_prompts={"generator": "p1"},
    )
    plan = replay_pin(pin)  # default require_prompt_text=False
    assert isinstance(plan, ReplayPlan)


# ---------------------------------------------------------------------------
# Single-threaded boundary check (boundary 1)
# ---------------------------------------------------------------------------


def test_concurrent_replays_stomp_each_other_documented_boundary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Document the phase 2 v1 boundary: os.environ is
    process-global. Two simultaneous replays of different
    pins WILL stomp each other. This test demonstrates the
    failure mode — phase 2 v1 is single-threaded only.

    Construct two pins with different values for the same
    var, apply both concurrently, observe that whichever
    enters second wins inside the inner block."""
    monkeypatch.delenv("PG_CONFLICT", raising=False)
    pin_a = capture_pin(
        run_id="a",
        llm_models={"generator": "m"},
        env_snapshot={"PG_CONFLICT": "value-a"},
    )
    pin_b = capture_pin(
        run_id="b",
        llm_models={"generator": "m"},
        env_snapshot={"PG_CONFLICT": "value-b"},
    )
    plan_a = build_replay_plan(pin_a)
    plan_b = build_replay_plan(pin_b)
    with apply_replay_plan(plan_a):
        assert os.environ["PG_CONFLICT"] == "value-a"
        with apply_replay_plan(plan_b):
            # B stomps A.
            assert os.environ["PG_CONFLICT"] == "value-b"
        # Restoring B's prior — which, when B applied, was
        # value-a (set by A).
        assert os.environ["PG_CONFLICT"] == "value-a"
    # All restored to original (unset).
    assert "PG_CONFLICT" not in os.environ
