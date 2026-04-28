"""M-D11 phase 2 (Phase D): Pin replay execution.

Phase 2 is the empirical test of M-D11 phase 1's locked v4
schema. Loads a `ModelPin` and applies the captured runtime
configuration so a downstream pipeline call reproduces the
captured run.

Per FINAL_PLAN M-D11 + Phase D milestones plan, replay is the
"re-run-from-pin capability". Phase 1 (commit 6c2f17f) shipped
the schema + capture; phase 2 ships:

  - `build_replay_plan(pin) -> ReplayPlan` — read pin, derive
    the set of env mutations + verification points needed.
    Pure / no side effects.
  - `apply_replay_plan(plan) -> ReplayContext` — execute the
    mutations. Returns a context manager that, on __exit__,
    restores prior env state. Reversibility is REQUIRED:
    without it replay would pollute the test runner / next
    pipeline call.
  - `verify_replay(pin) -> ReplayMismatch | None` — capture a
    fresh pin from current env; compare via
    pins_equivalent_for_replay(); return mismatched fields or
    None on success. Empirical proof the schema captured
    everything.

## Phase 2 v1 boundaries (per `docs/md11_phase2_threat_model.md`)

1. **Single-threaded.** os.environ mutation is process-global.
   Two concurrent replays will stomp each other. Phase 2 v1 is
   single-threaded; phase-2-of-phase-2 may add a process-pool
   isolation later.

2. **Prompt-hash is verification-only, not restoration.**
   `pin.prompt_version_hashes` records SHA-256 hashes — enough
   to *verify* a current prompt matches, NOT to *restore* a
   prompt. If the pin's prompts aren't independently persisted
   in the audit bundle, replay fails loudly with a
   `MissingPromptTextError`.

3. **Model swap is env-level only.** `replay_pin` sets
   `OPENROUTER_DEFAULT_MODEL` etc., but downstream clients may
   have read the env at import time and cached the model id.
   Replay does NOT introspect or mutate client internals. If
   the client is already imported and cached the value,
   replay's effect is observable only on subsequent process
   starts. Operators should re-import or restart the worker
   before replay.

4. **validation_set_hash is verify-only.** Replay does not
   restore the validation-set file from the hash; that's
   content-addressable storage territory. The pin records the
   hash so replay can detect drift; supplying the file is the
   operator's responsibility.

5. **No LLM client imports.** This module imports only stdlib
   and `model_pin`. The actual OpenRouter / inductor / verifier
   clients pick up the env on next call; pin_replay never
   touches their internals.

## Empirical verification contract

After `apply_replay_plan(plan)` returns, calling
`verify_replay(pin)` must return None — i.e. a fresh pin
captured from the now-configured env is replay-equivalent to
the original pin. If verify_replay returns a mismatch, either
the pin's schema is incomplete (a v5 schema bump needed) or
the replayer skipped a field. Either way it's a hard error,
not a warning.
"""

from __future__ import annotations

import contextlib
import hashlib
import os
import threading
from dataclasses import dataclass, field
from typing import Iterator

from src.polaris_graph.audit_ir.model_pin import (
    DEFAULT_REPLAY_ENV_VARS,
    ModelPin,
    capture_env_snapshot,
    capture_pin,
    pins_equivalent_for_replay,
)


# Module-level non-reentrant lock guarding os.environ mutation.
# Per Codex round-1 finding (commit 1ba9144): same-process
# nested/concurrent replays silently stomped each other in v1.
# v2 turns the stomp into a hard `PinReplayError` so misuse is
# loud — phase 2 v1 is single-threaded by design and should
# fail closed when callers violate that boundary.
_REPLAY_LOCK = threading.Lock()


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class PinReplayError(Exception):
    """Base for replay errors."""


class MissingPromptTextError(PinReplayError):
    """Raised when replay needs a prompt's text (not just its
    hash) but the operator didn't supply it. The pin's
    prompt_version_hash captures shape but not content; full
    restoration requires the original prompt text from the
    audit bundle."""


class PromptHashMismatchError(PinReplayError):
    """Raised when the operator supplies prompt text whose
    SHA-256 doesn't match the pin's prompt_version_hashes
    entry for that role. Per Codex round-1 finding (commit
    1ba9144): presence-check alone allowed wrong prompts to
    pass the 'ready to restore' gate. v2 hash-checks
    supplied text and rejects mismatches loudly."""


class ConcurrentReplayError(PinReplayError):
    """Raised when a replay tries to enter
    `apply_replay_plan` while another replay is already
    active in the process. os.environ is process-global;
    same-process concurrent or nested replays would stomp
    each other. Phase 2 v1 is single-threaded — process-pool
    isolation is phase 2 v2 territory."""


class ReplayVerificationError(PinReplayError):
    """Raised when verify_replay finds a mismatch — the
    fresh-captured pin doesn't match the source pin under
    pins_equivalent_for_replay. Either the schema missed a
    field or the replayer skipped one."""


