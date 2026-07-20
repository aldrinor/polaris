# 05 — The audit trail

## The standard

Given only this repository at its current commit, an external reviewer who distrusts us
can take any change, see why it was made, see what was measured, see what was reviewed,
and reproduce the proof with one documented command, without asking anybody a question.

If any link in that chain needs a person's memory, the chain is broken. The job of CI is
to make a broken chain unmergeable, so the chain cannot quietly rot between audits.

The reviewer is assumed hostile. That means the record must answer the sceptical question,
not the friendly one. Not "did a test pass" but "does that test prove anything".

## One folder per work unit

```
operations/units/i1402_fetch_cache_resume/
  mission.md                  the issue link, required effect, scope, out of scope,
                              acceptance, safety locks
  scope.json                  the measured surface, with the command that measured it
  path_trace.md               every hop from input to user-visible output, and every
                              chokepoint found, not only the one that was tripped on
  plan.md                     exact changes, allowed files, forbidden files, rollback,
                              score-safety list, activation step, known exclusions
  plan_lock.json              sha256 of plan.md plus frozen_utc
  characterization.md         what the failing test proves and what it does not
  evidence/
    issue_record.json
    hook_liveness.txt         the observed block message from each enforcer
    baseline/                 real output before the change
    change_diff.patch
    smoke/                    the seconds-long offline smoke
    after/                    real output after the change, effect visible
    post_merge/               the same proof re-run from the merged commit
    command_ledger.jsonl      every command run, with exit code and timestamp
    environment_lock.json     everything needed to reproduce
  reviews/
    diagnosis/                the read-only investigator payload
    plan/                     review of the plan
    change/                   review of the diff, iteration per file
  verification/
    focused_tests.json
    negative_control.json     the test run with the production change removed
    live_preflight.json       the small real run
    independent_detector.json the detector that imports zero production code
    semantic_reading.jsonl    one line per output item read, with its verdict
    score_safety.json         metrics that must not move, before and after
  release/
    pull_request_record.json
    merge_record.json
    activation_record.json
    rollback_record.json
    post_merge_proof.json
  proof.md                    the reproduce command and the quoted output lines
  gaps.md                     what was not covered. "Nothing" must be argued
  summary.md
```

## The chain, link by link

A change is auditable when all twenty of these exist and verify. CI job
`artifact_chain` checks presence and non-emptiness for any pull request touching `src/`.

1. The issue, created before the branch.
2. The mission, with acceptance criteria written before the work.
3. The measured surface, with the command that measured it.
4. The path trace, listing every chokepoint.
5. The failure reproduced before any edit.
6. The characterization test, failing on unchanged code.
7. The read-only diagnosis, from a different model.
8. The plan, with its freeze hash and time.
9. The exact diff.
10. Focused test results.
11. The negative control result.
12. The independent review payload.
13. The written verdict, parsed from the last `verdict:` line.
14. The live preflight on the real path.
15. The independent detector result.
16. The semantic reading of the output.
17. The score-safety table.
18. The merge record, made by the release service.
19. The activation record.
20. The post-merge proof from the merged commit.

Plus the rollback record and the gap list. A missing link blocks closure.

## Test integrity: why a passing test is not evidence

A green suite once passed fifty-two of fifty-two checks, bought with four workarounds that
each hid a real bug. So a passing test on its own proves nothing, and the audit record has
to show the things that make it mean something.

`verification/negative_control.json` is the key artifact. It records the test run with the
production change removed. The test must fail. If it passes without the fix, it was never
testing the fix.

This is the single strongest idea taken from proposal B. Proposal A had a
characterization-test-first rule, which catches a test written after the fact, but nothing
that catches a test which passes for the wrong reason.

The record must also show:

- The test failed before the change and passed after.
- The real entry point ran.
- Required components were not mocked away.
- No assertion was weakened in the same change.
- No skip or expected-failure marker was added.
- The actual output was examined, not only the exit code.
- The detector imports zero production modules.

That last one is checked mechanically by scanning the detector's imports. Production code
and its test can share the same blind predicate and both pass. A forensic script with no
production imports once found about eighty-five instances of a problem that the shared
predicate reported as zero.

## Proving the effect appears, not that the code exists

`proof.md` holds the exact command to reproduce and the quoted output lines showing the
effect. Not a description of the effect. The lines.

CI job `evidence_gate` fails if `proof.md` has no `reproduce:` line, or if
`evidence/after/` is empty.

