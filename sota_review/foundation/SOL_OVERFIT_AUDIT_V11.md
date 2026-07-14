The zero-drop proposal is directionally right but not sound enough to ship. The safe deterministic rule is narrower:

> Exact quotation may be admitted deterministically only as quotation. It may not be upgraded into a finding.

The current validator and all three built-in self-tests are green, yet targeted clinical adversaries still produce false admissions. No files were changed.

## 1. Zero-drop ruling

The existing shortcut in [report_ast.py](/home/polaris/wt/flywheel/scripts/report_ast.py:947) is unsound. With the semantic judge forced to `UNCERTAIN`, it currently admits all of these:

```text
SPAN:  Daily aspirin reduced all-cause mortality?
CLAIM: Daily aspirin reduced all-cause mortality.
```

```text
SPAN:  Hypothesis: Daily aspirin reduced all-cause mortality.
CLAIM: Daily aspirin reduced all-cause mortality.
```

```text
SPAN:  “Daily aspirin reduced all-cause mortality,” the authors hypothesized.
CLAIM: Daily aspirin reduced all-cause mortality.
```

```text
SPAN:  The data tentatively indicate daily aspirin reduced all-cause mortality.
CLAIM: Daily aspirin reduced all-cause mortality.
```

The stricter proposed rule fixes the last example because words were dropped. It does not fix the first two:

- Punctuation normalization converts a question into an assertion.
- Treating the text after `Hypothesis:` as a complete top-level clause drops the governing speech-act label without dropping a word from the clause.
- A heading can govern a complete following sentence:

```text
SPAN/document context:
HYPOTHESIS
Daily aspirin reduced all-cause mortality.

CLAIM:
Daily aspirin reduced all-cause mortality.
```

The claim is byte-identical to a complete sentence, but rendering it through the current templates—“Smith et al. show/find/establish that …” at [report_ast.py](/home/polaris/wt/flywheel/scripts/report_ast.py:445)—fabricates a result from a hypothesis.

Case normalization is not domain-general either. Case distinguishes genes, proteins, chemical notation, legal defined terms, and program identifiers. Whitespace and punctuation can be semantic in mathematics, tables, code, quotations, and clinical endpoint notation.

### Sound version

There are two separate lanes:

1. **Deterministic quotation lane**

   - The emitted payload must be byte-identical to the entire bound evidence unit.
   - Preserve case, punctuation, signs, quotation marks, and internal whitespace.
   - Only mechanically safe transformations such as output escaping are allowed.
   - Render neutrally: `Author writes: “<exact bytes>”`.
   - Never render it as `show`, `find`, `establish`, `demonstrate`, or “the study found.”
   - Its guarantee is only: “these bytes occur in this source.”

2. **Finding/paraphrase lane**

   - Every claim goes to a semantic judge.
   - The judge receives the claim, full evidence unit, governing heading/caption/quotation context, and source identity.
   - It must verify entailment, assertoric status, source ownership, direction, magnitude, scope, population, comparator, time, condition, modality, and quantifiers.
   - `UNCERTAIN`, unavailable, malformed, or missing context means rejection.

Clause-boundary detection may be used only to reject or route to the judge. It must never authorize admission. “Complete clause” is syntactic; “asserted finding belonging to this source” is semantic.

Clinical behavior: a trial’s hypothesis, protocol objective, adverse-event table heading, quoted prior study, subgroup qualifier, and noninferiority comparator all remain on the judge path. None can become a result merely because one sentence was copied intact.

## 2. Whole-validator audit

### `report_ast.py`

