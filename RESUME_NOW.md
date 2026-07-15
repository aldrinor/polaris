# RESUME BRIEF — box rebooted. You are POLARIS-VM Claude. CONTINUE the flywheel.
CRITICAL: DEEP THINKING / GATE = FABLE via your model function (spawn a fresh model 'fable' sub-agent for root-cause + line-by-line gating). DO NOT use Codex 5.6 Sol / codex exec / codex_gate.sh — it HANGS and kills this session.
FIRST ACTION: push the flywheel branch to GitHub as backup so a box flap can never threaten progress again: git -C /home/polaris/wt/flywheel push -u origin flywheel-v1 (fix auth if needed).
READ: /home/polaris/polaris_project/HANDOFF_FROM_LAPTOP.md + /home/polaris/polaris_project/flywheel_codex_design.md (the 867-line codex flywheel design).
FLYWHEEL STATE — /home/polaris/wt/flywheel (branch flywheel-v1):
- Rank 0 committed (0e0eca9): PG_STOP_AFTER_ROUTED_OUTLINE cheap outline-only gate.
- Baseline outline done: outputs/baseline_routed_outline.json (680KB).
- NEXT: read it line-by-line (grounding) -> build experiment #1 = SOURCE-ELIGIBILITY FIREWALL (relevant+English+peer-reviewed-journal+quality; tier a prior) -> run outline-only -> FABLE read-gate -> compose only if rich+eligible.
DISCIPLINE: one change -> cheap outline test -> read line-by-line -> FABLE gate -> only then compose. Keep steps SMALL. Never force-approve. Operator drives from phone.

## STATE RECONSTRUCTION — do this EVERY restart (chat/session history is GONE; rely ONLY on durable files, never memory):
1. `git -C /home/polaris/wt/flywheel log --oneline flywheel-v1` -> the exact ranks already DONE (currently through ~Rank 10). NEVER redo a committed rank.
2. `tail -50 /home/polaris/polaris_project/FLYWHEEL_PROGRESS.md` -> the latest findings + decisions.
3. Read `/home/polaris/polaris_project/flywheel_codex_design.md` (867 lines) -> the COMPLETE original plan (every rank + all 11 gates). Do not miss any rank.
4. Continue from the NEXT unfinished rank. Do NOT skip and do NOT redo. Commit + append one line to FLYWHEEL_PROGRESS.md after EACH step so the durable record stays complete.
GATE = FABLE always. NEVER Codex 5.6 Sol (it hangs).

## GITHUB BACKUP DISCIPLINE (BINDING) — push to GitHub after EVERY single change, no exceptions:
After each step (a fix, an experiment, a doc/plan update), IMMEDIATELY:
1. cp /home/polaris/polaris_project/FLYWHEEL_PROGRESS.md /home/polaris/polaris_project/flywheel_codex_design.md /home/polaris/polaris_project/RESUME_NOW.md /home/polaris/polaris_project/GATEWAY_PROMPT.txt /home/polaris/wt/flywheel/docs_backup/ 2>/dev/null   (so GitHub has EVERYTHING, not just code)
2. git -C /home/polaris/wt/flywheel add -A && git -C /home/polaris/wt/flywheel commit -m "<what changed>"
3. git -C /home/polaris/wt/flywheel push origin flywheel-v1
Push after EACH commit — never batch multiple changes before pushing. If a push fails (box network flap), retry it on your very next step. The automatic 2-min daemon is only a safety net; YOU push proactively so nothing waits.
