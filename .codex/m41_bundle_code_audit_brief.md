You are auditing the M-41 BUNDLE (4 coordinated V24 regression
fixes) as a code review. Per user autoloop rule, one Codex audit
covers all 4 parts; if blockers are found in any sub-fix, the
bundle is BLOCKED until resolved.

## Scope discipline

Audit ONLY the M-41 diff (commit at HEAD of PL-honest-rebuild-phase-1).
Four coordinated changes addressing V24's Codex pass-12 REGRESSED
verdict:

- **M-41a**: outline cap 5 → 6 (prompt + parser). File:
  `src/polaris_graph/generator/multi_section_generator.py` lines
  ~156 (OUTLINE_SYSTEM_PROMPT rule) + ~298 (parser validation).
- **M-41b**: drop trial summary table rows with >2 dashes. File:
  same as M-41a; `_extract_trial_summary_table` inner row loop.
- **M-41c**: deterministic claim-frame post-check. File: same;
  new functions `_m41c_sentence_names_trial`,
  `_m41c_frame_element_count`, `filter_underframed_trial_sentences`.
  Wired into `_run_section` after strict_verify.
- **M-41d**: evidence-selector jurisdictional floor for T3. File:
  `src/polaris_graph/retrieval/evidence_selector.py`. New
  `_row_jurisdiction()` + logic in the within-tier picker.

Test file: `tests/polaris_graph/test_m41_v24_regression_fixes.py`
(26 tests).

Do NOT re-audit M-30..M-40 behavior — those are held constant.

## Context

### V24 Codex pass-12 verdict: REGRESSED

V23 → V24 net -1 dimension:
- Regulatory BEAT_ONE → LOSE_BOTH (Mechanism displaced it)
- Jurisdictional BEAT_ONE → LOSE_BOTH
- Narrative depth LOSE_BOTH → BEAT_ONE (Mechanism)
- Others held.

### Root cause

M-40 mandated Mechanism section. M-25b capped outline at 5.
Outline LLM dropped Regulatory to make room. Cascading: M-37
Health Canada work stranded (no Regulatory section → no HC
citations); M-35 primary papers not prioritized by selector;
M-38 claim-frame rule was probabilistic prompt-only.

### Smoke test evidence (already committed in commit message)

1. M-41a: OUTLINE prompt compiles + exposes 6-section rule
2. M-41b: V24's literal thin rows (4 dashes) dropped; SURMOUNT-4
   meaningful row kept
3. M-41c: V24's literal under-framed "pooled analysis of SURPASS-2
   and -3" sentence dropped (1 frame element); V24's fully-framed
   SURPASS-2 sentence kept (7 frame elements)
4. M-41d: HC slot reserved in T3 selection even though HC scored
   lowest on relevance (6 FDA / 4 EMA / 1 NICE / 1 HC input → all
   4 jurisdictions represented in output of 8 slots)

## Files to read

```
src/polaris_graph/generator/multi_section_generator.py
  - OUTLINE_SYSTEM_PROMPT M-25b+M-41a rule (~line 156-157)
  - `_parse_outline` cap bump 5 → 6 (~line 297-302)
  - `_extract_trial_summary_table` dash-cell drop (inside row loop)
  - `filter_underframed_trial_sentences` + helpers (new section)
  - `_run_section` wiring (calls filter after strict_verify)

src/polaris_graph/retrieval/evidence_selector.py
  - `_M41D_JURISDICTION_HOSTS` + `_row_jurisdiction`
  - within-T3 picker: reserve one slot per present jurisdiction

tests/polaris_graph/test_m41_v24_regression_fixes.py (NEW)
```

## What to verify

1. **M-41a interaction with M-25b**. Old rule said "EXACTLY 5
   sections"; new rule says "5 by default, 6 when both Mechanism
   and Regulatory trigger". Is the rule unambiguous to the LLM?
   Does it prevent the outline from emitting 6 sections when
   only 4 have enough evidence (i.e., Mechanism forced
   but another section's <8 ev_ids)? The rule says "If the
   corpus supports 6 sections (at most 1 section would otherwise
   have <8 ev_ids)" — check that wording.

2. **M-41a parser 6-cap**. The truncation of >6 sections now
   keeps the first 6 (was first 5). Does this change any
   downstream assumption? Scan for hard-coded "5 sections" or
   "plans[:5]" in the codebase.

3. **M-41b dash-cell counter**. The logic splits the row on
   `|` and trims leading/trailing empty cells. For a row
   "| a | b | c |" this yields `['a', 'b', 'c']`. Is the 2-dash
   threshold too strict (drops rows with partial data) or too
   lenient (keeps rows where the critical cells are dashes)? The
   header has 7 columns; 2 dashes allowed = 71% cells populated.
   Any edge case with trailing whitespace or unicode dash
   variants? (Current set: em-dash U+2014, hyphen, en-dash
   U+2013, N/A, NA, empty.)

4. **M-41c trial-name regex false positives**. `[A-Z][A-Z0-9]{2,}-\d+`
   matches many ALL-CAPS-digit tokens. A sentence mentioning
   "ISO-9001" or "NCT03987023" (ClinicalTrials.gov ID) could
   match. False positives drop legitimate sentences. Is the
   regex tight enough?

5. **M-41c frame-element counter precision**. Each regex is
   permissive by design. A sentence containing "baseline" with
   unrelated context (e.g., "baseline configuration") still
   counts. Is this acceptable? What about "dose" in unrelated
   context? Check if any of the 7 pattern classes are too loose.

6. **M-41c interaction with strict_verify retry**. The retry
   path in `_run_section` keeps `report2` if it has more
   `total_kept` than `report1`. But M-41c runs AFTER the retry
   decision. Could a run where retry's report has more strict-
   verified sentences actually produce FEWER sentences after
   M-41c (if most of the retry's extras are under-framed)?

7. **M-41d T3 jurisdictional floor behavior under quota pressure**.
   When quota < number of present jurisdictions, the floor code
   reserves as many as fit (slots_left tracked). Is the order
   stable across runs? (Iteration over dict in insertion order —
   Python 3.7+ guarantees. Input order is the scored list. Stable.)

8. **M-41d T3 jurisdictional floor + M-25b T3 floor interaction**.
   M-25b already guaranteed 1 slot for T3 when T3 is present.
   M-41d now sub-divides that slot further. If T3 gets exactly 1
   slot from the tier quota, the jurisdictional floor still wants
   1 slot per jurisdiction — conflict. Does the code degrade
   gracefully? (Should: slots_left = quota = 1, one jurisdiction
   picked, loop breaks.)

9. **Generalization discipline**. M-41c regexes include clinical
   vocabulary (HbA1c, MACE) but also non-clinical (cycle-life,
   phase-transition, reaction-yield). M-41d host list is
   regulatory-jurisdiction agnostic. Any drug-specific hardcode?

## What counts as a blocker vs medium

- **BLOCKER**: crash on valid input; a path where the rule
  silently produces worse output than pre-M-41; a contradictory
  rule interaction (e.g., M-41a + M-25b produce no valid plan
  for a corpus that V23 handled); any test that fails.
- **MEDIUM**: tightening suggestions (trial-name regex
  specificity, frame-element pattern tightness), additional
  smoke scenarios, telemetry gaps (M-41c doesn't emit to
  manifest).
- **LOW**: wording, comments.

## Deliverable

Write `outputs/codex_findings/m41_code_audit/findings.md` with:
- Final verdict (READY | BLOCKED | CONDITIONAL)
- Blockers (zero if READY)
- Mediums
- One-sentence note per sub-fix (a/b/c/d) on whether it
  closes the intended V24 regression dimension.
