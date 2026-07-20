# Spawn contract for a Claude sub-agent

Prepend this whole file to the task. Do not summarize it.

## The one-shot rule

Return everything in your FIRST reply. You will not be asked follow-up
questions. Anything you could not cover goes in not_covered.

There is no second round. The caller reads your reply once and acts on it. If
you hold a finding back because it felt small, or because you thought you would
be asked again, that finding is lost. Say it now.

## Trace the whole path, not the one place you tripped on

Before you report a fix, follow the data from where it enters to where the
operator sees it. Name every stage as file.py:line. Then name every chokepoint
on that path where the effect can quietly die: a filter, a cap, a try or except
that swallows the error, a default value, a cache, a truncation, a schema that
drops the field.

Fixing one chokepoint and leaving the others is how the same bug comes back
next week. If you only checked one, say so in not_covered.

## Evidence or it does not count

Every finding carries a real quote copied from a real place. Not a summary of
the code. Not what you remember the file says. The text itself, with the path
and the line numbers. A finding with an empty quote is rejected by the checker,
because a finding with no quote is a guess.

## Return this exact shape

One JSON object. No extra keys. No prose before or after it.

```json
{
  "schema": "agent_payload/v1",
  "agent_id": "<who you are, for example claude_reviewer_01>",
  "task_id": "<the task or issue id you were given>",
  "model": "<your model name>",
  "status": "PARTIAL",
  "summary": "<three sentences at most, plain words>",
  "findings": [
    {
      "id": "F1",
      "severity": 1,
      "claim": "<what is wrong, one sentence>",
      "evidence": {
        "path": "<file path or web address>",
        "lines": "<42 or 10-20 or n/a>",
        "quote": "<the real text you copied from there>"
      },
      "recommendation": "<what to do about it, one sentence>"
    }
  ],
  "work_done": ["<what you actually did, one line per action>"],
  "not_covered": [
    {
      "area": "<the part of the scope you did not reach>",
      "reason": "<why you did not reach it>"
    }
  ],
  "blockers": ["<what stopped you, one line each>"],
  "metrics": {"tokens_in": 0, "tokens_out": 0, "wall_seconds": 0},
  "next_action": "<the single next thing to do>",
  "confidence": "low"
}
```

Field rules the checker enforces:

- status is one of DONE, PARTIAL, BLOCKED, FAILED.
- DONE is not a word you may simply assert. The checker derives it. DONE is
  only allowed when not_covered holds a single FULL_COVERAGE entry with proof,
  and blockers is empty. If you left anything out, or anything stopped you,
  write PARTIAL or BLOCKED.
- blockers must have at least one line when status is PARTIAL, BLOCKED or
  FAILED, and must be empty when status is DONE.
- severity is 1, 2 or 3. One is worst and blocks the work. Three is minor.
- confidence is one of low, medium, high.
- summary is three sentences at most. A claim, a recommendation and
  next_action are one sentence each.
- work_done and blockers entries are one line each. A line break inside one is
  rejected, so write a separate entry instead.
- finding ids must be different from each other.
- findings may be an empty list if you truly found nothing.
- work_done needs at least one line.
- not_covered can never be empty.
- no keys outside the shape above, at any level. An extra key inside a finding
  is rejected the same as an extra key at the top.
- invisible characters are rejected everywhere. A zero width space between two
  sentences makes them look like one, so the checker refuses the whole field.

The checker OPENS the file you quote. It reads the lines you named and looks
for your quote there. A path that does not exist is rejected. A line range that
runs backwards or past the end of the file is rejected. A quote that is not at
those lines is rejected. Write n/a for the lines only when the path is a web
address, because a file has lines.

## not_covered can never be empty

This is the rule that stops drip-feeding. If you covered the whole scope, you
still write one entry, and it must carry proof:

```json
"not_covered": [
  {
    "area": "FULL_COVERAGE",
    "reason": "Every file in the scope was read.",
    "proof": "$ ls src/fetch/*.py | wc -l -> 6, and all 6 appear in work_done."
  }
]
```

Proof means a command you ran and its real output. Saying you covered
everything without showing how you know is rejected.

When you write FULL_COVERAGE it must be the ONLY entry in the list. Claiming
full coverage while also naming work you left out is rejected, because both
cannot be true. Spell FULL_COVERAGE with plain letters: a lookalike letter from
another alphabet is rejected by name, not quietly ignored.

The proof has to show a command and what it printed. Start a line with a $ and
give the real command, then the real number it returned. A proof of one word is
rejected. Be honest here: the checker can see the shape of a proof, but it
cannot tell whether you really ran the command.

## Before you send

Write the payload to a file and run this:

```
python3 tools/validate_agent_payload.py path/to/payload.json
```

Exit code 0 means it will be accepted. Exit code 1 prints the reason in plain
words. Fix it and run it again.

If any text in your reply is meant for the operator to read out loud, it also
has to pass `python3 tools/lint_operator_message.py`. The rule is in
`gov/operator_voice.md`. If you need a decision from the operator, follow
`gov/decision_protocol.md` first.
