# RETRIEVE (SECTION 1.b) — LIVE ADVERSARIAL STRESS: SIGNED OFF

Branch: `bot/retrieve-core`. Section code at commit `4990d616`
(breadth resolver + scope-to-qgen + scope-to-backends, Design 7 D1-D3).
Live stress battery at commit `010689ac` (`scripts/retrieve_stress.py`).
Live run executed: **2026-07-10 10:53:48 UTC**.

This record signs off the RETRIEVE section against the FULL live adversarial
stress. The battery hit the REAL backends — Serper, Semantic Scholar, and
OpenAlex — over the network. Every returned hit was read line by line, with no
sampling, per CLAUDE.md §-1.1. The faithfulness engine was not touched. Every
change under test is query-breadth sizing or scope plumbing only. Nothing here
relaxes a claim gate.

---

## 1. The result — zero breaks

**8 cases. 8 passed. 0 breaks. clean = true. Passing iter = 1.**

The machine verdict, printed verbatim by the runner:

```
=== RETRIEVE_STRESS_RESULT ===
{"iter": 1, "clean": true, "total_cases": 8, "passed": 8, "breaks": []}
=== END ===
[retrieve_stress] summary -> outputs\retrieve_stress_i1\summary.json  clean=True
```

Exit code 0. The runner exits 0 only when `breaks` is empty, so exit 0 IS the
zero-break proof. The full evidence lives under
`outputs/retrieve_stress_i1/<case_id>/capture.jsonl` + `verdict.json`, with the
overall `summary.json` at the top. Every hit quoted below is copied out of those
capture files.

Offline cross-reference: the pure-logic sibling `scripts/retrieve_selftest.py`
and its lock record `.codex/I-fetch-lock/s1b-retrieve_locked.md` already proved
the SAME seams with no network. This live battery proves the same contract
against the real web.

---

## 2. What the battery proves — the two halves of the Design-7 contract

**Half A — breadth sizes from the user's ask, and is never clamped to the old
hardcode of 35.** Three deterministic cases drive the real `resolve_breadth`.

**Half B — scope reaches the live backends, per lane, and never drops the base
lane.** Five live cases. For each, a SCOPED lane and an untouched BASE lane are
both fired. The scoped lane must come back fully inside the window. The base
lane must still return out-of-window hits — that surviving base hit IS the
no-drop proof (CLAUDE.md §-1.3). Assertions are per lane, never on the union.

---

## 3. Case-by-case, with the real live hits quoted

### Group A — breadth honors the ask (deterministic, real resolver)

| Case | Result | Evidence line |
|---|---|---|
| `breadth_explicit_45_uncapped` | PASS | `query_budget=45 source=runconfig class=WIDE` — an explicit 45-query ask is honored, source is the RunConfig, and 45 > 35 so it is NOT clamped to the legacy hardcode. |
| `breadth_wide_from_prompt_80` | PASS | `query_budget=80 source=class class=WIDE` — a WIDE prompt widens to the WIDE class row of 80. |
| `breadth_narrow_from_prompt_shrinks` | PASS | `query_budget=15 source=class class=NARROW` — a NARROW prompt shrinks to 15, below 35. The ask can shrink too; the budget is a ceiling, not a padded target. |

The 35 in the middle column is `LEGACY_HARDCODE_QUERY_BUDGET`, the pre-Design-7
fixed default the resolver must never snap back to. None of the three cases
landed on 35.

### Group B — scope reaches the live backends, no base drop

**Hardest case 1 — Semantic Scholar year window (the biggest live corpus in the
run). `s2_year_scope_live`.**

Query `GLP-1 receptor agonist cardiovascular outcomes`, window 2023-2025.

- Scoped param sent to live S2: `year=2023-2025`.
- Scoped lane returned **979 hits. 978 carried a known year and EVERY ONE was
  inside 2023-2025. Out-of-window = 0.** One row carried no year at all and was
  skipped, never counted as in-window — the check refuses to claim a verdict it
  cannot ground.
- Base lane returned **1000 hits, of which 401 predate 2023** (real years seen:
  2018, 2018, 2022). Those pre-2023 hits surviving in the base lane is the
  no-drop proof.

Real hits, copied verbatim from `s2_year_scope_live/capture.jsonl`:

```
SCOPED  {"year": 2025, "venue": "Value in Health",
         "title": "Capturing the Additional Cardiovascular Benefits of SGLT2 Inhibitors ..."}
BASE    {"year": 2018,
         "title": "The incretin hormone GIP is upregulated in patients with atherosclerosis ..."}
```

The scoped year range across all 978 known-year rows was min 2023, max 2025.
The 2018 paper is present in the base lane and absent from the scoped lane. That
is scope filtering, on live data, with the base source kept.

**Hardest case 2 — OpenAlex language window. `openalex_language_scope_live`.**

Query `COVID-19 vaccine effectiveness`, language `fr`.

- Scoped filter sent to live OpenAlex: `language:fr`.
- Scoped lane: **50 works, all 50 in French.**
- Base lane: **50 works, all 50 in English (non-fr = 50).**

Real hits, verbatim from `openalex_language_scope_live/capture.jsonl`:

```
SCOPED  {"language": "fr", "year": 2024, "title": "Vaccine patriotism and public health cultures ..."}
BASE    {"language": "en", "year": 2022,
         "title": "Covid-19 Vaccine Effectiveness against the Omicron (B.1.1.529) ..."}
```

The scoped lane is 100% `fr`; the base lane still returns `en` work. Language
scope reached the live backend and the base language was not dropped.

**Hardest case 3 — OpenAlex date window. `openalex_date_scope_live`.**

Query `GLP-1 receptor agonist cardiovascular outcomes`, window 2023-2025.

- Scoped filter: `from_publication_date:2023-01-01,to_publication_date:2025-12-31`.
- Scoped lane: **50 works, all 50 inside 2023-2025.**
- Base lane: **50 works, 45 predate 2023** (real years seen: 2019, 2021, 2020).

**Case 4 — OpenAlex author scope. `openalex_author_scope_live`.**

Query `cardiovascular outcomes`, author `Nissen`.

- Scoped filter: `raw_author_name.search:Nissen`.
- Scoped lane: **50 works, all 50 list a Nissen author.** Base lane: **50 works,
  47 with no Nissen author** — the base is not narrowed to only-Nissen.

Real hit, verbatim from `openalex_author_scope_live/capture.jsonl`:

```
SCOPED  {"nissen_author": ["Steven E. Nissen"], "year": 2016,
         "title": "Liraglutide and Cardiovascular Outcomes in Type 2 Diabetes ..."}
```

**Case 5 — Serper scope reaches the backend. `serper_scope_reaches_backend_live`.**

Query `diabetes treatment guidelines`, window 2023-2025, region `ca`, language `en`.

- Scoped params built by the real production builder and accepted live with no
  error: `tbs=cdr:1,cd_min:01/01/2023,cd_max:12/31/2025`, `gl=ca`, `hl=en`.
- Base lane returned 9 live hits (e.g. `Standards of Care in Diabetes | ADA
  Clinical Guidelines`). The scoped call was accepted, additive to the base.

Honesty note (kept deliberately): Serper organic results carry no reliable
per-hit date, region, or language. So this case proves ONLY that the scoped
params are well-formed and reach live Serper without error. It does NOT fake a
per-hit date verdict Serper cannot support. Where a scoped row happened to carry
a parseable date, the year was checked against the 2023 floor; none violated it.

---

## 4. Honest residual notes

- **OpenAlex ran without an API key.** `PG_OPENALEX_MAILTO` and
  `PG_OPENALEX_API_KEY` are not set in this environment, so OpenAlex was hit on
  its public pool. All four OpenAlex lanes still returned full 50-row pages and
  passed. Serper and Semantic Scholar used their real keys from `.env`.
- **One S2 scoped row had no year.** It was skipped, not counted as in-window.
  Skipping an ungroundable row is the correct behavior, not a break.
- **Serper exposes no per-hit date.** By design the Serper lane makes no per-hit
  date claim (see case 5). This is an honesty limit of the backend, not a gap in
  the test.

---

## 5. Sign-off

RETRIEVE (Section 1.b) passed the full live adversarial stress on
2026-07-10 with **zero breaks, 8 of 8 cases, iter 1, clean = true**. Breadth
honors the ask and is never clamped to 35. Scope reaches the live backends per
lane, with real 2023-2025 date filtering, real French-only language filtering,
and real author filtering all confirmed on live hits — and the base lane keeps
its out-of-window sources every time, so nothing is dropped. Signed off.
