"""
Compose-stage validation using OpenAI as substitute for OpenRouter (which is 402 blocked).

PURPOSE: validate the LLM compose path of `compose_from_wiki()` end-to-end.
This is the ONE pipeline stage we have not exercised on real LLM output.

WHAT THIS PROVES:
- The wiki structure feeds correctly into the composer
- The LLM honors [REF:N] citations with the 5-lens scaffold
- _scrub_cot() runs cleanly on real model output
- [REF:N] -> [N] resolution works on real prose
- Final report assembles with bibliography
- Quality gate evaluates correctly

WHAT THIS DOES NOT PROVE:
- Final G-Eval score (model is gpt-4o-mini, not Qwen 3.5 Plus)
- Real LLM evidence extraction quality from raw markdown
- Production timeout behavior at 600-evidence scale

This is a mechanical-pipeline validator, not a quality benchmark.
"""
import asyncio
import os
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv
load_dotenv()

os.environ["PG_WIKI_ENABLED"] = "1"
os.environ["PG_WIKI_5LENS"] = "1"

import logging
logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger(__name__)


# ── OpenAI shim that mimics OpenRouterClient.generate() ──────────────

@dataclass
class _ShimResponse:
    content: str
    reasoning: Optional[str] = None
    input_tokens: int = 0
    output_tokens: int = 0
    reasoning_tokens: int = 0
    model: str = "gpt-4o-mini"
    duration_ms: float = 0
    raw_response: Optional[dict] = None


class OpenAIShimClient:
    """Minimal OpenAI client with the OpenRouterClient.generate() interface.

    Defaults to gpt-5 (the strongest available reasoning model). gpt-5 quirks:
    - Uses `max_completion_tokens`, NOT `max_tokens`
    - Only supports default temperature=1.0 (rejects custom temp)
    - Burns reasoning tokens BEFORE producing content — needs generous budget
    """

    # Models that share gpt-5's reasoning quirks (flagged for param handling)
    _REASONING_MODELS = {"gpt-5", "o3", "o3-mini", "o1", "o1-preview", "o1-mini"}

    def __init__(self, model: str = "gpt-5"):
        import httpx
        self.model = model
        self.is_reasoning = any(model.startswith(m) for m in self._REASONING_MODELS)
        self._client = httpx.AsyncClient(
            base_url="https://api.openai.com/v1",
            headers={
                "Authorization": f"Bearer {os.getenv('OPENAI_API_KEY', '')}",
                "Content-Type": "application/json",
            },
            timeout=httpx.Timeout(300.0, connect=30.0),
        )
        self.calls = 0
        self.total_input = 0
        self.total_output = 0
        self.total_reasoning = 0

    async def close(self):
        await self._client.aclose()

    async def generate(
        self,
        prompt: str,
        system: str = "",
        max_tokens: int = 4096,
        temperature: float = 0.3,
        timeout: Optional[float] = None,
        **kwargs,
    ) -> _ShimResponse:
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})

        body: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
        }

        if self.is_reasoning:
            # gpt-5/o3 burn reasoning tokens before content. Triple the budget
            # so reasoning doesn't starve the prose output.
            body["max_completion_tokens"] = max(max_tokens * 3, 8000)
            # No temperature — gpt-5 only accepts default 1.0
        else:
            body["max_tokens"] = max_tokens
            body["temperature"] = temperature

        start = time.monotonic()
        resp = await self._client.post("/chat/completions", json=body)
        resp.raise_for_status()
        data = resp.json()
        duration_ms = (time.monotonic() - start) * 1000

        content = data["choices"][0]["message"]["content"] or ""
        usage = data.get("usage", {}) or {}
        in_tok = usage.get("prompt_tokens", 0)
        out_tok = usage.get("completion_tokens", 0)
        rsn_tok = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens", 0)

        self.calls += 1
        self.total_input += in_tok
        self.total_output += out_tok
        self.total_reasoning += rsn_tok

        return _ShimResponse(
            content=content,
            input_tokens=in_tok,
            output_tokens=out_tok,
            reasoning_tokens=rsn_tok,
            model=self.model,
            duration_ms=duration_ms,
        )


# ── Build a small validated wiki slice ───────────────────────────────

