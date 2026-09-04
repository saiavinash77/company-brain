"""LLM workhorse helpers — Groq powers every agent (~1s latency), with
Gemini on Vertex AI and OpenRouter as fallbacks.

GROQ ROLE MAP (critical): Agno's OpenAIChat maps system messages to the
"developer" role by default (a newer OpenAI convention). Groq's server-side
minijinja template only accepts "system" on many models — sending "developer"
returns HTTP 400 "Unexpected message role", which kills every delegated
member-agent run (the team model gpt-oss-120b tolerates it, members on qwen
do not). The explicit role_map below keeps "system" as "system" everywhere.

FALLBACK ORDER per agent type:
1. Groq (if GROQ_API_KEY)             — fastest
2. Gemini on Vertex AI (on GCP)       — Google models, no key needed
3. OpenRouter free (if OPENROUTER_API_KEY) — quota-free safety net
"""
import os

from agno.models.google import Gemini
from agno.models.openai import OpenAIChat

from app.config import GOOGLE_API_KEY, GROQ_API_KEY, MISTRAL_API_KEY, OPENROUTER_API_KEY

OPENROUTER_BASE_URL = "https://openrouter.ai/api/v1"
OPENROUTER_DEFAULT_MODEL = "minimax/minimax-m3:free"

# Groq (and most OpenAI-compatible providers) want "system", not the
# OpenAI-specific "developer" alias Agno sends by default.
GROQ_ROLE_MAP = {
    "system": "system",
    "user": "user",
    "assistant": "assistant",
    "tool": "tool",
    "model": "assistant",
}

# Vertex AI config — on Cloud Run the service account authenticates itself,
# no API key involved. Locally it needs GOOGLE_APPLICATION_CREDENTIALS or
# `gcloud auth application-default login`.
GCP_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "company-brain-live")
GCP_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "asia-south1")
VERTEX_GEMINI_MODEL = os.environ.get("VERTEX_GEMINI_MODEL", "gemini-3.6-flash")


def _vertex_gemini(model_id: str = VERTEX_GEMINI_MODEL) -> Gemini:
    return Gemini(
        id=model_id,
        vertexai=True,
        project_id=GCP_PROJECT,
        location=GCP_LOCATION,
    )


def _vertex_available() -> bool:
    """Vertex path is usable when we're on GCP (metadata/ADC credentials)
    or the user has a Vertex-capable environment configured."""
    if os.environ.get("K_SERVICE"):  # set inside Cloud Run
        return True
    return os.path.exists(
        os.path.join(
            os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
        )
    )


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
    """Groq workhorse with fallback chain: Groq → Gemini (Vertex) → OpenRouter.

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
            role_map=GROQ_ROLE_MAP,
        )
    if _vertex_available():
        return _vertex_gemini()
    if OPENROUTER_API_KEY:
        return _openrouter()
    raise ValueError(
        "No LLM key set (GROQ_API_KEY / Vertex AI / OPENROUTER_API_KEY)."
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


def get_gemini_vertex() -> Gemini:
    """Google's Gemini via Vertex AI — used for OCR/vision and as a
    high-quality fallback. Authenticates via GCP credentials, no API key."""
    return _vertex_gemini()


def get_mistral_large(model_id: str = "mistral-large-latest"):
    """Mistral Large with fallback chain:
    Mistral → OpenRouter free → Gemini (Vertex)."""
    if MISTRAL_API_KEY:
        from agno.models.mistral import MistralChat

        return MistralChat(id=model_id, api_key=MISTRAL_API_KEY)
    if OPENROUTER_API_KEY:
        return _openrouter()
    if _vertex_available():
        return _vertex_gemini()
    raise ValueError(
        "No LLM key set (MISTRAL_API_KEY / OPENROUTER_API_KEY / Vertex AI)."
    )
