# SECTION 2 = SELECT+WEIGH — LOCKED

Branch: `bot/sec-s2-select`. Commit `d3864eaf` (S2 build + box-2 replay harness).
Date locked: 2026-07-10 (I-fetch-lock).

This is the second locked section of the POLARIS pipeline. Fetch (Section 1) hands
up the fetched-content set. SELECT+WEIGH reads that set and decides, line by line,
which lines to keep and which to drop, and it writes the S2 checkpoint
(`cp2_corpus_snapshot`). Everything after it (consolidate, outline, compose, verify,
render) is a later section and is NOT locked by this record.

The axis split is the whole point of this section:

- **Credibility is a WEIGHT, never a drop.** A credible, on-topic, in-scope source
  is never dropped. A low tier just carries a low weight into composition.
- **Three drop triggers only, decided per LINE:** (1) OFF-TOPIC, (2) OUT-OF-USER-SCOPE
  (the user's own explicit scope from RunConfig — dates / recency / type / geo / lang /
  author), (3) JUNK (chrome / boilerplate / bot-wall shells).
- Fail-open on any uncertainty. Every dropped line is disclosed, quoted verbatim.

The faithfulness engine is untouched. This section drops off-topic / out-of-scope /
junk LINES before composition; it never relaxes a claim gate. The kill-switch
`PG_LINE_SCREEN=0` makes it byte-identical to today (no line is ever touched).

---

## 1. The passing iter — what we locked

Locked at the first hamster iteration, `s2_hamster_i1`, run on the REAL box-2 drb_72
corpus with the REAL production judge (mirror role, temperature 0.0, source fan-out
32-wide, `stub=false`). Both legs of the section were proven on the same corpus in the
same iteration, and both completed clean with zero crash-resume replays.

- **Harness:** `scripts/s2_select_replay.py` (standalone CLI, LAW VII).
- **Line-screen reader:** `src/polaris_graph/retrieval/line_screen.py`.
- **Box-2 host:** `ssh6.vast.ai:38794`, repo at `/workspace/POLARIS`, git HEAD `d3864eaf`.
- **Box-2 input snapshot:** `outputs/paid_drb72_deep/workforce/drb_72_ai_labor/corpus_snapshot.json`
  (999 evidence rows, 6623 body lines — the paid deep drb_72 corpus with the known
  welded-chrome leaks, off-topic lines, and rich mixed sources).
- **Box-2 output dir (inert scope / main run):** `/workspace/POLARIS/outputs/s2_hamster_i1/`
  — holds `cp2_corpus_snapshot.json`, `disclosure.txt` (every dropped line quoted),
  `summary.json` (the five §6.4 lock-bar metrics), `line_screen_verdicts.jsonl` (the
  crash-resilient checkpoint).
- **Box-2 output dir (armed user scope / scope run):** `/workspace/POLARIS/outputs/s2_hamster_i1_scope/`
  — same four artifacts, run with the user's explicit "before June 2023" date scope
  armed.

Run totals, read straight from the two `summary.json` files:

| | main run (scope INERT) | scope run (scope ARMED "before June 2023") |
|---|---|---|
| sources in | 999 | 999 |
| sources kept | 996 | 965 |
| body lines total | 6623 | 6623 |
| body lines kept | 5930 | 5910 |
| lines dropped | 693 | 713 |
| — off_topic | 234 | 297 |
| — out_of_scope | 0 | 152 |
| — junk | 459 | 264 |
| whole-source drops | 3 (all junk shells) | 34 (31 date-window + 3 junk shells) |
| disagreement-restored (fail-open) | 535 | 600 |
| crash-resume replays | 0 | 0 |

Both runs report `all_lines_quoted: true`. The disclosure files quote every one of the
693 / 713 dropped lines verbatim. The condition evidence below quotes real lines from
those two runs.

---

## 2. The five conditions — quoted dropped-line and kept-line evidence

The five lock-bar conditions are §6.4 of `.codex/I-arch-plan/01_offtopic_subquery.md`
and are the five `cond_*` blocks the harness writes into `summary.json`.

### (a) Off-topic / out-of-scope / junk LINES are dropped, each line QUOTED

`summary.json → cond_a_lines_dropped_quoted`: 693 dropped lines in the main run
(`off_topic:234, out_of_scope:0, junk:459`), 713 in the scope run
(`off_topic:297, out_of_scope:152, junk:264`), `all_lines_quoted: true` in both.

DROPPED (junk — a JEP article page whose chart chrome leaked in), from
`s2_hamster_i1/disclosure.txt`:

> `--- autor_why_still_jobs — Why Are There Still So Many Jobs? ... ---`
> `  [junk] L20: −0.5 0.0 0.5 1.0 1.5 2.0 2.5 3.0`
> `  [junk] L4: > †To access the Data Appendix and disclosure statement, visit http://dx.doi.org/10.1257/jep.29.3.3 doi=10.1257/jep.29.3.3`

DROPPED (junk — Oxford ORA repository export/citation chrome welded onto the Frey &
Osborne record):