def _make_evidence(url: str, title: str, statement: str, quote: str,
                   tier: str = "GOLD", auth: float = 0.85,
                   year: int = 2024) -> dict:
    import hashlib
    eid = "ev_" + hashlib.md5(f"{url}_{statement}".encode()).hexdigest()[:12]
    return {
        "evidence_id": eid,
        "source_url": url,
        "source_title": title,
        "source_type": "academic",
        "statement": statement,
        "direct_quote": quote,
        "quality_tier": tier,
        "relevance_score": 0.85,
        "sig_authority": auth,
        "year": year,
        "doi": "",
    }


def _seed_evidence() -> list[dict]:
    """Realistic evidence covering 3 sections — uses real-shaped data."""
    return [
        # Section 1: Weight loss
        _make_evidence(
            "https://www.nejm.org/doi/full/10.1056/NEJMoa2114833",
            "Effect of Time-Restricted Eating on Weight Loss (NEJM 2022)",
            "Time-restricted eating produced 8.0% weight loss vs 6.3% with caloric restriction over 12 months (p=0.21).",
            "After 12 months, the time-restricted-eating group had lost 8.0% of body weight versus 6.3% in the caloric-restriction group; the difference was not statistically significant (P=0.21).",
        ),
        _make_evidence(
            "https://jamanetwork.com/journals/jamainternalmedicine/fullarticle/2784137",
            "Effects of TRE in Adults with Obesity (JAMA IM 2022)",
            "16:8 time-restricted eating reduced body weight by 3.4% (95% CI -4.5 to -2.3) at 12 weeks vs 1.8% control.",
            "TRE reduced body weight by 3.4% (95% CI, -4.5% to -2.3%) compared with 1.8% in the control group at 12 weeks.",
        ),
        _make_evidence(
            "https://academic.oup.com/ajcn/article/115/1/154/6447958",
            "Alternate Day Fasting Meta-analysis (AJCN 2022)",
            "Alternate-day fasting reduced body weight by 4.5 kg (95% CI -5.6 to -3.4) over 4-24 weeks across 9 RCTs.",
            "Pooled analysis of 9 RCTs (n=482) showed alternate-day fasting reduced body weight by 4.5 kg (95% CI -5.6 to -3.4) compared with usual diet.",
        ),
        _make_evidence(
            "https://www.thelancet.com/journals/landia/article/PIIS2213-8587(22)00063-9",
            "5:2 Diet vs Continuous Restriction RCT (Lancet D&E 2022)",
            "5:2 diet achieved 4.7 kg weight loss vs 3.5 kg with continuous restriction at 6 months (MD 1.2 kg, p=0.04).",
            "At 6 months, the 5:2 group lost 4.7 kg compared with 3.5 kg in the continuous-restriction group (mean difference 1.2 kg, p=0.04).",
        ),
        _make_evidence(
            "https://www.bmj.com/content/376/bmj-2021-068905",
            "Long-term Adherence to IF Protocols (BMJ 2022)",
            "Drop-out rates for intermittent fasting trials averaged 38% vs 24% for caloric restriction over 12 months.",
            "Across 27 trials, drop-out rates for intermittent fasting averaged 38% (range 12-52%) compared with 24% for caloric restriction over 12 months.",
            tier="SILVER",
        ),
        # Section 2: Cardiovascular
        _make_evidence(
            "https://www.ahajournals.org/doi/10.1161/CIRCULATIONAHA.123.066330",
            "TRE and Cardiovascular Mortality (AHA 2024)",
            "8-hour eating window associated with 91% increased cardiovascular mortality risk (HR 1.91, 95% CI 1.20-3.03).",
            "Compared with eating across 12-16 hours, an 8-hour eating window was associated with a 91% higher risk of cardiovascular mortality (HR 1.91, 95% CI 1.20-3.03).",
        ),
        _make_evidence(
            "https://www.acpjournals.org/doi/10.7326/M21-3261",
            "TRE and Lipid Profile RCT (Annals 2022)",
            "Time-restricted eating reduced LDL-C by 11.2 mg/dL (95% CI -18.4 to -4.0) and triglycerides by 22 mg/dL.",
            "After 8 weeks, TRE reduced LDL-cholesterol by 11.2 mg/dL (95% CI -18.4 to -4.0) and triglycerides by 22 mg/dL (95% CI -38 to -6).",
        ),
        _make_evidence(
            "https://journals.lww.com/co-cardiology/Abstract/2023/01000/intermittent_fasting_and_blood_pressure.7.aspx",
            "IF Effects on Blood Pressure Review",
            "Intermittent fasting reduced systolic BP by 6.0 mmHg (95% CI -8.2 to -3.7) across 12 trials.",
            "Pooled analysis showed intermittent fasting reduced systolic BP by 6.0 mmHg (95% CI -8.2 to -3.7) and diastolic BP by 3.5 mmHg.",
        ),
        _make_evidence(
            "https://www.sciencedirect.com/science/article/pii/S0002916523063320",
            "TRE Effect on Apolipoprotein B (AJCN 2023)",
            "TRE reduced apoB by 7.4 mg/dL (95% CI -12.8 to -2.0) and improved insulin sensitivity by 24%.",
            "TRE significantly reduced apoB by 7.4 mg/dL (95% CI -12.8 to -2.0) and improved insulin sensitivity (HOMA-IR) by 24% versus controls.",
        ),
        # Section 3: Safety
        _make_evidence(
            "https://www.cell.com/cell-metabolism/fulltext/S1550-4131(22)00425-X",
            "TRE Lean Mass Preservation",
            "Time-restricted eating preserved 91% of lean mass vs 75% with caloric restriction during 12-week weight loss.",
            "Participants in the TRE group preserved 91% of lean mass compared with 75% in the caloric-restriction group during 12 weeks of weight loss.",
        ),
        _make_evidence(
            "https://www.nature.com/articles/s41591-022-01971-4",
            "IF and Eating Disorder Risk (Nature Med 2022)",
            "Intermittent fasting was associated with 1.5x higher binge-eating risk (OR 1.49, 95% CI 1.21-1.84) in young adults.",
            "In a cohort of 2762 young adults, intermittent fasting was associated with higher binge-eating disorder risk (adjusted OR 1.49, 95% CI 1.21-1.84).",
        ),
        _make_evidence(
            "https://pubmed.ncbi.nlm.nih.gov/35635175/",
            "Adverse Events in IF Trials Meta-analysis",
            "Headache (12%), fatigue (8%), and irritability (6%) were the most common adverse events in IF trials.",
            "Across 18 trials reporting adverse events, the most common were headache (12% of participants), fatigue (8%), and irritability (6%).",
        ),
        _make_evidence(
            "https://jamanetwork.com/journals/jamanetworkopen/fullarticle/2790487",
            "Hypoglycemia Risk in Diabetic IF Patients",
            "T2D patients on insulin had 4.2x higher hypoglycemia risk during IF (RR 4.21, 95% CI 2.83-6.27).",
            "Type 2 diabetes patients on insulin therapy had a 4.21-fold higher hypoglycemia risk during intermittent fasting (RR 4.21, 95% CI 2.83-6.27).",
        ),
    ]


