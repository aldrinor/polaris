"""Build a condensed forensic input from the 5 beatboth5 manifests + log signals."""
import json

MANIFEST_DIR = "C:/POLARIS/outputs/audits/beatboth5/manifests"
LOG_SIGNALS = "C:/POLARIS/outputs/audits/beatboth5/log_signals.txt"
OUT = "C:/POLARIS/.codex/beatboth5/bug_forensic_input.md"
SLUGS = [72, 75, 76, 78, 90]


def g(d, *path, default="MISSING"):
    cur = d
    for p in path:
        if isinstance(cur, dict) and p in cur:
            cur = cur[p]
        else:
            return default
    return cur


def fmt(v, maxlen=400):
    s = repr(v)
    if len(s) > maxlen:
        s = s[:maxlen] + " ...[truncated]"
    return s


lines = []
lines.append("# Beat-Both 5-Question Forensic Input (condensed manifest funnel + quality fields)\n")
lines.append(
    "TASK FOR REVIEWER: From these 5-question run metrics + log signals, list EVERY bug / "
    "silent-no-op / silent-cap / quality-throttle you can infer, each with the metric evidence, "
    "a P0-P3 severity, category (faithfulness/completeness/capability/stability/presentation), "
    "and a fix direction. Be exhaustive; flag anything that silently caps quality.\n"
)

