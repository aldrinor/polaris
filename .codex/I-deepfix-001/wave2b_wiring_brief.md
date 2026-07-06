# Wave 2b-WIRING — wire the minimal-citation-set minimizer into the CWF render/weight seam

**Issue:** I-deepfix-001 (#1344). **Branch:** `bot/I-wire-001-integration`.
**Scope:** WIRING ONLY. The pure module (`citation_set_minimizer.py`) + its offline unit tests were built
and committed earlier (commit `af2f4abb`, brief `.codex/I-deepfix-001/wave2b_brief.md`). This step wires
that module into the render path behind the EXISTING default-OFF flag `PG_MIN_CITE_SET` (no new flag).

```
HARD ITERATION CAP: 5 per document. This is iter N of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.
```

---

## 1. The one seam, and WHY it is the only safe seam

Grounding: `REAL_PLAN_2026.md` → `traceability` item 1 ("Minimal independently-entailing inline set")
+ item 2 ("Corroboration weight channel — demoted … members render in the CWF surface
`_basket_corroboration_block` as count + tier weights; nothing deleted").

The minimizer decides, for ONE verified sentence and the basket members cited on it, **which members render
as inline `[N]` citations and which move to the corroboration WEIGHT channel**. That decision needs a render
location that has BOTH surfaces present for the same verified claim. Exactly ONE such location exists:

**`scripts/run_honest_sweep_r3.py :: _basket_corroboration_block`** — the CWF "Source corroboration (per
claim)" section. Per verified claim/basket it already renders:
- an **inline citation set** on the claim header — `_layer2_markers` = the `[N]` of every distinct-origin
  verified SUPPORTS member (built from the two-layer `citation_layer_policy`), AND
- a **weight channel** — one `SUPPORT: <url> [N] (tier …, weight …)` bullet per member.

So the wiring is: split the keep-all distinct-origin members into `inline_members` (their `[N]` renders on the
claim header) vs `weight_members` (pruned-non-entailing ++ MVC-redundant corroborators), and render the demoted
members as bullets with tier+weight **without** an inline `[N]`.

### Why NOT `verified_compose.py` body prose (drop-risk — deliberately untouched)
The body-prose composers (`build_verified_span_draft` / `build_short_member_sentence` /
`compose_basket_multicited_sentence`) attach one member's `[#ev:…]` token per sentence, and the multi-cited
path co-locates each member's **verbatim clause TEXT**. Pruning/demoting a member THERE would delete that
member's rendered CONTENT, not just its citation — a §-1.3 CONSOLIDATE-keep-all violation and a source-DROP.
The minimizer's own contract is a "render-channel placement decision only". The CWF block is exactly that
channel; the body prose is not. `verified_compose.py` is therefore read-only context here — NOT edited.

## 2. Files / functions / flag

- `scripts/run_honest_sweep_r3.py` — `_basket_corroboration_block` only. Two edits, both inside the existing
  `if _layer2_cite_enabled():` header block and the following per-member SUPPORT-bullet loop:
  1. After `_render_members = _cite_layers.cited_members`, when `PG_MIN_CITE_SET` is ON, call
     `minimize_citation_set(claim, _render_members)`; the header `_layer2_markers` is then built from
     `inline_members` only. Fail-open: any minimizer/wiring fault keeps ALL members inline.
  2. In the SUPPORT-bullet loop, a member NOT in the inline set omits its `_member_marker` `[N]` (it is a
     weight corroborator, not an inline citation). It STILL renders as a bullet with tier+weight (keep-all).
- Flag: `PG_MIN_CITE_SET` (default OFF — read by the module's `min_cite_set_enabled()`). No new flag.
  `PG_MIN_CITE_SET_MAX_INLINE` (default 0 = prune-only) tunes MVC demotion, read by the module.

## 3. The keep-all-render-placement invariant (what this preserves)

- **OFF ⇒ byte-identical.** When `PG_MIN_CITE_SET` is unset, `min_cite_set_enabled()` is False, the minimizer
  is never called, `_inline_members == _render_members`, every member renders inline `[N]` exactly as today,
  and `_layer2_markers`/bullets are byte-for-byte the legacy output. (The `min_cite_set_enabled` env read has
  no output effect; the NLI model is never loaded on the OFF path.)
- **Keep-all (no source dropped).** The SUPPORT-bullet loop still iterates the FULL keep-all
  `_render_members` list; a demoted member loses only its inline `[N]`, never its bullet. `inline ∪ weight`
  == all distinct-origin members. The printed corroboration COUNT is computed upstream from `verified`
  (unchanged) — demotion never lowers the count; demoted sources are still counted + disclosed.
- **Faithfulness-NEUTRAL.** No verdict, source, count, basket, or gate changes. strict_verify / NLI / 4-role
  D8 / provenance / span-grounding are neither imported nor invoked by the wiring (the minimizer's default
  `entail_fn` reads `entails_directional` to place a citation — it never changes any verdict). The minimizer's
  fail-open (None/uncertain ⇒ KEEP inline) is preserved, and the wiring adds a second fail-open guard: any
  exception from the minimizer call keeps ALL members inline and logs loud (never crashes the render).

## 4. Tests (`tests/polaris_graph/generator/test_min_cite_wiring_wave2b.py`, offline)

Entail seam stubbed via `monkeypatch.setattr(citation_set_minimizer, "_default_entail_fn", …)` — no model,
no GPU, no OpenRouter. Renders through the real `_basket_corroboration_block`.
1. **OFF ⇒ byte-identical + minimizer not called.** `PG_MIN_CITE_SET` unset: `minimize_citation_set` spied
   and asserted NEVER called; header shows all `[1][2][3]`, each bullet carries its `[N]` (legacy render).
2. **ON prune + demote ⇒ weight channel + keep-all.** 3 distinct-origin members: one entailing (inline),
   one OFFTOPIC (pruned), one redundant corroborator (MVC-demoted at `MAX_INLINE=1`). Inline header shows
   ONLY the load-bearing `[1]`; `[2]`/`[3]` appear NOWHERE (not inline); all 3 source URLs still render as
   SUPPORT bullets with tier+weight (keep-all: inline ∪ weight == all members).
3. **ON runtime fault ⇒ fail-open.** `minimize_citation_set` monkeypatched to raise: the render does NOT
   crash, and all members stay inline (`[1][2][3]` all present) — the drb_75 render-crash class cannot recur.

## 5. Run (offline, $0)
- `python -m pytest tests/polaris_graph/generator/test_min_cite_wiring_wave2b.py -x -q`
- Regression: `python -m pytest tests/polaris_graph/generator -k "verified_compose or corroboration or basket" -q`
- `python -c "import scripts.run_honest_sweep_r3"` smoke-import.

## 6. Files (this diff)
- EDIT `scripts/run_honest_sweep_r3.py` (`_basket_corroboration_block`, ~2 hunks, behind `PG_MIN_CITE_SET`).
- NEW `tests/polaris_graph/generator/test_min_cite_wiring_wave2b.py`.
- NEW `.codex/I-deepfix-001/wave2b_wiring_brief.md` (this brief).
No other file edited. `verified_compose.py` is read-only context (drop-risk — §1).
