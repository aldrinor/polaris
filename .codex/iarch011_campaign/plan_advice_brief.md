# ADVICE REQUEST — I-arch-011 22-bug fix campaign EXECUTION PLAN (NOT a diff gate; give engineering advice)

You are advising on the EXECUTION STRATEGY for fixing 22 bugs found in a forensic autopsy of the POLARIS
deep-research pipeline (clinical Parkinson's/DBS run that hung before render). Repo root = C:/POLARIS.

## MANDATE THAT APPLIES TO YOUR OWN ADVICE
Do NOT suggest anything that (1) DEGRADES FAITHFULNESS (relaxes strict_verify/NLI/4-role/span-grounding,
ships unverified-as-verified, weakens a fail-closed gate), (2) GRANDFATHERS/is OUTDATED (old model, pre-2024
approach superseded by 2025-2026 frontier), or (3) CHOKES THE NECK (adds a cap/floor/throttle/hard-filter/
thinner/bottleneck constraining throughput, breadth, or quality — the §-1.3 banned filter-and-cap anti-pattern).
The pipeline DNA is WEIGHT-AND-CONSOLIDATE, never FILTER-AND-CAP. Faithfulness is the only hard gate.

## THE 22 BUGS — 4 KEYSTONES (full detail: state/canary_forensic/deadbody/CONSOLIDATED_AUTOPSY.md)
1. **B19→B15 (hang):** distill_map (evidence_distiller.py:1270-1278,1484-1492) makes deepseek calls with NO
   per-call timeout; the credibility-pass sibling got PG_CREDIBILITY_PASS_WALL_S=600 (multi_section_generator.py:6692).
   One distill call ran 24.6min then a later one hung the asyncio loop forever (only the 10800s run-wall backstops).
   FIX: add a tight per-call wall-deadline to distill_map (mirror the sibling) + raise PG_DISTILL_MAX_PARALLEL
   (evidence_distiller.py:1657,1687 already has an asyncio.Semaphore — currently low). Parallel + per-call deadline.
2. **B17→B11/B22/B04/B20:** authority_score weighting silently no-opped (weight_basis="tier_prior" for all 528);
   tier classifier R1_stub_content_length demotes real journals (Lancet/Brain) to T7 "regardless of venue" because
   they fetched as stubs (regression of I-bug-775 #815). FIX: re-fetch degraded rows OR weight by venue-authority
   not fetch-length + restore authority_score primary.
3. **B18→B16:** weighted_enrichment.py:210 re-imposes a HARD selection_relevance<0.30 DROP (killed 729/746
   supports -> enrichment EMPTY) that evidence_selector.py:1944-1953 docstring FORBIDS (keep-all-sort-below-
   floor-last). Plus the floor uses a whole-question length denominator (evidence_selector.py:489-490) so a
   3-part long question demands ~22 exact-word matches/source. FIX: remove the hard drop + per-subquery
   relevance normalization. (THIS is a neck-choke bug — your advice must not re-add a floor.)
4. **B12→B14/B01:** bare json.loads on entailment_judge.py:695 + semantic_conflict_detector.py:779 can't parse
   garbled-200 (valid JSON + trailing text); novita+gmicloud 404 on response_format:json_object. FIX: tolerant
   first-{}-object parser + drop json_object -> 4 healthy hosts. (My prior rotation fix is committed; this completes it.)
Plus ~14 more (tier/credibility, contradiction empty-subject extractor, colliding ev_ids, clinical adequacy
false-pass + wrong-domain GLP-1 completeness checklist on a Parkinson's question, etc.).

## MY PROPOSED EXECUTION PLAN — critique it
- **Stage 1 (parallel, now):** (a) BUILD the ~10 mechanical/keystone fixes I know cold (B19 first — it's the only
  thing that lets a run COMPLETE+RENDER), via parallel Claude Codex Workflows, Codex gate, ITER CAP 3, serialize
  the hot shared files (run_gate_b.py, evidence_distiller.py, openrouter_client.py, the two judges,
  weighted_enrichment.py, evidence_selector.py, the tier/credibility files). (b) RESEARCH the ~9 quality-dependent
  bugs against 2025-2026 frontier (contradiction detection, authority scoring, relevance normalization, anti-bot
  fetch, clinical composition prompt+routing, stable LLM serving = first-party API vs self-host vs OpenRouter).
- **Stage 2:** build the research-validated Bucket-2 fixes (Codex cap 3, mandate).
- **Stage 3:** SERIOUS behavioral preflight — replay-harness on a banked corpus_snapshot, the effect must FIRE in
  the REAL rendered output (collapsed>0, enrichment appends, run COMPLETES to ## Abstract, render breadth wide),
  fail-loud, NOT "tests green / Codex approved". (§-1.4)
- **Stage 4:** VM launch the 5-Q sweep, §-1.1 line-by-line audit each report.md.

## QUESTIONS (answer each, schema below)
1. Sequencing: is "B19+mechanical first to get a completing run, research Bucket-2 in parallel" right? Any fix that
   MUST precede another (file/semantic dependency)?
2. File-collision map: which of the 22 fixes touch the SAME files and must be serialized vs truly parallel?
3. For each of the 4 keystones: is the fix approach SOUND + faithfulness-safe + non-neck-choke? Any trap?
   (e.g. for B19, what's a safe per-call distill wall-deadline value given deepseek reasoning-first runs 60-700s healthy?)
4. The preflight: what is the MINIMUM behavioral assertion set that proves all 4 keystones FIRED in real output
   (not config) on a resumed corpus_snapshot?
5. What am I MISSING / biggest risk to "all fixed + preflight + VM ASAP at highest quality"?

## OUTPUT SCHEMA
```
sequencing_verdict: <ok|change + why>
hard_dependencies: [...]
file_collision_serialize_groups: [[files that must serialize], ...]
keystone_review: { B19: <sound?+trap+safe_wall_value>, B17: ..., B18: ..., B12: ... }
preflight_min_assertions: [...]
biggest_risks: [...]
mandate_self_check: <confirm none of my advice degrades/grandfathers/neck-chokes>
```
