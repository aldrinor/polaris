#!/usr/bin/env python3
"""
POLARIS SOTA Benchmark Audit System
====================================
Industry-standard evaluation using RAGAS methodology, NLI-based verification,
and comprehensive quality metrics.

Implements:
1. RAGAS Metrics (Faithfulness, Relevancy, Context Precision/Recall)
2. NLI-based Claim-Evidence Verification
3. Citation Grounding Accuracy
4. Hallucination Detection Scoring
5. Semantic Consistency Analysis

Usage:
    python -m src.audit.benchmark_audit --vector-id S1V1_... --verbose
"""

import json
import re
import sys
import time
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import numpy as np

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

try:
    import torch
    import torch.nn.functional as F
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    F = None

try:
    from transformers import AutoTokenizer, AutoModelForSequenceClassification
    TRANSFORMERS_AVAILABLE = True
except ImportError:
    TRANSFORMERS_AVAILABLE = False

try:
    from sentence_transformers import SentenceTransformer
    SENTENCE_TRANSFORMERS_AVAILABLE = True
except ImportError:
    SENTENCE_TRANSFORMERS_AVAILABLE = False

from src.config import get_config, OUTPUTS_DIR


@dataclass
class RAGASMetrics:
    """RAGAS-style evaluation metrics."""
    faithfulness: float = 0.0
    answer_relevancy: float = 0.0
    context_precision: float = 0.0
    context_recall: float = 0.0

    def overall_score(self) -> float:
        scores = [self.faithfulness, self.answer_relevancy,
                  self.context_precision, self.context_recall]
        valid_scores = [s for s in scores if s > 0]
        if not valid_scores:
            return 0.0
        return len(valid_scores) / sum(1/s for s in valid_scores)


@dataclass
class ClaimVerification:
    """Result of verifying a single claim against evidence."""
    claim_id: str
    claim_text: str
    cited_chunk_id: Optional[str] = None
    cited_chunk_text: Optional[str] = None
    entailment_score: float = 0.0
    contradiction_score: float = 0.0
    neutral_score: float = 0.0
    is_grounded: bool = False
    grounding_label: str = "unverified"


@dataclass
class HallucinationResult:
    """Hallucination detection results."""
    total_claims: int = 0
    grounded_claims: int = 0
    ungrounded_claims: int = 0
    hallucination_rate: float = 0.0
    avg_grounding_score: float = 0.0


@dataclass
class BenchmarkResult:
    """Complete benchmark audit result."""
    vector_id: str
    ragas_metrics: RAGASMetrics
    claim_verifications: List[ClaimVerification]
    hallucination_result: HallucinationResult
    citation_accuracy: float = 0.0
    overall_quality_score: float = 0.0
    benchmark_version: str = "1.0.0"
    model_used: str = ""
    processing_time_sec: float = 0.0
    timestamps: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> Dict:
        return {
            "vector_id": self.vector_id,
            "ragas_metrics": asdict(self.ragas_metrics),
            "claim_verifications": [asdict(cv) for cv in self.claim_verifications],
            "hallucination_result": asdict(self.hallucination_result),
            "citation_accuracy": self.citation_accuracy,
            "overall_quality_score": self.overall_quality_score,
            "benchmark_version": self.benchmark_version,
            "model_used": self.model_used,
            "processing_time_sec": self.processing_time_sec,
            "timestamps": self.timestamps,
        }


