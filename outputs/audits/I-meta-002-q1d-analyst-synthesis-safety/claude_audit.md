# Claude architect audit — PR3 analyst-synthesis safety hardening (#953 q1d-c, CLINICAL-SAFETY)

## What this fixes (Codex-verified S1 — clinical-safety hole shipping in ~70% of report.md)
The Analyst Synthesis layer (the explicitly-UNVERIFIED ~70% of the shipped report) was (a) built from RAW
`<<<evidence>>>` blocks with NO `sanitize_evidence_text` — a §9.1.7 delimiter/injection BYPASS the verified
path doesn't have — and (b) only syntactically scrubbed (`[#ev]`/`[N]`), so the lethal fabrication class
already caught on a real smoke ("did not lead to discontinuation" contradicting evidence) could ship under
an "evidence-grounded" disclosure. Codex flagged it to promote early.

## Design (both Codex gates APPROVE; diff iter 2)
- **Evidence sanitization** — `_format_evidence_pool_for_prompt` routes BOTH the quote and the evidence_id
  through `sanitize_evidence_text(...)` (injection directives + delimiter literals + NFKD/invisible/
  homoglyph evasions), and the closing delimiter changed from bare `<<<end>>>` to `<<<end_evidence>>>` —
  the SAME delimiter the verified `wrap_evidence_for_prompt` uses and that the sanitizer redacts (a forged
  bare `<<<end>>>` was NOT in the redaction set; a forged `<<<end_evidence>>>` now IS). Redactions →
  `synthesis_evidence_redaction_count`.
- **Qualitative-negation SAFETY screen** — `_screen_qualitative_negations` (pure, no-network) operates PER
  LINE (preserving `###` headings + blank lines + paragraphs); within a prose line, an abbreviation-masked,
  decimal-safe splitter yields sentences, and any sentence matching BOTH a negation cue AND a safety/
  clinical-consequence term is DROPPED fail-closed. Runs after the syntactic scrubs, before return; counts
  → `synthesis_negation_dropped_count` + WARNING log. The span-verified core above is untouched.
  - Codex diff iter-1 P1 fix: safety terms use suffix handling (`hospitali\w*`, `contraindicat\w*`,
    `toxicit\w*`, `pregnan\w*`, `teratogen\w*`, `side\s+effects?`, `discontinu\w*`, `deaths?`, `harm\w*`,
    `warning\w*`, `fatal\w*`, `withdraw\w*`, `interaction\w*`, `black[-\s]?box\w*`) — truncated stems wrapped
    by `\b` previously failed to match the full inflected words. Negation cues broadened (bare `no`/`not`/
    `n't` + never/without/absent/none/neither/nor/lack/free of/fail to) so "not contraindicated" is caught.
- **Operator kill-switch** — `generate_analyst_synthesis` checks `PG_SWEEP_ANALYST_SYNTHESIS` (default "1")
  FIRST, before the openrouter import / prompt build / model call (so disabling avoids spend), returning
  `("", 0, 0)` (caller omits the section → span-verified core only).

## Verification (offline, no spend)
- 10 new safety tests + 29 existing analyst tests = 39 PASS, incl. the Codex-required inflected/plural
  variants ("did not lead to hospitalization", "no toxicity", "not contraindicated", "no pregnancy risk",
  "no side effects", "teratogenic"); benign + positive ("discontinuation occurred in 0.3%") + negation-
  without-safety KEPT; markdown structure preserved; decimal/`e.g.` not shredded; forged delimiters
  redacted; kill-switch returns "" with no model call; determinism.
- `verify_lock --consistency` OK. Both Codex gates APPROVE (brief iter-1 clean; diff iter 2).
- Frozen/untouched: strict_verify / provenance_generator's VERIFY path / D8 / runtime lock / the 5 PR-10
  contracts / the verified multi_section core. This only HARDENS the unverified layer (sanitize +
  drop-dangerous + kill-switch), never loosens anything.

## Clinical-safety note
Fail-closed throughout: over-drop only removes UNVERIFIED sentences (the verified core retains any real
finding); the kill-switch lets the operator ship the span-verified core alone. The §9.1.7 injection defense
now covers the analyst layer too.
