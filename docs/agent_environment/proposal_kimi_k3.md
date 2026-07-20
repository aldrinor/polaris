# AGENT WORKING ENVIRONMENT — COMPLETE DESIGN

Everything below is written to be created as-is on the VM. File paths are exact. Scripts are named exactly. Where a rule exists, the mechanism that enforces it is named in the same breath — a rule with no enforcement is a wish.

---

## A. GOVERNING DOCUMENT SET

### A.1 The full directory map (this is also the placement standard referenced in E)

```
repo-root/
  CLAUDE.md                  # auto-loaded by Claude Code. Small. Pointers only.
  AGENTS.md                  # 5 lines. Points Codex/other agents at CLAUDE.md. No duplication.
  README.md
  pyproject.toml
  .gitignore  .env.example
  gov/
    OPERATING_RULES.md       # HOW work is done. Standing rules.
    MISSION.md               # WHAT and WHY. Operator-owned. Lives outside the rules.
    DECISIONS.md             # Append-only decision log.
    GLOSSARY.md              # Plain-English terms for operator output.
    review_rubric.md         # The fixed review checklist (section G).
    naming_allowlist.txt     # Reviewed exceptions to the naming lint.
    naming_debt.txt          # The existing 210-item backlog. May only shrink.
    root_allowlist.txt       # Every entry allowed at repo root.
  state/
    session.md               # THE one state file. Current phase + single next action.
    plan.md                  # Active plan with checkboxes.
    handoff.md               # Written before planned stops.
    blocked.md               # Written on any halt. What mismatched, what was tried.
    operator_inbox.md        # Messages waiting for the operator.
    locks/                   # One JSON lock per running job. (gitignored)
    snapshots/               # Rotated copies of session.md, keep 20. (gitignored)
  memory/
    INDEX.md                 # One line per standing rule. The retrieval entry point.
    candidates.md            # Observations not yet promoted.
    standing/                # One file per domain: pipeline.md, evaluation.md, infra.md, agents.md
    journal/2025-01-15.md    # Daily log. Dates allowed HERE ONLY.
    attic/2025-01.md         # Dead memory, kept for audit. Dates allowed HERE ONLY.
  src/                       # Pipeline code.
  tests/                     # Characterization tests first, then unit tests.
  eval/                      # Eval harness, fixed eval sets, rubrics.
  evidence/
    ISS-0142/                # One directory per unit of work. The audit chain.
  ops/
    smoke.sh  snapshot.sh  reproduce.sh  cutover.md   # Runbooks and live-run scripts.
  tools/                     # Every enforcement script named in this design.
  .agents/
    outbox/  heartbeat/  killed/          # Agent payloads and watchdog data. (gitignored)
  .scratch/                  # THE single scratch location. Gitignored. 24-hour TTL.
```

Nothing else may exist at root. `gov/root_allowlist.txt` lists the entries above; `tools/lint_root.py` fails CI on any addition.

### A.2 What each governing file contains, and what it must never contain

**CLAUDE.md** — maximum 150 lines, enforced by `tools/check_memory_size.py` in CI. Exact section headings:

```
## What this file is
## Where things live            (the directory map, one line per directory)
## Before any work             (the boot sequence, section C)
## Phase discipline            (one line per phase, section D; details in gov/OPERATING_RULES.md)
## Halt conditions             (short list; full list in the rules file)
## How to speak to the operator
## Pointers                    (links to gov/, memory/INDEX.md, state/)
```

Must NEVER contain: mission, goals, task lists, progress, status, dates, version numbers, metric targets, names of people, anything with a shelf life. It is a boot loader, not a dashboard.

**gov/OPERATING_RULES.md** — exact section headings:

```
## 1. Scope
## 2. How these rules change
## 3. The phases
## 4. The single-next-action rule
## 5. Drift detection and stop procedure
## 6. Naming and placement
## 7. Evidence and the audit chain
## 8. Memory: promotion and pruning
## 9. Agents: payloads, canaries, budgets, kills
## 10. Halt conditions (full list)
## 11. What these rules must never contain
```

Must never contain: goals, deadlines, "current" anything, counts, targets. Section 2 says: rules change only by PR with operator approval; no rule file ever carries a version number or a date in its name; a rule that references a goal is deleted on sight.

