"""
Mesh Preflight -- side-by-side model comparison on real data.

Tests both GLM 5.1 and Qwen 3.6 Plus against the same sources,
comparing: extraction quality, entity yield, JSON compliance,
edge formation, retrieval relevance, composition citations.

Usage:
    python scripts/pg_mesh_preflight.py

Requires: OPENROUTER_API_KEY in .env
"""

import asyncio
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.polaris_graph.llm.openrouter_client import OpenRouterClient
from src.polaris_graph.wiki.mesh import MeshStore
from src.polaris_graph.wiki.mesh.claim_extract import extract_claims_from_source
from src.polaris_graph.wiki.mesh.compose.composer import compose_answer
from src.polaris_graph.wiki.mesh.edge_discovery import discover_edges_for_claims
from src.polaris_graph.wiki.mesh.ingest import ingest_file
from src.polaris_graph.wiki.mesh.retrieve.lethal import lethal_retrieve

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger("preflight")
logger.setLevel(logging.INFO)

# ----- test sources -----

SOURCE_A = """# GAC Filtration for PFAS Removal

Granular activated carbon (GAC) filtration is widely used for removing per- and polyfluoroalkyl substances (PFAS) from drinking water. In a 12-month study across 15 municipal treatment plants, GAC achieved an average removal efficiency of 85% for long-chain PFAS compounds including PFOS and PFOA, with contact times standardized at 10 minutes per treatment cycle.

The effectiveness of GAC varies significantly by PFAS chain length. Long-chain compounds (C8 and above) showed removal rates of 85-95%, while short-chain PFAS (C4-C6) like PFBS showed substantially lower removal at 40-60%. The carbon bed lifetime before breakthrough averaged 18 months for long-chain compounds but only 6-8 months for short-chain variants.

Cost analysis indicates GAC treatment adds approximately $0.15-0.25 per 1000 gallons of treated water, making it one of the more cost-effective PFAS removal technologies available for municipal-scale deployment. However, spent carbon disposal and regeneration costs can add 30-40% to the total lifecycle cost.

The EPA has recommended GAC as one of the best available technologies (BAT) for PFAS removal under the proposed Maximum Contaminant Levels (MCLs) of 4 parts per trillion for PFOS and PFOA individually."""

SOURCE_B = """# Reverse Osmosis for PFAS Treatment

Reverse osmosis (RO) membrane technology demonstrates superior PFAS removal performance compared to adsorption-based methods. A multi-site study involving 42 independent measurements across 8 water utilities found RO membranes achieved 95% or greater removal of all tested PFAS compounds, regardless of chain length.

The key advantage of RO over GAC is its effectiveness against short-chain PFAS compounds. While GAC removal drops to 40-60% for short-chain PFAS, RO maintains greater than 90% removal efficiency across all chain lengths tested (C4 through C14). This makes RO the preferred technology for water sources contaminated with mixed-chain-length PFAS.

However, RO generates a concentrated reject stream containing 15-25% of the input water volume, creating a secondary waste management challenge. The reject stream requires additional treatment or disposal, adding $0.40-0.60 per 1000 gallons to the total treatment cost.

Energy consumption for RO treatment averages 3-5 kWh per 1000 gallons, compared to negligible energy requirements for GAC. This energy penalty, combined with higher capital costs, makes RO approximately 2-3 times more expensive than GAC for large-scale municipal deployment."""

MODELS = [
    ("GLM 5.1", "z-ai/glm-5.1"),
    ("Qwen 3.5 Plus", "qwen/qwen3.5-plus-02-15"),
]

QUESTION = "What are the most effective methods for removing PFAS from drinking water, and how do they compare on cost and performance?"


# ----- runner -----

