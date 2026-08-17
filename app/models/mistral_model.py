from agno.models.mistral import MistralChat

from app.config import MISTRAL_API_KEY


def get_mistral_large(model_id: str = "mistral-large-latest") -> MistralChat:
    if not MISTRAL_API_KEY:
        raise ValueError("MISTRAL_API_KEY is not set. Add it to your .env file.")

    return MistralChat(id=model_id, api_key=MISTRAL_API_KEY)
