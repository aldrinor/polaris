# Claude architect audit — I-p2-042 (#831): S-tier foundation tokens

## What
S-tier redesign build-order step 1: globals.css @theme +--ease-standard (one motion
primitive) + --shadow-card/-hover (brand-temperature elevation, locked #c8102e); Card
primitive gains shadow-card + transition; canonical docs/web/s_tier_design_system.md +
file_directory ref. Type/spacing/color already tokenized; brand red operator-locked (kept).

## Dual gate (code + the operator-required VISUAL)
- Codex brief APPROVE (iter 2) + diff APPROVE (1 non-blocking tailwind-merge P2).
- Codex VISUAL -i: iter1 REQUEST_CHANGES (red wash too decorative on stacked cards) →
  tuned red −30% + more blur → iter2 APPROVE ("ambient warmth, not decoration; ships").
- build + eslint + prettier green (incl. the doc).

## Residual / follow-up
- visual_60 baselines need --update-snapshots (intentional global shadow; non-required lane).
- tailwind-merge won't collapse shadow-card vs a shadow-* override (no current caller does).
- This is foundation plumbing (subtle). Visible S-tier wins are the per-page rebuilds
  (Inspector-first), proof-as-visual-OS — the continuing program.
