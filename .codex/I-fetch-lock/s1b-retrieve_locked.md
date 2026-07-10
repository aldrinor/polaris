# SECTION 1.b = RETRIEVE (breadth + scope) — LOCKED

Branch: `bot/retrieve-core`. Date locked: 2026-07-10 (I-fetch-lock).

This is the second locked piece of Section 1. The fetch section (already locked
in `fetch_section_locked.md`) is the part that actually pulls source content off
the web. This piece, S1.b RETRIEVE, is the part BEFORE that: it decides HOW MANY
sub-queries to issue and HOW WIDE to search (the breadth resolver), and it carries
the operator's SCOPE — date window, geography, language, source type, named
authors — down into the query generator and into each search backend's request
parameters. Its job is done when the constructed query objects and the backend
request params correctly reflect RunConfig + scope. Everything after it (the live
fetch itself, tier weighting, off-topic screening, dedup, composition,
faithfulness) is a later section and is NOT locked by this record.

The faithfulness engine is untouched. Every change here is query breadth sizing or
scope-to-backend plumbing. It never relaxes a claim gate.

---

## 1. The passing iter — what we locked

The retrieve piece is locked at the S1.b build:

- **Commit `4990d616`** — "S1.b RETRIEVE: breadth resolver + scope-to-qgen +
  scope-to-backends (Design 7 D1-D3, master R11)".
- Files: `src/polaris_graph/retrieval/breadth_resolver.py` (the resolver),
  `config/settings/breadth_classes.yaml` (the sizing table, single source of
  breadth numbers — LAW VI, no magic numbers in code),
  `src/polaris_graph/retrieval/scope_directives.py` (the SCOPE DIRECTIVES prompt
  block), `src/polaris_graph/retrieval/scope_search_lanes.py` (the Serper / S2 /
  OpenAlex scope-param builders), plus the seam edits in
  `fs_researcher_query_gen.py`, `domain_backends.py`, `expert_facet_planner.py`,
  `live_retriever.py`, and the four RunConfig / scope FIXTURES under
  `tests/fixtures/retrieve/`.

The offline proof, re-run at lock time (pure logic — no network, no GPU, no LLM,
no live fetch):

- **`scripts/retrieve_selftest.py` — ALL PASS.** All five S1.b acceptance
  conditions returned `pass: true`; `all_pass: true`. Exit code 0.

The self-test drives the breadth resolver and the scope seams from RunConfig +
scope fixtures and asserts the CONSTRUCTED query objects and backend request
params. It uses a stubbed LLM, so it proves the SEAMS and the SIZING LOGIC — not
live retrieval yield. It is deterministic and committed inside this build, so this
is the passing iter, not a one-off. The five conditions below quote the
self-test's own machine-written evidence strings verbatim.

---

## 2. The five conditions — quoted evidence

### (a) BREADTH RESOLVER — sizes from RunConfig, a 35+ ask is HONORED

The core fix. The legacy code hardcoded 35 sub-queries. The resolver now sizes the
run — `query_budget`, `serper_k`, `s2_k`, `serper_total`, `fetch_cap` — from
RunConfig. An explicit operator ask of 60 must resolve to 60, never be capped back
to 35. A parsed breadth CLASS (WIDE / STANDARD / NARROW) with no explicit number
sizes every knob from that class row.

> `explicit RunConfig query_budget=60 -> resolved 60 (source=runconfig, >35`
> `honored=True); serper_k/s2_k/fetch_cap=12/12/300 from STANDARD class. WIDE`
> `class -> query_budget=80 serper_k=20 s2_k=20 serper_total=100 fetch_cap=740`
> `(source=runconfig_class).`

Read plainly: an explicit ask of 60 resolves to 60 (`source=runconfig`), and
`>35 honored=True` proves it was not clamped to the old hardcode. The per-query
counts it did not set (`serper_k`/`s2_k`/`fetch_cap` = 12/12/300) fill in from the
STANDARD class row. A WIDE directive with no numbers sizes every knob from the
WIDE row (`source=runconfig_class`): query_budget 80, serper_k/s2_k 20, serper
total 100, fetch cap 740.

Important framing (`config/settings/breadth_classes.yaml`, §-1.3): these class
rows are **compute-safety sizing** and generous ceilings that protect the box and
the wallet — they are NOT a breadth target the loop pads to. The issued query
count still EMERGES from facets, dedup, wall-clock, and checklist saturation. The
resolver HONORS the operator's ask and CLAMPS loudly (disclosed in the breadth
rationale) only at the absolute `abs_max` ceilings; it never silently forces a
number up or down. STANDARD deliberately equals today's 35 so a resolver-ON run
with no user ask drifts minimally from current behaviour.

### (b) SCOPE => SCOPE DIRECTIVES woven into the qgen prompts

When the operator states a scope, a SCOPE DIRECTIVES block must be woven into the
generated query-gen prompts so every constructed sub-query is constrained to it.
The block must reach BOTH the table-of-contents deconstruction prompt AND at least
one per-todo query-derivation prompt, and it must carry the actual parsed scope
terms (the date window and language), not just a header.

> `4/5 qgen prompts carry 'SCOPE DIRECTIVES (constr...'; TOC_has_block=True`
> `per_todo_has_block=True carries_window+lang=True; issued 1 queries.`

