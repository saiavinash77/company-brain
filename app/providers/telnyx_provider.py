import httpx

from app.config import TELYNX_API_KEY, TELYNX_NUMBER, OWNER_NUMBER
from app.providers.base_provider import BaseProvider


TELNYX_MESSAGING_URL = "https://api.telnyx.com/v2/messages"


class TelnyxProvider(BaseProvider):
    """WhatsApp integration via Telnyx Messaging API.

    Allows the Company Brain to send and receive WhatsApp messages.
    All owner communications are routed through the Top Agent.
    """

    def is_available(self) -> bool:
        return bool(TELYNX_API_KEY and TELYNX_NUMBER and OWNER_NUMBER)

    def get_tools(self) -> list:
        return [self.send_whatsapp_message, self.get_whatsapp_history]

    def get_instructions(self) -> str:
        if not self.is_available():
            return ""
        return (
            "You can communicate with the owner via WhatsApp through the Telnyx API.\n"
            "- Use send_whatsapp_message to send updates, morning briefings, "
            "lead alerts, or time-sensitive notifications.\n"
            "- WhatsApp is for concise updates and notifications, not full conversations.\n"
            "- Always identify yourself and be brief in WhatsApp messages.\n"
            f"- The owner's WhatsApp number is {OWNER_NUMBER}.\n"
        )

    async def send_whatsapp_message(self, message: str) -> str:
        """Send a WhatsApp message to the owner.

        Args:
            message: The text message to send.

        Returns:
            Confirmation of delivery status.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    TELNYX_MESSAGING_URL,
                    headers={
                        "Authorization": f"Bearer {TELYNX_API_KEY}",
                        "Content-Type": "application/json",
                    },
                    json={
                        "from": f"whatsapp:{TELYNX_NUMBER}",
                        "to": f"whatsapp:{OWNER_NUMBER}",
                        "text": message,
                    },
                    timeout=10.0,
                )
                if response.status_code in (200, 201, 202):
                    return f"WhatsApp message sent successfully."
                return f"Failed to send WhatsApp: {response.status_code} - {response.text}"
        except Exception as e:
            return f"Error sending WhatsApp message: {str(e)}"

    async def get_whatsapp_history(self, limit: int = 10) -> str:
        """Retrieve recent WhatsApp message history.

        Args:
            limit: Number of recent messages to retrieve.

        Returns:
            Summary of recent messages.
        """
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{TELNYX_MESSAGING_URL}?limit={limit}",
                    headers={
                        "Authorization": f"Bearer {TELYNX_API_KEY}",
                    },
                    timeout=10.0,
                )
                if response.status_code == 200:
                    data = response.json()
                    messages = data.get("data", [])
                    if not messages:
                        return "No recent WhatsApp messages found."
                    summary_lines = []
                    for msg in messages[-limit:]:
                        direction = msg.get("direction", "unknown")
                        text = msg.get("text", "")
                        summary_lines.append(f"[{direction}] {text}")
                    return "Recent WhatsApp messages:\n" + "\n".join(summary_lines)
                return f"Failed to retrieve messages: {response.status_code}"
        except Exception as e:
            return f"Error retrieving WhatsApp history: {str(e)}"