async def run_model_test(model_name: str, model_id: str, base_dir: Path):
    """Run the full pipeline with one model and return metrics."""
    logger.info("=" * 60)
    logger.info("TESTING: %s (%s)", model_name, model_id)
    logger.info("=" * 60)

    db_path = base_dir / f"{model_name.replace(' ', '_').lower()}.db"
    store = MeshStore.open(db_path)
    client = OpenRouterClient(model=model_id)

    metrics = {
        "model": model_name,
        "model_id": model_id,
        "errors": [],
    }

    try:
        # -- Step 1: Create workspace + ingest --
        ws_id = store.create_workspace(
            name=f"Preflight {model_name}",
            root_question=QUESTION,
        )

        file_a = base_dir / "source_a.md"
        file_a.write_text(SOURCE_A, encoding="utf-8")
        file_b = base_dir / "source_b.md"
        file_b.write_text(SOURCE_B, encoding="utf-8")

        src_a, _ = ingest_file(
            store=store, workspace_id=ws_id,
            file_path=file_a, kind="upload",
            url="https://example.com/gac-study",
        )
        src_b, _ = ingest_file(
            store=store, workspace_id=ws_id,
            file_path=file_b, kind="web",
            url="https://example.com/ro-study",
        )
        metrics["sources_ingested"] = 2

        # -- Step 2: Extract claims --
        t0 = time.time()
        try:
            result_a = await extract_claims_from_source(
                client=client, store=store,
                workspace_id=ws_id, source_page_id=src_a,
                query=QUESTION,
            )
            result_b = await extract_claims_from_source(
                client=client, store=store,
                workspace_id=ws_id, source_page_id=src_b,
                query=QUESTION,
            )
            extract_time = time.time() - t0
            metrics["extract_time_s"] = round(extract_time, 1)
            metrics["claims_a"] = len(result_a.inserted_claim_ids)
            metrics["claims_b"] = len(result_b.inserted_claim_ids)
            metrics["total_claims"] = metrics["claims_a"] + metrics["claims_b"]
            metrics["skipped_a"] = result_a.skipped
            metrics["skipped_b"] = result_b.skipped
            metrics["facts_seen_a"] = result_a.total_facts_seen
            metrics["facts_seen_b"] = result_b.total_facts_seen

            all_claim_ids = result_a.inserted_claim_ids + result_b.inserted_claim_ids
        except Exception as exc:
            metrics["errors"].append(f"EXTRACTION FAILED: {exc}")
            logger.error("Extraction failed for %s: %s", model_name, exc)
            return metrics

        # -- Step 3: Check entities --
        entities = store._conn.execute(
            "SELECT canonical_name, entity_type FROM entities "
            "WHERE workspace_id = ?", (ws_id,),
        ).fetchall()
        metrics["entity_count"] = len(entities)
        metrics["entity_names"] = [e["canonical_name"] for e in entities]
        metrics["entity_types"] = {
            e["canonical_name"]: e["entity_type"] for e in entities
        }

        # -- Step 4: Discover edges --
        edge_result = discover_edges_for_claims(
            store, workspace_id=ws_id,
            new_claim_ids=all_claim_ids,
        )
        metrics["edges_total"] = len(edge_result.edge_ids)
        metrics["edges_corroborate"] = edge_result.corroboration_count
        metrics["edges_contradict"] = edge_result.contradiction_count

        # -- Step 5: Retrieve --
        retrieval = lethal_retrieve(
            store, workspace_id=ws_id,
            question_text=QUESTION,
        )
        metrics["retrieved_claims"] = len(retrieval.scored_claims)
        metrics["gap_category"] = retrieval.gap_category
        if retrieval.scored_claims:
            metrics["top_score"] = round(retrieval.scored_claims[0][1], 4)
            top_claim = store.get_claim(retrieval.scored_claims[0][0])
            metrics["top_claim"] = top_claim["statement"][:100] if top_claim else "?"

        # -- Step 6: Compose --
        t1 = time.time()
        try:
            compose_result = await compose_answer(
                client, store,
                workspace_id=ws_id,
                retrieval_result=retrieval,
                question_text=QUESTION,
            )
            compose_time = time.time() - t1
            metrics["compose_time_s"] = round(compose_time, 1)
            metrics["answer_length"] = len(compose_result.answer_text)
            metrics["answer_words"] = len(compose_result.answer_text.split())
            metrics["bibliography_count"] = len(compose_result.bibliography)

            # Count citations
            import re
            citations = re.findall(r"\[\d+\]", compose_result.answer_text)
            metrics["citation_count"] = len(citations)
            unique_refs = set(citations)
            metrics["unique_citations"] = len(unique_refs)

            # Check for CoT leakage
            cot_markers = ["<think>", "<reasoning>", "**Planning", "**Step"]
            has_cot = any(m in compose_result.answer_text for m in cot_markers)
            metrics["cot_leakage"] = has_cot

            metrics["answer_preview"] = compose_result.answer_text[:300]
        except Exception as exc:
            metrics["errors"].append(f"COMPOSITION FAILED: {exc}")
            logger.error("Composition failed for %s: %s", model_name, exc)

        # -- Step 7: Claim quality sample --
        claims = []
        for cid in all_claim_ids[:5]:
            c = store.get_claim(cid)
            if c:
                claims.append({
                    "statement": c["statement"][:80],
                    "tier": c["tier"],
                    "has_numeric": bool(c["has_numeric"]),
                    "relevance": c["relevance_score"],
                })
        metrics["sample_claims"] = claims

    except Exception as exc:
        metrics["errors"].append(f"PIPELINE FAILED: {exc}")
        logger.error("Pipeline failed for %s: %s", model_name, exc)
    finally:
        await client.close()
        store.close()

    return metrics


