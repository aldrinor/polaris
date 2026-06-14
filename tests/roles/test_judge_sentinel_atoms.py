"""F05 (GH #1254) — Sentinel atom-detail threading into the terminal Judge prompt.

The D8 Judge rubber-stamped doc-level "unsupported" Sentinel signals because it only ever saw the
COMPRESSED grounded/ungrounded token, never the Sentinel's per-atom "why". This fix threads the
Sentinel decomposition's `[{atom, status, why}, ...]` detail into the Judge prompt — behind the
`PG_JUDGE_SENTINEL_ATOMS` flag (default OFF, byte-identical) — and adds an anti-rubber-stamp
instruction: a Sentinel-flagged unsupported atom may only be overturned with a per-atom
span-grounded rebuttal, never dismissed as "metadata" or "a direct match".

These tests prove, offline (NO network):
  - flag OFF (default): `build_judge_request` is BYTE-IDENTICAL to the locked benchmark prompt even
    when atom detail is supplied (the threading param is inert until the flag is set);
  - flag ON: the per-atom "why" + the anti-rubber-stamp instruction appear in the prompt, while the
    locked CLAIM/EVIDENCE/SIGNAL scaffold + the hard-enum params are byte-unchanged;
  - the 02-003 "implemented"-vs-"study" atom shape composes to UNSUPPORTED — produced by the
    UNCONDITIONAL Sentinel-override (UNTOUCHED by F05), the atom threading only enriches the prompt;
  - REGRESSION-LOCK: a Sentinel-UNGROUNDED claim with a confidently-VERIFIED Judge, WITH THE FLAG ON,
    STILL resolves UNSUPPORTED — proving the threading added NO escape clause that hands authority
    back to the Judge.

All assertions are STRUCTURAL (prompt text) or composition-verdict, never an evaluation of a live
model.
"""

from __future__ import annotations

import json

import pytest

from src.polaris_graph.roles.judge_adapter import (
    _ARBITER_INSTRUCTION,
    _SENTINEL_ATOMS_FLAG,
    _SENTINEL_ATOMS_INSTRUCTION,
    build_judge_request,
)
from src.polaris_graph.roles.judge_contract import JUDGE_CHOICES
from src.polaris_graph.roles.role_pipeline import run_claim_pipeline
from src.polaris_graph.roles.role_transport import (
    EvidenceDocument,
    RoleRequest,
    RoleResponse,
)
from src.polaris_graph.roles.sentinel_contract import parse_sentinel_decomposition

_MODEL = "qwen/qwen3.6-35b-a3b"
_CLAIM = "The researchers implemented a staggered introduction design."
_EVIDENCE = "Abstract We study the staggered introduction of a generative AI-based conversational assistant."
_MIRROR = "Research Methodology"
_SENTINEL = "ungrounded"

# The EXACT 02-003 Sentinel decomposition output from the dead-run forensic
# (.codex/I-arch-004/deadrun_artifacts/drb_72_ai_labor/four_role_role_calls.jsonl, claim
# 02-003-84d92a96): atom "implemented" -> unsupported, "rolling out" -> supported.
_O2_003_SENTINEL_RAW = json.dumps(
    {
        "atoms": [
            {
                "atom": "The researchers implemented a staggered introduction design",
                "type": "mechanism",
                "status": "unsupported",
                "why": "The span states they 'study the staggered introduction', not that they implemented it.",
            },
            {
                "atom": "rolling out the AI tool in phases across different agent groups over time",
                "type": "mechanism",
                "status": "supported",
                "why": "The span's 'staggered introduction' implies phases over time across groups.",
            },
        ],
        "unsupported_atoms": 1,
        "verdict": "unsupported",
    }
)


def _o2_003_atoms() -> list[dict]:
    """The per-atom list as the production parser surfaces it on the 02-003 output."""
    result = parse_sentinel_decomposition(_O2_003_SENTINEL_RAW)
    assert result.atoms is not None, "decomposition parser must carry the atom detail (F05)"
    return result.atoms


