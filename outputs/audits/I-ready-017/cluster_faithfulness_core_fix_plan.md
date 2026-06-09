# Cluster: FAITHFULNESS VERIFICATION CORE — Recommended Fix Approach (I-ready-017)

Planning only. No code edited. Each bug: SOTA research (cited) → code cross-check → fix
(file:line) → smoke test → §-1.1 line-by-line audit method → dependencies/risk.

Cluster bugs: BUG-01 (CoT scratchpad promoted to VERIFIED prose), BUG-02 (4-role verifier
evaluates whole doc not cited span), BUG-03 (empty/boilerplate counted VERIFIED), BUG-11
(unsupported S3 numerics ship with no disclosure).

---

## BUG-01 — Generator chain-of-thought scratchpad promoted into report.md as VERIFIED prose

### SOTA (2025-2026)
- Canonical truncation signal is `finish_reason == "length"` (OpenAI/vLLM/Azure docs); the
  punctuation heuristic ("ends mid-sentence") is explicitly the *less reliable* fallback.
  (community.openai.com truncation guide; vllm forums; stackviv max-tokens guide.)
- "Reasoning Models Sometimes Output Illegible Chains of Thought" (arXiv 2510.27338): later
  CoT portions are far more likely to be illegible; truncating CoT and forcing it as the
  answer degrades correctness — i.e. promoting a truncated reasoning trace is known-bad.
- "Safer Reasoning Traces: Measuring and Mitigating CoT Leakage" (arXiv 2603.05618) and
  "Leaky Thoughts" (arXiv 2506.15674): models struggle to separate reasoning from answer;
  reasoning content leaks into answers — the exact failure here.

### Code cross-check (CONFIRMED + sharpened beyond the audit)
- The promotion is at `openrouter_client.py:2453-2503` (the `elif len(result.reasoning.strip())
  >= 100:` branch), NOT only 2470-2497. The I-bug-089 truncation guard is `2470-2473`:
  `if ("[#ev:" not in result.reasoning and not _reasoning_clean.endswith((".","!","?",'"')))`.
  The scratchpad CONTAINED `[2]`/`[#ev:` tokens, so the `"[#ev:" not in reasoning` conjunct
  was False → the AND short-circuited → the guard did NOT fire → reasoning promoted to content
  verbatim (2489-2497). Root cause stated precisely: **the guard's AND is too weak — an
  embedded citation token defeats it.**
- SOTA signal availability: `finish_reason` IS parsed mid-stream at `openrouter_client.py:1215`
  but is **discarded** — `_accumulate_sse` returns `(content, reasoning, usage, served)` only
  (`:1266`), and `LLMResponse` (`:795-809`) has NO `finish_reason` field. So gating on
  `finish_reason=="length"` requires threading it through `_accumulate_sse` → `_read_stream`
  → `LLMResponse`. The audit's `output_tokens == max_tokens` is the available proxy but
  false-drops a generation that legitimately ends exactly at budget.

### Recommended fix (two layers; layer 1 is THE fix)
1. **Generator/promotion (primary, deterministic):** thread `finish_reason` out of the SSE
   accumulator into `LLMResponse.finish_reason`; in the `>=100` reasoning-promotion branch
   (`:2453`) refuse to promote when `finish_reason == "length"` (or, if finish_reason is
   genuinely absent for a provider, fall back to `output_tokens >= max_tokens` AND the
   existing no-terminal-punct check) → raise `ReasoningFirstTruncationError` (the SF-15
   fail-loud path already exists at `:2476`). This is SOTA-correct and matches the audit's
   intent while using the canonical signal, not just token-equality.
2. **Verifier-side discourse floor (defense-in-depth):** the audit proposes a meta-discourse
   denylist in strict_verify. §-1.1 TENSION: the operator repeat-bans pattern/string-presence
   checks. So (a) keep layer 1 as the real fix; (b) implement the floor as a CONFIG-DRIVEN
   (LAW VI) advisory that drops sentences whose semantic content narrates the writing act
   (`final attempt:`, `too choppy`, `I'll use the exact phrase`, `that's N more words`), with
   the phrase list in config not hardcoded; (c) note explicitly that span-scoped NLI (BUG-02
   fix) does NOT catch this — the scratchpad embeds verbatim source quotes so it entails. That
   is why the generation-side guard is the load-bearing fix.

### Smoke test
- Offline unit: feed the I-bug-089 branch an `LLMResponse` with reasoning ending
  `"...I need to add about 124 more words."`, `finish_reason="length"`, output==max_tokens,
  AND an embedded `[2]` token → assert `ReasoningFirstTruncationError` raised (the embedded
  token must NOT defeat the guard). Add the regression fixture from the actual scratchpad text.
