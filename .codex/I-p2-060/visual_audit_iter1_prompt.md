# Codex VISUAL audit — I-p2-060 (#???) Offline Inspector dropzone — FRONTIER bar — iter 1 of 5

You have VISION. Audit /inspector/offline — the disconnected-reviewer entry: drop a signed .tar.gz
bundle → it's SHA-256-verified + rendered fully in-browser (no backend/GPU). The LOADED state reuses
the already-S-tier InspectorView (verified at #833, not re-audited here). This audit is the ENTRY
(dropzone) state. Rendered live (no mock — client page). Front-load all; APPROVE iff zero P0/P1.

## What changed (assess-first)
The dropzone was a plain text-only `rounded border-2` box with a raw `bg-rose-500` error block.
Now: crafted drop zone (UploadCloud icon, drag-active brand-tint border-primary/50 bg-primary/5,
hover, ease-standard motion, rounded-xl) with a loading "Verifying bundle… checking SHA-256" state
(FileCheck2), and the error path now uses the shared ErrorState (tokens) instead of raw rose.

## Attached
1. offline_default_desktop  2. offline_mobile

## Locked / do NOT flag
- Brand #c8102e = drag-active accent only. Honest copy: SHA-256 checked, GPG verify explicitly
  out-of-scope (needs a CLI) — deliberate LAW II framing. Drag-active + loading + error states are
  interaction states (only default shown statically). Loaded state = InspectorView (separate, A-tier).

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { default_desktop: "", mobile: "" }
novel_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```
APPROVE iff a confident A-tier entry surface, zero P0/P1.
