# 04 — The agent communication contract

## The rule

Every agent returns everything it found in its first reply, in one payload, written to a
file. Including what it did not cover.

Asking an agent "anything else?" is banned. If the first reply is incomplete, the run is
marked failed. Findings are not accepted in instalments.

This exists because review findings historically arrived spread across iterations. That
inflates the iteration count, hides whether the review is converging, and lets a serious
finding sit unspoken while cheap ones are traded. A twenty-one iteration review once
produced about thirty real bugs at a cycle time that could not ship.

## The envelope

Every agent reply is written to
`operations/units/<unit_id>/agents/<agent_run_id>.txt` in exactly this shape:

```
---agent_payload---
{ one JSON object that validates against agent_response.schema.json }
---end_agent_payload---
verdict: APPROVE
```

The `verdict:` line is the last non-blank line of the file.

The lead reads the verdict from the file. Never from the agent's own spoken summary. In a
past review the task narrative said the gate was clean and the issue closed, while the
written verdict file said changes were requested. Self-reported verdicts drift toward
completion.

Allowed verdicts: `APPROVE`, `REQUEST_CHANGES`, `HALT`, `NOT_APPLICABLE`. A missing or
malformed verdict fails closed.

## governance/schemas/agent_response.schema.json

```json
{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "agent_response",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version", "unit_id", "agent_run_id", "role", "model",
    "task_given", "status", "coverage", "findings",
    "what_i_did_not_cover", "first_reply_complete",
    "tool_calls_made", "tokens_spent", "duration_seconds"
  ],
  "properties": {
    "schema_version": { "const": "1" },
    "unit_id": { "type": "string", "minLength": 1 },
    "agent_run_id": { "type": "string", "minLength": 1 },
    "role": {
      "enum": ["investigator", "builder", "reviewer", "detector", "monitor", "release"]
    },
    "model": {
      "type": "object",
      "additionalProperties": false,
      "required": ["provider", "model_id", "training_family", "lock_entry_sha256"],
      "properties": {
        "provider": { "type": "string", "minLength": 1 },
        "model_id": { "type": "string", "minLength": 1 },
        "training_family": { "type": "string", "minLength": 1 },
        "lock_entry_sha256": { "type": "string", "pattern": "^[a-f0-9]{64}$" }
      }
    },
    "task_given": { "type": "string", "minLength": 1 },
    "status": { "enum": ["complete", "partial", "blocked", "failed"] },
    "coverage": {
      "type": "object",
      "additionalProperties": false,
      "required": ["requested_items", "inputs_consumed", "commands_run", "excluded_items"],
      "properties": {
        "requested_items": { "type": "array", "items": { "type": "string" } },
        "inputs_consumed": {
          "type": "array",
          "minItems": 1,
          "items": {
            "type": "object",
            "additionalProperties": false,
            "required": ["path", "sha256"],
            "properties": {
              "path": { "type": "string" },
              "sha256": { "type": "string", "pattern": "^[a-f0-9]{64}$" },
              "range": { "type": "string" }
            }
          }
        },
        "commands_run": { "type": "array", "items": { "type": "string" } },
        "excluded_items": { "type": "array", "items": { "type": "string" } }
      }
    },
    "findings": {
      "type": "array",
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "finding_id", "severity", "basis", "claim",
          "evidence", "impact", "suggested_action", "affected_paths"
        ],
        "properties": {
          "finding_id": { "type": "string", "pattern": "^F[0-9]+$" },
          "severity": { "enum": ["blocker", "major", "minor", "cosmetic"] },
          "basis": { "enum": ["observed", "inferred"] },
          "claim": { "type": "string", "minLength": 1 },
          "evidence": {
            "type": "array",
            "minItems": 1,
            "items": {
              "type": "object",
              "additionalProperties": false,
              "required": ["path", "location", "quote"],
              "properties": {
                "path": { "type": "string", "minLength": 1 },
                "location": { "type": "string", "minLength": 1 },
                "quote": { "type": "string", "minLength": 1 }
              }
            }
          },
          "impact": { "type": "string", "minLength": 1 },
          "suggested_action": { "type": "string", "minLength": 1 },
          "affected_paths": { "type": "array", "items": { "type": "string" } },
          "late_finding": { "type": "boolean" }
        }
      }
    },
    "what_i_did_not_cover": {
      "type": "array",
      "minItems": 1,
      "items": { "type": "string", "minLength": 1 }
    },
    "first_reply_complete": { "const": true },
    "tool_calls_made": { "type": "integer", "minimum": 0 },
    "tokens_spent": { "type": "integer", "minimum": 0 },
    "duration_seconds": { "type": "number", "minimum": 0 },
    "artifacts_written": { "type": "array", "items": { "type": "string" } }
  }
}
```

### The three fields that do the work

`what_i_did_not_cover` has `minItems: 1`. It cannot be omitted and it cannot be empty. If
there is genuinely no gap, the array holds the single string:

```
"No known gap within the assigned task."
```

The lead then checks that claim against `coverage`. Forcing the sentence to be written
makes an unexamined claim visible. This preserves the honest gap list that already works
in this project.

