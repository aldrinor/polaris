# Verdict: burn the artifact

The reasoning engine is not fabrication-safe. The current release is burned.

I reviewed revision `267e81bccd55d3b12b96d9eb2283e3c287098087`. The six requested files match HEAD; unrelated files in the worktree are conflicted, but I did not touch them.

The existing adversarial suites all passed—including the release-boundary attack—while the real validator admitted every hostile input below. The tests prove only that their chosen attacks were blocked.

## P0 fabrication paths

### 1. “Entailment” does not test entailment

[report_ast.py:434](/home/polaris/wt/flywheel/scripts/report_ast.py:434) checks only:

- multi-digit number presence;
- 25% bag-of-words overlap.

It does not check negation, direction, modality, causality, comparator, units, scope, or who made the finding.

Exact admitted input:

```text
SPAN: the local employment-to-population ratio rose by 1.5 points
      in regions that adopted the technology

CLAUSE: the local employment-to-population ratio fell by 1.5 points
        in regions that adopted the technology
```

The real renderer produced:

> Writing in the American Economic Review in 2021, Bloom and Draca show that the local employment-to-population ratio fell by 1.5 points...

That is an attributed sentence its source contradicts.

Additional admitted attacks:

- Fabricated single-digit `9 percent`: single-digit numbers are deliberately ignored at [report_ast.py:449](/home/polaris/wt/flywheel/scripts/report_ast.py:449).
- `1.5 points` changed to `1.5 percent`: units are not checked.
- Fabricated publication-year claim: a number equal to `work.year` is unconditionally exempt.
- Negative signs, ranges, fractions and uncertainty are not represented by the numeric checker.

This alone invalidates the “182 fabrication attempts blocked” safety claim.

### 2. OWNED with no premises is an unrestricted factual lane

At [report_ast.py:611](/home/polaris/wt/flywheel/scripts/report_ast.py:611), an `Owned` node with no premises passes after checking only digits and known author names.

Exact admitted input:

```python
Owned(text="The intervention causes fatal liver injury among children.")
```

It rendered unchanged.

So did:

```python
Owned(text="The intervention doubled mortality among children.")
```

Spelled quantities are allowed in this lane. Novel lowercase entities—`mortality`, `children`—are never checked.

The released abstract already uses this bypass. [cellcog_composer.py:387](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:387) emits a premise-free factual claim that AI is a general-purpose technology of the Fourth Industrial Revolution restructuring work across industries. It appears at [report.md:5](/home/polaris/wt/flywheel/outputs/release/report.md:5).

That is why the current artifact is burned, not merely “at risk.”

### 3. Headings are untyped, unreceipted prose

[report_ast.py:540](/home/polaris/wt/flywheel/scripts/report_ast.py:540) validates a heading only for non-emptiness.

Exact admitted input:

```python
Heading(2, "Acemoglu proves that 47 percent of jobs will disappear.")
```

It rendered with an empty sidecar:

```markdown
## Acemoglu proves that 47 percent of jobs will disappear.
```

The publisher explicitly skips headings during receipt completeness checking at [publisher.py:186](/home/polaris/wt/flywheel/scripts/publisher.py:186).

The AST therefore has a third voice: `Heading`, which can assert anything.

### 4. The evidence table prints model-written prose and unverified fields

[report_ast.py:624](/home/polaris/wt/flywheel/scripts/report_ast.py:624) reads the model-authored `claim`. [report_ast.py:670](/home/polaris/wt/flywheel/scripts/report_ast.py:670) prints it. It also prints `level` and `method` without validating either against the span.

The real validator accepted and rendered this table:

| Actual span | Shipped model claim/fields |
|---|---|
| ratio **rose** 1.5 points | ratio **fell** 1.5 points; level=`children with cancer`; method=`randomized trial` |
| assistance **raised** output 40% | assistance **lowered** output 40%; level=`pregnant patients`; method=`meta-analysis` |
| exposure **reached** 32% | exposure **fell to** 32%; level=`criminal defendants`; method=`binding precedent` |

All three rows passed.

Table lines are skipped by the publisher’s prose-receipt check, while the sidecar records artificial strings such as `TABLE_ROW::<card-id>`, not the cells the judge reads. This reopens the exact “fabrication-proof table prints model prose” defect.

### 5. Cross-source connectives manufacture relations