**gov/MISSION.md** — this is where goals live, outside the rules:

```
## Mission            (one paragraph)
## Current objective  (exactly one; replaced, never appended)
## Success measures   (observable effects, not counts alone)
## Non-goals
## Closed objectives  (one line each, link to evidence)
```

Rules files may link to MISSION.md but never copy from it. That is the structural fix for stale rules: there is exactly one place where "what we want" exists, and zero places where it is duplicated.

**gov/DECISIONS.md** — append-only. Corrections are new entries that reference old ones. Entry format:

```
### D-0042 — chunker splits on headers only
- Date:
- Decision:        (one sentence)
- Reason:
- Alternatives rejected:
- Evidence:        (link to evidence/ISS-…)
- Reversible:      (yes/no + how)
- Requested by:    (operator, or agent proposal approved by operator)
```

---

## B. MEMORY ARCHITECTURE

The principle: after any context reset, the agent knows only what disk tells it. So memory lives in four layers with different load costs, and only the cheapest layer is always loaded.

### B.1 Layers and load rules

1. **Always loaded:** CLAUDE.md (≤150 lines). Nothing else is automatic.
2. **Loaded at every session start:** `memory/INDEX.md` (≤120 lines, CI-enforced). One line per standing rule:
   `- [pipeline] chunker splits on headers only — memory/standing/pipeline.md — last verified 2025-01-10`
3. **Loaded on demand:** `memory/standing/<domain>.md` (each ≤250 lines). Loaded only when the task touches that domain. Retrieval ritual is mechanical: before INTAKE closes, run `grep -ri "<task keywords>" memory/` and read what matches. This is a step in the boot sequence, not a suggestion.
4. **Written continuously, read rarely:** `memory/journal/<date>.md` — what happened, what failed, what it cost. `memory/candidates.md` — observations awaiting promotion.

### B.2 Standing entry format (every entry is checkable)

```
### chunker splits on headers only
- Rule:          (a statement that can be verified true or false)
- Why:           (one line)
- Source:        (D-0042 / evidence link / failure date)
- Promoted:
- Last verified:
- Verify by:     (exact command or check)
```

An entry without a "Verify by" line cannot be promoted. That is what makes pruning possible without judgment calls.

### B.3 Promotion rule: observation → candidate → standing

- **Observation → candidate:** written to `candidates.md` with date and evidence link, the same session it is noticed.
- **Candidate → standing:** requires (a) two independent observations with links, OR (b) one failure that cost more than one hour or a stated token amount — PLUS a "Verify by" method, PLUS approval from the operator or the dual-model review gate.
- Candidates.md is capped at 150 lines. Cap pressure forces a hygiene pass: promote, or drop to journal. Nothing lingers.

### B.4 Pruning (mechanical, scheduled, logged)

- `tools/memory_hygiene.py --report` runs at every session start and lists standing entries whose "Last verified" is older than 30 days.
- Each stale entry is re-verified by running its "Verify by" command. Pass → date refreshed. Fail or no longer relevant → demoted to `memory/attic/<month>.md` with a one-line reason. Never deleted — audit requirement.
- Every promotion and demotion is logged in the journal. The history of what the system believed is reconstructable.

---

## C. SESSION PERSISTENCE + RESUME

### C.1 What is written, and exactly when

`state/session.md` — exact format:

```
- Session ID:
- Last write (UTC):
- Phase:            (INTAKE | CHARACTERIZE | PLAN | EXECUTE | VERIFY | REVIEW | CUTOVER | CLOSE)
- Task:             (issue ID + one line)
- Single next action:   (ONE sentence)
- In-flight job:    (none | name, pid, log path, heartbeat path)
- Blockers:         (none | list)
- Spend so far:     (tokens, wall minutes)
- Git:              (branch, HEAD sha at last write)
```

Written: at session start; at every phase transition; before launching any job; after any job completes; every 10 minutes during long jobs (done by the `tools/longrun` wrapper, not by the agent remembering); and before any planned stop (plus `state/handoff.md`).

Every write is atomic: write to `session.md.tmp`, then `os.replace`. Before each overwrite, the old file is copied to `state/snapshots/` (keep 20, rotated). Session.md, plan.md, handoff.md, blocked.md are committed to git at phase boundaries and at CLOSE. Locks and snapshots stay gitignored.

