HARD ITERATION CAP: 5 per document. This is iter 2 of 5. (iter-1 REQUEST_CHANGES P1 — fail-closed must be structural — adopted in the REVISED SPEC at the END; the mechanical match-gate supersedes the analyst prompt-advisory of §CONCRETE PROPOSAL above.)
- Front-load ALL real findings. Reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

RULE NOW — emit the YAML verdict block FIRST. APPROVE this CONCRETE plan or REQUEST_CHANGES with specifics.
CLINICAL-SAFETY-RELEVANT (it feeds generation): the reuse pool must be FAIL-CLOSED — a reused claim earns
NO citation and NO provenance; it is re-grounded by strict_verify against THIS question's corpus or omitted.
NO SPEND offline (the read is a local sqlite query; default-OFF flag; no network/model).

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex brief-gate (iter 1) — PR10: wire the KG read-path into generation, fail-closed + campaign-scoped (#948)

Codex-verified gap (#941): `VerifiedClaimGraphStore` is WRITE-ONLY — `query_related_claims` /
`find_contradictions` are referenced only by the store + its tests; nothing in `src/` reads the reuse pool
back into generation → ZERO snowball reuse at runtime. Also the store is per-question `run_dir`, so even if
read it would always be empty (fresh db per question). Acceptance: call `query_related_claims` back into
generation (even lexical reuse beats zero), campaign-scope the KG across the 5 questions, FAIL-CLOSED.

## GROUNDED FACTS (verified; do not re-explore)
- `VerifiedClaimGraphStore.__init__` accepts EITHER `db_path` OR `run_dir` (exactly one). `write_claim`
  stores ALL verdicts but only VERIFIED rows are `reusable=1` (anti-poisoning, enforced in-store).
  `query_related_claims(claim_text)` returns ONLY reusable (VERIFIED) prior claims (lexical relatedness).
- The store is written in `sweep_integration.run_four_role_evaluation` as
  `VerifiedClaimGraphStore(run_dir=run_dir)` — PER-QUESTION, AFTER generation+strict_verify. So nothing is
  reusable within a single question, and there is no cross-question pool.
- `run_honest_sweep_r3`: `out_root = outputs/honest_sweep_r3` (the CAMPAIGN root); `run_dir = out_root /
  domain / slug` (per question). The sweep iterates questions SEQUENTIALLY (each fully completes
  retrieval→generation→strict_verify→4-role KG-write before the next) — NO concurrent KG writers.
- `generate_analyst_synthesis` (analyst_synthesis.py:398) is the UNVERIFIED analyst layer; it is already
  hardened — `_screen_qualitative_negations` (PR3 #953) drops fabricated qualitative-negation safety
  sentences and `_scrub_ev_tokens` (PR7 #946) strips any ev-token. Its prose is demarcated as unverified and
  carries NO `[#ev:...]` provenance. The VERIFIED core (multi_section generator + strict_verify) is separate.

## CONCRETE PROPOSAL (fail-closed, campaign-scoped, default-OFF)
1. **Campaign-scope the KG (no concurrency risk — sequential sweep):** `run_four_role_evaluation` opens the
   store at a CAMPAIGN db (`out_root/"verified_claim_graph_campaign.db"`) instead of `run_dir`, threaded
   down as a `campaign_kg_db` param (default falls back to `run_dir` so existing callers/tests are
   unchanged). Question N's 4-role write lands in the shared db; questions 1..N-1's VERIFIED claims become
   the reuse pool for N.
2. **Read-path into the UNVERIFIED analyst layer (the safest injection point):** in `run_honest_sweep_r3`,
   BEFORE `generate_analyst_synthesis`, open the campaign KG READ-ONLY and `query_related_claims(question)`
   → a list of prior-VERIFIED related claim TEXTS (cap N, e.g. 5). Pass them to `generate_analyst_synthesis`
   as a new optional `prior_verified_context: list[str]` rendered as a clearly-labeled advisory block:
   "PRIOR-VERIFIED RELATED FACTS (from other campaign questions; ADVISORY ONLY — re-ground against THIS
   question's evidence pool or OMIT; these carry NO citation and NO provenance)." Claim TEXT only — NEVER
   the prior evidence ids (so the generator cannot cite them; strict_verify drops any ungrounded sentence).
3. **FAIL-CLOSED is structural:** the verified core (multi_section + strict_verify) is UNTOUCHED — a reused
   claim that survives into the analyst (unverified) layer carries no `[#ev:...]`, is scrubbed/screened by
   the existing PR3/PR7 guards, and is never presented as a verified finding. A reused claim cannot earn
   provenance because its evidence ids are never injected into the current corpus.
4. **Default-OFF flag `PG_SWEEP_KG_REUSE`** (it changes the analyst prompt). When off: no read, no prompt
   change (byte-identical to today). When on: advisory priming only.
5. Tests (offline, NO SPEND): campaign store shared across two `run_four_role_evaluation`-style writes →
   question-2 read sees question-1's VERIFIED claim, NOT its UNSUPPORTED one (anti-poisoning preserved);
   `prior_verified_context` renders the labeled advisory block; flag-off → analyst prompt unchanged + no
   read; reused claim text carries no evidence id (fail-closed); only VERIFIED reusable.

## Constraints / frozen
snake_case; explicit imports; no except:pass; fail-closed. UNTOUCHED: strict_verify, multi_section verified
generator, provenance, the §9.1 chokepoint, anti-poisoning (only VERIFIED reusable). ≤200 LOC.

## The real risks to rule on
1. Is the UNVERIFIED analyst layer the right (safest) injection point vs the verified generator vs an
   output-only artifact? (Claim: analyst layer — it is non-authoritative, already screened by PR3/PR7, and
   carries no provenance, so advisory priming is structurally fail-closed; the verified core is untouched.)
2. Campaign-scoping via a shared `db_path` across the sequential sweep — any concurrency / cross-question
   leakage / anti-poisoning risk? (Claim: sequential writes, only VERIFIED reusable, claim-text-only read.)
3. Could a reused claim be presented as a CURRENT verified finding or earn provenance? (Claim: no — text
   only, no evidence ids injected, strict_verify untouched, analyst layer demarcated unverified.)
4. Default-OFF correct, or should reuse be ON for the benchmark? (I propose OFF until a live smoke.)

APPROVE iff this campaign-scopes the KG, reads `query_related_claims` into the UNVERIFIED analyst layer as
advisory-only claim TEXT (no evidence ids, no provenance), keeps the verified core + strict_verify +
anti-poisoning untouched, is default-OFF, and is testable offline with NO SPEND.

---

## REVISED SPEC — Codex brief-gate iter-1 REQUEST_CHANGES adopted (binding). Iter 2.

**iter-1 P1 (fail-closed must be STRUCTURAL, not prompt-advisory):** correct — "re-ground or omit" as a
prompt instruction is insufficient for clinical-safety reuse. Replaced with a MECHANICAL match-gate (Codex
path B, mechanically enforced): a prior-verified claim is mechanically OMITTED before it ever reaches the
prompt UNLESS the CURRENT question's corpus independently supports it.

1. **Mechanical match-gate (new `match_prior_claims_to_current_corpus`)** — reuses strict_verify's OWN
   primitives so the gate is identical to the verified core's content rule: `from
   clinical_generator.strict_verify import _content_words, _decimals, _min_overlap_threshold`. A prior
   claim text is KEPT iff some current `evidence_rows[i]` satisfies BOTH (mirroring strict_verify §9.1.3
   checks (d)+(e)): `len(_content_words(claim) & _content_words(evidence.direct_quote)) >=
   _min_overlap_threshold()` AND `_decimals(claim) <= _decimals(evidence.direct_quote)` (every decimal in
   the claim appears in the matched evidence). A KEPT claim is anchored to that CURRENT evidence id + its
   bibliography `[N]`. Every UNMATCHED prior claim is OMITTED — it never reaches generation. (Mechanical, not
   prompt-advisory.)
2. **Inject ONLY matched claims** into the analyst advisory block, each shown WITH its CURRENT bibliography
   `[N]` (e.g. "cross-question consistent, supported here by [3]: <claim>"). So a reused claim can only
   appear ANCHORED to current-corpus provenance `[N]` — NEVER a prior evidence id (prior ids are never read
   or injected). The analyst already cites by `[N]` (PR7) + is screened (PR3); a matched claim corresponds
   to a real current evidence row, so it is not a fabrication.
3. Campaign-scope (`db_path = out_root/verified_claim_graph_campaign.db`), claim-text-only read, default-OFF
   `PG_SWEEP_KG_REUSE`, anti-poisoning (only VERIFIED reusable) — all UNCHANGED (Codex-accepted).
4. Verified core (multi_section + strict_verify) + provenance + §9.1 chokepoint UNTOUCHED.

**Tests (offline, NO SPEND) — incl. Codex's two mandated cases:**
- A prior-VERIFIED claim NOT supported by the current corpus → `match_prior_claims_to_current_corpus` returns
  it NOT-present → it is OMITTED from the injected set (proven by asserting it is absent from the analyst
  advisory context, not merely uncited). [Codex required-change #2]
- A prior-VERIFIED claim supported by a current evidence row → returned ANCHORED to that current ev id + `[N]`
  only; the prior evidence id is NEVER in the output. [Codex required-change #3]
- match-gate reuses strict_verify thresholds (decimal-mismatch claim is omitted; 1-content-word overlap is
  omitted); only VERIFIED reusable; campaign db shared across two writes; flag-off → no read + analyst prompt
  byte-identical.
