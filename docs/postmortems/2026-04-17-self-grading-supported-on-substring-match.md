# Postmortem: Self-grading inflation — SUPPORTED defaulted from a substring match

- **Date:** 2026-04-17
- **Theme:** faithfulness
- **Severity:** P0 (inflated verdicts became the pipeline's ground truth)
- **Evidence:** `logs/bug_log.md` BUG-LB-SELF-GRADE-INFLATION; `scripts/_lb_process_pg_lb_sa_02.py`; `loopback/_honest_audit.txt` (649-line claim-by-claim record)

## What happened

The system was tasked to act as the honest verifier for 20 claims. The
verification heuristic checked whether each claim's `direct_quote` substring-
matched the source text, and if it did, defaulted the verdict to SUPPORTED with
no further adversarial check. It never compared the claim STATEMENT — which
over-extended past the quote — against the source.

It submitted 18 SUPPORTED / 2 PARTIAL / 0 NOT_SUPPORTED. An honest post-hoc
review (the 649-line record) found that roughly half should have been
NOT_SUPPORTED, including:

- a fabricated dose (2.8 mg QW) not in the source,
- a fabricated number of studies,
- a category mismatch — the claim said "serious" where the source said
  "gastrointestinal."

The inflated verdicts were consumed downstream before the error was caught.

## Root cause

Substring presence of a quote is not a verdict. The claim statement can say more
than the quote it cites; a quote can be genuinely present while the claim built
on top of it is fabricated or mis-categorized. The heuristic checked the wrong
object (quote-in-source) instead of the load-bearing one (statement-vs-source),
and it let the same system grade its own output as ground truth — a self-grading
feedback loop that inflates by construction.

## Contributing factors

- The verdict defaulted to SUPPORTED on a weak signal, so the burden of proof
  ran the wrong way; a verifier should have to earn SUPPORTED, not fall into it.
- Numbers and categories were never checked digit-by-digit or
  category-by-category, so fabricated doses and counts survived.
- The producing system also graded itself, with no independent audit between
  the verdict and its consumption downstream.

## Lessons (promoted to)

- A verifier must check the claim STATEMENT against the source digit-by-digit
  and category-by-category. Substring presence of a quote is never a verdict,
  and the same system must never grade its own output as ground truth.
- This is the concrete instance the standing metadata-audit ban is built on.
  Promoted to CLAUDE.md §-1.1 (line-by-line audit standard: claim-by-claim,
  citation-by-citation, per-claim VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED
  / UNREACHABLE; string-presence and pattern checks BANNED) and §-1.1.1
  (the faithfulness ghost is a mindset: judge by meaning, never by match/count).
- Promoted to memory: `feedback_line_by_line_audit_standard_2026_05_09.md` and
  `feedback_faithfulness_ghost_is_a_mindset_not_just_code_2026_07_10.md`.
- Reinforces the standing rule that an independent line-by-line audit runs after
  every stage — the builder never grades its own homework
  (`feedback_independent_line_audit_after_every_wheel_lock_2026_07_10.md`).