for slug in SLUGS:
    path = f"{MANIFEST_DIR}/drb_{slug}_manifest.json"
    with open(path) as f:
        m = json.load(f)

    lines.append(f"\n## Q drb_{slug}\n")
    lines.append(f"- question: {fmt(g(m,'question'), 300)}")
    lines.append(f"- status: {g(m,'status')}")
    lines.append(f"- release_allowed: {g(m,'release_allowed')}")
    lines.append(f"- cost_usd: {g(m,'cost_usd')}")
    lines.append(f"- domain: {g(m,'domain')}")
    lines.append(f"- contradictions_found: {g(m,'contradictions_found')}")
    lines.append(f"- discovery_llm_degraded: {g(m,'discovery_llm_degraded')}")
    lines.append(f"- discovery_rounds_on_fallback: {g(m,'discovery_rounds_on_fallback')}")
    lines.append(f"- synthesis_n_scrub_alert: {g(m,'synthesis_n_scrub_alert')}")
    lines.append(f"- uploaded_documents_used: {g(m,'uploaded_documents_used')}  uploaded_documents_blocked: {g(m,'uploaded_documents_blocked')}")
    lines.append(f"- v30_enabled: {g(m,'v30_enabled')}  v30_warnings: {fmt(g(m,'v30_warnings'),300)}")

    # retrieval funnel
    lines.append("\n### retrieval (funnel)")
    lines.append(f"- fetched: {g(m,'retrieval','fetched')}")
    lines.append(f"- failed: {g(m,'retrieval','failed')}")
    lines.append(f"- candidates_total: {g(m,'retrieval','candidates_total')}")
    lines.append(f"- candidates_processed: {g(m,'retrieval','candidates_processed')}")
    lines.append(f"- pre_filter: {g(m,'retrieval','pre_filter')}")
    lines.append(f"- corpus_truncated: {g(m,'retrieval','corpus_truncated')}")
    lines.append(f"- api_calls: {fmt(g(m,'retrieval','api_calls'), 500)}")

    # storm
    lines.append("\n### storm_query_expansion")
    for k in ['enabled','fired','firing_status','effective_query_count','questions_added','interviews','web_result_rows_merged','web_result_urls_harvested']:
        lines.append(f"- {k}: {g(m,'storm_query_expansion',k)}")

    # agentic
    lines.append("\n### agentic_search")
    for k in ['enabled','fired','firing_status','urls_discovered','urls_discovered_total','urls_selectable']:
        lines.append(f"- {k}: {g(m,'agentic_search',k)}")

    # discovery_funnel
    lines.append("\n### discovery_funnel")
    lines.append(f"- {fmt(g(m,'discovery_funnel'), 500)}")

    # evidence_selection
    lines.append("\n### evidence_selection")
    for k in ['evidence_total','evidence_selected','dropped_count','selection_strategy']:
        lines.append(f"- {k}: {g(m,'evidence_selection',k)}")
    lines.append(f"- selected_tier_counts: {fmt(g(m,'evidence_selection','selected_tier_counts'),300)}")
    lines.append(f"- full_tier_counts: {fmt(g(m,'evidence_selection','full_tier_counts'),300)}")
    lines.append(f"- notes: {fmt(g(m,'evidence_selection','notes'),400)}")

    # corpus credibility
    lines.append("\n### corpus_credibility_disclosure")
    for k in ['total_sources','weighted_credibility_mean','had_material_deviation','gate','domain']:
        lines.append(f"- {k}: {g(m,'corpus_credibility_disclosure',k)}")
    lines.append(f"- tier_counts: {fmt(g(m,'corpus_credibility_disclosure','tier_counts'),300)}")
    lines.append(f"- tier_fractions: {fmt(g(m,'corpus_credibility_disclosure','tier_fractions'),300)}")

    # generator
    # D-5 (#1182): sections_kept is the POLARIS section count surfaced into the §-1.1
    # POLARIS-vs-Gemini/ChatGPT comparison. As of the D-5 fix, run_honest_sweep_r3.py
    # computes sections_kept EXCLUDING 0-verified gap stubs (the universal survivor
    # signal: not dropped_due_to_failure and not is_gap_stub and sentences_verified>0),
    # so this count no longer over-states POLARIS's verified section count. Manifests
    # produced BEFORE the D-5 fix may carry a stale-inflated sections_kept; the manifest
    # lacks per-section is_gap_stub / sentences_verified, so the corrected count can only
    # be re-derived by re-running the sweep on the fixed code (not recomputed here).
    lines.append("\n### generator")
    lines.append(
        "- (D-5 #1182: sections_kept EXCLUDES 0-verified gap stubs ONLY for manifests "
        "generated AFTER the D-5 fix landed; manifests generated BEFORE the fix may "
        "OVER-COUNT sections by including gap stubs, and that over-count cannot be "
        "corrected here — the manifest carries no per-section is_gap_stub / "
        "sentences_verified, so re-derivation requires re-running the sweep on fixed code.)"
    )
    for k in ['sections_kept','sentences_verified','sentences_dropped','verified_words','words','limitations_words','analyst_synthesis_words','analyst_synthesis_input_tokens','analyst_synthesis_output_tokens']:
        lines.append(f"- {k}: {g(m,'generator',k)}")
    lines.append(f"- outline_sections: {fmt(g(m,'generator','outline_sections'),300)}")

    # quantified_analysis (all subfields)
    lines.append("\n### quantified_analysis (ALL subfields)")
    qa = g(m,'quantified_analysis')
    if isinstance(qa, dict):
        for k2, v2 in qa.items():
            lines.append(f"- {k2}: {fmt(v2, 350)}")
    else:
        lines.append(f"- {fmt(qa)}")

    # nli
    lines.append("\n### nli_verification")
    for k in ['advisory','judge','model','nli_status','eligible_sentences','sentences_checked','sentences_scored','skipped_no_span','entailed_count','neutral_count','contradicted_count','disputed_count','judge_error_count']:
        lines.append(f"- {k}: {g(m,'nli_verification',k)}")
    lines.append(f"- disputed (sample): {fmt(g(m,'nli_verification','disputed'),500)}")
    lines.append(f"- judge_errors: {fmt(g(m,'nli_verification','judge_errors'),300)}")

    # four_role
    lines.append("\n### four_role_evaluation (summary)")
    for k in ['coverage_fraction','release_allowed','fabricated_occurrence_latched']:
        lines.append(f"- {k}: {g(m,'four_role_evaluation',k)}")
    lines.append(f"- held_reasons: {fmt(g(m,'four_role_evaluation','held_reasons'),400)}")
    lines.append(f"- needs_rewrite: {fmt(g(m,'four_role_evaluation','needs_rewrite'),300)}")
    lines.append(f"- gaps: {fmt(g(m,'four_role_evaluation','gaps'),500)}")
    fv = g(m,'four_role_evaluation','final_verdicts')
    if isinstance(fv, dict):
        from collections import Counter
        c = Counter(fv.values())
        lines.append(f"- final_verdicts tally: {dict(c)} (n={len(fv)})")

    # report_redaction
    lines.append("\n### report_redaction (summary)")
    for k in ['redacted_count','redacted_claim_ids','already_absent_claim_ids']:
        lines.append(f"- {k}: {fmt(g(m,'report_redaction',k),300)}")

    # completeness
    lines.append("\n### completeness")
    cp = g(m,'completeness')
    if isinstance(cp, dict):
        for k2, v2 in cp.items():
            lines.append(f"- {k2}: {fmt(v2,300)}")

    # frame_coverage_report
    lines.append("\n### frame_coverage_report (coverage + must-cover gaps)")
    for k in ['schema_version','total_entities','total_slots','pass_count','partial_count','frame_gap_count','pipeline_fault_count']:
        lines.append(f"- {k}: {g(m,'frame_coverage_report',k)}")
    lines.append(f"- by_status: {fmt(g(m,'frame_coverage_report','by_status'),300)}")
    # entries: extract gaps (status not pass)
    entries = g(m,'frame_coverage_report','entries')
    if isinstance(entries, list):
        gap_notes = []
        for e in entries:
            if isinstance(e, dict) and e.get('status') != 'pass':
                gap_notes.append({k: e.get(k) for k in ('entity','status','note','doi') if k in e})
        lines.append(f"- non-pass entries: {fmt(gap_notes, 600)}")

    # adequacy + advisory extras
    lines.append("\n### misc advisory")
    lines.append(f"- adequacy: {fmt(g(m,'adequacy'),400)}")
    lines.append(f"- analytical_depth_advisory: {fmt(g(m,'analytical_depth_advisory'),500)}")
    lines.append(f"- evaluator_gate_advisory: {fmt(g(m,'evaluator_gate_advisory'),400)}")
    lines.append(f"- evaluator_rule_pass: {g(m,'evaluator_rule_pass')}  evaluator_rule_fail: {g(m,'evaluator_rule_fail')}")
    lines.append(f"- tool_utilization: {fmt(g(m,'tool_utilization'),400)}")
    lines.append(f"- fact_dedup: {fmt(g(m,'fact_dedup'),300)}")
    lines.append(f"- finding_dedup: {fmt(g(m,'finding_dedup'),300)}")
    lines.append(f"- judge_verdicts: {fmt(g(m,'judge_verdicts'),300)}")
    lines.append(f"- reasoning_trace: {fmt(g(m,'reasoning_trace'),300)}")

# append log signals
lines.append("\n\n## LOG SIGNALS (counts prefixed; from outputs/audits/beatboth5/log_signals.txt)\n")
lines.append("```")
with open(LOG_SIGNALS, encoding="utf-8", errors="replace") as f:
    lines.append(f.read().rstrip())
lines.append("```")

with open(OUT, "w", encoding="utf-8") as f:
    f.write("\n".join(lines))

print(f"WROTE {OUT}")
import os
print(f"SIZE {os.path.getsize(OUT)} bytes")
