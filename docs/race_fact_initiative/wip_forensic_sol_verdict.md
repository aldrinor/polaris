# SOL forensic verdict — all uncommitted changes in `faithoff`

Date: 2026-07-24 UTC  
Worktree: `/home/polaris/wt/faithoff`  
Mode: read/run-only. No repository file was modified by this audit.

## Executive verdict

**NO — do not launch the champion re-baseline from this worktree “as-is” using either new RACE launcher.**

The generation-code delta is an almost purely mechanical module rename and is safe for the fixed task-72 corpus: the old and new deletion modules implement the same predicates, the old module is a real `sys.modules` alias, and an executed scan of all 997 fixed-corpus rows found **zero deletion candidates**. The provenance and strict-verification engines are untouched.

The blocking problem is instead the two untracked launchers:

* `scripts/run_race_batch3_max.sh`
* `scripts/run_race_max_focus.sh`

They do **not** launch Gate-B and do **not** turn V30 on. Their actual path is:

```
run_race_*.sh
  -> baseline_triple.sh
  -> run_k3.sh
  -> run_raw_a.sh
  -> compose_agentic_report_s3gear329.py
  -> generate_multi_section_report()
```

`run_raw_a.sh:47-48` explicitly sets `PG_STRICT_VERIFY_OFF=1` and
`PG_ENABLE_ENTAILMENT=0`. The compose harness applies the default-on composition scope
contract before generation (`scripts/compose_agentic_report_s3gear329.py:422-499`).
Existing outputs from these exact launchers show the fixed 997-row corpus reduced to only
13–16 composition rows per draw. The resulting run is neither “V30-on” nor a valid
faithfulness-preserving Gate-B champion measurement.

**Exact minimal pre-launch quarantine:** stash the two untracked launcher files above
(including untracked files in the stash) and do not use them for the champion. Launch through
the real Gate-B/V30 route or a separately corrected, reviewed recipe. None of the other dirty
files must be reverted to prevent generation behavior in this particular frozen-corpus
re-baseline.

This is a launcher/configuration rejection, not a claim that merely having two inert shell
files present changes a different command. If the operator invokes a separately verified
Gate-B command, their presence is inert; they are listed as the minimal stash because they are
the only dirty artifacts presenting themselves as the requested RACE re-baseline entry point,
and invoking either would invalidate the measurement.

## Per-item verdict table

