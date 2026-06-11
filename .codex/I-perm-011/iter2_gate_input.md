HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# I-perm-011 (#1182) iter-2 diff gate — OFF-mode OUTLINE-prompt evidence-menu cap

## What this change is

drb_76 ran OFF-mode (PG_USE_RESEARCH_PLANNER unset) -> `generate_multi_section_report`
takes the legacy `_call_outline` branch, which serialized EVERY row of the ~544-row
evidence pool into the outline prompt. The generator (deepseek-v4-pro) is reasoning-first;
the larger serialized input induced a longer reasoning stream that consumed the WHOLE
16384-token completion ceiling (PG_REASONING_FIRST_HARD_CAP) on reasoning, emitting ZERO
content -> finish_reason=length -> the FX-01/SF-15 guard raised ReasoningFirstTruncationError.

The fix bounds ONLY the rows serialized into the OUTLINE prompt to a new call-time env knob
`PG_OUTLINE_MAX_EV` (default constant `PG_OUTLINE_MAX_EV_DEFAULT='150'`, read via os.getenv
inside `_call_outline` so it is per-run tunable + monkeypatch-testable):
- SMALL pool (len(evidence) <= cap): pre-cap build runs VERBATIM (verbose per-row digest incl
  160-char statement, header count == len(evidence)). Intended byte-identical.
- LARGE pool (len(evidence) > cap): menu sliced to evidence[:N] AND each digest TERSED to
  ev_id + tier + title only (160-char statement dropped). Header count reflects bounded N.
- cap<=0 disables (full pool, verbose).

CRITICAL claimed invariant: `allowed_ev_ids` (outline validation) stays computed from the
FULL pool, and the per-section path (deterministic fallback, M-44/M-52 primary-anchor
injection, per-section PG_MAX_EV_PER_SECTION=40 selection, full-text resolution
evidence_pool[ev_id]) all stay on the FULL pool. Edit confined inside `_call_outline`;
ON-mode (_assign_evidence_to_planned_outline) untouched.

## RED-TEAM CHECKLIST — answer each (a)-(e) explicitly with cited diff/test lines

(a) Does the OUTLINE no longer truncate on a large pool? i.e. is the serialized input
    bounded (row count capped to N, per-row digest tersed) so the induced reasoning stream
    no longer consumes the whole completion ceiling? Confirm the large-pool branch slices
    evidence[:N] AND drops the statement, and that BOTH the primary and retry generate()
    calls reuse the same bounded `prompt` (so retry is also bounded). Flag if the cap can be
    bypassed (e.g. env parse, non-positive handling, off-by-one at exactly cap).

(b) Do the per-section generators STILL get the FULL 544-pool selection — i.e. is ONLY the
    outline menu bounded, NOT validation/selection/resolution? Verify `allowed_ev_ids` is
    built from the full `evidence` list (not the sliced `outline_evidence`). Verify an ev_id
    the LLM picks that was DROPPED from the menu is still accepted. CRITICAL: in OFF mode the
    section ev_ids ARE the outline LLM's picks from this very menu — so if the LLM never SEES
    a dropped tail row, can it still pick it? Assess whether "per-section selection unchanged"
    actually holds in OFF mode, or whether it holds only because (i) N=150 > section demand
    ~120 AND (ii) the full-pool re-add nets (deterministic fallback + M-44/M-52 primary-anchor
    injection) recover anything important the bounded menu didn't show. State plainly whether
    this is a real regression risk or adequately mitigated.

(c) Are the faithfulness gates (strict_verify / NLI / 4-role) untouched? Confirm the edit is
    confined to outline-prompt serialization and runs upstream of full-pool text resolution,
    so no fabricated-claim can pass that previously failed.

(d) Is the small-pool path BYTE-IDENTICAL to the pre-cap build? Verify the <=cap branch is
    the unmodified original loop+prompt, and that the byte-identical test reproduces the
    pre-change build and asserts equality.