def _expected_off_prompt() -> str:
    """The locked benchmark prompt, reconstructed from the original instruction constant."""
    return (
        f"{_ARBITER_INSTRUCTION}\n\n"
        f"CLAIM:\n{_CLAIM}\n\n"
        f"EVIDENCE:\n{_EVIDENCE}\n\n"
        f"MIRROR_SIGNAL: {_MIRROR}\n"
        f"SENTINEL_SIGNAL: {_SENTINEL}\n\n"
        f"Allowed verdicts: {JUDGE_CHOICES}"
    )


# === (a) structural: flag OFF byte-identical even WITH atoms; flag ON shows per-atom why ==========
def test_flag_off_is_byte_identical_even_with_atoms(monkeypatch: pytest.MonkeyPatch) -> None:
    """The threading param is INERT with the flag OFF: supplying the full 02-003 atom detail leaves
    the prompt byte-identical to the locked benchmark (the §-1.3 OFF-path-byte-identical guarantee)."""
    monkeypatch.delenv(_SENTINEL_ATOMS_FLAG, raising=False)
    request = build_judge_request(
        _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL,
        sentinel_atoms=_o2_003_atoms(),
    )
    assert request.prompt == _expected_off_prompt()
    # The Sentinel's "implemented"-vs-"study" why must NOT have leaked into the OFF prompt.
    assert "not that they implemented it" not in request.prompt
    assert _SENTINEL_ATOMS_INSTRUCTION not in request.prompt


def test_flag_off_explicit_falsey_value_is_also_locked_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(_SENTINEL_ATOMS_FLAG, "0")
    request = build_judge_request(
        _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL,
        sentinel_atoms=_o2_003_atoms(),
    )
    assert request.prompt == _expected_off_prompt()


def test_flag_on_threads_o2_003_per_atom_why_and_anti_rubber_stamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ACCEPT (a): with the flag ON, the Judge prompt for the 02-003 claim now carries the Sentinel's
    per-atom 'implemented'-vs-'study' why AND the anti-rubber-stamp instruction — the exact detail the
    Judge dismissed as 'a direct match' in the forensic. (fails-before / passes-after the flag.)"""
    monkeypatch.setenv(_SENTINEL_ATOMS_FLAG, "1")
    request = build_judge_request(
        _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL,
        sentinel_atoms=_o2_003_atoms(),
    )
    # the unsupported atom + its why are present.
    assert "The researchers implemented a staggered introduction design" in request.prompt
    assert "not that they implemented it" in request.prompt
    assert "[unsupported]" in request.prompt
    # the anti-rubber-stamp directive is present.
    assert _SENTINEL_ATOMS_INSTRUCTION in request.prompt
    assert "do not dismiss" in request.prompt.lower()


def test_flag_on_preserves_locked_scaffold_and_params(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Flag ON appends AFTER the locked scaffold + leaves the hard-enum params untouched (the atom
    block adds prompt TEXT only — no verdict-handling, threshold, or enum change)."""
    monkeypatch.setenv(_SENTINEL_ATOMS_FLAG, "on")
    on_request = build_judge_request(
        _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL,
        sentinel_atoms=_o2_003_atoms(),
    )
    monkeypatch.delenv(_SENTINEL_ATOMS_FLAG, raising=False)
    off_request = build_judge_request(
        _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL,
        sentinel_atoms=_o2_003_atoms(),
    )
    # the locked scaffold is a byte-identical PREFIX of the flag-ON prompt.
    assert on_request.prompt.startswith(_expected_off_prompt())
    # params (hard-enum + max_tokens) are byte-identical across flag states.
    assert on_request.params == off_request.params
    assert on_request.params["structured_outputs"]["choice"] == JUDGE_CHOICES
    assert "guided_choice" not in on_request.params
    # ON is strictly longer (added atom block only).
    assert len(on_request.prompt) > len(off_request.prompt)