| Item | What the actual changed lines do | Active under Gate-B / V30? | Expected RACE/FACT direction | Ghost / post-gen / corpus subtraction | Criticality | Verdict |
|---|---|---|---|---|---|---|
| `acceptance_result.json` | Replaces a previous acceptance-harness result with a replay-like result: thin run 13→31 rows in 3 turns/3 searches; saturated run remains 8→8 in one turn. It contains timings and disclosure strings only; it is not executable configuration. | **No.** It is written by `tests/oracle/acceptance_portable.py:472-475,533-538`; no generation code reads it. | None. It cannot affect a run. | None. Data artifact only. | Stale/mutable acceptance output. | **DEAD-OR-STALE** |
| `src/polaris_graph/audit_ir/__init__.py` | Adds exports for `V30ClinicalSweepJobRunner`, its config, and its default factory while retaining the old exported names (`:29-35,147-155`). | **No** on the report-generation path. This is audit/queue API exposure. | None for RACE/FACT output. | None. | Audit infrastructure compatibility surface. | **IRRELEVANT-INFRA** |
| `src/polaris_graph/audit_ir/honest_sweep_job_runner.py` | Renames the config/class/factory to `V30Clinical*` (`:164-190,450-460`) and binds old names to the new objects (`:463-473`). The subprocess still targets `scripts/run_full_scale_v30_phase2.py` (`:455-458`); run/checkpoint logic is unchanged. | **No** for a direct Gate-B generation. Active only when the asynchronous `v30_clinical` job runner is used. | Neutral: naming-only behavior delta. | None. | Useful audit-job refactor, not report generation. One comment overclaims monkeypatch compatibility: initial alias identity is true, but rebinding one module attribute does not update the other. Executed probe: `factory_alias_initial=True`; `old_name_rebind_updates_new_name=False`. | **IRRELEVANT-INFRA** |
| `src/polaris_graph/audit_ir/inspector_router.py` | Registration now imports and calls `make_default_v30_clinical_sweep_job_runner` instead of the old factory name (`:402-426`). It still registers the same runner/template and swallows construction failures with a warning. | **No** for generation. Active only when the audit job queue initializes. | Neutral. | None. | Audit queue wiring. | **IRRELEVANT-INFRA** |
| `src/polaris_graph/generator/junk_deletion_gate.py` | Replaces the old implementation with a compatibility module that imports `content_integrity_deletion_gate` and installs that exact module object into `sys.modules[__name__]` (`:1-28`). | **Yes indirectly.** The run-level seam still imports the old path; it receives the canonical module object. | Semantics are unchanged from HEAD. No score delta on task 72 because its 997 rows produce zero delete decisions. | The underlying gate is authorized pre-generation pool subtraction, not a ghost or post-generation edit. Details below. | Compatibility shim for a generation-critical module. Module-level monkeypatches are observable; rebinding the legacy function alias alone is not. | **INCLUDE-IN-CHAMPION** |
| `src/polaris_graph/generator/content_integrity_deletion_gate.py` | Untracked canonical copy of the former junk gate. The substantive code delta is the predicate rename `is_row_content_junk` → `is_row_content_integrity_violation`, an old-name alias, and log-prefix/name changes. `partition_rows` calls the new canonical predicate (`:250`). | **Yes.** Run-level partition is called in `run_honest_sweep_r3.py:15919-15938`; compose-time screening is called under route-all in `multi_section_generator.py:12030-12074`. Gate-B forces route-all on. Deletion flags themselves are default-on, not Gate-B forced. | Bidirectional in principle: removing real chrome/off-subject rows can improve focus; a false positive removes coverage and can reduce comprehensiveness. On the fixed task-72 corpus the executed effect is exactly zero. | Authorized pre-generation subtraction under `CLAUDE.md §-1.3.1`; no verification bypass. It can remove what the writer may use, but cannot make an unsupported claim pass. | Generation-critical implementation, but byte-equivalent behavior to tracked HEAD apart from naming. | **INCLUDE-IN-CHAMPION**, with the predicate caveats in the deep section |
| `src/polaris_graph/generator/multi_section_generator.py` | Changes one lazy import from the old module path to the canonical new path (`:12045`). The call remains `is_row_deletable_offtopic(ev)` at compose (`:12058-12061`). No other generator logic changed. | **Yes.** `route_all_baskets_enabled()` resolves true by default and Gate-B explicitly force-sets `PG_ROUTE_ALL_BASKETS=1`. | No delta versus HEAD because the shim and canonical function are the same implementation. On task 72 all 997 calls return false. In max/full arms facet packing later restores every unrepresented row anyway. | This screen omits orphan off-topic baskets before prose composition, but it is pre-generation, not a post-generation edit or ghost. It does not alter verification. | Active one-line rename wiring. | **INCLUDE-IN-CHAMPION** |
| `tests/oracle/cassette.py` | On a replay miss, optionally writes a debug JSON containing the missed method/args and same-method recorded calls before raising (`:168-186`). It does not change successful replay behavior. | **No.** Test oracle only. | None. | None. | Helpful replay diagnostics. | **IRRELEVANT-INFRA** |
| `tests/oracle/llm_cassette.py` | Adds deterministic serialization for structured LLM calls and patches both `generate` and `generate_structured` during a cassette session (`:77-165`), restoring both afterward. | **No.** Test oracle only; no production imports. | None. | None. The test double does not weaken live verification. | Useful but incomplete test double: the `generate` wrapper does not expose the live client’s `reasoning_effort` parameter. Current acceptance call sites do not pass it. | **IRRELEVANT-INFRA** |
| `scripts/run_race_batch3_max.sh` | Hard-codes task 72 and the 997-row corpus, defines max/full/baseline environment arms (`:4-46`), and runs three draws for all three arms via `baseline_triple.sh` (`:48-63`). It uses `set -uo pipefail`, not `set -e`; `run_arm` prints after the child call, so an arm failure can be converted to success, and the final success message can yield exit 0 (`:2,48-65`). | **No.** It never calls `run_gate_b.py`; it reaches raw-A. It never sets V30. | Existing measurements are not improvements: baseline mean 0.500900, full 0.496600, max 0.493333. More importantly, the scores are invalid for the requested V30/Gate-B champion because faithfulness is disabled and only 13–16/997 rows reach composition. | **Yes, as invoked behavior:** raw-A explicitly disables strict verification/entailment, and the composition scope contract subtracts hundreds of fixed-pool rows before generation. No post-generation edit in the shell file itself, but it selects a banned/non-champion execution mode. | Intended champion launcher; load-bearing and unsafe for that purpose. | **FLAG — STASH BEFORE CHAMPION** |
| `scripts/run_race_max_focus.sh` | Runs selected arms (default max) through the same `baseline_triple.sh` chain (`:4-49`). It has the same missing `-e`/status-masking problem; unknown arm names merely print a message and execution continues (`:33-47`). | **No.** Same raw-A, non-V30 route. | Same invalid score basis and fixed-pool collapse as batch3. | Same strict-verification/entailment disable and scope reduction selected by the invoked chain. | Intended focused launcher; unsafe for champion use. | **FLAG — STASH BEFORE CHAMPION** |
| `tests/oracle/acceptance_portable.py` | Builds thin and saturated acceptance cases (`:88-296`), sets deterministic feature flags (`:63-70`), records/replays retrieval+LLM cassettes (`:431-507`), canonicalizes timings/disclosures (`:333-365`), and writes `acceptance_result.json` by default (`:525-538`). | **No.** Standalone oracle harness, not imported by production or pytest collection. | None for generation. | None. | Not yet portable from this worktree: the retrieval and LLM cassette tapes are absent. Replay can also create a missing golden file (`:477-483`), which can accidentally bless current behavior instead of comparing to an independently recorded oracle. | **IRRELEVANT-INFRA** |
| `tests/oracle/retrieval_cassette.py` | Records or replays `LiveRetrievalResult`, reconstructing evidence rows and patching live retriever references (`:31-198`). | **No.** Test-only monkeypatching. | None live. It can, however, hide oracle regressions: request identity omits `max_serper_results`, `max_s2_results`, and `fetch_cap` (`:67-91`), even though they alter retrieval output; replay also ignores seed/progress extras. | None live. | Test infrastructure with under-keyed cassette identity. | **IRRELEVANT-INFRA** |
| `tests/oracle/cassettes/acceptance_golden.json` | Frozen canonical expected output for the portable acceptance harness. It contains the same thin/saturated control facts as the current result but normalized timing. | **No.** Read only by the standalone oracle harness when that harness is invoked. | None live. | None. | Golden without the associated retrieval/LLM tapes; currently not independently replayable. | **DEAD-OR-STALE** until tapes/CI wiring exist |

