"""Helper: write 7 SourceAnalysisBatch responses in one shot."""
import json, os, sys
sys.stdout.reconfigure(encoding="utf-8", errors="replace")


def fact(st, q, p="Scientific", r=0.75, c="statistic"):
    return {"statement": st, "direct_quote": q, "fact_category": c,
            "relevance_score": r, "confidence": 0.85, "perspective": p, "entities": []}


def ana(url, title, stype, quality, year, venue, doi, facts, summary):
    return {"source_url": url, "source_title": title, "source_type": stype,
            "source_quality": quality, "overall_relevance": 0.8 if quality > 0.5 else 0.3,
            "year": year, "authors": [], "venue": venue, "doi": doi,
            "atomic_facts": facts, "evidence_summary": summary}


specs = {
    "1b4a8b1dfe53": [
        ana("https://www.semanticscholar.org/paper/c3b3425ebc4e1c18e1e951daa9988056869de3b4",
            "Does 4-week Ramadan IF affect cardiometabolic risk factors? SR+MA",
            "journal_article", 0.7, 2024, "Semantic Scholar", "", [
                fact("RDIF over 29-30 days evaluated for cardiometabolic risk factors in healthy adults",
                     "evaluate the effects of Ramadan diurnal intermittent fasting (RDIF; 29-30 days) on cardiometabolic risk factors (CMRF) in healthy adults",
                     "Regional", 0.88),
                fact("Ten scientific databases searched", "Ten scientific databases (EBSCOhost, CINAHL, Cochrane, EMBASE, PubMed/MEDLINE, Scopus",
                     "Methodological", 0.6),
                fact("Meta-regression examined cofactors", "examine the effect of various cofactors on the outcomes using sub-group meta-regression",
                     "Methodological", 0.65),
            ], "Ramadan diurnal IF SR+MA on CMRF in healthy adult Muslims."),
        ana("https://pmc.ncbi.nlm.nih.gov/articles/PMC10474717/",
            "SR+MA of long-term effects of behavioural physical activity interventions (OFF-TOPIC)",
            "journal_article", 0.4, 2023, "BMC Public Health", "10.1186/s12889-023-16541-7", [
                fact("OFF-TOPIC physical activity SR not IF",
                     "assess the long-term (at least 24 month) effectiveness of behavioural interventions on objectively measured physical activity",
                     "Methodological", 0.1),
            ], "OFF-TOPIC physical activity SR."),
    ],
    "3257df816834": [
        ana("https://www.semanticscholar.org/paper/bea6872d9e84f4cab8cb8dfc1a63eef699edcd7a",
            "Impact of IF on body composition and cardiometabolic outcomes",
            "journal_article", 0.75, 2024, "Semantic Scholar", "", [
                fact("Study examines IF effect on body composition and cardiometabolic outcomes",
                     "The impact of intermittent fasting on body composition and cardiometabolic outcomes", "Scientific", 0.85),
                fact("SR+MA design applied to IF body composition evidence",
                     "impact of intermittent fasting on body composition and cardiometabolic outcomes", "Methodological", 0.7),
            ], "IF SR+MA on body composition and cardiometabolic outcomes."),
        ana("https://www.semanticscholar.org/paper/580ad81a341a94cadaa96fbae1dd73b4758eedf3",
            "Efficacy of IF on improving liver function",
            "journal_article", 0.7, 2024, "Semantic Scholar", "", [
                fact("IF effect on liver function examined",
                     "Efficacy of intermittent fasting on improving liver function in individuals with",
                     "Scientific", 0.75),
            ], "IF liver function study."),
    ],
    "5e0a55c1a670": [
        ana("https://nutritionj.biomedcentral.com/counter/pdf/10.1186/s12937-023-00909-x",
            "Combined vs independent effects of exercise and IF: SR+MA",
            "journal_article", 0.65, 2023, "Nutrition Journal", "10.1186/s12937-023-00909-x", [
                fact("Exercise training and IF each effective for body composition and cardiometabolic health",
                     "Exercise training (Ex) and intermittent fasting (IF) are effective for improving body composition and cardiometabolic health",
                     "Scientific", 0.85),
                fact("Combined exercise+IF additive/synergistic effects not well established",
                     "whether combining Ex and IF induces additive or synergistic effects is less well established",
                     "Methodological", 0.78),
            ], "SR+MA of combined vs independent exercise+IF."),
        ana("https://www.frontiersin.org/articles/10.3389/fnut.2024.1362731/pdf?isPublishedV2=False",
            "Effects of IF combined with exercise on serum leptin and adipokines",
            "journal_article", 0.65, 2024, "Frontiers in Nutrition", "", [
                fact("IF + exercise effects on leptin and adipokines examined",
                     "Effects of intermittent fasting combined with exercise on serum leptin and adipo",
                     "Scientific", 0.7),
            ], "IF+exercise biomarker study."),
    ],
    "8340339c332f": [
        ana("https://doi.org/10.1016/j.advnut.2023.10.003",
            "IER vs CER: SR+MA of 28 RCTs in healthy adults",
            "journal_article", 0.4, 2024, "Advances in Nutrition", "10.1016/j.advnut.2023.10.003", [
                fact("Meta-analysis compared three IER protocols with CER in healthy adults",
                     "This meta-analysis compared the effects of these IER diets with continuous energy restriction (CER) on anthropometrics and cardiometabolic risk markers in healthy adults",
                     "Scientific", 0.85),
                fact("28 trials: TRE k=7, ADF k=10, 5:2 k=11, 2-52 weeks",
                     "Twenty-eight trials were identified that studied TRE (k = 7), ADF (k = 10), or the 5:2 diet (k = 11) for 2-52 wk",
                     "Scientific", 0.88),
            ], "2024 SR+MA of IER vs CER (28 RCTs)."),
        ana("https://www.semanticscholar.org/paper/29b1d5aa1379d92afa1a0b8edc9b17f05d02a9fb",
            "IF strategies: SR and network meta-analysis",
            "journal_article", 0.75, 2024, "Semantic Scholar", "", [
                fact("Network meta-analysis comparing IF with CER and ad-libitum",
                     "assess the effect of intermittent fasting diets, with continuous energy restriction or unrestricted (ad-libitum) diets on intermediate cardiometabolic outcomes",
                     "Methodological", 0.9),
                fact("Database search to 14 November 2024",
                     "Medline, Embase, and central databases from inception to 14 November 2024",
                     "Methodological", 0.55),
            ], "2024 IF network meta-analysis."),
    ],
    "bfb2610ec16d": [
        ana("https://www.frontiersin.org/articles/10.3389/fnut.2023.1090792/pdf",
            "IER vs CER on cardiometabolic health: meta-analysis",
            "journal_article", 0.75, 2023, "Frontiers in Nutrition", "", [
                fact("IER vs CER compared on cardiometabolic outcomes",
                     "Intermittent energy restriction vs. continuous energy restriction on cardiometab",
                     "Scientific", 0.85),
                fact("Meta-analytic design applied",
                     "Intermittent energy restriction vs. continuous energy restriction",
                     "Methodological", 0.7),
            ], "Frontiers 2023 IER vs CER meta-analysis."),
    ],
    "c5b80cd74fcb": [
        ana("https://www.frontiersin.org/journals/pharmacology/articles/10.3389/fphar.2024.1428601/pdf",
            "Time-restricted eating: mechanisms review",
            "journal_article", 0.7, 2024, "Frontiers in Pharmacology", "", [
                fact("TRE circadian mechanisms review",
                     "Time-restricted eating, the clock ticking behind the scenes",
                     "Emerging_Trends", 0.7),
            ], "TRE mechanistic review 2024."),
        ana("https://www.ncbi.nlm.nih.gov/pmc/articles/PMC9343887",
            "IER for weight loss: SR of cardiometabolic outcomes",
            "journal_article", 0.8, 2022, "PMC", "", [
                fact("SR of IER weight loss and cardiometabolic outcomes",
                     "Intermittent Energy Restriction for Weight Loss: A Systematic Review of Cardiome",
                     "Scientific", 0.85),
            ], "IER SR on weight loss + cardiometabolic outcomes."),
    ],
    "d269c6e2c520": [
        ana("https://translational-medicine.biomedcentral.com/track/pdf/10.1186/s12967-018-1748-4",
            "IER vs CER (Cioffi 2018)",
            "journal_article", 0.9, 2018, "Journal of Translational Medicine", "10.1186/s12967-018-1748-4", [
                fact("Cioffi 2018 meta-analysis of IER vs CER",
                     "summarized the most recent evidence on the efficacy of intermittent energy restriction (IER) versus continuous energy restriction on weight-loss, body composition, blood pressure and other cardiometabolic risk factors",
                     "Scientific", 0.95),
                fact("Cioffi 2018 WMD -0.61 kg no IER benefit over CER",
                     "no significant benefit of IER over CER on weight loss (weighted mean difference (WMD) -0.61 kg, 95% CI -1.70 to 0.47; P = 0.27)",
                     "Scientific", 0.96),
                fact("Cioffi 2018 fasting insulin lower in IER WMD -0.89 uU/mL",
                     "fasting insulin levels were significantly lower in the IER group (WMD = -0.89 \u03bcU/mL, 95% CI -1.56 \u03bcU/mL to -0.22\u03bcU/mL; P = 0.009; I2 = 0%)",
                     "Scientific", 0.92),
            ], "Cioffi 2018 foundational IER vs CER meta-analysis."),
        ana("https://www.ncbi.nlm.nih.gov/pmc/articles/PMC6884959",
            "IF for CVD prevention (Cochrane Review Protocol)",
            "protocol", 0.8, 2019, "Cochrane Database of Systematic Reviews", "", [
                fact("ADF defined as 24h complete fasting alternating with 24h ad libitum",
                     "cyclical feeding pattern that entails complete fasting (consumption of no calories) for a period of 24 hours, followed by ad libitum feeding for 24 hours",
                     "Methodological", 0.85),
                fact("TRF defined as >=12h daily complete fasting",
                     "complete fasting (consumption of no calories) for at least 12 hours per day with ad libitum feeding for the rest of the day",
                     "Methodological", 0.82),
                fact("Primary outcomes: CV mortality, MI, heart failure",
                     "Primary outcomes: CV mortality, Myocardial infarction (MI), Heart failure",
                     "Methodological", 0.8),
            ], "Cochrane protocol for IF CVD prevention."),
    ],
}


for rid, analyses in specs.items():
    resp = {
        "content": json.dumps({"analyses": analyses}, ensure_ascii=False),
        "reasoning": "",
        "input_tokens": 3000,
        "output_tokens": 800,
    }
    path = f"loopback/responses/resp_{rid}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(resp, f, indent=2, ensure_ascii=False)
    print(f"wrote {path}")
