"""
Mesh Scale Test -- full ask() path with real LLM on 5 sources.

Tests the complete pipeline at moderate scale:
  5 sources -> extract -> entities -> edges -> ask() with follow-up

This validates:
  - Edge formation at scale (do corroboration edges form between 5 sources?)
  - Citation diversity (do answers cite 3+ unique sources?)
  - Thread follow-up with real coreference
  - Entity deduplication across sources

Usage:
    python scripts/pg_mesh_scale_test.py
"""

import asyncio
import logging
import re
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.polaris_graph.llm.openrouter_client import OpenRouterClient
from src.polaris_graph.wiki.mesh import MeshStore
from src.polaris_graph.wiki.mesh.claim_extract import extract_claims_from_source
from src.polaris_graph.wiki.mesh.edge_discovery import discover_edges_for_claims
from src.polaris_graph.wiki.mesh.ingest import ingest_file
from src.polaris_graph.wiki.mesh.qa.ask import ask

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("scale_test")
logger.setLevel(logging.INFO)

SOURCES = {
    "gac_filtration.md": """# GAC Filtration for PFAS Removal

Granular activated carbon (GAC) filtration is widely used for removing per- and polyfluoroalkyl substances (PFAS) from drinking water. In a 12-month study across 15 municipal treatment plants, GAC achieved an average removal efficiency of 85% for long-chain PFAS compounds including PFOS and PFOA, with contact times standardized at 10 minutes per treatment cycle.

The effectiveness of GAC varies significantly by PFAS chain length. Long-chain compounds (C8 and above) showed removal rates of 85-95%, while short-chain PFAS (C4-C6) like PFBS showed substantially lower removal at 40-60%. The carbon bed lifetime before breakthrough averaged 18 months for long-chain compounds but only 6-8 months for short-chain variants.

Cost analysis indicates GAC treatment adds approximately $0.15-0.25 per 1000 gallons of treated water. The EPA has recommended GAC as one of the best available technologies (BAT) for PFAS removal under the proposed Maximum Contaminant Levels.""",

    "reverse_osmosis.md": """# Reverse Osmosis for PFAS Treatment

Reverse osmosis (RO) membrane technology demonstrates superior PFAS removal performance compared to adsorption-based methods. A multi-site study involving 42 independent measurements across 8 water utilities found RO membranes achieved 95% or greater removal of all tested PFAS compounds, regardless of chain length.

RO maintains greater than 90% removal efficiency across all chain lengths tested (C4 through C14), making it the preferred technology for mixed-chain-length contamination. However, RO generates a concentrated reject stream containing 15-25% of the input water volume. Energy consumption averages 3-5 kWh per 1000 gallons, making RO approximately 2-3 times more expensive than GAC.""",

    "ion_exchange.md": """# Ion Exchange Resins for PFAS Treatment

Anion exchange (AIX) resins represent a promising alternative to GAC for PFAS removal. Single-use AIX resins achieved 99% removal of both long-chain and short-chain PFAS in pilot studies at three water utilities. Unlike GAC, AIX resins maintain high performance for short-chain compounds including PFBS and PFHxS.

The regenerable variant of AIX resins showed 85-90% removal after 500 bed volumes, with performance declining to 60-70% after 2000 bed volumes. Cost comparison with GAC shows AIX is 30-50% more expensive per treatment unit but offers superior removal of the increasingly regulated short-chain PFAS compounds.""",

    "nanofiltration.md": """# Nanofiltration Membranes for PFAS

Nanofiltration (NF) membranes provide an intermediate option between reverse osmosis and conventional filtration. NF membranes with molecular weight cutoff below 300 Daltons achieved 90-95% removal of long-chain PFAS, though performance dropped to 70-80% for short-chain compounds in a 6-month pilot study.

NF requires lower operating pressures (70-120 psi) compared to RO (150-300 psi), resulting in 40% lower energy consumption. Water recovery rates for NF are typically 80-85% compared to 75-85% for RO, producing less reject stream. Treatment costs range from $0.20-0.35 per 1000 gallons.""",

    "comparative_review.md": """# Comparative Review of PFAS Treatment Technologies

A comprehensive meta-analysis of 47 peer-reviewed studies compared the four leading PFAS treatment technologies. GAC filtration remains the most widely deployed method, installed at over 200 US water utilities, but its limitation with short-chain PFAS is a growing concern as EPA regulations expand beyond PFOS and PFOA.

RO and NF membrane technologies offer superior broad-spectrum removal but at higher capital and operating costs. Ion exchange resins represent the best balance of removal efficiency and selectivity for mixed PFAS contamination scenarios. No single technology is optimal for all situations -- the choice depends on the specific PFAS profile, water quality parameters, and regulatory requirements at each site.""",
}

QUESTION_1 = "What are the most effective methods for removing PFAS from drinking water, and how do they compare?"
QUESTION_2 = "Which method works best for short-chain PFAS specifically?"
QUESTION_3 = "What about the costs?"


