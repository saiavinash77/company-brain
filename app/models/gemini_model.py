"""Gemini model helpers with OpenRouter 429-fallback.

Gemini's free tier returns HTTP 429 (RESOURCE_EXHAUSTED) once the daily quota
is spent, and Agno's Gemini client does NOT auto-fallback — a quota hit kills
the whole run and the office floor never animates. We subclass Agno's Gemini
and override ``aresponse`` so that a 429 transparently re-routes the SAME call
through OpenRouter (free tier). Agno still receives a real ``Gemini`` instance,
so its internal checks pass.
"""
from agno.models.google import Gemini
from agno.models.openai import OpenAIChat

from app.config import GOOGLE_API_KEY, OPENROUTER_API_KEY
from app.models.groq_model import _openrouter

_GEMINI_DEFAULT = "gemini-3.6-flash"


def _is_quota_error(exc) -> bool:
    msg = str(exc).lower()
    return "429" in msg or "resource_exhausted" in msg or "too many requests" in msg


class GeminiWithFallback(Gemini):
    """A Gemini model that retries on quota errors via OpenRouter."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._fb = _openrouter() if OPENROUTER_API_KEY else None

    async def aresponse(self, *args, **kwargs):
        try:
            return await super().aresponse(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            if self._fb is not None and _is_quota_error(e):
                return await self._fb.aresponse(*args, **kwargs)
            raise

    def response(self, *args, **kwargs):
        try:
            return super().response(*args, **kwargs)
        except Exception as e:  # noqa: BLE001
            if self._fb is not None and _is_quota_error(e):
                return self._fb.response(*args, **kwargs)
            raise


def _gemini_or_fallback(model_id: str):
    if GOOGLE_API_KEY:
        return GeminiWithFallback(id=model_id, api_key=GOOGLE_API_KEY)
    if OPENROUTER_API_KEY:
        return _openrouter()
    raise ValueError("No LLM key set (GOOGLE_API_KEY / OPENROUTER_API_KEY).")


def get_gemini_flash(model_id: str = _GEMINI_DEFAULT):
    return _gemini_or_fallback(model_id)


def get_gemini_pro(model_id: str = _GEMINI_DEFAULT):
    return _gemini_or_fallback(model_id)
