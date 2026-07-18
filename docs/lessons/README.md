# POLARIS Lessons Hub

Standing rules mined from the project's session logs, bug log, forensic plans, Codex/Fable verdicts, and operator memory. Each rule is written as guidance, with why it matters, a source pointer, and how often it recurred.

These are hub notes, not a new source of truth. Where a rule is already binding, the theme file names its canonical home (CLAUDE.md section or memory file). Read those for the authoritative wording.

## How to use this hub

- To grade a report or the pipeline's own data, read `line-by-line-audit-faithfulness-ghost.md` FIRST — a count is never a quality verdict.
- To debug a wrong/thin output, read `debugging-forensic-monitoring.md` — grep for the built-but-default-OFF module, gate on a re-read of the real output, prove it in a small real run.
- Before writing a Codex brief, read `codex-fable-review-gate-workflow.md` and measure the funnel first.

## Theme files (with mined lessons)

| Theme | File | Rules |
|---|---|---|
| Line-by-line audit standard & the faithfulness ghost (grading discipline) | [line-by-line-audit-faithfulness-ghost.md](line-by-line-audit-faithfulness-ghost.md) | 2 |
| Faithfulness engine & span grounding (runtime) | [faithfulness-engine-span-grounding.md](faithfulness-engine-span-grounding.md) | 6 |
| Retrieval, weighting & source triage (WEIGHT-not-FILTER) | [retrieval-weighting-source-triage.md](retrieval-weighting-source-triage.md) | 4 |
| Pipeline architecture, depth & parallel composition (the moat) | [pipeline-architecture-depth-parallel-composition.md](pipeline-architecture-depth-parallel-composition.md) | 5 |
| Debugging & forensic monitoring methodology | [debugging-forensic-monitoring.md](debugging-forensic-monitoring.md) | 7 |
| Model & token governance / sovereignty constraint | [model-token-governance-sovereignty.md](model-token-governance-sovereignty.md) | 2 |
| Codex/Fable review gate & issue-driven workflow | [codex-fable-review-gate-workflow.md](codex-fable-review-gate-workflow.md) | 5 |
| Evaluation, benchmarking & beat-both scoring | [evaluation-benchmarking-beat-both.md](evaluation-benchmarking-beat-both.md) | 4 |
| Governance cage, session protocol & state persistence | [governance-cage-session-protocol.md](governance-cage-session-protocol.md) | 1 |
| Autonomous execution loop & no-pause discipline | [autonomous-execution-loop-no-pause.md](autonomous-execution-loop-no-pause.md) | 1 |
| Resource discipline, VM ops & infrastructure | [resource-discipline-vm-ops.md](resource-discipline-vm-ops.md) | 1 |

## Taxonomy themes with no lessons mined in this batch

These themes are part of the taxonomy but drew no lessons from this mined set. Their standing rules already live at the canonical homes below; no hub file was written to avoid a placeholder.

- UI / web app & visual audit — CLAUDE.md §3.0 (6th artifact / visual audit); memory `feedback_visual_audit.md`, `feedback_top_tier_visually_verified_not_merged_2026_05_21.md`; `docs/ui_harness_master_plan_2026_05_25.md`.
- Operator communication & working norms — CLAUDE.md §0.4; memory `feedback_plain_declarative_writing_standard_2026_06_18.md`, `user_is_blind_screen_reader_2026_05_28.md`, `feedback_status_reports_full_list_every_run_2026_06_17.md`.
- Security & threat modeling — CLAUDE.md §9.1 invariant 7 (delimiter sanitization); memory `feedback_sovereignty_threat_model_2026_05_13.md`; `docs/md*_threat_model.md`, `docs/m26_threat_model.md`, `docs/crown_jewels.md`.
- Delivery mission, regulatory compliance & positioning (Carney) — CLAUDE.md §1.1 item 5 + §-1.1 item 4; `docs/carney_delivery_plan_v6_2.md`, `docs/compliance_templates/`, `docs/pricing_and_positioning.md`.
