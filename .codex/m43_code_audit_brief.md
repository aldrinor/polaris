You are auditing M-43 — a V26-triggered regression fix.

## V26 regression signal

V26 sweep completed 2026-04-22 05:38 (113.7 min). Preservation test
`test_nice_count_at_or_above_v25_baseline` FAILED:

```
V26 NICE dropped: 0 < 4 (M-42d preservation guard failure)
```

Jurisdictional bibliography counts V25 vs V26:
- FDA: 7 → 7 ✓
- EMA: 3 → 3 ✓
- HC:  1 → 3 ✓ (M-42d target met)
- NICE: 4 → 0 ❌

Root cause:
- V26 live_corpus_dump has 0 NICE URLs (V25 had 10)
- Log shows: `template has 11 anchors; capped to 10 via
  PG_SWEEP_MAX_REGULATORY_ANCHORS`
- clinical.yaml regulatory_anchors order: `hpfb-dgpsa.ca` (M-42d
  addition) is position 9, `who.int` is 10, `nice.org.uk` is 11
- Cap truncated to position 10 → NICE dropped from anchor query
  expansion → Serper never searched `site:nice.org.uk {question}`
  → no NICE URLs in retrieval pool → no NICE in biblio

## Fix (commit `e7829d5`)

Three files:

1. `src/polaris_graph/retrieval/regulatory_expander.py`:
   - `_DEFAULT_MAX_ANCHORS = 10` → `12`
   - Comment explains V26 regression chain

2. `scripts/run_full_scale_v27.py` (new):
   - V27 launcher with `PG_SWEEP_MAX_REGULATORY_ANCHORS=12` explicit
   - Env declaration makes the fix visible in sweep config, not
     hidden as a code-default change

3. `tests/polaris_graph/test_m43_anchor_cap.py` (new, 5 tests):
   - `test_default_cap_raised_to_12`
   - `test_clinical_yaml_emits_all_anchors_including_nice` — the
     regression guard; iterates clinical.yaml and asserts every
     declared anchor produces a `site:{host}` query, with a specific
     guard for nice.org.uk
   - `test_env_override_shrinks_cap` / `expands_cap` / `zero_disables_cap`

## What to verify

1. **Default-cap correctness**: is 12 the right value? 10 was
   arbitrary; 12 accommodates clinical.yaml's 11 anchors plus one
   future addition. Alternatives: 15 (more headroom), 0 (no cap).
   Trade-off: Serper API cost ~$0.0001/query × 2 extra = negligible.
   Is 12 acceptable or should it be higher?

2. **Test coverage**: the regression guard asserts `len(queries) ==
   len(declared_anchors)` which catches future "added anchor, cap
   not raised" scenarios automatically. Sufficient?

3. **V27 launcher**: is setting `PG_SWEEP_MAX_REGULATORY_ANCHORS=12`
   in the V27 env correct given the code default is now 12 too?
   (Defense-in-depth: env + default both protect. Code reviewer
   shouldn't have to trace an env default through multiple layers
   when debugging.)

4. **M-42d preservation guard check**: the M-42d selector code's
   preservation guard design (HC 2nd slot after 1-per-juris first
   pass) is CORRECT. The V26 regression is NOT an M-42d code bug
   — it's an M-42d config-layering bug: adding hpfb-dgpsa.ca to the
   YAML raised the anchor count past the retrieval-time cap. The
   M-42d selector's preservation guard only protects T3 tier quota
   allocation against HC stealing FDA/EMA/NICE slots; it can't
   protect against retrieval-layer cap truncation since by then
   the pool already missing NICE. M-43 fixes this at the correct
   layer (retrieval anchor expansion). Confirm this root-cause
   attribution.

5. **Autoloop V2 integrity**: the regression was CAUGHT by the
   Codex-required preservation test suite. This is the system
   working as intended. M-43 is a clean follow-up fix per V2
   runbook §5 (fix plan with root-cause classification). No halt
   condition triggered — this is the expected iterative flow.

## What counts as a blocker vs medium

- **BLOCKER**: cap change breaks other anchor templates; test
  coverage misses the regression pattern; V27 launcher has a
  syntax error or wrong argv handling; M-43 introduces a new
  regression in a different anchor source.
- **MEDIUM**: cap value is arbitrary (12 vs 15 vs 20); test
  naming; inline documentation quality.
- **LOW**: comment wording.

## Deliverable

Write `outputs/codex_findings/m43_code_audit/findings.md` with
verdict (READY | BLOCKED | CONDITIONAL). Under 500 words.
