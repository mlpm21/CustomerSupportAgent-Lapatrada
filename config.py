"""Application configuration.

Purpose:
    Load environment variables and define agent execution limits.

Used with:
    Used by agent.py to configure live OpenAI calls.

Notes:
    Importing loads the project .env if present. The key is required only when require_api_key() is called.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent / ".env")

OPENAI_API_KEY: str = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL: str = os.getenv("OPENAI_MODEL", "").strip()

MAX_TOOL_ROUNDS: int = 5
API_TIMEOUT_SECONDS: float = 30.0
MAX_STRUCTURED_OUTPUT_REPAIR_ATTEMPTS: int = 1


def require_api_key() -> str:
    """Return the configured key or explain how to enable live calls."""
    if not OPENAI_API_KEY:
        raise ValueError(
            "OPENAI_API_KEY is required for live model calls. "
            "Set it in the environment or in the project .env file."
        )
    return OPENAI_API_KEY
