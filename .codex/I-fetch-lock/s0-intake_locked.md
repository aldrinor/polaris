# SECTION 0 = S0 INTAKE — LOCKED

Branch: `bot/intake-core`. Date locked: 2026-07-10 (I-fetch-lock).

This is the intake section of the POLARIS pipeline — the very front door, before
any web fetch. Its job is to turn the operator's request into one resolved
`RunConfig`: read the prompt AND the control panel, parse every scope /
deliverable / breadth ask, resolve each knob through the fixed precedence ladder
(PANEL > PROMPT > ENV > CODE-DEFAULT), and write the cp0 checkpoint that every
later section reads. When it is done, the run has one settled control object and
a cp0 on disk. Everything after it (fetch, select, consolidate, compose, verify,
render) is a later section and is NOT locked by this record.

It touches no claim gate. The faithfulness engine is untouched. This section is
pure logic — regex extractors + a registry-driven precedence resolver + a cp0
writer. It never relaxes, moves, or replays a faithfulness decision.

---

## 1. The passing iter — what we locked

S0 intake is locked at this build:

- **Commit `0b9a8886`** — "S0 INTAKE: RunConfig from prompt + control panel
  (master §1, Design 3, Design 7 D1 parse)".
- Files: `src/polaris_graph/run_config.py` (the registry-driven resolver +
  cp0 writer/loader), `config/settings/run_config_knobs.yaml` (the knob
  registry — single source of knob truth, 31 registered knobs at this build),
  `src/polaris_graph/retrieval/breadth_directive_parser.py`,
  `src/polaris_graph/retrieval/deliverable_spec_extractor.py`,
  `scripts/intake_selftest.py`, `tests/polaris_graph/test_s0_intake_run_config.py`.

Two offline proofs, both re-run at lock time with the LLM passes OFF
(`llm_fn=None` everywhere) and an empty env — no network, no GPU, no LLM:

- **`scripts/intake_selftest.py` — ALL PASS.** All five acceptance conditions
  returned `pass: true`; `all_pass: true`; `registry_knob_count = 31`;
  `network_used: false`; `gpu_used: false`. Exit code 0.
- **`tests/polaris_graph/test_s0_intake_run_config.py` — 17 passed in 3.36s.**
  Every guard test green (see §4 for the one environment note).

The self-test is deterministic and lives inside the committed build, so this is
the passing iter, not a one-off. The five conditions below quote the self-test's
own machine-written evidence strings verbatim.

The self-test drives one rich prompt that carries scope + deliverable + breadth
asks at once, so conditions (a), (b), (c) read the SAME resolved object exactly
as production would:

> Write a two-page plain-language policy memo with Harvard references and an
> executive summary first, about 1500 words, on randomized trials of tirzepatide
> published since 2019 and before June 2023, using peer-reviewed journal articles
> only, focused on European sources, in English, and prioritize research by
> Anthony Fauci. Run at least 45 queries with 20 searches per query. Include a
> section on cardiovascular outcomes and organize by region.

---

## 2. The five conditions — quoted evidence

### (a) SCOPE PARSED — dates / source-type / geography / language / author each land as `parsed`

Every scope axis the operator named must be pulled out of the prompt and land in
`RunConfig` carrying `source='parsed'` (not a default, not a guess) with the
verbatim prompt span it came from.

> `all five scope axes parsed: dates='2023-06'<-'before June 2023' |`
> `source_type=['peer_reviewed_journal']<-'peer-reviewed journal' |`
> `geography=['European']<-'European sources' | language='en'<-'English' |`
> `author=['Anthony Fauci']<-'prioritize research by Anthony Fauci'`

Read plainly: the end-date `2023-06` came from `'before June 2023'`; the
source-type restriction `peer_reviewed_journal` from `'peer-reviewed journal'`;
geography `European` from `'European sources'`; language `en` from `'English'`;
author `Anthony Fauci` from `'prioritize research by Anthony Fauci'`. Each value
carries its own span, so it is a real parse, not an invented value.

### (b) DELIVERABLE PARSED — tone / structure / reference_style / length each land

The shape-of-the-answer asks must parse the same way: tone, structure slots,
reference style, and a length target each land as `parsed` with their spans.

> `tone/structure/reference_style/length parsed: tone=plain_language<-'plain-language' |`
> `structure=2 slots<-'Include a section on cardiovascular outcomes and organize by`
> `region; organize by region' | reference_style=harvard<-'Harvard references' |`
> `length=1500<-'about 1500 words'`

