HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; non-blockers are P2/P3.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

RULE NOW — emit the YAML verdict block FIRST. APPROVE this CONCRETE plan or REQUEST_CHANGES with specifics.
Small clinical-deliverable report-hygiene fix. NO SPEND (pure regex + tests, offline).

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex brief-gate (iter 1) — PR7: scrub bare [ev_NNN] citation-leak tokens (#946)

Codex-verified clinical defect (#941): the Analyst Synthesis scrub regex matches only `[#ev:...]`, NOT bare
`[ev_NNN]`; a dangling `[ev_012]` leaked into a published `report.md`. The synthesis layer must cite by
bibliography `[N]` markers ONLY — any `ev`-token (prefixed `[#ev:...]` OR bare `[ev_012]`) is a leaked
audit-grade signal and must be scrubbed.

## GROUNDED FACTS (verified; do not re-explore)
- `src/polaris_graph/generator/analyst_synthesis.py:108` `_EV_TOKEN_RE = re.compile(r"\[#ev:[^\]]*\]")` —
  matches the prefixed token `[#ev:<id>:<start>-<end>]` but NOT bare `[ev_012]` / `[ev_012:1-5]`.
- `_scrub_ev_tokens(text)` (`:324-338`) applies `_EV_TOKEN_RE.subn("", text)` + WARNs on n>0. It is the
  SINGLE chokepoint: called ONCE at `:476` on the synthesis `text` BEFORE `_scrub_invalid_n_markers` and
  before the section is returned for report assembly. There is NO separate report-level ev-token guard in
  `run_honest_sweep_r3.py` (grep clean), so fixing this regex closes the leak into `report.md`.
- Legitimate citation markers are `[N]` (numeric, e.g. `[1]`, `[12]`) — handled by `_N_MARKER_RE` /
  `_scrub_invalid_n_markers` and MUST be preserved.

## Files I have ALSO checked and they're clean
- `scripts/run_honest_sweep_r3.py` — no other ev-token emission/scrub into report.md (only `[#ev` in a
  generator-no-tokens diagnostic string at :331; bibliography render at :2989; no bare `[ev_` leak path).
- `tests/polaris_graph/test_analyst_synthesis.py` — `test_scrub_removes_single_ev_token` (:108),
  `test_scrub_removes_multiple_ev_tokens` (:115), `test_scrub_preserves_n_bibliography_markers` (:123) —
  the [#ev:...] + [N]-preservation coverage I will extend, not duplicate.

## CONCRETE PROPOSAL (small)
1. Extend the regex to catch BOTH forms in one pass:
   `_EV_TOKEN_RE = re.compile(r"\[#?ev[:_][^\]]*\]")` — the `[:_]` after `ev` is the guard so it matches
   `[#ev:...]` (prefixed) and `[ev_012]` / `[ev_012:1-5]` (bare) but NOT `[event]`/`[evidence]` (next char
   is a letter, not `:`/`_`) and NOT `[N]` numeric markers (no `ev`).
2. Update `_scrub_ev_tokens` docstring + the WARN message to say "ev-token ([#ev:...] or bare [ev_NNN])".
3. Tests (extend `test_analyst_synthesis.py`): bare `[ev_012]` scrubbed; `[ev_012:1-5]` scrubbed; mixed
   `[#ev:...]` + `[ev_012]` both scrubbed; `[N]` markers + ordinary text (`[event]`, the word "level")
   PRESERVED; no dangling `ev`-token substring (`[ev_` / `[#ev:`) survives the scrub.

## Constraints / frozen
snake_case; explicit imports; no except:pass. Untouched: `[N]` marker handling, strict_verify, provenance
core, the verified-findings layer's internal `[#ev:...]` → `[N]` conversion. ≤30 LOC. NO SPEND.

## The real risks to rule on
1. Does `\[#?ev[:_][^\]]*\]` over-match any legitimate token? (Claim: no — requires `ev` + `:`/`_`; `[N]`
   and the words `event`/`level`/`evidence` are untouched.)
2. Is `_scrub_ev_tokens` truly the only path bare `[ev_NNN]` can reach `report.md` (so a unit test on it is
   the right no-spend assertion), or is a higher report-level guard also needed?
3. Any case where a bare `[ev_NNN]` SHOULD be resolved to `[N]` rather than scrubbed? (Claim: no — the
   synthesis layer cites by `[N]` only; an ev-token there is always a leak, never a resolvable citation.)

APPROVE iff this scrubs bare `[ev_NNN]` (and `[ev_NNN:...]`) at the existing synthesis chokepoint, preserves
`[N]` markers and ordinary `ev`-prefixed words, is covered by offline tests asserting no dangling ev-token
survives, and leaves the verified core untouched.