At [report_ast.py:548](/home/polaris/wt/flywheel/scripts/report_ast.py:548), the model may choose `while`, `whereas`, `by contrast`, `but`, or `yet`. Each clause is checked separately; nobody proves the relation introduced by the connective.

Two positive, unrelated findings were admitted as:

> ...employment rose..., **by contrast** ...task output rose...

Neither source entails the contrast. The lie sits between the clauses, outside both span checks.

### 6. “The model never types a journal name” is false

`names_a_source()` claims to know surnames and venues, but [report_ast.py:235](/home/polaris/wt/flywheel/scripts/report_ast.py:235) populates only author strings. Venues are never added.

This passed:

```text
Science reports that the local employment-to-population ratio rose...
```

under an American Economic Review card.

Short author names under four characters are also deliberately invisible. If authors are stored as full names, a surname alone can likewise evade an exact full-string match.

## Can an owned verdict be false?

Yes. Determinism only proves reproducibility.

Three independent defects make false verdicts admissible:

1. Declared facets are unproved strings.  
   [argument_planner.py:599](/home/polaris/wt/flywheel/scripts/argument_planner.py:599) trusts `level`, `method`, and `horizon` directly from the card. There is no span binding for those tags.

2. The synthesis contract does not validate the asserted relationship.  
   Most operations have no operation-specific semantic check. `CONVERGES`, `CONTRASTS_DIRECTION`, `ESTABLISHES`, `DOES_NOT_ESTABLISH`, and `REMAINS_UNRESOLVED` can pass on anchoring alone.

   I passed the same premises through `CONVERGES` with both:

   ```text
   These findings point in opposite directions...
   These findings are not contradictory...
   ```

   Both were accepted.

3. The shipping gate discards the planned operation.  
   [report_ast.py:605](/home/polaris/wt/flywheel/scripts/report_ast.py:605) tries every operation and admits the sentence if any one passes. `Owned` does not even carry an `operation` field.

The planner templates also make invalid logical leaps. Different units license “not directly comparable”; they do not, by themselves, prove “not contradictory,” “what holds at A does not establish B,” or that observed differences are explained by level.

### A defensible verdict

A verdict needs a proof object, not tags:

```text
RelationProof
  operation
  premise claim-atom IDs
  verified shared dimensions
  verified differing dimensions
  polarity/modality/comparator for each premise
  rule whose preconditions were satisfied
  exact facet-supporting spans
  rendered conclusion template
```

`SAME_OUTCOME_DIFFERENT_UNIT` should license only:

> These findings concern different units and are not directly comparable.

“Not contradictory” requires substantially more: the same construct, compatible population/time/comparator, opposed surface results, and a formal demonstration that both can simultaneously be true because their scopes differ. If any facet is unproved, no verdict ships.

## Is cohesion safe with real LLM prose?

No.

It cannot mutate an `Attributed` object; that narrow claim is true. But it can create false `Owned` claims, and the owned-frame gate accepts them.

With two truthful admitted paragraphs whose only differing declared field was industry, the real pass generated and admitted:

> The same question can be put to healthcare, where the constraints on adoption differ from those in manufacturing.

Neither span mentioned constraints, adoption differences, or that comparison. The claim comes from the template at [cohesion_pass.py:201](/home/polaris/wt/flywheel/scripts/cohesion_pass.py:201).

Other unsafe templates assert that:

- two levels “do not answer the same question”;
- a level shift is “not merely one of scale”;
- differing methods agree and therefore carry more weight;
- mechanisms may change over time;
- sectoral constraints differ;
- the answer differs across sectors.

The pass itself makes no LLM call. Its risk when fed real LLM prose is therefore already present deterministically.

Reordering is also dependency-blind. `_assert_frozen()` proves attributed-node identity, but not that:

- verdicts remain after every premise they adjudicate;
- anaphora still has the same antecedent;
- paragraph order preserves argumentative dependencies.

A safe cohesion pass may choose only among proof-carrying transitions such as:

> The next evidence concerns the firm level rather than the occupation level.

That transition must carry the adjacent card IDs and verified facet bindings. Reordering must preserve an explicit dependency DAG.

## Generality claim: false

There is no `if domain ==` branch because the entire domain is hardcoded.

Examples:

- Labor-specific writer prompt: [cellcog_composer.py:212](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:212)
- Labor-specific outline: [cellcog_composer.py:324](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:324)
- Labor-specific abstract: [cellcog_composer.py:382](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:382)
- Labor-specific title: [cellcog_composer.py:933](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:933)
- Composer always calls the task-72 default contract: [cellcog_composer.py:827](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:827)

