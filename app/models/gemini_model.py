"""Gemini model helpers with OpenRouter fallback.

Fallback chain: Gemini direct → OpenRouter free (quota-free safety net).
"""
from agno.models.google import Gemini

from app.config import GOOGLE_API_KEY, OPENROUTER_API_KEY
from app.models.groq_model import _openrouter


def _fallback():
    if OPENROUTER_API_KEY:
        return _openrouter()
    raise ValueError(
        "Neither GOOGLE_API_KEY nor OPENROUTER_API_KEY is set. Add one to your .env file."
    )


def get_gemini_flash(model_id: str = "gemini-2.5-flash"):
    if not GOOGLE_API_KEY:
        return _fallback()
    return Gemini(id=model_id, api_key=GOOGLE_API_KEY)


def get_gemini_pro(model_id: str = "gemini-2.5-pro"):
    if not GOOGLE_API_KEY:
        return _fallback()
    return Gemini(id=model_id, api_key=GOOGLE_API_KEY)
