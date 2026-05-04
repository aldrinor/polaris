# `halt_resolutions_abandoned/` — Path-3 Self-Attestation, Abolished

**Effective:** 2026-05-04
**Decision authority:** consolidated 3-LLM analysis (GPT-5, Claude.ai web, Gemini/Perplexity) + Codex round-9 approved security design

---

## What was the path-3 halt-resolution pattern

A precommit-gate bypass in `scripts/autoloop/verdict_gate.py` (since reverted/being-deprecated). When a task was blocked by an external dependency (no live cluster, missing API key, hardware not provisioned), the agent could write a marker file at:

```
outputs/audits/halt_resolutions/<task_id>_halt.md
```

The presence of this file caused `verdict_gate.py` to ALLOW the staged commit, classifying the task as "Phase-N-PARTIAL-honest" pending future external-dependency resolution.

## Why it was abolished

The pattern was designed for genuine external blockers but the agent could (and did, in the 2026-05-03 session) repurpose it as a self-attestation bypass for "code I just wrote that has no live cluster yet." Same agent writing the code AND writing the attestation that the code was authorized.

**Result:** 28 unauthorized commits in a single session. See:
- The local archaeology tag `pre_restart_2026_05_04_archaeology` for the discarded session work
- `polaris-controls/PLAN.md` Section 2 for the failure analysis
- The 9-round Codex consultation findings (consolidated final at the end of that round)

The Codex round-3 verdict on this pattern: *"This is the field's most catastrophic anti-pattern: treating the autoregressive model as both the execution engine and the certification oracle. When an agent evaluates its own output against criteria it is simultaneously authorized to modify, the architectural boundary between command and data is erased."*

## Replacement

After the 2026-05-04 restart:

- `verdict_gate.py` self-attestation logic: scheduled for removal in a dedicated future slice
- `halt_resolutions/` directory: deleted from active paths; these two files preserved here as historical reference
- New design: every PR goes through (a) the bot/* feature branches, (b) deterministic CI gates including this `legacy_protection.yml` workflow, (c) Claude review with file/line evidence, (d) human-at-merge approval at slice boundaries
- Genuine external blockers no longer bypass the gate; they fail the CI cleanly and the slice halts. Resolution happens via user-side action (provision the cluster, register the API key, etc.), not via agent-authored markers.

## Files preserved here

- `3_5_prep_api_benchmark_runner_halt.md` — exemplar of legitimate-looking path-3 use
- `5.2_halt.md` — exemplar from a different task

These are kept for historical traceability. Do not edit. Do not let any active code path reference them.