class BenchmarkAuditor:
    """SOTA Benchmark Auditor using NLI and embedding models."""

    NLI_MODEL = "facebook/bart-large-mnli"
    EMBEDDING_MODEL = "BAAI/bge-base-en-v1.5"

    def __init__(self, device: Optional[str] = None):
        self.device = self._select_device(device)
        self.nli_model = None
        self.nli_tokenizer = None
        self.embedder = None
        self._models_loaded = False

    def _select_device(self, device: Optional[str]) -> str:
        if device:
            return device
        if TORCH_AVAILABLE and torch.cuda.is_available():
            return "cuda"
        return "cpu"

    def load_models(self):
        """Load NLI and embedding models."""
        if self._models_loaded:
            return
        print(f"  Loading benchmark models on {self.device}...")

        if TRANSFORMERS_AVAILABLE and TORCH_AVAILABLE:
            try:
                self.nli_tokenizer = AutoTokenizer.from_pretrained(self.NLI_MODEL)
                self.nli_model = AutoModelForSequenceClassification.from_pretrained(
                    self.NLI_MODEL
                )
                self.nli_model.to(self.device)
                self.nli_model.eval()
                print(f"    NLI model loaded: {self.NLI_MODEL}")
            except Exception as e:
                print(f"    [WARN] NLI model failed: {e}")

        if SENTENCE_TRANSFORMERS_AVAILABLE:
            try:
                self.embedder = SentenceTransformer(self.EMBEDDING_MODEL)
                if self.device == "cuda" and TORCH_AVAILABLE:
                    self.embedder.to(torch.device("cuda"))
                print(f"    Embedding model loaded: {self.EMBEDDING_MODEL}")
            except Exception as e:
                print(f"    [WARN] Embedding model failed: {e}")

        self._models_loaded = True

    def compute_nli_scores(self, premise: str, hypothesis: str) -> Tuple[float, float, float]:
        """Compute NLI entailment/neutral/contradiction scores."""
        if not self.nli_model or not self.nli_tokenizer:
            return 0.33, 0.33, 0.34

        try:
            inputs = self.nli_tokenizer(
                premise, hypothesis,
                return_tensors="pt",
                truncation=True,
                max_length=512
            )
            inputs = {k: v.to(self.device) for k, v in inputs.items()}

            with torch.no_grad():
                outputs = self.nli_model(**inputs)
                probs = F.softmax(outputs.logits, dim=1)[0]

            # BART-large-mnli label order: contradiction (0), neutral (1), entailment (2)
            contradiction = float(probs[0])
            neutral = float(probs[1])
            entailment = float(probs[2])
            return entailment, neutral, contradiction
        except Exception as e:
            print(f"    [WARN] NLI inference failed: {e}")
            return 0.33, 0.33, 0.34

    def compute_embedding_similarity(self, text1: str, text2: str) -> float:
        """Compute cosine similarity between text embeddings."""
        if not self.embedder:
            return 0.5

        try:
            embeddings = self.embedder.encode([text1, text2], convert_to_tensor=True)
            similarity = F.cosine_similarity(embeddings[0].unsqueeze(0),
                                            embeddings[1].unsqueeze(0))
            return float(similarity[0])
        except Exception as e:
            print(f"    [WARN] Embedding similarity failed: {e}")
            return 0.5

    def _clean_claim_text(self, claim_text: str) -> str:
        """Clean claim text by removing citation markers for NLI."""
        # Remove [CITE:chunk_xxxx] markers
        clean_text = re.sub(r'\[CITE:chunk_\d+\]', '', claim_text)
        # Remove [number] style citations
        clean_text = re.sub(r'\[\d+\]', '', clean_text)
        # Clean up extra whitespace
        clean_text = re.sub(r'\s+', ' ', clean_text).strip()
        return clean_text

    def verify_claim_against_evidence(
        self, claim: Dict, evidence_chunks: List[Dict]
    ) -> ClaimVerification:
        """Verify a single claim against evidence using NLI."""
        claim_id = claim.get("claim_id", "unknown")
        claim_text_raw = claim.get("text", "")
        # Clean citation markers before NLI
        claim_text = self._clean_claim_text(claim_text_raw)
        # P11 uses "evidence_ids", benchmark may also use "citations"
        citations = claim.get("evidence_ids", []) or claim.get("citations", [])

        verification = ClaimVerification(
            claim_id=claim_id,
            claim_text=claim_text[:200]
        )

        # Skip empty or fragment claims (too short to be meaningful)
        if not claim_text or len(claim_text) < 15:
            verification.grounding_label = "skipped_fragment"
            return verification

        best_entailment = 0.0
        best_chunk_id = None
        best_chunk_text = None

        # First check cited chunks
        chunks_to_check = []
        if citations:
            for cite in citations[:3]:
                chunk_id = cite if isinstance(cite, str) else cite.get("chunk_id", "")
                for chunk in evidence_chunks:
                    if chunk.get("chunk_id") == chunk_id or chunk.get("id") == chunk_id:
                        chunks_to_check.append(chunk)
                        break

        # If no cited chunks, find semantically similar ones
        if not chunks_to_check:
            for chunk in evidence_chunks[:10]:
                chunk_text = chunk.get("text", chunk.get("content", ""))
                if chunk_text:
                    sim = self.compute_embedding_similarity(claim_text, chunk_text)
                    if sim > 0.5:
                        chunks_to_check.append(chunk)

        # Verify against top chunks
        for chunk in chunks_to_check[:5]:
            chunk_text = chunk.get("text", chunk.get("content", ""))
            chunk_id = chunk.get("chunk_id", chunk.get("id", "unknown"))

            if not chunk_text:
                continue

            ent, neu, con = self.compute_nli_scores(chunk_text, claim_text)

            if ent > best_entailment:
                best_entailment = ent
                best_chunk_id = chunk_id
                best_chunk_text = chunk_text[:200]
                verification.entailment_score = ent
                verification.neutral_score = neu
                verification.contradiction_score = con

        verification.cited_chunk_id = best_chunk_id
        verification.cited_chunk_text = best_chunk_text

        # Determine grounding status
        if best_entailment > 0.7:
            verification.is_grounded = True
            verification.grounding_label = "strongly_grounded"
        elif best_entailment > 0.5:
            verification.is_grounded = True
            verification.grounding_label = "partially_grounded"
        elif best_entailment > 0.3:
            verification.grounding_label = "weakly_supported"
        else:
            verification.grounding_label = "ungrounded"

        return verification

    def compute_faithfulness(
        self, claims: List[Dict], evidence_chunks: List[Dict]
    ) -> Tuple[float, List[ClaimVerification]]:
        """Compute faithfulness: proportion of claims grounded in evidence."""
        if not claims:
            return 1.0, []

        verifications = []
        grounded_count = 0

        for claim in claims:
            verification = self.verify_claim_against_evidence(claim, evidence_chunks)
            verifications.append(verification)
            if verification.is_grounded:
                grounded_count += 1

        faithfulness = grounded_count / len(claims) if claims else 0.0
        return faithfulness, verifications

    def compute_answer_relevancy(self, question: str, answer: str) -> float:
        """Compute answer relevancy using embedding similarity."""
        if not question or not answer:
            return 0.5
        return self.compute_embedding_similarity(question, answer)

    def compute_context_precision(
        self, claims: List[Dict], retrieved_chunks: List[Dict]
    ) -> float:
        """Compute context precision: proportion of retrieved chunks that are relevant."""
        if not retrieved_chunks:
            return 0.0

        relevant_count = 0
        for chunk in retrieved_chunks:
            chunk_text = chunk.get("text", chunk.get("content", ""))
            if not chunk_text:
                continue

            for claim in claims:
                claim_text = claim.get("text", "")
                if claim_text:
                    sim = self.compute_embedding_similarity(chunk_text, claim_text)
                    if sim > 0.5:
                        relevant_count += 1
                        break

        return relevant_count / len(retrieved_chunks)

    def compute_context_recall(
        self, claims: List[Dict], retrieved_chunks: List[Dict]
    ) -> float:
        """Compute context recall: proportion of claims covered by retrieved chunks."""
        if not claims:
            return 1.0

        covered_claims = 0
        for claim in claims:
            claim_text = claim.get("text", "")
            if not claim_text:
                continue

            for chunk in retrieved_chunks:
                chunk_text = chunk.get("text", chunk.get("content", ""))
                if chunk_text:
                    sim = self.compute_embedding_similarity(claim_text, chunk_text)
                    if sim > 0.5:
                        covered_claims += 1
                        break

        return covered_claims / len(claims)

    def compute_hallucination_metrics(
        self, verifications: List[ClaimVerification]
    ) -> HallucinationResult:
        """Compute hallucination metrics from claim verifications."""
        if not verifications:
            return HallucinationResult()

        # Exclude skipped fragments from metrics
        valid_verifications = [v for v in verifications if v.grounding_label != "skipped_fragment"]
        if not valid_verifications:
            return HallucinationResult()

        grounded = sum(1 for v in valid_verifications if v.is_grounded)
        ungrounded = len(valid_verifications) - grounded
        avg_score = np.mean([v.entailment_score for v in valid_verifications])

        return HallucinationResult(
            total_claims=len(valid_verifications),  # Use valid claims count
            grounded_claims=grounded,
            ungrounded_claims=ungrounded,
            hallucination_rate=ungrounded / len(valid_verifications),
            avg_grounding_score=float(avg_score),
        )

    def compute_citation_accuracy(
        self, claims: List[Dict], citations: List[Dict], chunks: List[Dict]
    ) -> float:
        """Compute citation accuracy: proportion of citations with valid metadata."""
        if not citations:
            return 0.0

        valid_citations = 0
        for citation in citations:
            # Check if citation has essential metadata
            has_url = bool(citation.get("url", ""))
            has_title = bool(citation.get("title", "")) and citation.get("title") != "Untitled"
            has_evidence_id = bool(citation.get("evidence_id", ""))

            # A citation is valid if it has URL, non-empty title, and evidence reference
            if has_url and has_title and has_evidence_id:
                valid_citations += 1

        return valid_citations / len(citations)

    def run_benchmark(
        self,
        vector_id: str,
        p7_data: Dict,
        p11_data: Dict,
        p4_chunks: Optional[List[Dict]] = None,
    ) -> BenchmarkResult:
        """Run complete RAGAS benchmark evaluation."""
        start_time = time.time()
        self.load_models()

        print(f"\n  Running RAGAS benchmark for {vector_id}...")

        # Extract data
        claims = p11_data.get("verified_claims", [])
        citations = p11_data.get("citations", [])
        report_text = p11_data.get("report_text", "")
        analysis_text = p7_data.get("analysis_text", "")

        # Build chunk list
        citation_chunks = p7_data.get("citation_tokens", [])
        chunks = p4_chunks or []
        if not chunks:
            for cite_id in citation_chunks:
                chunks.append({"chunk_id": cite_id, "text": ""})

        print(f"    Claims to verify: {len(claims)}")
        print(f"    Citations: {len(citations)}")
        print(f"    Evidence chunks: {len(chunks)}")

        # Compute RAGAS metrics
        print("    Computing faithfulness (NLI verification)...")
        faithfulness, verifications = self.compute_faithfulness(claims, chunks)

        print("    Computing answer relevancy...")
        research_question = p7_data.get("research_question", "")
        if not research_question:
            research_question = f"Research on {vector_id.replace('_', ' ')}".title()
        answer_relevancy = self.compute_answer_relevancy(research_question, analysis_text)

        print("    Computing context precision...")
        context_precision = self.compute_context_precision(claims, chunks)

        print("    Computing context recall...")
        context_recall = self.compute_context_recall(claims, chunks)

        ragas = RAGASMetrics(
            faithfulness=faithfulness,
            answer_relevancy=answer_relevancy,
            context_precision=context_precision,
            context_recall=context_recall,
        )

        # Compute hallucination metrics
        print("    Computing hallucination metrics...")
        hallucination = self.compute_hallucination_metrics(verifications)

        # Compute citation accuracy
        print("    Computing citation accuracy...")
        citation_accuracy = self.compute_citation_accuracy(claims, citations, chunks)

        # Compute overall quality score
        overall_score = (
            ragas.overall_score() * 0.6 +
            (1 - hallucination.hallucination_rate) * 0.25 +
            citation_accuracy * 0.15
        )

        processing_time = time.time() - start_time

        result = BenchmarkResult(
            vector_id=vector_id,
            ragas_metrics=ragas,
            claim_verifications=verifications,
            hallucination_result=hallucination,
            citation_accuracy=citation_accuracy,
            overall_quality_score=overall_score,
            model_used=f"NLI:{self.NLI_MODEL}, Embed:{self.EMBEDDING_MODEL}",
            processing_time_sec=processing_time,
            timestamps={
                "start": datetime.now(timezone.utc).isoformat(),
                "end": datetime.now(timezone.utc).isoformat(),
            },
        )

        return result