Long jobs run only via `tools/longrun <name> -- <cmd>`, which: creates `state/locks/<name>.json` (pid, started, host), heartbeats it every 30 seconds, tees output to a log, and rewrites session.md every 10 minutes.

### C.2 The exact resume ritual after a crash or close

```
1. tools/clean_scratch.sh                  # delete .scratch entries older than 24h; log the count
2. df -h .                                 # disk under 80% full, or warn the operator first
3. cat state/session.md
   - missing or corrupt → restore newest state/snapshots/session.*.md
   - that also bad → STOP. Write state/blocked.md. Tell the operator.
     NEVER reconstruct state from model memory. Context after reset is not evidence.
4. git status && git rev-parse HEAD        # must match the Git line in session.md
   - mismatch → STOP, write blocked.md with both values, flag the operator
5. ls state/locks/                         # for each lock:
   ps -p <pid>                             #   alive → job still running; tail its log
   # dead AND heartbeat older than 5 min → mark job crashed, read log tail,
   # per plan: retry once or flag. Never silently restart.
6. grep -ri "<task keywords>" memory/      # load relevant standing memory
7. tools/memory_hygiene.py --report        # stale-rule list; hygiene if needed
8. Read state/plan.md; find first unchecked step
9. Say to the operator, in two sentences: "Resumed. Phase: X. Next: Y."
10. Do exactly the single next action. Nothing else comes first.
```

---

## D. EXECUTION PROTOCOL — MILITARY ORDER

### D.1 The phases, in order, forward-only

**0. INTAKE.** Exit requires `evidence/ISS-####/issue.md` with these exact headings:

```
## Problem             (one paragraph, plain English)
## Measured scope      (the count command + its pasted output. Estimates banned.
                        "~923 keys" would have failed this gate; the command
                        would have printed 1,644 before execution began.)
## Data path trace     (every stage the data passes through, file:line each,
                        and EVERY chokepoint where the effect can die)
## Acceptance criterion (the observable effect in real output, and how it will be shown)
## Budget              (tokens, minutes)
## Out of scope
```

**1. CHARACTERIZE.** Write tests that capture current behavior BEFORE any change. Committed before the fix commit. Enforced mechanically in section F.

**2. PLAN.** `state/plan.md`: maximum one page, maximum 7 steps. Each step declares `files_in_scope` and the evidence it will produce. Timebox: 30 minutes. Exactly one review round (the gate in G), exactly one revision allowed. A second dispute goes to the operator with both review payloads attached. This is the structural end of the v1→v4 planning loop: the protocol makes a third review round impossible, not merely discouraged.

**3. EXECUTE.** Steps in order. After each step: save evidence, update session.md, run the drift check:

```
git status --porcelain     # any changed file NOT in this step's files_in_scope
                           # = drift = HALT. Log it. Mini-replan (one round) or escalate.
```

**4. VERIFY.** Acceptance means the effect appears in real output. Run the real pipeline on a small real input via `ops/smoke.sh` on the actual GPU — offline tests are not a preflight. Then read the actual output and paste the verbatim quote into evidence. Counts and keyword matches are supporting data, never the verdict. If the change was not meant to move a metric, run `eval/run_compare.sh` (fixed eval set, same seed, before vs after) and attach proof the metric did not move.

**5. REVIEW.** The bounded dual-model gate (section G).

**6. CUTOVER** (risky infra only, per `ops/cutover.md`): isolate the work → clone the data (`cp -al` hardlink clone) → verify the clone (counts, checksums, sample reads) → atomic switch via symlink rename → smoke check → previous version kept as a symlink for instant rollback. Snapshot first via `ops/snapshot.sh` (retention: 5 — this kills the 48GB accumulation pattern).

**7. CLOSE.** Update journal and candidates. Set session.md to IDLE or the next task. Write handoff.md if stopping. Operator summary: maximum 5 sentences, plain English.

### D.2 Halt conditions (STOP + flag, no exceptions)