The compiled research contract is not passed into this composer.

### Legal attack

A valid bound judicial opinion passed `OFFICIAL_TEXT` policy in the provenance graph, then `CardBundle.resolve()` refused it:

```text
EXPRESSION_KIND_IS_NOT_RENDERABLE_AS_A_CITATION: 'official_text'
```

[report_ast.py:356](/home/polaris/wt/flywheel/scripts/report_ast.py:356) renders only journal and proceedings expressions. Therefore primary cases and statutes cannot reach the page.

The alleged “5/5 doctrinal findings reach the page” result measures only ledger assignment. My five-card doctrinal fixture assigned all five findings, but:

- four were assigned under “How the Fourth Industrial Revolution differs...”;
- one under occupational displacement;
- 19 of 26 subsections were empty;
- none could resolve as an official legal citation.

### Thin-evidence attack

With zero admitted cards, [cellcog_composer.py:810](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:810) aborts.

The ledger path is hashed but never read for coverage conclusions. Consequently a saturated search returning no admissible evidence cannot produce the correct answer, “the evidence does not settle this.” Zero evidence always means no report.

### Clinical behavior

The same composer would:

- use the AI/labor outline and title;
- demand a figure in every attributed finding;
- lack trial-specific population/intervention/comparator/outcome/time proof;
- treat guideline or registry official text as unrenderable;
- permit dose/unit/polarity swaps through lexical overlap.

## General fix architecture

| Fix | Clinical | Legal/comparative | Thin evidence | Domain change must be data |
|---|---|---|---|---|
| Proof-carrying claim atoms | PICO, endpoint, time, design, estimate, uncertainty and units each bind to exact spans | jurisdiction, authority, issue, holding/rule, posture and validity bind to exact text | Missing atoms produce UNKNOWN, never guessed tags | Add evidence-act and facet-schema rows; no topic regex |
| Close every prose lane | Trial headings/tables use validated atoms | Case/statute citations get official-text render templates | Coverage headings state only audited search status | Add citation/render templates and source-kind rows |
| Typed relation proofs | Pool/contrast only compatible endpoints and populations | Compare holdings only on the same legal issue, accounting for hierarchy and jurisdiction | One source or incompatible evidence yields `UNRESOLVED` | Add allowed relation rules and preconditions |
| Coverage conclusion node | “No eligible trial evidence found” only after registered searches complete | Same for courts/statutes/jurisdictions actually searched | Zero evidence can correctly ship a bounded non-settlement conclusion | Add required route families and saturation rules |
| Dependency-safe cohesion | Transitions state only verified design/population deltas | Transitions state only verified jurisdiction/authority deltas | No invented movement when evidence is absent | Add facet display names; code remains domain-neutral |

Code should implement the universal IR, proof checking, dependency preservation, and fail-closed rendering. A new domain should normally require rows in registries—evidence acts, facets, source kinds, citation templates, relation rules, and routing requirements—not edits to Python logic. A code edit is justified only for a genuinely new universal logical primitive, not a new topic.

## Additional burns

- The planner’s second-hand-source detector is not on the body-selection path. The ledger licenses every admitted card, including cards the planner marked fatal.
- `pair_ok()` identifies independent works by DOI inequality. Legal sources often have no DOI, while duplicated versions can have differing identifiers.
- `fact_use_ledger.natural_role()` trusts model-derived `has_number` at [fact_use_ledger.py:316](/home/polaris/wt/flywheel/scripts/fact_use_ledger.py:316).
- Narrate-once is exact only over the ledger’s derived finding IDs, not cards or necessarily works. Its fallback work identity can collide for anonymous sources sharing year and venue.
- Sparse corpora have no subsection floor. The five-card legal measurement confirmed 19 empty subsections.
- The release verifier rechecks byte bindings and attribution targets, but not semantic entailment. A perfectly hashed contradiction remains a contradiction.

Recommended ladder on frozen corpora:

1. Add the hostile tests above; current code must fail them.
2. Replace lexical entailment.
3. Close heading/frame/table/connective lanes.
4. Add proof-carrying verdicts.
5. Replace cohesion templates and enforce dependencies.
6. Run paired clinical, legal and thin fixtures at each rung.

Do not score or stack these changes until each rung independently clears its criterion-level safety checks.