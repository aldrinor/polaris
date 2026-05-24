# Claude architect audit — I-p2-053 (#853): Memory page S-audit

## Goal
Third cred-gated page (build-order step 5): /memory (workspace memory). Live it 401-redirects
without a real reviewer JWT. Audited by rendering locally (seeded session + route-mocked
/workspaces/ws_demo/memory fixture) to SEE every state. Fixture is visual-audit-only — never shipped.

## What looking-at-it found
This was the rawest of the cred-gated pages — closer to a dev console than a reviewer surface:
- Raw <select>/<textarea>/<button>, with the raw enum strings shown verbatim as labels
  ("user_preference", "domain_assumption", …) — internal vocabulary leaking into the UI.
- Raw Tailwind palette hovers (bg-blue-500/10, bg-rose-500/10) — bg-blue isn't even a POLARIS
  brand color.
- NO loading / error / empty states and NO try/catch: a failed listMemory was an unhandled
  promise rejection; an empty workspace was a blank page.

## What changed (1 file, full view rewrite)
- Design-system shell: a Card-wrapped "Remember something" form — labelled Kind select showing
  human labels (the <option> VALUES stay the raw MemoryKind so the e2e selectOption("rejected_
  source") still works), a labelled textarea, and the brand "Remember" button.
- A LoadState machine (loading / ok / error) with try/catch, rendering the shared state-kit
  (LoadingState / ErrorState / EmptyState with a Brain icon).
- Memory rows as elevated cards: a meaning-tinted kind chip (preferred source = verified-green,
  rejected source = refusal-neutral; preference / domain-assumption / prior-run = neutral — brand
  red is reserved for the single Remember action), a 3-line layout (chip + Forget / content /
  mono short-id · relative date · "reused N×" from the real use_count), and a tokenized Forget
  button (Trash icon, destructive-on-hover). A "SAVED MEMORY · N" heading anchors the list.
- Mobile: textarea no longer clips its placeholder; row metadata no longer squeezed (Codex
  visual iter-1 P1 + P2s).

## Preserved
WS = "ws_demo"; the real listMemory / rememberMemory / forgetMemory calls; the >=4-char save gate;
the option VALUES (raw enum); and all testids (memory-page, memory-banner, memory-save-kind,
memory-save-content, memory-save, memory-list, memory-row-*, memory-forget-*, recent-runs,
recent-run-*). The memory_page_controls e2e contract (save adds row, forget removes it) is intact.

## Honest framing
The banner keeps the honest caveat ("Save and forget are live … richer pin controls land in a
follow-up release"). "reused N×" and the relative date come from real entry fields. No fabricated
SHIPPED data — the visual-audit fixture is not committed.

## Dual Codex gate
- Brief APPROVE. Visual `-i` APPROVE iter-2 (desktop A / mobile A- / empty A). Code diff APPROVE.

## Honest verification state
LIVE-populated verification on polarisresearch.ca is DEFERRED — the page 401-redirects without the
real reviewer credential. States verified against a route-mocked fixture (visual audit only) + the
natural empty state.

## Constraints honored
Brand `#c8102e` (Remember only); tokens only; logic/testids/save-gate/option-values preserved; no
fabricated SHIPPED data; no test relaxation.

canonical-diff-sha256: 8844a3f68e2f7f50da36a90fe634694815f1bc3457fac1a11be84616cb3978cd
