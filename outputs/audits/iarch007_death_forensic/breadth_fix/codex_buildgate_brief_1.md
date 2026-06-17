# Codex DIFF gate — I-arch-007 BREADTH FIX (item 1, contract + resolver multi-citation) — iter 1/3

HARD ITERATION CAP: 5 per document. This is iter 1 of 5.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd by Claude on remaining-non-P0/P1 findings; do not bank issues for iter 6.
- If you detect "I'm holding back a P1 to surface in the next round" — DON'T. Surface it now. The 5-cap means iter 6 doesn't exist; banked findings die at iter 5.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

(Project caps the diff-gate at iter 3; the 5-cap directive above is the canonical wording. Same rules apply.)

---

## 0. STATIC REVIEW ONLY — DO NOT run pytest / DO NOT run the pipeline

You are at `-C C:/POLARIS -s read-only`. Read files from disk directly; do NOT execute pytest, do NOT spawn the pipeline, do NOT run any sweep. This is a static code review against the approved design. Reading files is fine; running them is not.

## 1. WHAT THIS DIFF IS (read this first — it reframes invariants (a)-(e))

This gate reviews the **item-1 breadth fix**, scoped to exactly the files the task names: `src/polaris_graph/generator/contract_section_runner.py`, `src/polaris_graph/generator/provenance_generator.py`, and the breadth tests.

