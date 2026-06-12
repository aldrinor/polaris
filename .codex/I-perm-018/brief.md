# Codex BRIEF gate — I-perm-018 (#1210): thread advisory_text + cross_trial_block into REDUCE

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
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

## Issue (#1210, I-perm-018) — deferred P2 from the #1209 keystone Codex diff-gate
The map-reduce REDUCE branch (`multi_section_generator._run_section`) returns the REDUCE
prompt via `render_reduce_user(distillate)` BEFORE the legacy prompt-assembly, so it does
NOT inject the legacy `advisory_text` (domain tone/emphasis) + the M-72 cross-trial
synthesis context. The distilled section therefore lost the legacy path's narrative
richness. Codex rated this P2 (quality, NOT faithfulness — strict_verify still runs).
Task: thread advisory + cross-trial into the REDUCE prompt; flag-OFF byte-identical; tests.

## Design (the as-built one — verify it is faithfulness-safe + correct)

### The hard constraint that shapes the design
The distill REDUCE output passes through `filter_and_strip_reduce_markers`, which DROPS any
sentence lacking a `[[finding:<id>]]` ledger marker. So I must NOT reuse
`render_cross_trial_synthesis_block` — its instruction "Cite the contributing [ev_XXX]
markers when stating the inference" tells the model to write synthesis sentences with
`[ev_XXX]` but NO `[[finding:]]` marker → those sentences would be DROPPED, and the prompt
would teach a citation grammar incompatible with the distill filter.

### FRAMING-ONLY narrative context
New `evidence_distiller._render_reduce_narrative_context(advisory_text, cross_trial_summaries)`
returns a clearly-labelled block: "NARRATIVE FRAMING CONTEXT (framing ONLY — NOT findings,
NOT sources)" + the instruction: "Use this to shape TONE, EMPHASIS, ORDER; you must NOT
write or cite any sentence FROM this block; every sentence still comes from the
VALIDATED_FINDINGS_LEDGER above and carries its [[finding:]] marker; do NOT introduce
numbers/claims/sources not in the ledger." Then DOMAIN_ADVISORY (the advisory text) +
CROSS_TRIAL_CONNECTIONS (bullet list of `p.summary` strings only — NO evidence-id marks, NO
"cite" instruction). Empty inputs → "" → the REDUCE prompt is byte-identical to pre-#1210.

`render_reduce_user(distillate, *, advisory_text="", cross_trial_summaries=None)` appends the
block only when non-empty. The distill branch in `_run_section` builds
`cross_trial_summaries = [p.summary for p in cross_trial_block.get_for_section(section.title)]`
(it already holds `advisory_text` + `cross_trial_block` as params) and passes both.

### Faithfulness analysis (the crux)
1. The narrative context is FRAMING ONLY. The REDUCE writer is told, twice, that every
   sentence must come from the ledger + carry a [[finding:]] marker, and to introduce no
   numbers/claims/sources not in the ledger.
2. `filter_and_strip_reduce_markers` is UNCHANGED — any sentence the model nonetheless writes
   from the context (lacking a [[finding:]] marker) is DROPPED. So a stray synthesis sentence
   cannot survive.
3. `strict_verify` is UNCHANGED — even a ledger-cited sentence that wrongly imports a
   context number fails (number not in the cited finding's span) and is dropped.
4. The cross-trial summaries (`p.summary`) are plain prose WITHOUT the evidence-id marks
   (the legacy renderer appends `evid_marks` AFTER `p.summary`; I use only `p.summary`).
So the change can only affect TONE/EMPHASIS/ORDER of ledger-derived sentences — it cannot add
an unfaithful claim. Worst case: a dropped sentence, never a fabrication.

### Wiring (default-OFF / byte-identical)
- EDIT `src/polaris_graph/generator/evidence_distiller.py`: new
  `_render_reduce_narrative_context` + `render_reduce_user` gains kw-only `advisory_text` /
  `cross_trial_summaries` (both empty default → byte-identical).
- EDIT `src/polaris_graph/generator/multi_section_generator.py` distill branch (only): build
  the summaries + pass advisory_text. Legacy (`distillate is None`) path UNCHANGED.
- NO change to strict_verify, the 4-role evaluator, D8, `filter_and_strip_reduce_markers`,
  or the legacy prompt path.

### Tests (`tests/polaris_graph/generator/test_reduce_narrative_context_iperm018.py`, 6)
- byte-identical when no advisory/cross-trial (3 equivalent call forms; no FRAMING block).
- helper empty → "".
- advisory appended as framing-only (contains DOMAIN_ADVISORY + the "NOT findings" +
  "must NOT write or cite any sentence FROM this block" guards + VALIDATED_FINDINGS_LEDGER).
- cross-trial summaries appended (CROSS_TRIAL_CONNECTIONS + the summary text).
- ledger row + write-instruction survive intact; no [#ev:] tokens.
- advisory-only → no empty CROSS_TRIAL_CONNECTIONS section.
Build: 6 new pass; 22 existing distiller tests pass (no regression).

## Questions
1. Is "framing-only narrative context, gated behind the existing distill filter +
   strict_verify" sufficient to keep this faithfulness-NEUTRAL? Any leak path I missed?
2. Is using `p.summary` only (dropping the legacy `[ev_XXX]` marks) the right call vs trying
   to make cross-trial inferences citable findings (which they are not — they're cross-source
   syntheses with no single binding span)?
3. Acceptance measures "narrative quality on the drb_76 offline replay" — for this prompt-only
   change, is the offline render assertion + the faithfulness argument enough, with the live
   narrative-richness check folded into the broad run? (No separate paid smoke for a prompt
   string.)
