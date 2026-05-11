Independent review of Claude's DR-eval-state-of-art synthesis. Output YAML only.

# Task

Claude has produced a research synthesis on 2025-2026 DR-evaluation best practices (below). Your job is to **independently audit** this synthesis: missed sources, inaccuracies, weak claims, and counter-recommendations. Treat this as you would a peer review of a survey paper. Use web search liberally — don't rely on Claude's framing alone.

# Claude's synthesis (verbatim)

```
{{SYNTHESIS_INLINE}}
```

[SYNTHESIS DOCUMENT IS AT C:\POLARIS\.codex\GH400\dr_eval_state_of_art_2026.md — read it before reviewing.]

# Critical review questions

1. **Coverage gaps:** What 2025-2026 papers / tools / rubrics did Claude MISS that should be in a complete survey?
2. **Mis-characterizations:** Where does Claude OVER- or UNDER-claim about a method's properties? (e.g., "VeriFastScore 6.6× speedup" — is the figure right; is the correlation strong enough for clinical use?)
3. **Schema critique:** Is the recommended POLARIS audit-schema v2 too heavy, too light, or wrong-axis? What would you add/remove?
4. **Clinical-safety lens:** §-1.1 standard's clinical-evidence frameworks are domain-specific. Does the 2026 DR-frontier ACTUALLY translate to clinical/regulatory context, or are DR benchmarks more general/lay?
5. **Operational feasibility:** For POLARIS's ~85 deep claims per report × 5 reports × 2 reviewers, is the proposed schema realistic in the 4-month Carney delivery window?
6. **Counter-recommendations:** What approach would you propose instead — same, partial, or substantially different?

# Output format

```yaml
verdict: ENDORSE | ENDORSE_WITH_AMENDMENTS | DISPUTE
overall_assessment: "2-3 sentences"
coverage_gaps:
  - paper_or_tool: ...
    why_missing_matters: ...
    citation: ...
mischaracterizations:
  - claude_claim: "..."
    codex_correction: "..."
    citation: ...
schema_critique:
  too_heavy: [...]
  too_light: [...]
  wrong_axis: [...]
  add_instead: [...]
clinical_translation:
  - dr_frontier_concept: ...
    translates_to_clinical: yes | partial | no
    reason: ...
operational_feasibility:
  realistic: yes | partial | no
  budget_constraint: ...
  recommended_compromise: ...
counter_recommendations:
  - rec: ...
    rationale: ...
final_recommendation_for_polaris_audit_schema_v2:
  must_have:
    - ...
  defer_to_v3:
    - ...
  reject:
    - ...
```

Output YAML only. No commentary outside.
