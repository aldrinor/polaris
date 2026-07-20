# 00 — Setup plan

## Target machine

Primary target is the Linux GPU VM. The Windows dev box is a secondary target and is
named at every step where the command differs. This is stated first because both source
proposals assumed Linux only. A cleanup timer written as a systemd unit does nothing on
the Windows box, and the Windows box is where the agent commits from. A design that only
fires on one of the two machines is the same "built but not wired" bug one layer up.

Windows equivalents used throughout:

| Linux | Windows |
| --- | --- |
| systemd timer | Scheduled Task running as SYSTEM |
| `setsid nohup` | the agent tool's own background mode |
| `sha256sum` | `Get-FileHash -Algorithm SHA256` |
| `chmod` / ACL reset | `icacls` |
| root-owned janitor | SYSTEM-owned janitor |

## Measured starting state

These were measured on 2026-07-19, not estimated. Both enforcement layers in this repo
are dead right now.

1. `.claude/settings.json` contains `{"hooks": {}}`. The block is empty. The four hook
   files in `.claude/hooks/` are never called. Verified by reading the file.
2. `git config core.hooksPath` returns `C:\POLARIS\.git\hooks`. That directory does not
   exist. Verified by `ls`. Git runs no hook and reports no error. So the pre-commit
   verdict check never fires either.
3. `AGENTS.md` is 99 lines and mixes permanent rules with a dated campaign, a dated model
   roster and dated provider numbers.

So today's rules are prose with nothing behind them. That is the single biggest change
this plan makes: every rule below either has a named enforcer that is proven to fire, or
is tagged `discipline-only, unenforceable`.

## The steps, in order

Each step says what to create and why it exists. Do them in this order. Later steps
assume earlier ones.

### Step 1 — Prove an enforcer can fire before writing any rules

Create `scripts/check_hook_liveness.py`. It checks three things and exits non-zero on any
failure: the hooks block in `.claude/settings.json` is non-empty, every hook path named
there exists on disk, and `git config core.hooksPath` resolves to a directory inside this
repository.

Then wire the hooks and run one deliberate violation to watch each hook block it. Record
the observed block message in `operations/units/<unit>/evidence/hook_liveness.txt`.

Why: everything else in this plan assumes hooks fire. Right now none do. Seeing the file
exist is not proof. Seeing it block a real action is proof.

Fix the stale path first:

```
git config core.hooksPath githooks
```

### Step 2 — Create the control repository

Create `agent_control/` as its own git repository, outside this repo's history, owned by
the operator. The agent has read access and no commit key.

It holds `constitution.md`, `halt_conditions.md`, `communication_standard.md`,
`model_lock.json`, and a `policy/` directory containing `naming_terms.txt`,
`root_allowlist.txt` and `canonical_pins.json`.

Why: the agent must not be able to weaken its own gates. If the naming rules and the pin
list live in the repo the agent commits to, the agent can edit them. Credit: proposal A.

### Step 3 — Write the policy files the gates read

Create `agent_control/policy/naming_terms.txt`, `root_allowlist.txt`, and
`canonical_pins.json`. Contents are specified in `02_naming_and_layout.md`.

Why: the gate scripts must read policy from a path the agent cannot write. Hard-coding
the banned list inside the script puts it back under agent control.

### Step 4 — Install the naming and placement gates

Create `scripts/check_naming.py` and `scripts/check_placement.py`. Full source is in
`02_naming_and_layout.md`. Wire both into `githooks/pre-commit` and into CI.

Why: a casual name cannot be renamed later at scale. The current 210-item rename backlog
exists because nothing blocked the first one.

### Step 5 — Measure every existing bad name, do not estimate

Run `python scripts/check_naming.py --scope repository --write-inventory`. It writes
every currently non-conforming path with its blob hash to
`agent_control/policy/name_migration_inventory.txt`.

The gate then allows a listed path to stay, and rejects any new one. The inventory may
shrink and may never grow. Any file you touch for another reason must be renamed in that
same change.

Why: 210 renames cannot block all other work, and a hard freeze would stall the project.
A shrink-only inventory converges without stopping anything. Credit: proposal B.

Measure it. Do not write a number you did not compute. The migration that was scoped at
"~923 config keys" and measured at 1,644 is what this rule is for.

### Step 6 — Create the directory skeleton and the single scratch location