> `  [junk] L0: *  * [BibTeX](https://ora.ox.ac.uk/objects/uuid:4ed9f1bd-27e9-4e30-997e-5fc8405b0491/export_record.bibtex)`
> `  [junk] L6: * [Email](https://ora.ox.ac.uk/objects/uuid:4ed9f1bd-27e9-4e30-997e-5fc8405b0491#emailForm)## Email this record`

DROPPED (off-topic — a bibliography/reference line about ChatGPT-in-academic-writing,
off the labor-market question):

> `--- ev_1265 — Systematic review of trends in the application of artificial intelligence ... ---`
> `  [off_topic] L1:  both opportunities and challenges in terms of ethics, quality and intellectual autonomy. References Alberth. (2023). The use of ChatGPT in academic writing: a blessing or a curse in disguise? Teflin Journal, 34(2), 337-352. Scopus.`

KEPT (the real substance survives on the same sources): from `s2_hamster_i1/cp2_corpus_snapshot.json`,
the Autor T1 body keeps its argument line —

> `KEPT> # There have been periodic warnings in the last two centuries that automation and new technology were going to wipe out large numbers of middle class jobs. The best-known early example is the Luddite ...`

### (b) A credible on-topic in-scope source is NEVER whole-dropped

`summary.json → cond_b_no_credible_whole_drop`: the main run whole-drops only 3
sources, and all 3 are junk shells (two-key concurrence), while 535 sources were
marquee/disagreement-protected.

The 3 whole-drops, from `s2_hamster_i1/disclosure.txt`, are not credible sources —
they are a bot-wall and two social-forum shells with no usable content:

> `=== WHOLE-SOURCE DROPS (two-key; marquee-exempt) ===`
> `[junk:concur:content_integrity_junk/shell] ev_688 — Let's confirm you are human (https://espace.library.uq.edu.au/view/UQ:2c7588c/UQ2c7588c_OA.pdf)`
> `[junk:concur:content_integrity_junk/shell] ev_621 — Job Search: Do HRs actually read all the resumes that they get for a particular position? (https://www.quora.com/...)`
> `[junk:concur:content_integrity_junk/shell] ev_481 — Is data entry clerk considered of having information management experience? (https://www.quora.com/...)`

The credible institutions the older I-deepfix-003 forensics saw mass-deleted all SURVIVE
here, with their content lines kept — from `s2_hamster_i1/cp2_corpus_snapshot.json`:

> `KEPT ev_020 tier=T3 :: X X Generative AI and jobs: A global analysis of potential effects on job quantity and quality Authors / Paweł Gmyrek, Janine Berg, David Be...`  (ILO)
> `KEPT ev_077 tier=T4 :: NBER WORKING PAPER SERIES GENERATIVE AI AT WORK Erik Brynjolfsson Danielle Li Lindsey R. Raymond Working Paper 31161 http://www.nber.org/pap...`  (NBER)

Credibility is a weight, not a drop: those two survive on their merits. The only way a
credible source leaves the pool is the user's own explicit scope filter — condition (d),
a different axis.

### (c) A rich MIXED source keeps its relevant lines and drops only the bad ones

`summary.json → cond_c_mixed_partial_keep`: 143 partial-keep sources in the main run,
127 in the scope run — sources where some lines drop and some stay, never all-or-nothing.

`autor_why_still_jobs` (T1): 25 lines, 22 kept, 3 dropped. The 3 dropped are chart /
data-appendix chrome (quoted in (a): L4, L20, and L21 chart labels). The 22 kept are the
real paper — from `cp2_corpus_snapshot.json`:

> `KEPT> # Why Are There Still So Many Jobs? The History and Future of Workplace Automation`
> `KEPT> David H. Autor is Professor of Economics, Massachusetts Institute of Technology ...`

`frey_osborne_computerisation` (T1): 18 lines, 1 kept, 17 dropped. The 17 dropped are
all Oxford ORA repository chrome — BibTeX / EndNote / RefWorks export links, "Email this
record", citation-style boilerplate, copyright notices (quoted in (a)). The single kept
line is the actual finding — from `cp2_corpus_snapshot.json`:

> `KEPT> Abstract: We examine how susceptible jobs are to computerisation. To assess this, we begin by implementing a novel methodology to estimate the probability of computerisation for 702 detailed occupatio...`

That is line-level select working exactly as designed: the source is not thrown away,
its one real content line is kept and its 17 chrome lines are dropped.

### (d) The user-scope filter drops out-of-scope and KEEPS in-scope; empty scope ⇒ ZERO

The user's explicit scope is a HARD filter, distinct from credibility, and it is inert
unless the user actually sets a scope. Proven by the pair of runs on the same corpus.

Empty scope (main run) — `summary.json → cond_d_scope`:

> `"scope_armed": false, "scope_active": false, "n_out_of_scope_line_drops": 0,`
> `"n_source_scope_whole_drops": 0, "note": "INERT — zero out_of_scope drops (activation rule)"`

