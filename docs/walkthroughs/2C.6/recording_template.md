# Phase 2C Walkthrough — Recording Template

Recording per session (9 sessions total: 3 templates × 3 browsers).

For each session, capture per-step observations using the same row format as Phase 1.8:
```
STEP #N: <step from test_inputs.md>
EXPECTED: <one-line>
OBSERVED: <one-line>
LATENCY: <ms or qualitative>
SEVERITY: PASS | P3 | P2 | P1 | P0
NOTES: <observations / video timestamp>
```

End each session with summary:
```
SESSION: Template=<X>, Browser=<Y>
OVERALL: <pass count>/20 steps
P0/P1/P2/P3 counts: <numbers>
TIME: <minutes>
EVALUATOR: <name>
```

After all 9 sessions, append cross-session summary (see test_inputs.md).

## Filename pattern

- `.private/walkthroughs/2C.6_<initials>_<browser>_<template>_<YYYY-MM-DD>.mp4` (×9)
- `outputs/audits/walkthroughs/2C.6_<initials>_<YYYY-MM-DD>.md` (single TRACKED summary covering all 9)
- `outputs/audits/attestations/2C.6_<initials>.md.asc` (GPG clearsigned)
