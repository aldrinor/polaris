"""I-deepfix-001 wave-2 (#1370) seconds-level RED/GREEN harness — REAL box2 chrome/noise fixtures.

Every string here is verbatim from box2's rendered report.md (LAW II: real data, not synthetic).
CHROME must DROP (is_render_chrome_or_unrenderable -> True); real FINDINGS must survive (-> False).
Run: python scripts/dr_benchmark/_wave2_assert.py
"""
import os
import sys

os.environ.setdefault("PG_RENDER_CHROME_SCREEN", "1")
os.environ.setdefault("PG_SOURCE_FURNITURE_CHROME", "1")

from src.polaris_graph.generator.weighted_enrichment import (  # noqa: E402
    is_render_chrome_or_unrenderable as chrome,
)

fails: list[str] = []


def check(name: str, cond: bool) -> None:
    print(("PASS " if cond else "FAIL ") + name)
    if not cond:
        fails.append(name)


# ── CLASS 2/5: chrome furniture the wave-1 vocab missed — MUST DROP ────────────
MUST_DROP_CHROME = {
    "chartdump_figure6": (
        "7 of 52 Economic Impact Workforce Impact Organizational Impact Productivity Growth "
        "GDP Contribution Innovation Rate Skill Development Employment Quality Wage Premiums "
        "Operational Efficiency Competitive Advantage Innovation Capacity "
        "+25% +1.5% +40% 80% +35% +20% +45% +60% +50% Figure 6"
    ),
    "doctitle_recital": 'The document is titled "The Impact and Effectiveness of Innovation Policy: Evidence."',
    "contact_phone": "Jan Hatzius at Goldman Sachs lists a contact phone number of +1 212 902-0394.",
    "navcta_view_details": "view details",
    "publisher_boiler": "The World Bank indicates that books in this series are published to communicate the results of the Bank's work.",
}
for name, s in MUST_DROP_CHROME.items():
    check("drop_chrome::" + name, chrome(s, require_sentence_form=True) is True)

# ── real GenAI-labor FINDINGS (verbatim box2) — MUST SURVIVE (over-drop guard) ─
MUST_KEEP = {
    "acemoglu_robot_wage": "One more robot per thousand workers reduces the employment-to-population ratio by 0.2 percentage points and wages by 0.42%.",
    "eloundou_exposure": "Roughly 1.8% of jobs could have over half their tasks affected by LLMs with simple interfaces and general training.",
    "gdp_projection": "AI will increase productivity and GDP by 1.5% by 2035, nearly 3% by 2055, and 3.7% by 2075.",
    "sme_no_effect": "The vast majority of SMEs (83%) report that generative AI has had no effect on overall staffing levels.",
    "accenture_developers": "Across three experiments and 4,867 developers, the analysis reports a 26.08% increase in completed tasks among developers using the AI tool.",
    # Fable gate (wave-2) byline-trap guards: real prose that CONTAINS the tightened phrases must SURVIVE.
    "byline_is_titled_in_prose": "The Brynjolfsson study, which is titled 'Generative AI at Work,' found a 14% average productivity gain [6].",
    "byline_learn_more_in_prose": "This complementarity allows workers to learn more about the mechanism of task substitution and raise output.",
    # Codex gate (wave-2) adversarial over-drop cases — each carries a finding SIGNAL, must SURVIVE.
    "codex_study_titled_found": "A study titled 'Generative AI at Work' found a 14% productivity gain among support agents [6].",
    "codex_compact_percent_list": "The model projects GDP gains of 1.5%, 3%, and 3.7% across the three horizons [81].",
    "codex_signed_stat_estimate": "The estimated coefficient was +0.123 (0.045), significant at the 1% level [34].",
    "codex_two_link_finding": "The finding by [Autor](https://mit.edu/a) is corroborated by [Acemoglu](https://mit.edu/b), who reports a 0.42% wage decline [3].",
    # Codex iter-2 continuing-P1: a signed statistic with a broad context word must SURVIVE (phone leg
    # is now format-tight + under the finding-signal guard).
    "codex_recruitment_signed_stat": "Recruitment efforts increased employment by +0.123 (0.045) in the treated group [34].",
}
for name, s in MUST_KEEP.items():
    check("keep_finding::" + name, chrome(s, require_sentence_form=True) is False)

# ── DEPTH (wave-2 whole-basket full-text grounding) — real analyst-synthesis code ─────────────
from src.polaris_graph.generator.analyst_synthesis_deviation_check import (  # noqa: E402
    _resolve_span_for_evidence_id as _rspan,
    _span_grounds_sentence as _grounds,
)
# T2 (the real over-drop): a grounded number lives in the source STATEMENT, not the narrow quote slice.
# Whole-basket full_text must recover it so the synthesis sentence GROUNDS (was wrongly dropped in box2).
_row_stmt = [{"evidence_id": "1",
              "direct_quote": "Generative AI at Work studies a customer-support deployment",
              "statement": "support agents increased productivity by 14 percent on resolutions"}]
check("depth_t2_statement_recovers_number",
      _grounds("support agents gained 14 percent in productivity [1]",
               _rspan("1", _row_stmt, full_text=True)) is True)
# T3 snippet/title LAUNDERING (Codex+Fable depth-gate P1): a number that appears ONLY in retrieval
# metadata (title/snippet) — NOT in the trusted body (direct_quote/statement) — must NEVER ground a
# fabricated sentence. Proves title/snippet are excluded from full_text.
_row_meta = [{"evidence_id": "1",
              "direct_quote": "the study examines task exposure",
              "statement": "exposure varies by occupation",
              "title": "Cited by 42",
              "snippet": "5 min read 2023 42 results"}]
check("depth_t3_snippet_number_does_not_launder",
      _grounds("AI affects 42% of jobs by 2023 [1]",
               _rspan("1", _row_meta, full_text=True)) is False)

print("\nRESULT: " + ("ALL_PASS" if not fails else ("FAILS=" + ",".join(fails))))
sys.exit(1 if fails else 0)
