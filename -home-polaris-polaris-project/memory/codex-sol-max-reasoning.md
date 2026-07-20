---
name: codex-sol-max-reasoning
description: "Standing rule — every Codex gate/consult runs as sol model at MAX reasoning, via CLI reading files"
metadata: 
  node_type: memory
  type: feedback
  originSessionId: 21e87760-8436-4090-870d-99ef2121882e
---

The user requires: **all Codex runs use the `sol` model (`gpt-5.6-sol`) at `max` reasoning effort**, driven via the Codex CLI so Codex reads the actual files line-by-line (not gating on evidence I paste).

**Why:** the operator wants the strongest independent check, and Codex's own file-reading (line-by-line) is more trustworthy than Claude summarizing evidence — especially after Claude caused a false-alarm.

**How to apply:**
- Invocation: `codex exec --dangerously-bypass-approvals-and-sandbox -c model_reasoning_effort=max - < promptfile`
- `model_reasoning_effort=max` is valid on gpt-5.6-sol (verified 2026-07-20; also accepts high). Use **max**, not high.
- The `--dangerously-bypass-approvals-and-sandbox` flag is REQUIRED on this box because the kernel blocks Codex's normal bwrap sandbox (namespace error) — without the bypass, Codex cannot open files at all. The user explicitly approved this flag ("yes, bypass OK", 2026-07-20). The auto-mode classifier will block the flag unless approved, so confirm before first use in a new context.
- Codex is authenticated via OAuth on this box (not OpenRouter). Use Codex CLI for gating, not OpenRouter model calls.
- In parallel workflows, give each Codex call a UNIQUE prompt file (e.g. /tmp/codex_<key>.md) — a shared path races and cross-contaminates.

See [[code-review-readiness]].
