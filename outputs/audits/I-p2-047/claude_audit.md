# Claude architect audit — I-p2-047 (#841): Upload page S-rebuild

## Goal
Push /upload from C+ (plain dashed drop zone, no drag feedback, empty lower half) to an A-tier
upload surface — and keep every claim honest (LAW II).

## What changed (3 files)
- `web/app/upload/components/upload_drop_zone.tsx`: UploadCloud icon; a real drag-active state
  (brand-tinted border/bg/icon + "Drop to upload" label) via a drag-depth useRef counter (Codex
  P2 — avoids onDragLeave child-flicker; onDragOver keeps preventDefault); idle hover +
  focus-visible ring + motion primitive. Upload error tokenized (text-rose-700 → text-destructive).
- `web/app/upload/page.tsx`: an honest 3-step band (Drop → Parsed into chunks → Preview the
  result) + a neutral /intake link. Title/subtext/metadata reworded to claim only what's true.
- `docs/web/s_tier_design_system.md`: Upload grade.

## LAW II honesty (the Codex diff gate's two catches — both correct, both fixed)
- **P1 (iter 1): false intake-grounding.** My first band claimed "Grounds your questions /
  include uploads as evidence when you ask a question" + a CTA "Ask a question with your
  uploads" — but selected upload IDs never leave /upload (runs start with `document_ids: []`),
  so the flow would silently discard uploads. Removed: step 3 → "Preview the result" (preview
  IS real via `open-preview-*`); CTA → neutral "Ask a research question". Also corrected the
  PRE-EXISTING subtext's same false "ground intake queries" claim.
- **P1 (iter 2): metadata.** `metadata.description` still said "Upload documents for grounding"
  — fixed to preview/chunk-inspection framing. Grep confirms ZERO grounding claims remain
  (band, CTA, subtitle, title, metadata).
- **P2 (iter 1): overbroad parse.** "POLARIS extracts the text and splits each document" →
  "Supported documents are split into retrievable chunks" (only md/txt parse today; PDF/DOCX
  queue). No claim that PDF/DOCX parse.
- Noted out-of-scope: the pre-existing `include-toggle-*` / SelectedDocsIndicator selection is
  non-functional plumbing (selection never reaches a run) — pre-existing backend wiring, not
  introduced here; this PR only stops the NEW copy from asserting grounding works.

## Preserved
`upload-dropzone` (role=button + handlers + sr-only input) + every testid; upload/poll/parse
logic + DocumentPreview untouched.

## e2e
upload_g1_g8 4/4 pass. dropzone/parse specs need the upload backend (not up in dev) — unchanged.

## Dual Codex gate
- Brief APPROVE (iter 1). Visual `-i` APPROVE (iter 1: desktop A / drag-active A+ / mobile A).
- Code diff: iters 1-2 caught the false grounding claims (LAW II); iters 1-4 progressively scrubbed every false grounding/over-parse claim; iter 5 APPROVE on the honest copy (final) — `.codex/I-p2-047/codex_diff_audit.txt`.

## Constraints honored
Brand `#c8102e` untouched; tokens only; logic/testids preserved; no test relaxation; honest
copy only.

canonical-diff-sha256: d531067baeab732e32b0d97fbb3c6190cb06d30dfa7d73c1309c4a32d00d4fba