Armed "before June 2023" scope (scope run) — `summary.json → cond_d_scope`:

> `"scope_armed": true, "scope_active": true, "n_out_of_scope_line_drops": 152,`
> `"n_source_scope_whole_drops": 31, "note": "ARMED — out_of_scope leg active"`

DROPPED out_of_scope (a 2025 paper, outside the user's pre-June-2023 window), from
`s2_hamster_i1_scope/disclosure.txt`:

> `  [out_of_scope] L3: Future of Work with AI Agents: Auditing Automation and Augmentation Potential across the U.S. Workforce - 2025 Computer Science`

DROPPED out_of_scope whole-source (post-window institutional reports — including credible
ones — leave the pool only because the USER asked for pre-June-2023), from
`s2_hamster_i1_scope/disclosure.txt`:

> `[out_of_scope:date_window] ev_150 — [PDF] The impact of Artificial Intelligence on productivity, distribution and ... (https://www.oecd.org/.../2024/04/the-impact)`
> `[out_of_scope:date_window] ev_019 — Toward understanding the impact of artificial intelligence on labor (https://mitsloan.mit.edu/...)`

KEPT in-scope: the pre-June-2023 sources survive in BOTH runs — Autor (2015), Frey &
Osborne (2016), Acemoglu & Restrepo (2019) are all kept with their content lines (see (c)).
Same corpus, empty scope = zero out_of_scope drops; that is the activation-rule proof.

### (e) Fail-open on uncertainty

`summary.json → cond_e_fail_open`: 535 disagreement-restored in the main run, 600 in the
scope run, `n_replayed_on_resume: 0`. A single uncertain "drop everything" verdict that
the metadata key does not concur on restores ALL of that source's lines (V5 two-key), so
the section never silently whole-drops on one shaky call.

RESTORED (a credible T1 paper the line-judge tried to drop; two-key did not concur, so
all lines were kept) — from `cp2_corpus_snapshot.json`:

> `RESTORED acemoglu_restrepo_robots_jobs tier=T1 whole_dropped=False :: We study the effects of industrial robots on US labor markets. We show theoretically that robots may reduce employment and wages ...`

Fail-open even errs toward KEEP on bot-wall pages rather than silently deleting them —
they are restored and DISCLOSED, not dropped in the dark:

> `RESTORED ev_072 tier=T7 whole_dropped=False :: ## Security check required We've detected unusual activity from your network. To continue, complete the security check below. Ray ID: a17b96...`

`n_replayed_on_resume: 0` means neither run crashed, so no replay was needed; the resume
path itself is the `line_screen_verdicts.jsonl` checkpoint — a kill mid-run replays
screened rows with no LLM calls and re-screens only the remainder. A checkpoint read/write
error proceeds as if absent, so a checkpoint bug can never invent or drop a verdict.

---

## 3. What "locked" means here

Locked means the line-level three-way select/drop reader is the settled S2 behaviour, and
its output boundary is `cp2_corpus_snapshot` — the screened corpus (kept lines only,
whole-drops removed, every kept row carrying a `line_screen` sidecar). Consolidate (S3)
and everything downstream read from that checkpoint.

The axis split is fixed: credibility is a weight and never a drop; off-topic,
out-of-user-scope, and junk are the only drops; every drop is decided per line, fails
open on uncertainty, and is disclosed verbatim. Whole-source drop stays two-key +
marquee-protected.

Not locked by this record: consolidate, outline, compose, verify, render — the later
sections. This branch wired none of them; S2 hands `cp2_corpus_snapshot` up and stops.

Faithfulness engine: untouched. No claim gate was relaxed, moved, or replayed. This
section removes off-topic / out-of-scope / junk lines BEFORE composition; the strict_verify
/ NLI / 4-role gates downstream are byte-for-byte the same. `PG_LINE_SCREEN=0` turns the
whole section off and is byte-identical to today.

---

## 4. How to re-prove it (on the box-2 real corpus)

```
# main run — inert scope (conditions a, b, c, e; and d empty-scope leg)
python scripts/s2_select_replay.py \
  --snapshot outputs/paid_drb72_deep/workforce/drb_72_ai_labor/corpus_snapshot.json \
  --parallel 32 --out outputs/s2_hamster_i1

# scope run — armed user scope (condition d armed leg)
python scripts/s2_select_replay.py \
  --snapshot outputs/paid_drb72_deep/workforce/drb_72_ai_labor/corpus_snapshot.json \
  --scope '{"date_end":"2023-06"}' --parallel 32 --out outputs/s2_hamster_i1_scope
```

Each run writes `summary.json` (the five `cond_*` metrics), `disclosure.txt` (every
dropped line quoted, §-1.3.1 fail-loud), `cp2_corpus_snapshot.json` (the screened corpus),
and `line_screen_verdicts.jsonl` (the crash-resilient checkpoint; add `--resume` to
continue after a kill). `--stub` runs the offline plumbing check with no key; the real
lock ran the real production judge (`stub=false`, temperature 0.0, 32-wide).
