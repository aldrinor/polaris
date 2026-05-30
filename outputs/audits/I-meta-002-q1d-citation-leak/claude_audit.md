# Claude architect audit — PR7: scrub bare [ev_NNN] citation-leak tokens (#946)

**Issue:** #946 (q1c-5, clinical-deliverable defect). **Branch:** `bot/I-meta-002-q1d-citation-leak`.
**Both Codex gates APPROVE iter-1** (brief + diff, zero P0/P1/P2). **NO SPEND** — pure regex + tests.

## What this fixes

Codex-verified clinical-deliverable defect (#941): the Analyst Synthesis scrub regex
`_EV_TOKEN_RE = \[#ev:[^\]]*\]` matched only the prefixed audit token `[#ev:<id>:<start>-<end>]`, NOT a bare
`[ev_012]`. A dangling `[ev_012]` consequently leaked into a published `report.md` — an unresolved citation
token visible to the reader in a clinical deliverable.

## The fix (small, single chokepoint)

`_EV_TOKEN_RE` → `\[#?ev[:_][^\]]*\]`. The `[:_]` after `ev` is the precision guard: it matches `[#ev:...]`
(prefixed) AND `[ev_012]` / `[ev_012:1-5]` (bare), while leaving numeric `[N]` citations and ordinary
bracketed words (`[event]`, `[evidence]`) untouched (their next char is a letter, not `:`/`_`). The scrub
runs at the single existing chokepoint `_scrub_ev_tokens` (analyst_synthesis.py:476), applied to the
synthesis text before report assembly — there is no separate report-level guard, so this closes the leak
into `report.md`. Scrub (not resolve) is correct: the synthesis layer cites by bibliography `[N]` only, so
any ev-token there is always a leak, never a resolvable citation. Docstring + WARN message updated.

## Untouched (verified core)

`[N]` marker handling (`_scrub_invalid_n_markers`), strict_verify, the provenance core, and the
verified-findings layer's internal `[#ev:...]` → `[N]` conversion are all unchanged.

## Tests (44 pass, NO SPEND)

6 NEW (test_analyst_synthesis.py): bare `[ev_012]` scrubbed; bare-with-span `[ev_007:12-48]` scrubbed;
mixed prefixed+bare both scrubbed; ordinary `[event]`/`[evidence]`/`[1]`/`[2]` PRESERVED; no dangling
`[ev_`/`[#ev` substring survives. Plus the existing 38 (analyst_synthesis + analyst_synthesis_safety) — no
regression.

## Verdict

Scrubs bare `[ev_NNN]` (+span) at the existing synthesis chokepoint, preserves `[N]` and ordinary bracketed
words, is covered by offline tests asserting no dangling ev-token survives, and leaves the verified core
untouched. Both gates APPROVE iter-1. Ready to queue for operator merge (Option A — no spend).