- Cheap live: 1 `generate()` call with a tiny `max_tokens` (e.g. 64) on V4 Pro → assert the
  truncated reasoning is NOT promoted (raises), not shipped as content.

### §-1.1 line-by-line audit method
Re-run the production verifier over the drb_72 artifacts after the fix and confirm the
specific scratchpad-derived claims **00-003 / 00-004 / 00-018** (currently graded S1/VERIFIED
in `four_role_claim_audit.json`, NLI-entailed in `nli_verification.json`) no longer exist as
claims (the section regenerates or fails loud). Open `report.md` `### Foundational_Theory`
(L20-28) and confirm the literal strings "Final attempt:", "But that might be too choppy.[2]",
"That's three sentences from the thesis.[2]" are ABSENT. A fresh synthetic unit test alone is
NOT the proof — the proof is the named drb_72 claim IDs changing verdict/disappearing.

### Dependencies / risk
No upstream dependency. **Highest-stakes P0; gate-blocker.** Risk MEDIUM: threading
finish_reason touches the hot streaming path (every LLM call) — additive field, low blast
radius, but must not break the non-streaming/`application/json` fallback path. Shares the
token-starvation trigger with BUG-09 (out of cluster) — same fix prevents the silent
contract-slot "pass."

---

## BUG-02 — Four-role verifier evaluates the WHOLE source doc, not the cited [start:end] span

### SOTA (2025-2026)
- ALCE (arXiv 2305.14627) citation quality = the *cited passage* must support the claim, not
  "supported somewhere in the corpus."
- Auto-GDA (ICLR 2025, arXiv 2410.03461): grounding verification operates on the retrieved
  *context window* fed to a lightweight NLI checker; the unit of verification is the passage,
  not the whole KB.
