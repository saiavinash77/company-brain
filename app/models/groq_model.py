from agno.models.openai import OpenAIChat

from app.config import GROQ_API_KEY


def get_groq_llama(model_id: str = "llama-3.3-70b-versatile") -> OpenAIChat:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set. Add it to your .env file.")

    return OpenAIChat(
        id=model_id,
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )
