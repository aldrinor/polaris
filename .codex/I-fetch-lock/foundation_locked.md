# FOUNDATION (WAVE 0) — LOCKED

Branch: `bot/foundation-core`. Date locked: 2026-07-10 (I-fetch-lock).

This is the WAVE-0 foundation that every pipeline section reads. It is two
things and only two things:

1. A **RunConfig control surface** — one registry of knobs, one resolver, a
   fixed precedence chain (PANEL > PROMPT > ENV > CODE-DEFAULT). Every knob the
   operator can set flows through this one door.
2. A **checkpoint envelope** — one uniform, data-only save/load format for the
   seven section-boundary checkpoints cp0..cp6, hash-chained, with a
   resume-from-any-point resolver and downstream-only RunConfig adjustment.

It touches no claim gate. The faithfulness engine is untouched. This PR is
additive only — no existing writer was migrated. Everything after this
(fetch, select, consolidate, compose, verify, render) is a later section and is
NOT locked by this record.

---

## 1. The passing iter — what we locked

The foundation is locked at the WAVE-0 build:

- **Commit `9df36fcd`** — "foundation-core (WAVE 0): RunConfig control surface +
  knob registry + resolver + cp0..cp6 checkpoint envelope + offline self-test".
- Files: `src/polaris_graph/run_config.py`,
  `config/settings/run_config_knobs.yaml` (38 knobs = single source of knob
  truth), `src/polaris_graph/checkpoint_envelope.py`,
  `scripts/foundation_selftest.py`, `tests/polaris_graph/test_foundation_core.py`.

Two offline proofs, both re-run at lock time (pure logic — no network, no GPU,
no LLM):

- **`scripts/foundation_selftest.py` — ALL PASS.** All five acceptance
  conditions returned `pass: true`; `all_pass: true`; registry knob count = 38.
  Exit code 0.
- **`tests/polaris_graph/test_foundation_core.py` — 14 passed in 3.76s.** Every
  guard test green.

The self-test is deterministic and lives inside the committed build, so this is
the passing iter, not a one-off. The five conditions below quote the self-test's
own machine-written evidence strings verbatim.

---

## 2. The five conditions — quoted evidence

### (a) PRECEDENCE — PANEL > PROMPT > ENV > CODE-DEFAULT

The whole point of the control surface: when the same knob is set at more than
one level, the higher level wins, in this fixed order. The self-test sets
`query_count` at all four levels at once and reads the ladder back.

> `query_count: panel=99 beats prompt=60 (span='run 60 quer') beats env(45 via`
> `PG_QGEN_FS_RESEARCHER_MAX_QUERIES) beats code_default=35; ladder=[('panel', 99,`
> `'panel'), ('prompt', 60, 'prompt'), ('env', 45, 'env'), ('default', 35, 'default')]`

Read the ladder plainly: with panel, prompt, env, and code-default all set for
`query_count`, the panel value 99 is what resolves. Strip the panel — the prompt
value 60 wins (and it carries the verbatim prompt span `'run 60 quer'`, so it is
a real parse, not an invented number). Strip the prompt — the env value 45 wins,
read from `PG_QGEN_FS_RESEARCHER_MAX_QUERIES`. Strip the env — the code default
35 wins. That is the precedence chain, proven end to end.

The resolver source constants that name each rung
(`src/polaris_graph/run_config.py`): `SOURCE_PANEL = "panel"`,
`SOURCE_PROMPT = "prompt"`, `SOURCE_ENV = "env"`, `SOURCE_DEFAULT = "default"`
(plus `SOURCE_ADJUST = "adjust"` for the downstream-resume rung in condition e).

### (b) ZERO-HARDCODE — every knob resolves to a declared source

No knob is a baked literal buried mid-pipeline. Every one of the 38 registered
knobs resolves through the resolver to a declared source. With an empty config
and clean env, every knob returns its code default — so an empty RunConfig is
byte-identical to today's behaviour. And every env-backed knob flips its source
to `env` the moment its `PG_` var is set, which proves the resolver actually
reads the env layer instead of returning a literal.

> `38 registered knobs: all resolve to a declared source`
> `(panel|prompt|env|default); empty-config resolves ALL 38 to`
> `source=default==code_default (byte-identical); 14/14 env-backed knobs FLIP to`
> `source=env when their PG_ var is set (layer read, not a literal). Zero`
> `mid-pipeline hardcodes.`

This is the LAW VI / §1.7 guarantee: zero raw env reads for registered knobs,
zero mid-pipeline hardcodes.

### (c) KNOB COVERAGE — every operator-named knob, on both surfaces

Every knob the operator named must exist AND be settable from BOTH user
surfaces: the deterministic prompt parse and the control-panel override. The
self-test proves all 14 operator-named knobs on both surfaces at once.

> `14 operator-named knobs, each present + prompt-settable + panel-settable:`
> `query_count->query_count: present=True prompt=True panel=True |`
> `searches_per_query->searches_per_query: present=True prompt=True panel=True |`
> `date_range(from)->date_from: present=True prompt=True panel=True |`
> `date_range(to)->date_to: present=True prompt=True panel=True |`
> `recency->recency: present=True prompt=True panel=True |`
> `source_type->source_types: present=True prompt=True panel=True |`
> `geography->geography: present=True prompt=True panel=True |`
> `language->language: present=True prompt=True panel=True |`
> `authors->authors: present=True prompt=True panel=True |`
> `scope->scope_focus: present=True prompt=True panel=True |`
> `tone->tone: present=True prompt=True panel=True |`
> `structure->structure: present=True prompt=True panel=True |`
> `depth->depth: present=True prompt=True panel=True |`
> `references->reference_style: present=True prompt=True panel=True`

Every row reads `present=True prompt=True panel=True`. No gaps.

### (d) CHECKPOINT ROUND-TRIP — cp0..cp6 write, read back, chain validates, verdict refused

Each of the seven section-boundary checkpoints must write to disk and read back
byte-for-byte identical, the payload data must come back identical, the whole
chain must validate as one hash-chain, and any attempt to smuggle a verdict into
a data-only checkpoint must be refused.

The seven stages (`CHECKPOINT_STAGES` in `checkpoint_envelope.py`):
cp0 s0_intake, cp1 s1_fetch, cp2 s2_select, cp3 s3_consolidate, cp4 s4_outline,
cp5 s5_compose, cp6 s6_verify. (S7 adjudicate+render is deliberately not a
resumable-past point — the D8 verdict is never checkpoint-replayed.)

> `cp0..cp6 all byte-identical round-trip + payload-identical`
> `[cp0:byte=True,data=True; cp1:byte=True,data=True; cp2:byte=True,data=True;`
> `cp3:byte=True,data=True; cp4:byte=True,data=True; cp5:byte=True,data=True;`
> `cp6:byte=True,data=True]; hash-chain validates end-to-end (['cp0', 'cp1',`
> `'cp2', 'cp3', 'cp4', 'cp5', 'cp6']); verdict-smuggling payload REFUSED=True`

Read plainly: all seven checkpoints round-trip byte-identical and
payload-identical, the hash-chain validates the full cp0..cp6 line, and a
payload carrying a forbidden verdict key (`is_verified`) is refused at save time.
The forbidden-verdict-key guard runs recursively at every nesting depth on BOTH
save and load — a resume re-runs every faithfulness gate from the reloaded data;
it can never replay a stored decision (§-1.3 data-only, LAW II fail-loud).

### (e) RESUME + ADJUSTMENT — resume from cp3, adjust downstream, upstream untouched

The resume contract: load checkpoint N, apply a downstream-only RunConfig
adjustment, re-run N+1..end. A valid downstream adjustment must take effect. An
out-of-scope adjustment (one that would change an upstream stage that already
ran) must be fail-loud rejected. The upstream checkpoints must be byte-untouched.
Superseded downstream checkpoints are archived, never deleted.

> `resume entry=cp3 (re-runs ('cp4', 'cp5', 'cp6')); downstream tone resolves to`
> `'executive_brief' (source=adjust) => change takes effect downstream; breadth`
> `adjustment at cp3 REFUSED=True; cp0-cp3 sha256 UNTOUCHED=True; cp4-cp6`
> `superseded (not deleted, archived at 2026-07-10T101348Z, index-recorded=True);`
> `chain still validates up to cp3=True`

Read plainly: resume at cp3 re-runs only cp4, cp5, cp6. A `tone` change to
`executive_brief` — a legal downstream knob at cp3 — resolves with
`source=adjust`, so the change takes effect. A `query_count` breadth change at
cp3 is refused, because breadth belongs to an upstream stage that already ran
(its earliest-resume-checkpoint is cp0, and cp3 is past it). The cp0..cp3 file
sha256s are unchanged by the resume. cp4..cp6 are moved under a superseded
archive and recorded in the index, not deleted (traceability). The chain still
validates up to cp3.

This is the validity matrix at work: each knob carries an
`earliest_resume_checkpoint`, and an adjustment is only accepted at or before
that point. Downstream-only, fail-loud on out-of-scope, supersede-never-delete.

---

## 3. What "locked" means here

Locked means: the control surface and the checkpoint envelope are the settled
foundation the section builds read from. The precedence chain, the 38-knob
registry, the cp0..cp6 envelope, and the resume+adjust contract are fixed. Any
section-level work adjusts knobs and reads/writes checkpoints THROUGH this
foundation — it does not re-invent the door.

Not locked by this record: fetch, select, consolidate, compose, verify, render.
Those are the later sections. This PR wired none of them onto the envelope yet —
it is additive foundation only, and no existing writer was migrated.

Faithfulness engine: untouched. No claim gate was relaxed, moved, or replayed.
The data-only checkpoint guard exists precisely so a resume can never replay a
stored verdict; it always re-runs the real gate from reloaded data.

---

## 4. How to re-prove it (offline, no spend)

```
python scripts/foundation_selftest.py --out summary.json
python -m pytest tests/polaris_graph/test_foundation_core.py -q
```

Both are pure logic — no network, no GPU, no LLM. The self-test writes
`summary.json` with each of the five conditions as a boolean plus its evidence
string, and exits 0 only if all five pass. The guard suite is 14 tests.
