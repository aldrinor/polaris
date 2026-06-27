"""Builds dedup_gold.json for the iwire014 DEDUP benchmark.

Reads the replay3 report.md, segments each '### section' body into CLAIM UNITS on
trailing-[N] citation boundaries, then applies a HAND-AUTHORED label table.

FAITHFULNESS LAW (binding): a unit is paraphrase_repeat (DROP-after-first) IFF
  (1) it restates the SAME claim already emitted earlier in the SAME section, AND
  (2) it carries the IDENTICAL citation set as that first emission, AND
  (3) it introduces NO new number/entity/fact.
Everything else is CONTENT (keep). When unsure -> keep. Varying-citation
restatements are KEEP (they are the negatives that catch a naive semantic dedup
that ignores citations).

Pure no-claim page-furniture (chrome / OCR fragments) is OUT OF SCOPE for the
dedup gold (that is the chrome fixture's job, iwire013/14). Sections that are
mostly broken OCR fragments are excluded; only claim-bearing sections are scored.

Cross-section dedup is OUT OF SCOPE: clustering is within-section only.
"""
import json
import re

REPORT = (
    r"C:/Users/msn/AppData/Local/Temp/claude/C--POLARIS/"
    r"dde5b4ec-b98b-4784-a4d2-3b7fd5d3e391/scratchpad/iwire014_replay3/report.md"
)
OUT = r"C:/POLARIS/outputs/audits/iwire014/benchmark/dedup_gold.json"

UNIT_RE = re.compile(r"(.*?)((?:\[\d+\])+)", re.DOTALL)
CITE_RE = re.compile(r"\[(\d+)\]")

# Sections included in the dedup gold (claim-bearing, parseable prose).
# Order = report order. Each maps unit-index -> (cluster_id, label, reason).
# label in {"keep","paraphrase_repeat"}.
#
# Sections in CURATED_SUBSET emit ONLY the labeled indices (the rest of the
# section's units are out of scope and skipped). Sections NOT in this set are
# FULLY covered: every parsed unit must carry a label or the build fails loudly.
CURATED_SUBSET = {"Corroborated Weighted Findings"}

