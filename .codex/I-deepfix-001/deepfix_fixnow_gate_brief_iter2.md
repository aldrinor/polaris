HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

# Codex diff gate iter 2 — I-deepfix-002 (#1363) consolidated fix-now set

Re-review of the same consolidated diff (`.codex/I-deepfix-001/deepfix_fixnow_consolidated.patch`, now 898 lines, 12 files). Your iter-1 verdict was REQUEST_CHANGES with 3 P1 + 2 P2. All 5 are now addressed. Verify each fix below, confirm no regression, and confirm no NEW P0/P1. The §-1.3 law and your P0 checklist from iter-1 still apply (faithfulness engine FROZEN; default-ON kill-switches byte-identical OFF; keep-and-disclose, no hard-drop). You confirmed `faithfulness_engine_untouched: true` and `ev016` acceptable in iter-1 — those stand.

## How each iter-1 finding was resolved

**P1-1 (DEFER-1 over-reach — the global bibliography `[N]` strip) — FIXED by REMOVING the over-reach.**
`multi_section_generator.py`: the off-topic suppression is now scoped to the standalone weighted-enrichment selection ONLY (`weighted_enrichment.diagnose_unbound_supports_selection` withholds confirmed-off-topic SUPPORTS members from `ev_ids` — unchanged). The global bibliography numberer is reverted to its proven baseline:
- `_merge_bibliographies(section_slices)` — the `offtopic_eids` param and the `if ev_id in _off: continue` skip are GONE. It builds the bibliography from whatever is actually cited.
- `_remap_section_markers_to_global(section_results, global_biblio)` — the `offtopic_eids` param, the `local_offtopic` set, and the `if n in local_offtopic: return ""` marker-drop are GONE. Every `[N]` in already strict_verify-PASSED section prose now maps to its global number; no verified citation can be orphaned.
- the call site no longer builds/passes `_offtopic_biblio_eids`.
- The loud disclosure log of `_wfe.offtopic_suppressed` (the enrichment-level telemetry) is KEPT — it only logs, never strips.
Verify: no path in `multi_section_generator.py` strips a `[N]` from verified section prose or omits a cited source from the numbered bibliography based on the off-topic label. The only off-topic suppression surface is the enrichment `ev_ids` withholding in `weighted_enrichment.py` (which you did not flag).

**P1-2 (F4 kill-switch leak) — FIXED.**
`live_retriever.py::_recovered_content_error_class`: the WHOLE screen is now behind the kill-switch — `if not registry_error_guard_enabled(): return ""` short-circuits FIRST, so with `PG_REGISTRY_ERROR_GUARD=0` none of `is_registry_error_page` / `is_error_shell_text` / `classify_block_page` runs and the legacy length-only adoption path is byte-identical. ON: all three screens run as before.

**P1-3 (B2 prompt-hardening leak) — FIXED.**
`credibility_llm_tiering.py`: `_PROMPT` is split into `_PROMPT_HEAD` + `_PROMPT_VENUE_HARDENING` + `_PROMPT_TAIL`. `build_tier_prompt` now includes the hardening clause ONLY when `_venue_corroboration_required()` (the same `PG_TIER_REQUIRE_VENUE_CORROBORATION` switch as the cap). With the switch OFF the rendered prompt is the byte-identical legacy un-hardened prompt. Verify: OFF restores both the cap AND the prompt to legacy.

**P2-1 (B2 cap not wired on the single-source dispatcher) — FIXED.**
`credibility_llm_tiering.py::classify_source_tier_llm` now applies `_cap_uncorroborated_top_tier(llm_res, signals, floor)` (the same cap as the batch path at ~line 530), so the single-source ON-path can no longer return an uncorroborated T1/T2 from a bare DOI/title. Gated by the same switch; only lowers, never drops.

**P2-2 (F1-STRUCTURAL `head.text` over-demotion) — FIXED.**
`credibility_pass.py::_assemble_baskets` SUPPORTS branch: the chrome screen now screens ONLY the member's `claim_local_span`, not the cluster `head.text`. A chrome/truncated basket HEAD can no longer demote an otherwise-clean member; each member is judged on its own span. Real-corpus outcome unchanged (per the implementer's note), over-demotion risk removed.

## What to verify in iter 2
1. The DEFER-1 revert is COMPLETE and coherent — no leftover reference to `offtopic_eids` / `_offtopic_biblio_eids` in `multi_section_generator.py`, no dangling `[N]` risk reintroduced, the enrichment-level `offtopic_suppressed` telemetry + disclosure log still intact.
2. F4 / B2 OFF paths are now genuinely byte-identical (no behavior leaks past the kill-switch).
3. No NEW issue introduced by these 5 edits.
4. The rest of the diff (F1, F3, F2, FIX-2, FIX-3, DEFER-4, the quantified 3-way merge) is unchanged from iter-1 where you raised no findings.

## Output schema (REQUIRED)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
faithfulness_engine_untouched: true | false
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```
