# 02 — Naming and file placement

## What a name must do

A name says what a thing is. It never says how mature it is, how good it is, when it was
made, or which attempt it was. Git already records maturity, quality and sequence. A name
that repeats them goes stale the moment the next version lands, and then nobody can tell
which file is the real one.

The grammar is snake_case. This is not a new choice. `CLAUDE.md` §4.1 already binds
snake_case and forbids kebab-case. One of the source proposals suggested kebab-case for
directories; that was rejected because two competing grammars in one repository is itself
the problem this section exists to stop.

Dates and issue numbers are facts, not opinions. `2026_07_19_scratch_permissions.md` and
`i1402_fetch_cache_resume` are fine. `final_plan.md` and `plan_v4.md` are not.

## The banned terms

`agent_control/policy/naming_terms.txt`, one term per line:

```
new
old
latest
current
final
finished
done
complete
real
true
honest
actual
genuine
improved
better
best
enhanced
optimized
advanced
smart
proper
good
great
super
mega
ultra
fixed
patched
hotfix
workaround
temp
tmp
junk
misc
stuff
things
copy
backup
bak
duplicate
wip
draft
quick
revised
updated
redo
working
```

Terms deliberately left out: `clean`, `fast`, `legacy`, `deprecated`. Each has an honest
descriptive or verb use, such as `scratch_clean.py`. A gate that fires on ordinary names
gets switched off, and a switched-off gate is worse than no gate. Precision is chosen over
coverage on purpose.

## The exact patterns

Applied to every segment of every path added or renamed.

```python
BANNED_TOKEN = re.compile(
    r"(?i)(?:^|[_.\-])(?:" + "|".join(terms) + r")(?=[_.\-]|$)"
)

BANNED_VERSION = re.compile(
    r"(?i)(?:^|[_.\-])(?:v|ver|version|rev|revision|iter|iteration|round|attempt|pass)"
    r"\d+(?=[_.\-]|$)"
)

BANNED_COPY_SUFFIX = re.compile(
    r"(?i)(?:\s*\(\d+\)|[_.\-]copy(?:[_.\-]?\d+)?)(?=\.[a-z0-9]+$|$)"
)

BANNED_CAMEL = re.compile(r"[a-z][A-Z]")

SNAKE_SEGMENT = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")
```

`BANNED_CAMEL` and `BANNED_COPY_SUFFIX` come from proposal B. Without them `FinalReport.md`
and `plan (1).md` pass every other check. The Windows file explorer produces the second
form by itself, which is how duplicates arrive without anyone typing them.

Root files written in capitals are allowed by explicit name only: `AGENTS.md`,
`CLAUDE.md`, `README.md`, `LICENSE`.

### These patterns were run, not just written

Run on 2026-07-19 against 36 cases: 21 that must be rejected and 15 that must pass. All 36
came out correct.

Rejected as expected, including the two evasions proposal A's version would have let
through: `honest_sweep_r3.py`, `real_results.json`, `final_plan.md`, `plan_v4.md`,
`fixed_mapper.py`, `temp_fix.py`, `process_v2.py`, `FinalReport.md`, `plan (1).md`,
`report_copy.md`, `new_design.md`, `improved_loop.py`, `backup_state.json`, `wip_notes.md`,
`iter3_verdict.txt`, `best_output.json`, `myFile.py`, `data-set.json`, `plan_rev2.md`,
`things.py`, `misc_utils.py`.

Passed as expected, with no false positives: `fetch_cache_resume.py`, `path_trace.md`,
`2026_07_19_scratch_permissions.md`, `i1402_fetch_cache_resume`, `00_plan.md`,
`0024_governance_cage.md`, `corpus_snapshot.json`, `scratch_clean.py`, `check_naming.py`,
`AGENTS.md`, `README.md`, `tier_classifier.py`, `session_log.md`,
`agent_response.schema.json`, `resume_pointer.json`.

`scratch_clean.py` passing is why `clean` was left out of the banned terms. A gate that
rejects ordinary names gets switched off.

A written regex is not a working regex. Re-run this set whenever the term list changes.

## The canonical tree

```
repo_root/
  AGENTS.md              permanent operating rules
  CLAUDE.md              Claude Code entry point, points at AGENTS.md
  README.md
  .gitignore
  .gitattributes
  pyproject.toml
  requirements.txt
  .github/               CI workflows
  .claude/               hooks and settings
  githooks/              git hooks, referenced by core.hooksPath
  config/                runtime configuration
  docs/                  product documentation
    decisions/           numbered decision records
    lessons/             theme hubs plus index.md
    postmortems/         dated incident write-ups
    mission.md           the only home of the current goal
  governance/            schemas and pin mirror, read-only to the agent at runtime
  operations/
    units/<unit_id>/     one folder per work unit, the audit chain
    memory/              observations, candidates, decisions
    incidents/           incident records
  scripts/               maintained scripts
  src/                   product source
  tests/                 tests
  tools/                 development tools
  state/                 runtime state, gitignored except pins
  journal/               session log, halts
  scratch/               the only disposable location, gitignored
```