1. State file and repo disagree.
2. A test that was green before this change is now red.
3. Any urge to add a cap, threshold, thinner, or sampling tweak to move a metric. The knob IS the bug. Halt and escalate with the evidence.
4. A severity-1 review finding still open after one fix round.
5. Budget exceeded: tokens, minutes, or disk.
6. Two consecutive failed attempts at the same step, or 30 minutes stuck. The agent writes what it tried to blocked.md and flags the operator. Silent sitting is a protocol violation, and the watchdog (below) makes it physically visible.
7. Acceptance not observable in real output. The task is not done. Continue or escalate — never declare done.

### D.3 The watchdog (the freeze killer)

`tools/watchdog.py` runs as a systemd user service (`Restart=always`), checking every 60 seconds:

- Every `state/locks/*.json` and `.agents/heartbeat/*.json`: heartbeat older than 5 minutes → capture diagnostics (`py-spy dump --pid <pid>`, log tail) → kill the process group → write the record to `state/blocked.md` and a one-sentence message to `state/operator_inbox.md`.
- The four-hour freeze becomes a five-minute freeze with a diagnosis attached and an operator flag.

---

## E. NAMING + FILE PLACEMENT STANDARD

### E.1 Banned patterns (exact regex, `tools/lint_names.py`)

```python
import re

BANNED_WORDS = (
    "honest|real|final|new|fixed|temp|tmp|improved|enhanced|better|"
    "latest|current|updated|old|legacy|backup|bak|copy|misc|wip|draft|junk"
)

NAME_RE = re.compile(
    rf"(?i:(?:^|[._\-])(?:{BANNED_WORDS})(?:[._\-]|$))"     # honest_  _final  -tmp.
    rf"|(?i:[._\-]v\d+(?:\.\d+)*(?:[._\-]|$))"              # _v2  -v1.3.
    r"|(?<!\d)\d{4}[._\-]\d{2}[._\-]\d{2}(?!\d)"            # embedded dates
)
```

Applied to every path segment. The word-boundary segments mean "prefix" and "fixture" pass; "final_report.md" and "notes_v2.md" fail. Dates fail everywhere EXCEPT allowlisted paths. `gov/naming_allowlist.txt` holds reviewed exceptions as path globs — and only these:

```
memory/journal/*
memory/attic/*
state/snapshots/*
tests/**
```

The existing 210-item backlog goes in `gov/naming_debt.txt`, which the lint reads as a grandfather list. CI enforces one extra rule: **the debt file may never gain lines** (`git diff` line-count check). The backlog can only shrink.

### E.2 Placement rules (`tools/lint_placement.py`, default-deny)

- `*.py` → only under `src/ tests/ tools/ eval/ ops/`
- `*.md` → only under `gov/ memory/ state/ evidence/` plus root `CLAUDE.md README.md AGENTS.md`
- `*.sh` → only under `ops/ tools/`
- Data artifacts (`*.json *.log *.txt *.csv`) → only under `evidence/ state/ .scratch/ .agents/ eval/`
- Any file matching no rule → violation. Root entries → must be in `gov/root_allowlist.txt` (`tools/lint_root.py`).

### E.3 The single scratch location

- Everything temporary goes in `.scratch/`. It is gitignored.
- `tools/clean_scratch.sh` runs at session start AND hourly via systemd timer: `find .scratch -mindepth 1 -mtime +1 -delete`. Deletion counts are logged to the journal.
- The promote-or-lose rule: anything worth keeping must be promoted into `evidence/` or `memory/` within 24 hours. Scratch cannot hold value, so value never dies there.
- Permissions: `umask 022` is set in the environment setup and in every tool wrapper, so no file is ever born unreadable. `tools/lint_perms.py` walks the repo and flags anything not owner-readable — the takeown incident cannot recur silently.
- `.gitignore` contains at minimum: `.scratch/  .agents/  state/locks/  state/snapshots/  __pycache__/  .venv/  .env`

### E.4 Mechanical enforcement (the part that makes it real)

```bash
# .git/hooks/pre-commit   (runs in under 2 seconds, staged files only)
python tools/lint_names.py --staged
python tools/lint_placement.py --staged
python tools/lint_root.py

# CI job "hygiene"        (every PR, whole repo)
python tools/lint_names.py --all
python tools/lint_placement.py
python tools/lint_root.py
python tools/lint_perms.py
python tools/check_memory_size.py
python tools/lint_knobs.py --diff origin/main...HEAD   # section H.2

# .git/hooks/commit-msg   (every commit links to its issue or is housekeeping)
# must match:  ^ISS-\d{4}: .+   or   ^(gov|memory|state): .+
```

