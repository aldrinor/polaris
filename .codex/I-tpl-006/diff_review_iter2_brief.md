## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 2 of 5. Verdict APPROVE iff zero P0/P1.
```

## §1 — Iter-1 P1+P2 disposition

| Iter-1 | Iter-2 fix |
|---|---|
| **P1** YAML safe_load fails on colon-bearing list items | **FIXED.** All inclusion/exclusion items now double-quoted strings; em-dashes replace colons. `python -c "yaml.safe_load(...)"` → `OK ai_sovereignty inclusion: 8 tiers: 6`. |
| **P1** ai_sovereignty not in SUPPORTED_DOMAINS | **FIXED.** scope_gate.py:69 SUPPORTED_DOMAINS now includes ai_sovereignty + canada_us + workforce (registered for I-tpl-006/7/8 trio). |
| **P2** Stale T7 comment | **FIXED.** Comment now correctly says T5. |
| **P2** Brookings/RAND treated as peer-reviewed | **FIXED.** Now explicitly: "Policy-institute reports from Brookings, RAND, Belfer Center, AI Now Institute, GovAI (treated as T6 — analyst commentary, NOT peer-reviewed)". T1 line now strictly "Peer-reviewed AI-policy journal articles". |

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
