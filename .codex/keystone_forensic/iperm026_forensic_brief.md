You are Codex doing an independent LINE-BY-LINE clinical-safety forensic. Read ONLY these files (do NOT grep or walk the whole repo — it contains access-denied codex_* temp dirs that crash exploration; open the named files directly):
- src/polaris_graph/generator/evidence_distiller.py
- src/polaris_graph/generator/live_deepseek_generator.py (focus: _find_best_span_for_sentence, _rewrite_draft_with_spans)
- src/polaris_graph/clinical_generator/strict_verify.py

GOAL: explain WHY the keystone map-reduce distilled report is THINNER than the legacy single-pass on the drb_76 "Safety and contraindications" section, and enumerate EVERY land mine where FAITHFUL, on-topic safety content is silently lost (never extracted by the MAP, dropped by the REDUCE/marker filter, or dropped by the final strict_verify on a binding technicality). The COLLAPSE is already fixed (commit 8d74d1bb) — distill now produces faithful verified prose; this is purely a RICHNESS/recall gap, NOT a faithfulness defect.

LIVE TRACE (clean fresh-cache MAXEV=8 A/B, deepseek-v4-pro, OVH VM):
- ledger=3 findings from the CDC safety source; REDUCE wrote 3 sentences; strict_verify kept 2, DROPPED 1 (distill verified=2 vs legacy 6-8).
- DROPPED sentence: "In nonblood Saccharomyces culture findings, at least 24 patients (19%) ... odds ratio of 10 (95% CI 3-32) compared to controls." NOT a fabrication — the source contains BOTH "odds ratio 10, 95% CI 3-32" AND "odds ratio [OR] 14, 95% CI 4-44" (different subgroups). strict_verify dropped it on NUMBER-SPAN BINDING (multiple numbers 24/19/10/3/32 not all inside one prose-matched span; "24 patients" not verbatim).

TWO SUSPECTED LAYERS (verify line-by-line; find MORE):
1. MAP UNDER-EXTRACTION: _MAP_SYSTEM / _render_map_user extract the qualitative contraindications but under-extract the NUMERIC safety facts (odds ratios, fatality rates, contamination/AMR-transfer risk) that legacy mines.
2. REDUCE NUMERIC SPAN-BINDING: _REDUCE_SYSTEM / render_reduce_user pack MULTIPLE numbers into one sentence; the downstream _find_best_span_for_sentence binds ONE ~800-char span, and strict_verify requires EVERY number-in-span — so a multi-number synthesized sentence whose numbers are scattered across the source is dropped. Related to I-gen-005 (range like "4-44"/"3-32" may tokenize as ONE token while the claim lists "4","44" separately).

HARD CONSTRAINTS (clinical faithfulness — LETHAL if violated):
- strict_verify / the 4-role vote / the D8 gate are BYTE-UNTOUCHABLE. Fixes must be MAP-extraction-side (prompt density) or REDUCE-output-shaping-side (e.g. one-number-per-sentence so numbers bind) ONLY. NO gate relaxation, NO fabrication. The final strict_verify stays the SOLE publication authority.
- Acceptance: distilled verified >= legacy on the Safety section with §-1.1 zero fabrication.

OUTPUT (plain text or YAML):
root_causes: [mechanism + file:line]
land_mines: [{location (file:line), mechanism, faithful_content_lost (concrete), fix (extraction/shaping-side only), faithfulness_safe (true/false)}]
proposed_fix_plan: [ordered concrete edits]
faithfulness_risks: [how each fix is contained so nothing unfaithful passes]
honesty_caveats: [what you could NOT verify; inference vs measured]
