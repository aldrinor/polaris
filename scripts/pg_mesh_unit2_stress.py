"""
Unit 2 CP-D stress test (not part of the pytest suite — a one-shot
validator that exercises ingest + claim_extract end to end with a
mock LLM and a realistic multi-source workspace).

Run with:
    python scripts/pg_mesh_unit2_stress.py
"""

from __future__ import annotations

import asyncio
import shutil
import sys
import tempfile
import time
from pathlib import Path

# Make `src.` imports work when running from project root
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np

from src.polaris_graph.schemas import SourceAnalysisBatch
from src.polaris_graph.wiki.mesh import MeshStore
from src.polaris_graph.wiki.mesh.claim_extract import (
    extract_claims_from_source,
)
from src.polaris_graph.wiki.mesh.ingest import ingest_file


class MockClient:
    """Returns a pre-baked SourceAnalysisBatch in call order."""

    def __init__(self, batches: list[SourceAnalysisBatch]):
        self.batches = batches
        self.calls = 0

    async def generate_structured(self, **kw):
        self.calls += 1
        return self.batches[(self.calls - 1) % len(self.batches)]


def mk_batch(
    source_url: str,
    facts: list[dict],
    source_quality: float = 0.75,
) -> SourceAnalysisBatch:
    return SourceAnalysisBatch.model_validate({
        "analyses": [{
            "source_url": source_url,
            "source_title": "Stress test source",
            "source_type": "journal_article",
            "source_quality": source_quality,
            "overall_relevance": 0.75,
            "atomic_facts": facts,
        }]
    })


def valid_fact(quote: str) -> dict:
    return {
        "statement": "Extracted claim derived from the following source quotation",
        "direct_quote": quote,
        "relevance_score": 0.8,
    }


BODY_1 = (
    "PFAS contamination in drinking water has become a major concern for "
    "public health agencies across North America, Europe, and East Asia. "
    "Granular activated carbon (GAC) achieved 85% removal of long-chain "
    "PFAS compounds in 10 minute contact time across independent trials "
    "at typical residential concentrations. Reverse osmosis membranes "
    "performed better at 95% CI 91-97% but required pressurization and "
    "produced substantial reject water volumes. Ion exchange resins "
    "showed variable performance with n=12 trials producing results from "
    "60% to 90% removal efficiency, with statistical significance p<0.01 "
    "in the pooled analysis."
)
BODY_2 = (
    "Short-chain PFAS removal remains technically challenging. "
    "Anion exchange resins showed superior performance for short-chain "
    "compounds compared to conventional GAC filtration in laboratory "
    "studies at controlled influent concentrations below 50 ng/L. "
    "Novel magnetic polymer composites demonstrated 92% adsorption "
    "capacity for PFBS and PFHxA in batch experiments with 30 minute "
    "contact times at circumneutral pH conditions."
)
BODY_3 = (
    "Cost-effectiveness analysis of household PFAS filtration. "
    "Point-of-use filters averaged low per-gallon treated costs across "
    "manufacturer-reported lifetime durations, with under-sink units "
    "producing lower per-gallon costs than faucet-mount alternatives in "
    "peer-reviewed evaluations. Whole-house systems demand higher upfront "
    "investment but deliver lower long-term operating costs at typical "
    "household water consumption rates of 300-400 gallons per day."
)


FACTS_1 = [
    valid_fact(
        "GAC achieved 85% removal of long-chain PFAS compounds in 10 minute "
        "contact time across independent trials at typical residential concentrations"
    ),
    valid_fact(
        "Reverse osmosis membranes performed better at 95% CI 91-97% but "
        "required pressurization and produced substantial reject water volumes"
    ),
    valid_fact(
        "Ion exchange resins showed variable performance with n=12 trials "
        "producing results from 60% to 90% removal efficiency"
    ),
    {
        "statement": "GAC removes PFAS effectively",
        "direct_quote": "GAC removes PFAS",
        "relevance_score": 0.6,
    },  # short quote → filtered
    {
        "statement": "Site uses cookies for tracking across the advertising network",
        "direct_quote": (
            "this website uses cookies to track the user across advertising "
            "services and apply our privacy policy worldwide"
        ),
        "relevance_score": 0.5,
    },  # cookie → filtered
]
FACTS_2 = [
    valid_fact(
        "Anion exchange resins showed superior performance for short-chain "
        "compounds compared to conventional GAC filtration in laboratory studies"
    ),
    valid_fact(
        "Novel magnetic polymer composites demonstrated 92% adsorption "
        "capacity for PFBS and PFHxA in batch experiments with 30 minute contact times"
    ),
    {
        "statement": "too short",
        "direct_quote": "x y z a b c d e f g h i j k l m n o p",
        "relevance_score": 0.6,
    },  # short statement → filtered
]
FACTS_3 = [
    valid_fact(
        "Point-of-use filters averaged low per-gallon treated costs across "
        "manufacturer-reported lifetime durations with under-sink units producing "
        "lower per-gallon costs"
    ),
    valid_fact(
        "Whole-house systems demand higher upfront investment but deliver lower "
        "long-term operating costs at typical household water consumption rates "
        "of 300-400 gallons per day"
    ),
]


