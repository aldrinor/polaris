You are auditing M-37 (Health Canada tier fix + jurisdictional
coverage prompt rule) as a code review before the next full-scale
sweep runs. Narrow scope.

## Scope discipline

Audit ONLY the M-37 diff. Three small, coherent changes:
1. Tier classifier: `hres.ca` added to `REGULATORY_DOMAINS` (+4 lines).
2. Clinical template: 3 new HC anchor hosts (+3 lines).
3. Section prompt: new rule #11b injected between #11 and #12.

Do NOT invent adversarial probes. If you find a real defect, cite
the exact file + line.

## Context — Codex DR pass-11 gap #2 (V23)

> Add Health Canada specificity alongside FDA, EMA, and NICE,
> including the Canadian product monograph / Summary Basis of
> Decision and any jurisdiction-specific safety communications.

V23 corpus had 7 Health Canada rows but zero HC entries in the
cited bibliography. Three root causes from on-disk forensics:

**Tier misclassification (the observed defect)**
- `pdf.hres.ca/dpd_pm/00073189.PDF` = MOUNJARO Product Monograph
  — classified as T4 confidence 0.65, rule=`R9_openalex_unverified_host_demoted_to_t4`.
- Reason: `pdf.hres.ca` was not on `REGULATORY_DOMAINS`, so R2d
  didn't fire. R9 then saw `openalex.type=article, is_peer_reviewed=True`
  but the host wasn't on `PEER_REVIEWED_JOURNAL_DOMAINS`, so it
  defaulted to T4.
- The OTHER V23 HC monograph (00083504.PDF) was saved by the
  R2c regulatory-content-marker rule because its title contained
  "Product Monograph". The first one didn't.

**Retrieval pressure** — corpus already had HC content, so this
is hygienic not corrective. Added `pdf.hres.ca`,
`recalls-rappels.canada.ca`, `health-products.canada.ca`.

**Prompt bias** — M-29 rule #11 covered precision but not
coverage. New #11b: cite at least one source per jurisdiction
PRESENT in the evidence subset.

## Smoke test I already ran

Post-fix, classifying the V23-failed URL via the canonical
`classify_source_tier(ClassificationSignals(...))` entry:
- URL: `https://pdf.hres.ca/dpd_pm/00073189.PDF`
- Title: `[PDF] MOUNJARO (tirzepatide injection)`
- openalex_publication_type=article, openalex_is_peer_reviewed=True
- **Result: T3, confidence 1.0, matched_rules=['R2d_regulatory_domain']**

So the MOUNJARO monograph now correctly classifies as T3 regulatory.

## Files to read

```
src/polaris_graph/retrieval/tier_classifier.py
  — line 146 (new entry in REGULATORY_DOMAINS frozenset)
config/scope_templates/clinical.yaml
  — lines ~115-125 (3 new anchor hosts in regulatory_anchors)
src/polaris_graph/generator/multi_section_generator.py
  — line 566 (new rule #11b inside SECTION_SYSTEM_PROMPT_TEMPLATE,
    between M-29 rule #11 and M-32 rule #12)
tests/polaris_graph/test_m37_health_canada.py
  — 14 tests covering all three changes
```

Do NOT read:
- archive/, outputs/ (except maybe `outputs/full_scale_v23/clinical/clinical_tirzepatide_t2dm/live_corpus_dump.json` if you want to verify the V23 classification state)
- competitor PDFs, loopback/
- other tier-classifier test files (covered by the regression sweep)

## What to verify

1. **Parent-domain match safety**. `hres.ca` was added. `_domain_matches`
   walks parents, so `pdf.hres.ca` and `www.hres.ca` match. Are
   there any unwanted HC-adjacent hosts that might now be wrongly
   promoted to T3? (e.g. a blog at `myblog.hres.ca` — unlikely
   since hres.ca is the Health Products Regulatory Electronic
   System domain, but worth noting.)

2. **Precedence**. `REGULATORY_DOMAINS` is consulted by R2d which
   fires early. Does this now short-circuit a case the previous
   R9 path handled? E.g., if a peer-reviewed paper somehow had
   `hres.ca` host (it doesn't in practice but hypothetically),
   R2d would give it T3 instead of letting R9 give it T1 via the
   allowlist. Acceptable trade-off? (I say yes — hres.ca is a
   regulatory-PDF host, not a journal host.)

3. **Clinical YAML changes**. Three new anchors. The M-28 expander
   already caps emission at `PG_SWEEP_MAX_REGULATORY_ANCHORS`
   (default 10). The template now has 10 anchors (7 original +
   3 new) — no overflow under default cap. But if user sets
   `PG_SWEEP_MAX_REGULATORY_ANCHORS=5`, one of the original
   anchors would drop out of rotation. Is this a concern?

4. **Prompt rule #11b**. Check for:
   - Rule numbering: inserted between #11 and #12 using "11b." —
     the existing #12 (M-32) still immediately follows.
   - Generalization: names FDA / EMA / NICE / Health Canada / TGA
     / PMDA / NMPA / WHO, not just HC. Fires on presence, not
     presence-checks.
   - No drug-specific hardcoding in the rule body (tests check
     this, but eyeball it).
   - The example phrase "KwikPen pen-device warnings" is prose
     in the rule body illustrating "jurisdiction-specific facts"
     — it's not a hardcoded drug branch. Acceptable?

5. **Non-regressions**. M-37 tests 14/14 pass. Full regression
   sweep 229/229 (tier classifier + M-30..M-37). No schema
   changes; no downstream consumer updates needed.

## What counts as a blocker vs medium

- **BLOCKER**: classifier regression where a non-regulatory host
  is now T3; YAML change that breaks template load; prompt edit
  that breaks existing rule-#12 evaluation; any test that fails
  under the new code.
- **MEDIUM**: tightening suggestions (e.g. narrow the regex
  detection of KwikPen-style examples, add more HC anchor hosts,
  surface the new rule in the Limitations / telemetry block).
- **LOW**: wording / comments.

## Deliverable

Write `outputs/codex_findings/m37_code_audit/findings.md` with:
- Final verdict (READY | BLOCKED | CONDITIONAL)
- Blockers (zero if READY)
- Mediums
- One-sentence note on whether the new rule #11b remains
  domain-agnostic enough for the template-driven abstraction.
