## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

## §1 — Issue + Acceptance

**GH#359 — I-bug-106: synthesis subheadings ### not ##.**

Issue body: "Analyst Synthesis section emits ## subheadings which conflict with main section headers. Should be ### per markdown hierarchy. Acceptance: synthesis prompt updated, regression test asserts no ## in synthesis output."

**Acceptance:**
- `ANALYST_SYNTHESIS_SYSTEM_PROMPT` requests ### subheadings (not ##).
- Prompt explicitly forbids ## (reserved for parent section).
- Regression test asserts the prompt requests ### and forbids ##.
- All existing analyst_synthesis tests pass.

## §2 — Proposed Change

| File | Δ |
|---|---|
| `src/polaris_graph/generator/analyst_synthesis.py` | -2/+5 lines: prompt updates `## subheadings` → `### subheadings`; explicit forbid `## headers`; user prompt instruction `## subheadings` → `### subheadings` |
| `tests/polaris_graph/test_analyst_synthesis.py` | +13: tighten `test_prompt_requires_subsections` from `"##" in PROMPT` to `"###" in PROMPT`; add new `test_prompt_forbids_double_hash_subheadings` |

**Net: -2 / +18 lines.** Trivial scope.

## §3 — Files clean

- `src/polaris_graph/generator/regulatory_synthesizer.py` — uses `## ` markers in module docstring (unrelated). Untouched. ✓
- `src/polaris_graph/generator/contract_section_runner.py` — same (module docstring). Untouched. ✓
- Other prompts: `src/polaris_graph/generator/analyst_synthesis.py:251` (user prompt) — also updated. ✓
- Runtime renderer / scrub paths: no logic changes (the ## → ### change is in the prompt only).

## §4 — Test Strategy

- `pytest tests/polaris_graph/test_analyst_synthesis.py -x -q` → 27 baseline + 2 new → 29 pass.
- Verified: `python -m pytest tests/polaris_graph/test_analyst_synthesis.py -x -q` → 29 passed in 3.12s on bot/I-bug-106 HEAD.

## §5 — Output Schema Bound

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

Expected APPROVE iter 1.