Read plainly: tone `plain_language` from `'plain-language'`; two structure slots
from the cardiovascular-section + organize-by-region asks; reference style
`harvard` from `'Harvard references'`; length target 1500 words from
`'about 1500 words'`.

### (c) BREADTH PARSED — query_count (35+ case) + searches_per_query land

The breadth asks — how many queries and how many searches per query — must parse,
and the query-count path is proven on a real 35+ number so the parser is not
silently capping.

> `query_count parsed >=35: query_budget=45 (35+ case)<-'Run at least 45 queries';`
> `searches_per_query=serper_k=20<-'20 searches per query'`

Read plainly: `query_budget=45` (a 35+ value, honoured, not clamped) from
`'Run at least 45 queries'`; `serper_k=20` (searches per query) from
`'20 searches per query'`.

### (d) PANEL BEATS PROMPT — control-panel override wins the precedence ladder

The whole point of the control surface: when the same knob is set on BOTH the
prompt and the control panel, the panel wins. The self-test parses
`query_budget=45` from the prompt, then sets the SAME knob to 99 on the panel and
reads it back.

> `prompt parsed query_budget=45 (source=parsed); control panel set query_budget=99`
> `-> resolved 99 (source=panel) - panel beats prompt`

Read plainly: with the prompt asking for 45 (source `parsed`), a panel override of
99 resolves to 99 with source `panel`. Panel beats prompt — the top rung of the
PANEL > PROMPT > ENV > CODE-DEFAULT ladder, proven end to end.

### (e) CP0 EVERY KNOB, NONE HARDCODED — cp0 carries all 31 knobs with a declared source

The cp0 checkpoint the intake section writes must carry EVERY registered knob, each
with a resolved source from the allowed layer set, and every default-sourced value
must equal the registry's `code_default` — proving the value came from the
`run_config_knobs.yaml` registry, never a literal buried in `run_config.py`. The
cp0 must also round-trip.

> `cp0 carries all 31 registry knobs, each with a source in`
> `['default', 'env', 'panel', 'parsed']; 14 default-sourced values all equal the`
> `registry code_default (none hardcoded); round-trip sha ok`

Read plainly: all 31 registry knobs are present in cp0, each tagged with a source
in `{default, env, panel, parsed}`; the 14 knobs that fell through to their code
default all equal the registry yaml value (zero mid-pipeline hardcodes, the
LAW VI guarantee); and cp0 reloads with a matching `question_sha`. An empty ask
therefore resolves to the registry defaults byte-for-byte, and every operator ask
flips the relevant knob's source off `default` to `parsed`/`panel`.

---

## 3. What "locked" means here

Locked means: the intake contract is the settled front door of the run. The four
things below are fixed, and every later section reads them rather than re-deriving
its own control values:

1. The precedence ladder PANEL > PROMPT > ENV > CODE-DEFAULT (condition d).
2. Scope parsing on all five axes (condition a).
3. Deliverable + breadth parsing (conditions b, c).
4. A cp0 checkpoint carrying all 31 registry knobs with declared sources, zero
   hardcodes (condition e).

Not locked by this record: fetch, select, consolidate, compose, verify, render.
Those are the later sections. This section only produces the resolved `RunConfig`
and the cp0 checkpoint — it does not fetch, weight, or compose anything.

Faithfulness engine: untouched. No claim gate was relaxed, moved, or replayed.
The intake layer is pure parsing + resolution + a data-only cp0 write.

---

## 4. How to re-prove it (offline, no spend)

The portable, load-bearing proof of the five conditions:

```
python scripts/intake_selftest.py --out summary.json
```

Pure logic — no network, no GPU, no LLM. It writes `summary.json` with each of the
five conditions as a boolean plus its evidence string, and exits 0 only if all five
pass. This reproduces in any fresh checkout of `bot/intake-core`.

The guard suite is a second proof:

```
python -m pytest tests/polaris_graph/test_s0_intake_run_config.py -q   # 17 passed
```

Honest note (LAW II): this test module itself is pure logic, but the
`tests/polaris_graph/` package conftest has an autouse fixture that imports the
Phase-B inspector registry at collection time, and that registry validates a
canonical demo artifact (`outputs/full_scale_v30_phase2_run14/clinical/clinical_tirzepatide_t2dm`).
That `outputs/` artifact is a gitignored runtime output, so in a bare fresh
worktree collection ERRORS with `RegistryError: Allowlisted artifact directory
missing` — this is an unrelated Phase-B environment coupling, NOT an S0 intake
failure. With the canonical demo artifact present (as in the main working copy),
the suite is a clean 17 passed. The 17-passed result at lock time was produced with
that artifact present. The self-test above needs no such artifact and is the
primary offline proof.
