# Codex diff — I-cd-035 (#635) — runbook update

Canonical-diff-sha256: `2e9a4d6d26291006e869266772a39948af5a2cecd2f91f110930b09c8777e5a9`. Docs-only change.

## Diff summary
- Stack table reflects current deploy state (OVH BHS5 polaris-orchestrator, not Vexxhost).
- LLM-production row: OpenRouter with V4-Pro + Gemma 4 31B (per I-cd-009).
- Sovereign-GPU target row: OVH H200 OR EU (Scaleway/Hetzner) per operator directive 2026-05-18.
- Vexxhost row: marked RETIRED for honest doc-state.
- Domain status: bare IP 51.79.90.35:3000 today; TLS at Seq 36 / #636.
- §1 framed as preserved-for-reference (not active path).

Final accuracy refresh deferred to I-D-05 / #651 per the breakdown.

Output schema:
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