def print_comparison(results: list[dict]):
    """Print a side-by-side comparison of model results."""
    print("\n" + "=" * 70)
    print("MESH PREFLIGHT -- MODEL COMPARISON")
    print("=" * 70)

    for r in results:
        print(f"\n{'-' * 70}")
        print(f"MODEL: {r['model']} ({r['model_id']})")
        print(f"{'-' * 70}")

        if r.get("errors"):
            for err in r["errors"]:
                print(f"  *** {err}")

        print(f"\n  EXTRACTION:")
        print(f"    Time:           {r.get('extract_time_s', '?')}s")
        print(f"    Facts seen:     A={r.get('facts_seen_a', '?')}, B={r.get('facts_seen_b', '?')}")
        print(f"    Claims inserted: A={r.get('claims_a', '?')}, B={r.get('claims_b', '?')} (total: {r.get('total_claims', '?')})")
        print(f"    Skipped A:      {r.get('skipped_a', '?')}")
        print(f"    Skipped B:      {r.get('skipped_b', '?')}")

        print(f"\n  ENTITIES ({r.get('entity_count', 0)}):")
        for name in r.get("entity_names", [])[:10]:
            etype = r.get("entity_types", {}).get(name, "?")
            print(f"    {name} ({etype})")

        print(f"\n  EDGES:")
        print(f"    Total:          {r.get('edges_total', 0)}")
        print(f"    Corroborate:    {r.get('edges_corroborate', 0)}")
        print(f"    Contradict:     {r.get('edges_contradict', 0)}")

        print(f"\n  RETRIEVAL:")
        print(f"    Claims found:   {r.get('retrieved_claims', 0)}")
        print(f"    Gap category:   {r.get('gap_category', '?')}")
        print(f"    Top score:      {r.get('top_score', '?')}")
        print(f"    Top claim:      {r.get('top_claim', '?')}")

        print(f"\n  COMPOSITION:")
        print(f"    Time:           {r.get('compose_time_s', '?')}s")
        print(f"    Words:          {r.get('answer_words', '?')}")
        print(f"    Citations:      {r.get('citation_count', '?')} ({r.get('unique_citations', '?')} unique)")
        print(f"    Bibliography:   {r.get('bibliography_count', '?')} entries")
        print(f"    CoT leakage:    {'YES WARNING' if r.get('cot_leakage') else 'No OK'}")

        print(f"\n  ANSWER PREVIEW:")
        preview = r.get("answer_preview", "(none)")
        for line in preview.split("\n")[:5]:
            print(f"    {line[:80]}")

        print(f"\n  SAMPLE CLAIMS:")
        for c in r.get("sample_claims", []):
            print(f"    [{c['tier']}] {'#' if c['has_numeric'] else '  '} "
                  f"rel={c['relevance']:.2f}  {c['statement']}")

    # -- Summary --
    print(f"\n{'=' * 70}")
    print("SUMMARY")
    print(f"{'=' * 70}")
    for r in results:
        errs = len(r.get("errors", []))
        claims = r.get("total_claims", 0)
        ents = r.get("entity_count", 0)
        edges = r.get("edges_total", 0)
        cites = r.get("citation_count", 0)
        cot = "LEAK" if r.get("cot_leakage") else "clean"
        status = "FAIL" if errs > 0 else "PASS"
        print(f"  {r['model']:20s}  {status}  claims={claims}  "
              f"entities={ents}  edges={edges}  citations={cites}  "
              f"cot={cot}  errors={errs}")


async def main():
    import tempfile
    base_dir = Path(tempfile.mkdtemp(prefix="mesh_preflight_"))
    logger.info("Working directory: %s", base_dir)

    results = []
    for model_name, model_id in MODELS:
        try:
            metrics = await run_model_test(model_name, model_id, base_dir)
            results.append(metrics)
        except Exception as exc:
            logger.error("Fatal error testing %s: %s", model_name, exc)
            results.append({
                "model": model_name,
                "model_id": model_id,
                "errors": [f"FATAL: {exc}"],
            })

    print_comparison(results)

    any_fail = any(r.get("errors") for r in results)
    if any_fail:
        print("\nWARNING  SOME MODELS HAD ERRORS -- check output above")
    else:
        print("\nOK  ALL MODELS PASSED PREFLIGHT")

    return 1 if any_fail else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
