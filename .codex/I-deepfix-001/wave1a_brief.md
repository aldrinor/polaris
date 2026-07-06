# Wave 1a build brief — group writer contract + bounded repair + labeled fallback block

**Campaign:** I-deepfix-001 (#1344). **Plan:** `.codex/I-deepfix-001/REAL_PLAN_2026.md`. **Branch:** `bot/I-wire-001-integration`.
**Invariant (non-negotiable):** all new behavior behind `PG_SYNTH_PRIMARY` (default OFF). OFF => **byte-identical** output on every existing path. Faithfulness engine (strict_verify / NLI / D8 / provenance / span-grounding / the stricter writer wrapper) **byte-untouched**. This is a clinical-safety change: under-relax is safe, over-relax is lethal.

## Files + exact anchors (verified 2026-07-05)
- `src/polaris_graph/generator/abstractive_writer.py`: `_WRITER_SYSTEM` (345-359, ends "...output exactly one sentence per span, nothing else."); `_build_writer_prompt` (362-400); `_call_writer` (404-438, passes `system=_WRITER_SYSTEM`); `make_writer_verify_fn` (285-341) = STRICTER wrapper (UNCHANGED).
- `src/polaris_graph/generator/verified_compose.py`: `_compose_one_basket` (1268-1335) — first-failure `fell_back=True; break` at 1303-1304; mid-line K-span glue `" ".join(kept + [fallback])` at 1329; disclosure glue at 1335. ARM-B helpers `partition_composed_disclosures` (1156-1171) + `render_degraded_disclosures` (1174-1189).
- `src/polaris_graph/generator/multi_section_generator.py`: writer construction + primary/stub branch (4913 `_build_verified_span_draft`; 4954 `PG_ABSTRACTIVE_WRITER` gate; 4961 `assert_activation_preconditions`; `_compose_section_per_basket`/`_run_section` 4781-5030).

## Change 1 — group writer contract (abstractive_writer.py)
1. Add `_WRITER_SYSTEM_GROUP` constant (do NOT edit `_WRITER_SYSTEM`): same faithfulness rules as `_WRITER_SYSTEM` (never add a fact not in a span; copy every number verbatim; every sentence ends with its exact provenance token copied char-for-char; copy every epistemic/scope qualifier; no markdown/chrome) EXCEPT the last clause becomes: "Write ONE coherent, connected multi-sentence narrative that covers this GROUP of verified spans in a logical order; each sentence ends with the exact provenance token(s) of the span(s) it rests on; you may order and connect the facts with plain connectives, but never state a fact not present in a provided span, and never merge two spans' numbers into a new aggregate."
2. `_build_writer_prompt(members, evidence_pool, *, revise_reasons=None, group_mode=False)`: when `group_mode`, the lead instruction becomes "Write ONE connected paragraph covering ALL the verified spans below, in a logical order; each sentence ends with the exact provenance token for the span(s) it rests on..." (spans+tokens block unchanged; revise_reasons block unchanged). When `group_mode=False` => byte-identical to today.
3. `_call_writer(..., group_mode=False)`: `system = _WRITER_SYSTEM_GROUP if group_mode else _WRITER_SYSTEM`; pass `group_mode` into `_build_writer_prompt`. Default False => byte-identical.

## Change 2 — bounded repair + labeled fallback block (verified_compose.py `_compose_one_basket`)
Add module env helpers: `_synth_primary_enabled()` (reads `PG_SYNTH_PRIMARY`, default OFF, same off-token set as `_compose_render_chrome_enabled`) and `_writer_repair_max()` (reads `PG_WRITER_REPAIR_MAX`, default 2, int, clamp >=0, LAW VI).
- OFF path: the current body runs UNCHANGED (first-failure break; the 1329 glue; disclosure) — byte-identical.
- ON path (`_synth_primary_enabled()` True AND the caller passed a group-capable re-draft writer): replace break-on-first-failure with:
  1. Verify ALL sentences of the draft; collect `(sentence, failure_reasons)` for every failing one; keep passing ones (same chrome-screen `continue` behavior for verified chrome).
  2. While failures remain and attempts < `_writer_repair_max()`: re-call the writer with `revise_reasons=` the collected wrapper failure reasons (RARR); re-verify the FRESH draft in full with the UNCHANGED `verify_fn` + own-region gate. (CoF re-attribution is already inside `verify_sentence_provenance` via PG_SPAN_RESOLVER — no new acceptance path.)
  3. Exit: all pass => `" ".join(kept)`. Budget exhausted => body = the verified authored sentences (`" ".join(kept)`); the uncovered facts' K-span becomes a SEPARATE labeled disclosure unit — return it via the ARM-B channel so `_run_section` appends it as its OWN `\n\n`-joined paragraph (NEVER `" ".join(kept + [fallback])`). Failed AUTHORED sentences are DISCARDED (never shipped).
- The K-span disclosure unit must be a `[`-prefixed own-line label (redactor no-touch set) and still pass provenance/region checks (it is a verbatim span). Reuse `build_verified_span_draft_multi` for the span text; wrap it in the labeled-disclosure prefix so `partition_composed_disclosures` routes it.
- `writer_fn` closure: today it is `writer_fn(basket, scoped_pool)`. Thread an optional re-draftable form so the repair loop can pass `revise_reasons` + `group_mode`. Keep the OFF closure signature/behavior byte-identical.

## Change 3 — primary-path wiring (multi_section_generator.py)
- When `PG_SYNTH_PRIMARY` is ON: the group-writer branch is the PRIMARY body path (implies `PG_ABSTRACTIVE_WRITER`; `assert_activation_preconditions()` at 4961 still hard-requires entailment=enforce); construct the writer closure with `group_mode=True` and re-draft support; demote the FIX-K span-dump (4913) to fallback-only. No new module-level imports on the hot path (use the existing inline-import discipline).
- OFF => the existing branch selection is byte-identical.

## Required tests (RED/GREEN, tests/polaris_graph/)
1. OFF byte-identical: `PG_SYNTH_PRIMARY` unset => `_compose_one_basket` output byte-identical to today on (a) all-pass draft, (b) first-sentence-fails draft (K-span glue), (c) no-verified-span (disclosure). Golden-string asserts.
2. ON group contract: `group_mode=True` prompt contains the connected-paragraph instruction + all spans+tokens; `_WRITER_SYSTEM_GROUP` selected.
3. ON bounded repair: a stub writer failing sentence 2 on attempt 1 and passing on attempt 2 => final body contains both sentences; attempts respected; `PG_WRITER_REPAIR_MAX=0` => no repair (single attempt).
4. ON labeled fallback: after repair budget exhausted with one uncovered fact => body = verified authored sentences; the K-span appears as a SEPARATE `\n\n` disclosure paragraph (NOT mid-line glued); a failed AUTHORED sentence is absent.
5. Faithfulness: the stricter writer wrapper is applied unchanged on the ON path; no sentence lacking a valid token survives; K-span passes region check.

## Gate (dual, mandatory)
Real Codex CLI (`env -u OPENAI_API_KEY codex exec --skip-git-repo-check -` on a self-contained inlined diff+brief; NO `-s read-only`) AND real Fable 5 agent, in parallel, on the diff. Both APPROVE => commit exact files. Codex red-team focus: OFF byte-identical proof; repair loop cannot loop-forever or ship a failed authored sentence; K-span still passes provenance/region; no faithfulness threshold/judge touched.
