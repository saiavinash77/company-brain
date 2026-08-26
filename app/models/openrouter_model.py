"""OpenRouter models — free-tier LLMs with Gemini-class capability.

OpenRouter is OpenAI-API-compatible, so Agno's OpenAIChat works with
base_url=https://openrouter.ai/api/v1. Primary free model:
nvidia/nemotron-3-super-120b-a12b:free (verified working Aug 2026).
"""
from agno.models.openai import OpenAIChat

from app.config import OPENROUTER_API_KEY

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_MODEL = "nvidia/nemotron-3-super-120b-a12b:free"


def get_openrouter_model(model_id: str | None = None):
    """OpenRouter chat model. Raises only if no key configured."""
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set. Add it to your .env file.")
    return OpenAIChat(
        id=model_id or OPENROUTER_DEFAULT_MODEL,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
        default_headers={"HTTP-Referer": "https://github.com/saiavinash77/company-brain",
                          "X-Title": "Company Brain"},
    )
