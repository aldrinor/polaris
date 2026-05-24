# Claude architect audit — I-p2-060 (#867): Offline Inspector dropzone S-audit

## Goal
Final secondary page in the post-journey frontier pass: /inspector/offline — the disconnected-
reviewer entry (drop a signed .tar.gz → SHA-256-verified + rendered fully in-browser, no backend or
GPU). The LOADED state reuses the already-S-tier InspectorView (#833), so this audit targets the
ENTRY (dropzone) state. Client page → live-verifiable; rendered directly.

## What looking-at-it found
The dropzone was a plain text-only `rounded border-2 border-dashed` box (no icon, no real
drag-active treatment) and the error path used a raw `bg-rose-500/5 text-rose-700` block — the same
raw-palette + uncrafted-state gaps fixed elsewhere.

## What changed (1 page file + tracker)
- Crafted drop zone matching the /upload bar: UploadCloud icon, drag-active brand-tint
  (border-primary/50 bg-primary/5), hover, ease-standard motion, rounded-xl, and a "Verifying
  bundle… checking SHA-256" loading state (FileCheck2, pulse, motion-reduce-safe).
- The raw-rose error block → the shared ErrorState (design tokens, role=alert).

## Preserved
The keyboard-operable dropzone (role=button + tabIndex + Enter/Space), the hidden file input,
handleFile/onDrop/onInputChange, loadBundleFromTarGz, the honest SHA-256-checked /
GPG-verify-out-of-scope copy, and the testids (inspector-offline, -dropzone, -file-input, -error).

## Dual Codex gate
- Brief APPROVE. Visual `-i` APPROVE iter-1 (default desktop A / mobile A-). Code diff APPROVE.
- Residual P2 (accept_remaining): drag-leave can briefly clear the drag-active style when the
  cursor crosses the new icon/label descendants — visual flicker only; the drop works. (The
  /upload page solved the analogous case with a drag-depth counter; a follow-up could mirror it.)

## Verification state
Live-verifiable (client page, no API) — rendered at /inspector/offline. The loaded-bundle state =
InspectorView, verified at #833.

## Constraints honored
Brand `#c8102e` (drag-active accent only); tokens only; a11y dropzone + logic + honest copy +
testids preserved; no fabricated data.

canonical-diff-sha256: fc59b62b0bf4337b823a7a5a4c3df55eefa7e1268abee64d57ed52ea77cbfabc
