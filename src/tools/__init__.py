"""
POLARIS v3 Tools Module

Specialized tools for agent use:
- Vision tool: Gemini-based image analysis
- PDF parser: Document extraction and analysis
- Agent Swarm: Full-scale 1500-step orchestration (KIMI parity)
- Vision Processor: MoonViT-style image understanding
- Long-Form Generator: 100K+ token document generation
- Streaming Reasoner: Real-time reasoning token visibility
- User Feedback: Mid-research intervention support
- File Analyzer: Excel, CSV, PDF analysis
- Browser Automation: JavaScript rendering with Playwright
- Access Bypass: Research access (Unpaywall, Archive.org, Sci-Hub)

All tools are LangChain-compatible for easy agent integration.
"""

from .vision_tool import (
    # Client
    GeminiVisionClient,
    get_vision_client,
    # Schemas
    ImageAnalysis,
    ChartData,
    TableData,
    # Tools
    analyze_image,
    extract_chart_data,
    extract_table_data,
    ocr_image,
    # Helpers
    analyze_research_image,
)

from .pdf_parser import (
    # Parser
    PDFParser,
    get_pdf_parser,
    # Schemas
    PDFDocument,
    PDFPage,
    PDFTable,
    PDFImage,
    PDFMetadata,
    # Tools
    parse_pdf,
    extract_pdf_text,
    extract_pdf_tables,
    analyze_pdf_with_vision,
    # Helpers
    quick_pdf_extract,
)

# KIMI K2.5 Parity Tools (Parts 20-27)
from .agent_swarm_full import (
    FullScaleSwarmOrchestrator,
    SwarmConfig,
    SubAgent,
    AgentState,
)

from .vision_processor import (
    VisionProcessor,
    VisionResult,
    ImageType,
)

from .long_form_generator import (
    LongFormGenerator,
    Section,
    CoherenceValidator,
    CoherenceResult,
)

from .streaming_reasoner import (
    StreamingReasoner,
    WebSocketReasoningStream,
    ReasoningToken,
)

from .user_feedback import (
    UserFeedbackManager,
    UserFeedback,
    FeedbackCheckpoint,
    FeedbackType,
)

from .file_analyzer import (
    FileAnalyzer,
    FileAnalysisResult,
    ChartGenerator,
)

from .browser_automation import (
    BrowserAutomation,
    BrowserResult,
)

from .access_bypass import (
    AccessBypass,
    AccessResult,
)

__all__ = [
    # Vision Tool
    "GeminiVisionClient",
    "get_vision_client",
    "ImageAnalysis",
    "ChartData",
    "TableData",
    "analyze_image",
    "extract_chart_data",
    "extract_table_data",
    "ocr_image",
    "analyze_research_image",
    # PDF Parser
    "PDFParser",
    "get_pdf_parser",
    "PDFDocument",
    "PDFPage",
    "PDFTable",
    "PDFImage",
    "PDFMetadata",
    "parse_pdf",
    "extract_pdf_text",
    "extract_pdf_tables",
    "analyze_pdf_with_vision",
    "quick_pdf_extract",
    # KIMI K2.5 Parity Tools (Parts 20-27)
    # Agent Swarm Full Scale
    "FullScaleSwarmOrchestrator",
    "SwarmConfig",
    "SubAgent",
    "AgentState",
    # Vision Processor (MoonViT-style)
    "VisionProcessor",
    "VisionResult",
    "ImageType",
    # Long-Form Generator
    "LongFormGenerator",
    "Section",
    "CoherenceValidator",
    "CoherenceResult",
    # Streaming Reasoner
    "StreamingReasoner",
    "WebSocketReasoningStream",
    "ReasoningToken",
    # User Feedback
    "UserFeedbackManager",
    "UserFeedback",
    "FeedbackCheckpoint",
    "FeedbackType",
    # File Analyzer
    "FileAnalyzer",
    "FileAnalysisResult",
    "ChartGenerator",
    # Browser Automation
    "BrowserAutomation",
    "BrowserResult",
    # Access Bypass
    "AccessBypass",
    "AccessResult",
]