`agent_control/` sits outside this tree as its own git repository. The agent reads it and
has no commit key for it.

Nothing else at the root. New root entries need an operator-signed change to
`agent_control/policy/root_allowlist.txt`.

Never in git: run outputs over 5MB, snapshots, secrets, anything under `scratch/`.

## The single scratch location

`scratch/` inside the repository, gitignored with exactly this line:

```
/scratch/
```

On the VM, bind-mount it at `/tmp` and set `TMPDIR` to it, so tools that write to the
system temp directory land in the one governed place. That idea is from proposal B.

Proposal A put scratch outside the repository. Rejected: the agent's working directory is
the repository, so a relative write still lands inside it. Moving scratch out does not
stop junk at the root. The write fence does.

Per-session directory: `scratch/s<utc_compact>/`. Created with permissions inherited from
the parent. The agent never sets restrictive permissions on its own files. That rule
exists because 23,105 files once accumulated with permissions so tight that a non-admin
user could not read them, and removing them needed elevated takeown.

Cleanup is owned by root on Linux and by SYSTEM on Windows, never by the agent's user.
That is the part that matters: a janitor running as the same user would be blocked by the
same permissions the agent created.

Rules: delete session directories older than seven days; if the total exceeds 50GB, delete
oldest first down to 40GB; reset permissions before deleting; write one line per deletion
to `scratch/janitor_log.txt`.

No wake sequence starts with a delete.

## Archive discipline

Snapshots exist only through `scripts/make_snapshot.py --subject <name>`, which writes to
`archive/<subject>/<yyyy_mm_dd>_<hash8>/` with a manifest of file names and hashes. The
script refuses to write a snapshot whose content hash equals the newest existing one. That
single refusal is what stops 48GB of duplicates. Retention: three per subject, 100GB
total, oldest first.

## The enforcement chain

Four layers, in the order they fire.

1. The write-fence hook blocks file creation outside the repository tree and the current
   scratch session directory, at tool-call time. Junk cannot be born.
2. `githooks/pre-commit` runs the naming and placement checks on staged additions.
3. CI re-runs both across the whole repository. A local hook can be bypassed, so CI is the
   authority and the hook is only a time saver.
4. `scripts/check_hook_liveness.py` proves layers 1 and 2 are actually wired.

The scripts are pinned in `agent_control/policy/canonical_pins.json`. Editing a gate to
weaken it changes its hash and trips `H1` at the next boot.

## scripts/check_naming.py

