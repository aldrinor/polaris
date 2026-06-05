# Implementation for #1098

See issue #1098 for details.

## Context
Operator authorized (2026-06-05) running the **paid single-question smoke run** on the OVH VM (51.79.90.35) using `bot/I-ready-consolidated` (the readiness-audit superset: B-then-A Tier-A/Tier-B work #1061–1065 + the 7 INDEP readiness fixes #1070–1084 + the I-ready-016b slate activation #1097). Purpose: validate the full-capability pipeline runs end-to-end on ONE locked golden question before the 5×1000 beat-both run.

## Acceptance criteria
- [ ] `bot/I-ready-consolidated` code deplo