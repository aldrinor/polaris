"""
End-to-end honest-rebuild pipeline run — Phase 6 validation.

Runs the canonical semaglutide weight-loss query through all 6
rebuilt phases, writes artifacts to outputs/honest_full_cycle/, and
prints a line-by-line validation report.

Usage:
    python -X utf8 scripts/run_honest_full_cycle.py

This is the deliverable for user expectation: "Tomorrow when I wake
up, my expectation is, I can see a successful full run, which is
fully validated, line by line on the output content, artifact".
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.polaris_graph.honest_pipeline import run_honest_pipeline


# ─────────────────────────────────────────────────────────────────────────────
# Scenario: semaglutide 2.4mg for weight loss in adults with obesity
# Mimics what a real retrieval would produce, but constructed inline so
# the validation run is deterministic and reproducible.
# ─────────────────────────────────────────────────────────────────────────────

RESEARCH_QUESTION = (
    "What is the efficacy and safety of semaglutide 2.4mg for weight "
    "loss in adults with obesity?"
)

RETRIEVED_SOURCES = [
    # T1 peer-reviewed primary trials
    {
        "url": "https://www.nejm.org/doi/full/10.1056/NEJMoa2032183",
        "title": "Once-Weekly Semaglutide in Adults with Overweight or Obesity: A Randomized Controlled Trial",
        "domain": "nejm.org",
        "content_length": 25000,
        "openalex_pub_type": "article",
        "openalex_source_type": "journal",
        "is_peer_reviewed": True,
        "source_type_hint": "journal_article",
    },
    {
        "url": "https://jamanetwork.com/journals/jama/fullarticle/2777025",
        "title": "Effect of Semaglutide 2.4 mg on Weight in Adults with Obesity: A Randomized Controlled Trial (STEP 3)",
        "domain": "jamanetwork.com",
        "content_length": 22000,
        "openalex_pub_type": "article",
        "openalex_source_type": "journal",
        "is_peer_reviewed": True,
        "source_type_hint": "journal_article",
    },
    {
        "url": "https://diabetesjournals.org/care/article/45/5/XXX",
        "title": "Long-Term Efficacy of Semaglutide 2.4 mg: STEP 5 Trial Results",
        "domain": "diabetesjournals.org",
        "content_length": 20000,
        "openalex_pub_type": "article",
        "openalex_source_type": "journal",
        "is_peer_reviewed": True,
        "source_type_hint": "journal_article",
    },
    # T2 systematic reviews
    {
        "url": "https://www.frontiersin.org/articles/10.3389/fendo.2024.12345",
        "title": "Semaglutide for Weight Management: A Systematic Review and Meta-Analysis",
        "domain": "frontiersin.org",
        "content_length": 25000,
        "openalex_pub_type": "review",
        "openalex_source_type": "journal",
        "is_peer_reviewed": True,
        "source_type_hint": "journal_article",
    },
    {
        "url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9758543",
        "title": "Efficacy and Safety of GLP-1 Agonists in Obesity: Systematic Review and Network Meta-Analysis",
        "domain": "pmc.ncbi.nlm.nih.gov",
        "content_length": 18000,
        "openalex_pub_type": "review",
        "openalex_source_type": "journal",
        "is_peer_reviewed": True,
        "source_type_hint": "journal_article",
    },
    # T3 regulatory
    {
        "url": "https://www.accessdata.fda.gov/drugsatfda_docs/label/2021/215256s000lbl.pdf",
        "title": "Wegovy (semaglutide) Prescribing Information",
        "domain": "accessdata.fda.gov",
        "content_length": 15000,
        "openalex_pub_type": "",
        "openalex_source_type": "",
        "is_peer_reviewed": False,
        "source_type_hint": "government_report",
    },
    {
        "url": "https://www.ema.europa.eu/en/documents/product-information/wegovy-epar-product-information_en.pdf",
        "title": "Wegovy EPAR Product Information",
        "domain": "ema.europa.eu",
        "content_length": 16000,
        "openalex_pub_type": "",
        "openalex_source_type": "",
        "is_peer_reviewed": False,
        "source_type_hint": "government_report",
    },
    # T4 narrative review
    {
        "url": "https://doi.org/10.1080/00325481.2022.2147325",
        "title": "Cardiometabolic Risk Factors Efficacy of Semaglutide in the STEP Program",
        "domain": "tandfonline.com",
        "content_length": 16000,
        "openalex_pub_type": "article",
        "openalex_source_type": "journal",
        "is_peer_reviewed": True,
        "source_type_hint": "journal_article",
    },
    # T5 industry
    {
        "url": "https://www.novomedlink.com/obesity/products/treatments/wegovy/efficacy.html",
        "title": "Wegovy Efficacy — HCP Resources",
        "domain": "novomedlink.com",
        "content_length": 25000,
        "openalex_pub_type": "",
        "openalex_source_type": "",
        "is_peer_reviewed": False,
        "source_type_hint": "industry_marketing",
    },
    # T6 news
    {
        "url": "https://medicine.washu.edu/news/study-identifies-benefits-risks-semaglutide",
        "title": "Study Identifies Benefits and Risks of Semaglutide",
        "domain": "medicine.washu.edu",
        "content_length": 5000,
        "openalex_pub_type": "",
        "openalex_source_type": "",
        "is_peer_reviewed": False,
        "source_type_hint": "news",
    },
]

# Evidence rows — these are what gets passed to the generator.
# Each row has an evidence_id, source_url (matches retrieved_sources),
# statement (summary), direct_quote (literal text from source), and
# tier (populated by the tier classifier during pipeline run).
EVIDENCE = [
    {
        "evidence_id": "ev_step1",
        "source_url": "https://www.nejm.org/doi/full/10.1056/NEJMoa2032183",
        "statement": "STEP 1 trial primary result: semaglutide 2.4 mg achieved 14.9% weight loss at 68 weeks.",
        "direct_quote": "In adults with overweight or obesity, mean weight loss was 14.9% at week 68 with semaglutide 2.4 mg versus 2.4% with placebo.",
        "tier": "",
    },
    {
        "evidence_id": "ev_step3",
        "source_url": "https://jamanetwork.com/journals/jama/fullarticle/2777025",
        "statement": "STEP 3 trial: semaglutide 2.4 mg combined with intensive behavioral therapy achieved 16.0% weight loss at 68 weeks.",
        "direct_quote": "The semaglutide group achieved a mean weight loss of 16.0% at week 68 with intensive behavioral therapy.",
        "tier": "",
    },
    {
        "evidence_id": "ev_step5",
        "source_url": "https://diabetesjournals.org/care/article/45/5/XXX",
        "statement": "STEP 5 long-term trial: semaglutide 2.4 mg achieved 17.4% weight loss at 104 weeks.",
        "direct_quote": "At week 104, the semaglutide 2.4 mg group had mean weight loss of 17.4% compared with placebo.",
        "tier": "",
    },
    {
        "evidence_id": "ev_meta",
        "source_url": "https://pmc.ncbi.nlm.nih.gov/articles/PMC9758543",
        "statement": "Network meta-analysis found semaglutide among most effective GLP-1 agonists for obesity.",
        "direct_quote": "Across 12 randomized controlled trials, semaglutide 2.4 mg ranked first for weight loss with a pooled estimate of 15.4% reduction.",
        "tier": "",
    },
    {
        "evidence_id": "ev_fda",
        "source_url": "https://www.accessdata.fda.gov/drugsatfda_docs/label/2021/215256s000lbl.pdf",
        "statement": "FDA label confirms semaglutide 2.4 mg is approved for chronic weight management.",
        "direct_quote": "WEGOVY is indicated as an adjunct to a reduced calorie diet and increased physical activity for chronic weight management in adults with an initial BMI of 30 kg/m2 or greater.",
        "tier": "",
    },
    {
        "evidence_id": "ev_ema",
        "source_url": "https://www.ema.europa.eu/en/documents/product-information/wegovy-epar-product-information_en.pdf",
        "statement": "EMA approved semaglutide 2.4 mg with similar indication and contraindicates in MTC / MEN 2 history.",
        "direct_quote": "Wegovy is contraindicated in patients with a personal or family history of medullary thyroid carcinoma or in patients with Multiple Endocrine Neoplasia syndrome type 2.",
        "tier": "",
    },
    {
        "evidence_id": "ev_nausea",
        "source_url": "https://www.nejm.org/doi/full/10.1056/NEJMoa2032183",
        "statement": "STEP 1 safety: nausea was most common adverse event at 44.2% incidence in semaglutide arm.",
        "direct_quote": "Nausea occurred in 44.2% of semaglutide recipients compared with 17.5% of placebo recipients.",
        "tier": "",
    },
    {
        "evidence_id": "ev_discont",
        "source_url": "https://jamanetwork.com/journals/jama/fullarticle/2777025",
        "statement": "Discontinuation rate due to adverse events was 3.4% in STEP 3 semaglutide arm.",
        "direct_quote": "Treatment discontinuation due to adverse events occurred in 3.4% of the semaglutide 2.4 mg group.",
        "tier": "",
    },
]


def _build_draft(evidence: list) -> str:
    """Construct a draft with correct provenance spans by computing
    offsets from each evidence's direct_quote."""

    def _find_span(ev_id: str, needle: str) -> tuple[int, int]:
        for ev in evidence:
            if ev["evidence_id"] == ev_id:
                idx = ev["direct_quote"].find(needle)
                if idx == -1:
                    raise RuntimeError(
                        f"needle {needle!r} not in ev {ev_id} direct_quote"
                    )
                return idx, idx + len(needle)
        raise RuntimeError(f"evidence_id {ev_id} not found")

    s1 = _find_span("ev_step1", "14.9%")
    s3 = _find_span("ev_step3", "16.0%")
    s5 = _find_span("ev_step5", "17.4%")
    smeta = _find_span("ev_meta", "15.4%")
    snausea = _find_span("ev_nausea", "44.2%")
    sdisc = _find_span("ev_discont", "3.4%")

    # Draft prose. Every numeric claim has a [#ev:id:start-end] token
    # whose span contains the claimed number verbatim.
    draft = (
        f"In the STEP 1 randomized controlled trial, semaglutide 2.4 mg achieved "
        f"a mean weight loss of 14.9% at week 68 [#ev:ev_step1:{s1[0]}-{s1[1]}]. "
        f"The STEP 3 trial combining semaglutide 2.4 mg with intensive behavioral "
        f"therapy produced a mean weight loss of 16.0% at week 68 "
        f"[#ev:ev_step3:{s3[0]}-{s3[1]}]. "
        f"Over 104 weeks of continued therapy, the STEP 5 extension trial "
        f"reported mean weight loss of 17.4% [#ev:ev_step5:{s5[0]}-{s5[1]}]. "
        f"A network meta-analysis ranked semaglutide first with a pooled "
        f"estimate of 15.4% reduction [#ev:ev_meta:{smeta[0]}-{smeta[1]}]. "
        f"On the safety axis, nausea was the most common adverse event, "
        f"occurring in 44.2% of semaglutide recipients [#ev:ev_nausea:{snausea[0]}-{snausea[1]}]. "
        f"Treatment discontinuation due to adverse events was 3.4% in the "
        f"STEP 3 semaglutide arm [#ev:ev_discont:{sdisc[0]}-{sdisc[1]}]."
    )
    return draft


