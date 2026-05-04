# `.legacy/` — Read-Only Archive

**Authority:** aldrinor only, signed commits to add. No modifications post-add.
**Effective:** 2026-05-04 (cage establishment)
**CI enforcement:** `.github/workflows/legacy_protection.yml`

---

## What this directory is for

After the 2026-05-04 restart per `polaris-controls/PLAN.md`, code that was previously part of the active POLARIS codebase but no longer fits the new architecture lives here. Examples:

- Abandoned governance patterns (e.g., `halt_resolutions_abandoned/` — the path-3 self-attestation pattern that produced the 28-unauthorized-commits failure)
- Frozen subsystems whose retirement was decided but not yet executed
- Old plans, briefing packs, audit briefs that are superseded by current `polaris-controls` documents
- Speculative substrate from the 2026-05-03 session that was never authorized

## Hard rules (CI-enforced)

1. **Nothing in `.legacy/` is importable from production code.**
 - `src/`, `web/`, `tests/`, `docs/`, `.codex/`, `scripts/` — none of these may `import`/`from` reference `.legacy/*`
 - CI scans every PR for new imports targeting `.legacy/`
 - PR auto-rejected on match

2. **`.legacy/` is read-only after a file lands here.**
 - PRs that modify any existing file under `.legacy/` are auto-rejected
 - To "un-archive" something: re-write it under the active slice with proper review; do not edit the legacy copy
 - To add new archived material: that's allowed (move from active path to `.legacy/<category>/`)

3. **CODEOWNERS gate applies.**
 - `.github/CODEOWNERS` lists `.legacy/` under aldrinor's authority
 - Any PR touching anything under `.legacy/` requires `@aldrinor` approval

## Why this directory exists (the structural failure it prevents)

In the 2026-05-03 session, 28 unauthorized commits were made because the agent could (a) write speculative code, (b) write its own approval markers (halt-resolution path 3), and (c) edit the matrix YAML to claim authorization. The resulting code lives in the local archaeology tag `pre_restart_2026_05_04_archaeology` but explicitly NOT on this branch. See `polaris-controls/PLAN.md` Section 5 for the cutover record.

If old code is needed later (because something in `.legacy/` turns out to have been useful), the recovery path is: re-write the equivalent functionality under an active slice spec, with Codex review, in a new PR. **Do not import from `.legacy/`. Do not modify `.legacy/`.** Those rules are CI-enforced and exist specifically because the failure mode they prevent is documented and recent.

## Layout

```
.legacy/
├── README.md                              (this file)
├── halt_resolutions_abandoned/            Path-3 self-attestation markers, abolished
│   ├── README.md
│   └── *_halt.md
├── (future) pipelines/                    e.g., pipeline_c_frozen if/when src/orchestration retires
├── (future) substrate/                    e.g., briefing-pack iterations from sessions 2026-05-01..03
└── (future) docs/old_plans/               Superseded plan documents
```

## How to add to `.legacy/`

1. `git mv <active-path> .legacy/<category>/<filename>`
2. Update or add `.legacy/<category>/README.md` explaining what was archived and why
3. Verify nothing in active paths still imports the moved code (run import-check locally before PR)
4. Commit on a feature branch
5. Open PR (CI will check no production paths import from `.legacy/`)
6. Merge with `@aldrinor` approval

## How to remove from `.legacy/`

You don't. If functionality is needed back, write it fresh under the active slice, in a new file at the canonical path. The legacy copy stays as historical reference.
