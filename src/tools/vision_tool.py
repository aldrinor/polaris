"""
POLARIS v3 Vision Tool

Multimodal analysis using Google Gemini for:
- Image analysis (charts, tables, diagrams)
- Data extraction from visual content
- Image captioning and description
- OCR and text extraction

Uses Gemini 3 Flash (multimodal) for vision tasks.
Gemini 2.0 Flash deprecated March 2026 - use gemini-3-flash or gemini-2.5-flash.
"""

import logging
import base64
import io
import os
from typing import List, Dict, Any, Optional, Literal
from pathlib import Path

from pydantic import BaseModel, Field
from langchain_core.tools import tool

import google.generativeai as genai


logger = logging.getLogger(__name__)


# =============================================================================
# Configuration
# =============================================================================

# Gemini model for vision tasks
# Options: gemini-3-flash (latest), gemini-3-pro, gemini-2.5-flash
# Note: gemini-2.0-flash deprecated March 3, 2026
VISION_MODEL = os.getenv("GEMINI_VISION_MODEL", "gemini-3-flash")

# Supported image formats
SUPPORTED_FORMATS = {"png", "jpg", "jpeg", "gif", "webp", "bmp"}


# =============================================================================
# Output Schemas
# =============================================================================

class ImageAnalysis(BaseModel):
    """Result of image analysis."""
    description: str = Field(description="General description of the image")
    image_type: Literal[
        "chart", "table", "diagram", "photo", "screenshot",
        "infographic", "map", "document", "other"
    ] = Field(description="Type of image")
    text_content: List[str] = Field(default_factory=list, description="Text extracted from image")
    data_points: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted data points")
    key_findings: List[str] = Field(default_factory=list, description="Key findings from the image")
    confidence: float = Field(ge=0.0, le=1.0, description="Analysis confidence")


class ChartData(BaseModel):
    """Extracted data from a chart."""
    chart_type: Literal["bar", "line", "pie", "scatter", "area", "histogram", "other"] = Field(
        description="Type of chart"
    )
    title: Optional[str] = Field(default=None, description="Chart title")
    x_axis_label: Optional[str] = Field(default=None, description="X-axis label")
    y_axis_label: Optional[str] = Field(default=None, description="Y-axis label")
    data_series: List[Dict[str, Any]] = Field(default_factory=list, description="Extracted data series")
    legend_items: List[str] = Field(default_factory=list, description="Legend items")
    source: Optional[str] = Field(default=None, description="Data source if mentioned")


class TableData(BaseModel):
    """Extracted data from a table."""
    title: Optional[str] = Field(default=None, description="Table title")
    headers: List[str] = Field(default_factory=list, description="Column headers")
    rows: List[List[str]] = Field(default_factory=list, description="Table rows")
    footnotes: List[str] = Field(default_factory=list, description="Footnotes")
    source: Optional[str] = Field(default=None, description="Data source")


# =============================================================================
# Vision Client
# =============================================================================

class GeminiVisionClient:
    """
    Gemini-based vision client for multimodal analysis.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = VISION_MODEL
    ):
        """
        Initialize the vision client.

        Args:
            api_key: Gemini API key (or from env)
            model: Model name for vision tasks
        """
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = model

        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not configured")

        # Configure API
        genai.configure(api_key=self.api_key)

        # Initialize model
        self.model = genai.GenerativeModel(self.model_name)

        logger.info(f"Gemini Vision client initialized: {self.model_name}")

    def _load_image(self, image_source: str) -> Dict[str, Any]:
        """
        Load image from file path, URL, or base64.

        Args:
            image_source: File path, URL, or base64 string

        Returns:
            Image dict for Gemini API
        """
        # Check if base64
        if image_source.startswith("data:image"):
            # Extract base64 data
            _, data = image_source.split(",", 1)
            return {
                "mime_type": "image/png",
                "data": data
            }

        # Check if file path
        path = Path(image_source)
        if path.exists() and path.is_file():
            suffix = path.suffix.lower().lstrip(".")
            if suffix not in SUPPORTED_FORMATS:
                raise ValueError(f"Unsupported image format: {suffix}")

            mime_type = f"image/{suffix}"
            if suffix == "jpg":
                mime_type = "image/jpeg"

            with open(path, "rb") as f:
                data = base64.standard_b64encode(f.read()).decode("utf-8")

            return {
                "mime_type": mime_type,
                "data": data
            }

        # Assume URL - let Gemini handle it
        return {"url": image_source}

    def analyze_image(
        self,
        image_source: str,
        prompt: Optional[str] = None
    ) -> ImageAnalysis:
        """
        Analyze an image and extract information.

        Args:
            image_source: File path, URL, or base64 image
            prompt: Optional custom prompt

        Returns:
            ImageAnalysis with extracted information
        """
        image = self._load_image(image_source)

        system_prompt = """You are an expert image analyst. Analyze this image and extract:
1. A clear description of what the image shows
2. The type of image (chart, table, diagram, photo, etc.)
3. Any text visible in the image
4. Key data points or findings
5. Your confidence in the analysis

Be precise and factual. Only describe what you can clearly see."""

        user_prompt = prompt or "Analyze this image in detail."

        try:
            # Create content with image
            if "data" in image:
                image_part = {
                    "inline_data": {
                        "mime_type": image["mime_type"],
                        "data": image["data"]
                    }
                }
            else:
                image_part = {"file_uri": image["url"]}

            response = self.model.generate_content([
                system_prompt,
                image_part,
                user_prompt
            ])

            # Parse response into structured format
            text = response.text

            # Extract components (simplified parsing)
            analysis = ImageAnalysis(
                description=text[:500] if text else "Unable to analyze image",
                image_type=self._detect_image_type(text),
                text_content=self._extract_text_mentions(text),
                data_points=[],
                key_findings=self._extract_key_findings(text),
                confidence=0.8 if text else 0.0
            )

            return analysis

        except Exception as e:
            logger.error(f"Image analysis failed: {e}")
            return ImageAnalysis(
                description=f"Analysis failed: {str(e)}",
                image_type="other",
                confidence=0.0
            )

    def extract_chart_data(self, image_source: str) -> ChartData:
        """
        Extract data from a chart image.

        Args:
            image_source: File path, URL, or base64 image

        Returns:
            ChartData with extracted values
        """
        image = self._load_image(image_source)

        prompt = """Analyze this chart and extract ALL data:

1. Chart type (bar, line, pie, scatter, area, histogram, other)
2. Title (if visible)
3. X-axis label and values
4. Y-axis label and values
5. All data series with their labels and values
6. Legend items
7. Data source (if mentioned)

Be precise with numbers. If a value is approximate, indicate that.
Return the data in a structured format."""

        try:
            if "data" in image:
                image_part = {
                    "inline_data": {
                        "mime_type": image["mime_type"],
                        "data": image["data"]
                    }
                }
            else:
                image_part = {"file_uri": image["url"]}

            response = self.model.generate_content([
                prompt,
                image_part
            ])

            text = response.text

            # Parse response
            chart_data = ChartData(
                chart_type=self._detect_chart_type(text),
                title=self._extract_title(text),
                x_axis_label=self._extract_axis_label(text, "x"),
                y_axis_label=self._extract_axis_label(text, "y"),
                data_series=self._extract_data_series(text),
                legend_items=self._extract_legend(text),
                source=self._extract_source(text)
            )

            return chart_data

        except Exception as e:
            logger.error(f"Chart extraction failed: {e}")
            return ChartData(chart_type="other")

    def extract_table_data(self, image_source: str) -> TableData:
        """
        Extract data from a table image.

        Args:
            image_source: File path, URL, or base64 image

        Returns:
            TableData with extracted rows and columns
        """
        image = self._load_image(image_source)

        prompt = """Extract ALL data from this table:

1. Table title (if visible)
2. Column headers
3. All rows of data (preserve exact values)
4. Any footnotes or notes
5. Data source (if mentioned)

Format the data as:
HEADERS: [header1, header2, ...]
ROWS:
- [value1, value2, ...]
- [value1, value2, ...]