```python
#!/usr/bin/env python3
"""Reject path names that describe maturity, quality or version instead of content.

Scopes:
  --scope staged      names added or renamed in the current commit (pre-commit default)
  --scope repository  every tracked path (CI)

A path already listed in the migration inventory is allowed to stay, but may never be
added. The inventory may shrink and may never grow.
"""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTROL = Path(os.environ.get("AGENT_CONTROL", REPO.parent / "agent_control"))
POLICY = CONTROL / "policy"
TERMS_FILE = POLICY / "naming_terms.txt"
INVENTORY_FILE = POLICY / "name_migration_inventory.txt"

CAPITAL_ROOT_FILES = {"AGENTS.md", "CLAUDE.md", "README.md", "LICENSE"}

BANNED_VERSION = re.compile(
    r"(?i)(?:^|[_.\-])(?:v|ver|version|rev|revision|iter|iteration|round|attempt|pass)"
    r"\d+(?=[_.\-]|$)"
)
BANNED_COPY_SUFFIX = re.compile(
    r"(?i)(?:\s*\(\d+\)|[_.\-]copy(?:[_.\-]?\d+)?)(?=\.[a-z0-9]+$|$)"
)
BANNED_CAMEL = re.compile(r"[a-z][A-Z]")
SNAKE_SEGMENT = re.compile(r"^[a-z0-9]+(?:_[a-z0-9]+)*$")


def load_terms() -> list[str]:
    if not TERMS_FILE.exists():
        sys.exit(f"FAIL: policy file missing: {TERMS_FILE}")
    terms = [
        line.strip()
        for line in TERMS_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    if not terms:
        sys.exit(f"FAIL: policy file empty: {TERMS_FILE}")
    return terms


def banned_token(terms: list[str]) -> re.Pattern[str]:
    joined = "|".join(re.escape(t) for t in terms)
    return re.compile(rf"(?i)(?:^|[_.\-])(?:{joined})(?=[_.\-]|$)")


def load_inventory() -> set[str]:
    if not INVENTORY_FILE.exists():
        return set()
    out = set()
    for line in INVENTORY_FILE.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out.add(line.split()[0])
    return out


def git(*args: str) -> list[str]:
    result = subprocess.run(
        ["git", *args], cwd=REPO, capture_output=True, text=True, check=True
    )
    return [line for line in result.stdout.splitlines() if line.strip()]


def paths_for(scope: str) -> list[str]:
    if scope == "staged":
        return git("diff", "--cached", "--name-only", "--diff-filter=AR")
    return git("ls-files")


def violations(path: str, token_re: re.Pattern[str]) -> list[str]:
    found: list[str] = []
    parts = path.split("/")
    for index, segment in enumerate(parts):
        is_leaf = index == len(parts) - 1
        if is_leaf and len(parts) == 1 and segment in CAPITAL_ROOT_FILES:
            continue
        if BANNED_CAMEL.search(segment):
            found.append(f"{segment}: mixed case, use snake_case")
        if BANNED_COPY_SUFFIX.search(segment):
            found.append(f"{segment}: copy suffix")
        if BANNED_VERSION.search(segment):
            found.append(f"{segment}: version or attempt number in the name")
        if token_re.search(segment):
            found.append(f"{segment}: name states maturity or quality, not content")
        stem = segment.split(".")[0] if is_leaf else segment
        if stem and not SNAKE_SEGMENT.match(stem):
            found.append(f"{segment}: not snake_case")
    return found


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--scope", choices=("staged", "repository"), default="staged")
    parser.add_argument("--write-inventory", action="store_true")
    args = parser.parse_args()

    token_re = banned_token(load_terms())
    inventory = load_inventory()
    paths = paths_for(args.scope)

    if args.write_inventory:
        bad = [p for p in git("ls-files") if violations(p, token_re)]
        INVENTORY_FILE.parent.mkdir(parents=True, exist_ok=True)
        INVENTORY_FILE.write_text(
            "# paths that predate the naming rule. This list may shrink, never grow.\n"
            + "\n".join(sorted(bad))
            + "\n",
            encoding="utf-8",
        )
        print(f"measured {len(bad)} non-conforming paths -> {INVENTORY_FILE}")
        return 0

    failures: list[str] = []
    for path in paths:
        if path in inventory:
            continue
        for problem in violations(path, token_re):
            failures.append(f"{path}  ->  {problem}")

    if failures:
        print("FAIL: naming rule. A name says what a thing is.")
        for line in failures:
            print("  " + line)
        print(f"\nPolicy: {TERMS_FILE}")
        return 1

    print(f"naming ok: {len(paths)} paths checked, scope={args.scope}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## scripts/check_placement.py

```python
#!/usr/bin/env python3
"""Reject anything at the repository root that is not on the signed allowlist."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
CONTROL = Path(os.environ.get("AGENT_CONTROL", REPO.parent / "agent_control"))
ALLOWLIST_FILE = CONTROL / "policy" / "root_allowlist.txt"
MAX_TRACKED_BYTES = 5 * 1024 * 1024


def load_allowlist() -> set[str]:
    if not ALLOWLIST_FILE.exists():
        sys.exit(f"FAIL: policy file missing: {ALLOWLIST_FILE}")
    return {
        line.strip().rstrip("/")
        for line in ALLOWLIST_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    }


def main() -> int:
    allowed = load_allowlist()
    tracked = subprocess.run(
        ["git", "ls-files"], cwd=REPO, capture_output=True, text=True, check=True
    ).stdout.splitlines()

    failures: list[str] = []
    for path in tracked:
        top = path.split("/")[0]
        if top not in allowed:
            failures.append(f"{path}  ->  '{top}' is not on the root allowlist")
        if path.startswith("scratch/"):
            failures.append(f"{path}  ->  scratch must never be tracked")
        full = REPO / path
        if full.is_file() and full.stat().st_size > MAX_TRACKED_BYTES:
            size = full.stat().st_size // (1024 * 1024)
            failures.append(f"{path}  ->  tracked file is {size}MB, cap is 5MB")

    if failures:
        print("FAIL: placement rule.")
        for line in failures:
            print("  " + line)
        print(f"\nPolicy: {ALLOWLIST_FILE}")
        return 1

    print(f"placement ok: {len(tracked)} tracked paths")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

## scripts/check_hook_liveness.py

This is the script the current repository would fail today, on both checks.

```python
#!/usr/bin/env python3
"""Prove the enforcement layer is wired. A rule with a dead enforcer is not a rule.

Failure here is halt condition H13.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SETTINGS = REPO / ".claude" / "settings.json"


