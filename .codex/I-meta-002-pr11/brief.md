RULE NOW — emit the YAML verdict block FIRST, before any prose. Do NOT explore the repo beyond the
grounded facts below (a prior run explored ~1MB and crashed without a verdict). Read AT MOST the 5
question texts + the SWEEP_QUERIES sibling entries if you must; otherwise rule from the facts here.

## Output schema (emit FIRST)
```yaml
verdict: APPROVE | REQUEST_CHANGES
p0: [...]
p1: [...]
p2: [...]
required_changes: [...]   # only if REQUEST_CHANGES
convergence_call: accept_remaining
```

# Codex brief-gate (iter 2) — I-meta-002 PR-11 (#937): wire 5 benchmark questions' runtime routing. APPROVE this CONCRETE plan.

PR-10 (commit bc926b3a) froze 5 native per_query_report_contract entries but they're inert at runtime
because the benchmark questions aren't registered with a domain that loads their template. APPROVE the
minimal wiring below, or REQUEST_CHANGES with specifics. NO SPEND / NO NETWORK.

## GROUNDED FACTS (sufficient — do not re-verify by exploring)
- run_one_query (scripts/run_honest_sweep_r3.py) takes a question dict `q`; it builds run_dir =
  out_root/q["domain"]/q["slug"] (:1256), logs domain/slug (:1299), and loads the scope template via
  load_scope_template(q["domain"]) (:1526-ish) → `_template`; the 4-role seam keys the contract by
  q["slug"] over that template (M3a native_gate_b_inputs.load_required_entities(_template, slug)).
- The question dicts live in SWEEP_QUERIES in the SAME file (entries ~340-620). This IS the registry
  the sweep/benchmark run iterates. (run_gate_b is just the transport/mode wrapper around run_one_query;
  it does not hold a separate slug→domain map.)
- Today: drb_72_ai_labor is registered (~:603) with domain="custom" — but its contract is in
  workforce.yaml, so load_scope_template("custom") has no drb_72 contract → builder fail-closes.
  drb_75/76/78/90 are NOT registered at all.
- The 5 frozen contract keys + their domain templates: drb_75_metal_ions_cvd, drb_76_gut_microbiota_crc,
  drb_78_parkinsons_dbs (clinical.yaml); drb_72_ai_labor (workforce.yaml); drb_90_adas_liability (policy.yaml).

## CONCRETE PROPOSAL (APPROVE or correct)
1. Change drb_72_ai_labor's domain "custom" → "workforce" (only the domain key; keep its question text
   + amplified-retrieval fields).
2. Add 4 SWEEP_QUERIES entries — drb_75_metal_ions_cvd/clinical, drb_76_gut_microbiota_crc/clinical,
   drb_78_parkinsons_dbs/clinical, drb_90_adas_liability/policy — each: slug EXACTLY the contract key,
   correct domain, LOCKED question text verbatim (.codex/I-safety-002b/golden_questions_locked.md),
   mirroring the existing clinical (clinical_tirzepatide_t2dm) / policy (policy_medicare_drug_price)
   sibling entry shape. NO field that triggers a live fetch/spend at registration (registration stubs).
3. Add tests/dr_benchmark/test_benchmark_routing.py: for each of the 5 slugs assert a SWEEP_QUERIES
   entry exists with the expected domain AND load_scope_template(domain) + load_required_entities(
   template, slug) resolves to a non-empty required_entities list. NO network.
4. Do NOT touch the frozen contract content, claim_audit_scorer.py, or the runtime lock (no promotion).

## The only real risks to rule on
1. Is SWEEP_QUERIES the correct registry for this wiring (vs a separate benchmark manifest)? Per the
   grounded facts it is — confirm or name the correct registry.
2. Could any SWEEP_QUERIES field trigger a live fetch/spend merely by registering an entry (import-time
   or registration-time)? If yes, which field must stay empty/None to keep registration no-network.
3. Fail-open risk: if a registered slug/domain doesn't match a contract, the M3a builder fail-closes
   (raises) — confirm that's the guard so a routing typo can never silently skip the safety gate.

APPROVE iff registering in SWEEP_QUERIES (drb_72 domain fix + 4 new entries) is correct, no-spend/
no-network, leaves the frozen contracts + lock untouched, and the per-question slug↔contract resolution
is test-proven.