---

## F. AUDIT SURVIVAL

The chain for any change, reconstructed by a hostile auditor who trusts nothing:

**1. Issue.** `evidence/ISS-0142/issue.md` — problem, measured scope with the pasted command output, data path trace, acceptance criterion, budget.

**2. Evidence.** Nothing mutating or evaluative runs bare. Everything runs through `tools/runlog ISS-0142 -- <cmd>`, which writes `evidence/ISS-0142/runs/<n>/` containing: `cmd.txt`, `stdout.txt`, `stderr.txt`, `exit.txt`, and `meta.json` (UTC time, git SHA, hostname, GPU model, environment hash from the lockfile). No logged run, no claim.

**3. Characterization-first, mechanically checked.** CI runs `tools/check_char_first.py ISS-0142 <merge-base>`: it checks out the base SHA, runs the PR's new test, and requires it to FAIL there. The failing output is stored in evidence. A test that never failed proves nothing — this makes the green-suite-cheat pattern structurally visible.

**4. Review verdict.** `evidence/ISS-0142/review.md` — both models' complete payloads, the rubric scores, the verdict. One round, both models, no drip.

**5. Diff and PR.** The PR touches only files in declared scope (CI checks against plan.md). PR body is generated from a template: issue link, measured scope, evidence links, review verdicts, rollback plan. Merge is blocked by `tools/check_audit_chain.py --pr` unless the evidence directory is complete.

**6. Post-merge proof.** `evidence/ISS-0142/postmerge.md` — on main, after merge: the acceptance command re-run with output attached; `ops/smoke.sh` live result; `eval/run_compare.sh` before/after (metric moved for the stated reason, or provably did not move); and the activation-marker grep: every feature emits a log marker, and CLOSE requires grepping the real run log for it. This is the structural answer to "committed + green + approved but never fired": **done is defined as the marker appearing in real output on main**, not as the merge.

**Reproduction and tamper-resistance.** `ops/reproduce.sh ISS-0142` checks out the recorded SHA and replays the acceptance command. CI rejects any PR that modifies the evidence directory of an already-merged issue. Each merge updates `evidence/INDEX.sha256`.

Auditor walkthrough, end to end: "Why did line 40 of src/chunker.py change?" → `git blame` → commit `ISS-0142: …` → PR → issue with measured scope → every command ever run for it → both review verdicts → the live proof on main → `ops/reproduce.sh ISS-0142` to re-run it themselves. No step requires trusting the agent.

---

## G. MULTI-AGENT COMMUNICATION CONTRACT

### G.1 The payload — every agent's FIRST and ONLY reply

Written to `.agents/outbox/<agent-id>.json`, validated by `tools/validate_payload.py`:

```json
{
  "schema": "agent-payload/1",
  "agent_id": "string",
  "task_id": "ISS-0142",
  "model": "string",
  "started_utc": "ISO8601",
  "finished_utc": "ISO8601",
  "status": "DONE | PARTIAL | BLOCKED | FAILED",
  "summary": "max 3 sentences, plain English",
  "findings": [
    {
      "id": "F1",
      "severity": 1,
      "claim": "string",
      "evidence": {"path": "string", "lines": "12-40", "quote": "VERBATIM text"},
      "recommendation": "string"
    }
  ],
  "work_done": [
    {"action": "string", "artifact": "path", "verified_by": "command", "result": "string"}
  ],
  "not_covered": [
    {"area": "string", "reason": "string"}
  ],
  "surprises": ["string"],
  "blockers": [{"what": "string", "tried": ["string"]}],
  "metrics": {"tokens_in": 0, "tokens_out": 0, "wall_seconds": 0, "files_read": 0, "commands_run": 0},
  "next_action": "one sentence",
  "confidence": "high | medium | low",
  "confidence_raiser": "what would raise it"
}
```

Validation rules that make toothpaste impossible:

