# Issue

Fill in every section. An issue that skips a section is not ready to work on.

This template exists to stop two failures. The first is tunnel view: an agent
fixes the one place it tripped on and never looks at the rest of the path, so
the same bug comes back somewhere else. The second is the guess: a scope stated
from memory instead of counted.

Check this file with the same tool that checks pull request bodies:

```
python3 tools/check_pr_body.py path/to/issue.md --issue
```

The checker opens the files this issue names. A path that does not exist is
rejected. A line number of zero, or one past the end of the file, is rejected.
A trace naming only one place is rejected, because one place is the place you
tripped on, not a path.

## Problem

<!-- What is wrong, in plain words. What does the operator see today, and what
should they see instead. No cause here, only the symptom. -->

<one plain sentence saying what is wrong>

## Measured scope

<!-- Run a command that counts the real size of the problem. Paste the command
and its real output in a fenced block. An estimate is rejected. A guess is
rejected. If you did not run a command, you do not know the scope. -->

<what the count means in one sentence>

```
<the exact command you ran>
<the exact output it printed>
```

## Data path trace

<!-- THIS IS THE ANTI TUNNEL VIEW SECTION. List every stage the data passes
through from the entry point to the thing the operator sees. One line per
stage, with file:line. Then list every chokepoint where the effect can die on
the way: a filter, a cap, a try or except, a default value, a cache, a
truncation, a schema drop. If you only name the one place you tripped on, you
have not traced the path. -->

Stages, in order:

- <file.py:line> <what this stage does to the data>
- <file.py:line> <what this stage does to the data>

Chokepoints where the effect can die:

- <file.py:line> <what would silently kill it here>

## Acceptance criterion

<!-- The observable effect in real output. Not "the test passes". Not "the code
is correct". What will be different in the thing the operator actually looks
at, and how will we see it. -->

<the observable effect, and where to look for it>

## Out of scope

<!-- What this issue will not touch. Anything you decide to leave alone belongs
here, now. This is the same rule as not_covered in the agent payload. -->

<what this issue will not touch>
