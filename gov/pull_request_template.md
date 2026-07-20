# Pull request

Fill in every section. A reviewer must be able to reconstruct why this change
exists without asking anyone a question.

Check this file before you open the pull request:

```
python3 tools/check_pr_body.py path/to/pr_body.md
```

The checker does not take the body's word for things it can check. It opens the
files named here, so an invented path is rejected by name. An issue number must
be a real number, and zero is not one. A section holding only TBD is rejected.
The rollback section must hold a real command, and the review section must hold
a verdict a reader can find.

## Issue link

<!-- The issue this closes. A real number like #123 or a real address. The word
TBD is rejected, because a change with no issue is a change with no reason. -->

<#123 or the full address of the issue>

## What changed

<!-- What you actually changed, in plain words, one line per change. Name the
files. Do not describe intent, describe the change. -->

<one line per change, naming the file>

## Evidence links

<!-- Proof it works. Test output, a run identifier, an artifact path, a log
path. Paste the real output in a fenced block. A claim with no evidence is not
evidence. -->

<what the evidence shows in one sentence>

```
<the exact command you ran>
<the exact output it printed>
```

## Review verdict

<!-- Who reviewed it and what they said. Name the reviewer and the verdict, and
link the verdict file if there is one. -->

<reviewer name, verdict, and where the verdict is written down>

## Not in scope

<!-- What this change deliberately does not fix, and what you left alone in the
same files. This is the same rule as not_covered in the agent payload. If you
touched one chokepoint on a data path and left the others, name them here. -->

<what this change does not fix>

## Rollback plan

<!-- Exactly how to undo this if it goes wrong in front of the operator. The
command, and anything that has to be undone by hand. -->

<the exact command to undo this, and anything that needs a hand>
