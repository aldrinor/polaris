# END-RESULT AUDIT — the finished report, claim by claim

Written 2026-07-10 12:45 UTC. Plain English. Operator is blind.

## The one-line answer

There is no finished report to audit yet.

The pipeline built the plan for a report, but it never wrote the report.
It got as far as the outline and stopped. So I cannot count claims,
because no claims were ever written. The honest verdict on "is the
finished report clinically faithful AND usable?" is: **NO — because the
finished report does not exist.** A report that was never composed cannot
be usable.

This is not me refusing to work. I checked the machine directly. I am
telling you exactly where the build actually got to, so you do not wake
up to a fake number.

## How far the pipeline actually got (checked live on box2)

I logged into box2 (ssh6.vast.ai:38794) and read the real output folders.
Here is what exists and what does not.

Exists — the early stages ran and left real checkpoints:
- **cp2 — corpus (select and weigh):** ran. It kept 5,930 evidence rows
  for the question about the impact of generative AI on freelancers'
  employment. (Note: this is a DeepResearch-Bench question, not a
  clinical one — see the note at the bottom.)
- **cp3 — baskets (consolidate):** ran. It grouped the evidence into about
  581 baskets (69 multi-source clusters plus 512 single-source ones),
  686 rows into the outline pool.
- **cp4 — outline:** ran. It produced a 5-section outline:
  1. Positive views on generative AI's impact on employment
  2. Negative views on generative AI's impact on employment
  3. Specific challenges of generative AI in the labor market
  4. Future opportunities from generative AI for employment
  5. Industry-specific application cases and risk summary

Does NOT exist — the stages that actually make a report:
- **cp5 — compose:** never ran. No prose was written.
- **cp6 — verify:** never ran. Nothing was fact-checked.
- **render:** never ran. There is no report.md, no HTML, no PDF from this
  build.
- **integration:** the branch `bot/pipeline-integration` does not exist on
  box2 or locally. The sections were never merged into one pipeline.
- **end-to-end smoke:** never ran.

Last write on box2 was the outline stage (s4) at 12:40 UTC, one minute
before I checked. No compose, verify, or render process is running. The
overnight driver reached the outline and has not moved past it.

## The claim-by-claim audit table

| Item | Result |
|---|---|
| Total claims in the report | 0 — no report was composed |
| VERIFIED | N/A — nothing to verify |
| PARTIAL | N/A |
| UNSUPPORTED | N/A |
| FABRICATED | N/A |
| Chrome / bot-page / error-page leaks in the report | Cannot measure — no report was rendered |
| Quote-dump hits (raw copied spans instead of written prose) | Cannot measure — no prose exists |
| Usable? | **NO** — there is no end-result document |
| Clinically faithful? | **NO** — a report that does not exist cannot be faithful |

I did not fill these boxes with invented numbers. Inventing them would be
the exact "fake working" the project rules forbid, and inventing a clean
claim audit for a clinical tool can hurt patients. The truthful entry is
"there is no report."

## The defects — honest list

1. **The pipeline is not finished.** It stopped at the outline (cp4). The
   three stages that turn an outline into a report — compose, verify,
   render — never ran. This is the biggest defect: there is no product.

2. **No integration branch.** `bot/pipeline-integration` does not exist.
   The separate section branches (foundation, intake, retrieve,
   select+weigh, consolidate, outline, and the downstream stubs) were
   never merged into one runnable pipeline. So even the parts that work
   cannot run end to end today.

3. **The outline stage flagged itself "degraded."** The cp4 digest carries
   `degraded: true`. On this project that usually means the step was
   starved of compute and had to fall back, not that it hung. It still
   produced 5 sections, but the flag means the outline was built under
   stress and should be re-run cleanly before it is trusted.

4. **A disputed 41% off-topic signal on the kept corpus.** A separate
   check of the 5,930 kept rows flagged 2,458 of them (about 41%) as
   possibly off-topic. Important: the overnight notes say this 41% came
   from a BROKEN audit method (it judged each line alone, with no
   context) and is not a confirmed gate defect — the real off-topic gate
   is judged correct. So treat this as "flagged, contested, needs a
   with-context re-check," not as proven corpus pollution. But it is still
   an open item, not a clean pass.

5. **A small basket residual.** About 3% of baskets (17 of 581) were
   flagged by a sound structural check for possible over-merge (two
   different claims fused, or a dropped member). Small, real, deferred to
   the optimization pass.

6. **The corpus question is not clinical.** This run was built on the
   generative-AI-and-jobs benchmark question. So even when the report is
   finished, this particular run will not be a clinical document. The
   "clinically faithful" test still applies as a standard, but there is no
   clinical content in this specific run to test.

## Bottom line

The build is real and the early stages left real checkpoints — corpus,
baskets, outline all exist and look coherent. But the pipeline stopped
before it wrote anything. There is no finished report, so it is not
usable and not faithful, because it is not there yet.

## What to do next (when you are awake)

1. Let the driver finish, or restart it, so it runs compose → verify →
   render and actually produces a report.
2. Re-run the outline cleanly so the `degraded` flag clears.
3. Then re-run THIS audit against the real rendered report — count the
   claims, mark VERIFIED / PARTIAL / UNSUPPORTED / FABRICATED, check for
   chrome and quote-dumps, and answer usable yes/no with real evidence.
4. Do not fire the paid competitor benchmark until step 3 says the report
   is usable.
