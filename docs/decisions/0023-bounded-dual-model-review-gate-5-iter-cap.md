# 0023. Bounded dual-model review gate: Codex and Fable, hard 5-iteration cap, front-loaded findings

Status: accepted

Date: 2026-05-06

## Context

This decision REVERSES an earlier rule. On 2026-04-18/19 the autonomous Codex loop was explicitly set to "no hard cap" — "Codex is the decision-maker, don't put a hard cap here, terminate only on approval." That rule was reversed on 2026-05-06 (`CLAUDE.md` §8.3.1) because unbounded iteration was commercially unviable: the 21-iteration `cleanup_audit` produced roughly 30 real bugs but a prohibitive cycle time. The durable form is the cap, not the no-cap.

Trust in the reviewer's findings is empirically justified — Codex caught a `git clean -fdX` that would have nuked `.env` and a 2.2GB checkpoint, a `.gitignore` inline-comment bug, and a Windows-only script break. Later (2026-07-04) a second real reviewer was added: Fable APPROVED while Codex caught a real parser edge that would have silently shipped a dark flag.

## Decision

Every brief and every diff is gated by BOTH the real Codex CLI AND the real Fable 5 model; both must return APPROVE before commit. Hard cap of 5 iterations per document. If a reviewer still returns REQUEST_CHANGES at iteration 5, Claude force-APPROVEs on the remaining non-P0/P1 findings, captures residuals as follow-up Issues, logs the force-approval, and proceeds — iteration 6 does not exist.

Every brief opens with the verbatim cap directive demanding ALL real findings front-loaded in iteration 1 (no drip-feeding), the same bar every iteration, and P0/P1 reserved for real execution risks. Invoke Codex as `env -u OPENAI_API_KEY codex exec` (OAuth/ChatGPT, never the API key). The verdict follows a bound YAML schema and is parsed from the written file's LAST `verdict:` line, never an agent self-report. The current heavy-thinking reviewer is Codex 5.6 Sol Max; do not use an Opus-4.8 advisor as the gate.

## Consequences

- Two genuinely independent reviewers catch what one misses, so never single-gate and never drop Fable to save time.
- Front-loading exists because without it the reviewer drip-feeds findings and inflates the iteration count; the cap only works if findings arrive in iteration 1.
- Force-approve plus a follow-up Issue preserves real residual bugs without letting them block shipping. Do not narrow scope to fake convergence, and do not iterate to 6.
- 1-2 iterations is the goal; 5 is a backstop. A verdict must come from the written file, because an agent's self-reported verdict is not trustworthy.