def main() -> int:
    tmp = Path(tempfile.mkdtemp())
    try:
        db = tmp / "stress.db"
        store = MeshStore.open(db)
        ws = store.create_workspace(
            name="pfas_stress",
            root_question="How do PFAS filters work?",
        )

        print("=== Stage 1: ingest 3 sources ===")
        t0 = time.monotonic()
        src_files: list[str] = []
        for i, body in enumerate([BODY_1, BODY_2, BODY_3], start=1):
            p = tmp / f"source_{i}.md"
            p.write_text(body, encoding="utf-8")
            src_id, was_new = ingest_file(
                store=store, workspace_id=ws, file_path=p,
                url=f"https://example.com/src{i}",
            )
            assert was_new is True
            src_files.append(src_id)
            print(f"  ingested source_{i}: {src_id}")
        ingest_elapsed = time.monotonic() - t0
        print(f"  total: {ingest_elapsed:.2f}s")

        print()
        print("=== Stage 2: claim extraction with mock LLM ===")
        batches = [
            mk_batch("https://example.com/src1", FACTS_1),
            mk_batch("https://example.com/src2", FACTS_2),
            mk_batch("https://example.com/src3", FACTS_3),
        ]
        client = MockClient(batches)
        t1 = time.monotonic()
        total_inserted = 0
        total_seen = 0
        for src_id in src_files:
            result = asyncio.run(extract_claims_from_source(
                client=client, store=store, workspace_id=ws,
                source_page_id=src_id,
                query="How do household PFAS filters compare?",
            ))
            total_inserted += len(result.inserted_claim_ids)
            total_seen += result.total_facts_seen
            print(
                f"  {src_id}: inserted={len(result.inserted_claim_ids)}, "
                f"seen={result.total_facts_seen}, skipped={result.skipped}"
            )
        extract_elapsed = time.monotonic() - t1
        print(
            f"  total: {extract_elapsed:.1f}s for {total_inserted} claims "
            f"({total_seen} facts seen)"
        )

        print()
        print("=== Stage 3: consistency checks ===")
        stats = store.workspace_stats(ws)
        print(
            f"  workspace: source_count={stats['source_count']}, "
            f"claim_count={stats['claim_count']}"
        )
        print(
            f"  tiers: GOLD={stats['gold_claims']}, "
            f"SILVER={stats['silver_claims']}, "
            f"BRONZE={stats['bronze_claims']}"
        )

        vec_count = store._conn.execute(
            "SELECT COUNT(*) FROM vec_claims"
        ).fetchone()[0]
        map_count = store._conn.execute(
            "SELECT COUNT(*) FROM vec_claims_mapping"
        ).fetchone()[0]
        print(f"  vec_claims={vec_count}, vec_claims_mapping={map_count}")
        assert vec_count == total_inserted, (
            f"vec_claims {vec_count} != inserted {total_inserted}"
        )
        assert map_count == total_inserted, (
            f"mapping {map_count} != inserted {total_inserted}"
        )
        assert stats["claim_count"] == total_inserted, (
            f"workspace.claim_count {stats['claim_count']} != inserted {total_inserted}"
        )

        print()
        print("=== Stage 4: KNN lookup ===")
        from src.utils.embedding_service import embed_texts
        q = embed_texts([
            "reverse osmosis membrane performance confidence interval"
        ])[0]
        q_arr = np.asarray(q, dtype=np.float32)
        hits = store.search_claims_by_vector(
            workspace_id=ws, query_embedding=q_arr, k=5,
        )
        print("  top-5 hits for 'reverse osmosis membrane performance':")
        for i, (clm_id, dist) in enumerate(hits):
            clm = store.get_claim(clm_id)
            print(
                f"    {i+1}. dist={dist:.3f} tier={clm['tier']} "
                f"stmt={clm['statement'][:60]}"
            )
        top_clm = store.get_claim(hits[0][0])
        quote_lower = top_clm["direct_quote"].lower()
        assert (
            "osmosis" in quote_lower
            or "reverse" in quote_lower
            or "ci" in quote_lower
        ), f"Top hit doesn't look like the RO claim: {top_clm['direct_quote'][:100]}"

        print()
        print("=== Stage 5: disk + DB sizing ===")
        db_size = db.stat().st_size
        sources_dir = store.sources_dir
        md_files = list(sources_dir.glob("*.md"))
        total_md_bytes = sum(f.stat().st_size for f in md_files)
        print(f"  mesh.db: {db_size / 1024:.1f} KB")
        print(
            f"  sources/: {len(md_files)} files, "
            f"{total_md_bytes / 1024:.1f} KB total"
        )

        print()
        print("=== Stage 6: re-open + verify persistence ===")
        store.close()
        store2 = MeshStore.open(db)
        stats2 = store2.workspace_stats(ws)
        vec_count2 = store2._conn.execute(
            "SELECT COUNT(*) FROM vec_claims"
        ).fetchone()[0]
        print(
            f"  after reopen: claims={stats2['claim_count']}, "
            f"vec_claims={vec_count2}"
        )
        assert stats2["claim_count"] == total_inserted
        assert vec_count2 == total_inserted

        # KNN still works after reopen
        hits2 = store2.search_claims_by_vector(
            workspace_id=ws, query_embedding=q_arr, k=3,
        )
        assert len(hits2) == 3, f"Expected 3 hits after reopen, got {len(hits2)}"
        store2.close()

        print()
        print("=== STRESS TEST PASSED ===")
        print(
            f"  {stats['source_count']} sources, "
            f"{stats['claim_count']} claims, "
            f"{vec_count} vectors"
        )
        print(f"  ingest: {ingest_elapsed:.1f}s, extract: {extract_elapsed:.1f}s")
        return 0

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    raise SystemExit(main())
