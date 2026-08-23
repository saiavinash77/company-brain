from agno.models.google import Gemini
from agno.models.openai import OpenAIChat

from app.config import GOOGLE_API_KEY, GROQ_API_KEY


def get_groq_llama(model_id: str = "llama-3.3-70b-versatile"):
    """Groq Llama 3.3 70B. Falls back to Gemini when GROQ_API_KEY is absent,
    so the team runs on a single key during development."""
    if GROQ_API_KEY:
        return OpenAIChat(
            id=model_id,
            api_key=GROQ_API_KEY,
            base_url="https://api.groq.com/openai/v1",
        )
    if not GOOGLE_API_KEY:
        raise ValueError(
            "Neither GROQ_API_KEY nor GOOGLE_API_KEY is set. Add one to your .env file."
        )
    return Gemini(id="gemini-3.6-flash", api_key=GOOGLE_API_KEY)
