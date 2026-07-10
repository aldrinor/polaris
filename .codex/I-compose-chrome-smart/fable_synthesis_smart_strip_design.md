# I-compose-chrome-smart — Fable design: chrome-free body BY CONSTRUCTION (smart synthesis), strips demoted to safety net

Branch: `bot/I-deepfix-relaunch`. Author: Fable 5 (architect). Builder: Opus. Gate: the compose test (read the prose).

Operator's insight under test: *"We now do deep synthesis, not quote-copying. A smart LLM that rephrases claims in its own analytical prose should never emit a cookie banner — chrome carries no claim to rephrase. So the body should be chrome-free by construction once synthesis truly fires."*

Verdict on the insight: **RIGHT, with one refinement.** The synthesized sentences themselves are already almost chrome-proof. But chrome enters today's body mainly through (i) the **verbatim fallback parachutes** that fire whenever synthesis fails — and synthesis fails a lot — and (ii) two prompts that actively **FORCE** chrome through by demanding one sentence per span. Fix both and the body is chrome-free by construction; the deterministic strips demote to a safety net and stay authoritative only on the one surface where copying is the contract (the Evidence base appendix).

---

## 1. Honest findings (Q1 / Q2 / Q3), with file:line

### Q1 — Does synthesis reliably fire? NO. Every failure lands on a verbatim parachute, and failures are routine.

**Body composer.** `PG_SYNTH_PRIMARY` is **default OFF in code** — `verified_compose.py:1519-1525`: *"``PG_SYNTH_PRIMARY`` gate (default OFF, LAW VI) ... unset/blank/off-token => OFF"*. Only the Gate-B cert launcher pins it ON (`scripts/dr_benchmark/run_gate_b.py:1639` — `"PG_SYNTH_PRIMARY": "1"`). Any resume-render / direct-sweep path that does not go through that env launcher composes the body with the **deterministic verbatim span writers** (`multi_section_generator.py:5485-5503` — `build_multi_member_sentences` / `build_short_member_sentence`, verbatim spans, no LLM).

Even with the flag ON, the group-writer pre-pass drafts only a fraction of baskets on real runs:

- `outputs/p6_preflight_postfix/resume_run.log:3274` — `pre-pass complete: 0/4 baskets drafted` (a whole section body = 100% verbatim fallback)
- `outputs/p6_postfix_resume/run.log:3467` — `2/6 baskets drafted`; `:3517` `4/6`; `:3521` `4/7`; `:3580` `3/6`
- `outputs/p6_preflight_postfix/resume_run.log:3302-3317` — `3/9`, `6/9`, `4/8`, `4/7`, `5/7`
- best case `outputs/p6_cert_fresh/run.log:25412` — `19/19` (it CAN fire fully)

Every undrafted or verify-failed basket falls to the **verbatim K-span fallback**: `verified_compose.py:1948-1970` (legacy path — `build_verified_span_draft_multi`, screened only by `_screen_fallback_chrome` at `:1490-1515`) or `_synth_primary_fallback_unit` `verified_compose.py:1768-1794` (SYNTH_PRIMARY path — labeled disclosure, same deterministic screen). Verbatim spans are exactly where chrome lives.

**Depth "Analysis" layer** (`depth_synthesis.py`). The LLM consolidation per basket is real (`_synthesize_one_basket` :841-898), but FIX-1 makes zero-survivor drafts fall back to the **deterministic verbatim span-join** (`:731-739`), rendered as an Analysis *finding*. A `drafted=0` pre-pass (`depth_synthesis_pre_pass` returns `{}`, `make_depth_synthesizer` returns `""` per basket) means **every** "finding" in the Analysis digest is a verbatim quote-join — a quote-dump dressed as analysis. The only chrome guard on those sentences is the shared deterministic predicate at `_collect` (`:679` — `screen(sentence)` = `is_render_chrome_or_unrenderable`), i.e. the whack-a-mole floor.

**Analyst Synthesis layer** (`analyst_synthesis.py`). Genuine LLM interpretive prose, but the emitter is fail-closed: the whole layer is **omitted** whenever the D3 PROMOTE gate is off (`:685-692`). So on many runs the only "synthesis" prose in the report is the depth layer + (maybe) the group writer.

**Always-verbatim surfaces.** FIX-K enrichment span dump (`multi_section_generator.py:5315-5343`) and the "Evidence base" appendix (`weighted_enrichment.py:5263-5366`) are verbatim by construction.

**Bottom line Q1:** the architecture is *synthesis-with-a-verbatim-parachute*. On live evidence the parachute fires for 30-100% of baskets in weak sections. The diagnostic report's chrome-in-body is exactly this: drafted=0 → verbatim span body/span-join findings → chrome rides in on whatever the deterministic predicate misses (~15 residual leak classes per `I-fetchclean-001` round 3).

### Q2 — Is the synthesis prompt chrome-aware? NO. Two prompts are actively chrome-FORCING; all four are silent on input junk.

