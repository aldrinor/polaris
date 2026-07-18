# POLARIS Postmortems

Blameless postmortems for the costly failures and days lost across POLARIS
development. Each entry focuses on what happened, why the system allowed it, and
what durable rule the lesson was promoted to — not on who did it.

Every file follows the same shape:

- `## What happened`
- `## Root cause`
- `## Contributing factors`
- `## Lessons (promoted to)`

## Index (newest first)

| Date | Theme | Incident |
|---|---|---|
| 2026-07-08 | review-process | [Wrong division of labor — a 2.3M-token fan-out that produced nothing](2026-07-08-fable-brain-opus-hands-gate-split.md) |
| 2026-07-05 | autonomy | [The 4-hour autonomous freeze — a delete guard blocked every loop wake on line one](2026-07-05-four-hour-autonomous-freeze-rm-rf-guard.md) |
| 2026-07-02 | evaluation | [Offline tests are not a preflight — a stale cache hid three stacked bugs](2026-07-02-offline-tests-not-a-preflight-keystone-collapse.md) |
| 2026-06-13 | process | [The lost day — breadth-hacks bolted on instead of executing the approved design](2026-06-13-lost-day-breadth-hacks-instead-of-executing-approved-design.md) |
| 2026-04-17 | faithfulness | [Self-grading inflation — SUPPORTED defaulted from a substring match](2026-04-17-self-grading-supported-on-substring-match.md) |
| 2026-04-13 | resource / VM-ops | [Backgrounding a long run with `&` orphaned it and it was SIGKILLed](2026-04-13-bash-background-ampersand-sigkill.md) |
| 2026-03-17 | review-process | [Background agents report "done" while the work is unwired](2026-03-17-background-agents-report-done-but-unwired.md) |
| 2026-03-02 | review-process | [A green audit bought with test cheats hid the real bugs](2026-03-02-green-audit-bought-with-test-cheats.md) |

## Cross-cutting themes

- **A green number is not proof.** A passing test, a matched substring, a green
  audit count, or an "implemented and tested" report can all be true on the
  surface while the real work is unwired, cheated, or served from stale cache.
  Verify by reading the live behavior and the actual call site (2026-03-17,
  2026-03-02, 2026-04-17, 2026-07-02).
- **Don't chase a number against the design.** Bolt-on caps, targets, and
  thinners fight the weight-and-consolidate architecture; breadth and quality
  emerge from honest work, they are not forced (2026-06-13).
- **Autonomy needs safe wakes and durable completion.** No guard-tripping command
  at a wake's start; a finished workflow must self-commit so completion equals
  committed (2026-07-05, 2026-04-13).
- **Separate diagnosis from building.** A confident-but-wrong root cause flowed
  straight into wrong code and a token blowup until diagnosis and building were
  split with a gate between them (2026-07-08).
