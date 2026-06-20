# BEAT-BOTH ONGOING BUG LOG (durable, append-only)

**Purpose (operator-locked 2026-06-20):** during every VM run, the 5-min forensic monitor appends every bug/issue discovered (from memory/log/reasoning/output) HERE, in point form. This log MERGES into the post-run Phase-1 audit so nothing is lost between the live run and the offline audit. Append-only — never delete; mark RESOLVED in place.

Format per entry:
```
[YYYY-MM-DD HH:MM UTC] run=<id> phase=<stage> SEV=<P0/P1/P2/P3> area=<log|memory|reasoning|citation|output>
- BUG: <one line, concrete>
- EVIDENCE: <log line / span / file:line>
- BENCHMARK_IMPACT: <deeptrace|drb2|both|none + why>
- STATUS: OPEN | RESOLVED(<commit/issue>)
```

---

## ENTRIES

_(none yet — first VM run under the new plan has not started; run7 is being audited offline as Phase 1)_
