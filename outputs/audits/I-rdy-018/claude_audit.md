# Claude architect audit — I-rdy-018 / GH #514

**Branch:** `bot/I-rdy-018-openrouter-rehearsal`
**Commits:** `20017a77` (rehearsal capability) + 2 polaris merges (#551/#554 fixes) + `7002c57d` (rehearsal evidence)
**Canonical diff:** `.codex/I-rdy-018/codex_diff.patch` — sha256 `a72bddf25833fda3f139e93db1d37bfd76a1578ab7cfc31533e3c881b77d7f8c`
**Diff:** 5 files, +502 (`scripts/v6/run_rehearsal.py` 208 · `tests/v6/test_run_rehearsal.py` 75 · `tests/v6/fixtures/rehearsal_prompts.yaml` 29 · `docs/carney_handover/rehearsal_procedure.md` 108 · `docs/carney_handover/rehearsal_evidence.md` 82).

## What #514 delivers (Carney readiness Phase 4)

The OpenRouter V4 Pro **rehearsal capability** + the **evidence** that the
non-sovereign rehearsal path passes end-to-end:

1. **`scripts/v6/run_rehearsal.py`** — `check-models` (probes OpenRouter for
   the V4 Pro generator + Gemma 4 31B verifier) and `run` (executes the
   8-prompt fixed prompt set through pipeline-A, `--max-cost` cost cap,
   `--out-root` artifact dir; per-prompt terminal-verdict detection).
2. **`tests/v6/fixtures/rehearsal_prompts.yaml`** — 8 non-confidential
   prompt templates (clinical, policy, tech, due_diligence, ai_sovereignty,
   canada_us, workforce, custom).
3. **`tests/v6/test_run_rehearsal.py`** — 4 harness tests.
4. **`docs/carney_handover/rehearsal_procedure.md`** — operator procedure.
5. **`docs/carney_handover/rehearsal_evidence.md`** — the executed-rehearsal
   evidence (this run).

## Verification

| Check | Result |
|---|---|
| `tests/v6/test_run_rehearsal.py` | **4/4 pass** (offline, 5.8 s) |
| `check-models` | PASS — `deepseek/deepseek-v4-pro` + `google/gemma-4-31b-it` both available on OpenRouter |
| 8-prompt billed rehearsal | **8/8 prompts reached a terminal verdict** — harness emitted `RESULT: PASS — the full non-sovereign rehearsal path passed start-to-finish` |
| Per-prompt | 1 `success`, 2 `partial_qwen_advisory`, 2 `partial_thin_corpus`, 3 `abort_corpus_inadequate` — every one a clean honest terminal verdict; zero `error_*`, zero hangs |
| Total cost | $0.2408 (cap $5.00/run — never approached) |
| Robustness fixes | #551 + #554 empirically validated — `policy` prompt that hung 31 min in the prior run completed cleanly this time |

## Self-audit against #514 acceptance

- *Phase-4 acceptance — "the full non-sovereign rehearsal path passes
  start-to-finish":* **VERIFIED** — harness `RESULT: PASS`, 8/8 terminal.
- *Evidence package captured:* **VERIFIED** — `rehearsal_evidence.md` records
  the UTC window, check-models result, per-prompt run_id→status→cost table,
  total cost, the exact command, and RESULT.
- *Honest framing:* `rehearsal_evidence.md` does not overclaim — it states
  plainly that `abort_*`/`partial_*` are honest terminal outcomes (the
  corpus-adequacy gate correctly declining a thin corpus is a *pass* of the
  rehearsal, not a content quality claim), and discloses the OpenRouter 429
  rate-limiting + the non-fatal Redis `run_events` emit errors.

## Risk assessment

- `run_rehearsal.py` is a standalone operator script under `scripts/v6/`; it
  imports pipeline-A entry points, adds no production code path. LOW.
- The rehearsal is billed but operator-authorized ($5/run cap; actual $0.24). NONE.
- The capability files (`20017a77`) had not had a prior Codex diff review;
  this review is their first — the canonical diff covers all 5 files.

**Verdict: ready for Codex diff review.**
