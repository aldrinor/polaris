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
INPUT #1: Drug name (clinical scope) — type 'tirzepatide'
EXPECTED: Clinical drug audit template suggested within 200ms; click loads scope examples
OBSERVED: Suggestion appeared at ~3500ms (well over 200ms budget); template loaded but scope examples panel was empty
LATENCY: ~3.5s (4× over budget)
SEVERITY: P1 phase-rework — F1 latency budget blown; scope panel empty contradicts dashboard inline-scope substrate
NOTES: Recorded at 02:14 in video. Network tab showed `/scope/check` round-trip = 800ms; remaining 2.7s was unattributed render delay. Filed under F1, not F3 (Block C uploads were endpoint-contract-only and PASSed per Phase-1-PARTIAL bar).
```

## At end of recording

Append a 1-paragraph summary:

```
OVERALL: <how many of 17 passed cleanly>
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
