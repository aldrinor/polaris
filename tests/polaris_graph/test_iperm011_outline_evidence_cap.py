"""
I-perm-011 (#1182) regression tests: OFF-mode OUTLINE-prompt evidence-menu cap.

CONTEXT
-------
drb_76 ran OFF-mode (`PG_USE_RESEARCH_PLANNER` unset) -> the legacy
`_call_outline` path serialized EVERY row of the ~544-row evidence pool into the
outline prompt. deepseek-v4-pro is reasoning-first; the larger serialized input
induced a longer reasoning stream that consumed the WHOLE 16384-token completion
ceiling on reasoning, emitting ZERO content -> finish_reason=length -> the
FX-01/SF-15 guard correctly raised `ReasoningFirstTruncationError` rather than
ship the scratchpad as VERIFIED prose.

THE FIX (this test exercises it)
--------------------------------
`_call_outline` now bounds the rows SERIALIZED into the outline prompt to
`PG_OUTLINE_MAX_EV` (default 150, env-tunable, read at call time):

  * SMALL pool (`len(evidence) <= cap`): the pre-cap build is BYTE-IDENTICAL —
    verbose per-row digest (incl. the 160-char statement), count == len(evidence).
  * LARGE pool (`len(evidence) > cap`): the menu is sliced to the top-N
    highest-priority rows AND each digest is TERSED (ev_id + tier + title only;
    the 160-char statement is dropped). The count string reflects the bounded N.

INVARIANTS THIS TEST PINS
-------------------------
1. Large pool -> the outline prompt row-count + char-count are bounded, and the
   `Evidence summaries (N rows)` header reflects the bounded N (not the full pool).
2. Small pool -> the outline prompt is BYTE-IDENTICAL to the pre-change build
   (verbose digest, full count).
3. `allowed_ev_ids` validation STILL spans the FULL pool: an ev_id from the
   dropped low-relevance tail is still accepted by `_parse_outline` — proving the
   MENU shrank but the per-section selection/validation/resolution surface did
   NOT (the CRITICAL per-section-unaffected invariant).
"""
from __future__ import annotations

import json

import pytest

import src.polaris_graph.llm.openrouter_client as orc_module
from src.polaris_graph.generator.multi_section_generator import (
    PG_OUTLINE_MAX_EV_DEFAULT,
    _call_outline,
    _parse_outline,
)


# ─────────────────────────────────────────────────────────────────
# Test harness: a fake OpenRouterClient that CAPTURES the outline prompt.
# `_call_outline` imports OpenRouterClient via a function-local
# `from src.polaris_graph.llm.openrouter_client import OpenRouterClient`,
# so we patch the symbol on that SOURCE module.
# ─────────────────────────────────────────────────────────────────

class _FakeResponse:
    def __init__(self, content: str) -> None:
        self.content = content
        self.input_tokens = 10
        self.output_tokens = 10
        self.reasoning_tokens = 0


class _CapturingClient:
    """Records every prompt sent to .generate and returns a fixed valid outline."""

    captured_prompts: list[str] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    async def generate(self, *, prompt, system, max_tokens, temperature):  # noqa: D401
        type(self).captured_prompts.append(prompt)
        # Return a valid 5-section outline JSON so no retry fires (keeps the
        # captured-prompt list to exactly one entry on the happy path).
        outline = {
            "sections": [
                {"title": "Efficacy", "focus": "f", "ev_ids": ["ev_000", "ev_001", "ev_002"]},
                {"title": "Safety", "focus": "f", "ev_ids": ["ev_003", "ev_004", "ev_005"]},
                {"title": "Comparative Effectiveness", "focus": "f", "ev_ids": ["ev_006", "ev_007"]},
                {"title": "Dose Response", "focus": "f", "ev_ids": ["ev_008", "ev_009"]},
                {"title": "Regulatory", "focus": "f", "ev_ids": ["ev_010", "ev_011"]},
            ]
        }
        return _FakeResponse(json.dumps(outline))

    async def close(self) -> None:
        pass


@pytest.fixture(autouse=True)
def _patch_client(monkeypatch):
    _CapturingClient.captured_prompts = []
    monkeypatch.setattr(orc_module, "OpenRouterClient", _CapturingClient)
    # Neutralise the reasoning-trace context tagger (it is a no-op here but keep
    # the import surface stable regardless of sink registration).
    monkeypatch.setattr(
        orc_module, "set_reasoning_call_context", lambda *a, **k: None, raising=False
    )
    yield


