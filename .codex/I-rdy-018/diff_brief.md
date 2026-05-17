# Codex DIFF review — I-rdy-018 / GH #514: OpenRouter V4 Pro rehearsal + evidence package

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

---

## 0. What you are reviewing

The **code + evidence diff** for GH #514 (Carney readiness Phase 4 — OpenRouter
V4 Pro rehearsal + evidence package).

- **Diff to review:** `.codex/I-rdy-018/codex_diff.patch`
  — canonical-diff-sha256 `a72bddf25833fda3f139e93db1d37bfd76a1578ab7cfc31533e3c881b77d7f8c`
  (trailer line; sha is over the patch body above it).
- **Claude architect audit:** `outputs/audits/I-rdy-018/claude_audit.md`
- **Scope:** 5 files, +502. `scripts/v6/run_rehearsal.py` (208, the harness),
  `tests/v6/test_run_rehearsal.py` (75), `tests/v6/fixtures/rehearsal_prompts.yaml`
  (29), `docs/carney_handover/rehearsal_procedure.md` (108),
  `docs/carney_handover/rehearsal_evidence.md` (82, the run evidence).
- **Note:** the 4 capability files were committed earlier (`20017a77`) without
  a prior Codex diff review; this review is their first. `run_rehearsal.py` is
  208 lines because it IS the issue's deliverable (a standalone operator
  script under `scripts/v6/`, no production code path touched).

## 1. What #514 delivers

The rehearsal capability + the evidence it passes. `run_rehearsal.py`:
`check-models` (OpenRouter availability probe for the V4 Pro generator +
Gemma 4 31B verifier) and `run` (8 fixed non-confidential prompts through
pipeline-A, `--max-cost` cap, per-prompt terminal-verdict detection,
`RESULT: PASS` iff every prompt reaches a terminal verdict).

## 2. Verification done

- `tests/v6/test_run_rehearsal.py` — **4/4 pass** offline (5.8 s).
- The operator-authorized 8-prompt billed rehearsal ran: **8/8 prompts
  reached a terminal verdict**, harness `RESULT: PASS`. Per-prompt: 1
  `success`, 2 `partial_qwen_advisory`, 2 `partial_thin_corpus`, 3
  `abort_corpus_inadequate`; total cost $0.2408 (cap $5.00). No `error_*`,
  no hangs.
- The branch carries the #551 + #554 retrieval-robustness fixes (merged from
  `polaris`); the rehearsal empirically re-validated them — the `policy`
  prompt that hung 31 min in the prior attempt completed cleanly.

## 3. Red-Team checklist — please verify

1. **Harness correctness** — `run_rehearsal.py` `run`: does it correctly
   detect a terminal verdict per prompt, accumulate cost, honour `--max-cost`,
   and emit `RESULT: PASS` iff every prompt reached a terminal verdict (and
   FAIL otherwise)? Any path where a non-terminal/`error_*` run is silently
   counted as pass?
2. **`check-models`** — does it fail loud if the generator or evaluator is
   absent (no silent skip)?
3. **Prompt set** — `rehearsal_prompts.yaml`: 8 templates, non-confidential,
   no secrets/PII.
4. **Evidence honesty** — does `rehearsal_evidence.md` accurately reflect the
   run (per-prompt run_ids, statuses, costs, total $0.2408, RESULT PASS)? Is
   the framing of `abort_*`/`partial_*` as honest *terminal* outcomes correct
   and not an overclaim?
5. **No secrets** — the diff (incl. the evidence doc + procedure doc) carries
   no API keys / `.env` values.
6. **Hygiene** — LAW VI (no hardcoded endpoints/keys; cost cap + out-root are
   CLI args), snake_case, no `except: pass`, no silent downgrade.
7. **Scope** — does the diff stay within #514 (rehearsal capability +
   evidence), with no unrelated "while we're at it" changes?

## 4. Required output schema (§8.3.9)

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