- Every key required. `not_covered` may NOT be empty — if scope was fully covered, the entry must say so and state the proof ("scope was files X, Y, Z; all three read in full"). The honest gap list is structurally mandatory, not a virtue.
- Every finding must carry a verbatim quote. The verifier model re-reads the quote and checks the claim does not over-extend it — the claim's support must be inside the quoted text. Over-extension is severity-1. This kills the substring-match self-grade.
- PARTIAL or FAILED requires non-empty blockers.
- A schema-invalid payload is not debated: one automatic retry for schema errors only, then the agent is killed and respawned with tighter scope, or escalated. Findings never arrive across iterations because follow-up questions do not exist in this protocol.

The spawn template every sub-agent receives states the one-shot rule in writing: "Return everything in your first reply. You will not be asked follow-up questions. Anything you cannot cover goes in not_covered."

### G.2 Early detection and kill (the 72-agent lesson)

- **Harness self-test first.** `tools/agent_harness.py` spawns one trivial agent and validates the full round trip before ANY fleet launch. A broken harness can never again be mistaken for slow progress.
- **Canary sequence, automatic.** Fan-out above 3 runs 1 → validate payload AND spot-check one evidence citation (does file:line resolve? is the quote verbatim?) → 5 → validate → full fleet. Any failure kills the launch before real money is spent.
- **Budgets enforced by the harness, not the agent.** Spawn requires `--budget-tokens` and `--budget-minutes`. Fleet default cap: 20 agents, overridable only with `--operator-override`. A fleet token cap stops the 2M-token bleed at the cap, automatically.
- **Heartbeat + kill.** Agents heartbeat `.agents/heartbeat/<id>.json` every 60 seconds with their current step. Stale 5 minutes, or 2 intervals with the step unchanged and no new evidence files → watchdog captures diagnostics, kills the process group, writes `.agents/killed/<id>.json` with the reason, salvages any partial payload, flags the operator in one sentence.
- **Burn-rate check.** Tokens past 50% with zero findings → lead polls; at 80% with zero findings → kill. "Working" with nothing to show is a failing agent, caught early.

### G.3 The bounded dual-model review gate

Two different models (e.g., Claude and Codex). Each receives: the diff, the issue, the acceptance criterion, and `gov/review_rubric.md`:

```
1. Does the diff do what the issue says — and nothing more?
2. Does any change add a cap, threshold, thinner, truncation, or sampling tweak
   that exists to move a metric?  (yes = severity-1, automatic)
3. Is every quality claim backed by a verbatim quote that FULLY supports it?
4. Do the tests assert behavior, or do they cheat — mock call counts,
   substring smoke, broad excepts, tests that re-implement the code?
5. Is the effect observable in real pipeline output, with the run log attached?
6. Was the whole data path traced, and every other chokepoint ruled out?
7. Are names and placements compliant?
8. Can this be reverted safely?
```

Bounds: one round, both models in parallel, 20-minute timebox, verdicts as payloads. Both PASS → merge. A severity-1 → one fix round, one re-review. Anything unresolved after that → the operator decides, with both payloads attached. No third round exists.

### G.4 Operator voice (the operator is blind and reads by ear)

Fixed format, maximum 5 sentences, flat lists only (nested bullets read badly by ear), no emoji, no cheerleading, no jargon — say "the chunker dropped the table" not "the segmentation subsystem regressed":

```
"Status: verify. The fix fired in the live run on main.
Next: review by both models. Problem: none."
```

---

## H. TOP 5 FAILURE MODES AND THEIR STRUCTURAL PREVENTION

**1. Quality judged by count, keyword, or sample instead of meaning.**
Acceptance criteria must be observable effects proven with verbatim quotes from real output (INTAKE template, VERIFY phase). The review gate's rubric item 3 forces a second model to re-read each quote and confirm the claim stays inside it. Every plan must state how many complete outputs will be read end-to-end. Counts are supporting data and can never be the verdict.

**2. Knobs bolted on to force a metric.**
`tools/lint_knobs.py` diffs every PR and flags any new numeric constant, threshold, cap, truncation, or sampling parameter in `src/` unless the PR cites a DECISIONS entry backed by measured evidence. Rubric item 2 makes it an automatic severity-1. Halt condition 3 stops the agent mid-temptation. Post-merge proof must show the metric moved for the stated reason or provably did not move.