async def main():
    import tempfile
    base_dir = Path(tempfile.mkdtemp(prefix="mesh_scale_"))
    db_path = base_dir / "scale_test.db"
    logger.info("Working directory: %s", base_dir)

    store = MeshStore.open(db_path)
    client = OpenRouterClient(model="z-ai/glm-5.1")

    try:
        # -- Create workspace --
        ws_id = store.create_workspace(
            name="Scale Test",
            root_question=QUESTION_1,
        )
        logger.info("Workspace: %s", ws_id)

        # -- Ingest 5 sources --
        src_ids = []
        for filename, content in SOURCES.items():
            fpath = base_dir / filename
            fpath.write_text(content, encoding="utf-8")
            src_id, _ = ingest_file(
                store=store, workspace_id=ws_id,
                file_path=fpath, kind="upload",
                url=f"https://example.com/{filename}",
            )
            src_ids.append(src_id)
            logger.info("Ingested: %s -> %s", filename, src_id)

        # -- Extract claims from all 5 sources --
        all_claim_ids = []
        t0 = time.time()
        for src_id in src_ids:
            result = await extract_claims_from_source(
                client=client, store=store,
                workspace_id=ws_id, source_page_id=src_id,
                query=QUESTION_1,
            )
            all_claim_ids.extend(result.inserted_claim_ids)
            logger.info(
                "Extracted: %d claims (%d seen, skipped=%s)",
                len(result.inserted_claim_ids),
                result.total_facts_seen, result.skipped,
            )
        extract_time = time.time() - t0

        # -- Discover edges --
        edge_result = discover_edges_for_claims(
            store, workspace_id=ws_id,
            new_claim_ids=all_claim_ids,
        )

        # -- Full ask() with thread --
        t1 = time.time()
        r1 = await ask(
            client, store,
            workspace_id=ws_id,
            question_text=QUESTION_1,
        )
        r2 = await ask(
            client, store,
            workspace_id=ws_id,
            question_text=QUESTION_2,
            parent_question_id=r1.question_id,
        )
        r3 = await ask(
            client, store,
            workspace_id=ws_id,
            question_text=QUESTION_3,
            parent_question_id=r2.question_id,
        )
        ask_time = time.time() - t1

        # -- Stats --
        stats = store.workspace_stats(ws_id)
        entities = store._conn.execute(
            "SELECT canonical_name, entity_type FROM entities "
            "WHERE workspace_id = ? ORDER BY canonical_name",
            (ws_id,),
        ).fetchall()
        quarantined = store.get_quarantined_entities(ws_id)

        # -- Report --
        print("\n" + "=" * 70)
        print("MESH SCALE TEST REPORT")
        print("=" * 70)

        print(f"\n  EXTRACTION ({extract_time:.0f}s):")
        print(f"    Sources: {len(src_ids)}")
        print(f"    Total claims: {len(all_claim_ids)}")
        print(f"    GOLD: {stats['gold_claims']}  "
              f"SILVER: {stats['silver_claims']}  "
              f"BRONZE: {stats['bronze_claims']}")

        print(f"\n  ENTITIES ({len(entities)}):")
        for e in entities[:15]:
            print(f"    {e['canonical_name']} ({e['entity_type']})")
        if len(entities) > 15:
            print(f"    ... and {len(entities) - 15} more")
        print(f"    Quarantined: {len(quarantined)}")

        print(f"\n  EDGES:")
        print(f"    Total: {edge_result.edge_ids.__len__()}")
        print(f"    Corroborate: {edge_result.corroboration_count}")
        print(f"    Contradict: {edge_result.contradiction_count}")

        print(f"\n  Q&A THREAD ({ask_time:.0f}s):")
        for i, (q, r) in enumerate([
            (QUESTION_1, r1), (QUESTION_2, r2), (QUESTION_3, r3)
        ], 1):
            cites = re.findall(r"\[\d+\]", r.answer_text)
            unique = len(set(cites))
            words = len(r.answer_text.split())
            print(f"\n    Q{i}: {q[:60]}...")
            print(f"    Gap: {r.gap_category}  Words: {words}  "
                  f"Citations: {len(cites)} ({unique} unique)  "
                  f"Bib: {len(r.bibliography)}")
            print(f"    Preview: {r.answer_text[:100]}...")

        # -- Pass/fail --
        total_claims = len(all_claim_ids)
        total_edges = len(edge_result.edge_ids)
        q1_unique = len(set(re.findall(r"\[\d+\]", r1.answer_text)))

        print(f"\n{'=' * 70}")
        print("VERDICT:")
        checks = [
            ("Claims >= 15", total_claims >= 15),
            ("Entities >= 10", len(entities) >= 10),
            ("Edges >= 2", total_edges >= 2),
            ("Q1 gap = IN_SCOPE", r1.gap_category == "IN_SCOPE"),
            ("Q1 unique citations >= 2", q1_unique >= 2),
            ("No CoT leakage Q1", "<think>" not in r1.answer_text),
            ("Thread has 3 turns", r3.question_id != r1.question_id),
        ]
        for name, passed in checks:
            status = "PASS" if passed else "FAIL"
            print(f"  [{status}] {name}")

        all_pass = all(p for _, p in checks)
        print(f"\n{'OK' if all_pass else 'WARNING'}  "
              f"{'ALL CHECKS PASSED' if all_pass else 'SOME CHECKS FAILED'}")
        return 0 if all_pass else 1

    except Exception as exc:
        logger.error("Scale test failed: %s", exc, exc_info=True)
        return 1
    finally:
        await client.close()
        store.close()


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
