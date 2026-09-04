"""LLM workhorse helpers — Gemini on Vertex AI powers every agent.

Why Gemini on Vertex (2026-09-04): Groq's free tier caps EVERY request at
8000 tokens/minute per model, and the team's accumulated context (system
prompts + team history + tool results) grows past that within a few turns —
Groq then rejects the whole request ("Request too large … Requested 9322"),
which no amount of retrying can fix. Gemini on Vertex authenticates via the
Cloud Run service account (no API key), has no such per-request ceiling, and
gemini-2.5-pro is a quality upgrade for the coordinator.

Model map:
- Team coordinator: gemini-2.5-pro  (best quality)
- Member agents:    gemini-2.5-flash (fast, cheap, tool-capable)
- OCR/vision:        gemini-3.6-flash via Vertex (app/main.py)
- Fallbacks:         Groq (fast, if GROQ_API_KEY set) → OpenRouter free

GROQ ROLE MAP (kept for the Groq fallback): Agno's OpenAIChat maps system
messages to the "developer" role by default (an OpenAI convention). Groq's
server-side minijinja template only accepts "system" on many models —
sending "developer" returns HTTP 400 "Unexpected message role". The explicit
role_map below keeps "system" as "system".
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
# LOCATION NOTE: "global" (not asia-south1) — the regional asia-south1
# endpoint only serves a subset of Gemini models; the global endpoint serves
# all of them, including gemini-2.5-pro (verified live with the Cloud Run
# service account token).
GCP_PROJECT = os.environ.get("GOOGLE_CLOUD_PROJECT", "company-brain-live")
GCP_LOCATION = os.environ.get("GOOGLE_CLOUD_LOCATION", "global")

# Coordinator (team brain) gets the pro model for quality; member agents get
# flash for speed and cost. Both verified live on Vertex asia-south1.
VERTEX_TEAM_MODEL = os.environ.get("VERTEX_TEAM_MODEL", "gemini-2.5-pro")
VERTEX_MEMBER_MODEL = os.environ.get("VERTEX_MEMBER_MODEL", "gemini-2.5-flash")
VERTEX_OCR_MODEL = os.environ.get("VERTEX_GEMINI_MODEL", "gemini-3.6-flash")


def _vertex_gemini(model_id: str) -> Gemini:
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
    adc = os.path.join(
        os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
    )
    win_adc = os.path.expandvars(r"%APPDATA%\gcloud\application_default_credentials.json")
    return os.path.exists(adc) or os.path.exists(win_adc)


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
    """Backwards-compatible alias: the team used to ask for "the Groq model"
    by name. Gemini on Vertex is now the primary; Groq the fast fallback,
    with the critical role_map fix (see module docstring)."""
    return get_team_model()


# Model split for per-model quota headroom + cost control: the team
# coordinator rides the pro model, member agents the flash model. Separate
# model ids also keep their token budgets independent.
def get_team_model():
    """Model for the Team itself (the coordinator / Chief of Staff brain)."""
    if _vertex_available():
        return _vertex_gemini(VERTEX_TEAM_MODEL)
    if GROQ_API_KEY:
        return OpenAIChat(
            id="openai/gpt-oss-120b",
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
            max_retries=10,
            role_map=GROQ_ROLE_MAP,
        )
    if OPENROUTER_API_KEY:
        return _openrouter()
    raise ValueError("No LLM available (Vertex AI / GROQ_API_KEY / OPENROUTER_API_KEY).")


def get_member_model():
    """Model for member agents (sales, finance, legal, …) — fast flash tier
    so a 10-agent team run stays quick and cheap."""
    if _vertex_available():
        return _vertex_gemini(VERTEX_MEMBER_MODEL)
    if GROQ_API_KEY:
        return OpenAIChat(
            id="qwen/qwen3.8-27b",
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
            max_retries=10,
            role_map=GROQ_ROLE_MAP,
        )
    if OPENROUTER_API_KEY:
        return _openrouter()
    raise ValueError("No LLM available (Vertex AI / GROQ_API_KEY / OPENROUTER_API_KEY).")


def get_gemini_vertex() -> Gemini:
    """Google's Gemini via Vertex AI — used for OCR/vision and as a
    high-quality fallback. Authenticates via GCP credentials, no API key."""
    return _vertex_gemini(VERTEX_OCR_MODEL)


def get_mistral_large(model_id: str = "mistral-large-latest"):
    """Mistral Large with fallback chain:
    Mistral → OpenRouter free → Gemini (Vertex)."""
    if MISTRAL_API_KEY:
        from agno.models.mistral import MistralChat

        return MistralChat(id=model_id, api_key=MISTRAL_API_KEY)
    if OPENROUTER_API_KEY:
        return _openrouter()
    if _vertex_available():
        return _vertex_gemini(VERTEX_MEMBER_MODEL)
    raise ValueError(
        "No LLM key set (MISTRAL_API_KEY / OPENROUTER_API_KEY / Vertex AI)."
    )
