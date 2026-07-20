# 03 — Memory and session persistence

## Part one: memory

### The problem this solves

Memory must grow across sessions and never reset. But everything that grows must not be
loaded at every boot, or the boot read gets larger every week until it stops being read.
So memory is split into three tiers. Only the first is always loaded.

### Tier 0 — always loaded, with a hard line budget

| File | Budget | Enforced by |
| --- | --- | --- |
| `AGENTS.md` | 260 lines | CI job `governance_budget` |
| `agent_control/constitution.md` | 250 lines | CI job `governance_budget` |
| `docs/lessons/index.md` | one line per rule | CI job `governance_budget` |

The boot read stays under about 500 lines forever. The budget is a `wc -l` check that
fails the build. Without a mechanical budget these files grow, because every incident
feels worth adding.

### Tier 1 — indexed, loaded when the index says it is relevant

Theme hubs in `docs/lessons/`: `review_gate.md`, `verification.md`, `autonomy_recovery.md`,
`resources.md`, `naming_placement.md`, `communication.md`, `debugging.md`. Each is capped
at 300 lines. Each rule carries at least one incident link.

`docs/lessons/index.md` has one line per rule, in this exact format:

```
L-041 | triggers: fetch, cache, resume | rule: resume from the closest checkpoint, never fresh | hub: autonomy_recovery.md
```

Retrieval is a required step, not a hope. In the `SURVEY` phase, grep the index for the
trigger words that match the work unit and write `lessons_consulted: L-007, L-041` into
`plan.md`. A lesson that applied and was not consulted is a review finding.

This is the honest seam: the grep is mechanical, the judgement of which triggers match is
not. Marked discipline-only.

### Tier 2 — raw observations, append-only, never loaded whole

`operations/memory/observations/` holds one JSON file per observation. Writing one costs
nothing and passes no gate. The point is that noticing is free.

```json
{
  "observation_id": "7f50e0a1",
  "recorded_utc": "2026-07-19T04:12:33Z",
  "unit_id": "i1402_fetch_cache_resume",
  "statement": "A blank provider completion was recorded as succeeded.",
  "basis": "observed",
  "root_cause": "The status mapping accepted empty content as ok.",
  "scope": ["provider_client", "status_mapping"],
  "evidence": [
    {"path": "operations/units/i1402_fetch_cache_resume/evidence/smoke/log.txt",
     "sha256": "…", "location": "line 44",
     "quote": "content='' finish_reason=None status=ok"}
  ],
  "applies_when": ["declared output is required"],
  "does_not_apply_when": ["zero output is valid in the action contract"],
  "revalidate_when": ["the status schema changes"],
  "status": "active"
}
```

There is no confidence score. A number attached to a judgement invites the judgement to be
made by the number. That is the faithfulness ghost in miniature.

### How memory grows: observation, candidate, standing rule

**Observation to candidate.** At `WRAP`, an observation becomes a candidate if any of
these is true: it cost thirty minutes or more, a grep of the observation store finds a
similar earlier entry, or the operator flagged it.

A candidate is a file in `operations/memory/candidates/` naming the rule, the incidents,
and the enforcement that would be shipped with it.

**Candidate to standing rule.** Promotion requires all of the following. This is checked
by CI job `rule_has_enforcer`.

1. A second independent incident, or an explicit operator instruction.
2. The rule is general beyond one file.
3. A characterization test that fails on the old behaviour and passes on the new.
4. A shipped mechanical enforcer in the same commit: a hook, a CI check, a schema field or
   a test. If mechanical enforcement is impossible, the rule ships tagged
   `discipline-only, unenforceable`, and that tag is a required field.
5. A different model approves the rule and its enforcer.
6. The operator commits it, if it belongs in `agent_control/`.

A rule with no enforcer and no honest tag is rejected by CI. This is the mechanism against
the pattern where an already-locked rule was re-violated in three separate later
campaigns: the rule existed as prose, and prose does not fire.

### Statuses, because memory is never deleted

Five statuses: `active`, `contested`, `superseded`, `revoked`, `revalidation_required`.

Two records that contradict each other are both kept and both marked `contested`, linked
to each other. Work stops if a contested pair touches the active plan. Deleting the loser
of a contradiction destroys the evidence that the question was ever open. This is from
proposal B; proposal A had only active and retired, which cannot express it.

Any record about something that can change carries a `revalidate_when` trigger: a provider
API change, a dependency lock change, a moved source path, a cache schema change. When a
trigger fires, retrieval returns the record marked `revalidation_required`. It does not
silently return it as current.

### Pruning, which is not deletion

Every twentieth session, `scripts/memory_audit.py` runs at `WRAP` and does three things.

1. Candidates older than thirty sessions with no second incident move to
   `operations/memory/decisions/not_recurring.md`, with the reason recorded.
2. Any standing rule whose named enforcer no longer exists in the tree is reported to the
   operator in one plain line. The rule may still be live but unguarded, which is exactly
   how locked rules got re-violated.
3. Superseded rules get a `superseded_by` field and move to the retired hub.

Nothing is deleted. Everything stays greppable in the file and in git history.

## Part two: session persistence

### What is on disk and when it is written

