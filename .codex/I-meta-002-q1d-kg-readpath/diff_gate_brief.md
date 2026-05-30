HARD ITERATION CAP: 5 per document. This is iter 2 of 5.
- Front-load ALL findings. Reserve P0/P1 for real execution risks.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## iter-1 REQUEST_CHANGES — P1 + P2 FIXED in the regenerated patch (re-verify):
- **iter-1 P1 (read path not mechanically read-only):** `VerifiedClaimGraphStore.__init__` gains
  `read_only=False`. When True it opens via the SQLite `file:<path>?mode=ro` URI (uri=True) — NO parent
  mkdir, NO `_ensure_table` DDL, cannot create/migrate/write-lock/mutate; a missing/unreadable db raises
  `sqlite3.OperationalError`. `gather_reuse_context` now opens with `read_only=True` and the outer except
  fail-opens to []. Write mode (default) unchanged. New tests: missing-db read creates nothing + fail-opens;
  a read_only store reads but `write_claim` raises OperationalError.
- **iter-1 P2 (flag not normalized):** `kg_reuse_enabled` now compares `.strip().lower()` against lowercase
  off-values, so FALSE/No/OFF (any case) stay disabled. New test asserts the full off/on matrix.

Evidence: 13 KG-reuse tests PASS (incl. the 2 new read-only + the case-normalize matrix); 22 PASS with
verified_claim_graph (the read_only param is additive — write path byte-unchanged). `py_compile` OK.

RULE NOW — emit the YAML verdict block FIRST. Read ONLY the patch at
`.codex/I-meta-002-q1d-kg-readpath/codex_diff.patch` (6 files, +262/-1). CLINICAL-SAFETY-RELEVANT (feeds
the analyst layer); fail-closed must be MECHANICAL. NO SPEND (read-only sqlite; default-OFF; no net/model).

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]
convergence_call: accept_remaining
```

# Codex diff-gate (iter 1) — PR10: campaign KG reuse read-path, fail-closed (#948)

Verify the diff implements the brief-gate-APPROVE'd design (brief APPROVE iter 2 — mechanical match-gate).

## What to verify
1. **Mechanical match-gate** (`memory/kg_reuse_gate.match_prior_claims_to_current_corpus`): reuses
   strict_verify's OWN `_content_words` / `_decimals` / `_min_overlap_threshold`. A prior claim is KEPT only
   if some CURRENT evidence row shares >= threshold content words AND contains every decimal in the claim;
   anchored to that CURRENT evidence id. Unmatched prior claims are OMITTED (never returned). NEVER returns a
   prior evidence id.
2. **gather_reuse_context**: default-OFF (`kg_reuse_enabled`, `PG_SWEEP_KG_REUSE`); opens the campaign KG
   READ-ONLY; `query_related_claims` (anti-poisoning: only VERIFIED reusable rows); claim-TEXT-only; passes
   texts through the match-gate; capped; fail-open (any error → []).
3. **Campaign-scope** (`sweep_integration`): `run_four_role_evaluation` + `run_four_role_seam` gain
   `campaign_kg_db=None` (default → per-`run_dir`, existing callers/tests unchanged); when given, the KG is
   persisted to the shared campaign db. Sequential sweep → no concurrent writers.
4. **Injection** (`multi_section_generator` → `analyst_synthesis`): `prior_verified_context` threaded to the
   UNVERIFIED analyst layer only; `_format_prior_verified_context` renders a labeled advisory block with the
   claim + CURRENT evidence id, instructing `[N]`-only current-bibliography citation; empty input → "" (prompt
   byte-identical). VERIFIED generator (multi_section sections) + strict_verify path UNTOUCHED.
5. **run_honest_sweep wiring**: gathers reuse context before generation (fail-open, logged), passes
   `prior_verified_context` to `generate_multi_section_report`, and `campaign_kg_db=out_root/...campaign.db`
   to `run_four_role_seam`.

## Evidence (verified by Claude main-thread, NO SPEND)
- 10 KG-reuse tests PASS incl. Codex's two mandated cases: a prior-VERIFIED claim NOT supported by the
  current corpus is OMITTED (`test_gather_anti_poisoning_and_unsupported_omitted`); a supported claim is
  anchored to the CURRENT ev id only (never a prior id). Plus match-gate decimal-mismatch/low-overlap/dedup,
  anti-poisoning (UNSUPPORTED-verdict prior excluded), flag-off→[], empty advisory block.
- 54 PASS no-regression (analyst_synthesis + safety) + 34 PASS (verified_claim_graph + sweep_integration +
  gate-b seam — the campaign_kg_db threading default-None preserves behavior). `py_compile` OK on all 5
  source files. Patch +262/-1.

## The real risks to rule on
1. Is fail-closed now MECHANICAL (omit-unless-current-corpus-supported), not prompt-advisory? (Claim: yes —
   the match-gate drops unmatched claims before they reach any prompt; reuses strict_verify's exact rule.)
2. Can a reused claim earn provenance or appear with a PRIOR evidence id? (Claim: no — claim TEXT only, prior
   ids never read; matched claims carry the CURRENT ev id; verified core + strict_verify untouched.)
3. Anti-poisoning intact (only VERIFIED reusable)? campaign_kg_db default-None preserves existing callers?
   (Claim: yes — query_related_claims filters reusable=1; default None → per-run_dir.)
4. Default-OFF + fail-open (a KG/read error never aborts or alters a run)?

APPROVE iff the diff makes reuse MECHANICALLY fail-closed (omit-unless-current-supported, anchored to current
ev ids only, no prior ids, no provenance), preserves anti-poisoning + the verified core + strict_verify, is
campaign-scoped with default-None back-compat, default-OFF, fail-open, and offline-tested with NO SPEND.
