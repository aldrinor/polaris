# 0008. Junk-deletion carve-out: delete only chrome and confirmed off-topic sources, fail-open, disclosed

Status: accepted

Date: 2026-07-09

## Context

ADR 0006 says never DROP a source, only weight it. But weighting genuine junk to zero is not enough: a zero-weight row still sits in the evidence pool, the bibliography, and the corroboration counts, where it pollutes a clinical report — a bot page rated T1, a predatory PDF counted eighteen times. Weight-0 does not equal clean. Operator-authorized (2026-07-09, I-deepfix-003 #1374, `CLAUDE.md` §-1.3.1).

## Decision

The never-DROP rule is lifted for exactly two junk classes:

- (a) Chrome non-sources — bot/captcha/cookie/login/404/"not found"/empty pages. These are failed fetches, not sources.
- (b) Whole sources a SEMANTIC topic judge confirms are off-topic to the research question.

Deletion is by judge verdict ONLY, FAIL-OPEN (any uncertainty means KEEP), never by tier, lexical guess, or a breadth number. An off-topic SPAN inside an on-topic source drops the span and keeps the source. Every deletion is DISCLOSED — deleted-row count plus reason in Methods, fail loud, never silent.

## Consequences

- Credible ON-TOPIC sources, even low-tier, social, or non-journal, are NEVER deleted, only weighted. The carve-out must never touch them — that would be the banned filter-and-cap returning by the back door.
- The carve-out is deliberately narrow and fail-open precisely so it cannot become a backdoor for the number-forcing drops that ADR 0006 bans. Deletion is triggered ONLY by content-integrity (chrome) or a semantic off-topic verdict.
- Disclosure is mandatory: the report states what was removed and why, so a reader can audit the deletion, and a silent purge is itself a defect.
- The semantic topic judge is now a required component; a lexical or tier-based shortcut for off-topic detection is explicitly forbidden.
