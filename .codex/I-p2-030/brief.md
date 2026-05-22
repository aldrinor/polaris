# Codex BRIEF review — I-p2-030 (#769): concrete standards gates (responsive/i18n/content/perf/security)

HARD ITERATION CAP: 5. iter 2 (iter-1 fixed: G-SEC redaction+tamper-logs, G-PERF export budget, G-CONTENT domain-copy). APPROVE iff the gates are concrete, measurable, complete, and faithful to rubric dims 9-13. Docs/standards only.

## Task
Operationalize the 16-dim rubric's dimensions 9-13 (state/polaris_phase2_ui_breakdown_2026_05_21.md) into concrete MEASURABLE gates that every Phase-2 UI task is audited against.

## Acceptance criteria
1. `.codex/PHASE2_GATES.md` defines measurable gates: G-RESP (viewport matrix 1440/1024/768/390 + 200/400% zoom + forced-colors + print + target-size), G-I18N (EN-first waiver + i18n-readiness: no hardcoded strings, Intl formatting, +30% expansion), G-CONTENT (honesty copy banned/required, caveats, refusal-as-feature), G-PERF (LCP<2.5/CLS<0.1/INP<200, route JS<250KB, span-open<1s, KG 1k@60fps), G-SEC (RBAC/egress/data-class/PHI-PII/signed-export — evidence not badge).
2. Wired into `.codex/DESIGN_AUDIT_BRIEF_FORMAT.md` §3 (dims 9-13 cite the gate IDs + measured values).
3. Honest about CI wiring being a follow-up (operator-admin .github/workflows; #567/#720).

## Files I have ALSO checked and they're clean
- state/polaris_phase2_ui_breakdown_2026_05_21.md (dims 9-13, the source).

## Review focus
1. Are the thresholds CONCRETE + MEASURABLE (not vague)? Any wrong/unrealistic number?
2. Any dim-9-13 sub-requirement dropped vs the standard?
3. EN-first waiver correctly scoped (i18n-ready now, FR later)?

## Output schema
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
```