## Exact active-path proof

### Real Gate-B / V30 path

`scripts/dr_benchmark/run_gate_b.py` applies its slate before running a query
(`:5607-5653`). The slate sets `PG_ROUTE_ALL_BASKETS=1` (`:1291-1298`), includes that
flag in the force-on set (`:2377-2384`), requires it (`:2048-2055`), and allows it
through sanitization (`:3967-3974`). The pre-spend checks reassert the slate
(`:4461` onward). An executed environment probe after applying the slate returned:

```
PG_ROUTE_ALL_BASKETS=1
route_all_baskets_enabled=True
```

The route-all default also resolves true through
`src/polaris_graph/generator/config_defaults.py:803`, but Gate-B does not rely on the
default.

The four deletion controls are different:

```
PG_DELETE_CHROME_NONSOURCE
PG_DELETE_OFFTOPIC_SOURCE
PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY
PG_DELETE_OFFTOPIC_FRESH_VERDICT_ONLY
```

They are default-on in `content_integrity_deletion_gate.py:73-102`; none is in the
Gate-B slate, force-on set, required set, or allowlist, and none was present in either
inspected `.env`. Thus the gate is on under the observed Gate-B environment because
of module defaults, not because Gate-B pins it. An explicit process environment can
still disable it.

Gate-B also sets the V30 flags immediately before entering `run_one_query`
(`run_gate_b.py:5812-5813`). The run-level partition happens in
`scripts/run_honest_sweep_r3.py:15919-15968`, then the surviving pool flows to
multi-section generation.

