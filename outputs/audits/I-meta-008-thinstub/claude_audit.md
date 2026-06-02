# Dual-audit reconciliation — I-meta-008 #1034 (thin oa_full_text stub blocks OpenAlex)

## Process (per operator directive 2026-06-02 + §-1.1)
Two INDEPENDENT auditors ran in PARALLEL on the v2 diff + the run-6 frame evidence:
- **Claude** independent auditor (general-purpose agent, read frame_fetcher.py + diff + tests + run6 evidence line-by-line).
- **Codex** independent auditor (`env -u OPENAI_API_KEY codex exec`, gpt-5.5 xhigh, 69,936 tokens) — `.codex/I-meta-008-thinstub/codex_audit.txt`.

## Both verdicts: APPROVE — zero P0, zero P1.

### Consensus (both auditors agreed)
- `acemoglu_automation` (the target bug): FIXED. 540-char OA stub < 1200 → Step 4 OpenAlex fires → 1331-char abstract beats the stub → OPEN_ACCESS / openalex_abstract.
- `acemoglu_robots`: already addressed by #1033 (OpenAlex 688 → ABSTRACT_ONLY).
- `autor` / `frey_osborne`: unchanged IFF their run-6 oa_full_text ≥ 1200 (both flagged this as a dependency, not independently verifiable from the evidence file — accepted; both got real content in run-6).
- `brynjolfsson` / `eloundou`: NOT helped by OpenAlex by design (CrossRef abstract present blocks Step 4). The "effect number not extractable" is a generator-extraction / source-depth residual, NOT a fetch bug. eloundou's OpenAlex abstract is only 56 chars (unfixable via OpenAlex); brynjolfsson's 1113-char OpenAlex abstract makes a future "fire-OpenAlex-when-crossref-thin" a candidate follow-up, out of scope here.
- `fourth_industrial_revolution`: url-pattern path, out of scope.

### Findings addressed (commit 2)
- **P2 (Claude, §-1.1 clinical-safety):** a thin stub could outrank a SHORTER real abstract → a paywall junk stub becoming the extracted span is the hazard. FIX: `_pick_richest_abstract` admits the stub ONLY when no real abstract resolved (`if partial_full_text and not candidates`). Now a real abstract of ANY length beats the stub. Test `test_short_real_abstract_beats_longer_stub`.
- **P2 (BOTH):** the provenance edge (any_oa_url True + full-text empty + no abstract → now METADATA_ONLY, fixing a latent v1 OPEN_ACCESS-with-empty-quote bug) lacked a test. FIX: `test_oa_locator_but_all_text_empty_is_metadata_only`.

### Not actioned (documented, non-blocking)
- **P2 (Claude):** the helper unit test asserts a crossref-vs-openalex equal-length tie that the orchestrator's mutual-exclusion gating can never produce. Harmless — it tests the helper's documented contract in isolation. Kept.
- **P2 (Codex):** the ProvenanceClass enum docstring reads broader than the (pre-existing) any_oa_url→OPEN_ACCESS behavior. Pre-existing, out of scope for this fetch fix.

## Honest residual (both agree)
After v2, `brynjolfsson`/`eloundou` may still read "effect number not extractable" — a generator-extraction / paywalled-full-text issue, NOT a thin-stub fetch bug. The diff's claimed target (acemoglu_automation thin-stub) is correctly and verifiably fixed. Net: v2 grounds 2 more foundational canonical papers (Acemoglu Automation + Robots) with real verified abstract text.

## Tests
131/131 (frame_fetcher 57 + slot_fill 49 + manifest 25). Codex also ran the targeted suite via `python -m pytest` and reported pass.
