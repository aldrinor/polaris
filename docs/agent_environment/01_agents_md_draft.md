# AGENTS.md — agent operating rules

This file is permanent. It holds how work is done, not what is being worked on.

The mission lives in `docs/mission.md`. Model names and provider limits live in
`agent_control/model_lock.json`. Neither is repeated here. If you are reading this file to
find the current goal, you are reading the wrong file.

This file is a router. Detail lives in `docs/agent_environment/`. Budget: 260 lines,
enforced by CI job `governance_budget`. A file that grows without limit stops being read.

The budget comes from measuring this content at 241 lines and adding headroom. An earlier
draft set it at 200 before the content existed, then exceeded it. Shaving real rules out
to hit an invented number is the same mistake as adding a knob to move a metric. Measure
first, then set the limit.

## 1. Boot and resume

Run on every session start, every restart, and after any context reset. Do not skip a step
because the session feels continuous. Detail: `03_memory_and_session.md`.

1. Verify pins against `agent_control/policy/canonical_pins.json`. Mismatch is `H1`. Stop.
2. Verify the enforcers: `python scripts/check_hook_liveness.py`. A dead hook is `H13`. A
   rule with a dead enforcer is not a rule, so nothing after this can be trusted.
3. Read this file, then `docs/lessons/index.md`.
4. Read `state/session/resume_pointer.json`: the unit, the phase, the single next action.
5. If it carries a halt, deal with the halt. Not the backlog.
6. Read the active `plan.md` and `agent_control/emergency_playbook.md`.
7. Reconcile processes by the evidence rule in section 6.
8. Resume every run from its closest checkpoint. Never fresh. If a fresh relaunch of the
   same run is starting, kill it by process id before it overwrites the good snapshot.
9. Append a resume entry to `journal/session_log.md`.
10. Say one line: phase, last action, next action, halt flag. Then do the next action.

Target: executing within ten minutes of session start.

## 2. The work unit and the eleven phases

Every unit of work is one GitHub issue, created before any branch, code, or brief. The
identifier is `i<issue>_<snake_slug>`. The record is `operations/units/<identifier>/`.

State the current phase and the single next action in every operator-facing message.
Acting outside the current phase is `H2`: stop and flag. Do not improvise.

| Phase | What happens | Exit artifact |
| --- | --- | --- |
| `INTAKE` | Issue created first, with acceptance criteria | `mission.md` |
| `SURVEY` | Measure the whole surface with commands. Trace the data path end to end and list every chokepoint, not only the one you tripped on | `scope.json`, `path_trace.md` |
| `DIAGNOSE` | A read-only investigator on a different model names the root cause and the exact change boundary | `reviews/diagnosis/` |
| `PLAN` | One `plan.md`. One review round. Then a freeze line and a hash | `plan_lock.json` |
| `BASELINE` | Characterization test written first and failing now. Real output captured | `evidence/baseline/` |
| `BUILD` | Smallest diff, only the paths the frozen plan allows | `evidence/change_diff.patch` |
| `VERIFY_LOCAL` | Tests, static checks, a seconds-long smoke, and a negative control | `verification/` |
| `REVIEW` | Different-model gate, five iterations maximum, verdict read from the file | `reviews/change/` |
| `PROVE_LIVE` | One small real run on the real path. The effect appears in real output | `verification/live_preflight.json` |
| `MERGE_ACTIVATE` | The release service merges. Activation is separate. Re-prove after merge | `release/` |
| `WRAP` | Journal, memory promotion, orphan sweep, scratch cleaned, issue closed | clean `git status` |

A phase may be marked not applicable only with a written reason. That is discipline-only
and unenforceable; the reviewer is the only check on it.

Order inside `SURVEY` is fixed: issue exists, then grep every call site and consumer, then
a seconds-long smoke, then brief the reviewer. Hand the reviewer the call-site scan so it
verifies rather than discovers. That is what drops review iterations from five to one.

Never plan from an estimate. Every count in `plan.md` carries the command that produced
it. A tilde followed by a digit fails `plan_lint`.

## 3. Verification

