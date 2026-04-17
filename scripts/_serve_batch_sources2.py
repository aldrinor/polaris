"""Round 2: 4 more SourceAnalysisBatch responses."""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def fact(st, q, p="Scientific", r=0.7, c="causal_link"):
    return {"statement": st, "direct_quote": q, "fact_category": c,
            "relevance_score": r, "confidence": 0.8, "perspective": p, "entities": []}


def ana(url, title, stype, qual, year, venue, doi, facts, summary):
    return {"source_url": url, "source_title": title, "source_type": stype,
            "source_quality": qual, "overall_relevance": 0.75 if qual > 0.55 else 0.4,
            "year": year, "authors": [], "venue": venue, "doi": doi,
            "atomic_facts": facts, "evidence_summary": summary}


specs = {
    "1e9bf5334122": [
        ana("https://www.mayoclinic.org/healthy-lifestyle/nutrition-and-healthy-eating/expert-answers/intermittent-fasting/faq-20441303",
            "Mayo Clinic IF FAQ", "web", 0.35, 2024, "Mayo Clinic", "", [
                fact("Mayo Clinic consumer FAQ on IF benefits", "Intermittent fasting: What are the benefits?", "Public_Health", 0.4),
            ], "Mayo Clinic consumer FAQ — mostly cookie banner content fetched."),
        ana("https://hsph.harvard.edu/news/the-health-benefits-of-intermittent-fasting/",
            "Harvard HSPH: health benefits of IF", "web", 0.55, 2024, "Harvard School of Public Health", "", [
                fact("Harvard HSPH coverage of IF health benefits", "The health benefits of intermittent fasting", "Public_Health", 0.55),
            ], "Harvard public-health news article on IF."),
    ],
    "28be5fde06f8": [
        ana("https://today.uic.edu/benefits-intermittent-fasting-research/",
            "UIC coverage: IF is safe and effective", "web", 0.5, 2024, "UIC Today", "", [
                fact("UIC research coverage stating IF is safe and effective",
                     "Research shows that intermittent fasting is safe and effecti", "Public_Health", 0.55),
            ], "UIC institutional coverage of IF research."),
        ana("https://pmc.ncbi.nlm.nih.gov/articles/PMC10945168/",
            "IF and health outcomes: umbrella review", "journal_article", 0.9, 2024, "PMC", "", [
                fact("Umbrella review of 23 meta-analyses with 351 associations across 34 health outcomes",
                     "A total of 351 associations from 23 meta-analyses with 34 health outcomes were included", "Scientific", 0.95),
                fact("91% of meta-analyses retained (21/23)",
                     "Twenty-one (91%) meta-analyses with 346 associatio", "Methodological", 0.85),
                fact("Outcomes categorized: anthropometric 155, lipid 83, glycemic 57, circulatory 41",
                     "anthropometric measures (n = 155), lipid profiles (n = 83), glycemic profiles (n = 57), circulatory system index (n = 41)", "Scientific", 0.9),
                fact("AMSTAR and GRADE quality tools applied; PROSPERO CRD42023382004",
                     "A Measurement Tool to Assess Systematic Reviews (AMSTAR), and the certainty of evidence was assessed using the Grading of Recommendations, Assessment, Development, and Evaluations (GRADE) system", "Methodological", 0.88),
            ], "2024 umbrella review of IF meta-analyses — top-of-pyramid evidence."),
    ],
    "827b00f93787": [
        ana("https://pmc.ncbi.nlm.nih.gov/articles/PMC9946909/",
            "Beneficial effects of IF: narrative review", "journal_article", 0.75, 2023, "PMC", "", [
                fact("IF has beneficial effects equivalent to caloric restriction",
                     "intermittent fasting has beneficial effects equivalent to those of caloric restric", "Scientific", 0.85),
                fact("Caloric restriction difficult to maintain long-term; IF easier alternative",
                     "Caloric restriction is a popular approach to treat obesity and its associated chronic illnesses but is difficult to maintain for a long time", "Public_Health", 0.75),
            ], "Narrative review positioning IF as equivalent-to-CR with better adherence."),
        ana("https://www.massgeneralbrigham.org/en/about/newsroom/articles/pros-and-cons-of-intermittent-fasting",
            "Mass General Brigham: Pros and Cons of IF", "web", 0.55, 2024, "Mass General Brigham", "", [
                fact("IF positioned as non-miraculous weight strategy with research-informed pros and cons",
                     "It's not a magic cure for losing weight, but the research on intermittent fasting", "Public_Health", 0.6),
            ], "Academic medical center public coverage of IF."),
    ],
    "ba25e6e3bed7": [
        ana("https://www.hopkinsmedicine.org/health/expert-qa/intermittent-fasting-what-is-it",
            "Hopkins Medicine: IF What Is It", "web", 0.55, 2024, "Hopkins Medicine", "", [
                fact("Hopkins clinical expert-Q&A describing IF mechanisms",
                     "Intermittent Fasting: What Is It, And How Does It Work?", "Public_Health", 0.55),
            ], "Hopkins Medicine public clinical coverage."),
        ana("https://www.npjournal.org/article/S1555-4155(23)00395-1/fulltext",
            "IF: Approaches, Benefits, and [Risks]", "journal_article", 0.65, 2023, "The Journal for Nurse Practitioners", "", [
                fact("Review of IF approaches, benefits, and risks for practitioner audience",
                     "Intermittent Fasting: Exploring Approaches, Benefits, and", "Scientific", 0.7),
            ], "Practitioner-oriented IF review."),
    ],
}


for rid, analyses in specs.items():
    resp = {
        "content": json.dumps({"analyses": analyses}, ensure_ascii=False),
        "reasoning": "", "input_tokens": 3000, "output_tokens": 700,
    }
    with open(f"loopback/responses/resp_{rid}.json", "w", encoding="utf-8") as f:
        json.dump(resp, f, indent=2, ensure_ascii=False)
    print(f"wrote {rid}")
