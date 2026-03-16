"""
POLARIS - Production-Grade Research Pipeline

FIX 120: Load environment variables at package initialization.
This ensures API keys are available before any module imports them.
"""
import os
from pathlib import Path

# Load .env file at package import time
from dotenv import load_dotenv

# Find the project root (parent of src/)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_ENV_FILE = _PROJECT_ROOT / ".env"

if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=True)
