# 0003. Compose the report first, verify per-sentence afterward

Status: accepted

Date: 2026-07-05

## Context

For months the reports came out shallow and disjointed. The root cause, converged by Codex and Fable over a study of DeepTRACE, DeepResearch-Bench-II, LongCite, STORM, WebWeaver and TTD-DR (`REAL_PLAN_2026`, 2026-07-05): the composition unit and the verification unit were the same thing. When every unit you compose must also be a unit that passes the faithfulness gate, the writer cannot build a narrative across evidence — it can only emit verifiable fragments, which read as a list of disconnected sentences.

## Decision

Compose a coherent report first. Then run the unchanged faithfulness gate as a downstream, per-sentence filter. The composition unit must not be forced to also be the verification unit. Coverage is treated as a co-equal goal alongside faithfulness, not a side effect.

## Consequences

- Depth is now free to emerge at composition time, because the writer builds narrative first and grounding is checked afterward, not at every fragment boundary.
- The faithfulness gate is unchanged — it still runs per sentence and still drops what it cannot ground (see ADR 0014). Separating the two units does not weaken grounding; it stops grounding from starving depth.
- This is the load-bearing architecture conclusion after a long run of depth failures, so it should be treated as a fixed constraint: never re-couple composition granularity to verification granularity to simplify a stage.
- It sets up the section-modular direction (ADR 0018, ADR 0019): compose whole sections, verify their sentences downstream, and let report depth be the sum over all sections.
