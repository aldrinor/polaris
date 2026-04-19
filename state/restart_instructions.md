# Restart Instructions

## Current state (2026-04-19 00:05 UTC) — AUTONOMOUS SWEEP+AUDIT LOOP IN FLIGHT

**Branch**: `PL-honest-rebuild-phase-1`
**HEAD**: `3e4dd03` (Codex pass 8 findings — READY verdict)
**Test suite baseline**: 432 passing

---

## CRITICAL: what you (next session) must do if resuming

The user (`aldrin.or@c-polarbiotech.com`) is asleep. They explicitly
directed this session to run an autonomous loop. Do NOT wait for
user input. Execute the loop.

### The autonomous loop

```
[ongoing] 8-query full sweep (bg task bs3hpf8r0, monitor bb4cs4x3a)
    ↓ (monitor emits "sweep_complete summary_written")
[step 1] Bundle full sweep output for Codex audit:
    - outputs/sweep_r3_final/sweep_summary.{json,md}
    - For each of 8 queries:
      - manifest.json
      - report.md
      - verification_details.json
      - evaluator_rule_checks.json
      - qwen_judge_output.json
      - run_log.txt
      - bibliography.json
      - contradictions.json
      - corpus_adequacy.json
[step 2] Write docs/pipeline_audit_context/16_pass_9_content_audit.md
    with bundle references + mandate (content quality, not code)
[step 3] Dispatch Codex pass 9 as bg task using the SAME pattern that
    worked: `cat /tmp/codex_pass9_prompt.txt | codex exec
    --sandbox workspace-write - > stdout 2> stderr`
[step 4] Monitor for findings.md
[step 5] Read verdict:
    - If APPROVED / READY / similar → go to [step 7]
    - If issues flagged → go to [step 6]
[step 6] Parse Codex findings, identify root causes, implement fixes,
    run full test suite (must stay ≥432 pass), commit, re-run 8-query
    sweep (rm -rf outputs/sweep_r3_final && python -m scripts.run_honest_sweep_r3
    --out-root outputs/sweep_r3_final), go back to [step 1]
[step 7] Write morning-read summary to logs/session_log.md, commit,
    mark tasks 110/122/123/124/125 completed. Tell user when they
    return.
```

### Hard caps (safeguards)

- **Max 3 full sweep-audit-fix cycles.** Each sweep costs ~$0.01-0.02
  from the smokes; 3 cycles × 8 queries × ~5 min = ≤2 hours.
- If Codex keeps flagging orthogonal issues (no convergence), STOP
  after cycle 3 and write a detailed "why I stopped" note in
  session_log for the user.
- Never skip a Codex pass — the user specifically said
  "you must need to make Codex to agree".
- Never run a sweep without first checking the test suite passes
  (`python -m pytest tests/polaris_graph/ -q` must end with
  "N passed, 0 failed" where N ≥ 432).

### What's already done in this session

- Pass 3 READY (B-102 closed)
- Pass 4 CONDITIONAL → M-1 timeout (ac593e1) + M-2 span finder (b2b6f5a)
- Pass 5 CONDITIONAL → M-5 PT12 fix (5cf6959) + M-3/M-4/M-6 (3921bc0)
- Pass 6 CONDITIONAL → M-6 lexical echo + M-4 correction (9f2801a)
- Pass 7 NOT-READY → M-6 dynamic threshold (e38c43f)
- Pass 8 READY-FOR-8-QUERY-SWEEP (3e4dd03)
- **Current**: 8-query sweep running; waiting for completion

### Key files

- `docs/pipeline_audit_context/0{7,8,9,10,11,12,13,14,15}_*.md` — the
  briefs dispatched to Codex (pass 3 through pass 8)
- `outputs/codex_findings/full_audit_pass_{3..8}/findings.md` — Codex
  verdicts (all tracked in git)
- `outputs/sweep_r3_final/` — in-flight 8-query sweep output (gitignored
  but referenced)
- `logs/session_log.md` — append-only audit trail
- `docs/todo_list.md` — Active section has Pass 5/Pass 4 sections at top
- `tests/polaris_graph/` — 432 tests; must stay green at every fix

### Auth

Codex CLI uses OAuth (chatgpt). No API key burn. `which codex` returns
`/c/Users/msn/AppData/Roaming/npm/codex`. Version 0.121.0.

### Dispatch pattern that WORKS (don't use argv)

```bash
cat /tmp/codex_passN_prompt.txt | codex exec --sandbox workspace-write - \
  > outputs/codex_findings/full_audit_pass_N/codex_stdout.log \
  2> outputs/codex_findings/full_audit_pass_N/codex_stderr.log
```

Argv-style `codex exec "$(cat prompt.txt)"` silently wedges on Windows.

---

## If you find things are broken on arrival

- Check `git log --oneline -20` to see what's been committed
- Check `tasklist //FI "IMAGENAME eq codex.exe"` for stuck codex processes;
  `taskkill //F //IM codex.exe` if wedged >20 min with <200 stderr lines
- Check `ls outputs/sweep_r3_final/` — presence of sweep_summary.json
  means sweep finished
- Run `python -m pytest tests/polaris_graph/ -q | tail -3` to verify
  test suite is still green

Everything is recoverable. The loop is the source of truth.