### The two RACE shell files are not that path

Both untracked scripts call `scripts/race_fact/baseline_triple.sh`. That calls
`run_k3.sh`, which pins the Kimi K3 generation model and execs `run_raw_a.sh`
(`run_k3.sh:25-35`). Raw-A explicitly documents and implements a faithfulness-off
ablation:

```
PG_STRICT_VERIFY_OFF=1       # run_raw_a.sh:47
PG_ENABLE_ENTAILMENT=0       # run_raw_a.sh:48
```

It then calls `compose_agentic_report_s3gear329.py` (`run_raw_a.sh:75-76`), not
`run_gate_b.py`. No V30 flag is set in this chain.

The compose script applies the composition scope contract before the generator
(`compose_agentic_report_s3gear329.py:422-499`) and only later calls
`generate_multi_section_report` (`:630-648`). Existing compose summaries from these
launchers prove the effect:

| Arm | Input rows | Rows reaching composition across its three draws | Relevant flags |
|---|---:|---:|---|
| baseline | 997 | 14, 13, 13 | strict off, entailment off, route-all on, facet packs off, V30 unset |
| full | 997 | 15, 14, 13 | strict off, entailment off, route-all on, facet packs on, V30 unset |
| max | 997 | 16, 13, 13 | strict off, entailment off, route-all on, facet packs on, V30 unset |

That is executed-output evidence, not an inference from comments.

## Deep forensic analysis: content-integrity / junk-deletion gate

### What changed versus HEAD

A direct diff between HEAD’s full `junk_deletion_gate.py` and the new
`content_integrity_deletion_gate.py` showed only:

1. canonical module/log naming;
2. `is_row_content_junk` renamed to
   `is_row_content_integrity_violation`;
3. `is_row_content_junk` retained as a bound compatibility alias
   (`content_integrity_deletion_gate.py:120-124`);
4. `partition_rows` calls the new canonical name (`:250`);
5. the old file becomes a `sys.modules` alias shim (`junk_deletion_gate.py:1-28`).

There is no new deletion criterion in the uncommitted delta.

### Exact deletion predicates

The partition is order-preserving and returns `(kept, deleted)`. It makes a copy only
of a deleted row to add `deletion_reason`; it does not mutate input rows
(`content_integrity_deletion_gate.py:212-270`).

A row is deleted only if its ID is not exempt and one of these branches fires:

1. **Content-integrity/chrome branch** (`:105-117,250-253`)

   * Enabled unless `PG_DELETE_CHROME_NONSOURCE` is an off token.
   * Reads only `row["content_integrity_junk"]`.
   * Missing/false/empty/off-token values keep the row.
   * Any other truthy value deletes it.
   * Exceptions keep the row.

   There is no lexical, tier, numeric relevance, NLI, or entailment calculation in
   this predicate. It trusts an upstream stamp. The implementation is broader than
   “boolean judge verdict only”: for example the string `"unknown"` is truthy and not
   an off token, so it deletes. Executed probe:

   ```
   content_integrity_junk="unknown" -> True
   content_integrity_junk="false"   -> False
   ```