def _make_evidence(n: int) -> list[dict]:
    """n evidence rows with a LONG statement so the verbose vs terse digest
    difference is observable in prompt length."""
    long_stmt = "This is a long evidence statement sentence repeated. " * 6  # >160 chars
    rows = []
    for i in range(n):
        rows.append({
            "evidence_id": f"ev_{i:03d}",
            "title": f"Source title number {i} about the research topic",
            "statement": f"[{i}] {long_stmt}",
            "tier": "T2",
        })
    return rows


def _build_expected_verbose_prompt(research_question: str, evidence: list[dict]) -> str:
    """Reproduce the PRE-CAP verbose build byte-for-byte so we can assert the
    small-pool path is byte-identical."""
    from src.polaris_graph.generator.provenance_generator import sanitize_evidence_text

    summary_blocks = []
    for ev in evidence:
        ev_id = ev.get("evidence_id", "")
        title = (ev.get("title", "") or "")[:120]
        stmt = (ev.get("statement", "") or "")[:160]
        tier = ev.get("tier", "")
        title_clean, _ = sanitize_evidence_text(title)
        stmt_clean, _ = sanitize_evidence_text(stmt)
        if title_clean:
            summary_blocks.append(
                f"{ev_id} [{tier}] | title: {title_clean} | {stmt_clean}"
            )
        else:
            summary_blocks.append(f"{ev_id} [{tier}]: {stmt_clean}")
    summary_text = "\n".join(summary_blocks)
    return (
        f"Research question: {research_question}\n\n"
        f"Evidence summaries ({len(evidence)} rows):\n"
        f"{summary_text}\n\n"
        f"Return the JSON section plan."
    )


# ─────────────────────────────────────────────────────────────────
# Test 1: LARGE pool -> outline prompt is bounded (row-count + header).
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_large_pool_outline_prompt_bounded(monkeypatch):
    cap = 150
    monkeypatch.setenv("PG_OUTLINE_MAX_EV", str(cap))
    big_pool = _make_evidence(544)

    parse_result, _retry, _in, _out = await _call_outline(
        "Does drug X work?", big_pool, "deepseek/deepseek-v4-pro", 0.2, 2500,
    )

    # At least the primary call fired; the retry (if any) reuses the SAME bounded
    # prompt, so EVERY captured prompt must be bounded — assert on all of them.
    assert len(_CapturingClient.captured_prompts) >= 1
    for prompt in _CapturingClient.captured_prompts:
        # The header count must be the BOUNDED N, not the 544 full-pool size.
        assert f"Evidence summaries ({cap} rows):" in prompt
        assert "(544 rows)" not in prompt

        # Exactly `cap` evidence-row lines are serialized (one per `ev_NNN` prefix
        # appearing at a line start in the summary block).
        ev_line_count = sum(
            1 for line in prompt.splitlines() if line.startswith("ev_")
        )
        assert ev_line_count == cap, f"expected {cap} serialized rows, got {ev_line_count}"

        # Only the TOP-N (deterministically-ordered) rows are present; the dropped
        # tail (e.g. ev_543) is NOT serialized into the menu.
        assert "ev_000 " in prompt
        assert "ev_543" not in prompt

        # TERSE digest: the long statement text must NOT appear in the large-pool menu.
        assert "long evidence statement sentence" not in prompt


# ─────────────────────────────────────────────────────────────────
# Test 2: SMALL pool -> outline prompt is BYTE-IDENTICAL to the pre-cap build.
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_small_pool_outline_prompt_byte_identical(monkeypatch):
    monkeypatch.setenv("PG_OUTLINE_MAX_EV", "150")
    small_pool = _make_evidence(40)  # 40 <= 150 -> small-pool path
    rq = "Does drug X work?"

    await _call_outline(rq, small_pool, "deepseek/deepseek-v4-pro", 0.2, 2500)

    assert len(_CapturingClient.captured_prompts) >= 1
    prompt = _CapturingClient.captured_prompts[0]

    expected = _build_expected_verbose_prompt(rq, small_pool)
    assert prompt == expected, "small-pool outline prompt must be byte-identical"

    # Sanity: the verbose statement text IS present on the small-pool path.
    assert "long evidence statement sentence" in prompt
    assert "Evidence summaries (40 rows):" in prompt


