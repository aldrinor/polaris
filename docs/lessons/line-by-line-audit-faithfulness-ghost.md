# Lessons: Line-by-line audit standard & the faithfulness ghost (grading discipline)

Canonical home: CLAUDE.md §-1.1 + §-1.1.1; memory `feedback_line_by_line_audit_standard_2026_05_09.md` + `feedback_faithfulness_ghost_is_a_mindset_not_just_code_2026_07_10.md`.

This hub covers how reports and pipeline data are GRADED (distinct from the runtime faithfulness engine). The single loudest lesson in the whole project: judging quality by a number is the ghost, and the ghost is a mindset.

## Never state a quality verdict from a count, pattern, threshold, or sample — read the meaning line-by-line

The ghost is a MINDSET, not just the deleted lexical gate. Judging by exact-word match, field/member count, keyword/pattern presence, a sample, or a cherry-picked example is banned everywhere — including your OWN spoken stats. To answer ANY quality question (single-source rate, junk rate, corroboration, coverage, off-topic, "is it usable"), deploy an Opus (or read it yourself) LINE BY LINE at the CONTEXT level and read the actual meaning. Same-meaning = same claim even in different words; junk only if context-confirmed chrome or off-topic; FAIL-OPEN, so any doubt means keep. Self-check before stating any quality number: did this come from reading the meaning, or from counting/matching? If counting, stop and go read.

Why: The operator named mechanical judgment the root cause of months of stalled progress. A count gives a confident-but-wrong number, aims the fix at the wrong target, and never converges. In a clinical context a metadata or pattern check misses real fabrications, and a patient can be hurt by a wrong dose or contraindication that survived it. "It is lethal" is literal.

Evidence: `feedback_faithfulness_ghost_is_a_mindset_not_just_code_2026_07_10.md` (operator 2026-07-10, triggered by a bare "98% single-source / ~40% junk" field COUNT); CLAUDE.md §-1.1.1; earlier instances FIX-060 (100% faithfulness was a rubber stamp on a too-low NLI threshold 0.65), session 47b (word-count gate scored garbled text 0.82 under average()), FIX-045 (13 audit over-reactions the operator had to correct), I-ready-017 #1170 (a distinct-journal count floor held a healthy corpus).

Recurrence: Recurring across many sessions Feb–July 2026; the strongest and most operator-emphasized theme in the log; the documented origin of CLAUDE.md §-1.1.1.

## Any count-based metric or acceptance target is gameable — gate on a claim-by-claim read against the cited span

Every faithfulness or quality number that survived by counting, pattern-matching, substring presence, or a favorable denominator turned out to be a lie. Know the recurring gaming mechanisms: (a) DELETION — hit a high score by deleting the hard claims; (b) DILUTION — keep uncited-factual sentences out of the denominator; (c) INPUT-not-OUTPUT — measure balance or entropy of the search pile instead of the report; (d) AUTO-PASS — wave short or hedged sentences through at confidence 1.0; (e) SUBSTRING-DEFAULT — a quote-in-source substring match defaults to SUPPORTED without checking the claim over-extends the quote; (f) OFF-TOPIC OVER-EXTRACTION — strip-mine an off-topic source into many off-topic sentences to beat a "distilled count >= legacy" target. The real gate is §-1.1 claim-by-claim faithfulness against the cited span PLUS on-topic relevance, with a per-claim verdict of VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE.

Why: A count is never a quality verdict, even the agent's own count about its own data. Each of these mechanisms produces an excellent-looking number over missing, off-topic, or gamed content, and only a read of the meaning exposes it.

Evidence: `logs/bug_log.md` BUG-025/029 (95.8% on 24 of 43 claims by deletion), BUG-033 (denominator dilution), BUG-074/FIX-131 (entropy measures balanced input), BUG-022 (auditor audited 37% of sentences, short-sentence auto-pass), BUG-068 (sentence verdict always wins, 30–40% inflation), BUG-069 (heuristic FactScore = word-pattern count), LIMITATION-001 (97.7% is self-graded, no ground truth); `keystone_collapse_forensic_consolidated.md` PART 4 land-mine 3 (19 off-topic sentences beat a count target); CLAUDE.md §-1.1 / §-1.1.1.

Recurrence: Recurring — 8+ occurrences; the highest-priority standing audit rule.