Acceptance is the effect appearing in real output, failing loud otherwise. Not "the
reviewer approved the diff". Not "tests green". A module can be built, imported in a test,
shown green, and never called by the live path. A default-off flag looks exactly like a
working feature in code review.

So any change that introduces a flag must either turn it on in `release/activation_record.json`
or link a follow-up issue that will. CI job `activation_gate` fails a merge that adds a
new default-off flag with neither.

## Score safety

`verification/score_safety.json` lists the metrics that must not move, with their values
before and after, and a written explanation for anything that did move.

This exists because of a campaign where caps and thinners were bolted on to force a
breadth number upward, while the correct design sat approved from six days earlier. Each
knob was locally plausible and globally a regression.

Two mechanical checks help. Any new configuration key in the diff must appear in the
frozen plan with a design reason. And the review brief carries the standing question: does
any added knob exist to make a number move? If yes, the knob is the finding.

Whether a stated design reason is honest or is a knob wearing a reason is discipline-only.
The reviewer being a different model is the only check on it.

## Reproducibility

`evidence/environment_lock.json` records the source commit, container image digest,
dependency lock hashes, interpreter version, GPU model and driver, the model lock hash,
the configuration hash, feature flag states, input artifact hashes, cache schema and keys,
and the API evidence hash for every provider limit relied on. Secret names, never secret
values.

The auditor runs two commands. Replay uses the captured inputs. Live checks the present
external system. The report says which is which, because a replay pass and a live pass
mean different things and conflating them hides a provider that changed under us.

## Authority, removed rather than promised

The builder account cannot merge, cannot bypass a required check, cannot change branch
protection, cannot edit a stored verdict, cannot edit `agent_control/`, and cannot delete
evidence.

Only the release service merges, and only when the machine-readable gate passes. The
release service cannot write code.

This is structural on purpose. A promise not to merge was made and then broken, in a
failure that produced twenty-eight unwanted commits. Removing the authority worked; the
promise did not.

Investigators and reviewers get a read-only mount. An investigator with write access
expands into token-heavy exploration instead of cheap read-only diagnosis; two fan-outs
that fused investigation and building burned about 2.3 million tokens and produced
nothing.

## The CI gates

| Job | Fails when |
| --- | --- |
| `hook_liveness` | hooks unwired, or `core.hooksPath` outside the repo |
| `naming_gate` | a new path breaks the naming rule, or the migration inventory grew |
| `placement_gate` | an unknown root entry, tracked scratch, or a tracked file over 5MB |
| `governance_budget` | `AGENTS.md` over 200 lines or `constitution.md` over 250 |
| `plan_lint` | a `~` followed by a digit in `plan.md` without a stated reason |
| `plan_lock` | `plan.md` changed after `frozen_utc` with no recorded invalidation |
| `artifact_chain` | any required artifact missing or empty on a `src/` change |
| `evidence_gate` | `proof.md` has no reproduce command, or `after/` is empty |
| `negative_control` | the negative control artifact is missing or records a pass |
| `detector_purity` | the independent detector imports a production module |
| `activation_gate` | a new default-off flag with no activation record and no follow-up |
| `verdict_gate` | the last `verdict:` line is missing, malformed, or not APPROVE |
| `diff_match` | `change_diff.patch` does not match the pull request diff |
| `rule_has_enforcer` | a new standing rule with no enforcer and no honest tag |
| `post_merge_proof` | the post-merge re-run digest was not committed |

Pre-commit runs a subset for speed. CI is the authority, because a local hook can be
bypassed and the structure must not depend on anybody's discipline.

## Cross-links, so the chain can be walked both ways

Every commit message carries the trailer `Unit: i1402_fetch_cache_resume`. The pull
request body links the issue and lists the artifact paths. Journal entries name the unit.
Halts are tracked files in `journal/halts/`, because a halt is an audit event and hiding
it would be the most interesting thing to hide.

Any sentence in the journal claiming something was fixed or done carries an `evidence:`
path. The wrap checklist enforces it and the folder layout makes it cheap to satisfy.

## What this chain cannot prove

Stated plainly, because an audit trail that claims completeness it does not have is worse
than a modest one.

1. That the quoted evidence supports the claim it is attached to. Presence is mechanical,
   meaning is not.
2. That the semantic reading was a real read rather than a skim.
3. That the gap list is complete rather than merely non-empty.
4. That the named root cause is the true root cause.
5. That a phase marked not applicable really was.
6. That a design reason attached to a new knob is honest.

For every one of these the only check is a reviewer on a different model reading the
actual evidence. That is why review independence is a structural rule and not a
preference.
