"""Judge (Qwen3.6) adapter — terminal-arbiter request builder + LOUD-FAIL caller.

The Judge is the terminal arbiter: it sees the claim, the evidence, and the Mirror +
Sentinel signals, and emits exactly one of the 5 canonical verdicts. It runs self-hosted
under vLLM with a HARD ENUM constraint at decode time — `structured_outputs.choice =
JUDGE_CHOICES` (current vLLM spelling; `guided_choice` is DEPRECATED, F4). Qwen context is
BOUNDED (`max_tokens`); do not assume unbounded.

FAIL LOUD (NOT closed): `parse_judge_verdict` raises `JudgeEnumError` on any non-enum token.
`run_judge` deliberately does NOT wrap that — a missing/garbage arbiter verdict must
propagate, never coerce to a default. (Sentinel/Mirror fail CLOSED; the Judge fails LOUD —
do not pattern-copy a fail-closed wrap here.)
"""

from __future__ import annotations

from src.polaris_graph.roles.judge_contract import (
    JUDGE_CHOICES,
    Verdict,
    parse_judge_verdict,
)
from src.polaris_graph.roles.role_transport import (
    RoleCallRecord,
    RoleRequest,
    RoleResponse,
    RoleTransport,
)

_ROLE = "judge"

# Bounded Qwen context (F4: do not assume unbounded). The verdict is a single enum token,
# so a small ceiling is sufficient and keeps the arbiter from drifting into prose.
_DEFAULT_MAX_TOKENS = 16

# vLLM hard-enum spec key (current spelling, NOT guided_choice).
_STRUCTURED_OUTPUTS_KEY = "structured_outputs"
_CHOICE_KEY = "choice"

_ARBITER_INSTRUCTION = (
    "You are the terminal arbiter. Given the claim, the evidence, and the Mirror and "
    "Sentinel signals below, output exactly one verdict token and nothing else."
)


def build_judge_request(
    claim: str,
    evidence: str,
    mirror_verdict: str,
    sentinel_verdict: str,
    *,
    model_slug: str,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> RoleRequest:
    """Build the terminal-arbiter request with the hard-enum constraint + bounded context.

    `params["structured_outputs"]["choice"]` is `JUDGE_CHOICES` (the 5 canonical verdicts),
    the current vLLM choice-constrained decoding spelling (F4). `max_tokens` is bounded.
    The prompt carries the claim, evidence, and the upstream Mirror + Sentinel signals.
    """
    prompt = (
        f"{_ARBITER_INSTRUCTION}\n\n"
        f"CLAIM:\n{claim}\n\n"
        f"EVIDENCE:\n{evidence}\n\n"
        f"MIRROR_SIGNAL: {mirror_verdict}\n"
        f"SENTINEL_SIGNAL: {sentinel_verdict}\n\n"
        f"Allowed verdicts: {JUDGE_CHOICES}"
    )
    params = {
        _STRUCTURED_OUTPUTS_KEY: {_CHOICE_KEY: JUDGE_CHOICES},
        "max_tokens": max_tokens,
    }
    return RoleRequest(
        role=_ROLE,
        model_slug=model_slug,
        prompt=prompt,
        params=params,
    )


def run_judge(
    transport: RoleTransport,
    claim: str,
    evidence: str,
    mirror_verdict: str,
    sentinel_verdict: str,
    *,
    model_slug: str,
    max_tokens: int = _DEFAULT_MAX_TOKENS,
) -> tuple[Verdict, list[RoleCallRecord]]:
    """Call the transport once and parse the enum verdict, FAIL LOUD.

    Returns the `Verdict` and a 1-element `RoleCallRecord` list (one record per completion,
    iter-3 P1-a). `parse_judge_verdict` raises `JudgeEnumError` on any non-enum token; that
    propagates by design — there is NO silent default for the terminal arbiter.
    """
    request = build_judge_request(
        claim,
        evidence,
        mirror_verdict,
        sentinel_verdict,
        model_slug=model_slug,
        max_tokens=max_tokens,
    )
    response: RoleResponse = transport.complete(request)
    # FAIL LOUD: a non-enum verdict raises JudgeEnumError here and is NOT caught.
    verdict = parse_judge_verdict(response.raw_text)
    record = RoleCallRecord(
        role=_ROLE,
        model_slug=model_slug,
        served_model=response.served_model,
        raw_text=response.raw_text,
        parsed=verdict,
    )
    return verdict, [record]
