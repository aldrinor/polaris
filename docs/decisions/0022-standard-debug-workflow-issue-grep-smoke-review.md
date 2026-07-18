# 0022. Standard debug workflow: GitHub Issue first, grep adjacent, smoke test, then review

Status: accepted

Date: 2026-05-09

## Context

Operator directive (2026-05-09) after admitting nine PRs had bypassed the workflow. Skipping steps wastes Codex review iterations and full-sweep budget. Empirically, bugs that surfaced only because the operator pushed, or that blew a full ten-minute sweep, would have been caught by a grep plus a seconds-long smoke test. The trap is treating full sweeps as smoke tests because they are available — they are expensive and slow.

## Decision

Every task, bug, or issue follows this exact sequence:

1. `gh issue create` BEFORE any branch, code, or brief. Title `I-<prefix>-NNN — <summary>`, body with acceptance criteria.
2. Comprehensive grep of all call sites, consumers, downstream checks, and tests, listed in the brief under "Files I have ALSO checked and they're clean".
3. Offline smoke test — a single sentence or single section, NOT a full sweep.
4. Brief the reviewer, including the adjacent-file scan so the reviewer VERIFIES rather than discovers.

The goal is 1-2 iterations per task; the 5-iteration cap (ADR 0023) is a backstop, not a target. Close the issue when the PR merges.

## Consequences

- Grepping the call sites before briefing means the reviewer confirms a scoped change instead of discovering surprises mid-review, which is what collapses iteration count.
- A full sweep is not a smoke test. Use the seconds-long single-sentence smoke before spending a ten-minute sweep, or the sweep budget is wasted on bugs a grep would have caught.
- The issue-first step gives every unit of work acceptance criteria and a home before any code exists, which feeds the sequential issue cage (ADR 0024).
- The first task-work tool call after the boot ritual is `gh issue create` or `gh issue view`; the second is the grep; the third is the smoke test. Anything else is out of order.