2. **Default topic-judge-only branch** (`:146-160,163-209,254-261`)

   * Enabled unless `PG_DELETE_OFFTOPIC_SOURCE` is an off token.
   * The default `PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY=1` selects this branch.
   * A positive `content_relevance_label` of `relevant` or
     `escalated_relevant` vetoes deletion unconditionally (`:192-194`).
   * It then requires an affirmative subject-level stamp:
     `topic_off_subject is True`, one of the accepted affirmative strings, or
     `topic_relevance_verdict == "off_subject"` (`:146-160,195-196`).
   * `topic_offtopic_demoted` alone does not delete.
   * `demoted`, `escalated_demoted`, numeric reranker scores, tiers, lexical
     matches, NLI results, and missing verdicts do not delete on this path.
   * When a concrete `fresh_off_subject_ids` collection is supplied and
     fresh-only mode is on, the row ID must be in that set (`:199-202`).
   * Errors keep the row.

3. **Legacy off-topic branch** (`:127-143,261-263`)

   This is reachable only when
   `PG_DELETE_OFFTOPIC_TOPIC_JUDGE_ONLY=0`. It calls
   `weighted_enrichment._is_confirmed_offtopic`, reintroducing the older weighted
   enrichment interpretation. It is not the observed default Gate-B path, but it is
   a real kill-switch path and therefore the blanket claim “a lexical/tier/number
   path can never delete” is true only while topic-judge-only remains on.

4. **Exemption** (`:234-248`)

   Any ID in `exempt_ids` is kept before either deletion branch.

Executed predicate matrix:

```
missing verdict/stamp                         -> kept
topic_offtopic_demoted only                   -> kept
topic_off_subject=True                        -> deletable
topic_relevance_verdict=OFF_SUBJECT           -> deletable
OFF_SUBJECT + positive relevance conflict     -> kept
off-aspect / demoted-only                     -> kept
stale OFF_SUBJECT, fresh IDs omitted (None)   -> deletable
stale OFF_SUBJECT, concrete empty fresh set   -> kept
```

### The run-level and compose-time calls do not have identical safety properties

The run-level call in `run_honest_sweep_r3.py:15919-15938` is the stronger one:

* it passes a concrete `_fresh_off_subject_ids` set made by the current topic-judge
  pass (`:13872-13969`);
* it exempts marquee and `v30_entity_id` contract anchors (`:15926-15931`);
* it records disclosure before atomically replacing the pool (`:15939-15963`);
* the entire seam catches exceptions and keeps the pre-partition pool (`:15964-15968`).

The upstream topic judge is a semantic LLM split and fails open on errors/unparseable
responses (`topic_relevance_gate.py:288-315,635-653`). It stamps OFF_SUBJECT at
`:704-709` and clears stale subject stamps for ON/OFF_ASPECT verdicts at `:710-726`.

However, the judge is asked about the **main research question**, not each source’s
originating subquery (`run_honest_sweep_r3.py:13948-13954`;
`topic_relevance_gate.py:340-343`). A source legitimately serving a distinct
subquestion can therefore be falsely classified OFF_SUBJECT. Freshness proves only
that the judgment happened in this run; it does not prove the judgment is correct.

The compose-time call is weaker:

```python
is_row_deletable_offtopic(ev)
```

at `multi_section_generator.py:12058-12061` supplies neither fresh IDs nor exemptions.
Consequences:

* a stale OFF_SUBJECT stamp is deletable because `fresh_off_subject_ids=None`
  disables the freshness check;
* marquee/contract IDs have no exemption at this call;
* a false-positive subject stamp can suppress an otherwise useful orphan basket.

The router still skips already-claimed baskets before applying the off-topic test
(`verified_compose.py:3945-3954`), so it cannot remove a basket that a section already
claims. It omits only orphan singleton/baskets from route-all placement
(`:3951-3978`).