**3. False "done" — test cheats, work never wired in, offline-only passes.**
`check_char_first.py` requires the new test to fail at the base SHA. Rubric item 4 scans for test cheats. The activation-marker rule defines done as the feature's marker appearing in the real run log on main. `ops/smoke.sh` runs the real pipeline on the real GPU before VERIFY can close — offline tests are not a preflight, by protocol.

**4. Ungoverned scale-out — broken fleets, frozen agents, token bleed.**
Harness self-test before any launch. Automatic canary 1 → 5 → N with payload validation and evidence spot-checks. Per-agent and fleet budgets enforced by the harness. Watchdog kills 5-minute-stale agents with diagnostics attached. Fleet cap of 20 without explicit operator override. The "2/72 done, 68 FAILED" pattern dies at the self-test or the first canary.

**5. Workspace rot — scratch sprawl, naming decay, disk bloat, ACL lockouts.**
One gitignored `.scratch/` with 24-hour auto-clean and the promote-or-lose rule. Root allowlist plus default-deny placement lint in pre-commit AND CI. The naming regex blocks new violations at commit time, and the grandfathered debt file can only shrink. `umask 022` plus `lint_perms.py` prevents unreadable-file lockouts. Snapshot retention of 5 and an 80% disk alarm at session start prevent the 48GB accumulation.

The remaining lessons are covered where they live: estimate-scoping dies at INTAKE's measured-scope gate; the v1→v4 planning loop dies at PLAN's one-revision rule with no third round; drip-fed findings die at payload validation with no follow-up questions in the protocol.

### Build order (first session executes this, in order)

1. Create the directory tree and empty governing files.
2. Write CLAUDE.md, OPERATING_RULES.md, MISSION.md, review_rubric.md, the three allowlists.
3. Write the lint scripts and hooks; verify they fail on a deliberately bad file.
4. Write runlog, longrun, watchdog, clean_scratch; verify the watchdog kills a frozen dummy process.
5. Write agent_harness.py and validate_payload.py; verify the canary sequence on a 3-agent fleet.
6. Run `ops/smoke.sh` once against the live pipeline and file the output as `evidence/ISS-0001`.

---

## WHAT I DID NOT COVER

- **Multiple machines.** This design assumes one GPU VM and one operator. Locks and heartbeats are single-host; nothing here handles two VMs editing the same repo or a network file system.
- **Secrets.** Only the placement rule (.env gitignored, .env.example committed) is specified. Credential rotation, vaults, and key expiry are not designed.
- **Exact CI system.** All checks are portable scripts with exact commands, but I did not write the GitHub Actions / GitLab YAML that wires them in.
- **The full review rubric text.** Structure and the eight items are given; the exact scoring scale and per-item wording would need one drafting pass.
- **Issue tracker dependency.** I used files under `evidence/` so the design works with no external service. If the operator uses GitHub Issues, the mapping (ISS numbers to issue numbers) is not specified.
- **Windows-style ACLs.** The takeown incident suggests restrictive ACLs; I assumed a Linux VM and addressed it with umask plus a permissions lint. A Windows or NTFS environment needs a different mechanism.
- **Per-model prompt adaptation.** The payload schema is model-agnostic JSON, but I did not write the per-model spawn templates (Claude vs. Codex phrasing differences).
- **Watchdog supervision.** Systemd `Restart=always` plus a session-start liveness check is specified, but a silently wrong-but-running watchdog (e.g., scanning the wrong directory) is not detected by anything.
- **Concurrent edits to the same file.** Job-level locks exist; fine-grained file-level locking between two live agents does not.
- **Operator overrides.** If the operator orders a knob added by hand, the system logs it as a decision but cannot and does not prevent it. That authority is the operator's by design.
- **Long-horizon memory growth.** The attic and size caps handle months; I did not project or design compaction for multi-year accumulation.
- **Real-time interruption.** The operator can leave messages in `state/operator_inbox.md`, but mid-run interruption of a live agent by the operator is only specified for halts, not for steering.
- **Dollar costs.** Budgets are in tokens and minutes. A per-model price table converting those to dollars is not included.
- **Disaster recovery of the VM itself.** Snapshot retention is specified; full VM restore from a dead disk is not.