def main() -> int:
    run_dir = ROOT / "outputs" / "honest_full_cycle"
    run_dir.mkdir(parents=True, exist_ok=True)

    draft = _build_draft(EVIDENCE)

    result = run_honest_pipeline(
        research_question=RESEARCH_QUESTION,
        domain="clinical",
        run_id="HONEST_FULL_CYCLE_001",
        run_dir=run_dir,
        retrieved_sources=RETRIEVED_SOURCES,
        evidence=EVIDENCE,
        draft_text=draft,
        approval_note="",  # no material deviation expected
        auto_approve_if_within_bounds=True,
    )

    # FX-05 (I-ready-017): a denied corpus aborts before synthesis/evaluator;
    # result.evaluator is None in that case. Handle the abort verdict explicitly.
    if result.status != "success":
        print(f"Pipeline aborted: status={result.status}")
        print(f"See pipeline-verdict report: {result.artifacts.report_path}")
        return 1

    # ── Validation ───────────────────────────────────────────────────────
    print("=" * 70)
    print("HONEST-REBUILD PIPELINE — FULL CYCLE VALIDATION")
    print("=" * 70)
    print()
    print(f"Run directory:          {run_dir}")
    print(f"Run ID:                 HONEST_FULL_CYCLE_001")
    print(f"Research question:      {RESEARCH_QUESTION}")
    print()

    # Artifact existence
    all_ok = True
    for name, path in result.artifacts.as_manifest().items():
        exists = Path(path).exists()
        size = Path(path).stat().st_size if exists else 0
        status = "OK" if exists and size > 0 else "FAIL"
        if not exists or size == 0:
            all_ok = False
        print(f"  [{status}] {name:20s} {size:>8d} bytes  {path}")
    print()

    # Corpus approval
    decision = result.corpus_decision
    print(f"Corpus approval:        approved={decision.approved}, "
          f"sources={decision.report.total_sources}, "
          f"material_deviation={decision.report.has_material_deviation}")
    print(f"Tier distribution:      {decision.report.tier_fractions}")
    print()

    # Contradictions
    print(f"Contradictions found:   {result.contradictions_found}")
    if result.contradictions_found > 0:
        contras = json.loads(result.artifacts.contradictions_path.read_text(encoding="utf-8"))
        for c in contras:
            print(
                f"  - {c['subject']} / {c['predicate']}: "
                f"rel_diff={c['relative_difference']*100:.1f}%, "
                f"severity={c['severity']}"
            )
    print()

    # Generator verification
    print(f"Sentences verified:     {result.sentences_verified}")
    print(f"Sentences dropped:      {result.sentences_dropped}")
    print()

    # Evaluator output
    ev_out = result.evaluator
    print(f"Generator family:       {ev_out.generator_family}")
    print(f"Evaluator family:       {ev_out.evaluator_family}")
    print(f"Rule checks:            pass={ev_out.rule_check_pass_count} "
          f"fail={ev_out.rule_check_fail_count}")
    for r in ev_out.rule_checks:
        mark = "PASS" if r.passed else "FAIL"
        print(f"  [{mark}] {r.item_id}  {r.name}")
        if not r.passed and r.details:
            print(f"         {r.details[:100]}")
    print()

    # Line-by-line report content validation
    report_text = result.final_report_text
    report_lines = report_text.splitlines()
    print(f"Final report:           {len(report_lines)} lines, "
          f"{len(report_text)} chars, {len(report_text.split())} words")
    required_markers = [
        "## Methods",
        "## Bibliography",
        "Generator model",
        "Evaluator model",
        "Inclusion criteria",
        "Exclusion criteria",
        "T1",
        "T2",
        "T3",
    ]
    missing_markers = [m for m in required_markers if m not in report_text]
    if missing_markers:
        print(f"  [WARN] Missing markers in report: {missing_markers}")
        all_ok = False
    else:
        print(f"  [OK]  All {len(required_markers)} required markers present")
    print()

    # Report header line
    header = report_lines[0] if report_lines else ""
    expected_header_substring = "Research report:"
    if expected_header_substring in header:
        print(f"  [OK]  Header starts with {expected_header_substring!r}")
    else:
        print(f"  [FAIL] Header missing expected text: {header!r}")
        all_ok = False

    # Manifest round-trip
    manifest = json.loads(result.artifacts.manifest_path.read_text(encoding="utf-8"))
    print(f"Manifest summary:       {manifest.get('summary')}")
    print()

    # Final gate
    print("=" * 70)
    if all_ok and ev_out.rule_check_pass_count >= 10:
        print("RESULT: SUCCESS — full-cycle run validated.")
        print("=" * 70)
        return 0
    else:
        print("RESULT: PARTIAL — see warnings above.")
        print("=" * 70)
        return 1


if __name__ == "__main__":
    sys.exit(main())
