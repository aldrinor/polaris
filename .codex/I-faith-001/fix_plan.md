# POLARIS faithfulness-leak — root cause (smoke-proven) + fix plan

Investigation: Claude Codex Workflow (5 parallel root-cause probes → synthesis → smoke). Verified by me
re-running the smoke scripts. Target: run9 stated [6]-cited claims (14% vs span's 15%, 35%, attrition,
CSAT, partial-equilibrium) NOT present in the fetched Brynjolfsson span → 7/72 POLARIS claims span-unsupported.

## ROOT CAUSE (ranked, smoke-proven)

**RC-1 (PRIMARY) — the M-69 Fix #4 unconditional contract-entity rescue.**
`src/polaris_graph/generator/contract_section_runner.py:515-525`. The production verifier
(`generator/provenance_generator.py: verify_sentence_provenance`, NOT clinical_generator/strict_verify.py
which does not run in the sweep) CORRECTLY drops the fabricated sentences. Then this rescue loop restores
ANY dropped sentence whose `toks[0].evidence_id` is a contract entity — keyed only on the entity id,
**never on the drop reason**. `brynjolfsson_genai_at_work` is a contract entity, so every fabricated [6]
sentence is laundered back into `kept`. It was added to undo a content-word-overlap false-drop (the
SURPASS-5 25K-char regression) but does not discriminate.
SMOKE PROOF (I ran it): verifier drops S1(14%)+S2(35%) with `no_integer_overlap_any_cited_span`; rescue
restores 2/2. Matches verification_details.json section 2 = total_in 28 / kept 28 / dropped 0.

**RC-2 (SECONDARY, the fabrication SOURCE) — the narrative-paragraph LLM call has no anti-fabrication check.**
`contract_section_runner.py:456-470` calls `build_slot_narrative_prompt` (`slot_fill.py:594-654`), a
free-form "14-20 sentence / 300-450 word narrative" LLM call, and appends its output RAW. The structured
slot-fills get a verbatim-substring guard (`parse_slot_fill_response`, slot_fill.py:114-187); the narrative
does NOT — its only control is a prompt string ("strict_verify will reject hallucinations"), which V4 Pro
ignored, inventing "14%" (vs source 15%), "35%", "two months", "attrition", CSAT, "partial-equilibrium".

**RC-3 (TERTIARY, latent) — integer check is intersection, not subset.**
`provenance_generator.py:1345`: a sentence passes if ANY one of its integers is in the span (not all).
Not load-bearing here (14/35 overlap nothing), but a latent smuggling vector ("improved 15% over 14 months"
would pass on the 15 alone).

## FIX PLAN (why each works)

**Fix A — drop-reason guard on the rescue (minimal, HIGH confidence, smoke-proven).**
`contract_section_runner.py:515-518`: never rescue a sentence dropped for a numeric reason
(`number_not_in_any_cited_span`, `no_integer_overlap_any_cited_span`). WHY it works: the rescue's purpose
(undo content-overlap false-drops on legitimately verbatim slot prose) is orthogonal to numeric drops, so
excluding numeric drop-reasons closes the 14%/35% leak WITHOUT re-introducing the SURPASS-5 regression and
WITHOUT over-dropping the 8 honest "not extractable" slot gap-disclosures (which drop for content-overlap,
not numeric). SMOKE-PROVEN: with the guard, 14%/35% stay DROPPED, 15% stays KEPT.
ACCEPTANCE: the 3 smoke scripts show S1/S2 FAIL and S3(15%) PASS after the guard.

**Fix B — STREAM SEPARATION (the real structural fix, MEDIUM-HIGH confidence).**
The M-69 rescue must protect ONLY the deterministic verbatim slot-fill prose (`render_slot_prose`), NOT the
free-form narrative paragraph. Tag narrative-stream sentences and make them rescue-INELIGIBLE — they must
pass `verify_sentence_provenance` on their own. WHY it works: it removes the rescue blanket from the exact
stream that fabricates, so the QUALITATIVE fabrications (attrition/CSAT/partial-equilibrium — which pass the
content-overlap floor and only the entailment judge could catch) are also no longer auto-rescued. Fix A
alone does NOT catch these (they have no fabricated integer); Fix B does.
ACCEPTANCE: re-run Q72; the Generative_AI section must show dropped>0 and the report must not contain
"35 percent"/"attrition"/"partial-equilibrium" unless present in the [6] span.

**Fix C — anti-fabrication guard on the narrative path (defense-in-depth, MEDIUM).**
Give `build_slot_narrative_prompt` output the same verbatim/entailment discipline as slot-fills, OR constrain
the prompt to only restate already-verified field payloads (no new numbers/specifics). WHY: attacks RC-2 at
the source so there's nothing to rescue. Higher effort; B is the cleaner gate.

## Honest residual / risk
- Fix A is proven for the numeric fabrications (14%, 35%) only. The qualitative fabrications (attrition,
  CSAT, partial-equilibrium) pass the content-word floor and depend on the entailment judge — Fix A does NOT
  catch them. The COMPLETE fix is A+B (B removes the rescue from the narrative stream entirely).
- Over-drop risk: B could drop some legitimate narrative sentences that ARE entailed; that is the correct
  conservative behavior for a span-grounded clinical system (better to drop than to assert unsupported).
- This is a PRODUCTION faithfulness bug in POLARIS's core promise; it is more important than any Q72
  completeness rerun.

## Codex gate verdict (REVISE_PLAN — root cause CONFIRMED, plan made more complete)
Codex independently confirmed: root_cause_correct = YES; fix_A_closes_numeric_leak = YES (it ran the 8 real
"not extractable" disclosures → they drop for `no_content_word_overlap`, NOT numeric, so Fix A's drop-reason
guard correctly PRESERVES them); fix_B_needed_for_qualitative = YES. Required additions before implementing:
- **Fix A detail:** there is no scalar `drop_reason`; inspect the `failure_reasons` LIST prefixes.
- **Fix D (NEW, Codex-reproduced):** `provenance_generator.py:1345` integer check is INTERSECTION not subset —
  "15 percent over 35 weeks" passes against a span containing only 15. Require ALL sentence integers present in
  cited spans (subset), keeping the local-window fallback for missing integers. Without this, a mixed
  supported+fabricated integer claim still leaks.
- **Fix B design:** do NOT infer stream from prose shape. Deterministic + narrative prose are JOINED before
  rewrite/verify (`contract_section_runner.py:483`), so no stream marker survives. Carry explicit sidecar
  stream metadata through sentence splitting, OR run separate verifier passes per stream.
- **Fix C is REQUIRED, not optional:** B only prevents laundering of DROPS; it does not stop qualitative
  narrative claims that PASS the entailment judge (or runs under off/warn mode). The narrative anti-fabrication
  guard is required for deterministic qualitative closure.
- **Regulatory stream (M-70 `render_regulatory_prose`):** another LLM-written stream under the same rescue
  blanket; decide rescue-ineligible OR strengthen its parser.
COMPLETE Codex-gated fix = A (failure_reasons guard) + D (integer subset) + B (explicit stream metadata +
per-stream verify) + C (narrative anti-fabrication, required) + regulatory-stream classification.

## Smoke artifacts (re-runnable)
- outputs/q1_run9/smoke_brynjolfsson_leak.py  — verifier drops 14%/35%, keeps 15% (I ran: confirmed).
- outputs/q1_run9/smoke_contract_rescue_leak.py — rescue restores both (I ran: confirmed).
- outputs/q1_run9/smoke_exact_sentences.py — byte-exact kept strings drop in verifier → localizes to rescue.
