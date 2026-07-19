# Oracle Status — Acceptance Harness (Layer 2)

_Last updated: 2026-07-19 — deterministic browser-free golden achieved; codex verdict: **ORACLE-TRUSTWORTHY**._

The acceptance harness (`tests/oracle/acceptance_portable.py`) is the deterministic oracle for the
outline agent's retrieval loop. It runs two scenarios:

- **THIN** (positive control) — a seed with real gaps that MUST trigger scoped retrieval and mutate
  the outline.
- **SATURATED** (negative control) — a fully-built seed that MUST stay at zero retrieval.

## The 3 blockers (why the harness was not yet trustworthy)

1. **Vacuous positive control.** `run_thin()` recorded `outline_mutated` and search counts but never
   *asserted* on them, so a THIN run that silently fired zero searches would still have "passed" —
   the positive control was asserting nothing. (The negative control already had an enforced
   `valid_negative_control`; the positive side had no mirror.)

2. **Live, non-deterministic boundaries.** The harness had TWO sources of non-determinism: the
   OpenRouter LLM and the live retriever/browser. Every run hit the network and the browser, so the
   result artifact was never reproducible and no byte-level regression signal existed. In particular
   the `decide` step calls `generate_structured` (parsed `ReactDecision`), which was NOT frozen —
   only `generate` was — so the loop's control flow was non-deterministic even with the LLM cassette
   in place.

3. **Wall-clock leakage into behaviour-selecting inputs.** Real fetch latency (~58–84s per live gap
   search) was baked into (a) the per-step `({elapsed:.1f}s)` header the notebook feeds the decide
   prompt (`analysis_notebook.py:269`) and (b) the `... in {elapsed:.1f}s` string
   `search_more_evidence` writes into its ToolResult markdown (`outline_agent.py:821/825`). On replay
   with frozen retrieval those timings become ~0s, changing the decide prompt's length and tripping
   the char-budget truncation — a one-character diff that made replay MISS against the recording.

## Fixes

### Positive-control assertion fix
`run_thin()` now computes and returns an **enforceable** `valid_positive_control = search_calls >= 1
and outline_mutated`, mirroring the negative control's `valid_negative_control`. Both the live
`main()` path and the oracle path now exit non-zero if the positive control (THIN) did not fire a
search + mutate the outline, or if the negative control (SATURATED) took any retrieval. A vacuous
control now fails loud instead of passing silently.

### Cassette-based deterministic golden (achieved)
Both non-deterministic boundaries are now frozen, making the whole run reproducible and browser-free:

- **`tests/oracle/llm_cassette.py`** — extended to freeze BOTH `generate` AND `generate_structured`
  (the decide step). Schema type is part of request identity; pydantic responses are (de)serialized
  via `model_dump(mode="json")` / `model_validate`.
- **`tests/oracle/retrieval_cassette.py`** (new) — Layer 2 seam. Monkeypatches the single
  `run_live_retrieval` funnel so record hits the network/browser exactly ONCE at seed time and replay
  reconstructs a `LiveRetrievalResult` from the frozen JSON-native slice with NO Serper / fetch /
  browser. The wall-clock `retrieval_deadline_monotonic` is deliberately excluded from the request
  key (timing input, not behaviour selector).
- **Wall-clock normalization** — a `_frozen_step_clock()` context manager zeroes the per-step
  `elapsed_seconds` and rewrites the `in <elapsed>s` token in step markdown at its SOURCE (before the
  length-sensitive digest truncation), identically in record and replay, so record==replay byte-for-
  byte without hiding any real behaviour change. `_canonical_golden()` drops `elapsed_s` and
  normalizes disclosure timings for the byte-compare.
- **Modes** (`--mode seed-retrieval | record | replay`): `seed-retrieval` = live LLM + live retriever
  (network/browser once, captures both tapes); `record` = live LLM + frozen retrieval (no browser,
  emits golden); `replay` = both frozen (no network at all, reproduces golden byte-identically). A
  `replay` mismatch exits 3.

Result: `replay` reproduces `tests/oracle/cassettes/acceptance_golden.json` **byte-identically**.
THIN fires 3 scoped searches and mutates the outline (`valid_positive_control=true`); SATURATED stays
at zero retrieval (`valid_negative_control=true`). Any future diff in the golden is a real regression.

### Cassette diagnostics
`tests/oracle/cassette.py` gained an opt-in `PG_ORACLE_DEBUG_MISS` dump (missed args vs recorded
same-method args) to make replay-MISS triage fast.

## Committed artifacts

- `tests/oracle/acceptance_portable.py` — portable harness (oracle modes + enforced controls)
- `tests/oracle/llm_cassette.py`, `tests/oracle/retrieval_cassette.py`, `tests/oracle/cassette.py`
- `tests/oracle/cassettes/acceptance_llm.jsonl`, `acceptance_retrieval.jsonl` — frozen tapes
  (gitignore `*.jsonl` exception added; both scanned for plaintext secrets — clean)
- `tests/oracle/cassettes/acceptance_golden.json` — the byte-stable golden reference
- `acceptance_result.json` — latest deterministic run artifact

## Verdict

Codex: **ORACLE-TRUSTWORTHY** — the acceptance harness now enforces both controls, is fully
deterministic across replays, and requires no live network or browser to reproduce the golden.