| Mechanism | Ruling | General replacement and clinical behavior |
|---|---|---|
| `_LEAD_POISON`, `_TRAIL_POISON`, direction/scope/negation lists | Unsafe because they support the final shortcut at [line 913](/home/polaris/wt/flywheel/scripts/report_ast.py:913). Any unlisted modifier becomes a hole. | Delete the deterministic paraphrase admission. Lists may cheaply reject, but absence means `UNKNOWN → judge`. Clinically, “nominally,” “after adjustment,” “per protocol,” or “except among…” cannot slip because a list omitted them. |
| `_KNOWN_VENUES` | A denylist of famous venues is intrinsically incomplete. An unknown venue is currently treated as no venue. | Corpus matching remains a cheap rejection signal; no hit must mean unknown, not “names no source.” Judge every free-text source/ascription question. |
| `_REPORTING_VERB_WORDS` / `_ATTRIB_PATTERN` | Synonym-defeatable. | Structural attribution only, or unconditional semantic source/ascription judgment. |
| `_GROUP_WORDS` / `_COMMON_SUBJECTS` | Synonym-defeatable and role-taxonomy-dependent. | Do not infer “contains no actor” from failure to match group nouns. |
| `_EMPIRICAL_VERB` | Critical unsafe admission gate at [line 786](/home/polaris/wt/flywheel/scripts/report_ast.py:786): no listed verb means the judge is never called. | Judge every premise-free `Owned` sentence, or abolish free-form premise-free assertions. |
| `_MAGNITUDE_ABS`, `SPELLED_QTY`, `FORECAST`, entity-capital heuristics | Denylists: unlisted factual predicates, quantities, entities, forecasts, and absolutes admit. | These may reject known hazards only. All remaining free text stays unknown. |
| Heading validator | Unsafe: headings are accepted after a small list of prohibited forms. | Heading must be a structurally generated label or semantically classified as a non-propositional noun phrase. |
| `while` classified as neutral | Unsafe. `while` can assert contrast or simultaneity. | Use separate sentences or plain `and`; any relational connective requires a relation proof. |
| Numeric/unit and direction checks | Acceptable only as reject-only defenses. | Keep them for cheap certain rejection; never interpret survival as support. |

Concrete current false admissions, even when the frame judge is configured to return `UNCERTAIN`:

```text
The Cambridge cohort uncovered that the treatment cured disease.
The Oxford investigators ascertained that the drug was effective.
The Karolinska cohort detected a survival benefit.
The treatment eradicated disease.
The intervention prolonged survival.
```

All five pass because the reporting, group, and empirical-verb lists do not contain the relevant words.

These headings also pass:

```text
Daily aspirin eradicates disease
The intervention guarantees recovery
The treatment cured cancer
```

Clinical behavior after the fix: all are rejected or judge-routed regardless of whether the predicate is “cured,” “ameliorated,” “prolonged,” “conferred benefit,” or a novel synonym.

### `synthesis_contract.py`

The central issue is not just incomplete lists. A recognized phrase can license a proof while an unrelated fabrication rides in the same sentence.

This exact synthesis passes both `validate()` and `prove()`:

```text
These studies observe different units of analysis,
and the intervention eradicates disease.
```

The first clause matches `_CLAIM_PATTERNS` at [line 359](/home/polaris/wt/flywheel/scripts/synthesis_contract.py:359); the proof checks the unit relation, but nothing proves the added eradication claim.

Other findings:

- `CAUSAL_IMPORT`, `FORECAST`, `UNIVERSAL`, and `SPELLED_QTY` are unsafe denylists at [lines 82–95](/home/polaris/wt/flywheel/scripts/synthesis_contract.py:82).
- `SAFE_CAPS` contains task-specific entities such as “Artificial Intelligence” and “Fourth Industrial Revolution,” allowing them without premises. That is explicit task-72 overfit.
- `LEVEL_CUES` at [line 164](/home/polaris/wt/flywheel/scripts/synthesis_contract.py:164) is economics-specific and polysemous. For example, `plant` can mean a manufacturing unit or a botanical clinical intervention.
- Unknown claim patterns reject, which is the right direction, but matching one phrase does not prove the entire sentence.
- `method` and `horizon` can still be trusted from declared fields without equivalent span-bound proof.
- `BOUNDARY`/`COVERAGE_GAP` proofs at [line 561](/home/polaris/wt/flywheel/scripts/synthesis_contract.py:561) do not prove the object of the limitation.

General replacement:

- A synthesis must be an AST of typed propositions, not free prose searched for one recognized phrase.
- Every proposition in the sentence must map to a proof conclusion.
- The final prose should be compiled from the proof object using a closed template; no model-written suffixes or conjunctions.
- Every facet used in a proof needs an exact evidence span and semantic binding.
- Unknown or ambiguous facets remain `UNKNOWN` and cannot participate in a relation.

Clinical behavior: “different populations,” “different comparators,” “different endpoints,” and “different follow-up periods” can be stated only when both trial cards prove those facets. A unit contrast can never smuggle in “the drug improves survival.”

### `argument_planner.py`

The default contract beginning at [line 141](/home/polaris/wt/flywheel/scripts/argument_planner.py:141) is task-72-specific and is also loaded by `report_ast.py`. Being configurable does not make the default path domain-general.

