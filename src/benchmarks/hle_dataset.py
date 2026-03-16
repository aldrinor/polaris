#!/usr/bin/env python3
"""
HLE (Humanity's Last Exam) Dataset Handler
===========================================
Manages access to the HLE benchmark dataset for POLARIS evaluation.

The HLE benchmark consists of 2,500+ expert-level questions across multiple
domains, designed to test reasoning and knowledge at the frontier of human
expertise.

Source: https://lastexam.ai
Paper: https://arxiv.org/abs/2501.14249

Usage:
    from src.benchmarks.hle_dataset import HLEDataset

    dataset = HLEDataset()
    questions = dataset.get_sample(n=50)
    for q in questions:
        print(q.question_text)
"""

import json
import logging
import random
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import UTC, datetime

logger = logging.getLogger(__name__)

# Dataset paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
DATA_DIR = PROJECT_ROOT / "data" / "benchmarks"
HLE_CACHE_FILE = DATA_DIR / "hle_dataset_cache.json"


@dataclass
class HLEQuestion:
    """A single question from the Humanity's Last Exam benchmark."""

    question_id: str
    question_text: str
    subject: str
    difficulty: str = "expert"  # HLE questions are all expert-level
    answer_type: str = "open"  # open, multiple_choice, numeric
    ground_truth: Optional[str] = None  # Hidden for public questions
    ground_truth_explanation: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    # For multimodal questions
    has_image: bool = False
    image_path: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary format."""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HLEQuestion":
        """Create from dictionary."""
        return cls(
            question_id=data.get("question_id", data.get("id", "")),
            question_text=data.get("question_text", data.get("question", "")),
            subject=data.get("subject", data.get("category", "general")),
            difficulty=data.get("difficulty", "expert"),
            answer_type=data.get("answer_type", "open"),
            ground_truth=data.get("ground_truth", data.get("answer")),
            ground_truth_explanation=data.get("ground_truth_explanation", data.get("explanation")),
            metadata=data.get("metadata", {}),
            has_image=data.get("has_image", False),
            image_path=data.get("image_path"),
        )


@dataclass
class HLEDatasetStats:
    """Statistics about the HLE dataset."""

    total_questions: int = 0
    subjects: Dict[str, int] = field(default_factory=dict)
    text_only: int = 0
    multimodal: int = 0
    cached_date: Optional[str] = None


class HLEDataset:
    """
    Handler for the Humanity's Last Exam (HLE) benchmark dataset.

    HLE is a multi-modal benchmark at the frontier of human knowledge,
    consisting of 2,500 expert-level questions across dozens of subjects
    including mathematics, humanities, and natural sciences.

    Attributes:
        questions: List of HLE questions loaded from cache or seed data
        stats: Dataset statistics
    """

    # Subject categories in HLE
    SUBJECTS = [
        "mathematics",
        "physics",
        "chemistry",
        "biology",
        "computer_science",
        "medicine",
        "law",
        "economics",
        "history",
        "philosophy",
        "linguistics",
        "psychology",
        "engineering",
        "astronomy",
        "earth_science",
        "other",
    ]

    def __init__(self, cache_path: Optional[Path] = None):
        """
        Initialize the HLE dataset handler.

        Args:
            cache_path: Path to cached dataset file. Defaults to data/benchmarks/hle_dataset_cache.json
        """
        self.cache_path = cache_path or HLE_CACHE_FILE
        self.questions: List[HLEQuestion] = []
        self.stats = HLEDatasetStats()

        # Ensure data directory exists
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        # Load dataset
        self._load_dataset()

    def _load_dataset(self) -> None:
        """Load dataset from cache or initialize with seed questions."""
        if self.cache_path.exists():
            self._load_from_cache()
        else:
            self._initialize_seed_dataset()
            self._save_to_cache()

        self._compute_stats()

    def _load_from_cache(self) -> None:
        """Load questions from cache file."""
        try:
            with open(self.cache_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            self.questions = [
                HLEQuestion.from_dict(q) for q in data.get("questions", [])
            ]
            self.stats.cached_date = data.get("cached_date")
            logger.info(f"Loaded {len(self.questions)} HLE questions from cache")
        except Exception as e:
            logger.warning(f"Failed to load HLE cache: {e}")
            self._initialize_seed_dataset()

    def _initialize_seed_dataset(self) -> None:
        """
        Initialize with a seed set of HLE-style questions.

        These are representative samples based on publicly available HLE
        question types and difficulty levels. Full dataset requires download
        from https://lastexam.ai.
        """
        logger.info("Initializing HLE seed dataset...")

        # Seed questions representative of HLE difficulty and style
        seed_questions = [
            # Mathematics
            {
                "question_id": "hle_seed_math_001",
                "question_text": "Consider the Riemann zeta function. Prove that the nontrivial zeros all have real part 1/2, or provide a counterexample.",
                "subject": "mathematics",
                "answer_type": "open",
                "ground_truth": "This is the Riemann Hypothesis, one of the Clay Millennium Problems. It remains unproven.",
            },
            {
                "question_id": "hle_seed_math_002",
                "question_text": "What is the asymptotic growth rate of the number of partitions of n, as proved by Hardy and Ramanujan?",
                "subject": "mathematics",
                "answer_type": "open",
                "ground_truth": "p(n) ~ (1/(4n*sqrt(3))) * exp(pi * sqrt(2n/3)) as n approaches infinity",
            },
            # Physics
            {
                "question_id": "hle_seed_physics_001",
                "question_text": "Explain the holographic principle and its implications for black hole information paradox resolution.",
                "subject": "physics",
                "answer_type": "open",
                "ground_truth": "The holographic principle suggests that all information in a volume of space can be encoded on its boundary. This implies black hole information is preserved on the event horizon, potentially resolving the information paradox through subtle correlations in Hawking radiation.",
            },
            {
                "question_id": "hle_seed_physics_002",
                "question_text": "Derive the Bekenstein-Hawking entropy formula S = A/(4*l_p^2) from first principles.",
                "subject": "physics",
                "answer_type": "open",
                "ground_truth": "Starting from the thermodynamic analogy of black hole mechanics, combine the first law dM = (kappa/8pi)dA with Hawking temperature T = hbar*kappa/(2pi*c*k_B) to derive S = k_B*c^3*A/(4*G*hbar).",
            },
            # Chemistry
            {
                "question_id": "hle_seed_chem_001",
                "question_text": "Explain the mechanism of enzyme catalysis in cytochrome P450 enzymes, including the role of the heme iron center.",
                "subject": "chemistry",
                "answer_type": "open",
                "ground_truth": "Cytochrome P450 uses a heme-thiolate coordination to activate molecular oxygen. The catalytic cycle involves substrate binding, electron transfer from NADPH via reductase, O2 binding, second electron transfer, O-O bond cleavage forming Compound I (Fe(IV)=O porphyrin radical cation), and hydrogen abstraction followed by rebound hydroxylation.",
            },
            # Biology
            {
                "question_id": "hle_seed_bio_001",
                "question_text": "Describe the molecular mechanism of CRISPR-Cas9 target recognition and DNA cleavage, including the role of PAM sequences.",
                "subject": "biology",
                "answer_type": "open",
                "ground_truth": "Cas9 first recognizes PAM (typically NGG) through the PAM-interacting domain, triggering local DNA unwinding. The guide RNA then base-pairs with the target strand, forming an R-loop. Conformational changes in HNH and RuvC nuclease domains position them for coordinated cleavage of both DNA strands 3 bp upstream of PAM.",
            },
            # Computer Science
            {
                "question_id": "hle_seed_cs_001",
                "question_text": "Prove that P != NP or explain why this problem remains unsolved despite decades of effort.",
                "subject": "computer_science",
                "answer_type": "open",
                "ground_truth": "The P vs NP problem remains unsolved. Known barriers include relativization (Baker-Gill-Solovay), natural proofs (Razborov-Rudich), and algebrization (Aaronson-Wigderson). Current techniques are provably insufficient to resolve the question.",
            },
            {
                "question_id": "hle_seed_cs_002",
                "question_text": "Describe the theoretical foundations of transformer attention mechanisms and explain why they outperform RNNs for sequence modeling.",
                "subject": "computer_science",
                "answer_type": "open",
                "ground_truth": "Transformers use scaled dot-product attention: Attention(Q,K,V) = softmax(QK^T/sqrt(d_k))V. This allows O(1) path length for any token pair vs O(n) for RNNs, enabling better gradient flow and parallelization. Multi-head attention captures different relationship types.",
            },
            # Medicine
            {
                "question_id": "hle_seed_med_001",
                "question_text": "Explain the molecular basis of immunotherapy checkpoint inhibitors and why they are effective against some cancers but not others.",
                "subject": "medicine",
                "answer_type": "open",
                "ground_truth": "Checkpoint inhibitors block PD-1/PD-L1 or CTLA-4 interactions that tumors exploit to evade T-cell attack. Efficacy correlates with tumor mutational burden (more neoantigens = better response), PD-L1 expression, and tumor microenvironment immunogenicity. Cold tumors with low immune infiltration respond poorly.",
            },
            # Economics
            {
                "question_id": "hle_seed_econ_001",
                "question_text": "Derive the Black-Scholes option pricing formula and explain its assumptions and limitations.",
                "subject": "economics",
                "answer_type": "open",
                "ground_truth": "Black-Scholes derives from Ito calculus and risk-neutral pricing: C = S*N(d1) - K*e^(-rT)*N(d2). Key assumptions: constant volatility, no dividends, log-normal returns, continuous trading, no transaction costs. Limitations include volatility smile, fat tails, and market microstructure effects.",
            },
            # Philosophy
            {
                "question_id": "hle_seed_phil_001",
                "question_text": "Evaluate Godel's incompleteness theorems and their implications for the foundations of mathematics and artificial intelligence.",
                "subject": "philosophy",
                "answer_type": "open",
                "ground_truth": "Godel showed that any consistent formal system containing arithmetic is incomplete (true but unprovable statements exist) and cannot prove its own consistency. Implications: mathematical truth transcends formal proof; Lucas-Penrose argue this limits machine intelligence, though this interpretation is disputed.",
            },
            # History
            {
                "question_id": "hle_seed_hist_001",
                "question_text": "Analyze the historiographical debates surrounding the fall of the Western Roman Empire and evaluate the relative importance of internal vs external factors.",
                "subject": "history",
                "answer_type": "open",
                "ground_truth": "Gibbon emphasized internal decay (moral decline, Christianity). Modern scholarship (Ward-Perkins, Heather) rebalances toward external factors (barbarian migrations, Hunnic pressure). Wickham and others stress transformation rather than fall. Current consensus: multi-causal collapse involving economic, military, political, and environmental factors.",
            },
        ]

        self.questions = [HLEQuestion.from_dict(q) for q in seed_questions]
        logger.info(f"Initialized with {len(self.questions)} seed questions")

    def _save_to_cache(self) -> None:
        """Save current questions to cache file."""
        try:
            data = {
                "questions": [q.to_dict() for q in self.questions],
                "cached_date": datetime.now(UTC).isoformat(),
                "version": "1.0.0",
            }
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            logger.info(f"Saved {len(self.questions)} questions to cache")
        except Exception as e:
            logger.error(f"Failed to save HLE cache: {e}")

    def _compute_stats(self) -> None:
        """Compute dataset statistics."""
        self.stats.total_questions = len(self.questions)
        self.stats.subjects = {}
        self.stats.text_only = 0
        self.stats.multimodal = 0

        for q in self.questions:
            subject = q.subject
            self.stats.subjects[subject] = self.stats.subjects.get(subject, 0) + 1
            if q.has_image:
                self.stats.multimodal += 1
            else:
                self.stats.text_only += 1

    def get_sample(
        self,
        n: int = 10,
        subjects: Optional[List[str]] = None,
        text_only: bool = True,
        seed: Optional[int] = None,
    ) -> List[HLEQuestion]:
        """
        Get a random sample of questions.

        Args:
            n: Number of questions to sample
            subjects: Filter to specific subjects (None = all)
            text_only: If True, exclude multimodal questions
            seed: Random seed for reproducibility

        Returns:
            List of sampled HLEQuestion objects
        """
        if seed is not None:
            random.seed(seed)

        # Filter questions
        candidates = self.questions

        if subjects:
            candidates = [q for q in candidates if q.subject in subjects]

        if text_only:
            candidates = [q for q in candidates if not q.has_image]

        # Sample
        n = min(n, len(candidates))
        return random.sample(candidates, n)

    def get_by_subject(self, subject: str) -> List[HLEQuestion]:
        """Get all questions for a specific subject."""
        return [q for q in self.questions if q.subject == subject]

    def get_by_id(self, question_id: str) -> Optional[HLEQuestion]:
        """Get a specific question by ID."""
        for q in self.questions:
            if q.question_id == question_id:
                return q
        return None

    def add_questions(self, questions: List[HLEQuestion]) -> None:
        """
        Add questions to the dataset.

        Args:
            questions: List of HLEQuestion objects to add
        """
        existing_ids = {q.question_id for q in self.questions}

        for q in questions:
            if q.question_id not in existing_ids:
                self.questions.append(q)
                existing_ids.add(q.question_id)

        self._compute_stats()
        self._save_to_cache()

    def import_from_json(self, file_path: Path) -> int:
        """
        Import questions from a JSON file.

        Args:
            file_path: Path to JSON file with question data

        Returns:
            Number of questions imported
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)

            questions = data if isinstance(data, list) else data.get("questions", [])
            new_questions = [HLEQuestion.from_dict(q) for q in questions]

            initial_count = len(self.questions)
            self.add_questions(new_questions)

            return len(self.questions) - initial_count
        except Exception as e:
            logger.error(f"Failed to import questions: {e}")
            return 0

    def get_stats(self) -> Dict[str, Any]:
        """Get dataset statistics as a dictionary."""
        return {
            "total_questions": self.stats.total_questions,
            "subjects": self.stats.subjects,
            "text_only": self.stats.text_only,
            "multimodal": self.stats.multimodal,
            "cached_date": self.stats.cached_date,
        }


def self_test() -> bool:
    """Run self-tests for HLE dataset."""
    print("Running HLE Dataset self-tests...")

    # Test initialization
    dataset = HLEDataset()
    assert dataset.stats.total_questions > 0
    print(f"  [PASS] Dataset initialized with {dataset.stats.total_questions} questions")

    # Test sampling
    sample = dataset.get_sample(n=5, seed=42)
    assert len(sample) == 5
    print(f"  [PASS] Sampling works (got {len(sample)} questions)")

    # Test subject filtering
    math_qs = dataset.get_by_subject("mathematics")
    assert all(q.subject == "mathematics" for q in math_qs)
    print(f"  [PASS] Subject filtering works ({len(math_qs)} math questions)")

    # Test question retrieval
    if dataset.questions:
        first_id = dataset.questions[0].question_id
        q = dataset.get_by_id(first_id)
        assert q is not None
        assert q.question_id == first_id
        print("  [PASS] Question retrieval by ID works")

    # Test stats
    stats = dataset.get_stats()
    assert "total_questions" in stats
    assert "subjects" in stats
    print("  [PASS] Statistics generation works")

    print("\nAll HLE Dataset self-tests PASSED!")
    return True


if __name__ == "__main__":
    self_test()
