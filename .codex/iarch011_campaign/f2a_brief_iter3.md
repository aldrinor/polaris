HARD ITERATION CAP: 3 per document. This is iter 3 of 3 (FINAL).
- Front-load ALL real findings. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; classify the rest P3/P2/cosmetic.
- This is the CAP. If you return REQUEST_CHANGES, Claude force-APPROVEs on remaining non-P0/P1 findings and captures them as follow-up Issues.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff review — I-arch-011 F2a-ALONE + disclosure fix (iter 3, FINAL) — the 794->9 fix

Review the patch FILE (static only, do NOT run pytest):

    .codex/iarch011_campaign/f2a_diff.patch   (3 files; workdir C:/POLARIS read-only)

## WHAT CHANGED SINCE YOUR ITER-2 REVIEW
Your iter-2 verdict was REQUEST_CHANGES with ONE P1 (zero P0s): the judge=None "run" path (priors-only)
set the per-source ``credibility_unscored`` labels INSIDE ``credibility_analysis`` but did NOT surface a
disclosed gap on an operator-visible carrier, so priors-only weights could ship without the LAW II
disclosure (the old "degrade" path set ``_credibility_disclosed_gap``; F2a's "run" path did not).

**P1 ADDRESSED** (your accepted option 2 — "set an explicit credibility_disclosed_gap on the judge=None
run path"):
 - New NAMED constant ``_CREDIBILITY_PRIORS_ONLY_DISCLOSED_GAP`` (multi_section_generator.py, next to the
   existing ``_CREDIBILITY_NO_JUDGE_DISCLOSED_GAP``) — text="credibility_pass_priors_only: the LLM
   credibility judge was not wired ... scored every source by deterministic authority priors only and
   labeled them credibility_unscored — this gap is disclosed. The binding faithfulness gates ... unaffected."
 - On the "run" SUCCESS path (after the budget re-check), when ``credibility_pass_judge is None`` AND
   ``credibility_analysis is not None`` AND ``_credibility_disclosed_gap is None`` (so a more-specific
   timeout-degrade gap is never overwritten), set ``_credibility_disclosed_gap =
   _CREDIBILITY_PRIORS_ONLY_DISCLOSED_GAP``.
 - This carrier IS operator-visible: run_honest_sweep_r3.py:11395-11397 reads ``multi.credibility_disclosed_gap``
   and writes ``manifest["credibility_disclosed_gap"]``. ``_credibility_disclosed_gap`` already flows to
   MultiSectionResult at multi_section_generator.py:8174 (field declared :954).
 - New unit test ``test_iarch011_f2a_judge_none_run_path_surfaces_disclosed_gap`` pins the wiring.

## THE REST (unchanged from iter-2, already at zero P0)
F2b is fully reverted (no env mutation; ``grep -c 'environ\[.PG_STRICT\|_advisory_entailment'`` == 0). The
basket per-member verify runs entailment-ENFORCE (default), bounded by PG_CREDIBILITY_PASS_MAX_INFLIGHT=16
over the I-arch-007 ITEM-2a per-thread judge client + the 3000s wall. F2a guard split: judge=None+gov-present
-> "run" (priors-only basket build); gov-missing -> "degrade"; legacy -> "raise". 51 tests pass; offline
membership-ceiling preflight: 754 unbound-SUPPORTS surfaced / 663 render sources (collapse was 9).

## YOUR JOB
A. Confirm the P1 is RESOLVED: the judge=None "run" path now surfaces the disclosed gap on an
   operator-visible carrier (manifest credibility_disclosed_gap). Confirm the guard (``_credibility_disclosed_gap
   is None``) does not clobber the more-specific timeout-degrade disclosure, and that the SUCCESS-path-only
   placement is correct (no double-set, no set on the abort path).
B. Confirm NO new P0/P1 introduced by the disclosure change.
C. 3-PRONG still holds: no faithfulness relaxation, no grandfather, no cap/floor/throttle/wrong-merge.

## OUTPUT SCHEMA (return EXACTLY this; last `verdict:` line is parsed)
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