def main() -> int:
    problems: list[str] = []

    if not SETTINGS.exists():
        problems.append(f"{SETTINGS} does not exist")
    else:
        settings = json.loads(SETTINGS.read_text(encoding="utf-8"))
        hooks = settings.get("hooks") or {}
        if not hooks:
            problems.append(
                f"{SETTINGS} has an empty hooks block: the hook files are never called"
            )
        for event, entries in hooks.items():
            for entry in entries:
                for hook in entry.get("hooks", []):
                    command = hook.get("command", "")
                    for token in command.split():
                        if token.endswith(".py"):
                            target = (REPO / token.strip("'\"")).resolve()
                            if not target.exists():
                                problems.append(
                                    f"{event}: command points at missing file {target}"
                                )

    result = subprocess.run(
        ["git", "config", "core.hooksPath"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    configured = result.stdout.strip()
    if not configured:
        problems.append("git core.hooksPath is unset: no git hook runs")
    else:
        hooks_dir = Path(configured)
        if not hooks_dir.is_absolute():
            hooks_dir = REPO / hooks_dir
        if not hooks_dir.exists():
            problems.append(
                f"git core.hooksPath points at {hooks_dir}, which does not exist. "
                "Git runs no hook and reports no error."
            )
        else:
            try:
                hooks_dir.resolve().relative_to(REPO.resolve())
            except ValueError:
                problems.append(
                    f"git core.hooksPath points outside the repository: {hooks_dir}"
                )
            if not (hooks_dir / "pre-commit").exists():
                problems.append(f"no pre-commit hook in {hooks_dir}")

    if problems:
        print("FAIL H13: the enforcement layer is not wired.")
        for line in problems:
            print("  " + line)
        return 1

    print("hook liveness ok: claude hooks registered, git hooks path inside repo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

Wiring alone is not proof. After wiring, commit a deliberately bad name once and record
the block message in `evidence/hook_liveness.txt`. Seeing the file exist is not proof.
Seeing it block is proof.

## githooks/pre-commit

```sh
#!/bin/sh
# Enforcement runs before the commit exists. CI repeats all of it.
set -e

python scripts/check_hook_liveness.py
python scripts/check_naming.py --scope staged
python scripts/check_placement.py
python scripts/check_plan_lint.py --scope staged
python scripts/check_artifact_chain.py --scope staged
```

Install with:

```
git config core.hooksPath githooks
chmod +x githooks/pre-commit
```

On Windows, `chmod` is not needed; git runs the script through its bundled shell.

## The janitor

Linux, `/etc/systemd/system/scratch_janitor.timer`, running as root:

```ini
[Unit]
Description=Clean the agent scratch directory

[Timer]
OnCalendar=daily
OnBootSec=5min
Persistent=true

[Install]
WantedBy=timers.target
```

```sh
#!/bin/sh
# scratch_janitor.sh — runs as root so agent-set permissions cannot block deletion.
set -e
SCRATCH="/srv/agent/repo/scratch"
LOG="$SCRATCH/janitor_log.txt"

find "$SCRATCH" -mindepth 1 -maxdepth 1 -type d -mtime +7 -print | while read -r dir; do
  chmod -R u+rwX "$dir" 2>/dev/null || true
  rm -rf "$dir"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) deleted age $dir" >> "$LOG"
done

while [ "$(du -sb "$SCRATCH" | cut -f1)" -gt 53687091200 ]; do
  oldest=$(find "$SCRATCH" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' \
    | sort -n | head -1 | cut -d' ' -f2-)
  [ -z "$oldest" ] && break
  chmod -R u+rwX "$oldest" 2>/dev/null || true
  rm -rf "$oldest"
  echo "$(date -u +%Y-%m-%dT%H:%M:%SZ) deleted size $oldest" >> "$LOG"
done
```

Windows, registered once as SYSTEM:

```powershell
$action = New-ScheduledTaskAction -Execute "powershell.exe" `
  -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\Deep Cove Research\scripts\scratch_janitor.ps1"'
$trigger = New-ScheduledTaskTrigger -Daily -At 4am
Register-ScheduledTask -TaskName "agent_scratch_janitor" -Action $action `
  -Trigger $trigger -User "SYSTEM" -RunLevel Highest
```

The PowerShell janitor resets permissions with `icacls <dir> /reset /T /C /Q` before
`Remove-Item -Recurse -Force`. That order is what handles the permission problem seen in
this repository.

## agent_control/policy/root_allowlist.txt

```
AGENTS.md
CLAUDE.md
README.md
LICENSE
.gitignore
.gitattributes
pyproject.toml
requirements.txt
.github
.claude
githooks
config
docs
governance
operations
scripts
src
tests
tools
state
journal
scratch
```
