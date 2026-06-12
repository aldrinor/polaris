# Codex DIFF gate — I-perm-018 (#1210): advisory + cross-trial into REDUCE (framing-only)

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — reserve P0/P1 for real execution risks; cosmetic = P3/P2.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on non-P0/P1; no iter 6.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (required)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

## The diff
`.codex/I-perm-018/codex_diff.patch` (staged). 3 files, +~180. Read these EXACT files
(do NOT scan the whole repo — codex_* temp dirs crash exec):
- EDIT `src/polaris_graph/generator/evidence_distiller.py` — new `_render_reduce_narrative_context`
  + `render_reduce_user` gains kw-only `advisory_text` / `cross_trial_summaries`.
- EDIT `src/polaris_graph/generator/multi_section_generator.py` — distill REDUCE branch builds
  the summaries + passes advisory_text (the only behavioral edit; also a 1-line doc-comment
  clarification near line 2398 from the keystone work).
- NEW `tests/polaris_graph/generator/test_reduce_narrative_context_iperm018.py` — 6 tests.

The brief was APPROVED at `.codex/I-perm-018/codex_brief_verdict.txt` (read for acceptance
criteria + the design rationale).

## What it does (prompt-only; faithfulness-NEUTRAL)
Threads the legacy domain `advisory_text` + the M-72 cross-trial inferences into the distill
REDUCE prompt as a FRAMING-ONLY block (TONE/EMPHASIS/ORDER), restoring the legacy path's
narrative richness that the distill branch had dropped. It is NOT findings/citable.

## Red-team this — focus
1. **Faithfulness leak (the crux):** can any sentence written FROM the framing block survive?
   The block says twice "you must NOT write or cite any sentence FROM this block; every
   sentence comes from the VALIDATED_FINDINGS_LEDGER and carries its [[finding:]] marker." AND
   the UNCHANGED `filter_and_strip_reduce_markers` drops any sentence lacking a [[finding:]]
   marker, AND the UNCHANGED strict_verify re-checks every surviving sentence. Is there a path
   where context prose becomes a published unfaithful claim? (There must be none.)
2. **Byte-identical when off:** `render_reduce_user(distillate)` and
   `render_reduce_user(distillate, advisory_text="", cross_trial_summaries=None/[])` must equal
   the pre-#1210 prompt exactly (no NARRATIVE FRAMING block). Verify the `narrative_section`
   conditional. The legacy (`distillate is None`) path is untouched.
3. **No [ev_XXX] leakage from cross-trial:** I use ONLY `p.summary` (plain prose), NOT the
   legacy renderer's appended evidence-id marks — so the prompt cannot teach a citation grammar
   incompatible with the distill filter. Confirm.
4. **Number leakage:** if a cross-trial summary contains a number and the model writes it onto
   a ledger sentence, strict_verify drops it (number not in the cited finding's span). Confirm
   the worst case is a dropped sentence, never a fabrication.

## Honest notes
- This is a prompt string change; its "narrative richness" effect is qualitative, folded into
  the broad operator-gated run (no separate paid smoke proves a prompt string). The
  faithfulness argument + the offline render assertions are the proof here.
- Tests: 6 new pass; 22 existing distiller tests pass (no regression).