| File | Holds | Written |
| --- | --- | --- |
| `state/session/resume_pointer.json` | unit, phase, next action, halt | every phase change, every ten tool calls, before any detached launch |
| `state/session/heartbeat` | empty file, its modification time is the signal | every tool call |
| `state/session/processes.json` | pid, process group, command, log path, llm io directory, watchdog pid | every launch and cleanup |
| `state/runs/<run_id>/manifest.json` | status, checkpoint path, last progress time | by the run itself, at every checkpoint |
| `journal/session_log.md` | the human-readable log | every phase gate and wrap |

### The resume pointer

```json
{
  "session_id": "s20260719t0412z",
  "unit_id": "i1402_fetch_cache_resume",
  "phase": "BUILD",
  "phase_step": "writing the diff for src/fetch/cache.py",
  "next_action": "run the fetch cache unit tests",
  "halt": null,
  "tool_calls_since_pin_check": 3,
  "updated_utc": "2026-07-19T04:12:33Z"
}
```

Exactly one next action. If there is more than one, the phase protocol has already been
broken.

### Writing it safely

Write to a temporary file in the same directory, flush, `os.fsync`, then `os.replace`.

```python
import json, os, tempfile
from pathlib import Path

def write_state(path: Path, payload: dict) -> None:
    directory = path.parent
    directory.mkdir(parents=True, exist_ok=True)
    handle, temporary = tempfile.mkstemp(dir=directory, suffix=".tmp")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as stream:
            json.dump(payload, stream, indent=2, sort_keys=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    except BaseException:
        Path(temporary).unlink(missing_ok=True)
        raise
```

`os.replace` is atomic on both Windows and Linux. A plain rename over an existing file is
not atomic on Windows, which is why it is named exactly. A crash mid-write leaves the old
pointer intact, never a truncated one.

Proposal B used SQLite with write-ahead logging for this. Rejected: JSON is readable by a
hostile auditor with `cat` and can be read aloud to the operator, and `os.replace` gives
the crash safety that SQLite was wanted for. Journals stay as append-only JSON lines,
where a partial last line is detectable and discardable.

### Completion means committed

Commit at every phase gate. Every detached run commits its own output as its final step.
A finished overnight build once sat uncommitted from 04:45 to 08:49 because the session
that would have committed it never got past its first command. The run committing itself
removes that dependency.

### Long runs

Launch detached, with the tool's own background mode, never a shell `&`. A process
backgrounded with `&` inside a tool call gets orphaned and killed silently while the tool
reports success. That cost about ten hours across two runs. The same command in the
foreground with the tool's background mode ran for seven hours and forty-eight minutes
cleanly.

Each run gets a bounded watchdog: every five minutes, if the process is dead and there is
no new output and fewer than three attempts have been made, relaunch with `--resume`. The
bound stops an infinite relaunch loop burning credit.

## The resume ritual

Identical after a crash, a context reset, or a clean start. Run `python scripts/resume.py`,
which performs these steps in order and refuses to continue past a failure.

1. **Verify pins.** Hash every file in `agent_control/policy/canonical_pins.json`. Compare
   working tree against the pin. A mismatch is `H1`: write the halt file, say one line,
   stop. No later step runs.
2. **Verify the enforcers.** `python scripts/check_hook_liveness.py`. A dead hook is `H13`.
   Rules with dead enforcers are not rules, so nothing else can be trusted.
3. **Read `AGENTS.md`, then `docs/lessons/index.md`.**
4. **Read `state/session/resume_pointer.json`.** This gives the unit, the phase and the
   single next action.
5. **If a halt is set, deal with the halt.** Not the backlog.
6. **Read the plan progress table** in `operations/units/<unit_id>/plan.md`. Completed
   phases are never redone. Each one has an evidence link proving it happened.
7. **Reconcile processes.** For each entry in `processes.json`, check `kill -0 <pid>`, the
   log modification time, the raw model input-output directory modification time, and the
   phase state.
   - Alive and progressing: reattach the monitor.
   - Dead with work pending: relaunch with `--resume`.
   - Frozen: a run is hung only if the model input-output directory, the log, and the
     phase are all frozen past the timeout. A large reasoning call can run about nine
     minutes with a silent log and then return. Only when all three are frozen, kill by
     process id, never by name, and relaunch with `--resume`.
8. **Resume runs from checkpoints.** For every run manifest with status running or failed,
   resume from its checkpoint path. Never fresh. If a fresh relaunch of the same run is
   found starting, kill that process first, before it overwrites the good snapshot. A
   downstream crash does not corrupt intact upstream data; a fresh re-run once discarded
   more than forty minutes of completed, paid retrieval work.
9. **Check the working tree.** `git status --porcelain`. Changes matching the current
   phase step continue. Anything unexplained moves to scratch and is noted in the journal.
10. **Append a resume entry** to `journal/session_log.md` with the pin hash, the unit, the
    phase and the next action.
11. **Speak one line to the operator**, then do the action:

```
Resumed. Unit i1402. Phase: build. Next action: run the fetch cache unit tests. Halt flag: none.
```

Target: executing within ten minutes of session start.

A clean start with no work in flight runs the same ritual. Step 4 finds phase `idle`, and
the agent goes to `docs/mission.md` or waits for an assignment.

### Drift check during a session

Every ten tool calls or fifteen minutes, whichever comes first: re-verify the pins, re-read
the resume pointer, and restate the phase and next action. If the action about to be taken
does not serve the stated next action, that is drift. Stop and flag `H2`. Do not improvise
a correction.
