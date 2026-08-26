"""OpenRouter models — free-tier LLMs with Gemini-class capability.

OpenRouter exposes an OpenAI-compatible API, so Agno's OpenAIChat client
works with base_url=https://openrouter.ai/api/v1.

Model choice (verified live 2026-08-26):
- minimax/minimax-m3:free  → primary free workhorse
- google/gemma-4-31b-it:free → alternate (sometimes rate-limited upstream)

FALLBACK ORDER per agent type:
1. Groq (if GROQ_API_KEY)          — fastest
2. Gemini direct (if GOOGLE_API_KEY) — best quality
3. OpenRouter free (if OPENROUTER_API_KEY) — quota-free safety net
"""
from agno.models.google import Gemini
from agno.models.openai import OpenAIChat

from app.config import GOOGLE_API_KEY, GROQ_API_KEY, MISTRAL_API_KEY, OPENROUTER_API_KEY

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_MODEL = "minimax/minimax-m3:free"


def _openrouter(model_id: str = OPENROUTER_DEFAULT_MODEL) -> OpenAIChat:
    return OpenAIChat(
        id=model_id,
        api_key=OPENROUTER_API_KEY,
        base_url=OPENROUTER_BASE_URL,
    )


def get_openrouter(model_id: str = OPENROUTER_DEFAULT_MODEL) -> OpenAIChat:
    """Direct OpenRouter access (raises if key missing)."""
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY is not set. Add it to your .env file.")
    return _openrouter(model_id)


def get_groq_llama(model_id: str = "llama-3.3-70b-versatile"):
    """Groq Llama 3.3 70B with fallback chain:
    Groq → Gemini → OpenRouter free."""
    if GROQ_API_KEY:
        return OpenAIChat(
            id=model_id,
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
    if GOOGLE_API_KEY:
        return Gemini(id="gemini-3.6-flash", api_key=GOOGLE_API_KEY)
    if OPENROUTER_API_KEY:
        return _openrouter()
    raise ValueError(
        "No LLM key set (GROQ_API_KEY / GOOGLE_API_KEY / OPENROUTER_API_KEY)."
    )


def get_mistral_large(model_id: str = "mistral-large-latest"):
    """Mistral Large with fallback chain:
    Mistral → OpenRouter free → Gemini."""
    if MISTRAL_API_KEY:
        from agno.models.mistral import MistralChat

        return MistralChat(id=model_id, api_key=MISTRAL_API_KEY)
    if OPENROUTER_API_KEY:
        return _openrouter()
    if GOOGLE_API_KEY:
        return Gemini(id="gemini-3.6-flash", api_key=GOOGLE_API_KEY)
    raise ValueError(
        "No LLM key set (MISTRAL_API_KEY / OPENROUTER_API_KEY / GOOGLE_API_KEY)."
    )