- "Verified Misguidance: Structural Citation Failures in Search-Augmented LLMs"
  (arXiv 2605.28565) and the Attribution/Citation/Quotation survey (arXiv 2508.15396): a
  citation that points at the wrong span is itself a faithfulness failure even when the fact
  is true elsewhere. SemanticCite (per Aman's AI factuality primer): full-text content
  verification, not existence/somewhere-in-doc.

### Code cross-check (CONFIRMED — and the seam violates its OWN prompt contract)
- `native_gate_b_inputs._resolve_evidence` (`:354-375`) builds `EvidenceDocument(doc_id=
  evidence_id, text=text)` with the WHOLE `record[_RECORD_TEXT_KEY]` (`:367`). The cited
  offsets exist on each `ProvenanceToken.start/end` (`provenance_generator.py:407-415`) but the
  call site (`native_gate_b_inputs.py:420-421`) passes only `[token.evidence_id ...]` — **start
  /end are discarded.**
- `sentinel_adapter.py:280` fills the decomposition prompt's `{span}` = `"\n\n".join(doc.text
  for doc in evidence_documents)` = whole doc. But `_DECOMPOSITION_PROMPT` (`:207`) literally
  promises "a CLAIM that cites ONLY that span ... supported by the SPAN alone." **Input ≠
  contract.** That makes BUG-02 unambiguous: the certified Sentinel's 0-false-accept guarantee
  was measured on a true span; production feeds it the whole doc, voiding the guarantee.
- `role_pipeline.py:314` hands the Judge the same join — same defect downstream.

### Discriminator run offline against the real artifacts (06-004 / ev_015)
- ev_015 `direct_quote` len 3890. Claim 06-004 = "AI adoption raises demand for AI skills",
  cites `[#ev:ev_015:2900-3700]`.
- Support ("higher demand for AI-related skills") sits at doc pos **751-769** — OUTSIDE
  [2900:3700]. Cited window [2900:3700] is about productivity/wage %, not skills demand.
- Content-overlap test (claim content words {adoption, demand, raises, skills}):
  - vs CITED window [2900:3700]: overlap = {adoption} only → **1 < the ≥2 floor → would FAIL**.
  - vs whole doc (current 4-role behavior): trivially passes → **the false-accept**.
  - vs a bounded ≤400-byte local window at pos ~600-1000: overlap = {adoption, demand, skills}
    = 3 → **PASSES** strict_verify's bounded-window policy.
- **Conclusion:** 06-004 is the *tolerated imprecise-citation* case — the fact is in the
  source, just outside the cited byte range. Exact-slice would DROP it; strict_verify's
  bounded-window TOLERATES it. So the fix's tolerance level is a Codex/operator policy call;
  the defect (whole-doc over-acceptance) is unambiguous either way.

### Recommended fix
Thread `(start, end)` from `verification.tokens` to `_resolve_evidence` and slice each
`EvidenceDocument.text` to the cited window before `run_claim_pipeline` (so Sentinel/Judge see
exactly what the prompt promises). **Do NOT silently adopt either tolerance** — RECOMMEND
mirroring strict_verify's `_find_local_support_window`/`_find_local_content_window` so BOTH
the mechanical pre-check and the authoritative seam share ONE windowing policy (no layer
weaker than the other). If any imprecise-citation tolerance is retained, surface it as an
"imprecise_citation" advisory on the claim (clinically, a citation pointing at the wrong span
IS a faithfulness defect — never silently accept). Exact-slice-vs-bounded-window is the
explicit Codex decision; present both with the 06-004 evidence above.

### Smoke test
- Offline unit: build a 2-token claim where the support is at doc pos 100 but the cited token
  is `:2000-2400`; assert the seam input span does NOT contain the support under exact-slice
  (and, under bounded-window, that a far-away 400-byte window is NOT silently joined). Add the
  06-004/ev_015 case as a real fixture.
- Cheap live: one Sentinel decomposition call on 06-004 with the cited-window span → assert
  the "demand for AI skills" atom is `unsupported` (currently SUPPORTED on whole-doc text).

### §-1.1 line-by-line audit method
Re-run the 4-role seam over drb_72 with the fix; confirm **06-004-d42337ed** flips from
SUPPORTED→UNSUPPORTED (its support is provably outside the cited window). Then re-verify the
205/215-sub-span population: spot-check that genuinely-in-span claims (the ~15 clean numeric
claims in §4 of the audit, e.g. 14.4% wage @ ev_015 [2900:3700] which IS in the cited window)
remain VERIFIED — proving the fix is precise, not a blanket recall cut. Compare claim-by-claim
verdict deltas against `four_role_claim_audit.json`.

### Dependencies / risk
No upstream dependency. **P0; gate-blocker.** Risk MEDIUM-HIGH: this is the authoritative
release gate (`manifest.judge_verdicts.superseded_by_four_role_seam=true`); tightening it
shifts recall, and the exact-slice-vs-window choice directly changes how many claims survive.
Must land with the windowing-policy decision explicit so it does not diverge from strict_verify.

---

## BUG-03 — Empty sentences + "not extractable" boilerplate counted VERIFIED

### SOTA (2025-2026)
- FActScore / VeriFastScore (arXiv 2505.16973): a "claim" is an atomic *factual assertion*;
  content-free strings are not claims and must not count toward precision.
- MedRAGChecker (arXiv 2601.06519): decomposes into atomic claims and tags under-evidence /
  contradiction; a non-assertion is excluded before scoring — empty "claims" inflating the
  denominator is a known measurement bug.

### Code cross-check (CONFIRMED — precise mechanism)
- `provenance_generator.verify_sentence_provenance` content-floor is gated `if sentence_content:`
  at `:1411`. `_content_words` (`:867-874`) returns `set()` for an empty/token-only sentence
  (a sentence that reduces to `.` after token strip). So `if sentence_content:` is False →
  **the floor is SKIPPED → the empty sentence passes as verified.** Confirmed in
  `verification_details.json`: 4 Foundational_Theory.kept sentences reduce to `.` with
  `verifier_pass=True`, and `nli_verification.json` independently rates them NEUTRAL ("empty,
  no factual assertions").
- The 16 "X: not extractable from available primary content" lines are a DIFFERENT sub-case —
  they DO have content words, so they clear the floor; this is the same class as BUG-01's
  process-narration / non-assertion, and a false non-extractability claim citing a NARROW span
  that excludes the data returns NLI NEUTRAL and passes.

### Recommended fix
Two distinct changes (do NOT present as one mechanism):
1. **Empty-sentence precondition** (this issue): before the `if sentence_content:` floor at
   `:1411`, add — if `_content_words(sentence_stripped)` is empty AND `_decimals_in`/`_numbers_in`
   are empty → `is_verified=False`, reason `empty_or_contentless_sentence`. Mirror in
   `clinical_generator/strict_verify.py:268`.
2. **"not extractable" boilerplate** → FOLD into the BUG-01 verifier discourse-floor issue
   (same non-assertion class), and for any "not extractable/not provided" negation claim, judge
   against the FULL cited row (fail-closed), not the narrow window — closes the
   qualitative-negation-escapes-regex blind spot.

### Smoke test
Offline unit: feed `verify_sentence_provenance` a sentence that is only
`[#ev:acemoglu_restrepo_automation_tasks:0-800].` → assert `is_verified is False`,
reason `empty_or_contentless_sentence`. Use the 4 actual empty sentences from
`verification_details.json` as fixtures.

### §-1.1 line-by-line audit method
Re-run the verifier over drb_72; confirm the 4 empty Foundational_Theory.kept sentences (the
`[#ev:...:0-800].`×2 pairs) drop to `verifier_pass=False`, and the 16 "not extractable" lines
(count them in `report.md` — currently exactly 16) are dropped or disclosed. Confirm the kept
count (176) decreases by the contentless count and that no genuine claim is collateral-dropped.

### Dependencies / risk
**Downstream/shared-root with BUG-01** (same strict_verify missing-semantic-floor). Best
landed in the same verifier-floor issue as BUG-01 layer 2. P1. Risk LOW for the empty-sentence
precondition (additive guard); the boilerplate half inherits BUG-01's §-1.1 config tension.

---

## BUG-11 — Unsupported S3 numeric claims ship with NO disclosure

### SOTA (2025-2026)
- "The Energy to Say No: Pre-Generation Abstention for Safety-Critical Medical RAG"
  (openreview MtKSNKnNzN) + "Energy Landscapes Enable Reliable Abstention" (arXiv 2509.04482):
  in safety-critical RAG, robust abstention/disclosure is a first-order requirement — the
  system must surface what it could not ground, not silently drop it.
- MedRAGChecker (arXiv 2601.06519): explicitly reports an "under-evidence" rate as a
  first-class output — every unsupported claim is disclosed, regardless of how it is scored.

### Code cross-check (CONFIRMED)
- `release_policy.apply_*` filters `material_rows = [row for row in d8_rows if row.is_material]`
  at `:197`, where `is_material` = severity in `_MATERIAL_SEVERITIES=("S0","S1","S2")` (`:49`,
  `:102-103`). So S3 UNSUPPORTED rows skip BOTH the rewrite loop (`:213`) AND the residual gap
  (`:226`). Every claim STARTS at S3 (`native_gate_b_inputs.py:425` default observe-only) and is
  only raised when it covers a required contract entity — off-contract numerics stay S3.
- Confirmed in `manifest.four_role_evaluation`: 29 UNSUPPORTED, but `needs_rewrite`=17 (all S1)
  and `gaps`=1 (coverage). The 13 UNSUPPORTED-not-rewritten are S3, incl. numerics "~14.4%
  higher wages" (04-001), "ILO 7.8%" (05-003), "global GDP by 7%" (06-000), "£100 million"
  (06-011). `report.md` has those figures and ZERO occurrences of "unsupported"/"residual"/"S3".

### Recommended fix (SPLIT — per advisor)
1. **Disclosure (this issue; low-risk, clearly right):** decouple disclosure from gating. Even
   if S3 stays non-gating, emit a VISIBLE advisory gap (new gap kind, e.g.
   `advisory_unsupported_offcontract`) or an "Unverified claims" appendix for EVERY
   UNSUPPORTED/FABRICATED row regardless of severity. Iterate ALL `d8_rows` (not just
   `material_rows`) for the disclosure channel; keep the material filter for the GATING channel.
   Backed by MedRAGChecker "under-evidence rate" + "Energy to Say No" abstention-surfacing.
2. **Severity-model change (route to Codex/operator, do NOT bundle):** "reconsider defaulting
   off-contract numeric claims to S3" changes the severity model itself — that is a policy
   decision for Codex/operator, not a unilateral code fix.

### Smoke test
Offline unit: an UNSUPPORTED S3 numeric row → assert the release decision produces a disclosed
residual gap (advisory) even though `release_allowed` is unchanged by it. Use 04-001/05-003/
06-000/06-011 as fixtures.

### §-1.1 line-by-line audit method
Re-run release_policy over drb_72 claim rows; confirm each of 04-001, 05-003, 06-000, 06-011
produces a disclosed residual/advisory entry, and that the rendered report (or manifest gap
list) now contains an explicit "unverified/unsupported" disclosure for each — currently zero.
Confirm `release_allowed` and the coverage HOLD are unchanged (disclosure is additive, not a
new gate).

### Dependencies / risk
No upstream dependency. P2 (disclosure half). Risk LOW — additive reporting channel; the
gating logic and `release_allowed` are untouched. The severity-model half is operator-gated and
explicitly out of this fix's scope.

---

## Cluster dependency + sequencing summary
- BUG-01 (P0) and BUG-02 (P0) are independent gate-blockers; either can land first.
- BUG-03 (P1) is shared-root with BUG-01 (same verifier floor) — land in the same verifier
  issue as BUG-01 layer 2.
- BUG-11 disclosure half (P2) is fully independent; the severity-model half is operator-gated.
- §-1.1 cross-cut: every smoke test + audit method is anchored to THIS run's claim IDs
  (00-003/00-004/00-018, 06-004, the 4 empty + 16 "not extractable", 04-001/05-003/06-000/
  06-011). Proof = re-running the verifier over the drb_72 artifacts and confirming each named
  ID's verdict change — not a fresh synthetic test alone.
