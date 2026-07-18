The score path should use the 838-card curated corpus, let the current render finish as a baseline, then run one fixed compose. Defer the audit until afterward.

The investigation’s central diagnosis needs one correction: the production identity gate is already wired correctly. The actual `0 verdicts placed` defect is a poisoned source-name index.

## Verified diagnosis

- `outputs/provenance_graph.json` contains 356 positively identified manifestations: 305 `VERSION_OF_PUBLISHED` and 51 `SAME_WORK`.
- The current curated bundle resolves 820 cards successfully under `journal_articles_only`.
- [provenance.py](/home/polaris/wt/flywheel/scripts/provenance.py:1367) already imports the canonical `event_ledger.IDENTITY_PROVEN` allowlist and returns structured `identity_verdict`, `disposition`, and `reason_code`.
- [report_ast.py](/home/polaris/wt/flywheel/scripts/report_ast.py:397) already consumes that resolver through `graph.resolve_attribution()`.

The production zero-placement failure is here:

- [report_ast.py](/home/polaris/wt/flywheel/scripts/report_ast.py:329) indexes every token in every author string as a source name.
- The corpus contains the corporate byline `on behalf of the INSPIRING Project Consortium`.
- Consequently, `_source_words` contains `the` and `of`.
- A valid planner verdict was directly refused as:

```text
OWNED_NAMES_A_SOURCE: 'the'
```

That refusal occurs before its identity or synthesis proof can matter. The P0/P1 failures in `fab_base.log` are a separate fixture defect: [test_fabrication_paths.py](/home/polaris/wt/flywheel/scripts/test_fabrication_paths.py:68) manually constructs manifestations without running the production identity reducer, leaving `semantic_binding=None`.

Therefore: do not add a separate venue allowlist. Venue strings are metadata, not identity proof; using them to admit sources would reopen the laundering hole.

# Phase 0 — Bank the in-flight baseline

PID 230716 is gone. Its replacement, PID 232534, is currently healthy and composing the same pinned curated corpus. Do not kill it and do not start another writer.

Acceptance:

- Process exits.
- `outputs/release/report.md` exists and is nonempty.
- Preserve it before the fixed compose overwrites the release path.

Command:

```bash
cd /home/polaris/wt/flywheel

ACTIVE="$(pgrep -fo 'python -u scripts/cellcog_composer.py.*--write')"
while test -n "$ACTIVE" && kill -0 "$ACTIVE" 2>/dev/null; do
  sleep 15
done

test -s outputs/release/report.md
mkdir -p outputs/baselines
cp outputs/release/report.md outputs/baselines/task72_pre_verdict_fix.md

set -a
source .env
set +a

python scripts/score_report_race.py \
  --report outputs/baselines/task72_pre_verdict_fix.md \
  --task-id 72 \
  --model-name polaris_task72_pre_verdict_fix \
  --race-model openai/gpt-5.5 \
  --max-workers 4
```

If the process exits without publishing, skip the baseline score; do not spend time recovering that render.

# Phase 1 — Repair verdict placement without weakening identity

## 1.1 Keep one identity authority

Edit [report_ast.py](/home/polaris/wt/flywheel/scripts/report_ast.py:375):

- Continue calling `graph.resolve_attribution(binding, policy)`.
- Do not create `REPORT_AST_ALLOWED_VENUES`, DOI lists, task-specific names, or card-derived identity rules.
- Strengthen the structured handoff by requiring all of:

```python
att.admitted
att.disposition == P.DISPOSITION_ADMIT
att.reason_code == P.RC_ADMITTED
att.identity_verdict in event_ledger.IDENTITY_PROVEN
att.names_expression_id is not None
```

This imports the canonical allowlist; it does not copy it.

Fail closed on any inconsistent tuple. Card fields such as `venue`, `doi`, `authors`, `attribution`, or `identity_verdict` remain non-authoritative.

## 1.2 Fix the poisoned source-name index

Edit `CardBundle._index_person()` in [report_ast.py](/home/polaris/wt/flywheel/scripts/report_ast.py:329).

Rules:

- Always index the normalized full author/byline as a phrase.
- For an individual person:
  - One-token name: index it, including short surnames such as `Wu` and `Ng`.
  - `Surname, Given`: index the surname portion.
  - `Given … Surname`: index only the terminal surname, excluding particles such as `de`, `van`, `von`, `da`.
- For corporate/group bylines:
  - Index the full phrase.
  - Index explicit acronyms.
  - Never index function words or every component token.
- Never place tokens such as `the`, `of`, `on`, `behalf`, `for`, `and`, `by` in `_source_words`.

Keep the existing independent defenses:

- Exact venue phrases from the graph.
- `_KNOWN_VENUES` for corpus-absent famous venues.
- The general `<Proper subject> <reporting verb> that` construction.
- The owned oblique-attribution firewall.

This closes the false-positive without allowing a model to type its own attribution.

