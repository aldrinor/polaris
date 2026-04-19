# POLARIS full-audit pass 6 — non-gating follow-ups review

You are doing a lightweight final-verification audit before POLARIS
runs the 8-query full sweep. Pass 5 declared CONDITIONAL with one
gating medium (M-5 PT12 false positive) and three non-gating
follow-ups (M-3, M-4, M-2). A fourth non-gating item (M-6) was
surfaced during pass 5 for PT13 title/question exemption.

All 4 non-gating items were addressed in commit `3921bc0`. This is
your sanity check that:

1. They don't break anything
2. They don't create new silent-failure modes
3. They don't regress the M-1 / M-2 / M-5 fixes validated in earlier passes

## Commits since pass 5

- `5cf6959` — M-5 PT12 fix (gating from pass 5, already blessed)
- `4e056a8` — docs sync
- `3921bc0` — **M-3 / M-4 / M-6 / M-2-docs bundle** (this commit under review)

## Your mandate

### 1. M-6 PT13 title + question-inherited exemption

Read `src/polaris_graph/evaluator/external_evaluator.py` lines 370-425
(the PT13 block after the M-5 PT12 fix). Answer:

- Title-line strip: the code does
  `if lines_pt13[0].lstrip().startswith("# ")` then drops line 0.
  Is that the right test for "this is the H1 title"? What if the
  report starts with a blank line or a code fence?
- Question-inherited exemption: the code builds
  `question_superlatives` by regex-matching single-word superlatives
  in `protocol["research_question"]`, then exempts any PT13 hit whose
  matched phrase equals (case-insensitive, stripped) one of those
  words. Is the multi-word case correctly left unexempted? Example:
  question contains "best practices" — should the exemption match
  "best" only, not "best practices"? Verify against the regex.
- Is there an evasion: an attacker-controlled question containing
  "unparalleled" and "unmatched" could disable PT13 flagging of those
  exact words in the generated prose. Is that an intended semantics
  of "question-inherited"?

Tests in `tests/polaris_graph/test_external_evaluator.py` (2 new):
`test_pt13_exempts_title_and_question_inherited_superlatives` and
`test_pt13_still_flags_real_generator_superlatives`.

### 2. M-3 PT13 advisory surfacing

Read `src/polaris_graph/evaluator/evaluator_gate.py` (the whole file
is small). Answer:

- New `ADVISORY_RULES` dict with PT13 only. Is this pattern
  symmetric with `RELEASE_BLOCKING_RULES` / `COMPLIANCE_BLOCKING_RULES`?
- The advisory branch adds to `reasons` but NOT to `rule_blockers`,
  and does NOT set `abort_on_rule`. Gate_class therefore stays
  `pass` (if no other issues) or `partial`/`abort` (if they exist).
  Is this the intended semantics?
- The `advisory_` prefix avoids collision with existing `rule_*` and
  `qwen_*` reason grep patterns. Are there downstream consumers of
  `reasons` that would be surprised by this new prefix?

Tests: `test_m3_pt13_failure_surfaces_in_reasons_without_gating` and
`test_m3_pt13_passing_does_not_emit_advisory_reason`.

### 3. M-4 runbook material_deviation section

Read `docs/runbook.md` §8 "corpus.material_deviation=true on a
released manifest". The framing claim: "treat the 8-query sweep
output as a pipeline reliability signal, not a quality benchmark
of the generated report's content."

Is this framing accurate? Specifically:

- Does the codebase actually let material_deviation runs through
  (i.e., the corpus_approval_gate auto-approves OR a substantive
  operator note is required)?
- Are the listed re-run levers (`PG_LIVE_MAX_SERPER_PER_Q`,
  academic-first backends, narrower question) real and effective?

### 4. M-2 docs-only deferral

Read `docs/todo_list.md` M-2 entry. The claim is that the
content-aware span finder (commit `b2b6f5a`) already addressed the
dominant root cause with the measurable drops in drop rate. Further
mitigations are deferred unless 8-query sweep shows a regression.

Is this a reasonable disposition, or should at least one of the
options (per-template `PG_PROVENANCE_MIN_CONTENT_OVERLAP`) be
implemented pre-sweep?

### 5. Suite state

Re-run `python -m pytest tests/polaris_graph/ -q` and report.

Expected: 428 pass. Earlier passes had environmental failures in
Codex's shell (WinError 5 on temp dirs); please note whether those
reproduce.

### 6. Final verdict

One of:
- **READY-FOR-8-QUERY-SWEEP**: all follow-ups sound, nothing new
  surfaced
- **NOT-READY**: one of the new changes regresses something or
  creates a new gating issue
- **CONDITIONAL**: ship pending one targeted additional fix

## Output

Write to `outputs/codex_findings/full_audit_pass_6/findings.md`
with frontmatter:

```yaml
---
verdict: READY-FOR-8-QUERY-SWEEP | NOT-READY | CONDITIONAL
pass: 6
commit: 3921bc0
m6_sound: true | false
m3_sound: true | false
m4_sound: true | false
m2_deferral_reasonable: true | false
new_blockers: <int>
new_mediums: <int>
rationale: |
  <2-4 sentence executive summary>
---
```

Followed by `## 1..6.` mirroring the sections above.

## Authentication

OAuth (chatgpt). No API-key burn.

## Expected duration

10-15 minutes (smaller scope than passes 4/5).

---

Start:

```
git log --oneline b2b6f5a..HEAD | head
git show 3921bc0 --stat
python -m pytest tests/polaris_graph/ -q 2>&1 | tail -3
```

Then walk sections 1-6.
