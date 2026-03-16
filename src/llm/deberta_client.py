"""
POLARIS DeBERTa NLI Client

Local DeBERTa model for Natural Language Inference.
Uses microsoft/deberta-base-mnli (free, local inference).

Replaces expensive LLM calls for claim verification.
725,600 comparisons × $0 = $0 (vs $10+ with Gemini)
"""

import logging
from typing import Tuple, Optional, List
from functools import lru_cache

logger = logging.getLogger(__name__)

# Flag to track if model is available
_model_available = False
_model = None
_tokenizer = None


def _load_model():
    """
    Load DeBERTa model lazily.

    Uses microsoft/deberta-base-mnli for NLI.
    (Previous model microsoft/deberta-v3-base-mnli-fever-anli was removed from HuggingFace)
    """
    global _model_available, _model, _tokenizer

    if _model is not None:
        return True

    try:
        from transformers import AutoModelForSequenceClassification, AutoTokenizer
        import torch

        model_name = "microsoft/deberta-base-mnli"

        logger.info(f"Loading DeBERTa model: {model_name}")

        _tokenizer = AutoTokenizer.from_pretrained(model_name)
        _model = AutoModelForSequenceClassification.from_pretrained(model_name)

        # Move to GPU if available
        if torch.cuda.is_available():
            _model = _model.cuda()
            logger.info("DeBERTa loaded on GPU")
        else:
            logger.info("DeBERTa loaded on CPU")

        _model.eval()
        _model_available = True
        return True

    except ImportError as e:
        logger.warning(f"Transformers not installed: {e}")
        logger.warning("Install with: pip install transformers torch")
        _model_available = False
        return False

    except Exception as e:
        logger.error(f"Failed to load DeBERTa model: {e}")
        _model_available = False
        return False


def is_available() -> bool:
    """Check if DeBERTa model is available."""
    return _load_model()


class NLIModelUnavailableError(RuntimeError):
    """Raised when NLI model is not available and cannot make predictions."""
    pass


def validate_nli_available() -> bool:
    """
    Validate that NLI model is available for predictions.

    Should be called at startup (e.g., in preflight.py) to ensure
    the system can make real NLI predictions.

    Returns:
        True if model is available

    Raises:
        NLIModelUnavailableError: If model cannot be loaded
    """
    if not _load_model():
        raise NLIModelUnavailableError(
            "DeBERTa NLI model is not available. "
            "Install with: pip install transformers torch"
        )
    return True


def predict_nli(premise: str, hypothesis: str) -> Tuple[str, float]:
    """
    Predict NLI relationship between premise and hypothesis.

    Args:
        premise: The evidence text (what we know)
        hypothesis: The claim text (what we're checking)

    Returns:
        Tuple of (label, confidence)
        - label: "entailment", "neutral", or "contradiction"
        - confidence: 0.0 to 1.0

    Raises:
        NLIModelUnavailableError: If model is not available
        RuntimeError: If prediction fails

    Example:
        >>> predict_nli(
        ...     "52% of wells tested positive for coliform bacteria",
        ...     "Many private wells are contaminated"
        ... )
        ("entailment", 0.87)
    """
    if not _load_model():
        raise NLIModelUnavailableError(
            "DeBERTa NLI model is not available. "
            "Cannot make NLI predictions without the model. "
            "Install with: pip install transformers torch"
        )

    try:
        import torch

        # Tokenize
        inputs = _tokenizer(
            premise,
            hypothesis,
            return_tensors="pt",
            truncation=True,
            max_length=512,
            padding=True,
        )

        # Move to same device as model
        if torch.cuda.is_available():
            inputs = {k: v.cuda() for k, v in inputs.items()}

        # Predict
        with torch.no_grad():
            outputs = _model(**inputs)
            logits = outputs.logits

        # Get probabilities
        probs = torch.softmax(logits, dim=1)[0]

        # Label mapping (model-specific)
        # microsoft/deberta-base-mnli uses: 0=contradiction, 1=neutral, 2=entailment
        labels = ["contradiction", "neutral", "entailment"]

        # Get best prediction
        best_idx = probs.argmax().item()
        confidence = probs[best_idx].item()
        label = labels[best_idx]

        return label, confidence

    except NLIModelUnavailableError:
        raise
    except Exception as e:
        logger.error(f"DeBERTa prediction failed: {e}")
        raise RuntimeError(f"NLI prediction failed: {e}") from e


def predict_nli_batch(
    pairs: List[Tuple[str, str]],
    batch_size: int = 32,
) -> List[Tuple[str, float]]:
    """
    Batch NLI prediction for multiple premise-hypothesis pairs.

    Args:
        pairs: List of (premise, hypothesis) tuples
        batch_size: Batch size for processing

    Returns:
        List of (label, confidence) tuples

    Raises:
        NLIModelUnavailableError: If model is not available
        RuntimeError: If prediction fails
    """
    if not _load_model():
        raise NLIModelUnavailableError(
            "DeBERTa NLI model is not available. "
            "Cannot make NLI predictions without the model. "
            "Install with: pip install transformers torch"
        )

    try:
        import torch

        results = []

        for i in range(0, len(pairs), batch_size):
            batch = pairs[i:i + batch_size]
            premises = [p for p, h in batch]
            hypotheses = [h for p, h in batch]

            # Tokenize batch
            inputs = _tokenizer(
                premises,
                hypotheses,
                return_tensors="pt",
                truncation=True,
                max_length=512,
                padding=True,
            )

            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}

            # Predict batch
            with torch.no_grad():
                outputs = _model(**inputs)
                logits = outputs.logits

            probs = torch.softmax(logits, dim=1)
            labels = ["entailment", "neutral", "contradiction"]

            for j in range(len(batch)):
                best_idx = probs[j].argmax().item()
                confidence = probs[j][best_idx].item()
                results.append((labels[best_idx], confidence))

        return results

    except NLIModelUnavailableError:
        raise
    except Exception as e:
        logger.error(f"Batch prediction failed: {e}")
        raise RuntimeError(f"Batch NLI prediction failed: {e}") from e


class DeBERTaNLI:
    """
    DeBERTa NLI client class interface.

    For use in verification pipeline.
    """

    def __init__(self):
        """Initialize and load model."""
        self._loaded = _load_model()

    def is_available(self) -> bool:
        """Check if model is available."""
        return self._loaded

    def predict(self, premise: str, hypothesis: str) -> Tuple[str, float]:
        """
        Predict NLI relationship.

        Args:
            premise: Evidence text
            hypothesis: Claim text

        Returns:
            (label, confidence) tuple
        """
        return predict_nli(premise, hypothesis)

    def predict_batch(
        self,
        pairs: List[Tuple[str, str]],
        batch_size: int = 32,
    ) -> List[Tuple[str, float]]:
        """
        Batch prediction.

        Args:
            pairs: List of (premise, hypothesis) tuples
            batch_size: Batch size

        Returns:
            List of (label, confidence) tuples
        """
        return predict_nli_batch(pairs, batch_size)