## 1.3 Use one facet contract

The composer and validator currently derive separate planner contracts. Edit:

- [report_ast.py](/home/polaris/wt/flywheel/scripts/report_ast.py:1468)
- [cellcog_composer.py](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:98)

Add an explicit `set_facet_contract(contract)` or pass the contract into validation. The exact `planner_contract` used by `find_bundles()` must also be used by `_premise_with_span_facets()`.

Do not let `report_ast` independently recompile the question. That can produce different aliases and currently omits the composer’s polarity map.

## 1.4 Give deterministic verdicts a proof-carrying type

The planner’s verdict is currently an ordinary `Owned` node and therefore depends on another GLM frame-classification call. That creates a second path to `0` even after the source-index repair.

Add a frozen `ProvenVerdict` subtype of `Owned` in [report_ast.py](/home/polaris/wt/flywheel/scripts/report_ast.py:134):

```python
@dataclass(frozen=True)
class ProvenVerdict(Owned):
    operation: str = ""
```

Requirements:

- The LLM JSON parser must not construct this type.
- Only the deterministic planner may construct it.
- Validation must:
  1. Re-resolve every premise.
  2. Re-derive span facets.
  3. Re-run `validate()` and `prove()`.
  4. Re-render the verdict from a closed canonical template.
  5. Require node text to equal that canonical rendering.
- Skip only the redundant semantic frame judge after those checks pass. Ordinary `Owned` nodes continue through the judge.
- A forged `ProvenVerdict`, stale proof, altered text, missing span facet, same-source pair, or unknown operation still rejects.

Canonical templates should assert only the proved relation, for example:

```text
These findings concern different span-supported units of analysis—the firm and regional levels—and are not directly comparable.
```

For apparent conflict, use `RECONCILES` only when the stronger opposed-direction and compatible-horizon proof succeeds. Otherwise degrade to `CONTRASTS_LEVEL`; never manufacture “not contradictory.”

Update [cellcog_composer.py](/home/polaris/wt/flywheel/scripts/cellcog_composer.py:675) so `_verdict_node()` constructs this type from the recomputed proof.

Also print a refusal histogram:

```text
candidate comparison bundles
rejected: source-name
rejected: missing span-bound unit
rejected: unproved relation
placed
```

That makes another silent `840 -> 0` impossible.

# Phase 2 — Repair and extend the acceptance suite

Files:

- [scripts/_test_fixtures.py](/home/polaris/wt/flywheel/scripts/_test_fixtures.py:39)
- [scripts/test_fabrication_paths.py](/home/polaris/wt/flywheel/scripts/test_fabrication_paths.py:64)
- [scripts/test_gate_is_wired.py](/home/polaris/wt/flywheel/scripts/test_gate_is_wired.py:219)
- New: `tests/test_report_ast_identity_and_verdict_placement.py`

Replace hand-built manifestation profiles with the real construction path:

```text
ensure_work
→ ingest_bytes
→ event_ledger.derive_binding_core
→ Graph.resolve_attribution
→ CardBundle.resolve
```

Fixture text must contain randomized positive front-matter evidence—title/byline/DOI and generic journal-version furniture—so the identity reducer genuinely earns `IDENTITY_PROVEN`. Do not stamp `semantic_binding` directly in a positive test.

Acceptance assertions:

- P0 true finding passes for an identity-proven source.
- P1 span-proved different-unit verdict passes.
- Every negative attack still rejects for its intended semantic reason, not because an unstamped fixture masked it with `SOURCE_POLICY_REFUSES`.
- `None`, unknown tokens, `UNRESOLVED_BINDING`, and `DIFFERENT_WORK` reject.
- Editing card `venue`, `doi`, `authors`, or `attribution` cannot promote identity.
- `the` and `of` are absent from `_source_words`.
- `Acemoglu`, `Wu`, an exact corporate-author phrase, and a graph venue remain detectable.
- At least one comparison is placed and every placed verdict revalidates at final render.

Metamorphic test:

1. Generate several unrelated fixtures with random titles, DOIs, people, venues, subject words, and units.
2. Consistently rename all identifiers in both bytes and metadata: admission and placement count must remain unchanged.
3. Change only requested identity while holding bytes fixed: admission and placement must fall to zero for the changed source.
4. Add a corporate author of the form `on behalf of the <random> Consortium`: common prose tokens must remain usable, while the exact corporate name remains forbidden in owned prose.
5. Replace all venues: behavior must remain structural and contain no task-72, DOI, author, or venue literal.

Commands:

```bash
cd /home/polaris/wt/flywheel
export PYTHONPATH=scripts:src

pytest -q \
  tests/test_report_ast_identity_and_verdict_placement.py \
  tests/test_binding_gate_foundation.py \
  tests/test_binding_gate_acceptance.py \
  tests/test_runtime_contract_generality.py

python scripts/test_fabrication_paths.py
python scripts/test_gate_is_wired.py
```

