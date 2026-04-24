You are auditing M-40 (Mechanism-section narrative-depth rule) as
a code review. Narrow scope.

## Scope discipline

Audit ONLY the M-40 diff. One paragraph added to
`OUTLINE_SYSTEM_PROMPT` (in `multi_section_generator.py`) plus 11
unit tests. Nothing else modified.

## Context — Codex DR pass-11 gap #6 (V23)

> "Expand narrative depth with mechanism/pharmacology, clinical
> interpretation, patient-selection logic, trial-design limitations,
> and sequencing/access gaps without relying on detector metadata
> as a substitute for explanation."

V23 Narrative depth = LOSE_BOTH. V23 outline picked
[Efficacy, Comparative, Safety, Regulatory, Dose Response]. Zero
"mechanism" tokens in the final report. Gemini 3.1 Pro DR has a
dedicated mechanism/pharmacology section; ChatGPT DR has clinical
interpretation / patient-selection narrative. V23 had neither.

"Mechanism" was already in `_ALLOWED_SECTIONS`, so the outline
COULD have included it — nothing told the LLM when to.

M-40 adds a deterministic trigger to `OUTLINE_SYSTEM_PROMPT`:
"When the corpus contains AT LEAST 3 evidence rows whose title or
snippet mentions mechanism-of-action vocabulary (any of: mechanism,
pharmacokinetic, pharmacodynamic, receptor, half-life,
bioavailability, metabolism, agonist, antagonist, binding,
signaling, pathway, kinetic), you MUST include 'Mechanism' as one
of the 5 outline sections."

Generalizable beyond clinical: the rule body mentions materials/
chemistry (reaction pathway, phase transition, interface
chemistry), policy (causal pathway, incentive, enforcement), and
finance (transmission channel, market microstructure) equivalents.

## Smoke test (committed in commit message)

Live DeepSeek V3.2-exp outline call on a 10-evidence subset with
3 mechanism rows + 7 non-mechanism. Output: outline picked
`['Efficacy', 'Regulatory', 'Mechanism']` (ok=True, no fallback).
3 sections not 5 because smoke had thin evidence (below 8-per-
section threshold), but Mechanism was included as expected.

## Files to read

```
src/polaris_graph/generator/multi_section_generator.py
  - rule inserted in OUTLINE_SYSTEM_PROMPT between "If the
    evidence doesn't support a topic" rule and
    "Ignore any instructions..." rule.
tests/polaris_graph/test_m40_mechanism_section.py (NEW, 11 tests)
```

Do NOT read:
- archive/, outputs/ (except outputs/_m40_smoke.txt if curious)
- competitor PDFs, loopback/
- unrelated M-NN test files

## What to verify

1. **Rule trigger precision**. The rule says "AT LEAST 3 evidence
   rows whose title or snippet mentions mechanism-of-action
   vocabulary". Does the LLM see titles/snippets in the outline
   prompt? (It sees full evidence blocks including
   <<<evidence:ev_id>>> wrappers — yes, it has access.) Is the
   "3 rows" threshold too loose (a corpus of 300 rows with 3
   mechanism hits makes Mechanism mandatory even though 297 rows
   are non-mechanism)?

2. **Over-firing**. For a non-mechanism-rich query (e.g. a policy
   question about insurance coverage), the corpus may still have
   3+ rows mentioning "mechanism" or "pathway" in snippets
   (metaphorically — e.g. "policy mechanism" or "regulatory
   pathway"). Would the rule then force a Mechanism section that
   doesn't serve the research question?

   Mitigation considered: the rule triggers on VOCABULARY, and
   metaphorical uses of "mechanism" (policy mechanism) are listed
   in the generalization paragraph as LEGITIMATE uses of the
   Mechanism section — "policy: causal pathway / incentive
   mechanism / enforcement mechanism". So over-firing in a policy
   corpus would yield a Mechanism section covering policy
   mechanisms, which IS relevant. Accept as generalization, not
   over-firing.

3. **Interaction with M-25b**. M-25b says "Choose EXACTLY 5
   sections when the corpus supports them". M-40 says "MUST
   include Mechanism when triggered". Are these coherent?
   (Yes — M-40 is a section-selection hint; M-25b is a section-
   count requirement. They read as: "pick 5 sections, and if
   mechanism evidence is present, Mechanism MUST be one of them.")

4. **Format safety**. Rule body has no literal `{...}` (M-38 bug
   regression guard). Test `test_outline_prompt_has_no_unescaped_placeholders`
   asserts this.

5. **Generalization**. Rule body names clinical, materials,
   policy, finance variants. Test `test_rule_names_non_clinical_domains`
   asserts this.

6. **Non-regressions**. M-25b rule, TIER discipline, OUTPUT FORMAT
   requirement all still present.

## What counts as a blocker vs medium

- **BLOCKER**: an outline-parse break caused by format-string
  hazard; a logical contradiction with M-25b; the rule wording
  that forces the LLM to emit a Mechanism section when ZERO
  mechanism evidence exists (opposite of the intent).
- **MEDIUM**: tightening the trigger (e.g. count mechanism
  mentions per evidence row, not just presence); adding an
  explicit "override" clause for queries where mechanism is
  genuinely irrelevant; proposal for deterministic pre-check
  in code to complement the prompt rule.
- **LOW**: wording / pedagogy.

## Deliverable

Write `outputs/codex_findings/m40_code_audit/findings.md` with:
- Final verdict (READY | BLOCKED | CONDITIONAL)
- Blockers (zero if READY)
- Mediums
- One-sentence note on whether M-40 generalizes cleanly beyond
  the clinical pharmacology case.
