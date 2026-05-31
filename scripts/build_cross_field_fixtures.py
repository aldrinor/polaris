"""Build the S3 cross-field + S4 adversarial-thin authority fixtures (GH #983).

These are TEST FIXTURES (allowed synthetic test inputs per LAW VI / §9.4 — they
live under tests/fixtures/). Each row is a non-clinical source with a mocked
OpenAlex/ROR AuthoritySignals payload + structural fields. The expected
source_class / confidence band is asserted in the S3 / S4 tests.

S3 cross-field (>=50): law / physics / policy / JP-gov / African-energy with
defensible source_class + honest confidence.
S4 adversarial-thin: grey-lit / non-English / niche-regional with deliberately
THIN OpenAlex -> must land honest-LOW confidence in the mid-band.
"""
from __future__ import annotations

import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
FIX_DIR = REPO_ROOT / "tests" / "fixtures" / "authority"


def _row(url, field, signals, structural=None, expect_class=None, expect_conf=None):
    return {
        "url": url,
        "field": field,
        "authority_signals": signals,
        "structural": structural or {},
        "expect_source_class": expect_class,
        "expect_confidence": expect_conf,
    }


def _scholarly(cited, h_index, two_yr, inst_type="education", core=True, doaj=True,
               year=2022, country="US"):
    return {
        "cited_by_count": cited,
        "source_id": "https://openalex.org/S100",
        "venue_summary_stats": {"h_index": h_index, "2yr_mean_citedness": two_yr},
        "is_core": core,
        "is_in_doaj": doaj,
        "apc_prices": None,
        "publication_year": year,
        "ror_id": "https://ror.org/edu1",
        "institution_type": inst_type,
        "country_code": country,
    }


def _official(inst_type="government", country="JP"):
    return {
        "cited_by_count": None,
        "source_id": "",
        "venue_summary_stats": None,
        "is_core": None,
        "is_in_doaj": None,
        "apc_prices": None,
        "publication_year": 2023,
        "ror_id": "https://ror.org/gov1",
        "institution_type": inst_type,
        "country_code": country,
    }


def _thin(year=None):
    return {
        "cited_by_count": None,
        "source_id": "",
        "venue_summary_stats": None,
        "is_core": None,
        "is_in_doaj": None,
        "apc_prices": None,
        "publication_year": year,
        "ror_id": "",
        "institution_type": "",
        "country_code": "",
    }


def build_cross_field() -> list[dict]:
    rows: list[dict] = []
    # Physics journals (PRIMARY_SCHOLARLY).
    for i in range(12):
        rows.append(_row(
            f"https://journals.aps.org/prl/abstract/physics{i}", "physics",
            _scholarly(800 + i, 250, 9.0), expect_class="PRIMARY_SCHOLARLY",
            expect_conf="HIGH",
        ))
    # JP government ministries via ROR + PSL gov suffix (PRIMARY_OFFICIAL).
    jp_hosts = ["mhlw.go.jp", "meti.go.jp", "mext.go.jp", "env.go.jp",
                "soumu.go.jp", "maff.go.jp"]
    for h in jp_hosts:
        rows.append(_row(
            f"https://www.{h}/policy/doc.html", "jp_gov",
            _official("government", "JP"), expect_class="PRIMARY_OFFICIAL",
            expect_conf="HIGH",
        ))
    # African-energy policy bodies (PRIMARY_OFFICIAL via ROR government).
    for i, h in enumerate(["energy.go.ke", "nersa.org.za", "energycommission.gov.gh"]):
        rows.append(_row(
            f"https://www.{h}/report{i}", "african_energy",
            _official("government", "KE" if i == 0 else "ZA"),
            expect_class="PRIMARY_OFFICIAL", expect_conf="HIGH",
        ))
    # Policy think-tank / nonprofit (SECONDARY).
    for i in range(8):
        rows.append(_row(
            f"https://policyinstitute.test/brief{i}", "policy",
            _official("nonprofit", "GB"), expect_class="SECONDARY",
            expect_conf="MEDIUM",
        ))
    # Law-firm commentary blogs (COMMENTARY via junk path /blog/).
    for i in range(12):
        rows.append(_row(
            f"https://lawfirm{i}.test/blog/analysis-{i}", "law",
            _thin(2024), structural={"url_path": f"/blog/analysis-{i}"},
            expect_class="COMMENTARY", expect_conf=None,
        ))
    # Law scholarship (education ROR + journal) PRIMARY_SCHOLARLY.
    for i in range(10):
        rows.append(_row(
            f"https://lawreview.test/article/{i}", "law",
            _scholarly(40 + i, 60, 3.0, inst_type="education"),
            expect_class="PRIMARY_SCHOLARLY", expect_conf="HIGH",
        ))
    return rows


def build_adversarial_thin() -> list[dict]:
    rows: list[dict] = []
    # Grey-lit / non-English / niche-regional, deliberately THIN OpenAlex.
    samples = [
        ("https://greylit.test/working-paper-1", "grey_lit"),
        ("https://greylit.test/working-paper-2", "grey_lit"),
        ("https://revista-regional.test/articulo-1", "non_english"),
        ("https://revista-regional.test/articulo-2", "non_english"),
        ("https://niche-regional.test/report-a", "niche_regional"),
        ("https://niche-regional.test/report-b", "niche_regional"),
        ("https://obscure-journal.test/paper-x", "grey_lit"),
        ("https://local-ministry-archive.test/doc-7", "niche_regional"),
        ("https://small-ngo.test/whitepaper", "grey_lit"),
        ("https://regional-univ.test/thesis-3", "non_english"),
    ]
    for url, field in samples:
        rows.append(_row(url, field, _thin(2021), expect_conf="LOW"))
    return rows


def main() -> None:
    FIX_DIR.mkdir(parents=True, exist_ok=True)
    cross = build_cross_field()
    thin = build_adversarial_thin()
    (FIX_DIR / "cross_field_50_urls.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in cross) + "\n",
        encoding="utf-8",
    )
    (FIX_DIR / "adversarial_thin_field.jsonl").write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in thin) + "\n",
        encoding="utf-8",
    )
    print(f"cross_field rows: {len(cross)}  adversarial_thin rows: {len(thin)}")


if __name__ == "__main__":
    main()