For max/full configurations, facet evidence packing runs after the router
(`multi_section_generator.py:12090-12115`). Its lossless fallback assigns every
unrepresented evidence row, including zero-overlap rows, to a stable section
(`facet_evidence_packs.py:208-223`). An executed fixture confirmed:

```
route-all router: off-topic orphan -> omitted
facet pack after router: same ID -> restored; missing IDs=[]
already-claimed off-topic basket -> retained by router
```

Thus the compose deletion screen is score-relevant in configurations without the
lossless facet pack (notably the baseline arm); max/full later restore the row. The
run-level pool partition, when it fires, remains globally load-bearing because a row
removed there cannot be restored downstream.

### Can it delete a good or load-bearing source?

**Yes.** There are three proven false-positive surfaces:

1. an upstream detector writes any truthy non-off string such as `"unknown"` into
   `content_integrity_junk`;
2. the main-question topic judge incorrectly marks a valid subquery source
   OFF_SUBJECT;
3. the compose-time call sees a stale OFF_SUBJECT stamp because it does not receive a
   fresh-ID set.

Positive relevance vetoes only the off-topic branch, not the content-integrity branch.
Marquee/contract exemptions exist only at the run-level partition, not at compose.

There is no direct tier/number/lexical delete in the observed default branch and no
missing-verdict delete. The legacy weighted path becomes reachable only if the
topic-judge-only flag is explicitly disabled.

### Score direction

The direction is inherently conditional:

* **Potential help:** removing real navigation chrome, bot pages, unrelated PDFs, or
  truly off-subject sources prevents low-quality baskets from consuming prose and can
  improve focus/relevance.
* **Potential harm:** a false positive removes source coverage, distinct facts, and
  citation opportunities. At run level it permanently reduces what the writer may
  say; under a comprehensiveness-heavy RACE/FACT judge this is a direct downside.

The fixed corpus gives a concrete answer for this specific re-baseline. The resolved
task-72 corpus contains 997 rows. An executed full scan found:

```
topic_off_subject present:              0
topic_relevance_verdict present:        0
content_integrity_junk present:         0
is_row_deletable_offtopic(row):         0 / 997
is_row_content_integrity_violation(row):0 / 997
```

It does contain 633 `topic_offtopic_demoted` rows, but the default predicate correctly
keeps those. Therefore the uncommitted gate rename/import is a **behavioral no-op on
the frozen corpus at compose time**. A preceding live scope/topic phase could create
new stamps; the raw-A launcher’s tracked composition scope contract is what actually
caused the observed 997→13–16 collapse, not this uncommitted predicate.

### Faithfulness safety and ban classification

This is **pre-generation corpus subtraction**, expressly covered by the operator’s
`CLAUDE.md §-1.3.1` exception for stamped content-integrity junk and semantically
confirmed whole-source OFF_SUBJECT material. It is not a post-generation prose edit.
It is not entailment/NLI admission logic, premise binding, or an emitted==admitted
ghost.

Its faithfulness property is monotonic:

1. the row is removed before the grounding snapshot/generator;
2. the writer therefore loses that permitted evidence;
3. strict verification never receives the missing row as a valid grounding anchor;
4. removing a row cannot turn an unsupported claim into a supported one.

It can hurt breadth, and a false positive can deprive an otherwise supported claim of
its anchor, causing that claim to fail or never be written. That is a
comprehensiveness/availability risk, not a mechanism by which an unsupported claim
passes.

## Compatibility audit of the rename

Executed module identity checks returned:

```
old import is canonical module:      True
importlib old is canonical module:   True
sys.modules objects identical:       True
patch canonical predicate via old module observed by partition: True
```

The shim itself is therefore correct. One narrower compatibility claim is false:
`is_row_content_junk` is a one-time function-object alias at
`content_integrity_deletion_gate.py:120-124`, while `partition_rows` looks up
`is_row_content_integrity_violation` at runtime (`:250`). Rebinding only the legacy
function name does not replace the canonical global used by `partition_rows`.
Executed result:

