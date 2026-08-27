from agno.models.google import Gemini
from agno.models.mistral import MistralChat

from app.config import GOOGLE_API_KEY, MISTRAL_API_KEY, OPENROUTER_API_KEY


def get_mistral_large(model_id: str = "mistral-large-latest"):
    """Mistral Large. Fallback chain when MISTRAL_API_KEY is absent:
    Gemini → OpenRouter free model."""
    if MISTRAL_API_KEY:
        return MistralChat(id=model_id, api_key=MISTRAL_API_KEY)
    if GOOGLE_API_KEY:
        return Gemini(id="gemini-2.5-flash", api_key=GOOGLE_API_KEY)
    if OPENROUTER_API_KEY:
        from app.models.openrouter_model import get_openrouter_model

        return get_openrouter_model()
    raise ValueError(
        "No LLM key set (MISTRAL_API_KEY / GOOGLE_API_KEY / OPENROUTER_API_KEY)."
    )
