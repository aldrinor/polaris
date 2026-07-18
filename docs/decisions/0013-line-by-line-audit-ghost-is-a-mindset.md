# 0013. Line-by-line audit standard; the faithfulness ghost is a mindset; re-audit after every lock

Status: accepted

Date: 2026-05-09

## Context

This is the highest-priority standing standard, flagged as a repeat-violation pattern (2026-05-09) and given its root-cause name on 2026-07-10. It governs how reports and pipeline data are GRADED, which is distinct from the runtime faithfulness engine (ADR 0014). In clinical context the stakes are literal: a pattern-matching audit misses real fabrications, and a patient can be hurt by a wrong dose, contraindication, or indication population that survived a metadata check. "It is lethal" is meant literally.

The "faithfulness ghost" is a MINDSET — judging by count, keyword, pattern, sample, or cherry-pick instead of reading the actual meaning. The operator names this mindset the root cause of months of stalled progress: mechanical judgment gives confident-but-wrong numbers, aims fixes at the wrong target, and never converges.

## Decision

Every audit, evaluation, comparison, benchmark, BEAT-BOTH framing, or quality judgment MUST be:

- claim-by-claim against the actually-fetched cited span text (not title or abstract),
- reasoning-step-by-reasoning-step,
- citation-by-citation,
- with the domain's industrial benchmark applied (PRISMA 2020, AMSTAR-2, GRADE per claim, ICMJE, Cochrane RoB 2 / ROBINS-I / QUADAS-2 for clinical; jurisdiction labels for regulatory),
- ending in a per-claim verdict of VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED / UNREACHABLE with the supporting span quoted.

STRICTLY BANNED as quality signals: word/citation/unique-source counts, pattern presence, sample-based audits, string-match PASS/FAIL, metadata comparison, AND the agent's own count/keyword/string-match judgments about its own data. Before stating ANY quality number, self-check: did this come from reading the meaning, or from counting/matching? If counting, STOP and read.

The moment any section or wheel claims finished or LOCKED, run an INDEPENDENT line-by-line re-audit with a FRESH judge (not the loop that built and self-certified it) that re-reads the section's real output exhaustively, not sampled. The relevance/off-topic judge must see each line WITH its context (surrounding passage, subquery, main question); per-line-isolation judging is forbidden because it over-flags massively.

## Consequences

- Same-meaning equals same claim even in different words; the audit judges meaning, not word overlap, and fails open on doubt (keep).
- The builder never grades its own homework. A wheel's own pass proves the loop THINKS it passed, not that it did — worthless under the clinical-safety bar. Sign-off requires the fresh, exhaustive re-audit.
- Length is a liability, not an advantage: a long, fabrication-laden output is worse than a short, audit-grade one.
- If you propose a metadata or pattern audit, or state a quality number from a count instead of a read, you have failed the standard — even when Claude itself is the one judging.
