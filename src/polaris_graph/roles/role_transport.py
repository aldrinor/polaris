"""Shared transport + result types for the POLARIS 4-role adapters (I-meta-002 sub-PR-4).

Pure data contracts + a typing Protocol. There is NO network here and NO spend: the
real transport (the thing that actually performs an LLM completion) is sub-PR-5 and is
DEPENDENCY-INJECTED into each adapter. Tests inject a MOCK transport that returns canned
`RoleResponse`s. This module deliberately does NOT import `openrouter_client` (the real
transport that wraps it is sub-PR-5).

Per-call identity capture (iter-3 fix, Codex P1-a): every adapter returns ONE
`RoleCallRecord` per transport completion so the Path-B identity gate (sub-PR-5) can verify
`served==pinned` for EVERY call — no completion may be hidden inside an adapter without its
own record. Single-call roles (Sentinel, Judge) emit a 1-element list; Mirror (two passes)
emits a 2-element list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from src.polaris_graph.roles.mirror_contract import CitationSpan


@dataclass(frozen=True)
class EvidenceDocument:
    """One evidence document handed to a role, carrying a STABLE `doc_id`.

    The `doc_id` is the citation identity the Mirror adapter binds against (iter-4): a
    citation span may only point at a `doc_id` that appears in the supplied documents, so
    the document set is the ground-truth identity pool, not a free-text payload.
    """

    doc_id: str
    text: str


@dataclass
class RoleRequest:
    """A role-tagged request to the transport.

    `role` and `model_slug` are the pinned identity the Path-B gate (sub-PR-5) checks the
    served identity against. The payload is carried as either a chat `messages` list OR a
    single `prompt` string (a role uses whichever its serving convention requires). `params`
    holds everything else the transport needs, including the structured-output spec
    (`structured_outputs`), the bounded `max_tokens`, and the `documents` payload (kept in
    `params["documents"]` so it is introspectable by the adequacy/identity checks and the
    tests).
    """

    role: str
    model_slug: str
    messages: list[dict] | None = None
    prompt: str | None = None
    params: dict[str, Any] = field(default_factory=dict)


@dataclass
class RoleResponse:
    """A transport completion.

    `raw_text` is the model's raw output string (parsed by the role's sub-PR-2 contract).
    `served_model` is the identity the transport actually served (the Path-B gate compares
    it to the pinned `model_slug`). `citations` is the OPTIONAL structured-span path for the
    managed Mirror route (iter-3 P1-b): when the transport already normalized citations into
    spans, they arrive here; otherwise the adapter parses `<co>` spans out of `raw_text`.
    """

    raw_text: str
    served_model: str | None = None
    usage: dict[str, Any] | None = None
    citations: list[CitationSpan] | None = None


@dataclass
class RoleCallRecord:
    """One captured transport completion for the Path-B identity/capture gate (sub-PR-5).

    Echoes the pinned role + requested `model_slug` and the `served_model` the transport
    reported, alongside the `raw_text` and the role-contract `parsed` result. EXACTLY one
    record is emitted per transport completion (iter-3 P1-a).
    """

    role: str
    model_slug: str
    served_model: str | None
    raw_text: str
    parsed: Any


@runtime_checkable
class RoleTransport(Protocol):
    """The injected completion boundary.

    The real implementation (sub-PR-5) performs the actual LLM call; in this PR every caller
    injects a mock. Synchronous by design — the per-axis live call shape it mirrors
    (`live_judge.py`) is synchronous.
    """

    def complete(self, request: RoleRequest) -> RoleResponse:
        """Perform one completion for `request` and return its `RoleResponse`."""
        ...