- `abstractive_writer.py:407-421` `_WRITER_SYSTEM` (the body writer): *"You rewrite already-verified evidence spans into clean, plain, declarative news-style sentences. ... **You output exactly one sentence per span, nothing else.**"* — given a cookie-banner span as `SPAN 3`, an obedient writer is **instructed** to rephrase it into a news-style sentence. The only "chrome" wording in the prompt is about the writer's own OUTPUT format (*"no markdown, links, bullets, headings ... academic chrome like 'this study'"*), not about junk in the INPUT spans.
- `abstractive_writer.py:431-449` `_WRITER_SYSTEM_GROUP`: *"Write ONE coherent, connected multi-sentence narrative that **covers this GROUP of verified spans**"* — same coverage forcing.
- `depth_synthesis.py:796-805` `_SYNTHESIS_SYSTEM`: *"You consolidate several already-verified evidence spans that report the SAME finding into ONE clean, plain, declarative news-style sentence. ... You output EXACTLY one sentence, nothing else"* — silent on junk inputs.
- `analyst_synthesis.py:72-128` `ANALYST_SYNTHESIS_SYSTEM_PROMPT`: four CORE RULES ([N] citations, hedging, no facts beyond the pool, reference the verified core) — silent on boilerplate.

Today's entire chrome defense at the synthesis INPUT is deterministic: `_compose_junk_screen` member screen (`abstractive_writer.py:643-662`), `_dechrome_distinct_origin_supports` (`depth_synthesis.py:414-437`, `:859-867`). The smartest chrome detector in the pipeline — the writer LLM itself — is given no permission to refuse junk and a coverage contract that overrides its judgment. The operator's point stands verified.

### Q3 — Does the appendix leak? YES, by construction — and deterministic strip IS the right tool there.

`build_evidence_base_section` (`weighted_enrichment.py:5263-5366`) emits **verbatim units** screened only by the ONE shared predicate (`_make_junk_screen` == `is_render_chrome_or_unrenderable`, `:4765-4775`) plus the off-topic span withhold. Any leak class the predicate misses renders in the appendix (the `I-fetchclean-001` round-3 residuals: journal masthead VOL/NO headers, bot-wall interstitial lines, cookie-shell vocab — 15 live leak spans). The appendix is the one surface whose IDENTITY is verbatim copying (the audit-grade evidence record); synthesizing/summarizing it would turn it into a second body and destroy the audit surface. So: keep it verbatim, keep the deterministic strip authoritative THERE, and keep improving it at the FETCH layer (the replay loop) — the appendix inherits every fetch fix for free.

---

## 2. The essential fix (a) (b) (c)

Faithfulness engine (strict_verify / entailment union / D8 / provenance) untouched everywhere. §-1.3 intact: nothing below drops a source; skips/labels/screens act on SPANS and RENDER only. All new flags default-ON with byte-identical OFF.

### (b) FIRST — chrome-aware prompts (the operator's fix; highest leverage, smallest diff)

One shared flag **`PG_SYNTH_PROMPT_CHROME_AWARE`** (default ON, read at call time; OFF ⇒ prompt strings byte-identical). Implementation: a conditional suffix/substitution helper, NOT an edit of the base constants (so OFF is provably byte-identical).

The shared junk-refusal clause (appended to every synthesis-writer system prompt):

> "Some input spans may contain website boilerplate rather than research content: navigation menus, cookie or consent notices, login / subscribe / paywall prompts, 'reading time' or share bars, bot-check / CAPTCHA / 404 / error-page text, page headers and footers, journal mastheads and running headers, reference-list fragments, download or PDF links. Boilerplate carries no factual claim. NEVER rephrase, quote, or reproduce it. If a span is only boilerplate, SKIP it — output nothing for that span. If a span mixes boilerplate with a substantive finding, state only the substantive finding."

Per-file edits:
1. `abstractive_writer.py` — append clause to `_WRITER_SYSTEM` + `_WRITER_SYSTEM_GROUP`; under the flag, soften the coverage contract: single mode *"one sentence per SUBSTANTIVE span; skip boilerplate spans"*; group mode *"cover the substantive spans; skip boilerplate spans"*. Same softening in the `_build_writer_prompt` lead (`:469-483`).
2. `depth_synthesis.py` — append clause to `_SYNTHESIS_SYSTEM` and the `_build_synthesis_prompt` lead (`:814-818`), plus *"if every span is boilerplate, output nothing"*.
3. `analyst_synthesis.py` — add CORE RULE 5 to `ANALYST_SYNTHESIS_SYSTEM_PROMPT`: *"Never quote or reproduce website boilerplate (cookie/consent notices, navigation, subscription prompts, error pages, mastheads). State only substantive findings, in your own words."*

