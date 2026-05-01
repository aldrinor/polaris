# Codex Red-Team Checklist (v1.0)

**Purpose:** This is the fixed adversarial checklist Codex applies to every task in the Carney Delivery Plan. It is INDEPENDENT of Claude's task brief — Claude cannot remove items from this checklist for a given task. It exists to prevent ceremony, phantom completion, and rubber-stamp reviews.

**Created:** 2026-05-01. **Owner:** Codex review process.
**Used for:** every task in Phase 0 through Phase 5 of `docs/carney_delivery_plan_v5_1_redline.md`.

---

## How Codex applies this

For each task review, Codex receives:
1. The task brief (`task_<id>_review_brief.md`)
2. The task manifest (`task_<id>_manifest.json` — see schema below)
3. The git diff (PR or commit range)
4. Test output (CI logs, command output)
5. Acceptance artifacts (recordings, screenshots, traces, transcripts)

Codex applies this checklist independently. Findings are recorded with severity P0/P1/P2 and tied to specific checklist items.

---

## Universal checks (apply to every task)

| # | Item | Required artifact | Codex action |
|---|---|---|---|
| U1 | Task ID matches the plan | manifest.task_id present and matches `docs/task_acceptance_matrix.yaml` | RED if missing |
| U2 | All `green_criteria` from acceptance matrix have linked evidence | manifest.evidence_links covers every criterion | RED if any unlinked |
| U3 | All `required_artifacts` from acceptance matrix exist on disk + committed | git ls-files confirms presence | RED if missing |
| U4 | Diff matches task scope | code change is bounded to declared files | YELLOW if scope-creep, RED if mid-task acceptance criterion changed |
| U5 | Tests pass | manifest.test_commands all return 0 in CI | RED if any fail |
| U6 | New functionality has new tests | diff coverage analyzer shows new code is tested | YELLOW if untested |
| U7 | Documentation manifest is COMPLETE (not prose-only) | manifest fields all populated, non-empty, linked | RED if any required field empty |
| U8 | Open bugs are listed (not silently dropped) | manifest.open_bugs is honest about known issues | RED if known issue not listed |

## UI/user-flow task additional checks

| # | Item | Required artifact | Codex action |
|---|---|---|---|
| F1 | Recording attached | manifest.recordings has video/audio of fresh-state walkthrough | RED if missing |
| F2 | Walkthrough is fresh state, not coached | recording shows new account / clean cookies / no developer console | RED if dev mode or coached |
| F3 | Adversarial inputs covered | recording shows evaluator-supplied inputs (not curated demo prompts) | RED if only curated |
| F4 | All 4 input classes attempted | supported / unsupported / ambiguous / failing — recording shows each | RED if class skipped |
| F5 | Empty states tested | recording shows zero-result, error, partial-load conditions | YELLOW if happy-path only |
| F6 | Mobile / narrow viewport tested | screenshot at 375px width | YELLOW if missing |

## Crown jewel surfacing checks (apply to every Phase 2 task)

| # | Item | Required artifact | Codex action |
|---|---|---|---|
| C1 | Every user-visible factual assertion is gated-and-clickable OR `ungated` badged | sampled report shows no silent unsupported claims | RED if any silent ungated assertion |
| C2 | Evidence Contract schema validated | manifest.artifacts includes a JSON Schema validation pass against `docs/evidence_contract.md` | RED if validation fails |
| C3 | Frame coverage panel above-the-fold in report view | screenshot shows it before scroll | RED if buried |
| C4 | Contradictions navigable (not just shown) | recording shows badge → side pane → all sides | RED if static-text only |
| C5 | Two-family disagreement visibly flagged | sampled report with disagreement shows the flag | RED if signal hidden |

## LLM-call / model-serving task additional checks

| # | Item | Required artifact | Codex action |
|---|---|---|---|
| L1 | Trace IDs flow from API → queue → LLM call → SSE event | OpenTelemetry trace shows full chain | RED if broken |
| L2 | Family segregation invariant holds | generator and evaluator are different lineages, RuntimeError raised if violated | RED if not enforced |
| L3 | strict_verify gate applied | per-sentence verify decisions visible in trace | RED if absent |
| L4 | Cancel / retry / resume work | manifest.test_commands include queue acceptance test | RED if test missing |

## Documentation manifest schema (referenced by U7)

Every `task_<id>_manifest.json` MUST have:

```json
{
  "task_id": "0.6",
  "phase": 0,
  "title": "DeepSeek V4 Pro hardware decision",
  "owner": "claude+user",
  "started_at": "2026-05-02T10:00:00Z",
  "completed_at": "2026-05-04T15:00:00Z",
  "estimate_hours": 16,
  "actual_hours": 14,
  "changed_files": ["docs/hardware_decision.md", "..."],
  "test_commands": ["python -m pytest tests/hardware/", "..."],
  "artifacts": [
    {"type": "decision", "path": "docs/hardware_decision.md"},
    {"type": "quote", "path": ".private/ovh_quote.pdf"}
  ],
  "recordings": [],
  "trace_ids": [],
  "open_bugs": [],
  "evidence_links": [
    {"green_criterion": "Path A/B/C committed", "artifact": "docs/hardware_decision.md", "line_range": "1-30"}
  ],
  "codex_findings_addressed": ["P1: ..."],
  "walkthrough_artifact": null
}
```

Empty arrays must be deliberate, not default. If a field doesn't apply, document why in `artifacts[]` with type `n/a-rationale`.

## Escalation rules (Codex applies these mechanically)

| Trigger | Action |
|---|---|
| Same P1 finding twice across two reviews of same task | RED, escalate to user |
| Acceptance criterion changed mid-task without RED escalation first | RED |
| Task exceeds 150% of estimate_hours | YELLOW first time, RED second time |
| Walkthrough missing for UI/flow task | RED |
| Recording not fresh state | RED |
| Manifest field empty without `n/a-rationale` | RED |
| 48h elapsed since walkthrough required without recording | task auto-reverts to BLOCKED, plan halts |
| Evidence Contract Gate not satisfied for Phase 2 task | RED, no exceptions |
| Codex GREEN given AND walkthrough recording reveals issue afterward | retroactive RED, task re-opened |

## Anti-patterns Codex refuses (will RED on sight)

- Prose-only doc updates without manifest
- "Tests will be added in next task" — RED, tests required at task GREEN
- "Will be polished in Phase 3" — RED, scope-creep deferral
- "Same as previous task" — RED, manifest must be specific
- "TODO" in committed code without an open bug filed
- "Demo data" in production code path without explicit dev-only env guard

## Scope of this checklist

Applies from Phase 0 Task 0.1 through Phase 5 final handover. Every task. No exceptions. Codex does not skip checklist items "for speed."

If Claude argues that a checklist item doesn't apply, Codex requires a YAML override in `task_<id>_manifest.json` under `checklist_overrides[]` with rationale. User reviews overrides at end-of-phase.

---

**Version pinning**: this checklist v1.0 is committed to git. Changes require a new version (v1.1, v2.0) and explicit user approval. Mid-build modifications are RED.