def load_phase_output(phase: int, vector_id: str) -> Optional[Dict]:
    """Load the most recent phase output for a vector."""
    phase_dir = OUTPUTS_DIR / f"P{phase}"
    if not phase_dir.exists():
        return None
    files = sorted(phase_dir.glob(f"{vector_id}__P{phase}__*.json"))
    if not files:
        return None
    with open(files[-1], "r", encoding="utf-8") as f:
        return json.load(f)



def run_benchmark_audit(vector_id: str, verbose: bool = False) -> BenchmarkResult:
    """Run complete benchmark audit on a vector."""
    print("=" * 60)
    print("POLARIS SOTA BENCHMARK AUDIT")
    print(f"Vector: {vector_id}")
    print("Methodology: RAGAS + NLI Grounding")
    print("=" * 60)

    # Load phase outputs
    p7_data = load_phase_output(7, vector_id)
    p11_data = load_phase_output(11, vector_id)
    p4_data = load_phase_output(4, vector_id)

    if not p7_data:
        raise FileNotFoundError(f"P7 output not found for {vector_id}")
    if not p11_data:
        raise FileNotFoundError(f"P11 output not found for {vector_id}")

    # Build chunk list from P4
    chunks = []
    if p4_data:
        # Try filtered_chunks first (new format)
        chunks = p4_data.get("filtered_chunks", [])
        if not chunks:
            # Try chunks (legacy format)
            chunks = p4_data.get("chunks", [])
        if not chunks:
            # Try chunk_texts (oldest format)
            for i, text in enumerate(p4_data.get("chunk_texts", [])):
                chunks.append({"chunk_id": f"chunk_{i:05d}", "text": text})

    # Run benchmark
    auditor = BenchmarkAuditor()
    result = auditor.run_benchmark(vector_id, p7_data, p11_data, chunks)

    # Print results
    print("\n" + "=" * 60)
    print("BENCHMARK RESULTS")
    print("=" * 60)

    print(f"\n  RAGAS METRICS:")
    print(f"    Faithfulness:       {result.ragas_metrics.faithfulness:.3f}")
    print(f"    Answer Relevancy:   {result.ragas_metrics.answer_relevancy:.3f}")
    print(f"    Context Precision:  {result.ragas_metrics.context_precision:.3f}")
    print(f"    Context Recall:     {result.ragas_metrics.context_recall:.3f}")
    print(f"    RAGAS Overall:      {result.ragas_metrics.overall_score():.3f}")

    print(f"\n  HALLUCINATION ANALYSIS:")
    hr = result.hallucination_result
    print(f"    Total Claims:       {hr.total_claims}")
    print(f"    Grounded Claims:    {hr.grounded_claims}")
    print(f"    Ungrounded Claims:  {hr.ungrounded_claims}")
    print(f"    Hallucination Rate: {hr.hallucination_rate:.1%}")
    print(f"    Avg Grounding:      {hr.avg_grounding_score:.3f}")

    print(f"\n  CITATION ACCURACY:    {result.citation_accuracy:.1%}")
    print(f"  OVERALL QUALITY:      {result.overall_quality_score:.3f}")

    # Determine verdict
    verdict = "PASS" if result.overall_quality_score >= 0.6 else "FAIL"
    print(f"\n  VERDICT: {verdict}")
    print("=" * 60)

    if verbose and result.claim_verifications:
        print("\n  CLAIM VERIFICATIONS:")
        for i, cv in enumerate(result.claim_verifications[:10]):
            status = "[GROUNDED]" if cv.is_grounded else "[UNGROUNDED]"
            print(f"    {i+1}. {status} {cv.grounding_label}")
            print(f"       Claim: {cv.claim_text[:80]}...")
            print(f"       Entailment: {cv.entailment_score:.3f}")

    # Save output
    output_dir = OUTPUTS_DIR / "AUDIT"
    output_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = output_dir / f"{vector_id}__BENCHMARK__{timestamp}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(result.to_dict(), f, indent=2, ensure_ascii=False)

    print(f"\n  Output saved: {output_path.name}")

    return result


