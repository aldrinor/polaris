"""
MoonViT-Style Vision Processor
===============================
Native vision processing for research images, charts, and diagrams.

KIMI K2.5 uses MoonViT (400M params) for vision. We implement equivalent
capabilities using a combination of:
1. Local vision models (CLIP, BLIP)
2. OCR (Tesseract, EasyOCR)
3. Chart understanding (ChartOCR concepts)
4. Gemini Vision API fallback
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class ImageType(Enum):
    """Type of image content."""
    PHOTO = "photo"
    CHART = "chart"
    DIAGRAM = "diagram"
    TABLE = "table"
    SCREENSHOT = "screenshot"
    DOCUMENT = "document"
    UNKNOWN = "unknown"


@dataclass
class VisionResult:
    """Result from vision processing."""
    image_type: ImageType
    extracted_text: str
    description: str
    data_points: List[Dict]
    confidence: float
    metadata: Dict[str, Any]


class VisionProcessor:
    """
    MoonViT-style vision processor.

    Provides comprehensive image understanding for research.
    """

    def __init__(
        self,
        use_local_models: bool = True,
        use_ocr: bool = True,
        use_gemini_fallback: bool = True,
        model_device: str = "cpu",
    ):
        self.use_local_models = use_local_models
        self.use_ocr = use_ocr
        self.use_gemini_fallback = use_gemini_fallback
        self.device = model_device

        # Initialize components
        self._init_ocr()
        self._init_local_models()

    def _init_ocr(self):
        """Initialize OCR engines."""
        self.tesseract = None
        self.easyocr_reader = None

        if self.use_ocr:
            try:
                import pytesseract
                self.tesseract = pytesseract
                logger.info("[VISION] Tesseract OCR initialized")
            except ImportError:
                logger.warning("[VISION] Tesseract not available")

            try:
                import easyocr
                self.easyocr_reader = easyocr.Reader(['en'])
                logger.info("[VISION] EasyOCR initialized")
            except ImportError:
                logger.warning("[VISION] EasyOCR not available")

    def _init_local_models(self):
        """Initialize local vision models."""
        self.clip_model = None
        self.blip_model = None
        self.clip_processor = None

        if self.use_local_models:
            try:
                from transformers import CLIPProcessor, CLIPModel
                self.clip_model = CLIPModel.from_pretrained("openai/clip-vit-base-patch32")
                self.clip_processor = CLIPProcessor.from_pretrained("openai/clip-vit-base-patch32")
                logger.info("[VISION] CLIP model loaded")
            except Exception as e:
                logger.warning(f"[VISION] CLIP not available: {e}")

    def classify_image_type(self, image_path: str) -> ImageType:
        """Classify the type of image."""
        if not self.clip_model:
            return ImageType.UNKNOWN

        try:
            from PIL import Image

            image = Image.open(image_path)

            # CLIP zero-shot classification
            labels = ["a photograph", "a chart or graph", "a diagram",
                     "a table", "a screenshot", "a document page"]

            inputs = self.clip_processor(
                text=labels,
                images=image,
                return_tensors="pt",
                padding=True
            )

            outputs = self.clip_model(**inputs)
            probs = outputs.logits_per_image.softmax(dim=1)

            idx = probs.argmax().item()
            type_map = [ImageType.PHOTO, ImageType.CHART, ImageType.DIAGRAM,
                       ImageType.TABLE, ImageType.SCREENSHOT, ImageType.DOCUMENT]

            return type_map[idx]

        except Exception as e:
            logger.warning(f"[VISION] Classification failed: {e}")
            return ImageType.UNKNOWN

    def extract_text_ocr(self, image_path: str) -> Tuple[str, float]:
        """Extract text using OCR."""
        text = ""
        confidence = 0.0

        # Try EasyOCR first (often better for complex layouts)
        if self.easyocr_reader:
            try:
                results = self.easyocr_reader.readtext(image_path)
                text = " ".join([r[1] for r in results])
                confidence = sum(r[2] for r in results) / len(results) if results else 0
                if text.strip():
                    return text, confidence
            except Exception as e:
                logger.debug(f"[VISION] EasyOCR failed: {e}")

        # Fallback to Tesseract
        if self.tesseract:
            try:
                from PIL import Image
                img = Image.open(image_path)
                text = self.tesseract.image_to_string(img)
                # Tesseract doesn't provide confidence easily
                confidence = 0.7 if text.strip() else 0.3
            except Exception as e:
                logger.debug(f"[VISION] Tesseract failed: {e}")

        return text, confidence

    def extract_chart_data(self, image_path: str) -> Dict[str, Any]:
        """Extract data from chart images."""
        result = {
            "chart_type": "unknown",
            "title": "",
            "x_label": "",
            "y_label": "",
            "data_series": [],
            "legend": [],
        }

        # Use OCR to extract labels
        text, _ = self.extract_text_ocr(image_path)

        # Basic parsing of extracted text
        lines = text.split('\n')
        for line in lines:
            if any(kw in line.lower() for kw in ['title', 'figure']):
                result["title"] = line

        # For advanced chart extraction, use Gemini Vision
        if self.use_gemini_fallback:
            gemini_result = self._gemini_chart_analysis(image_path)
            if gemini_result:
                result.update(gemini_result)

        return result

    def _gemini_chart_analysis(self, image_path: str) -> Optional[Dict]:
        """Use Gemini Vision for chart analysis."""
        import os

        if not os.getenv("GOOGLE_API_KEY"):
            return None

        try:
            import google.generativeai as genai
            from PIL import Image

            genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
            model = genai.GenerativeModel("gemini-2.0-flash")

            img = Image.open(image_path)

            response = model.generate_content([
                """Analyze this chart/graph image and extract:
                1. Chart type (bar, line, pie, scatter, etc.)
                2. Title
                3. X-axis label and values
                4. Y-axis label and values
                5. Data series with values
                6. Legend entries

                Respond in JSON format.""",
                img,
            ])

            import json
            # Parse JSON from response
            text = response.text
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]

            return json.loads(text)

        except Exception as e:
            logger.warning(f"[VISION] Gemini chart analysis failed: {e}")
            return None

    def process_image(
        self,
        image_path: str,
        context: str = "",
    ) -> VisionResult:
        """
        Full image processing pipeline.

        Args:
            image_path: Path to image file
            context: Surrounding text context for better understanding
        """
        # Classify image type
        image_type = self.classify_image_type(image_path)

        # Extract text
        extracted_text, ocr_confidence = self.extract_text_ocr(image_path)

        # Get description and data based on type
        description = ""
        data_points = []

        if image_type == ImageType.CHART:
            chart_data = self.extract_chart_data(image_path)
            description = f"Chart: {chart_data.get('title', 'Untitled')}"
            data_points = chart_data.get('data_series', [])

        elif image_type == ImageType.TABLE:
            # Table extraction
            table_data = self._extract_table(image_path)
            description = "Data table"
            data_points = table_data

        else:
            # General image description via Gemini
            description = self._get_image_description(image_path, context)

        return VisionResult(
            image_type=image_type,
            extracted_text=extracted_text,
            description=description,
            data_points=data_points,
            confidence=ocr_confidence,
            metadata={
                "source_path": image_path,
                "context": context,
            }
        )

    def _extract_table(self, image_path: str) -> List[List[str]]:
        """Extract table data from image."""
        # Use OCR with table structure analysis
        try:
            # This is a simplified version
            # Production would use more sophisticated table detection
            text, _ = self.extract_text_ocr(image_path)

            # Parse as rows/columns
            rows = text.strip().split('\n')
            table = [row.split() for row in rows if row.strip()]

            return table

        except Exception as e:
            logger.warning(f"[VISION] Table extraction failed: {e}")
            return []

    def _get_image_description(self, image_path: str, context: str) -> str:
        """Get general image description."""
        if self.use_gemini_fallback:
            import os
            if os.getenv("GOOGLE_API_KEY"):
                try:
                    import google.generativeai as genai
                    from PIL import Image

                    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
                    model = genai.GenerativeModel("gemini-2.0-flash")

                    img = Image.open(image_path)

                    prompt = "Describe this image in detail for research purposes."
                    if context:
                        prompt += f" Context: {context}"

                    response = model.generate_content([prompt, img])
                    return response.text

                except Exception as e:
                    logger.warning(f"[VISION] Description failed: {e}")

        return "Image description not available"