Read plainly: with `PG_SCOPE_TO_QGEN=1` and the rich scope fixture (window
2019..June-2023, German, EU+US, peer-reviewed, named author), 4 of 5 constructed
prompts carry the `SCOPE DIRECTIVES (constrain every generated query to ALL of
these):` header; it reaches the TOC prompt and the per-todo prompt; and
`carries_window+lang=True` confirms the block holds the real parsed terms
(`2023-06` + `de`). "issued 1 queries" is the stubbed-LLM offline count — this
test proves the scope block reaches the query-construction seam, not a live query
yield.

### (c) SCOPE => Serper request params carry date / geo / language

The web-search backend (Serper) request must carry the scope as its native
parameters: a date range as `tbs`, geography as `gl`, language as `hl`.

> `Serper scoped params = {"gl": "eu", "hl": "de", "tbs":`
> `"cdr:1,cd_min:01/01/2019,cd_max:06/30/2023"}`

Read plainly: the 2019-01-01..2023-06-30 window becomes Google's custom-date-range
form `cdr:1,cd_min:01/01/2019,cd_max:06/30/2023`; EU geography becomes `gl=eu`;
German becomes `hl=de`. The scope reaches the search backend as real request
params, not a discarded annotation.

### (d) SCOPE => S2 (year / publicationTypes) + OpenAlex (language / author) carry scope

The scholarly backends must carry the scope too, each in its own native form:
Semantic Scholar takes a `year` range and a `publicationTypes` filter; OpenAlex
takes `language` and `authors`.

> `S2 scoped params = {"publicationTypes": "JournalArticle", "year":`
> `"2019-2023"}; OpenAlex scoped params = {"authors": ["Jane Doe"], "language":`
> `"de"}`

Read plainly: the window becomes S2 `year=2019-2023`, the peer-reviewed-journal
preference becomes `publicationTypes=JournalArticle`, the German constraint
becomes OpenAlex `language=de`, and the named author becomes
`authors=["Jane Doe"]`. Every stated scope dimension lands on the right backend
knob.

### (e) FS-RESEARCHER METHOD INTACT + FAIL-OPEN when no scope is stated

Two guarantees in one. First, the FS-Researcher query method is untouched: with NO
scope threaded, the loop still deconstructs the topic (TOC) => derives a per-todo
query => calls the injected retriever, byte-identical to today. Second, fail-open:
when the scope is EMPTY but EVERY scope flag is ON, zero scoped params are built
and zero directive block is emitted — an absent scope never fabricates a filter.

> `FS method: issued 1 queries, 1 retrieve calls, TOC ran, no scope block leaked`
> `(intact=True). Fail-open (empty scope, all flags ON): serper={} s2={}`
> `openalex={} directive_block_appended=False (zero_filters=True).`

Read plainly: with no scope, the method fired end to end (TOC ran, one query
issued, one retrieve call) and no SCOPE DIRECTIVES block leaked into the prompts
(`intact=True`). Then, with an empty scope and all four scope flags forced ON, the
Serper / S2 / OpenAlex builders each returned `{}` and no directive block was
appended (`zero_filters=True`). This is the §-1.3 fail-open rule: any uncertainty
or absence => no constraint invented. (The "1 queries / 1 retrieve calls" figures
are the stubbed-LLM offline counts; the point proven is the method path and the
fail-open behaviour, not a live yield.)

---

## 3. What "locked" means here

Locked means: the breadth resolver and the scope-to-backend plumbing are the
settled way S1.b sizes a run and carries scope. The resolver reads breadth from
RunConfig and the `breadth_classes.yaml` sizing table (honor the ask, clamp loud
only at `abs_max`, never pad to a target). Scope, when stated, reaches the query
prompts as a SCOPE DIRECTIVES block and reaches Serper / S2 / OpenAlex as their
native request params. When scope is absent, every lane fails open to no
constraint. Every seam is behind an env flag (`PG_BREADTH_RESOLVER`,
`PG_SCOPE_TO_QGEN`, `PG_SERPER_SCOPE_FILTER`, `PG_S2_SCOPE_FILTER`,
`PG_OPENALEX_SCOPE_FILTER`), each per-knob env-overridable.

Not locked by this record: the live fetch itself (that is `fetch_section_locked.md`
on `bot/retrieve-core`), tier weighting, off-topic screening, dedup, composition,
verify, render. Those are later sections. This build wired the sizing and scope
seams only; it did not touch any downstream stage.

Faithfulness engine: untouched. No claim gate was relaxed, moved, or replayed.
Widening breadth or carrying scope changes only WHAT is searched and HOW MANY
sub-queries are issued — every recovered source still flows through the same
extractor and the same strict_verify / 4-role gates as before.

---

## 4. How to re-prove it (offline, no spend)

```
python scripts/retrieve_selftest.py --out outputs/retrieve_selftest/summary.json
```

Pure logic — no network, no GPU, no LLM, no live fetch. The self-test drives the
resolver and the scope seams from the committed RunConfig / scope fixtures under
`tests/fixtures/retrieve/`, writes `summary.json` with each of the five conditions
as a boolean plus its evidence string, and exits 0 only if all five pass.