Unsafe safety decisions include:

- Outcome, polarity, negator, and clause-break vocabularies.
- Fixed token windows and nearest-outcome attachment.
- `secondhand_cues` and `forecast_cues` at [lines 256–280](/home/polaris/wt/flywheel/scripts/argument_planner.py:256).
- Declared method/horizon fields treated as proof inputs.
- Digit presence treated as evidence of an estimate.
- Corpus absence treated as a research gap.
- Verdict and bridge templates asserting more than their inputs prove.

All of these second-hand or forecast spans currently remain fully eligible:

```text
Brown demonstrated that the drug reduced mortality.
Prior investigators established that the drug reduced mortality.
Earlier work uncovered a survival benefit.
The drug is anticipated to reduce mortality.
The intervention is poised to improve survival.
Mortality is destined to fall after adoption.
```

General replacement:

- Contract vocabularies may nominate candidate facets only.
- A semantic facet extractor must return `{value, exact supporting span, confidence/verdict}`.
- Only affirmative, unambiguous bindings enter comparisons.
- Second-hand ownership and observed-vs-forecast status must be judged for every candidate span.
- Numeric comparison requires a typed numeric manifest: outcome, estimate, unit, population, comparator, time, uncertainty, and design.
- Corpus absence must be phrased only as “not represented in this corpus” unless a separate search-completeness proof licenses a broader absence.

Clinical behavior: an unlisted phrase such as “was anticipated to lower mortality” becomes forecast/unknown and cannot be compared with an RCT estimate. A sample size or trial-registration number cannot make a span a quantitative effect estimate.

### `cohesion_pass.py`

Immutability of `Attributed` objects is valuable, but it does not make the pass safe. The pass creates new factual relations through its templates at [line 181](/home/polaris/wt/flywheel/scripts/cohesion_pass.py:181).

These current cohesion-style sentences pass validation:

```text
Whether the pattern seen in cardiology recurs in oncology is an empirical
question, and the answer is not the same one.

The cohort evidence above and the trial evidence below are answerable to
different threats, so their agreement carries more weight than either alone.

The findings above speak to the short-term horizon; over the long-term
horizon the same mechanisms need not hold.
```

The inputs do not prove differing answers, agreement, evidentiary weight, or mechanism instability.

Reordering frozen paragraphs is also not semantically neutral: it can change the antecedent of “this result,” “the former,” or “these findings” without changing any object bytes.

General replacement:

- A premise-free cohesion node may express only document structure, such as “The next section considers safety outcomes.”
- Any statement about evidence, comparability, agreement, strength, or limits must carry premise IDs and a relation proof.
- Generate transitions from proved conclusions, not raw dominant metadata.
- Disable paragraph reordering unless cross-paragraph anaphora and discourse dependencies are represented and preserved; the safe default is no reorder.

Clinical behavior: moving from an observational cohort to an RCT may be labeled structurally, but the system cannot claim greater confidence, agreement, or different bias threats without a method proof tied to both studies.

## 3. Fail-safe use of unavoidable lists

Lists are acceptable only under these rules:

1. **Closed protocol vocabulary**

   Node types, operation enums, source-policy kinds, and renderer template IDs may be allowlists. Unknown values reject.

2. **Lexical hazard recognizers**

   A match may reject or route to the judge. No match means `UNKNOWN`, never `SAFE`.

3. **Facet ontologies**

   An unlisted synonym produces an unknown facet. A relation requiring that facet cannot be formed. A listed match is still only a candidate because polysemy can produce false positives.

4. **Source/entity/reporting detection**

   A known match rejects free-text use. Failure to find a match does not prove that no source or actor was named.

5. **Semantic judges**

   Call them unconditionally on every free-text factual, source-owning, or evidence-relational lane. Unavailable, malformed, conflicting, or uncertain verdicts reject.

6. **Generated proof language**

   Compile text from the proof object using a closed renderer. Do not search arbitrary model prose for one phrase and then license the whole sentence.

The implementation invariant should be:

```text
known hazard       -> REJECT
affirmative proof  -> ADMIT
everything else    -> JUDGE
judge not clearly affirmative -> REJECT
```

The current code instead contains several instances of:

```text
not in my word list -> ADMIT
```

Those are release blockers.

The built-in synthesis, planner, and cohesion suites all passed while the counterexamples above were admitted. The suites therefore demonstrate consistency with their enumerated fixtures, not general safety.