Create the canonical tree in `02_naming_and_layout.md`. Create `scratch/` and put exactly
`/scratch/` in `.gitignore`. On the VM, bind-mount `scratch/` at `/tmp` so tools that
write to the system temp directory land in the one governed place.

Why: one governed location, and the write fence in Step 7 blocks creation anywhere else.

### Step 7 — Install the write fence and the janitor

Add the write-fence check to the pre-tool hook: file creation is allowed only under the
repository tree or the current scratch session directory.

Install the janitor as a root-owned systemd timer on the VM, and a SYSTEM-owned Scheduled
Task on Windows. It resets permissions and then deletes, and it runs daily.

Why: about 230 junk folders and 23,105 files accumulated at the working root, some with
permissions so restrictive that removing them needed elevated takeown. A janitor running
as the same user would be blocked by the same permissions. Root or SYSTEM ownership is
what defeats that. Credit: proposal A.

### Step 8 — Install the agent payload schema and validator

Create `governance/schemas/agent_response.schema.json` and
`scripts/validate_agent_payload.py`. Full schema in `04_agent_contract.md`.

Why: this is the anti-toothpaste enforcer. A reply missing its gap list, or missing
evidence on a finding, is rejected by the validator before a human reads it.

### Step 9 — Install the fan-out harness with the canary and the kill switch

Create `scripts/fan_out.py` with the canary rule and the failure-rate kill switch from
`04_agent_contract.md`.

Why: a 72-agent fan-out reached 2 done, 68 failed and about 2.0M tokens before anyone
noticed. A mandatory canary makes a broken harness cost 2 agents.

### Step 10 — Install session state and the resume ritual

Create `state/session/resume_pointer.json` written with `os.replace`, the heartbeat file,
and `scripts/resume.py`. Full ritual in `03_memory_and_session.md`.

Why: a session must resume at the exact next action after a crash, and must never re-run
work that a checkpoint already holds.

### Step 11 — Install the memory tree

Create `operations/memory/observations/`, `candidates/`, `decisions/`, and
`docs/lessons/index.md`.

Why: memory grows across sessions in files on disk, and the boot read stays small.

### Step 12 — Install the CI gates

Add the jobs listed in `05_audit_trail.md` to `.github/workflows/`.

Why: a local hook can be bypassed. CI is the authority. The pre-commit hook is only there
to save a round trip.

### Step 13 — Replace AGENTS.md

Replace the current file with `01_agents_md_draft.md`. Move the campaign section to
`docs/mission.md`. Move the model roster and provider numbers to
`agent_control/model_lock.json`.

Why: rules are permanent, missions are dated, and mixing them makes a reader unable to
tell law from news.

### Step 14 — Dogfood it on one throwaway work unit

Run one small real change end to end through all eleven phases. Confirm every artifact in
`05_audit_trail.md` exists, and that CI blocks the merge when you deliberately delete one
of them.

Why: this is the same rule the design applies to everything else. The effect has to appear
in real output. A design that has never been run is not proven.

## Conflicts between the proposals and what was chosen

Proposal C returned no design. Its entire output was `Monitor armed. Waiting for the
generation to land.` There were two proposals to merge, not three.