Never state a quality verdict from a count, a keyword, a pattern, a threshold, or a
sample. That includes your own numbers about your own data. Read the meaning line by line.
A count is an inventory. It is never a verdict.

Before writing any quality number, ask: did this come from reading the meaning, or from
counting? If from counting, stop and go read.

> acceptance = the effect ACTUALLY APPEARS in the real output, FAILS LOUD if not — NOT
> "the reviewer approved the diff", NOT "tests green". WHY: diff-review and green tests
> check CODE, not OUTPUT behaviour.

Offline tests are not a preflight. A fix is proven by one small real run on the real path.
A detection fix is proven by an independent detector importing zero production code,
because production and its test can share a blind spot and both pass.

Never let a failure path record success. A blank result, a stub, a swallowed exception or
a truncated response must raise, or set an explicit degraded status. This is the most
recurring defect in this project's history.

Before rebuilding anything, grep for an existing module or flag. Winning machinery is
usually already built and switched off, and default-off looks exactly like not-built from
the output. Every campaign ends with an explicit activation step.

Artifact chain and gates: `05_audit_trail.md`.

## 4. Review and independence

The builder never grades its own work. A reviewer must be a different model family.
Unknown lineage fails closed.

Diagnosis is separate from building. The investigator is read-only and specifies the exact
change; the builder builds only that. Fusing them turns a confident wrong diagnosis
straight into wrong code.

Reviews are capped at five iterations, all findings front-loaded in iteration one. Read
the verdict from the last `verdict:` line of the written file, never from an agent's own
summary; self-reported verdicts drift toward completion.

Every agent reply is complete in its first reply, in one payload, including what it did
not cover. Asking an agent "anything else?" is banned. Contract: `04_agent_contract.md`.

When you find a violation of a rule that was already locked, add a gate that fails loud.
Do not just fix the instance. A written rule does not stop recurrence.

## 5. Autonomy

Once authorised, execute. You do not decide when to stop.

Stops come from three places only: a reviewer verdict, a numbered halt, or the operator
typing stop. These are not halt conditions: a natural cadence checkpoint, a count of
merged work, a good place to check in, a clean resource state, or the operator not having
been updated recently.

Once a bug is traced and the fix is safety-neutral, fix, test, gate and relaunch straight
away. Hold only when the path forward would override an operator lock or change safety
behaviour. Writing a long note asking a question with no real decision in it is the
failure this rule exists for.

After a crash downstream of a checkpoint, resume from the closest checkpoint. Never re-run
fresh. A downstream crash does not corrupt intact upstream data, and a fresh relaunch can
overwrite the good snapshot.

Four layers keep long work alive, preserved because they are proven live:

> 1. **Detached work survives session-close.** Launch long runs `setsid nohup` on the box
>    so they finish regardless of the agent's session/loop/stall. The output files get
>    written no matter what — the FLOOR.
> 2. **Box-side watchdog survives the agent's stall.** Alongside each detached run, a
>    bounded watchdog (every ~5 min: if proc dead + no output + attempts<3 → relaunch
>    `--resume`). A crash resurrects without the agent. Bounded (max 3) so it can't
>    infinite-loop and burn credit.
> 3. **The monitoring loop re-arms on EVERY outcome** — success, abort, crash, error, or
>    uncertainty — UNLESS the whole job is done + the summary written. A failure NEVER ends
>    the loop; it triggers the playbook then re-arms. When unsure, the default is act +
>    relaunch + re-arm — NEVER freeze.
> 4. **Durable plan/playbook FILES survive a context reset.** On resume, read the plan +
>    emergency playbook off disk and reattach — the files ARE the memory.

No wake may begin with a command that can prompt for approval. Wakes open read-only. Bulk
deletion belongs to the janitor. Four hours were lost to a delete on line one of a wake
with nobody present to approve it.

Never background a process with a shell `&` inside a tool call. It gets orphaned and
killed silently while the tool reports success. Use the tool's own background mode.

Completion means committed. Commit per unit. Every long run self-commits its output as its
final step, so a finished build cannot sit uncommitted because a session died.

## 6. Anomalies, processes and resources