def test_flag_on_no_atoms_is_locked_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flag ON but no atom detail (None / empty) adds NOTHING — a guardian/noninverted-mode Sentinel
    carries no atoms, so the Judge prompt is the locked benchmark for those claims."""
    monkeypatch.setenv(_SENTINEL_ATOMS_FLAG, "1")
    for atoms in (None, [], [{}], ["not-a-dict"]):
        request = build_judge_request(
            _CLAIM, _EVIDENCE, _MIRROR, _SENTINEL, model_slug=_MODEL,
            sentinel_atoms=atoms,  # type: ignore[arg-type]
        )
        assert request.prompt == _expected_off_prompt(), atoms


# === pipeline composition: the override (UNTOUCHED) produces the 02-003 BLOCK; threading is inert ==
_PIPE_EVIDENCE = [
    EvidenceDocument(
        doc_id="brynjolfsson_genai_at_work",
        text="Abstract We study the staggered introduction of a generative AI-based conversational assistant using data from 5,172 customer-support agents.",
    )
]
_PIPE_SLUGS = {
    "mirror": "z-ai/glm-5.1",
    "sentinel": "minimax/minimax-m2",
    "judge": "qwen/qwen3.6-35b-a3b",
}
_TIMESTAMP = "2026-06-14T00:00:00Z"


class _O2003Transport:
    """Replays the 02-003 four-role shape: Mirror grounds a citation, the Sentinel returns the real
    02-003 decomposition (verdict 'unsupported', one unsupported atom), the Judge confidently rubber-
    stamps VERIFIED. Captures the Judge request so the test can inspect the threaded atom detail."""

    def __init__(self) -> None:
        self.judge_request: RoleRequest | None = None

    def complete(self, request: RoleRequest) -> RoleResponse:
        if request.role == "mirror":
            if "pass2_input" in request.params:
                content_hash = request.params["pass2_input"]["content_hash"]
                payload = {"content_hash": content_hash, "classification": "Research Methodology"}
                return RoleResponse(raw_text=json.dumps(payload), served_model=request.model_slug)
            from src.polaris_graph.roles.mirror_contract import CitationSpan

            return RoleResponse(
                raw_text="The researchers implemented a <co>staggered introduction</co> design.",
                served_model=request.model_slug,
                citations=[
                    CitationSpan(span_start=0, span_end=8, doc_ids=("brynjolfsson_genai_at_work",))
                ],
            )
        if request.role == "sentinel":
            return RoleResponse(raw_text=_O2_003_SENTINEL_RAW, served_model=request.model_slug)
        if request.role == "judge":
            self.judge_request = request
            return RoleResponse(raw_text="VERIFIED", served_model=request.model_slug)
        raise AssertionError(f"unexpected role {request.role!r}")


def _run_o2_003(transport, monkeypatch):
    # Force the certified decomposition Sentinel mode (minimax slug already routes there, but pin it
    # so the test is independent of the default-mode derivation).
    monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "decomposition")
    return run_claim_pipeline(
        transport,
        claim_id="02-003-84d92a96",
        claim="The researchers implemented a staggered introduction design.",
        evidence_documents=_PIPE_EVIDENCE,
        severity="S3",
        s0_categories=[],
        model_slugs=_PIPE_SLUGS,
        timestamp=_TIMESTAMP,
    )


def test_o2_003_composes_to_unsupported_via_override(monkeypatch: pytest.MonkeyPatch) -> None:
    """ACCEPT (a) — composition: the 02-003 claim BLOCKS (final UNSUPPORTED) even though the Judge says
    VERIFIED. NOTE: the BLOCK is produced by the UNCONDITIONAL Sentinel-override (the Sentinel parses
    UNGROUNDED via its 1 unsupported atom) — F05 did NOT touch that override and does NOT flip this
    verdict. This composition test documents the end-to-end BLOCKED state the override guarantees."""
    monkeypatch.setenv(_SENTINEL_ATOMS_FLAG, "1")
    transport = _O2003Transport()
    result = _run_o2_003(transport, monkeypatch)
    assert result.raw_judge_verdict == "VERIFIED"          # the Judge still rubber-stamps in isolation
    assert result.sentinel_result is not None
    assert result.sentinel_result.parsed_ok is True
    assert result.final_verdict == "UNSUPPORTED"           # the unconditional override BLOCKS it
    assert result.d8_row.verdict == "UNSUPPORTED"


def test_o2_003_threads_atom_why_into_judge_prompt(monkeypatch: pytest.MonkeyPatch) -> None:
    """The wiring proof: with the flag ON, the Judge call for 02-003 actually received the Sentinel's
    per-atom 'implemented'-vs-'study' why (so a model Judge could no longer rubber-stamp blind)."""
    monkeypatch.setenv(_SENTINEL_ATOMS_FLAG, "1")
    transport = _O2003Transport()
    _run_o2_003(transport, monkeypatch)
    assert transport.judge_request is not None
    prompt = transport.judge_request.prompt or ""
    assert "not that they implemented it" in prompt
    assert _SENTINEL_ATOMS_INSTRUCTION in prompt


def test_o2_003_flag_off_judge_prompt_has_no_atom_detail(monkeypatch: pytest.MonkeyPatch) -> None:
    """Flag OFF: the Judge prompt in the live pipeline is the locked benchmark — no atom detail leaks
    (and the override STILL blocks the claim, so OFF is at least as strict)."""
    monkeypatch.delenv(_SENTINEL_ATOMS_FLAG, raising=False)
    transport = _O2003Transport()
    result = _run_o2_003(transport, monkeypatch)
    assert transport.judge_request is not None
    prompt = transport.judge_request.prompt or ""
    assert "not that they implemented it" not in prompt
    assert _SENTINEL_ATOMS_INSTRUCTION not in prompt
    # the override still blocks even with no threading.
    assert result.final_verdict == "UNSUPPORTED"


# === (b) REGRESSION-LOCK: flag ON adds NO escape clause — UNGROUNDED + VERIFIED Judge still BLOCKS ==
class _UngroundedConfidentJudgeTransport:
    """A Sentinel that parses UNGROUNDED (verdict 'unsupported', 1 unsupported atom) + a Judge that
    confidently returns VERIFIED. The unconditional override MUST still force UNSUPPORTED — with the
    flag ON. If the atom threading ever handed authority back to the Judge, this would flip to
    VERIFIED, which is the faithfulness RELAXATION the spec forbids (auto-P0)."""

    def complete(self, request: RoleRequest) -> RoleResponse:
        if request.role == "mirror":
            if "pass2_input" in request.params:
                content_hash = request.params["pass2_input"]["content_hash"]
                return RoleResponse(
                    raw_text=json.dumps({"content_hash": content_hash, "classification": "x"}),
                    served_model=request.model_slug,
                )
            from src.polaris_graph.roles.mirror_contract import CitationSpan

            return RoleResponse(
                raw_text="grounded answer",
                served_model=request.model_slug,
                citations=[
                    CitationSpan(span_start=0, span_end=8, doc_ids=("brynjolfsson_genai_at_work",))
                ],
            )
        if request.role == "sentinel":
            return RoleResponse(raw_text=_O2_003_SENTINEL_RAW, served_model=request.model_slug)
        if request.role == "judge":
            return RoleResponse(raw_text="VERIFIED", served_model=request.model_slug)
        raise AssertionError(f"unexpected role {request.role!r}")


def test_regression_lock_flag_on_ungrounded_plus_verified_judge_still_unsupported(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """ACCEPT (b): WITH THE FLAG ON, a Sentinel-UNGROUNDED claim + a confidently-VERIFIED Judge STILL
    resolves UNSUPPORTED. This proves F05 added NO escape clause — the unconditional override is
    intact, the atom threading only enriches the Judge prompt and never overturns the override."""
    monkeypatch.setenv(_SENTINEL_ATOMS_FLAG, "1")
    monkeypatch.setenv("PG_SENTINEL_GROUNDEDNESS_MODE", "decomposition")
    transport = _UngroundedConfidentJudgeTransport()
    result = run_claim_pipeline(
        transport,
        claim_id="regression-lock-claim",
        claim="The researchers implemented a staggered introduction design.",
        evidence_documents=_PIPE_EVIDENCE,
        severity="S3",
        s0_categories=[],
        model_slugs=_PIPE_SLUGS,
        timestamp=_TIMESTAMP,
    )
    assert result.raw_judge_verdict == "VERIFIED"   # the Judge confidently rebuts
    assert result.final_verdict == "UNSUPPORTED"    # the override still BLOCKS — no escape clause
    assert result.d8_row.verdict == "UNSUPPORTED"
