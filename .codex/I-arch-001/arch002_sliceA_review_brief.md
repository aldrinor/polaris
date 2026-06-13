# Codex CODE REVIEW — POLARIS I-arch-002 (#1246) Slice A (stop dropping fetched URLs), iter 2 of ≤5

HARD ITERATION CAP: 5 per document. This is iter 2 of 5.

## ITER 1 → ITER 2: what changed (verify each is closed; OFF still byte-identical)
Iter 1 = REQUEST_CHANGES (0 P0; faithfulness untouched; caps correctly gated; breadth deletions 0-default). Fixes applied (commit **2aa09d0f**, on top of a6510e78):
1. **P1 (P-W2scope) — the three scope gates now KEEP-with-weight under the flag, not DROP:** (a) `_apply_scope_denylist` (`evidence_selector.py` ~1478-1500) — under the flag, a denylisted row is KEPT, stamped `scope_denylist_demoted` + `credibility_class=low_denylist`, n_dropped=0; OFF = exact prior `continue`-drop. (b) `prefer_journal_over_arxiv` (~1564-1585) — under the flag the arXiv twin is KEPT, stamped `arxiv_journal_twin`/`preferred_version=journal`; OFF drops as before. (c) topic gate (`run_honest_sweep_r3.py` ~5020) — under the flag the `evidence_for_gen = _topic_result.kept_rows` reassignment is SKIPPED (keep all; weight-demote via the [scope] log); OFF = exact prior drop. **VERIFY** OFF is byte-identical for all three and ON genuinely keeps every row.
2. **P2 — the `[breadth-disclosure]` `_log` is now gated behind the flag** (`run_honest_sweep_r3.py` ~5996) so the default OFF path writes NO `run_log.txt` line. **VERIFY** OFF byte-identity restored.
3. P2 outline-menu headroom risk: acknowledged as a live run-quality note (fail-loud via FX-01; lever = Novita 32K route), NOT a code change.
Tests: +4 scope tests (OFF drops / ON keeps-with-marker); 18 pass incl. the OFF-byte-identical selector suite.
**Re-review the new diff `git diff a6510e78..HEAD` for these fixes; confirm OFF byte-identity + ON keep-all; then APPROVE if the P1+P2 are genuinely closed and no NEW P0/P1.**
- Front-load ALL real findings in iter 1. No drip-feeding.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — classify non-blockers as P3/P2; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, force-APPROVE on remaining non-P0/P1.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## What this is
Code review of **Slice A** of the WEIGHT-AND-CONSOLIDATE migration (CLAUDE.md §-1.3): make the pipeline **use the URLs it fetches instead of dropping them before composition**. Everything is behind the master flag `PG_SWEEP_CREDIBILITY_REDESIGN`. **The hard, non-negotiable invariant: flag OFF must be byte-identical to the prior tree.** The faithfulness engine (strict_verify / NLI / 4-role / provenance) must be UNTOUCHED — selection/generation only ever SUBTRACTS sources, so keeping MORE rows cannot fabricate; verify nothing here weakens a hard gate.

## The diff to review
Branch `bot/I-arch-002-no-dumping`, commits **cb4c6306..HEAD** (HEAD=a6510e78). Review:
```
git diff cb4c6306..HEAD -- src/polaris_graph/retrieval/evidence_selector.py scripts/run_honest_sweep_r3.py src/polaris_graph/generator/multi_section_generator.py
```
plus the new/changed tests `tests/polaris_graph/test_arch002_no_dumping.py`. Design + checklist: `docs/consolidation_design_wave3.md`, `.codex/I-arch-001/arch002_build_checklist.md` (steps P-W1, P-KEY, P-W4sel, P-W4gen, P-W2breadth, and the finding_dedup-bypass portion of P3.3).