> on ANY anomaly read the actual log / reasoning / raw-LLM-IO line-by-line RIGHT THEN —
> never surface liveness, never "wait and see." Distinguish a slow call from a hang with
> EVIDENCE: the raw-LLM-IO capture-dir mtime is THE truth (a big reasoning call can run ~9
> min log-silent then return); CPU state, `ep_poll`/`do_poll` wchan, and file mtimes
> corroborate. A run is HUNG only if llm_io AND log AND phase are ALL frozen past the
> timeout — only then kill PID-SCOPED (never name-global pkill; the operator runs
> concurrent sessions) + relaunch `--resume`.

> result lands → line-by-line audit → if it fails the bar → forensic root-cause → FIX →
> relaunch ASAP (prefer `--resume` from the saved checkpoint to skip re-work) → repeat.
> Bounded ≤3 fix-cycles per unit, then mark best-achieved + surface the residual lever.

> faithfulness NEVER relaxed; PID/slug-scoped kills only; commit-per-unit (uncommitted
> work on a shared tree gets wiped); log every incident; if a paid service nears empty,
> notify the operator.

One heavy review process at a time. Inventory processes before and after every heavy step
and kill orphans by process id. Heavy runs belong on the box, not the laptop.

When a run drifts, stalls, dies or goes off the fix direction, escalate to the two
independent reviewer roles immediately. They decide hold, investigate, fix and relaunch
from the nearest checkpoint, or let it run. The executing agent does not own that call.

## 7. Models and budgets

Every call verifies its model against `agent_control/model_lock.json` before sending. A
mismatch fails the call. Stale defaults drifting into side roles caused three incidents.

Reasoning effort and output budgets go to the real provider maximum.

> A starved budget truncates reasoning → empty content → fail / coverage-collapse
> ('half-ass job'). `max_tokens` is a CAP, not a target (billing is by actual usage) → a
> generous cap is free insurance.

> **Read the API doc, DON'T guess** the allowed max per model.

The lock records each limit with a hash of the API response it was read from and the date.
A budget with no evidence entry is invalid.

Never ask a model to do deterministic bookkeeping. Merging identifier lists or copying span
offsets by hand fails at scale. Emit a short marker and compute the exact value in code.

Ship every new layer behind a flag that is default-off and byte-identical when off, then
activate it in the same campaign. Off forever is the same as not built.

## 8. Talking to the operator

The operator is blind and reads by ear. Short sentences. Subject, verb, fact. Numbers and
names said plainly. No jargon, no cheerleading.

Every status message is four lines: phase, what was completed, the single next action, the
halt flag.

Announce every background launch in one spoken line as it fires, and read the result,
verdict and counts inline when it finishes. Progress that lives only in a visual panel
does not exist.

Self-check before sending: would a person understand this if read aloud once?

## 9. Halt conditions

Each writes `journal/halts/<utc>_<id>.md`, sets the halt flag, and is spoken in one line.

| Id | Condition |
| --- | --- |
| `H1` | Canonical pin mismatch |
| `H2` | Action attempted outside the current phase |
| `H3` | `SURVEY` plus `PLAN` exceeded 90 minutes. Split the work unit |
| `H4` | A blocking finding unresolved at review iteration five |
| `H5` | Same root cause twice. Stop patching, write the postmortem first |
| `H6` | Memory above 85 percent or CPU above 90 percent for two minutes, or GPU exhausted |
| `H7` | Sub-agent failures at or above 20 percent of launched, or three in a row |
| `H8` | Tokens or wall-clock at twice the frozen plan budget |
| `H9` | The fix would override an operator lock or change safety behaviour |
| `H10` | An action would overwrite a good checkpoint |
| `H11` | A phase gate reached with a required artifact missing |
| `H12` | A paid service near empty |
| `H13` | An enforcer is dead: hooks unwired, or `core.hooksPath` outside the repo |
| `H14` | No valid rollback exists for a risky cutover |

## 10. Forbidden

Merging your own work. Editing a stored verdict. Editing `agent_control/`. Changing branch
protection. Deleting audit evidence. Creating a file outside the repository tree or the
current scratch session directory. Adding a configuration knob to move a metric; if you
are adding a knob to make a number move, the knob is the bug.
