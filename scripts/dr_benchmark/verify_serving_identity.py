"""Serving-identity probe for the 3 self-hosted verifier roles — I-meta-002 PR-8 / M2.

Given the three role base URLs (resolved from env: ``PG_<ROLE>_BASE_URL`` /
``PG_<ROLE>_API_KEY``), this probe queries each vLLM server's ``/v1/models`` and
asserts that the SERVED model id equals the role's locked ``model_slug`` from
``config/architecture/polaris_runtime_lock.yaml``.

Unlike ``openai_compatible_transport``, this probe targets self-host-only roles
and intentionally does NOT reuse that transport's ``OPENROUTER_API_KEY`` fallback:
the only auth source is ``PG_<ROLE>_API_KEY``, and when it is unset NO
Authorization header is sent (a self-hosted vLLM without ``--api-key`` needs none).
This guarantees the probe can never leak the OpenRouter key to a self-host box.

This is the deterministic identity check the M4 ``served==pinned`` gate trusts:
before a paid benchmark run, the operator runs this probe to confirm each box is
serving the EXACT pinned model. ``/v1/models`` is the right primary vLLM identity
surface (Codex brief-gate P2): vLLM advertises its ``--served-model-name`` as the
``id`` of the single entry in ``data``. An optional 1-token chat completion is a
readiness-only nicety and is intentionally NOT performed here (it would spend).

No-spend / no-network-in-tests boundary (LAW II): the HTTP client is
DEPENDENCY-INJECTED via ``probe_serving_identity(http_client=...)``. Tests pass an
``httpx.Client(transport=httpx.MockTransport(...))`` returning canned ``/v1/models``
bodies — there is NO network in any code path pytest exercises. The ``__main__``
entrypoint builds a real ``httpx.Client``; that path is run ONLY by the operator
during the paid canary, never by tests.

Fail loud (LAW II): a served id that does not match the lock, an unreachable
endpoint, a malformed ``/v1/models`` body, or an UNSET ``PG_<ROLE>_BASE_URL``
all raise ``ServingIdentityError`` (the probe never returns a silently-degraded
"reachable but unknown" success).
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass

import httpx

from scripts.architecture.verify_lock import load_lock

# The three self-hosted verifier roles this probe covers. The generator runs on
# OpenRouter (serving_route: openrouter) and is HARD-EXCLUDED — it is never probed.
SELF_HOST_ROLES = ("mirror", "sentinel", "judge")

# OpenAI-compatible model-listing path appended to each role's base_url. This is
# the vLLM identity surface: data[0].id == the launched --served-model-name.
_MODELS_PATH = "/v1/models"

# Per-role env var stems (LAW VI), identical to openai_compatible_transport.
# NOTE: no OPENROUTER_API_KEY fallback here. The probe targets self-host-only
# roles, so it intentionally does NOT reuse the transport's OpenRouter fallback —
# this prevents leaking the OpenRouter key to a self-host URL (Codex P2).
_BASE_URL_ENV_TEMPLATE = "PG_{role}_BASE_URL"
_API_KEY_ENV_TEMPLATE = "PG_{role}_API_KEY"

# Reuse the shared LLM timeout knob (LAW VI): same env var, same fallback as the
# transport, so a probe and a real completion share one configured timeout.
_TIMEOUT_SECONDS = int(os.getenv("PG_LLM_TIMEOUT_SECONDS", "90"))


class ServingIdentityError(RuntimeError):
    """A self-host serving-identity check failed loudly.

    Raised on an unset base-url env, an unreachable / non-200 endpoint, a
    malformed ``/v1/models`` body, or a served model id that does not equal the
    locked slug. The probe NEVER returns a silently-degraded success.
    """


@dataclass(frozen=True)
class RoleIdentityReport:
    """Structured per-role result of the serving-identity probe.

    ``served_model`` is the id vLLM advertises at ``/v1/models`` (its
    ``--served-model-name``); ``expected_slug`` is the lock-pinned ``model_slug``;
    ``matches_lock`` is True iff they are equal. ``reachable`` is True iff the
    endpoint answered HTTP 200 with a parseable ``/v1/models`` body.
    """

    role: str
    base_url: str
    expected_slug: str
    reachable: bool
    served_model: str | None
    matches_lock: bool


def _expected_slugs() -> dict[str, str]:
    """Lock-pinned ``model_slug`` per self-host role (the expected served ids).

    Sourced from the single machine-readable runtime lock via ``load_lock`` so the
    probe's expectations can never drift from the architecture lock (LAW VI).
    """
    lock = load_lock()
    required_roles = lock["required_roles"]
    return {role: required_roles[role]["model_slug"] for role in SELF_HOST_ROLES}


def _resolve_base_url(role: str) -> str:
    """Resolve ``PG_<ROLE>_BASE_URL`` for a self-host role; fail loud if unset.

    Mirrors ``openai_compatible_transport.role_endpoint``: a self-host role with no
    configured endpoint is a deployment error, never a silent default (LAW VI).
    """
    env_name = _BASE_URL_ENV_TEMPLATE.format(role=role.upper())
    base_url = os.getenv(env_name)
    if not base_url:
        raise ServingIdentityError(
            f"{env_name} is not set; the self-hosted {role!r} endpoint must be "
            f"configured before the identity probe can run (LAW VI)."
        )
    return base_url.rstrip("/")


def _resolve_api_key(role: str) -> str:
    """Resolve ``PG_<ROLE>_API_KEY`` only; return "" when unset.

    Intentionally NO ``OPENROUTER_API_KEY`` fallback (unlike the transport): the
    probe targets self-host-only roles, so it must never send the OpenRouter key
    to a self-host box. When this returns "", the probe sends NO Authorization
    header (a self-hosted vLLM without ``--api-key`` needs none).
    """
    return os.getenv(_API_KEY_ENV_TEMPLATE.format(role=role.upper()), "")


def _served_model_id(raw: dict, *, role: str, base_url: str) -> str:
    """Extract the served model id from a vLLM ``/v1/models`` body. Fail loud.

    vLLM returns ``{"object": "list", "data": [{"id": "<served-model-name>", ...}]}``.
    A non-object top-level body, a missing/empty ``data`` array, a non-dict first
    entry, or an absent ``id`` is a malformed identity surface and raises (via the
    structured ``ServingIdentityError`` path, not a bare ``AttributeError``) rather
    than returning a guess.
    """
    if not isinstance(raw, dict):
        raise ServingIdentityError(
            f"{role!r} {base_url}{_MODELS_PATH} returned a non-object body "
            f"({raw!r}); cannot confirm served identity."
        )
    data = raw.get("data")
    if not isinstance(data, list) or not data:
        raise ServingIdentityError(
            f"{role!r} {base_url}{_MODELS_PATH} returned no model list "
            f"(data={data!r}); cannot confirm served identity."
        )
    first = data[0]
    if not isinstance(first, dict):
        raise ServingIdentityError(
            f"{role!r} {base_url}{_MODELS_PATH} first model entry was not an object "
            f"({first!r})."
        )
    served = first.get("id")
    if not isinstance(served, str) or not served.strip():
        raise ServingIdentityError(
            f"{role!r} {base_url}{_MODELS_PATH} model entry carried no id "
            f"({first!r})."
        )
    return served.strip()


def probe_role_identity(
    role: str, *, http_client: httpx.Client, expected_slug: str
) -> RoleIdentityReport:
    """Probe ONE role's ``/v1/models`` and check served id == ``expected_slug``.

    Fails loud (``ServingIdentityError``) on unset base-url env, transport error,
    non-200 status, malformed body, or a served id that differs from the locked
    slug. The ``http_client`` is INJECTED (tests pass a MockTransport stub).
    """
    base_url = _resolve_base_url(role)
    api_key = _resolve_api_key(role)
    url = f"{base_url}{_MODELS_PATH}"
    # Send Authorization ONLY when a per-role key is configured. A self-hosted
    # vLLM launched without --api-key needs none; we never send an empty or
    # foreign Bearer to a self-host box (no-leak — Codex P2).
    headers: dict[str, str] = {}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"

    try:
        response = http_client.get(url, headers=headers, timeout=_TIMEOUT_SECONDS)
    except httpx.HTTPError as exc:
        raise ServingIdentityError(
            f"{role!r} endpoint unreachable at {url}: {exc}"
        ) from exc

    if response.status_code != httpx.codes.OK:
        raise ServingIdentityError(
            f"{role!r} endpoint returned HTTP {response.status_code} at {url}"
        )

    try:
        raw = response.json()
    except (ValueError, httpx.DecodingError) as exc:
        raise ServingIdentityError(
            f"{role!r} endpoint returned a non-JSON body at {url}: {exc}"
        ) from exc

    served_model = _served_model_id(raw, role=role, base_url=base_url)
    matches_lock = served_model == expected_slug
    if not matches_lock:
        raise ServingIdentityError(
            f"{role!r} served model {served_model!r} does NOT match the locked "
            f"slug {expected_slug!r} at {url}; the box is serving the wrong model."
        )
    return RoleIdentityReport(
        role=role,
        base_url=base_url,
        expected_slug=expected_slug,
        reachable=True,
        served_model=served_model,
        matches_lock=True,
    )


def probe_serving_identity(*, http_client: httpx.Client) -> list[RoleIdentityReport]:
    """Probe ALL 3 self-host roles. Raises on the FIRST failure (fail loud).

    Returns one ``RoleIdentityReport`` per role when every served id matches its
    locked slug. The ``http_client`` is INJECTED so tests run with no network.
    """
    expected = _expected_slugs()
    reports: list[RoleIdentityReport] = []
    for role in SELF_HOST_ROLES:
        reports.append(
            probe_role_identity(
                role, http_client=http_client, expected_slug=expected[role]
            )
        )
    return reports


def _format_report(reports: list[RoleIdentityReport]) -> str:
    """Render a structured per-role identity report for the operator."""
    lines = ["serving-identity probe — per role:"]
    for report in reports:
        lines.append(
            f"  {report.role}: reachable={report.reachable} "
            f"served_model={report.served_model!r} "
            f"expected={report.expected_slug!r} "
            f"matches_lock={report.matches_lock}"
        )
    return "\n".join(lines)


def main(stream=sys.stdout) -> int:
    """Operator entrypoint — builds a REAL httpx.Client and probes all 3 roles.

    Run ONLY during the paid canary (the boxes must be up). Exit 0 iff every
    role's served id matches its locked slug; non-zero (and a printed error) on
    any failure. NOT exercised by tests — tests call ``probe_serving_identity``
    with an injected stub.
    """
    with httpx.Client() as client:
        try:
            reports = probe_serving_identity(http_client=client)
        except ServingIdentityError as exc:
            print(f"FAIL: {exc}", file=stream)
            return 1
    print(_format_report(reports), file=stream)
    print("OK — all 3 verifier roles serve their locked slugs.", file=stream)
    return 0


if __name__ == "__main__":
    sys.exit(main())
