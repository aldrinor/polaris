HARD ITERATION CAP: 5 per document. This is iter 1 of the M3b DIFF gate.
- Front-load ALL real findings in iter 1. No drip-feeding across iterations.
- Same quality bar regardless of iteration count.
- "Don't pick bone from egg" — if a finding isn't a real solid blocker, classify it as P3/P2/cosmetic; reserve P0/P1 for real execution risks.
- If iter 5 returns REQUEST_CHANGES, the document is force-APPROVE'd; do not bank issues.
- Verdict APPROVE iff zero NOVEL P0 AND zero continuing P0 AND zero P1.

## Output schema (REQUIRED — emit this exact YAML block as your final output)
```yaml
verdict: APPROVE | REQUEST_CHANGES
novel_p0: [...]
continuing_p0: [...]
p1: [...]
p2: [...]
convergence_call: continue | accept_remaining
```

# Codex DIFF-gate — I-meta-002 PR-9/M3b: Gate-B seam + verifier transport no-leak + evidence normalization + native S0 annotations + offline seam test

The M3 DESIGN was APPROVED by you on iter 2 (.codex/I-meta-002-pr9-m3/codex_brief_verdict_iter2.txt).
This is the M3b implementation diff. Verify it conforms to the approved design + your rulings.

## HARD CONSTRAINTS (operator-locked)
- NO MONEY / NO NETWORK in this PR. The seam test injects a FAKE RoleTransport; nothing deploys to Vast.
- NATIVE-ONLY, NEVER the gold rubric: the seam/caller/evidence-normalization must NEVER read
  outputs/dr_benchmark; only the NON-benchmark clinical_tirzepatide_t2dm contract is annotated.
- D8 remains the SINGLE binding gate (no second gate).
- Frozen, no drift: claim_audit_scorer.py, runtime lock (do NOT promote). M3a builder logic
  (native_gate_b_inputs.py coverage/severity) is committed + APPROVE'd — M3b only CALLS it.

## Your approved-design rulings M3b must honor (verify each in the diff)
1. Timing seam = B: a `four_role_input_builder` param on run_one_query; when PG_FOUR_ROLE_MODE on +
   transport injected, the builder is called AFTER generation and the BUILDER WINS over any directly
   passed four_role_inputs. Backward-compatible (default None → existing callers unaffected).
2. The SEAM (not the builder) writes bundle.audit_map to run_dir/four_role_claim_audit.json.
3. Transport no-leak (hard_require): the 3 self-host verifier roles use ONLY PG_<ROLE>_API_KEY, NEVER
   fall back to OPENROUTER_API_KEY; when the per-role key is empty the Authorization header is OMITTED
   ENTIRELY (no empty `Bearer `). Generator path unchanged.
4. Evidence normalization deterministic + no network: url=source_url (full canonical), DOI via
   `10.\d{4,9}/...` regex, PMID deterministic; keys match ProvenanceToken.evidence_id.
5. clinical_tirzepatide_t2dm S0 required_entities carry severity + s0_category + NON-BLANK
   coverage_content_requirements (the M3a validator raises on blank).

## Review emphasis
- (a) builder-WINS precedence + audit_map written to run_dir.
- (b) transport no-leak exactly as ruled (no OPENROUTER_API_KEY fallback for verifier roles; omit
  header when keyless; generator excluded/unchanged).
- (c) evidence normalization is deterministic, no network, and the lookup keys align with
  ProvenanceToken.evidence_id so coverage can actually fire on real data.
- (d) clinical.yaml S0 annotations: non-blank content requirements; severity/s0_category valid.
- (e) the seam test proves the D8 decision flows to manifest['release_allowed'] + manifest['status']
  using a FAKE transport (no network).
- (f) backward-compat: existing run_one_query callers that pass no builder are byte-unaffected.
- (g) the run_one_query manifest-status change does not corrupt the abort-status taxonomy. NOTE: the
  smoke section below documents that tests/polaris_graph has 49 PRE-EXISTING failures (proven by
  git-stash comparison to the M3a-committed HEAD — the same tests fail with M3b reverted), including
  two test_manifest_contract source-inspection tests that grep run_honest_sweep_r3.py line patterns.
  Please confirm you agree these are pre-existing and that the M3b diff introduces no NEW status/manifest
  regression.

## SMOKE RESULTS (verbatim follow; then the build spec; then the DIFF)