# ─────────────────────────────────────────────────────────────────
# Test 3: default (env UNSET) still caps a >150 pool, leaves <=150 verbatim.
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_default_cap_applies_when_env_unset(monkeypatch):
    monkeypatch.delenv("PG_OUTLINE_MAX_EV", raising=False)
    default_cap = int(PG_OUTLINE_MAX_EV_DEFAULT)
    big_pool = _make_evidence(default_cap + 200)

    await _call_outline("q", big_pool, "deepseek/deepseek-v4-pro", 0.2, 2500)
    prompt = _CapturingClient.captured_prompts[0]
    assert f"Evidence summaries ({default_cap} rows):" in prompt

    # And a pool exactly AT the default cap is the byte-identical verbose path.
    _CapturingClient.captured_prompts = []
    at_cap_pool = _make_evidence(default_cap)
    await _call_outline("q", at_cap_pool, "deepseek/deepseek-v4-pro", 0.2, 2500)
    prompt2 = _CapturingClient.captured_prompts[0]
    assert f"Evidence summaries ({default_cap} rows):" in prompt2
    assert "long evidence statement sentence" in prompt2  # verbose digest retained


# ─────────────────────────────────────────────────────────────────
# Test 4: CRITICAL per-section invariant — validation still spans the FULL pool.
# An ev_id from the DROPPED low-relevance tail is still accepted by the outline
# validator, proving the cap shrank only the MENU, not the per-section
# selection/validation/resolution surface.
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_allowed_ev_ids_still_full_pool(monkeypatch):
    cap = 150
    monkeypatch.setenv("PG_OUTLINE_MAX_EV", str(cap))
    big_pool = _make_evidence(544)

    # The LLM picks ev_543 — a row that was DROPPED from the bounded outline menu
    # (only ev_000..ev_149 are serialized). If allowed_ev_ids regressed to the
    # capped set, this id would be rejected as unknown. The outline must accept it.
    tail_id = "ev_543"

    class _TailPickClient(_CapturingClient):
        async def generate(self, *, prompt, system, max_tokens, temperature):
            type(self).captured_prompts.append(prompt)
            outline = {
                "sections": [
                    {"title": "Efficacy", "focus": "f", "ev_ids": ["ev_000", "ev_001", tail_id]},
                    {"title": "Safety", "focus": "f", "ev_ids": ["ev_002", "ev_003", "ev_004"]},
                    {"title": "Comparative Effectiveness", "focus": "f", "ev_ids": ["ev_005", "ev_006"]},
                    {"title": "Dose Response", "focus": "f", "ev_ids": ["ev_007", "ev_008"]},
                    {"title": "Regulatory", "focus": "f", "ev_ids": ["ev_009", "ev_010"]},
                ]
            }
            return _FakeResponse(json.dumps(outline))

    _TailPickClient.captured_prompts = []
    monkeypatch.setattr(orc_module, "OpenRouterClient", _TailPickClient)

    parse_result, _retry, _in, _out = await _call_outline(
        "q", big_pool, "deepseek/deepseek-v4-pro", 0.2, 2500,
    )

    # tail_id was NOT in the serialized menu...
    assert tail_id not in _TailPickClient.captured_prompts[0]
    # ...but the outline validator (allowed_ev_ids = FULL pool) still ACCEPTED it.
    assert parse_result.ok is True, parse_result.reason_codes
    eff = next(p for p in parse_result.plans if p.title == "Efficacy")
    assert tail_id in eff.ev_ids, (
        "ev_id from the dropped tail must remain selectable — proves allowed_ev_ids "
        "still spans the full pool (per-section selection unaffected)"
    )


# ─────────────────────────────────────────────────────────────────
# Test 5: disabling the cap (PG_OUTLINE_MAX_EV<=0) -> full pool, verbose digest.
# ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_cap_disabled_serializes_full_pool_verbose(monkeypatch):
    monkeypatch.setenv("PG_OUTLINE_MAX_EV", "0")  # disabled
    pool = _make_evidence(300)
    await _call_outline("q", pool, "deepseek/deepseek-v4-pro", 0.2, 2500)
    prompt = _CapturingClient.captured_prompts[0]
    assert "Evidence summaries (300 rows):" in prompt
    assert "long evidence statement sentence" in prompt  # verbose retained
    assert "ev_299 " in prompt  # full tail present