**Compatibility proven against the real gates:** `_draft_passes_wrapper` (`abstractive_writer.py:578-608`) verifies only the sentences the writer EMITS — it never requires span coverage — so a skipped junk span cannot fail a draft. An ALL-junk basket ⇒ empty draft ⇒ `writer_empty_draft` ⇒ K-span fallback ⇒ `_screen_fallback_chrome` empties it ⇒ honest gap disclosure (`verified_compose.py:1500-1515`, `:1959-1970`). The chain ends clean; no chrome, no silent blank. Every emitted sentence still passes the unchanged verify (strict_verify + entailment union + D8) — this is purely ADDITIVE to the faithfulness engine.

### (a) Make synthesis fire reliably; when it can't, disclose — never dump

1. **a1 — `PG_SYNTH_PRIMARY` default ON in code.** Flip the default at `verified_compose.py:1519-1525` (kill-switch OFF ⇒ legacy byte-identical). Rationale: the Gate-B launcher already pins it ON; the code default closes the resume-render / direct-sweep gap — the exact gap class the analyst emitter already fail-closed against (`analyst_synthesis.py:680-692`). The body's PRIMARY producer becomes the group writer everywhere.
2. **a2 — label every verbatim survivor in the body.** The SYNTH_PRIMARY fallback already ships labeled (`_uncovered_fact_disclosure`, `verified_compose.py:1789-1794`). Extend the same honesty to the depth layer: a FIX-1 span-join finding carries a **"(verbatim evidence)"** label beside the existing cross_source/single_source tier (`depth_synthesis.py`: findings built from the fallback branch at `:731-739` get `label` set; `build_depth_layer` renders it). Flag `PG_DEPTH_FALLBACK_LABEL` default ON; OFF ⇒ byte-identical. A quote-join is never again dressed as an analytical finding — disclosure, not deletion (§-1.3).
3. **a3 — strips stay as the safety net, demoted not deleted.** Keep the shared predicate exactly where it already guards synthesis output: depth `_collect` `:679`, `_screen_fallback_chrome`, `_screen_fixk_render_chrome`. They catch the sentence the LLM still copies through on a bad day. No new strip work in the body path.
4. **a4 — drafted-rate is a first-class forensic number.** The pre-pass already logs `N/M baskets drafted` (`abstractive_writer` pre-pass, `depth_synthesis.py:986-989`). Surface both ratios in the run manifest (like fetch-yield) so a <50% drafted section is visible every monitoring tick instead of being reconstructed post-mortem.

### (c) Appendix: verbatim + deterministic strip is RIGHT there; tighten by trimming, not dropping

1. Keep `build_evidence_base_section` verbatim and screened by the ONE shared predicate (already true — `weighted_enrichment.py:4765-4775`). Do NOT synthesize/summarize the appendix: it is the audit-grade verbatim evidence record; a summary would duplicate the body and erase the record.
2. **Trim tokens inside kept units** (the F7 pattern: inline masthead/CONTACT token strip) rather than dropping whole rows — the source keeps its [N] and its span (§-1.3 keep-all; deletion only under the §-1.3.1 junk carve-out with disclosure).
3. The `I-fetchclean-001` fetch-corpus replay loop remains the appendix's improvement engine at the FETCH layer — every fetch-side fix cleans the appendix for free. The whack-a-mole is thus confined to the one surface where it is the correct tool.
4. Add a one-line preamble under the "## Evidence base" header (default-ON flag `PG_EVIDENCE_BASE_PREAMBLE`): *"Verbatim source excerpts, weight-ordered, screened for page furniture."* — so a reader never mistakes appendix quotes for synthesized findings. (C4 already trails these sections as an appendix: `multi_section_generator.py:7324-7358`, applied at `:11109-11114`.)

---

## 3. How the compose test proves it

1. Run the single-question box-2 smoke (the retest helper on this branch) with all defaults (all new flags ON).
2. Split `report.md` at the appendix boundary (`## Evidence base`).
3. **BODY (above the boundary) — read the prose:** zero hits for the `I-fetchclean-001` fixture leak classes (cookie/consent, nav menus, masthead VOL/NO, bot-wall/CAPTCHA, reading-time, subscribe/login); every Analysis finding reads as an analytical sentence; any verbatim survivor carries its "(verbatim evidence)" / uncovered-fact label.
4. **Faithfulness unchanged:** strict_verify / entailment / D8 kept-sentence counts equal or better vs. the pre-change run; no engine file touched (diff shows prompts + flags + labels only).
5. **Flag-OFF byte-identity (offline):** with `PG_SYNTH_PROMPT_CHROME_AWARE=0`, assert the four system-prompt strings byte-equal the current constants; with each new flag OFF, the corresponding path is byte-identical (existing test pattern).
6. **The real gate:** the operator hears the body read aloud. If a cookie banner survives in the BODY, the fix failed — regardless of any counter.

Why this beats strip-harder: the strips have a measured floor (15 residual leak classes after three fix rounds — regex can't enumerate the web). The writer LLM already semantically recognizes boilerplate; today it is ORDERED to rephrase it ("one sentence per span") and never told it may refuse. Granting refusal + making the synthesizer the reliable primary removes the chrome channel from the body **by construction**, while every emitted sentence still clears the unchanged faithfulness engine. The strips keep working exactly where copying remains the contract.