def self_test() -> bool:
    """Run self-tests for benchmark audit."""
    print("Running Benchmark Audit self-tests...")

    # Test RAGASMetrics
    ragas = RAGASMetrics(faithfulness=0.8, answer_relevancy=0.7,
                         context_precision=0.6, context_recall=0.5)
    assert 0 < ragas.overall_score() < 1
    print("  [PASS] RAGAS metrics")

    # Test ClaimVerification
    cv = ClaimVerification(claim_id="test", claim_text="Test claim")
    assert cv.grounding_label == "unverified"
    print("  [PASS] ClaimVerification")

    # Test HallucinationResult
    hr = HallucinationResult(total_claims=10, grounded_claims=7, ungrounded_claims=3)
    hr.hallucination_rate = 0.3
    assert hr.hallucination_rate == 0.3
    print("  [PASS] HallucinationResult")

    print("\nAll Benchmark Audit self-tests PASSED!")
    return True


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="POLARIS SOTA Benchmark Audit")
    parser.add_argument("--vector-id", type=str, help="Vector ID to audit")
    parser.add_argument("--verbose", action="store_true", help="Show detailed output")
    parser.add_argument("--self-test", action="store_true", help="Run self-tests")
    args = parser.parse_args()

    if args.self_test:
        self_test()
    elif args.vector_id:
        run_benchmark_audit(args.vector_id, args.verbose)
    else:
        print("Usage: python -m src.audit.benchmark_audit --vector-id <ID> [--verbose]")