**The diff is TEST-ONLY. Both prod files are UNCHANGED vs HEAD — BY DESIGN.** This is not missing work. Per the approved design `outputs/audits/iarch007_death_forensic/breadth_fix/BREADTH_FIX_DESIGN.md` §1.1–§1.2, the whole-basket inline multi-citation render (item 1) is **already wired and faithful in the live tree** (it landed earlier — commit `a8b6ea3f` #1257 + the FIX-1 PART-B chain). Re-implementing it now would be fake-working (LAW II) and would collide with the committed death-fix. Per design §1.2 ("No code change in item 1 beyond the test"), item 1's deliverable is **the proving tests only**.

The two NEW (untracked, intent-to-add) files under review:
- `tests/polaris_graph/generator/test_breadth_corroborator_faithfulness_iarch007.py` (240 lines) — contract-path net-new faithfulness control.
- `tests/polaris_graph/generator/test_resolver_multicitation_iarch007.py` (318 lines) — resolver-path multi-citation prove-only + helper-level negatives.

**Out of scope for THIS gate (different owners, do NOT flag their absence):**
- The 437 unbound-source enrichment path (`weighted_enrichment.py` + `multi_section_generator.py`) — separate owner/gate per design §2.
- Item 3 (attaching DIFFERENT-cluster / non-contract sources as contract corroborators) — **deliberately NOT implemented**; blocked by the contract-entity wall and would relax anti-cross-claim (§-1.1 lethal). See the scope-lock at `contract_section_runner.py` `def`-region around the "SCOPE NOTE (Codex iarch007 P1 #2)" docstring (search that string).

## 2. THE APPROVED DESIGN (your oracle)

Read in full: `outputs/audits/iarch007_death_forensic/breadth_fix/BREADTH_FIX_DESIGN.md` (§1.1 "Current state — VERIFIED, do NOT re-implement", §1.2 "residual = test only", §1.3 faithfulness-neutrality, §4 "the test that proves it").

## 3. THE ALREADY-WIRED PROD CODE THE TESTS PIN (read by stable symbol, NOT line number — lines drift)

In `src/polaris_graph/generator/provenance_generator.py`:
- `build_basket_supports_by_cluster(...)` — SUPPORTS-only per-cluster index (keys only on `span_verdict == "SUPPORTS"`).
- `verified_corroborators_for_tokens(...)` — the shared anti-cross-claim core. Two load-bearing guards to confirm the tests actually exercise:
  - **single-cluster guard**: `if len(_ccids) != 1: continue` — a token mapping to MULTIPLE clusters (ambiguous claim) expands NOTHING.
  - **pool-resolution guard**: `if _support_eid not in seen and _support_eid in evidence_pool:` — a SUPPORTS member with no `evidence_pool` row is NEVER surfaced (no real source ⇒ no citation).
- `resolve_provenance_to_citations(...)` / `resolve_provenance_to_citations_with_count(...)` — the resolver render; baskets-absent ⇒ legacy single-citation (OFF path byte-identical).

In `src/polaris_graph/generator/contract_section_runner.py`:
- The V30 contract path hoists `build_basket_supports_by_cluster` once, threads baskets + `cluster_id_by_evidence` into `resolve_provenance_to_citations`, and per-sentence appends each corroborator via `verified_corroborators_for_tokens` (search those symbol names).
- The **contract-entity wall** (`plan.contract_entities_by_id.get(...)` → `if ... is None: continue`) and the **scope-lock** docstring ("SCOPE NOTE (Codex iarch007 P1 #2)") that records cross-cluster attachment as out-of-bounds.

Confirm these symbols/guards are present and UNCHANGED vs HEAD. If you believe the diff secretly edits prod code, say so with the exact hunk — but `git diff HEAD -- <both prod files>` is empty (Claude verified).

## 4. WHAT TO VERIFY — invariants (a)-(e), reframed for a test-only diff

For a test-only diff, "no gate relaxed / no fabricated citation / OFF byte-identical" means the **tests truthfully PIN the existing faithful behavior and a passing run cannot mask a relaxation**. Verify, claim-by-claim against the actual test source:

**(a) Threads/adds ONLY same-cluster verified-SUPPORTS basket members already in `evidence_pool`; cannot introduce a fabricated/unsupported/cross-cluster citation.**
- `test_resolver_multicitation_iarch007.py`:
  - `test_core_single_cluster_token_surfaces_all_other_supports` — whole basket surfaces; UNSUPPORTED member absent.
  - `test_core_multi_cluster_token_never_expands_cross_claim` — asserts `corro == []` for a multi-cluster token (the `len(_ccids) != 1` guard). Confirm the fixture genuinely sets a 2-cluster binding for the token.
  - `test_core_excludes_member_absent_from_pool` — `del pool["ev_d"]` then asserts ev_d excluded (the pool-resolution guard).
  - `test_supports_index_keeps_only_supports_members` / `_skips_cluster_with_no_supports` — index is SUPPORTS-only; advisory `total_clustered_origin_count` never indexed.
- `test_breadth_corroborator_faithfulness_iarch007.py`:
  - `test_contract_path_supports_member_absent_from_pool_never_surfaces` — drives REAL `run_contract_section` (via the shared harness `_run`); a SUPPORTS, same-cluster, pool-ABSENT phantom must appear NOWHERE (biblio + inline), while an in-pool corroborator DOES surface (non-vacuous positive companion). Confirm the phantom is truly absent from the pool AND in the basket index, so the only thing excluding it is the pool-resolution guard.

**(b) Generates NO new textual claim.** These are tests + a fake/injected LLM; the REAL components are `strict_verify` + the citation rewriter. Confirm no test asserts a claim sentence not produced by the existing render path, and the injected LLM is not used to smuggle a hand-authored claim into `verified_text` that bypasses verification.

**(c) NO gate relaxed (strict_verify / NLI / 4-role / span-grounding / floor / sentinel).** The tests do not modify any gate. Confirm: (i) the contract-path test uses the REAL contract driver (not a stub that skips verify); (ii) the resolver tests build their cited sentence via REAL `verify_sentence_provenance` (not a hand-faked `SentenceVerification`) — see `_one_cited_sentence`; (iii) no test monkeypatches/relaxes a threshold.

**(d) OFF/degrade path byte-identical.** Confirm:
- `test_resolver_off_path_byte_identical` — no basket args ⇒ only the cited source, exactly one inline marker, legacy 5-key biblio row.
- `test_resolver_one_param_absent_stays_legacy` — baskets-without-binding OR binding-without-baskets ⇒ legacy single citation (param-presence gate).
- `test_contract_path_pool_absent_member_does_not_change_render` — `verified_text` BYTE-IDENTICAL with vs without the pool-absent phantom (clean exclusion, no renumbering side effect).

**(e) Does not revert any death-fix change.** Both new files are purely ADDITIVE (new files; they IMPORT the shared harness `test_lane_section_arch005_contract_path` and `credibility_pass` symbols; they modify nothing the death-fix owns). Confirm no edit to `multi_section_generator.py`, `credibility_pass.py`, `entailment_judge.py`, or any committed death-fix test. The two prod files are unchanged vs HEAD.

## 5. ESCALATION NOTE

If you find a GENUINE faithfulness hole in the **already-wired prod code** (not the tests) — e.g. the anti-cross-claim or pool-resolution guard is actually bypassable — that is a NEW-ISSUE escalation, not an item-1-test fix. Flag it as P0/P1 with the exact symbol + reasoning; the only files Claude can edit this iter are the two test files. A test gap (a control that doesn't actually exercise the guard it claims) IS an in-scope P0/P1 — flag it.

## 6. OUTPUT — emit EXACTLY this schema; FINAL line must be the verdict

```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
remaining_blockers_for_execution: [...]
```

APPROVE iff zero P0 AND zero P1. The VERY LAST line of your output must be `verdict: APPROVE` or `verdict: REQUEST_CHANGES` (parsed mechanically). If REQUEST_CHANGES, give concrete per-finding bullets naming the exact test/assertion.