```
patch_old_function_alias_seen_by_partition=False
```

Repository search found no existing test/production caller monkeypatching that legacy
function name, so this is not a live champion behavior break. It does make the
docstring’s broad “patching any predicate on either name” claim too strong.

The audit-runner aliases have the same Python rebinding limitation:

```
HonestSweepJobRunner is V30ClinicalSweepJobRunner                         True
old default factory is new default factory                               True
rebinding old factory attribute updates new factory attribute            False
```

Again, that is audit infrastructure rather than report generation.

## Oracle/test-infrastructure findings

The untracked acceptance harness is not wired into pytest or production. It also is
not currently portable from the worktree because only
`acceptance_golden.json` exists; the retrieval and LLM JSONL tapes named at
`acceptance_portable.py:314-318` are absent.

`retrieval_cassette.py` under-keys replay requests. Its key omits
`max_serper_results`, `max_s2_results`, and `fetch_cap` (`:67-91`) even though the live
retriever uses those values to cap/change results
(`live_retriever.py:5694-5723`). It also accepts seed-related extras in the wrapper
but does not include them in replay identity. This can make a test replay pass under
a materially different retrieval configuration. It has no live-generation impact.

`llm_cassette.py` correctly patches/restores both normal and structured methods for
the current harness. Its ordinary `generate` wrapper does not mirror the live
`reasoning_effort` argument, so a future acceptance call that supplies that keyword
will fail at the test double rather than record/replay it.

## Mechanical and executed checks

* Read every tracked diff and every untracked file in full.
* Python AST parsing succeeded for all changed/untracked Python files.
* `bash -n` succeeded for both untracked shell files.
* JSON parsing succeeded for `acceptance_result.json` and the golden cassette.
* `git diff --check` succeeded.
* Focused tests: **80 passed, 1 skipped** in 8.63 s across:
  * junk deletion gate;
  * honest sweep runner;
  * S4 coverage parsing;
  * route-all;
  * RACE batch configuration;
  * Gate-B seam.
* Final `git status --short` matched the initial dirty inventory; the audit introduced
  no repo change.

### Faithfulness-engine immutability proof

The exact command

```
git diff --quiet -- \
  src/polaris_graph/generator/provenance_generator.py \
  src/polaris_graph/clinical_generator/strict_verify.py
```

returned exit code **0**, and `git status --short` returned no entry for either path.
The only `multi_section_generator.py` delta is the one-line module import rename.
Therefore:

* `provenance_generator.py` is **UNTOUCHED**;
* `clinical_generator/strict_verify.py` is **UNTOUCHED**;
* no dirty change weakens or bypasses those engines.

The raw-A launchers are rejected precisely because their invoked environment turns
strict verification and entailment off; that is configuration selected by the new
entry points, not a modification to either engine.

## Final go/no-go

**Safe to run the champion re-baseline as-is: NO.**

**Minimal set to stash/quarantine first:**

1. `scripts/run_race_batch3_max.sh`
2. `scripts/run_race_max_focus.sh`

They are untracked, so a normal tracked-only stash is insufficient; the quarantine
must include untracked files. Do not substitute either launcher for Gate-B. The next
generation spend should use a command whose executed environment proves all of the
following before the first paid call:

* it enters `run_gate_b.py`;
* V30 is on;
* `PG_STRICT_VERIFY_OFF` is not enabled;
* entailment is enabled as required by Gate-B;
* the fixed 997-row corpus is not collapsed by the raw-A composition scope contract;
* route-all is pinned on;
* the exact draw/arm labels correspond to the intended champion measurement.

The canonical deletion-gate rename, shim, and one-line generator import may remain:
they preserve tracked behavior, touch no faithfulness engine, and make zero decisions
on the fixed task-72 corpus. The unrelated audit/oracle artifacts do not enter
generation and do not need to be reverted for run correctness, though the stale
acceptance artifacts should not be represented as a complete portable CI oracle.
