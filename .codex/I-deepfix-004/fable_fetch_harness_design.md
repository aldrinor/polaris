# Fast fetch cited-content harness — Fable design (2026-07-09)

Opus builds this. Proves in ~5 min (parallel) whether the fetch/search module returns the CITED article — replaces the hours-long full-pipeline test loop. Grounded in real code + the live banked corpus + Crossref; every URL/fingerprint verified.

## Seam under test
`refetch_for_extraction_with_diagnostics(url, max_chars=2000)` (live_retriever.py:3181). One call exercises the whole chain: `_fetch_content` → AccessBypass cascade (B1 DOI-redirect resolution access_bypass.py:3840, `#page` anchor, B2 fitz page-slice access_bypass.py:4896, Zyte, PDF extractors) → clean_fetch_body → fetch-shell screen → step-D front-matter screen (live_retriever.py:3347) → provenance quote. Returns `(quote, diagnostics)`; `quote` = EXACTLY the stored span; `diagnostics["failure_mode"]` ∈ {'', wrong_content_front_matter, fetch_shell, paywall_shell, thin_content, fetch_failed, timeout, exception}. Already thread-parallel-safe (daemon thread + own loop, joined at PG_FETCH_DEADLINE_SECONDS=90; PG_BYPASS_MAX_INFLIGHT sem=32) → fan-out = plain ThreadPoolExecutor, no asyncio surgery.
NOT-yet-built (day-one RED = fix-loop targets, not harness bugs): step H challenge co-signal; step B3 title-locate (no-anchor containers can only pass via honest degrade today).

## Files
- `scripts/fetch_cited_content_harness.py` (~300 LOC, read-only imports from src/).
- `config/fetch_harness_cases.yaml` (the labeled set — data, editable without code).
- `tests/polaris_graph/test_fetch_harness_oracle.py` (offline oracle unit tests vs the REAL banked span heads).
- Results: `outputs/fetch_harness/<utc>/results.json` + report.md. GitHub issue first (§-1.2).

## squash(text)
NFKD → strip combining marks → casefold → keep letters+digits only. Survives PDF hyphen-breaks, diacritics, case. All fingerprints below already squashed.

## 22 labeled cases (all real, verified)
**A. Good controls — expect `article` (breaking these FAILS the harness):**
- good_arxiv_html ev_752 `https://arxiv.org/html/2503.00079v1` → contains `ailiteracy`
- good_feds_note ev_508 `https://www.federalreserve.gov/econres/notes/feds-notes/ai-adoption-and-firms-job-posting-behavior-20260327.html` → `jobposting`
- good_oa_pdf_nber ev_023 `https://www.nber.org/system/files/working_papers/w31161/w31161.pdf` → `generativeaiatwork`/`brynjolfsson`
- good_oecd_fullreport ev_590 `https://www.oecd.org/en/publications/oecd-employment-outlook-2023_08785bba-en/full-report/artificial-intelligence-and-the-labour-market-introduction_ea35d1c5.html` → `broecke`/`employmentoutlook2023`

**B. Combined-PDF w/ page anchor — expect `article` (B must RECOVER; degrade = FAIL):**
- dgpu_sport_managers ev_664 `https://doi.org/10.58224/2658-5286-2026-9-2-203-210` → contains `спортивныхменеджеров`/`волонтерск`/`карьерныхтраекторий` (Грушина 203–210); group dgpu_reb_9_2
- dgpu_poultry ev_700 `https://doi.org/10.58224/2658-5286-2026-9-2-87-95` → `птицепродуктов`/`птицеводств` (Сарсадских 87–95); group dgpu_reb_9_2
- ecsoc_parinov ev_232 `https://doi.org/10.17323/1726-3247-2025-5-53-86` → `институциональн`/`паринов` ; NOT `социальныйпортреткластеров` (banked wrong head)
Live proof: ev_664 & ev_700 today share identical head "физическое развитие…" (2 articles, 1 blob).

**C. No-anchor multi-work containers — expect `no_front_matter_span` (PASS = wrong_content_front_matter degrade OR a non-front-matter real span; FAIL = front-matter/committee-list adopted):**
- dgpu_whole_issue `https://doi.org/10.58224/2658-5286-2025-8-5` → NOT `редакционнаяколлегия`
- naukarus_japan ev_487 `https://doi.org/10.34660/inf.2024.42.58.280` (if eligible: `distributionnetworks`/`kharlanov`); group naukarus_sco
- naukarus_food ev_490 `https://doi.org/10.34660/inf.2024.63.64.277` (if eligible: `foodexports`/`chinesemarket`/`razumnova`); group naukarus_sco
- isg_2026 ev_470 `https://doi.org/10.46299/isg.2026.1.10` → NOT `marchenkodmytro` (banked committee-list head); group isg
- isg_2025 ev_358 `https://doi.org/10.46299/isg.2025.2.9` → NOT `marchenkodmytro`; group isg
- auspicia_energy ev_624 `https://doi.org/10.36682/a_2025_2_4` → NOT `recenzovanyvedeckycasopis` (masthead); if eligible `energysecurity`/`invasionofukraine`/`kovacova`; group auspicia
- auspicia_2 ev_599 `https://doi.org/10.36682/a_2025_2_5` → NOT `recenzovanyvedeckycasopis`; group auspicia
Live proof: ev_358 & ev_470 (different volumes!) share the committee-list head; ev_624 & ev_599 share the "AUSPICIA Recenzovaný vědecký časopis" masthead. Detector gaps for the loop: is_issue_front_matter contents-vocab has no Czech `obsah`, nothing catches a committee list.

