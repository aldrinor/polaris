---
name: investigate-then-consult
description: "Before acting on any finding, investigate deeply then consult the user first — never rough judgment"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

When monitoring the flywheel/fetch and I notice ANYTHING (an anomaly, a bug, a suspicious number, a design smell, a possible fabrication hole): do NOT act on it or draw a conclusion from a quick look. First investigate deeply (root-cause it, verify the claim with real code/data, rule out my own misreading), THEN bring the finding to the user and consult BEFORE taking action.

**Why:** I have a repeated failure mode of rough/premature judgments that turn into messes — e.g. tonight I ran competing fetch runners on a rough assumption ("wrong blob dir, no product") and corrupted the ledger; earlier I false-reported "no regressions" by reading only the top-9 criteria; I misdiagnosed judge-leniency as a deterministic-admit bug. Each was a snap judgment acted on without deep investigation or checking with the user first.

**How to apply:** (1) Monitor closely and continuously, surface every real new event. (2) On any finding, investigate to root cause with evidence before saying what it is. (3) Present the investigated finding to the user and ask before acting — especially anything that mutates shared state (git, ledger, blobs, running processes) or touches the fabrication guard. (4) Never launch a process that competes with an owning agent. One writer. Related: [[codex-5-6-token-cost-rule]].
