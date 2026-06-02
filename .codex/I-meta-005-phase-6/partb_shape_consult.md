CODEX MICRO-RULING (Phase 6 Part B implementation shape). You already ruled
B-impl-1: "integrative synthesis = a NORMAL planned section that emits [ev_XXX] and
passes strict_verify; do not retrofit analyst_synthesis." This refines HOW the
Integrative section enters the on-mode plan. One decision.

## Constraint discovered in the code
A TRUE cross-section synthesis needs the OTHER sections' content to integrate —
but a "normal planned section" is generated IN PARALLEL with the others
(`_run_section` per outline item), so it cannot see their verified prose. Two shapes:

- **Shape 1 (parallel planned section):** add an `Integrative` archetype; the
  planner emits an `Integrative` outline item with its OWN allocated cross-cutting
  evidence (the planner assigns broad/overview evidence to it). It is generated +
  strict_verified exactly like any section, in parallel. It synthesizes FROM ITS
  ALLOCATED EVIDENCE (not from the other sections' prose). Fully "a normal planned
  section"; respects pruning automatically (it's in the pruned outline or not);
  counts as verified_words. Weaker "integration" (own-evidence, not cross-section).

- **Shape 2 (post-sections verified synthesis call):** after all sections are
  generated+verified, run ONE more generation fed the full evidence pool + the
  other sections' verified prose, prompted to synthesize WITH [ev_XXX] tokens, run
  through the SAME strict_verify, counted as verified_words, gated on-mode AND
  `not partial_mode` (so it is disabled in partial_saturation exactly like the 5
  appenders → respects pruning). It is NOT analyst_synthesis (new verified path;
  analyst_synthesis demoted). Stronger cross-section integration, but structurally a
  verified "appender" gated to respect pruning rather than an outline item.

## The question
Which shape for Phase 6 Part B? Shape 1 is literally "a normal planned section" (your
words) but gives weaker integration. Shape 2 gives true cross-section synthesis,
stays VERIFIED (strict_verify) + pruning-respecting (gated on not-partial), but is an
"appender-shaped" verified call. HARD constraints either way: verified-only (no
ungrounded sentence in verified_text); OFF byte-identical; respects partial_mode;
analyst_synthesis demoted on-mode; counts as verified_words.

Answer: `shape: 1 | 2` + one-line why + any HARD constraint (e.g. for shape 1: how
the planner must allocate evidence to the Integrative item; for shape 2: the exact
pruning gate).