def _outline() -> list[dict]:
    return [
        {"section_id": "s01", "title": "Weight Loss and Body Composition",
         "description": "Effect of intermittent fasting protocols on body weight, fat mass, and adherence."},
        {"section_id": "s02", "title": "Cardiovascular and Lipid Health",
         "description": "Cardiovascular outcomes including lipid profile, blood pressure, and mortality risk."},
        {"section_id": "s03", "title": "Safety Profile and Adverse Effects",
         "description": "Adverse events, contraindications, and risks across populations."},
    ]


# ── Main validation ──────────────────────────────────────────────────

async def main():
    if not os.getenv("OPENAI_API_KEY"):
        print("ERROR: OPENAI_API_KEY not set in .env")
        return 1

    model_name = os.getenv("OPENAI_TEST_MODEL", "gpt-5")
    print("=" * 70)
    print(f"WIKI COMPOSE VALIDATION via OpenAI shim ({model_name})")
    print("=" * 70)

    # ── Stage 1: Build wiki from seed evidence ───────────────────────
    print("\n[1/4] Building wiki from 13 seed evidence pieces")
    from src.polaris_graph.wiki.wiki_builder import build_wiki

    evidence = _seed_evidence()
    outline = _outline()
    print(f"  Evidence: {len(evidence)} pieces")
    print(f"  Outline:  {len(outline)} sections")

    wiki = build_wiki(
        evidence=evidence, outline=outline,
        query="intermittent fasting health benefits and risks",
        vector_id="OPENAI_COMPOSE_VALIDATION",
    )

    total_claims = sum(len(c) for c in wiki.section_claims.values())
    print(f"  Built wiki: {total_claims} claims, {len(wiki.bibliography)} bib entries")
    for sid, claims in wiki.section_claims.items():
        sec_title = next((s["title"] for s in outline if s["section_id"] == sid), sid)
        print(f"    {sid}: {len(claims):2d} claims | {sec_title[:45]}")

    if total_claims == 0:
        print("\nFAIL: wiki has no claims — cannot proceed")
        return 1

    # ── Stage 2: Compose with OpenAI shim ────────────────────────────
    print(f"\n[2/4] Composing report via OpenAI shim ({model_name})")
    from src.polaris_graph.wiki.wiki_composer import compose_from_wiki

    client = OpenAIShimClient(model=model_name)
    start = time.monotonic()
    try:
        result = await compose_from_wiki(
            client=client,  # type: ignore[arg-type]
            wiki_result=wiki,
            query="intermittent fasting health benefits and risks",
            outline=outline,
        )
    except Exception as exc:
        print(f"\nFAIL: compose_from_wiki raised: {type(exc).__name__}: {exc}")
        await client.close()
        return 1

    elapsed = time.monotonic() - start
    await client.close()

    # ── Stage 3: Inspect output ─────────────────────────────────────
    print(f"\n[3/4] Compose complete in {elapsed:.0f}s ({client.calls} LLM calls)")
    print(f"  Status: {result['status']}")
    print(f"  Quality gate: {result['quality_gate_result']}")

    sections = result["sections"]
    qm = result["quality_metrics"]
    print(f"\n  Sections composed: {len(sections)}/{len(outline)}")
    print(f"  Total words:       {qm['total_words']}")
    print(f"  Total citations:   {qm['total_citations']}")
    print(f"  Unique sources:    {qm['unique_sources']}")
    print(f"  Zero-cite sec:     {qm['zero_cite_sections']}")
    print(f"  Avg cite/sec:      {qm['avg_citations_per_section']:.1f}")

    for s in sections:
        print(f"    {s['section_id']}: {s['word_count']:4d} words, "
              f"{len(s['citation_ids']):2d} unique cites — {s['title'][:40]}")

    # ── Stage 4: Validation checks ──────────────────────────────────
    print(f"\n[4/4] Validation checks")
    checks = []

    # V1: All sections produced content
    v1 = len(sections) == len(outline)
    checks.append(("V1 all sections composed",
                   v1, f"{len(sections)}/{len(outline)}"))

    # V2: No CoT leakage (look for telltale phrases)
    cot_phrases = ["let me", "i need to", "first, i'll", "thinking about",
                   "let's start", "i should", "i will write", "okay,",
                   "as an ai", "i'll write", "here's a"]
    cot_hits = []
    for s in sections:
        low = s["content"].lower()
        for ph in cot_phrases:
            if ph in low:
                cot_hits.append((s["section_id"], ph))
    v2 = len(cot_hits) == 0
    checks.append(("V2 no CoT leakage", v2,
                   f"{len(cot_hits)} hits" if cot_hits else "clean"))

    # V3: All citation prefixes resolved → bare [N].
    # The model intermittently emits [REF:N], [CITE:N], or [Ref:N].
    leftover_pattern = re.compile(r"\[(?:REF|CITE|Ref|Cite|ref|cite):\d+\]")
    leftover_refs = []
    for s in sections:
        if leftover_pattern.search(s["content"]):
            leftover_refs.append(s["section_id"])
    # Also check the abstract via final_report
    abstract_leak = bool(leftover_pattern.search(result.get("final_report", "")))
    if abstract_leak:
        leftover_refs.append("abstract")
    v3 = len(leftover_refs) == 0
    checks.append(("V3 citation prefixes resolved",
                   v3, f"{len(leftover_refs)} leaks" if leftover_refs else "clean"))

    # V3b: No literal [N] placeholder (model writing template literal as citation)
    placeholder_hits = []
    if re.search(r"\[N\]", result.get("final_report", "")):
        placeholder_hits.append("final_report")
    for s in sections:
        if re.search(r"\[N\]", s["content"]):
            placeholder_hits.append(s["section_id"])
    v3b = len(placeholder_hits) == 0
    checks.append(("V3b no literal [N] placeholder",
                   v3b, f"{len(placeholder_hits)} leaks" if placeholder_hits else "clean"))

    # V4: Citation density relative to the available source pool.
    # Absolute ceiling = (unique_sources / total_words) * 100. With only 13
    # seed sources and ~2000 words, the ceiling is ~0.65/100w. We require
    # the model to hit at least 80% of that ceiling, i.e. it must use most
    # of the available sources rather than recycling a few. At production
    # scale (200 sources / 10K words) this becomes 0.8 * 2.0 = 1.6/100w.
    avg_density = (qm["total_citations"] / qm["total_words"] * 100) if qm["total_words"] else 0
    ceiling = (qm["unique_sources"] / qm["total_words"] * 100) if qm["total_words"] else 0
    target_density = ceiling * 0.8
    v4 = avg_density >= target_density
    checks.append(("V4 citation density vs pool",
                   v4, f"{avg_density:.2f}/100w vs target {target_density:.2f} "
                        f"(ceiling {ceiling:.2f})"))

    # V5: Every numbered citation in body exists in bibliography
    bib_refs = set(b["ref_num"] for b in wiki.bibliography)
    orphans = []
    for s in sections:
        nums = set(int(n) for n in re.findall(r"\[(\d+)\]", s["content"]))
        for n in nums:
            if n not in bib_refs:
                orphans.append((s["section_id"], n))
    v5 = len(orphans) == 0
    checks.append(("V5 no orphan citations",
                   v5, f"{len(orphans)} orphans" if orphans else "0 orphans"))

    # V6: Final report assembled with bibliography
    final = result["final_report"]
    v6 = (
        "## References" in final
        and "[1]" in final
        and len(final) > 1000
    )
    checks.append(("V6 final report assembled",
                   v6, f"{len(final)} chars"))

    # V7: Word count gate (relaxed for 3-section test)
    v7 = qm["total_words"] >= 1500
    checks.append(("V7 word count >= 1500",
                   v7, f"{qm['total_words']} words"))

    # Print results
    print()
    all_pass = True
    for name, ok, detail in checks:
        marker = "PASS" if ok else "FAIL"
        if not ok:
            all_pass = False
        print(f"  [{marker}] {name:30s} {detail}")

    # ── Save artifacts ──────────────────────────────────────────────
    out_dir = Path("outputs/polaris_graph")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / "OPENAI_COMPOSE_VALIDATION.md"
    out_file.write_text(final, encoding="utf-8")
    print(f"\nReport saved: {out_file} ({len(final)} chars)")

    # ── Cost ────────────────────────────────────────────────────────
    # Pricing per million tokens (rough estimates)
    pricing = {
        "gpt-5":         (1.25, 10.00),
        "gpt-5-mini":    (0.25,  2.00),
        "o3":            (15.00, 60.00),
        "o3-mini":       ( 3.00, 12.00),
        "gpt-4o":        ( 2.50, 10.00),
        "gpt-4o-mini":   ( 0.15,  0.60),
        "gpt-4-turbo":   (10.00, 30.00),
    }
    in_p, out_p = pricing.get(model_name, (1.25, 10.00))
    cost = (client.total_input / 1_000_000 * in_p) + (client.total_output / 1_000_000 * out_p)
    print(f"\n  LLM calls:        {client.calls}")
    print(f"  Input tokens:     {client.total_input}")
    print(f"  Output tokens:    {client.total_output}")
    print(f"  Reasoning tokens: {client.total_reasoning}")
    print(f"  Cost:             ${cost:.4f}")

    print("\n" + "=" * 70)
    print("RESULT: " + ("ALL PASS" if all_pass else "SOME FAILED"))
    print("=" * 70)
    print("\nNOTE: this validates the MECHANICAL pipeline only.")
    print("Final G-Eval quality requires real Qwen 3.5 Plus run on full evidence.")

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