| # | Question | Chosen | Why | From |
| --- | --- | --- | --- | --- |
| D1 | Target machine | Linux VM primary, Windows named per step | The dead hooks are on Windows; a Linux-only design would not fire there | new |
| D2 | Where rules live | Operator-owned control repo | An agent that can edit its own gates has no gates | A |
| D3 | State store | JSON written with `os.replace` | A hostile auditor can read JSON and the operator can hear it read aloud; `os.replace` gives the crash safety SQLite was wanted for | A |
| D4 | Tooling shape | Discrete named scripts | B's design routes everything through an `agentctl` binary B did not write; an unwritten dependency is not an enforcer | A |
| D5 | Phase count | 11 named phases | B's 17 carry real content but do not fit one spoken line; A's 10 omitted the negative control and the post-merge proof | A and B |
| D6 | Name grammar | snake_case | `CLAUDE.md` §4.1 already binds snake_case; adopting B's kebab-case would create two competing grammars | project law |
| D7 | Existing bad names | Shrink-only migration inventory | 210 renames cannot block all work, and a freeze would stall everything | B |
| D8 | Regex evasions | CamelCase and ` (1)` suffix included | A's regex misses `FinalReport` and `plan (1).md` | B |
| D9 | Scratch location | `scratch/` inside repo, gitignored, bind-mounted to `/tmp` | The agent's working directory is the repo, so moving scratch outside does not stop root junk; the write fence is what stops it | B and A |
| D10 | Scratch cleanup | Root or SYSTEM owned janitor | The observed permission disaster needed elevated takeown; a same-user janitor would be blocked by the same permissions | A |
| D11 | Test integrity | Negative control required | A had no mechanism against a green suite bought with test cheats | B |
| D12 | Payload contract | JSON Schema with `additionalProperties: false` | A's YAML is easier to read, but only a schema with `minItems: 1` on the gap list can be mechanically rejected | B |
| D13 | Merge authority | Release service is the only merger | Removes the authority instead of promising not to use it | A and B |
| D14 | Plan convergence | 90-minute clock plus a frozen hash | The plan that went v1 to v4 over four hours had no clock; a freeze line is what ends it | A |
| D15 | Scope estimates | A `~N` lint on the plan file | The 923-versus-1,644 failure was a tilde nobody challenged | A |
| D16 | Memory status | Five statuses including `contested` | A binary active/retired cannot hold two contradicting true observations | B |
| D17 | Halt naming | Numbered `H1` to `H14` | The operator is blind; "H6 fired" is one spoken token | A |
| D18 | Fan-out gate | Canary proves 8 harness steps, then kill at 20 percent or 3 in a row | B's canary list is more complete; A's thresholds match the observed 68-of-72 failure | A and B |

## Every named failure and the thing that stops it

| Failure | Enforcer | Kind |
| --- | --- | --- |
| Faithfulness ghost, quality claimed from a count | Schema requires a non-empty evidence quote per finding; review template bans a count as a verdict | Part mechanical, part discipline |
| Lost day, a knob added to move a number | Any new config key must appear in the frozen plan with a design reason; the diff shows new keys | Mechanical |
| Green audit bought with test cheats | Negative control artifact required in `verification/` | Mechanical |
| Built but never wired | `PROVE_LIVE` phase, activation record, hook liveness check | Mechanical |
| Self-grading on a substring | The detector must import zero production modules, checked by import scan | Mechanical |
| Offline tests treated as a preflight | `PROVE_LIVE` cannot be satisfied by an offline artifact | Mechanical |
| Four-hour freeze at a wake | Wakes start read-only, watchdog relaunches, heartbeat under 300s | Mechanical |
| 72-agent fan-out burning budget | Canary plus kill switch inside the harness | Mechanical |
| Plan sprawl from v1 to v4 | 90-minute clock and a `frozen_utc` hash | Mechanical |
| Scope taken from an estimate | `~N` lint on the plan file | Mechanical |
| 230 junk folders at the root | Write fence plus root-owned janitor | Mechanical |
| 48GB of duplicate snapshots | Snapshot script refuses a duplicate content hash; retention cap | Mechanical |
| 210-item rename backlog | Naming regex plus shrink-only inventory | Mechanical |
| Toothpaste findings across iterations | Schema field `first_reply_complete`, and a late finding raises an incident | Mechanical |
| Agent stops itself | Stop hook blocks yielding outside `WRAP`, a halt, or an operator question | Mechanical |
| Fresh re-run destroying a good checkpoint | Resume reads the checkpoint manifest first and kills a fresh relaunch | Mechanical |

## What is discipline-only and cannot be enforced

This list is honest on purpose. Calling a discipline a mechanism is the same
self-deception the faithfulness ghost is made of.

1. Whether the quoted evidence actually supports the claim. A schema can force a quote to
   be present. It cannot read the quote.
2. Whether a line-by-line read really happened, or was a skim.
3. Whether the named root cause is the true root cause.
4. Whether a `did_not_cover` list is complete, rather than merely non-empty.
5. Whether a phase marked not-applicable really was not applicable.
6. Whether an operator-facing sentence is genuinely plain.
7. Whether a new config key that carries a design reason in the plan is honest, or a knob
   dressed in a reason.

For each of these the design does the enforceable half and marks the rest. The reviewer
gate is the only check on this list, which is why the reviewer must be a different model.

## A note on this file set's own names

Under the rule in `02_naming_and_layout.md`, `01_agents_md_draft.md` fails, because
`draft` describes maturity and not content. The operator specified that filename, so it
is written as asked. At adoption it should be renamed to `01_agents_md_content.md` and it
belongs in the migration inventory until then. The rule bites its own author on day one,
which is the correct behaviour.
