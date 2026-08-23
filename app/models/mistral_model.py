from agno.models.google import Gemini
from agno.models.mistral import MistralChat

from app.config import GOOGLE_API_KEY, MISTRAL_API_KEY


def get_mistral_large(model_id: str = "mistral-large-latest"):
    """Mistral Large. Falls back to Gemini when MISTRAL_API_KEY is absent,
    so the team runs on a single key during development."""
    if MISTRAL_API_KEY:
        return MistralChat(id=model_id, api_key=MISTRAL_API_KEY)
    if not GOOGLE_API_KEY:
        raise ValueError(
            "Neither MISTRAL_API_KEY nor GOOGLE_API_KEY is set. Add one to your .env file."
        )
    return Gemini(id="gemini-3.6-flash", api_key=GOOGLE_API_KEY)
