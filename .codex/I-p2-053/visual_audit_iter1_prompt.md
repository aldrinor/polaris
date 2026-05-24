# Codex VISUAL audit — I-p2-053 (#853) Workspace memory, A++/S bar — iter 1 of 5

You have VISION. Audit /memory (cred-gated workspace memory). It fetches GET
/workspaces/ws_demo/memory; these screenshots are rendered LOCALLY with a seeded client session +
a Playwright route-mocked FIXTURE (visual-audit only — never shipped; page keeps fetching real
data). Front-load all; don't pick bone from egg; APPROVE iff zero P0/P1.

## What changed (assess-first rebuild — page was already built but raw)
Before: raw <select>/<textarea>/<button>, raw enum strings shown as labels (user_preference, …),
raw bg-blue-500/bg-rose-500 hovers (not even brand), NO loading/error/empty states, no try/catch.
Now:
- design-system shell: Card-wrapped "Remember something" form, labelled Kind select (human labels;
  the option *values* stay the raw enum for the e2e), labelled textarea, brand "Remember" button.
- state-kit loading / error / empty (Brain icon) states added (none existed).
- memory rows are elevated cards with a MEANING-tinted kind chip (preferred=verified-green,
  rejected=refusal, prior-run/preference/assumption=neutral — brand red reserved for the single
  Remember action), short mono id, relative time, "reused N×" (real use_count), and a tokenized
  Forget button (Trash icon, destructive-on-hover).
- "Prior research" card surfaces prior_run_summary entries.

## Attached
1. mem_populated_desktop  2. mem_populated_mobile  3. mem_empty_desktop

## Locked / do NOT flag
- Brand #c8102e (Remember button + global nav active only). Fixture visual-audit-only. LIVE-
  populated verification DEFERRED (real JWT needed; 401-redirects without it) — judge layout/states.
- A prior_run_summary entry appears BOTH in "Prior research" and in the full list — intentional
  (the card is a highlight; the list is the complete memory). The honest "richer pin controls land
  in a follow-up" banner is deliberate.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
per_screen_grades: { populated_desktop: "", populated_mobile: "", empty: "" }
novel_p0: [...]
continuing_p0: []
p1: [...]
p2: [...]
highest_leverage_change_to_S: "..."
convergence_call: continue | accept_remaining
```
APPROVE iff a confident A-tier workspace-memory surface (clean controls, meaningful chips, designed
states), zero P0/P1.