# ---------------------------------------------------------------------------
# Plan + mismatch records
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class EnvMutation:
    """One env-var change to apply during replay.

    `op` is one of:
      - "set": os.environ[name] = value (value is a str,
         possibly "")
      - "delete": os.environ.pop(name, None)
    """

    name: str
    op: str  # "set" | "delete"
    value: str | None  # str when op="set"; None when op="delete"


@dataclass(frozen=True)
class ReplayPlan:
    """Pure description of what replay would do — no side
    effects. Apply via `apply_replay_plan(plan)`.
    """

    pin: ModelPin
    env_mutations: tuple[EnvMutation, ...]


@dataclass(frozen=True)
class ReplayMismatch:
    """One field that differs between the source pin and a
    fresh-captured pin after replay.

    A non-empty list of mismatches means replay didn't fully
    reproduce the captured config.
    """

    field_name: str
    expected: object
    actual: object


# ---------------------------------------------------------------------------
# Build plan
# ---------------------------------------------------------------------------


def build_replay_plan(pin: ModelPin) -> ReplayPlan:
    """Derive the set of mutations needed to replay `pin`.

    Pure: reads `pin` + current `os.environ`, returns a plan.
    No side effects.

    Currently only env mutations are planned — model + prompt
    + validation-set restoration are out of scope per phase 2
    v1 boundaries (see module docstring).
    """
    if not isinstance(pin, ModelPin):
        raise PinReplayError(
            f"build_replay_plan needs a ModelPin, "
            f"got {type(pin).__name__}"
        )

    mutations: list[EnvMutation] = []
    for name, target in pin.env_snapshot.items():
        # `target` is `str | None`. Phase 1 v4 semantics:
        #   None  → var was unset at capture; replay must
        #           DELETE the env var.
        #   ""    → var was explicitly set to empty string;
        #           replay must SET it (matters because
        #           int(os.getenv("X", "default")) returns
        #           "default" when X is unset but "" when X
        #           is set to "").
        #   other → SET to that string.
        if target is None:
            mutations.append(
                EnvMutation(name=name, op="delete", value=None)
            )
        else:
            mutations.append(
                EnvMutation(name=name, op="set", value=target)
            )

    return ReplayPlan(
        pin=pin,
        env_mutations=tuple(mutations),
    )


# ---------------------------------------------------------------------------
# Apply (reversible context manager)
# ---------------------------------------------------------------------------


@contextlib.contextmanager
def apply_replay_plan(plan: ReplayPlan) -> Iterator[ReplayPlan]:
    """Apply a replay plan. Reversible context manager.

    Captures the current value of every var the plan touches
    BEFORE mutating, then restores on `__exit__` (success or
    exception). Reversibility is REQUIRED — replay must not
    pollute the process env beyond its `with` block.

    Phase 2 v1 boundary: single-threaded only. Same-process
    concurrent or nested calls raise
    `ConcurrentReplayError`. The module holds a non-reentrant
    `threading.Lock` to enforce this — misuse is loud, not
    silent stomping.

    Phase 2 v2 may add process-pool isolation (subprocess per
    replay) so concurrent replays become safe.
    """
    if not isinstance(plan, ReplayPlan):
        raise PinReplayError(
            f"apply_replay_plan needs ReplayPlan, "
            f"got {type(plan).__name__}"
        )

    # Try to acquire the module-level lock without blocking.
    # If another replay holds it, fail loudly — concurrent
    # replays would stomp each other's env restoration.
    if not _REPLAY_LOCK.acquire(blocking=False):
        raise ConcurrentReplayError(
            "another replay is already active in this process; "
            "phase 2 v1 is single-threaded — wait for the "
            "outer `with apply_replay_plan` to exit, or use "
            "subprocess isolation"
        )
    try:
        # Snapshot prior state. None means "var was unset"; str
        # means "var was set to that string". Symmetric with
        # the pin schema.
        prior: dict[str, str | None] = {}
        for mut in plan.env_mutations:
            prior[mut.name] = os.environ.get(mut.name)

        try:
            # Apply.
            for mut in plan.env_mutations:
                if mut.op == "delete":
                    os.environ.pop(mut.name, None)
                elif mut.op == "set":
                    if mut.value is None:
                        raise PinReplayError(
                            f"set mutation for {mut.name!r} "
                            f"has value=None (should be str)"
                        )
                    os.environ[mut.name] = mut.value
                else:
                    raise PinReplayError(
                        f"unknown mutation op: {mut.op!r}"
                    )
            yield plan
        finally:
            # Restore — even on exception. Order doesn't
            # matter since each var's prior is captured
            # independently.
            for name, prior_value in prior.items():
                if prior_value is None:
                    os.environ.pop(name, None)
                else:
                    os.environ[name] = prior_value
    finally:
        _REPLAY_LOCK.release()


# ---------------------------------------------------------------------------
# Verify
# ---------------------------------------------------------------------------


