## §0 — HARD ITERATION CAP

```
HARD ITERATION CAP: 5. iter 1 of 5. Verdict APPROVE iff zero P0/P1.
```

GH#196 I-tpl-006. Brief iter-1 P1 fixed (vendor sources now T5 per global tier taxonomy from clinical.yaml; T7 reserved for preprints/conference abstracts). YAML safe_load verified.

Net diff: 1 file (~85 lines). Pure config addition.

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
