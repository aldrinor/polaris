M-14 V34 cross-jurisdiction synthesizer — code review.

**Skip git status.** Codex at gpt-5.4 + xhigh.

## Context

Phase C plan v2 GREEN-locked. M-14 is the first Phase C
critical-path milestone — closes LB Regulatory by emitting
cross-jurisdiction synthesis with explicit divergence
detection.

The dominant Phase C risk for V34 (per the plan): **over-claim**
— flattening genuine FDA-vs-EMA disagreement into bland
"regulators worldwide approved" prose.

## What landed (commit 20c2461)

`src/polaris_graph/generator/cross_jurisdiction_synthesizer.py`
(~330 lines):
- `JurisdictionFinding(jurisdiction, field_name, value,
  bound_ev_id, source_url=None)` frozen dataclass — the input
  per-jurisdiction × field record.
- `FieldVerdict(field_name, verdict, jurisdictions,
  bound_ev_ids, similarity)` per-field structured verdict.
- `CrossJurisdictionSynthesis(paragraphs, verdicts)` top-level
  output.
- `synthesize_cross_jurisdiction(findings, convergence_floor=0.5)`:
  groups findings by `field_name` (case-insensitive), computes
  pairwise minimum Jaccard, emits one of four verdicts per
  field:
    - single_source: only one jurisdiction has a non-empty
      value.
    - convergence: all pairs ≥ floor → flattened paragraph
      naming all contributing jurisdictions + binding all
      citations + canonical (longest) prose.
    - divergence: any pair < floor → bullet list, one per
      jurisdiction, each with its own citation.
    - no_findings: all values empty.
- Pure deterministic — no LLM calls. M-70 LLM prose is reused
  verbatim inside M-14's templates.
- LAW II validation:
    - Unknown jurisdiction string raises ValueError (no fuzzy
      matching of typos).
    - convergence_floor outside [0, 1] raises ValueError.
    - Empty findings list → empty synthesis (no crash).
    - Empty value → "no finding" (skipped), not "explicit
      absence" (which would be misleading).
- Tokenization mirrors M-10 template_classifier (lowercased,
  stopword-filtered content tokens).

## Tests: 21 total

All green. Coverage:
- Known/unknown jurisdiction recognition + raise on unknown.
- Single-source paragraph names jurisdiction + caveat.
- Convergence with 3+ jurisdictions (longest-value canonical).
- Divergence with assertion that NO flattening phrases
  ("regulators worldwide", "globally approved", etc.) appear.
- Multi-field grouping; alphabetical paragraph order.
- Case-insensitive field_name grouping.
- Empty values skipped; all-empty → no_findings.
- Threshold bounds + behavior.
- Determinism (same input → same output).
- JSON round-trip.
- Realistic 4-jurisdiction × 3-field mixed-verdict scenario.

## Anti-scope (deferred)

- Wiring M-14 into the V34 sweep pipeline (next sub-milestone).
  This commit ships the module + tests; integration into
  `report_contract.py` / `multi_section_generator.py` is the
  next step.
- LLM-driven synthesis (deliberately rejected — M-14 is
  detection, not generation).
- New jurisdictions beyond FDA/EMA/MHRA/PMDA/NICE/HC/TGA.

## Your job

Code review for M-14. Verdict: GREEN / PARTIAL / DISAGREE.

## Specific things to validate

1. **LAW II over-claim defense.** Walk through the divergence
   paragraph emission and convince yourself an LLM (or buggy
   refactor) cannot smuggle "regulators agree" prose past the
   templated bullet structure.

2. **Convergence threshold (0.5 default).** Is this the right
   default? Higher (0.7) biases toward divergence (operator
   sees more disagreement); lower (0.3) flattens more. Phase
   C risk register says "biases toward DIVERGENCE — the safer
   failure mode under LAW II". Agree?

3. **Pairwise minimum Jaccard.** A single dissenting
   jurisdiction drops a 4-way unanimous into divergence. Is
   that the right semantics, or should there be a "majority
   convergence with one outlier" verdict?

4. **Longest-value canonical** for convergence. The longest
   value gets shown verbatim. Is there a case where this
   silently drops a critical detail from a shorter
   jurisdiction's prose?

5. **Citation binding.** Every emitted paragraph cites
   bound_ev_ids. The Inspector renderer downstream needs to
   resolve these to displayable evidence cards. Are the
   citation tokens (`[ev_id]`) compatible with the existing
   strict_verify regex?

6. **Determinism.** No LLM. Test verifies. Any non-deterministic
   path (set iteration, dict ordering) I missed?

7. **Anything else.**

## Output

Write to `outputs/codex_findings/m14_review/findings.md`:

```markdown
# Codex review of M-14

## Verdict
GREEN / PARTIAL / DISAGREE

## Specific issues
File:line bugs / gaps.

## LAW II over-claim defense
Is the divergence path airtight?

## Threshold + verdict semantics
Agree with 0.5 default + min-Jaccard + longest-canonical?

## Recommended changes
If PARTIAL.

## M-15a readiness
After M-14 locks, M-15a (auth substrate) is next on the
critical path. Anything in M-14 that needs to settle first?

## Final word
GREEN to lock M-14 + proceed to M-15a / PARTIAL with edits /
DISAGREE.
```

Be terse. Under 200 lines.
