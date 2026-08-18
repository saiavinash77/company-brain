from agno.models.openai import OpenAIChat

from app.config import GROQ_API_KEY, GROQ_MODEL


def get_groq_llama(model_id: str | None = None) -> OpenAIChat:
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY is not set. Add it to your .env file.")

    return OpenAIChat(
        id=model_id or GROQ_MODEL,
        api_key=GROQ_API_KEY,
        base_url="https://api.groq.com/openai/v1",
    )