## What Slice A changes (verify each is flag-gated + OFF byte-identical)
1. **P-W1** (`evidence_selector.py`): the relevance FLOOR keep-filter — under the flag, keep ALL scored rows (the below-floor rows carry their `selection_relevance` weight) instead of the `>= floor` hard-drop (the live 236/589 cut). New helper `_credibility_redesign_enabled()`. OFF => exact prior filter.
2. **P-KEY** (`run_honest_sweep_r3.py` ~4765): hoist `_cred_redesign_on` once; the flag previously governed ONLY the disclosure pass.
3. **P-W4sel** (`run_honest_sweep_r3.py`): the TWO `_capped_finding_dedup_selection` sites (initial ~L4911 + regen/saturation ~L5631) skip under the flag so the keep-all pool is not re-truncated to `PG_LIVE_MAX_EV_TO_GEN`.
4. **P-W4gen** (`multi_section_generator.py`): per-section ROW caps (`PG_MAX_EV_PER_SECTION`) at all sites + the outline menu (`PG_OUTLINE_MAX_EV`) become a serialized CHAR budget (`PG_SECTION_EV_CHAR_BUDGET` default 120000) under the flag. OFF keeps the 30/150 clamp.
5. **P-W2breadth** (`multi_section_generator.py` + `run_honest_sweep_r3.py`): DELETE `_augment_legacy_section_breadth` (PG_LEGACY_SECTION_BREADTH_TARGET), the PG_SECTION_SOURCE_BREADTH_TARGET widener, and `enforce_breadth_canary` (PG_BREADTH_CANARY_MIN) — claimed all 0-default no-ops (so deletion is byte-identical WITHOUT a flag).
6. **finding-dedup member-drop bypass** (`run_honest_sweep_r3.py` ~L5926 final pass): under the flag, skip replacing `evidence_for_gen` with the deduped rows.

## REVIEW QUESTIONS (answer EACH, grounded in file:line)
1. **OFF byte-identical (the P0 question).** For EVERY change above, when `PG_SWEEP_CREDIBILITY_REDESIGN` is unset, is behavior byte-identical to cb4c6306? Name any site that alters OFF behavior. In particular: (a) is each per-section/outline cap dissolution truly wrapped behind the flag (the 30/150 clamps are REAL non-zero defaults, so an unwrapped dissolve is NOT byte-identical)? (b) Are the three breadth deletions ALL genuinely 0-default no-ops on the default AND the Gate-B paid path (grep their env defaults + any non-zero set in run_gate_b.py)?
2. **Completeness of "no dumping" under the flag.** With the flag ON, is there ANY remaining hard-drop/cap of fetched rows between selection and composition that this slice missed (so the pipeline would still dump)? Name it.
3. **Faithfulness safety.** Does anything here touch strict_verify / provenance / NLI / 4-role, or change a per-sentence verification verdict? It must not. Confirm the only effect is MORE sources reaching composition (still each span-grounded at generation). Any path where keeping more rows could regress a hard gate?
4. **The unconditional re-pointed disclosure LOG** (the agent flagged it fires OFF+ON, vs the deleted one which only fired when PG_LEGACY_SECTION_BREADTH_TARGET>0). Does it touch any artifact (report/SVs/manifest) or only stdout? Is the added default-path log line acceptable or must it be flag-gated for strict OFF-byte-identical?
5. **The full outline menu under the flag** re-enters the reasoning-first headroom hazard PG_OUTLINE_MAX_EV bounded (a large terse menu). Is it genuinely fail-loud (FX-01 catches, never ships scratchpad), or could it silently degrade on the live run? P-severity?
6. **Logic/correctness of the char-budget trim** (`_budget_trim_ev_ids` / the per-section sites): does it preserve per-facet reserved rows (`reserved_floor`), and is the OFF path's row-cap behavior exactly preserved?
7. **Any bug** in the large multi_section_generator.py change (deletions leaving dangling references, broken outline assembly, an ungated site) or the run_honest_sweep gating.

## OUTPUT SCHEMA (end with EXACTLY this)
```yaml
verdict: APPROVE | REQUEST_CHANGES
off_byte_identical: yes|no — <any site that changes OFF behavior, file:line>
no_dumping_complete: yes|no — <any remaining drop/cap under the flag>
faithfulness_untouched: yes|no — <any strict_verify/provenance change>
novel_p0: [...]
continuing_p0: []
p1: [...]
p2: [...]
breadth_deletions_zero_default: confirmed|not — <evidence>
convergence_call: continue | accept_remaining
top_changes_before_execution: [<minimal fixes; empty if APPROVE>]
```
APPROVE iff OFF is byte-identical, faithfulness is untouched, and no remaining drop defeats the no-dumping goal. Cosmetic log lines are P2/P3, not blockers, unless they break strict OFF-byte-identical.