Be precise with all values. Include units where visible."""

        try:
            if "data" in image:
                image_part = {
                    "inline_data": {
                        "mime_type": image["mime_type"],
                        "data": image["data"]
                    }
                }
            else:
                image_part = {"file_uri": image["url"]}

            response = self.model.generate_content([
                prompt,
                image_part
            ])

            text = response.text

            # Parse response
            table_data = TableData(
                title=self._extract_title(text),
                headers=self._extract_headers(text),
                rows=self._extract_rows(text),
                footnotes=self._extract_footnotes(text),
                source=self._extract_source(text)
            )

            return table_data

        except Exception as e:
            logger.error(f"Table extraction failed: {e}")
            return TableData()

    def extract_text(self, image_source: str) -> str:
        """
        Extract all text from an image (OCR).

        Args:
            image_source: File path, URL, or base64 image

        Returns:
            Extracted text
        """
        image = self._load_image(image_source)

        prompt = """Extract ALL text visible in this image.
Preserve the layout as much as possible.
Include all text, labels, titles, captions, and annotations.
If text is unclear, indicate with [unclear]."""

        try:
            if "data" in image:
                image_part = {
                    "inline_data": {
                        "mime_type": image["mime_type"],
                        "data": image["data"]
                    }
                }
            else:
                image_part = {"file_uri": image["url"]}

            response = self.model.generate_content([
                prompt,
                image_part
            ])

            return response.text

        except Exception as e:
            logger.error(f"Text extraction failed: {e}")
            return ""

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _detect_image_type(self, text: str) -> str:
        """Detect image type from analysis text."""
        text_lower = text.lower()
        if "chart" in text_lower or "graph" in text_lower:
            return "chart"
        elif "table" in text_lower:
            return "table"
        elif "diagram" in text_lower:
            return "diagram"
        elif "map" in text_lower:
            return "map"
        elif "screenshot" in text_lower:
            return "screenshot"
        elif "infographic" in text_lower:
            return "infographic"
        elif "document" in text_lower:
            return "document"
        elif "photo" in text_lower:
            return "photo"
        return "other"

    def _detect_chart_type(self, text: str) -> str:
        """Detect chart type from text."""
        text_lower = text.lower()
        if "bar" in text_lower:
            return "bar"
        elif "line" in text_lower:
            return "line"
        elif "pie" in text_lower:
            return "pie"
        elif "scatter" in text_lower:
            return "scatter"
        elif "area" in text_lower:
            return "area"
        elif "histogram" in text_lower:
            return "histogram"
        return "other"

    def _extract_text_mentions(self, text: str) -> List[str]:
        """Extract text mentions from analysis."""
        # Simple extraction - look for quoted text
        import re
        mentions = re.findall(r'"([^"]+)"', text)
        return mentions[:10]  # Limit to 10

    def _extract_key_findings(self, text: str) -> List[str]:
        """Extract key findings from analysis."""
        # Look for bullet points or numbered items
        import re
        findings = []

        # Match bullet points
        bullets = re.findall(r'[•\-\*]\s*(.+?)(?=\n|$)', text)
        findings.extend(bullets[:5])

        # Match numbered items
        numbered = re.findall(r'\d+\.\s*(.+?)(?=\n|$)', text)
        findings.extend(numbered[:5])

        return findings[:5]

    def _extract_title(self, text: str) -> Optional[str]:
        """Extract title from text."""
        import re
        match = re.search(r'[Tt]itle[:\s]+([^\n]+)', text)
        return match.group(1).strip() if match else None

    def _extract_axis_label(self, text: str, axis: str) -> Optional[str]:
        """Extract axis label."""
        import re
        pattern = rf'{axis}[- ]?axis[:\s]+([^\n]+)'
        match = re.search(pattern, text, re.IGNORECASE)
        return match.group(1).strip() if match else None

    def _extract_data_series(self, text: str) -> List[Dict[str, Any]]:
        """Extract data series from text."""
        # Simplified - would need more sophisticated parsing
        return []

    def _extract_legend(self, text: str) -> List[str]:
        """Extract legend items."""
        import re
        match = re.search(r'[Ll]egend[:\s]+(.+?)(?=\n\n|$)', text, re.DOTALL)
        if match:
            items = re.findall(r'[•\-\*]\s*(.+?)(?=\n|$)', match.group(1))
            return items
        return []

    def _extract_headers(self, text: str) -> List[str]:
        """Extract table headers."""
        import re
        match = re.search(r'[Hh]eaders?[:\s]+\[?([^\]\n]+)', text)
        if match:
            headers = [h.strip().strip("'\"") for h in match.group(1).split(",")]
            return headers
        return []

    def _extract_rows(self, text: str) -> List[List[str]]:
        """Extract table rows."""
        import re
        rows = []
        matches = re.findall(r'-\s*\[([^\]]+)\]', text)
        for match in matches[:50]:  # Limit rows
            values = [v.strip().strip("'\"") for v in match.split(",")]
            rows.append(values)
        return rows

    def _extract_footnotes(self, text: str) -> List[str]:
        """Extract footnotes."""
        import re
        footnotes = re.findall(r'\*+\s*(.+?)(?=\n|$)', text)
        return footnotes[:5]

    def _extract_source(self, text: str) -> Optional[str]:
        """Extract data source."""
        import re
        match = re.search(r'[Ss]ource[:\s]+([^\n]+)', text)
        return match.group(1).strip() if match else None


# =============================================================================
# LangChain Tools
# =============================================================================

@tool
def analyze_image(
    image_path: str,
    analysis_type: str = "general"
) -> Dict[str, Any]:
    """
    Analyze an image and extract information using Gemini vision.

    Args:
        image_path: Path to image file or URL
        analysis_type: Type of analysis (general, chart, table, text)

    Returns:
        Analysis results with extracted data
    """
    try:
        client = GeminiVisionClient()

        if analysis_type == "chart":
            result = client.extract_chart_data(image_path)
            return result.model_dump()
        elif analysis_type == "table":
            result = client.extract_table_data(image_path)
            return result.model_dump()
        elif analysis_type == "text":
            text = client.extract_text(image_path)
            return {"extracted_text": text}
        else:
            result = client.analyze_image(image_path)
            return result.model_dump()

    except Exception as e:
        logger.error(f"Image analysis failed: {e}")
        return {"error": str(e)}


@tool
def extract_chart_data(image_path: str) -> Dict[str, Any]:
    """
    Extract data points from a chart image.

    Args:
        image_path: Path to chart image

    Returns:
        Extracted chart data including type, labels, and values
    """
    try:
        client = GeminiVisionClient()
        result = client.extract_chart_data(image_path)
        return result.model_dump()
    except Exception as e:
        logger.error(f"Chart extraction failed: {e}")
        return {"error": str(e)}


@tool
def extract_table_data(image_path: str) -> Dict[str, Any]:
    """
    Extract data from a table image.

    Args:
        image_path: Path to table image

    Returns:
        Extracted table data with headers and rows
    """
    try:
        client = GeminiVisionClient()
        result = client.extract_table_data(image_path)
        return result.model_dump()
    except Exception as e:
        logger.error(f"Table extraction failed: {e}")
        return {"error": str(e)}


@tool
def ocr_image(image_path: str) -> str:
    """
    Extract text from an image using OCR.

    Args:
        image_path: Path to image

    Returns:
        Extracted text
    """
    try:
        client = GeminiVisionClient()
        return client.extract_text(image_path)
    except Exception as e:
        logger.error(f"OCR failed: {e}")
        return f"OCR failed: {str(e)}"


# =============================================================================
# Convenience Functions
# =============================================================================

def get_vision_client(**kwargs) -> GeminiVisionClient:
    """Get a configured vision client."""
    return GeminiVisionClient(**kwargs)


def analyze_research_image(
    image_source: str,
    context: str = ""
) -> Dict[str, Any]:
    """
    Analyze an image in a research context.

    Args:
        image_source: Image path or URL
        context: Research context for better analysis

    Returns:
        Analysis with research-relevant findings
    """
    client = GeminiVisionClient()

    # First, determine image type
    general = client.analyze_image(image_source, f"Context: {context}" if context else None)

    result = {
        "general_analysis": general.model_dump(),
        "image_type": general.image_type,
    }

    # If chart, extract data
    if general.image_type == "chart":
        chart_data = client.extract_chart_data(image_source)
        result["chart_data"] = chart_data.model_dump()

    # If table, extract data
    elif general.image_type == "table":
        table_data = client.extract_table_data(image_source)
        result["table_data"] = table_data.model_dump()

    # Always extract text
    result["extracted_text"] = client.extract_text(image_source)

    return result
