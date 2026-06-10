# drb_78_parkinsons_dbs — Claude independent §-1.1 audit + reconcile with Codex

Target run: outputs/audits/beatboth7/drb_78_parkinsons_dbs (SUCCESS run with real report.md).
NOT the .codex/forensic abort run (that was a separate abort_scope_rejected run).

## Codex verdict (provided)
ran=true, beat_chatgpt=true, beat_gemini=true, fabrication_found=false
(matches .codex/beatboth7/drb_78_parkinsons_dbs_audit_verdict2.txt)

## Claude independent line-by-line verification (high-severity claims vs cited spans in evidence_pool.json)
- S0 dopaminergic_withdrawal_caution:12100-12900 -> FDA carbidopa-levodopa label NMS/hyperpyrexia withdrawal warning. VERIFIED (lethal-if-wrong claim is faithful).
- S1 dbs_vs_medical_therapy_rct:0-800/100-900/800-1600 -> NEJM NEJMoa060281 abstract. Every number matches: N=156, PDQ-39 +9.5, UPDRS-III +19.6, 50/78 P=0.02, 55/78 P<0.001, SAE 13% vs 4% P<0.04, fatal ICH, overall AE 64% vs 50% P=0.08. VERIFIED.
- parkinson_staging_progression:0-800 -> MDS-UPDRS parts I-IV. VERIFIED.
- dbs_complications_warning_signs:0-800 -> abstract supports "hardware complications"; report honestly discloses no family-recognition info extractable. VERIFIED + honest gap.
- ev_544:500-1300 -> 225 DBS pts, 85%/58%/42%, US$42-146. VERIFIED.
- ev_736:2700-3500/3000-3800/3400-4200 -> psychosis up to 70%, HR 1.71, 49% hosp HR 1.49; OH 30-50%, fall 43-68%; underweight HR 2.05. VERIFIED.
- ev_034:4400-5200/3900-4700 -> mobility 60.5% at 11-20yr; tremor 45.2% early. VERIFIED.
- ev_681:9100-9900/3800-4600 -> R2=0.36, anxiety -0.30, depression -0.17; 58.2% wives/24.6% husbands/age 66.6/92.5%. VERIFIED.
- ev_575:2900-3700 -> 2.1:1 men:women referral ratio > PD diagnosis ratio. VERIFIED.

Result: 0 fabrications, 0 unsupported S0/S1 claims. Report also redacts claims that failed 4-role verification and discloses retrieval gaps. polaris_faithful = TRUE.

## Comparative
- Beat Gemini = TRUE (clean). Gemini over-specifies with unverifiable superscript cites: "90,000/yr, 1.5M", PHS "0.3% incidence, ~4% mortality", "4-5 extra hours/day", PDD "85% by age 90"; confident, thin grounding. I hunted Gemini for defects and found four real over-claims.
- Beat ChatGPT = NOT ESTABLISHED (Claude disagrees with Codex). I ran the SAME defect-hunt on ChatGPT that I ran on Gemini and found ZERO self-evidently fabricated/unsupported/over-claimed clinical assertions: ChatGPT systematically hedges ("usually under 2%", "rates vary by era and definition"), labels its own inferences ("a clinical inference", "pragmatic synthesis, not a validated triage scale"), gives ranges with explicit uncertainty, and defers to local authority. Both reports sit at ZERO fabrications. POLARIS's only edge is per-claim span traceability = a process/metadata advantage, which the 2026-06-09 first full §-1.1 dual audit of this exact 5-Q set EXPLICITLY ruled insufficient to count as "beat" (auditors refused to manufacture a defect against gpt_5_5_pro). My earlier draft cited that memory as "consistent" while reversing its conclusion — corrected here.

## Reconcile (task rule: disagree OR codex-failed -> conservative beat=false unless BOTH true, + flag)
auditors_agree = FALSE (Codex bc=true; Claude bc=not-established. They diverge on beat_chatgpt.)
final_beat_chatgpt = FALSE (conservative: not both-true; flagged disagreement).
final_beat_gemini = TRUE (both auditors agree true).
polaris_faithful = TRUE (0 fabrications, independently verified S0 dosing + all S1 efficacy numbers on cited spans).
FLAG: beat_chatgpt is the contested field. POLARIS is faithful and beats Gemini, but on the brief's bar ("more faithful = fewer fabrications/unsupported, better grounding") it does NOT out-faithful a genuinely careful, zero-fabrication ChatGPT report; traceability alone is not a §-1.1 win.
