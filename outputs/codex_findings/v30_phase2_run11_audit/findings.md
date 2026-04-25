# Codex V30 Phase-2 run-11 audit

**7-dimension verdict**: BB=1/7 | BO=4/7 | LB=2/7 | TIE=0/7

## Ship classification

- Gate: `ITERATE`
- Net progress vs run-10: `BB+0, BO+0, LB+0`
- Regressions: no dimension-level regressions
- Slot-level regressions: `SURPASS-1` lost the explicit population field from run-10 and now has truncated baseline/endpoint text (`run-10 report.md:7`; `run-11 report.md:7`)
- Table-level regressions: in the current 2026-04-25 run-11 file, `Trial Summary` and `Trial Program Timeline` are 2 stale rows, not 4, and still contradict the body (`run-10 report.md:83-88`; `run-11 report.md:98-110`)

## 7-dim analysis

### 1. Citations — BO

Delta vs run-10: stronger BO, not enough for BB. The bibliography cleanup is real: regulatory entries now read as human labels instead of bare entity IDs (`run-11 report.md:161-166`; `run-10 report.md:139-144`), and `SURPASS-5` again carries primary-trial ETD/CI/P in-body (`run-11 report.md:23`; `run-10 report.md:23`).

That still does not reach `BB`. `SURPASS-6` remains all-gap (`run-11 report.md:27`), `SURPASS-CVOT` is still a curator gap with a placeholder bibliography item (`run-11 report.md:31,159`), several T1 bibliography entries still have blank URLs (`run-11 report.md:152,154-155,160`), and the summary/timeline tables still misstate trial facts (`run-11 report.md:102-110`). ChatGPT remains denser on pivotal-program primary framing and label-backed citation use (`state/compare_chatgpt_dr.txt:161-195,377-420,455-505,966-982`). Run-11 still beats Gemini on source hierarchy because Gemini's works cited visibly include Pharmacy Times, Lilly promo, HCPLive, and CBC (`state/compare_gemini_dr.txt:680-688,810-854`).

### 2. Regulatory — LB

Delta vs run-10: improved surface usability, still loses both. Run-11 is better at the bibliography and subsection surface: the label names are readable (`run-11 report.md:161-166`) and the FDA Zepbound block now carries real contraindication and dosing text (`run-11 report.md:51-68`) instead of pure stubs (`run-10 report.md:51`).

But the regulatory body remains too thin for `BO`. FDA Mounjaro is still a one-line stub (`run-11 report.md:47`), EMA is all-`not extractable` (`run-11 report.md:72`), NICE TA924 is all-`not extractable` (`run-11 report.md:76`), and Health Canada is all-`not extractable` (`run-11 report.md:84`). ChatGPT gives a usable U.S./EMA dosing-warning comparison (`state/compare_chatgpt_dr.txt:36-49,966-982`). Gemini still provides much fuller FDA/Health Canada warning-update narrative (`state/compare_gemini_dr.txt:530-550,573-644`). Regulatory stays `LB`.

### 3. Jurisdiction — BO

Delta vs run-10: flat `BO`. Run-11 still explicitly covers U.S., EU, U.K., and Canada in-body (`run-11 report.md:45-84`), and the bibliography labels make that breadth easier to read (`run-11 report.md:161-166`). That remains broader than Gemini's explicitly FDA/Health-Canada-heavy regulatory discussion (`state/compare_gemini_dr.txt:530-550,573-644`).

ChatGPT still beats run-11 on jurisdictional usability because it materially contrasts U.S. contraindications/warnings with EMA SmPC framing rather than merely naming authorities (`state/compare_chatgpt_dr.txt:36-49,966-982`). So this remains `BO`, not `BB`.

### 4. Claim-frames — BO

Delta vs run-10: major repairs, but not enough for a category lift. Run-11 repairs the two biggest run-10 frame regressions: `SURMOUNT-2` is no longer all-gap and now has baseline HbA1c, baseline weight, primary endpoint, sponsor, and partial framing (`run-11 report.md:35`; `run-10 report.md:35`), and `SURPASS-5` again has the core ETD/CI/P result in-body (`run-11 report.md:23`; `run-10 report.md:23`). The Thomas clamp subsection also regains population detail and glucagon suppression (`run-11 report.md:41`; `run-10 report.md:41`).

That still does not reach `BB`. `SURPASS-6` remains all-`not extractable` (`run-11 report.md:27`), `SURPASS-CVOT` remains gap-only (`run-11 report.md:31`), `SURPASS-3` and `SURPASS-4` are still mostly skeletal (`run-11 report.md:15,19`), and `SURPASS-1` regresses locally with truncated baseline/endpoint text and no population field (`run-11 report.md:7`; `run-10 report.md:7`). ChatGPT still leads on full-trial PICO completeness for `SURPASS-2/5/6` (`state/compare_chatgpt_dr.txt:161-195,377-420,455-505`). Run-11 likely still edges Gemini on uncertainty discipline, but Gemini remains fuller on `SURPASS-5/6`, `SURMOUNT-2`, and CVOT narration (`state/compare_gemini_dr.txt:197-213,329-353,425-433`). Claim-frames stays `BO`.

### 5. Structure — BO

Delta vs run-10: mixed; category unchanged. Run-11 still preserves the contract slot scaffold across efficacy, mechanism, regulatory, safety, comparative, subgroups, methods, and contradiction disclosure (`run-11 report.md:5-148`). That keeps it ahead of Gemini's purely narrative structure for auditability (`state/compare_gemini_dr.txt:26-32,653-679`).