def verify_replay(
    pin: ModelPin, *, run_id: str = "verify_replay"
) -> tuple[ReplayMismatch, ...]:
    """Capture a fresh pin from the current env and compare to
    `pin` via pins_equivalent_for_replay.

    Returns a tuple of mismatches — empty tuple = full match.
    Use this INSIDE the `with apply_replay_plan(...)` block;
    outside the block, env is restored to its pre-replay state
    and verification is meaningless.

    Important caveat: this only verifies env_snapshot fidelity.
    Multi-model + prompts + retrieval versions + inductor are
    captured as the SAME values from the source pin (we can't
    fresh-capture them because phase 2 v1 doesn't restore
    them — see module docstring boundaries 2-4). So a fresh
    pin captured here will reuse the source pin's
    llm_models / llm_providers / etc. The empirical test is
    really: does env_snapshot round-trip cleanly?
    """
    if not isinstance(pin, ModelPin):
        raise PinReplayError(
            f"verify_replay needs ModelPin, "
            f"got {type(pin).__name__}"
        )

    # Fresh-capture an env snapshot using the same names the
    # source pin captured — apples-to-apples.
    fresh_env = capture_env_snapshot(tuple(pin.env_snapshot))

    # Build a fresh pin reusing the source pin's non-env
    # fields. We can't restore models / prompts / etc. in
    # phase 2 v1, so re-asserting them is the empirical
    # equivalent of "the env-only roundtrip works".
    fresh_pin = capture_pin(
        run_id=run_id,
        llm_models=dict(pin.llm_models),
        llm_providers=dict(pin.llm_providers) or None,
        retrieval_source_versions=dict(pin.retrieval_source_versions),
        inductor_type=pin.inductor_type,
        env_snapshot=fresh_env,
    )
    # Note: the fresh pin's inductor_version_hash will be None
    # (we didn't pass profile_text). For pure env-roundtrip
    # verification, force-equate them via dataclass replace.
    from dataclasses import replace
    fresh_pin = replace(
        fresh_pin,
        inductor_version_hash=pin.inductor_version_hash,
        validation_set_hash=pin.validation_set_hash,
        prompt_version_hashes=dict(pin.prompt_version_hashes),
    )

    if pins_equivalent_for_replay(pin, fresh_pin):
        return ()

    # Walk the fields and report each mismatch.
    mismatches: list[ReplayMismatch] = []
    if pin.pin_schema_version != fresh_pin.pin_schema_version:
        mismatches.append(
            ReplayMismatch(
                "pin_schema_version",
                pin.pin_schema_version,
                fresh_pin.pin_schema_version,
            )
        )
    # env_snapshot is the only field replay actually sets, so
    # walk per-key.
    for key in set(pin.env_snapshot) | set(fresh_pin.env_snapshot):
        a = pin.env_snapshot.get(key)
        b = fresh_pin.env_snapshot.get(key)
        if a != b:
            mismatches.append(
                ReplayMismatch(
                    f"env_snapshot[{key}]", a, b,
                )
            )
    return tuple(mismatches)


def replay_pin(
    pin: ModelPin,
    *,
    require_prompt_text: bool = False,
    prompt_text: dict[str, str] | None = None,
) -> ReplayPlan:
    """Convenience wrapper: validate + build plan.

    `require_prompt_text=True` enforces that the operator has
    supplied prompt_text for every role in
    pin.prompt_version_hashes. Without prompt text, hash-only
    pins can be VERIFIED but not RESTORED — the contract is
    documented in the module docstring (boundary 2).

    If require_prompt_text=True and any role's text is missing,
    raises MissingPromptTextError listing the unmatched roles.
    Phase 2 v1 returns the plan but does NOT actually use
    prompt_text — wiring into the system prompt depends on
    consumer integration which is phase-2-of-phase-2.
    """
    if not isinstance(pin, ModelPin):
        raise PinReplayError(
            f"replay_pin needs ModelPin, "
            f"got {type(pin).__name__}"
        )

    if require_prompt_text:
        if prompt_text is None:
            prompt_text = {}
        # Operator must supply text for every captured prompt
        # hash. If they don't, fail loudly.
        missing = [
            role
            for role in pin.prompt_version_hashes
            if role not in prompt_text
            or not prompt_text[role].strip()
        ]
        if missing:
            raise MissingPromptTextError(
                f"prompt text missing for roles: {sorted(missing)}; "
                f"replay cannot restore prompts from hash alone"
            )
        # Per Codex round-1 finding: presence-only check let
        # an operator pass arbitrary non-blank text and have
        # it accepted as "the captured prompt". Hash-check
        # the supplied text against pin.prompt_version_hashes
        # so wrong prompts can't slip through the gate.
        mismatches: list[tuple[str, str, str]] = []
        for role, expected_hash in pin.prompt_version_hashes.items():
            text = prompt_text[role]
            actual_hash = hashlib.sha256(
                text.encode("utf-8")
            ).hexdigest()
            if actual_hash != expected_hash:
                mismatches.append((role, expected_hash, actual_hash))
        if mismatches:
            details = "; ".join(
                f"{role} expected={exp[:12]}... actual={act[:12]}..."
                for role, exp, act in mismatches
            )
            raise PromptHashMismatchError(
                f"supplied prompt text doesn't hash-match the "
                f"pin's prompt_version_hashes: {details}"
            )

    return build_replay_plan(pin)
