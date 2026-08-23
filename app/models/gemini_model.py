from agno.models.google import Gemini

from app.config import GOOGLE_API_KEY


def get_gemini_flash(model_id: str = "gemini-3.6-flash") -> Gemini:
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY is not set. Add it to your .env file.")

    return Gemini(id=model_id, api_key=GOOGLE_API_KEY)


def get_gemini_pro(model_id: str = "gemini-3.6-flash") -> Gemini:
    if not GOOGLE_API_KEY:
        raise ValueError("GOOGLE_API_KEY is not set. Add it to your .env file.")

    return Gemini(id=model_id, api_key=GOOGLE_API_KEY)