But the table layer regresses. In the current 2026-04-25 run-11 file, `Trial Summary` and `Trial Program Timeline` contain 2 data rows, not 4, and the `SURMOUNT-2` row still contradicts the body by claiming `people without diabetes`, `HbA1c`, and `-10%` (`run-11 report.md:35,98-110`). The completeness checklist also still overstates coverage (`run-11 report.md:126`). ChatGPT remains the structural leader because it pairs study-architecture framing with a fuller evidence timeline (`state/compare_chatgpt_dr.txt:50-67,1096-1110`). Structure remains `BO`.

### 6. Contradictions — BB

Delta vs run-10: unchanged `BB`. Run-11 keeps the strongest contradiction handling of the three artifacts: a 16-item disclosure list, explanation of detector over-flagging, and explicit strict-verify traceability language (`run-11 report.md:128-148`).

ChatGPT discusses uncertainties and evidence gaps, but not in an equivalent tier-labeled contradiction audit (`state/compare_chatgpt_dr.txt:1055-1086`). Gemini closes with confident synthesis and no comparable contradiction layer (`state/compare_gemini_dr.txt:664-679`). `BB` holds.

### 7. Narrative depth — LB

Delta vs run-10: locally richer, globally still thin. Run-11 is longer and locally better where the frame repairs landed: `SURPASS-5`, `SURMOUNT-2`, Safety, Comparative, and Population Subgroups are denser than run-10 at the slot level (`run-11 report.md:23,35,88-96`; `run-10 report.md:23,35,71-79`).

But the report still reads as a shallow slot stack across most of efficacy and regulatory (`run-11 report.md:5-84`), and the contradiction caveats remain concentrated in the appendix instead of shaping the core narrative (`run-11 report.md:92,96,128-148`). ChatGPT still sustains the deepest end-to-end clinical synthesis across efficacy, safety, regulation, uncertainty, and timeline (`state/compare_chatgpt_dr.txt:595-630,916-1001,1055-1086,1096-1119`). Gemini remains broader on mechanism, `SURMOUNT-2`, CVOT, and regulatory updates even though parts are overclaimed (`state/compare_gemini_dr.txt:39-59,329-353,425-440,573-644,653-679`). Narrative depth stays `LB`.

## Reconciliation

- Bibliography cleanup is real, but it does **not** lift Citations `BO -> BB`. The labels are much better (`run-11 report.md:161-166`), yet the report still carries a placeholder `SURPASS-CVOT` bibliography item, multiple blank T1 URLs, an all-gap `SURPASS-6`, and stale/wrong summary tables (`run-11 report.md:27,31,102-110,152,154-155,159-160`).
- `SURMOUNT-2` recovery plus `SURPASS-5` ETD restoration materially repair run-10's biggest claim-frame regressions, but they do **not** lift Claim-frames `BO -> BB`. ChatGPT still has fuller pivotal-trial framing, especially `SURPASS-6` (`state/compare_chatgpt_dr.txt:377-420,455-505`), and run-11 still has hard gaps at `SURPASS-6` and `SURPASS-CVOT` (`run-11 report.md:27,31`).
- Regulatory does **not** move `LB -> BO`. Six subsections render and the labels are finally usable, but five of the six remain mostly stub-like in substance (`run-11 report.md:47,72,76,80,84`). That is still behind both ChatGPT's U.S./EMA prescribing comparison and Gemini's FDA/Health Canada warning-update coverage (`state/compare_chatgpt_dr.txt:966-982`; `state/compare_gemini_dr.txt:530-550,573-644`).
- Net progress vs run-9 checkpoint: yes at the slot level, no at the category level. Run-11 is cleaner than run-9 on bibliography labeling, `SURPASS-5` rendering, and `SURPASS-6` citation binding, but the 7-dimension score still sits at `BB=1 | BO=4 | LB=2` rather than moving the `BB` count above the run-9 audit (`outputs/codex_findings/v30_phase2_run9_audit/findings.md:3`; `outputs/codex_findings/v30_phase2_run10_audit/findings.md:3`).
- Run-11 is **not** the first `BEAT_BOTH_SHIP` candidate. It still has two `LB` dimensions (`Regulatory`, `Narrative depth`), so it misses both the strict ship rule and the checkpoint rule.

## Recommended action

`ITERATE-narrow-fix-list`

- Prioritize `SURPASS-6` extraction from the Rosenstock JAMA 2023 abstract/PMC structure; that is now the biggest remaining efficacy-frame blocker (`run-11 report.md:27`).
- Treat `SURPASS-CVOT` as a deliberate downgrade problem, not a silent-placeholder problem: either bind a verified abstract-safe frame or route the slot to a secondary-evidence downgrade path (`run-11 report.md:31,159`).
- Replace regulatory stub rendering with verified sentence-level synthesis from fetched label text for FDA Mounjaro, EMA, NICE TA924, and Health Canada (`run-11 report.md:47,72,76,84`).
- Rebuild `Trial Summary` and `Trial Program Timeline` strictly from rendered body slots; on 2026-04-25 the current run-11 file has 2 stale rows, not 4 (`run-11 report.md:98-110`).
- Add a guard for truncated slot text so `SURPASS-1` cannot regress from a populated frame to clipped strings (`run-11 report.md:7`; `run-10 report.md:7`).