LABELS = {
    "Task-based automation framework (Acemoglu & Restrepo, JEP 2019)": {
        # Pure narrative; every unit a distinct claim, all cite [1]. All keep.
        0: ("ar_framework", "keep", "First statement: framework for automation effects on labor demand."),
        1: ("ar_taskalloc", "keep", "Distinct claim: task allocation to capital and labor (task content of production)."),
        2: ("ar_displace_def", "keep", "Distinct claim: automation lets capital replace labor in tasks."),
        3: ("ar_displace_effect", "keep", "Distinct claim: this shifts task content against labor = displacement effect."),
        4: ("ar_newtasks", "keep", "Distinct claim: counterbalanced by creation of new tasks (comparative advantage)."),
        5: ("ar_reinstate_def", "keep", "Distinct claim: new tasks shift content toward labor = reinstatement effect."),
        6: ("ar_reinstate_raises", "keep", "Distinct claim: reinstatement always raises labor share and labor demand."),
        7: ("ar_contrast", "keep", "Distinct claim: contrast of displacement vs reinstatement direction."),
        8: ("ar_contrast2", "keep", "Distinct claim: displacement = replace in existing tasks vs reinstatement = new tasks."),
        9: ("ar_decomp", "keep", "Distinct claim: authors provide an empirical decomposition."),
        10: ("ar_decomp_slow", "keep", "Distinct claim: slower employment growth = acceleration in displacement effect."),
        11: ("ar_manuf", "keep", "Distinct new entity: acceleration pronounced in manufacturing."),
        12: ("ar_weak_reinstate", "keep", "Distinct claim: weaker reinstatement effect contributed to trends."),
        13: ("ar_weak_reinstate2", "keep", "Distinct framing tying empirical evidence to weaker reinstatement; new qualifier."),
        14: ("ar_productivity", "keep", "Distinct new factor: slower productivity growth accounts for slower employment growth."),
    },
    "Labor-market polarization and complementarity (Autor, JEP 2015)": {
        0: ("au_substitute", "keep", "First statement: Autor thesis that automation substitutes for labor."),
        1: ("au_complement", "keep", "Distinct claim: automation also complements labor, raises output and demand."),
        2: ("au_complement_channel", "keep", "Distinct claim: complementary channel via productivity gains expanding output."),
        3: ("au_interdependence", "keep", "Distinct claim: input interdependence propagates value across domains."),
        4: ("au_laborsupply", "keep", "Distinct claim: interaction with labor-supply adjustments; net effect not substitution alone."),
        5: ("au_synthesis", "keep", "Distinct claim: synthesis - automation simultaneously displaces and augments labor."),
    },
    "Empirical_Displacement": {
        # Two heavy paraphrase clusters with IDENTICAL [8][9][10], plus a
        # robot-density [4,5,6,7] cluster, plus distinct [4] claims.
        0: ("ed_idstrategy", "keep", "First statement: identification strategy (exposure to robots) cites [4]."),
        1: ("ed_population", "keep", "Distinct claim: population = US labor markets."),
        2: ("ed_robotdensity", "keep", "First statement of robot-density effect: 0.2 pp + 0.42% wages, cites [4,5,6,7]."),
        3: ("ed_outcome", "keep", "Distinct claim: outcome = employment and wages."),
        4: ("ed_method", "keep", "First statement of method: 702 occupations, Gaussian process classifier, cites [8,9,10]."),
        5: ("ed_exposure", "keep", "First statement of exposure measure = probability of computerisation, cites [8,9,10]."),
        6: ("ed_geo", "keep", "Distinct claim: geographic/industrial variation links robotics advances to local conditions."),
        7: ("ed_quantify", "keep", "Distinct claim: study quantifies robot-density vs employment/wage relationship."),
        8: ("ed_robotdensity", "paraphrase_repeat", "Restates robot-density employment effect (0.2 pp), SAME cites [4,5,6,7], no new number (drops wage)."),
        9: ("ed_metriccontrast", "keep", "Distinct claim: pp-vs-percentage metric contrast between employment and wage outcomes."),
        10: ("ed_negative", "keep", "Distinct claim AND different cite set [4,6,7]: effects consistently negative in direction."),
        11: ("ed_insum", "keep", "Summative distinct claim cites [4]: negative effects on employment AND wages."),
        12: ("ed_method", "paraphrase_repeat", "Restates method (702/Gaussian), SAME cites [8,9,10], no new number/entity."),
        13: ("ed_exposure", "paraphrase_repeat", "Restates exposure measure = probability of computerisation, SAME cites [8,9,10]."),
        14: ("ed_method", "paraphrase_repeat", "Restates method (702/Gaussian) verbatim variant, SAME cites [8,9,10]."),
        15: ("ed_exposure", "paraphrase_repeat", "Restates exposure measure, SAME cites [8,9,10]."),
        16: ("ed_exposure", "paraphrase_repeat", "Restates exposure measure (Gaussian classifier vs probability of computerisation), SAME cites [8,9,10]."),
        17: ("ed_method", "paraphrase_repeat", "Restates method (702/Gaussian), SAME cites [8,9,10]."),
        18: ("ed_exposure", "paraphrase_repeat", "Restates exposure measure, SAME cites [8,9,10]."),
        19: ("ed_method", "paraphrase_repeat", "Restates method (702/Gaussian), SAME cites [8,9,10]."),
        20: ("ed_exposure", "paraphrase_repeat", "Restates exposure measure, SAME cites [8,9,10]."),
        21: ("ed_exposure", "paraphrase_repeat", "Restates exposure measure, SAME cites [8,9,10]."),
        22: ("ed_exposure", "paraphrase_repeat", "Restates exposure measure (the bare canonical form), SAME cites [8,9,10]."),
        23: ("ed_idstrategy", "paraphrase_repeat", "Key Findings recap line restates unit 0 (identification strategy) verbatim, SAME cite [4]."),
        24: ("ed_metriccontrast_recap", "keep", "Tension recap restates metric-contrast claim but with DIFFERENT cite set [4,5,6] vs [4,5,6,7] -> keep."),
    },
    "Generative-AI productivity field evidence (Brynjolfsson et al., QJE 2025)": {
        # All cite [11]. Intervention/staggered/5,172 restated ~7x.
        0: ("ga_intervention", "keep", "First statement of intervention = generative AI conversational assistant, cites [11]."),
        1: ("ga_design", "keep", "First statement of design: staggered introduction, data from 5,172 customer-support agents, cites [11]."),
        2: ("ga_intervention", "paraphrase_repeat", "Restates intervention, SAME cite [11], no new number/entity."),
        3: ("ga_design", "paraphrase_repeat", "Restates staggered-introduction design with 5,172 agents, SAME cite [11], no new number."),
        4: ("ga_design", "paraphrase_repeat", "Restates staggered introduction among 5,172 agents, SAME cite [11]."),
        5: ("ga_intervention", "paraphrase_repeat", "Restates intervention rolled out via staggered introduction, SAME cite [11]."),
        6: ("ga_intervention", "paraphrase_repeat", "Restates intervention/staggered-introduction among customer-support agents, SAME cite [11]."),
        7: ("ga_design", "paraphrase_repeat", "Restates staggered introduction = study design, SAME cite [11]."),
    },
    "Foundational_Theory": {
        # Section-final recap lines; cross-section duplicates of Task-based section
        # are out of scope -> first occurrence WITHIN this section = keep.
        0: ("ft_framework", "keep", "First (and only) emission of this claim within this section; cross-section dedup out of scope."),
        1: ("ft_newtasks", "keep", "Distinct claim within section (counterbalanced by new tasks); first emission here."),
    },
    "Corroborated Weighted Findings": {
        # ONLY the Stable Diffusion / text-to-image cluster (units 310-316) is in
        # scope here. This section is 372 mostly-distinct units; the rest are
        # single-occurrence claims (keeps) or chrome and are EXCLUDED to keep the
        # gold curated. This cluster is the ONLY one in the report that exercises
        # ORDER-INDEPENDENT citation-SET equality: the same claim recurs with the
        # citation group shuffled ([156,157,158] -> [157,156,158] -> [158,156,157]).
        # Citation comparison MUST be set-based (order-independent), not as an
        # ordered list -- a candidate comparing ordered lists would wrongly KEEP
        # these repeats. Labeled via SET equality per the faithfulness law.
        310: ("cwf_controlnet_solo", "keep", "First ControlNet sentence, citation set {156} (distinct set from the glued variant)."),
        311: ("cwf_midjourney", "keep", "First statement: Midjourney/Stable-Diffusion-1.5 idea-frontier expansion, set {156,157,158}."),
        312: ("cwf_latentdiffusion", "keep", "First statement: latent-diffusion text-to-image algorithms (SD/Midjourney/DALL-E/Imagen/Flux), set {156,157,158}."),
        313: ("cwf_controlnet_glued", "keep", "First emission of the ControlNet+Midjourney glued-text claim with set {156,157,158} (differs from unit 310's set {156})."),
        314: ("cwf_latentdiffusion", "paraphrase_repeat", "Byte-identical restatement of unit 312; citation SET {157,156,158}=={156,157,158} (order shuffled); no new entity."),
        315: ("cwf_controlnet_glued", "paraphrase_repeat", "Byte-identical restatement of unit 313; citation SET {158,156,157}=={156,157,158} (order shuffled); no new entity."),
        316: ("cwf_latentdiffusion", "paraphrase_repeat", "Byte-identical restatement of unit 312; citation SET {158,156,157}=={156,157,158} (order shuffled); no new entity."),
    },
}