**D. Hub/landing/error shells — expect `refused` (PASS iff eligible=False):**
- hub_hbr ev_527 `https://hbr.org/topic/subject/generative-ai`
- hub_oecd ev_726 `https://www.oecd.org/en/topics/policy-issues/future-of-work.html`
- hub_voced ev_734 `https://www.voced.edu.au/focus-ai-and-education-and-employment`
- challenge_voced `https://www.voced.edu.au/challenge?destination=%2Ffocus-ai-and-education-and-employment`
- quora ev_337 `https://www.quora.com/What-is-the-potential-impact-of-generative-AI-on-individual-workers-activities`

**E. Paywalled — expect `recover_or_disclose` (PASS = real text via Zyte OR honest refusal; FAIL = SSRN delivery chrome adopted):**
- ssrn_1 ev_398 `https://papers.ssrn.com/sol3/Delivery.cfm/5136877.pdf?abstractid=5136877&mirid=1` (if eligible `labormarketeffectsofgenerative`/`hartley`); NOT `suggestedcitation`/`pagesposted`
- ssrn_2 ev_747 `https://papers.ssrn.com/sol3/Delivery.cfm/5133376.pdf?abstractid=5133376&mirid=1` (if eligible `agenticgenai`/`workforcedevelopment`); NOT `suggestedcitation`/`pagesposted`

**F. OA wrong-work swap — expect `article_or_degrade`:**
- oa_swap ev_349 `https://doi.org/10.9728/dcs.2025.26.12.3433` (if eligible `innovationstrategies`/`ecosystemcompanies`); NOT `reveliolabs` (banked swapped-in wrong work)

## Oracle (harness-owned; NEVER import the production predicate — I-wire-013 independence)
- squash / contains_any / contains_none (substring on squashed).
- front_matter_structural(quote): (≥3 dot-leader-then-page lines regex `\.{3,}\s*[ivxlcdm\d]{1,5}\b`) OR (`редакционнаяколлегия`) OR (`tableofcontents`) OR (`editorialboard` AND `issn`). Co-signals — a lone `содержание` must NOT fire (real poultry prose has "содержание белка").
- global collision: group ELIGIBLE quotes by squash; two cases with different DOIs sharing one squash → FAIL both `container_collision`.
- distinct_group: within a group every eligible pair must differ after squash.
Eligible = quote ≥200 chars. Verdict per class: article=PASS iff failure_mode=='' AND eligible AND contains_any AND contains_none AND NOT front_matter_structural (fetch_failed/timeout/exception→UNREACHABLE, blocks green but labeled honestly; else FAIL). article_or_degrade / recover_or_disclose = PASS as above else DEGRADED_OK on {wrong_content_front_matter,fetch_shell,paywall_shell,thin_content,fetch_failed,timeout} else FAIL. no_front_matter_span = PASS iff failure_mode=='wrong_content_front_matter' OR (eligible AND contains_none AND NOT front_matter_structural AND contains_any-where-listed); DEGRADED_OK other refusals; FAIL iff front-matter span adopted. refused = PASS iff NOT eligible; FAIL iff eligible.

## Fan-out / isolation
ThreadPoolExecutor(PG_HARNESS_MAX_PARALLEL default 12; use 6 if the main pipeline is mid-run). Per case future.result(PG_HARNESS_CASE_TIMEOUT_S=240); total PG_HARNESS_TOTAL_TIMEOUT_S=900. ~4–6 min for 22. First-class: `--only <case|ev>` (seconds), `--rerun-failures <results.json>`, `--list`, `--url <u> --expect <cls> --contains <stem>`.

## Output / exit
Console + report.md + results.json. Every FAIL quotes the first 300 chars of the offending span (repr) — the span text IS the proof (§-1.1, never a count). results.json per case: url, expect, verdict, failure_mode, access_method, raw_char_count, elapsed, quote head, each check bool. Exit: 0 green (no FAIL/UNREACHABLE), 1 any FAIL/UNREACHABLE, 2 VOID (flags off/key missing), 3 internal.

## Flag-gate refusal (can't fake a pass)
At startup assert pdf_cited_work_slice_enabled(), span_cited_work_screen_enabled()+cited_span_shell_detect_enabled(), PG_REFETCH_FULL_BODY not falsey, PG_DISABLE_ACCESS_BYPASS!=1, ZYTE_API_KEY non-empty. Any off → print "RESULT VOID — FIX FLAGS OFF", write no PASS, exit 2. Flag states stamped into report header + results.json.

## Fast fix-loop
Run full set on VM (~5 min) → read report.md fails (quoted bad span + failure_mode + access method) → `--only <case>` with INFO logging, read trace (`[B1-DOI]`,`[ACCESS]`,`[refetch_for_extraction]`,`[B1-FURNITURE]`) → surgical fix in src/ (detector vocab / anchor mapping / screen wiring — never a cap) → `--rerun-failures` (~1–2 min) → repeat. GREEN = 0 FAIL + all 4 good controls PASS in the SAME run → only THEN authorize the full pipeline. Day-one RED targets: isg committee-list (no detector), Auspicia Czech masthead (`obsah` missing), dgpu journal-page-vs-PDF-index anchor offset (content fingerprint catches offset errors), hubs (no fetch-side hub signal), voced challenge (step H unbuilt).

## Run on VM
`ssh -p 20988 root@ssh9.vast.ai`, `cd /workspace/POLARIS && set -a && . .env && set +a && PYTHONIOENCODING=utf-8 PYTHONPATH=/workspace/POLARIS python3 scripts/fetch_cited_content_harness.py`. §8.4: PG_HARNESS_MAX_PARALLEL=6 if main run active; leave PG_CLINICAL_PDF_EXTRACTOR unset unless mineru confirmed up. No mocks (live net is the point); oracle unit tests are the only offline part, use real banked span strings as fixtures.
