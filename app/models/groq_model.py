"""LLM workhorse helpers — Groq powers every agent (free-tier Gemini was
taking 20-50s per call; Groq answers in ~1s), with OpenRouter as a
quota-free safety net.

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


def get_groq_llama(model_id: str = "openai/gpt-oss-120b", max_retries: int = 10):
    """Groq workhorse (llama-3.3-70b-versatile was retired) with fallback
    chain: Groq → Gemini → OpenRouter free.

    max_retries is the OpenAI SDK's automatic-retry count for 429s — Groq's
    free tier caps every model at ~8000 tokens/minute, and a 10-agent team
    run easily needs 3+ minutes of calls. The SDK backs off exponentially
    (seconds → minutes), so raising retries keeps a team run alive past the
    rate-limit window instead of dying mid-handoff with a RunError."""
    if GROQ_API_KEY:
        return OpenAIChat(
            id=model_id,
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
            max_retries=max_retries,
        )
    if GOOGLE_API_KEY:
        return Gemini(id="gemini-3.6-flash", api_key=GOOGLE_API_KEY)
    if OPENROUTER_API_KEY:
        return _openrouter()
    raise ValueError(
        "No LLM key set (GROQ_API_KEY / GOOGLE_API_KEY / OPENROUTER_API_KEY)."
    )


# Model split for rate-limit headroom: the team coordinator and the member
# agents ride DIFFERENT Groq models, so their token budgets don't collide
# (each model id gets its own 8000/min allowance on the free tier).
# gpt-oss-120b stays the team brain (best quality); qwen3.8-27b is a solid
# tool-using worker at a fraction of the token cost.
TEAM_MODEL_ID = "openai/gpt-oss-120b"
MEMBER_MODEL_ID = "qwen/qwen3.8-27b"


def get_team_model() -> OpenAIChat:
    """Model for the Team itself (the coordinator / Chief of Staff brain)."""
    return get_groq_llama(TEAM_MODEL_ID)


def get_member_model() -> OpenAIChat:
    """Model for member agents (sales, finance, legal, …) — a separate model
    id so a busy team run gets 2× the aggregate tokens-per-minute budget."""
    return get_groq_llama(MEMBER_MODEL_ID)


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