# mojibake repair: the em-dash rendered as U+FFFD-ish bytes in source.
MOJIBAKE = "�"


def repair(text):
    # The report uses an em-dash that decodes to a replacement char in places.
    return text.replace(MOJIBAKE, "—")


def split_sections(text):
    parts = re.split(r"\n### ", text)
    out = []
    for p in parts[1:]:
        nl = p.index("\n")
        header = p[:nl].strip()
        body = p[nl + 1 :]
        m = re.search(r"\n## ", body)
        if m:
            body = body[: m.start()]
        out.append((header, body))
    return out


def units_from_body(body):
    units = []
    for m in UNIT_RE.finditer(body):
        raw_text = m.group(1)
        cites = [int(x) for x in CITE_RE.findall(m.group(2))]
        norm = re.sub(r"\s+", " ", raw_text).strip()
        if not norm:
            continue
        units.append((norm, cites))
    return units


def main():
    text = open(REPORT, encoding="utf-8").read()
    secs = dict(split_sections(text))
    gold = []
    for section, label_map in LABELS.items():
        if section not in secs:
            raise SystemExit(f"Section not found in report: {section!r}")
        units = units_from_body(secs[section])
        curated = section in CURATED_SUBSET
        for idx, (sentence, cites) in enumerate(units):
            if idx not in label_map:
                if curated:
                    continue  # out-of-scope unit in a curated-subset section
                raise SystemExit(
                    f"Unlabeled unit {idx} in section {section!r}: {sentence[:80]!r}"
                )
            cluster_local, label, reason = label_map[idx]
            gold.append(
                {
                    "section": section,
                    "sentence": repair(sentence),
                    "citations": cites,
                    "cluster_id": f"{section_slug(section)}::{cluster_local}",
                    "label": label,
                    "reason": reason,
                }
            )
        # sanity: ensure no stray label index beyond parsed units
        for idx in label_map:
            if idx >= len(units):
                raise SystemExit(
                    f"Label index {idx} out of range for section {section!r} ({len(units)} units)"
                )
    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(gold, f, indent=2, ensure_ascii=False)
    keep = sum(1 for g in gold if g["label"] == "keep")
    rep = sum(1 for g in gold if g["label"] == "paraphrase_repeat")
    print(f"wrote {OUT}")
    print(f"total items     : {len(gold)}")
    print(f"keep (content)  : {keep}")
    print(f"paraphrase_repeat (drop): {rep}")
    print(f"distinct clusters: {len(set(g['cluster_id'] for g in gold))}")


def section_slug(section):
    s = re.sub(r"[^a-zA-Z0-9]+", "_", section).strip("_").lower()
    return s[:32]


if __name__ == "__main__":
    main()
