M-2 web app skeleton + V30 mounting — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

M-1 is GREEN locked (3 review rounds, 51 tests). Now M-2: mount V30
run-14 as canonical demo via FastAPI router, with HTML shell scaffold
for the 5 Inspector views.

## What landed

Files:
- `src/polaris_graph/audit_ir/registry.py` — V30 artifact discovery
- `src/polaris_graph/audit_ir/serializer.py` — manual recursive
  walker handling Path, MappingProxyType, frozen dataclasses
- `src/polaris_graph/audit_ir/inspector_router.py` — FastAPI
  APIRouter with 5 routes
- `scripts/templates/inspector_shell.html` — 5-view tab scaffold
- `scripts/static/inspector/inspector.css` — audit-grade visual
  language (dark, mono for IDs, tier color tokens)
- `scripts/static/inspector/inspector.js` — loads IR, renders
  tier-mix strip + tab counts + report shell scaffold
- `scripts/live_server.py` — included router (single edit)

Tests: 51 → 72 (21 new).
- test_audit_ir_registry.py: 7 tests for run discovery
- test_audit_ir_serializer.py: 6 tests for JSON coercion
- test_inspector_router.py: 8 tests with FastAPI TestClient

Live_server boots cleanly: 5 inspector routes + 77 existing = 82 total.

## Routes mounted

| Method | Path | Purpose |
|--------|------|---------|
| GET | /api/inspector/runs | list runs |
| GET | /api/inspector/runs/{slug} | full AuditIR JSON |
| GET | /api/inspector/runs/{slug}/report.md | raw markdown |
| GET | /inspector | redirect to canonical demo |
| GET | /inspector/{slug} | HTML shell (5-view scaffold) |

## Phase A intent

Per FINAL_PLAN.md: Phase A serves CONTROLLED-ACCESS demo traffic only
— invite-only / pilot / NOT open internet beta. Phase B replaces the
existing PipelineRunner single-run lock with queue + concurrency.

This means M-2 deliberately does NOT add auth or rate-limiting at the
router layer; the existing live_server auth + the Phase A access-
gating policy is the trust boundary.

## Your job

Code review for M-2. Verdict: GREEN / PARTIAL / DISAGREE.

## Specific things to validate

1. **Router design.** APIRouter mounted via app.include_router — single
   edit to live_server.py. Is this the right integration pattern, or
   should the routes have lived inside live_server.py directly?

2. **Run discovery.** registry.py scans outputs/**/manifest.json with
   no caching. For 1-3 demo runs that's fine; at Phase C with
   50-100 templates this becomes O(N) on every request. Should I add
   a simple in-memory cache now or defer to Phase C?

3. **Serializer.** Manual recursive walker replacing dataclasses.asdict()
   because MappingProxyType can't be pickled. Any issues with this
   approach? Specifically:
   - Does the recursion handle every IR type correctly?
   - Should it be more defensive (e.g., explicit guard against
     circular refs)?
   - JSON-safety: does it produce output that round-trips through
     json.dumps without errors? (Test asserts this — but does anything
     else need attention?)

4. **HTML shell.** 5-view tab scaffold, vanilla JS, no framework.
   Inline CSS/JS is fine for Phase A but Phase B will likely need
   componentization. Is the current structure acceptable as-is, or
   does it need bones-up restructuring before M-3 wires the report
   click-to-inspect interaction?

5. **CSP in live_server.py.** The existing security headers middleware
   has a Content-Security-Policy that allows 'self' + cdn.jsdelivr.net.
   The inspector loads /static/inspector/inspector.js via 'self'. Is
   there any CSP gotcha I'm missing for the inspector page?

6. **Tier color tokens.** I used T1=green, T2=blue, T3=yellow, T4=orange,
   T5=red, T6=purple, T7=gray. Some Phase B users might want a
   colorblind-safe palette. Is this acceptable for Phase A or should
   I switch now?

7. **Phase A access gating.** The router doesn't add auth. Is that
   correct given the FINAL_PLAN's "controlled-access only / not open
   internet beta" stance, or should I add a soft "Phase A" banner +
   no-index meta to make the limitation visible?

8. **Test coverage gaps.** 21 new tests for M-2 — anything important
   not covered?

## Output

Write to `outputs/codex_findings/m2_review/findings.md`:

```markdown
# Codex review of M-2

## Verdict
GREEN / PARTIAL / DISAGREE

## Specific issues
List concrete bugs / gaps / design problems.

## Recommended changes
If PARTIAL: specific edits (file:line).

## M-3 readiness
Is the IR -> JSON path ready for M-3 (View 1 click-to-inspect)
to consume?

## Final word
GREEN to lock M-2 / PARTIAL with edits / DISAGREE.
```

Be terse. Under 300 lines.
