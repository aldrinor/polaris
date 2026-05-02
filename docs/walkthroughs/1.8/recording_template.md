# Phase 1 Walkthrough — Recording Template

For each test input from `test_inputs.md`, capture:

```
INPUT #N: <input text>
EXPECTED: <one-line of what should happen>
OBSERVED: <one-line of what actually happened>
LATENCY: <approx ms or "fast/slow">
SEVERITY: PASS | P3 nit | P2 minor | P1 phase-rework | P0 broken-core
NOTES: <anything weird, screenshot frame number if recording>
```

Example filled-in row:

```
INPUT #6: What is BPEI?
EXPECTED: Modal with 2-5 candidate meanings within 1s
OBSERVED: Modal appeared at 800ms; 4 candidates shown (Beth Israel, biopsychosocial, business process, BC environmental act)
LATENCY: ~800ms (acceptable)
SEVERITY: PASS
NOTES: Candidate "BC environmental act" is interesting — POLARIS surfaced something I hadn't thought of. Useful.
```

If a step fails:

```
INPUT #14: Reference uploaded doc in query
EXPECTED: Citation [#ev:user_doc_*] click → side pane shows span from my PDF
OBSERVED: Citation appeared but click did nothing; no side pane opened
LATENCY: N/A
SEVERITY: P1 phase-rework — F3b grounding flow broken on user docs
NOTES: Recorded at 14:32 in video. Console showed `Cannot read property 'span' of undefined`.
```

## At end of recording

Append a 1-paragraph summary:

```
OVERALL: <how many of 22 passed cleanly>
P0 count: <number>
P1 count: <number>
P2 count: <number>
P3 count: <number>
RECOMMENDATION: ship / ship-with-fixes / halt
EVALUATOR: <your name + date>
```

## File naming

Save the completed log alongside the video:
- `.private/walkthroughs/1.8_<initials>_<YYYY-MM-DD>.mp4` (video, gitignored)
- `outputs/audits/walkthroughs/1.8_<initials>_<YYYY-MM-DD>.md` (this filled template, TRACKED)

The TRACKED markdown file becomes part of task 1.8's verdict evidence per Plan v13 §C-private (HMAC-tracked alongside walkthrough video SHA in attestation).
