"""V30 Phase-2 sweep run-1 root-cause regression:
contract DOI↔PMID cross-validation.

The first V30 Phase-2 full-scale sweep extracted prose from the
SPRINT blood-pressure trial into the SURPASS-2 slot because
`config/scope_templates/clinical.yaml` had the wrong PMID
(34010531 = SPRINT, not Frias SURPASS-2). The anti-fabrication
check passed because SPRINT prose WAS verbatim in the fetched
abstract — the substring check cannot catch wrong-paper extraction.

This module is the SCHEMA-level regression test: parse every
per_query_report_contract entity and verify that when both `doi`
and `pmid` are populated, the PubMed EUtils esearch for that DOI
returns the declared PMID (or returns an empty list when the DOI
is not indexed, which is still consistent — PubMed just doesn't
know about it yet).

Run this offline-free via a deterministic fixture when possible.
For the live-network variant, use `-m needs_network`.
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest
import yaml


_SKIP_NETWORK = os.environ.get("PG_SKIP_NETWORK_TESTS", "0").strip() in (
    "1", "true", "True",
)


def _load_all_contracts() -> list[tuple[str, str, dict]]:
    """Return list of (template_name, slug, contract_dict) for every
    per_query_report_contract in every scope_templates/*.yaml."""
    out: list[tuple[str, str, dict]] = []
    for tmpl_path in Path("config/scope_templates").glob("*.yaml"):
        with tmpl_path.open("r", encoding="utf-8") as f:
            tmpl = yaml.safe_load(f) or {}
        contracts = tmpl.get("per_query_report_contract") or {}
        if not isinstance(contracts, dict):
            continue
        for slug, ctr in contracts.items():
            if not isinstance(ctr, dict):
                continue
            out.append((tmpl_path.name, slug, ctr))
    return out


class TestContractDoiPmidConsistency:
    """Pure-YAML preflight checks for contract DOI/PMID integrity."""

    def test_every_entity_has_valid_doi_or_pmid_or_url(self) -> None:
        """Every required_entity must have at least ONE resolvable
        identifier (doi, pmid, or url_pattern). No naked-anchor
        entities allowed — M-56 cannot fetch from an anchor alone."""
        defects: list[str] = []
        for tmpl_name, slug, ctr in _load_all_contracts():
            for e in ctr.get("required_entities", []) or []:
                if not isinstance(e, dict):
                    continue
                eid = e.get("id", "<no-id>")
                doi = e.get("doi")
                pmid = e.get("pmid")
                url = e.get("url_pattern") or e.get("url")
                if not any((doi, pmid, url)):
                    defects.append(
                        f"{tmpl_name}:{slug}.{eid}: no doi/pmid/url_pattern"
                    )
        assert not defects, "Contract defects:\n" + "\n".join(defects)

    def test_no_ev_live_namespace_in_contract_ids(self) -> None:
        """Codex M-63 Medium 3 guard: no contract entity id may
        collide with the live-retrieval `ev_\\d+` keyspace."""
        import re
        pattern = re.compile(r"^ev_\d+$")
        defects: list[str] = []
        for tmpl_name, slug, ctr in _load_all_contracts():
            for e in ctr.get("required_entities", []) or []:
                if not isinstance(e, dict):
                    continue
                eid = e.get("id", "")
                if isinstance(eid, str) and pattern.match(eid):
                    defects.append(
                        f"{tmpl_name}:{slug}.{eid}: collides with "
                        f"live-retrieval namespace"
                    )
        assert not defects, "Contract defects:\n" + "\n".join(defects)


@pytest.mark.skipif(
    _SKIP_NETWORK,
    reason="Requires PubMed EUtils network access",
)
class TestContractDoiPmidConsistencyLive:
    """Cross-check every contract (DOI, PMID) pair against PubMed
    EUtils. SKIPPED unless PG_SKIP_NETWORK_TESTS is unset.

    Run manually before shipping a contract edit:
        pytest tests/polaris_graph/test_v30_contract_doi_pmid_consistency.py -v -k live
    """

    def test_doi_pmid_pairs_consistent_with_pubmed(self) -> None:
        import httpx
        import time
        defects: list[str] = []
        for tmpl_name, slug, ctr in _load_all_contracts():
            for e in ctr.get("required_entities", []) or []:
                if not isinstance(e, dict):
                    continue
                eid = e.get("id", "<no-id>")
                doi = e.get("doi")
                pmid = e.get("pmid")
                if not doi or not pmid:
                    continue
                try:
                    r = httpx.get(
                        "https://eutils.ncbi.nlm.nih.gov/entrez/"
                        "eutils/esearch.fcgi",
                        params={
                            "db": "pubmed",
                            "term": f"{doi}[doi]",
                            "retmode": "json",
                        },
                        timeout=30,
                    )
                    pmids = (
                        r.json()
                        .get("esearchresult", {})
                        .get("idlist", [])
                    )
                except Exception as exc:  # noqa: BLE001
                    defects.append(
                        f"{tmpl_name}:{slug}.{eid}: "
                        f"network lookup failed: {exc}"
                    )
                    continue
                time.sleep(0.35)  # polite rate limit
                # PubMed returning empty list is ACCEPTABLE (DOI
                # not indexed yet); mismatch is the fail case.
                if pmids and str(pmid) not in pmids:
                    defects.append(
                        f"{tmpl_name}:{slug}.{eid}: "
                        f"doi={doi} yaml_pmid={pmid} "
                        f"pubmed_pmids={pmids} -- MISMATCH "
                        f"(wrong paper; M-56 would extract from "
                        f"whatever PubMed returns, silently "
                        f"corrupting the report)"
                    )
        assert not defects, (
            "Contract DOI/PMID defects (network-verified):\n"
            + "\n".join(defects)
        )
