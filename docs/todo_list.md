# DEPRECATED — see `docs/task_acceptance_matrix.yaml`

**This file is deprecated as of 2026-05-02 per Plan v13 Bootstrap §K Step 14.**

The Active Project Definition (APD) Scope source is now:
- `docs/task_acceptance_matrix.yaml` — per-task GREEN criteria, change_files_glob, substrate_prep
- `docs/carney_delivery_plan_v6_2.md` — mission + phase plan

This file is preserved as a stub so the few remaining historical references
(audit-trail briefs, prior codex findings) don't 404. Do NOT add new content here.

For current state of all 130+ tasks, query the matrix:
```
grep -E "^\s+(task_|status:|user_action:)" docs/task_acceptance_matrix.yaml
```

Or check the Stop hook output — it computes the next actionable task in
canonical-plan sequence by reading the matrix.

**Active task as of 2026-05-02:** Phase 0 Task 0.5 (in_progress; Backend
modernization + Dramatiq queue acceptance test). Subsequent tasks queue per
matrix sequence.