(e) Are the tests MEANINGFUL (not tautological)? Do they pin: large-pool bounded header+row
    count + terse digest + dropped tail absent; small-pool byte-identical; default cap when
    env unset; at-cap pool verbose; the CRITICAL allowed_ev_ids-spans-full-pool invariant via
    a dropped-tail ev_id still accepted by _parse_outline; cap-disabled full verbose. Flag any
    invariant asserted in prose but NOT covered by a test.

## SIZING CAVEAT the author DISCLOSES (assess, do not re-derive)

N=150 is coverage-favoring (>= ~120 OFF-mode section demand) but the truncation upper-bound
fit is a HYPOTHESIS from a SINGLE known-good datapoint: 53 verbose rows worked / 544 failed;
150 terse rows (~16-17K menu chars) are ~20-25% LARGER than the 53-verbose known-good (~13K).
The author states a live V4 Pro 1-query canary is the real acceptance step beyond this offline
diff, with documented fallbacks (lower PG_OUTLINE_MAX_EV toward ~120, then the Novita
no-row-cut route = raise PG_REASONING_FIRST_HARD_CAP to 32000 + pin novita, a separate
I-provider-001 env lever NOT in this diff). Judge whether shipping at 150 with a canary
gate is acceptable for an OFFLINE DIFF approval, or whether the default must be lowered NOW.
Note: this gate is the offline diff gate; the live canary is a SEPARATE downstream step.

## DIFF (git --no-pager diff HEAD -- src/polaris_graph/generator/multi_section_generator.py)