Hard gate: do not compose until positive controls pass, all attacks remain closed, and placement is greater than zero.

# Phase 3 — Corpus decision

Use the 838-card curated corpus.

Why:

- It retains all 285 raw work IDs and all 279 admitted works found in the full corpus.
- It caps redundancy at three cards per work; the full corpus reaches 83 cards for a single work.
- The composer can use at most roughly 12 cards per subsection. An additional 4,531 admitted snippets do not create citation breadth.
- The curated set already yielded 840 candidate comparisons.
- The full set previously produced no usable comparisons, greatly enlarges planner/ledger work, and contains 299 duplicate IDs.
- “Journal articles only” is enforced by the graph’s expression policy, not by card count. The 820 admitted curated cards already resolve to journal-permitted expressions.

Pin and promote the current artifact:

```bash
cd /home/polaris/wt/flywheel
mkdir -p outputs/compose_inputs
cp \
  /tmp/claude-1000/-home-polaris-polaris-project/21e87760-8436-4090-870d-99ef2121882e/scratchpad/cards_curated.json \
  outputs/compose_inputs/task72_cards_curated.json

echo \
'a8a06549710525886f2d359acf918fd0c6676639617ce5f1b30f1efd06f91fb4  outputs/compose_inputs/task72_cards_curated.json' \
  | sha256sum --check -
```

Do not use keep-first dedup as the final compose input: 35 curated rows intentionally select a non-first variant of a duplicate ID with better facets/binding context.

# Phase 4 — Fixed compose and decisive score

Preflight:

```bash
cd /home/polaris/wt/flywheel
set -a
source .env
set +a

export PYTHONPATH=scripts:src
export PG_MAX_COST_PER_RUN=100000
export PG_RESEARCH_QUESTION="$(cat /home/polaris/polaris_project/task72_prompt.txt)"
export PG_GENERATOR_MODEL=z-ai/glm-5.2
export PG_GLM5_MIN_MAX_TOKENS=32000
export PG_GENERATOR_LLM_TIMEOUT_SECONDS=600

python -u scripts/cellcog_composer.py \
  --cards outputs/compose_inputs/task72_cards_curated.json \
  --graph outputs/provenance_graph.json \
  --ledger outputs/event_ledger.jsonl \
  --policy journal_articles_only \
  --dry | tee /tmp/task72_fixed_dry.log

grep -E 'comparison bundles found|sound cross-source verdicts placed' \
  /tmp/task72_fixed_dry.log
```

Acceptance: `sound cross-source verdicts placed` must be greater than zero. Zero is a failed build, not permission to render.

Compose:

```bash
python -u scripts/cellcog_composer.py \
  --cards outputs/compose_inputs/task72_cards_curated.json \
  --graph outputs/provenance_graph.json \
  --ledger outputs/event_ledger.jsonl \
  --policy journal_articles_only \
  --expect-cards-sha a8a06549710525886f2d359acf918fd0c6676639617ce5f1b30f1efd06f91fb4 \
  --write | tee /tmp/task72_fixed_write.log
```

Before scoring, require:

- Published report exists.
- Placed verdict count is positive.
- AST has zero unlawful nodes.
- Report has attributed findings and owned analytical verdicts.
- No second writer is running.

Score:

```bash
test -s outputs/release/report.md
! pgrep -af 'cellcog_composer.py.*--write'

python scripts/score_report_race.py \
  --report outputs/release/report.md \
  --task-id 72 \
  --model-name polaris_task72_flywheel_v1 \
  --race-model openai/gpt-5.5 \
  --max-workers 4

RESULT=third_party/deep_research_bench/results/race/polaris_task72_flywheel_v1/race_result.txt
cat "$RESULT"

python - "$RESULT" <<'PY'
import re, sys
text = open(sys.argv[1]).read()
score = float(re.search(r"Overall Score:\s*([0-9.]+)", text).group(1))
assert score > 0.5603, f"MISS: {score:.4f} <= 0.5603"
print(f"BEAT RACE: {score:.4f} > 0.5603")
PY
```

The task is complete only if that final assertion passes.

# Phase 5 — Audit after the score

Defer it completely until Phase 4 finishes. It is not an input to the selected corpus, and its current quarantine calibration is unusable.

Then edit [glm_transport.py](/home/polaris/wt/flywheel/scripts/card_audit/glm_transport.py):

- Replace `asyncio.run()` and per-call `OpenRouterClient` construction with a thread-local synchronous `httpx.Client`.
- POST non-streaming to `/chat/completions`.
- Preserve retries, fail-closed behavior, usage accounting, and result envelope.
- Add a transport test proving repeated threaded calls do not create event loops or leak clients.

Resume from the durable 394-row checkpoint:

```bash
cd /home/polaris/wt/flywheel
python3 scripts/card_audit/run_audit.py --workers 9
```

Treat its output as diagnostic until the separate Tier-0/entailment over-quarantine calibration is repaired.