`evidence` has `minItems: 1` and every item needs a `quote`. A finding with no quoted
source text is rejected by the validator before a human reads it. This is the enforceable
half of the rule against judging by counts.

`first_reply_complete` is `const: true`. The agent must assert it. It is not proof, but it
puts the claim in the record, so a later drip-fed finding is a contradiction of something
written down rather than a difference of memory.

### Severity words, not numbers

`blocker`, `major`, `minor`, `cosmetic`. Not P0 to P3. The operator is blind and reads by
ear; "blocker" carries its meaning when read aloud and "P1" does not.

## Iteration rules

Five iterations maximum per review. Every brief opens with this, word for word:

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- If a finding isn't a real solid blocker, classify it minor or cosmetic; reserve
  blocker and major for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-approved on remaining
  non-blocking findings; do not bank issues for iter 6.
- If you detect "I'm holding back a blocker to surface next round" — DON'T. Surface it
  now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE if and only if zero blockers and zero majors remain.
```

From iteration two onward a reviewer may only do two things: update an earlier finding by
its identifier, or raise a finding caused by the fixes made since. A new finding against
unchanged material must carry `late_finding: true`. The validator refuses a new
identifier at iteration two or later without that flag, and a late finding opens an
incident in `operations/incidents/` against the review process.

So drip-feeding is still possible, and it now leaves a permanent mark in the audit chain
instead of hiding inside the iteration count.

Hand the reviewer the call-site scan from the `SURVEY` phase. A reviewer that verifies
rather than discovers converges in one or two iterations instead of five.

## What the lead checks

`python scripts/validate_agent_payload.py <file> --surface <measured_surface.json>`

Mechanical rejections:

- The payload does not parse, or fails the schema.
- `what_i_did_not_cover` is missing or empty.
- Any finding has no evidence, or evidence with no quote.
- `inputs_consumed` is empty.
- An assigned path in the measured surface does not appear in `inputs_consumed`.
- The reviewer's `training_family` equals the builder's, or is unknown.
- `model` does not match `agent_control/model_lock.json`.
- The verdict line is missing or is not the last non-blank line.
- A new finding identifier appears at iteration two or later without `late_finding`.

A rejected payload gets exactly one retry, with the specific defect named. A second
rejection marks the run failed.

Then the lead reads every finding and its quoted evidence. That read is discipline-only
and unenforceable. The schema can force a quote to be present. It cannot tell whether the
quote supports the claim. Naming that seam honestly is the point; a validator that
"checked the findings" would be the same mechanical self-deception the faithfulness ghost
is made of.

## Fan-out: the canary and the kill switch

A 72-agent fan-out once reached two done, sixty-eight failed and about two million tokens
before anyone noticed. It looked like slow progress. It was a broken harness.

These rules live in `scripts/fan_out.py`, in code, not in a document.

**1. The canary is mandatory.** Any fan-out of more than three agents launches exactly two
canaries first, and nothing else until they return. The canary must prove all eight of
these, because a harness can fail at any one of them:

1. The prompt reached the agent.
2. The model matched the lock.
3. The payload file was written where expected.
4. The payload parses.
5. It passes the schema.
6. It passes coverage validation.
7. The verdict line parses.
8. The lead can open one cited evidence item and read it.

Step eight matters. A payload that parses is not a payload that says anything. No canary
pass means no fleet. A broken harness then costs two agents.

**2. Failure-rate kill switch.** The harness counts launched, complete and failed. It
kills all remaining agents, by task or process id, when failures reach twenty percent of
launched, or three fail in a row. That fires `H7`.

At the observed rate, sixty-eight of seventy-two, this trips within the first wave.

**3. Liveness deadline.** Each agent must write its payload within twice its declared
expected duration. Overdue is presumed dead, killed, and counted as failed.

**4. Budget fence.** Per-agent and per-fleet token and wall-clock budgets are declared in
the frozen plan. The harness enforces them. A breach fires `H8`.

**5. Wave size at most eight** after the canaries, so the kill switch always has time to
act before a large batch is committed.

**6. Concurrency limit.** Four agent processes at once by default, and one heavy reviewer
process. Inventory processes before and after every wave, and kill orphans by process id
only. A name-wide kill would hit the operator's other sessions.

## Killing a hung agent

An agent is hung only when all of these are frozen past the provider timeout: the raw
model input-output directory modification time, the agent log modification time, and the
phase state. Process state and wait channel corroborate.

A large reasoning call can run about nine minutes with a silent log and then return
normally. Killing on log silence alone destroys good work.

Kill by recorded process id and start time. Never by name.

## Talking to the operator during a fan-out

At launch, one line:

```
Started 8 survey agents. Two canaries passed first. I will report when they finish.
```

At completion, plain numbers and the actual finding:

```
Survey done. 8 launched. 7 complete. 1 failed and was retried once.
Top finding: the config surface is 1,644 keys, not the 923 in the plan.
Next action: split the work unit, the measured surface exceeds the frozen plan.
```

Counts describe process inventory. They never describe quality. The finding itself is read
in plain English, not summarised as a score.