```diff
diff --git a/src/polaris_graph/generator/multi_section_generator.py b/src/polaris_graph/generator/multi_section_generator.py
index de2a9182..cbf0ad7f 100644
--- a/src/polaris_graph/generator/multi_section_generator.py
+++ b/src/polaris_graph/generator/multi_section_generator.py
@@ -86,6 +86,53 @@ PG_CONTRACT_SLOT_MIN_MAX_TOKENS: int = int(
     os.getenv("PG_CONTRACT_SLOT_MIN_MAX_TOKENS", "6000")
 )
 
+# I-perm-011 (#1182): OUTLINE-prompt evidence-menu cap (OFF-mode `_call_outline`).
+#
+# WHY: drb_76 ran OFF-mode (PG_USE_RESEARCH_PLANNER unset) -> generate_multi_section_report
+# takes the legacy `_call_outline` branch, which serialized EVERY row of the ~544-row
+# evidence pool into the outline prompt (one ~100-300-char summary block per row). The
+# generator (deepseek-v4-pro) is reasoning-first: the larger serialized input induced a
+# longer reasoning stream that consumed the WHOLE 16384-token completion ceiling
+# (PG_REASONING_FIRST_HARD_CAP on the default provider) on reasoning, emitting ZERO content
+# -> finish_reason=length -> the FX-01/SF-15 guard correctly raised
+# ReasoningFirstTruncationError rather than ship the scratchpad as VERIFIED prose. This is
+# the OUTLINE-level analog of the M-24 per-section >100K-token bug, which was fixed at the
+# SECTION level by PG_MAX_EV_PER_SECTION but never applied to the OUTLINE prompt.
+#
+# THE CAP IS MENU-ONLY: only the rows SERIALIZED into the outline prompt are bounded. The
+# evidence pool is deterministically priority/tier/relevance-ORDERED before it reaches the
+# outline (evidence_selector relevance-floor + Gate-B tier-balanced selection), so a top-N
+# slice keeps exactly the rows the sections prioritize and drops only the low-relevance tail
+# that no section would cite. `allowed_ev_ids` validation, full-text resolution
+# (evidence_pool[ev_id]), the deterministic fallback, the M-44/M-52 primary-anchor
+# injection, and the per-section PG_MAX_EV_PER_SECTION selection ALL stay on the FULL pool.
+# Faithfulness gates (strict_verify / NLI / 4-role) are downstream of full-pool text
+# resolution and are untouched.
+#
+# DEFAULT 150 is COVERAGE-FAVORING: sized ABOVE the realized OFF-mode section demand
+# (~120 ev_ids = 5-6 sections x 12-20 each) so the planner still sees every row a section
+# would pick — that is what keeps per-section selection effectively unchanged in OFF mode
+# (where the section ev_ids ARE the outline LLM's picks from this menu). On the LARGE-pool
+# branch the per-row digest is also TERSED (ev_id + tier + title only; the 160-char
+# statement is dropped) because the outline only PLANS section structure, so the statement
+# text is not needed there; tersing roughly halves per-row chars, widening reasoning
+# headroom at the same N. Env-tunable; read at CALL time (not import) so the cap and digest
+# are tunable per-run and unit-testable.
+#
+# HONEST SCOPE / SIZING CAVEAT: the two bounds do NOT yet provably coincide at 150.
+#   * coverage LOWER bound: N >= ~120 (section demand) — 150 clears this with headroom.
+#   * truncation UPPER bound: argued from a SINGLE known-good datapoint (53 VERBOSE rows
+#     worked pre-a030b024 ~= 13K menu chars; 544 verbose failed). 150 TERSE rows ~= 16-17K
+#     menu chars — i.e. ~20-25% LARGER than the only known-good input, NOT demonstrably
+#     within it. So 150 is chosen for coverage, and the truncation fit is a HYPOTHESIS that
+#     a live V4 Pro 1-query canary must confirm; it is NOT proven by this offline diff.
+#   * If the canary truncates at 150, the documented levers (in priority order) are: lower
+#     PG_OUTLINE_MAX_EV toward ~120 (where the two bounds nearly coincide), then the Novita
+#     no-row-cut route (raise PG_REASONING_FIRST_HARD_CAP to 32000 + pin
+#     OPENROUTER_PROVIDER_ORDER=novita), which is the separate I-provider-001 env/provider
+#     lever, NOT this code change.
+PG_OUTLINE_MAX_EV_DEFAULT: str = "150"
+
 
 # Allowed section labels. The outline call is constrained to pick from
 # this list; prevents the model from inventing off-topic section titles.
@@ -993,30 +1040,79 @@ async def _call_outline(
     # LLM literally didn't see it. Title is now included (truncated to
     # 120 chars) so trigger-vocabulary rules can match against title
     # text. Minor increase in prompt size (~60 extra chars per row).
-    summary_blocks = []
-    for ev in evidence:
-        ev_id = ev.get("evidence_id", "")
-        title = (ev.get("title", "") or "")[:120]
-        stmt = (ev.get("statement", "") or "")[:160]
-        tier = ev.get("tier", "")
-        # Sanitize via the provenance sanitizer (both title and stmt).
-        title_clean, _ = sanitize_evidence_text(title)
-        stmt_clean, _ = sanitize_evidence_text(stmt)
-        if title_clean:
-            summary_blocks.append(
-                f"{ev_id} [{tier}] | title: {title_clean} | {stmt_clean}"
-            )
-        else:
-            summary_blocks.append(f"{ev_id} [{tier}]: {stmt_clean}")
-    summary_text = "\n".join(summary_blocks)
-
-    prompt = (
-        f"Research question: {research_question}\n\n"
-        f"Evidence summaries ({len(evidence)} rows):\n"
-        f"{summary_text}\n\n"
-        f"Return the JSON section plan."
-    )
+    # I-perm-011 (#1182): OUTLINE-prompt evidence-menu cap. Read at CALL time (not an
+    # import-time constant) so the cap + digest mode are tunable per-run and unit-testable
+    # via monkeypatch. `outline_max_ev` bounds ONLY the rows serialized into the outline
+    # prompt; `allowed_ev_ids` (validation) and every downstream consumer stay on the FULL
+    # pool. See PG_OUTLINE_MAX_EV_DEFAULT for the full rationale.
+    try:
+        _outline_max_ev = int(os.getenv("PG_OUTLINE_MAX_EV", PG_OUTLINE_MAX_EV_DEFAULT))
+    except (TypeError, ValueError):
+        _outline_max_ev = int(PG_OUTLINE_MAX_EV_DEFAULT)
+    if _outline_max_ev <= 0:
+        # Non-positive => disabled => no cap (full pool, verbose digest = byte-identical).
+        _outline_max_ev = len(evidence)
+
+    if len(evidence) <= _outline_max_ev:
+        # SMALL-POOL PATH — BYTE-IDENTICAL to the pre-cap build. The pool was small enough
+        # that the outline never truncated before, so this branch is left exactly as it was
+        # (verbose per-row digest incl. the 160-char statement, count == len(evidence)).
+        summary_blocks = []
+        for ev in evidence:
+            ev_id = ev.get("evidence_id", "")
+            title = (ev.get("title", "") or "")[:120]
+            stmt = (ev.get("statement", "") or "")[:160]
+            tier = ev.get("tier", "")
+            # Sanitize via the provenance sanitizer (both title and stmt).
+            title_clean, _ = sanitize_evidence_text(title)
+            stmt_clean, _ = sanitize_evidence_text(stmt)
+            if title_clean:
+                summary_blocks.append(
+                    f"{ev_id} [{tier}] | title: {title_clean} | {stmt_clean}"
+                )
+            else:
+                summary_blocks.append(f"{ev_id} [{tier}]: {stmt_clean}")
+        summary_text = "\n".join(summary_blocks)
+
+        prompt = (
+            f"Research question: {research_question}\n\n"
+            f"Evidence summaries ({len(evidence)} rows):\n"
+            f"{summary_text}\n\n"
+            f"Return the JSON section plan."
+        )
+    else:
+        # LARGE-POOL PATH — bound the OUTLINE menu to the top-N highest-priority rows AND
+        # terse each digest (ev_id + tier + title only; DROP the 160-char statement). The
+        # pool is deterministically priority/tier/relevance-ORDERED upstream, so [:N] keeps
+        # exactly the rows sections prioritize and drops only the low-relevance tail. The
+        # statement text is unnecessary here because the outline only PLANS section
+        # structure; dropping it widens reasoning headroom at the same N, which is what
+        # prevents the reasoning-first writer from spending the whole completion ceiling on
+        # planning and emitting zero content (the drb_76 ReasoningFirstTruncationError).
+        outline_evidence = evidence[:_outline_max_ev]
+        summary_blocks = []
+        for ev in outline_evidence:
+            ev_id = ev.get("evidence_id", "")
+            title = (ev.get("title", "") or "")[:120]
+            tier = ev.get("tier", "")
+            title_clean, _ = sanitize_evidence_text(title)
+            if title_clean:
+                summary_blocks.append(f"{ev_id} [{tier}] | title: {title_clean}")
+            else:
+                summary_blocks.append(f"{ev_id} [{tier}]")
+        summary_text = "\n".join(summary_blocks)
+
+        prompt = (
+            f"Research question: {research_question}\n\n"
+            f"Evidence summaries ({len(outline_evidence)} rows):\n"
+            f"{summary_text}\n\n"
+            f"Return the JSON section plan."
+        )
 
+    # allowed_ev_ids stays on the FULL pool so outline validation does NOT regress: a section
+    # ev_id the LLM picks is accepted iff it is anywhere in the pool, and full-text resolution
+    # downstream (evidence_pool[ev_id]) spans every row. The cap shrank only the MENU, never
+    # the validation/resolution surface.
     allowed_ev_ids = {ev.get("evidence_id", "") for ev in evidence}
     allowed_ev_ids.discard("")
 
```

## NEW TEST FILE (untracked: tests/polaris_graph/test_iperm011_outline_evidence_cap.py)

```python
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
```

## Build-agent reported test result (VERIFY plausibility against the diff+test; do not trust blindly)

New test file: 5/5 passed. Regression: 117/117 passed across test_m203_outline_collapse,
test_m31_outline_resilience, test_m40_mechanism_section, test_m57_contract_outline,
test_m62_non_clinical_regression, test_multi_section_gap4,
test_generator_domain_outline_iready009, test_domain_general_sections_phase6. Full generator
dir: 79/79 passed.

## OUTPUT SCHEMA (REQUIRED — §8.3.9). End with a line starting `verdict:`

verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]

The final line MUST start with `verdict: APPROVE` or `verdict: REQUEST_CHANGES`.
