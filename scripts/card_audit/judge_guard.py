#!/usr/bin/env python3
"""The entailment-judge ERROR-SENTINEL guard (Sol Phase 8 additional attack: "a side-judge
`("ENTAILED", "judge_error: ...")` sentinel, which must map to uncertainty rather than admission").

`report_ast.entailed_by_span` consults `report_ast._semantic_judge`, which folds the judge's reply
through `report_ast._canon_verdict`. That fold reads ONLY the verdict token: a judge that returns
`("ENTAILED", "judge_error: transport blew up")` is admitted, because `_canon_verdict('ENTAILED')` is
`ENTAILED` and the `why`/excerpt string is never inspected. A judge that self-reports an error while
still saying ENTAILED is therefore an admission the audit must NOT trust.

This guard does NOT reinvent faithfulness and does NOT modify `report_ast` (Sol §1: reuse the entailment
judge; the task forbids touching report_ast.py). It is a thin WRAPPER the audit installs AROUND whatever
entailment judge is wired: it downgrades an `ENTAILED`-with-error reply to `UNCERTAIN`, which
`entailed_by_span` already rejects (fail-closed). A genuine `ENTAILED` with a normal deciding excerpt is
passed through unchanged, so a healthy judge still admits the true finding.

GENERALITY (Sol Phase 8): there is not one DOI, subject, venue, or benchmark literal here. The guard
fires on the STRUCTURE of the reply (verdict token + error marker in the excerpt), never on content.
"""
from __future__ import annotations

import report_ast as RA

# Markers a judge only emits when it could not actually decide — an admission carrying any of these is a
# masked failure, not a real ENTAILED. Matched case-insensitively as substrings of the deciding excerpt.
_ERROR_MARKERS = (
    'judge_error', 'judge error', 'exception', 'traceback', 'fail closed', 'fail-closed',
    'unavailable', 'timeout', 'timed out', 'transport', 'internal error',
)

# The affirmative verdict tokens `report_ast._canon_verdict` would fold to ENTAILED (so the guard catches
# every surface form that would admit, not just the literal word "ENTAILED").
_ADMIT_TOKENS = frozenset({'ENTAILED', 'MATCH', 'YES', 'TRUE', 'ENTAILS'})


def guard_entailment_judge(inner_judge):
    """Wrap an entailment judge `inner_judge(clause, span) -> (verdict, why)` so that a reply which ADMITS
    while self-reporting an error is downgraded to UNCERTAIN (which `entailed_by_span` rejects). A judge
    that raises is also folded to UNCERTAIN — the fail-closed direction, exactly as `_semantic_judge`
    would. Returns a new callable with the same signature."""
    def guarded(clause, span):
        try:
            v, why = inner_judge(clause, span)
        except Exception as e:                          # noqa: BLE001 — a raising judge fails closed
            return 'UNCERTAIN', f'judge raised (fail closed): {type(e).__name__}'
        token = str(v or '').strip().upper()
        excerpt = str(why or '').lower()
        if token in _ADMIT_TOKENS and any(m in excerpt for m in _ERROR_MARKERS):
            return 'UNCERTAIN', f'judge admitted while self-reporting an error; downgraded (fail closed): {why}'
        return v, why
    return guarded


def install_guarded_judge():
    """Install the guard around the CURRENTLY-wired entailment judge (or the production default when none
    is wired), so a self-reporting-error admission can never enter the audit. Returns the previous judge so
    a caller can restore it. `set_entailment_judge` clears report_ast's judge cache, so a masked verdict
    already memoised for a (span, clause) pair is not reused."""
    prev = getattr(RA, '_ENTAILMENT_JUDGE', None)
    base = prev if prev is not None else RA._llm_entailment_judge
    RA.set_entailment_judge(guard_entailment_judge(base))
    return prev
