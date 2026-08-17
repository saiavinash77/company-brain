from twilio.rest import Client
from twilio.base.exceptions import TwilioRestException

from app.config import TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, OWNER_NUMBER
from app.providers.base_provider import BaseProvider


class TwilioProvider(BaseProvider):
    """WhatsApp integration via Twilio Messaging API.

    Allows the Company Brain to send and receive WhatsApp messages.
    All owner communications are routed through the Top Agent.

    Requires: TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN, TWILIO_PHONE_NUMBER, OWNER_NUMBER
    """

    def __init__(self):
        self._client = None

    def _get_client(self) -> Client:
        if not self._client:
            self._client = Client(TWILIO_ACCOUNT_SID, TWILIO_AUTH_TOKEN)
        return self._client

    def is_available(self) -> bool:
        return bool(TWILIO_ACCOUNT_SID and TWILIO_AUTH_TOKEN and TWILIO_PHONE_NUMBER and OWNER_NUMBER)

    def get_tools(self) -> list:
        return [self.send_whatsapp_message, self.get_whatsapp_history]

    def get_instructions(self) -> str:
        if not self.is_available():
            return ""
        return (
            "You can communicate with the owner via WhatsApp through Twilio.\n"
            "- Use send_whatsapp_message to send updates, morning briefings, "
            "lead alerts, or time-sensitive notifications.\n"
            "- WhatsApp is for concise updates and notifications, not full conversations.\n"
            "- Always identify yourself and be brief in WhatsApp messages.\n"
            f"- The owner's WhatsApp number is {OWNER_NUMBER}."
        )

    async def send_whatsapp_message(self, message: str) -> str:
        """Send a WhatsApp message to the owner.

        Args:
            message: The text message to send.

        Returns:
            Confirmation of delivery status.
        """
        try:
            client = self._get_client()
            msg = client.messages.create(
                from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
                to=f"whatsapp:{OWNER_NUMBER}",
                body=message,
            )
            return f"WhatsApp message sent successfully. SID: {msg.sid}"
        except TwilioRestException as e:
            return f"Failed to send WhatsApp: {e.code} - {e.msg}"
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
            client = self._get_client()
            messages = client.messages.list(
                limit=limit,
                from_=f"whatsapp:{TWILIO_PHONE_NUMBER}",
                to_=f"whatsapp:{OWNER_NUMBER}",
            )
            if not messages:
                return "No recent WhatsApp messages found."
            summary_lines = []
            for msg in messages:
                direction = "outbound" if msg.direction == "outbound-api" else "inbound"
                summary_lines.append(f"[{direction}] {msg.body or '(media)'}")
            return "Recent WhatsApp messages:\n" + "\n".join(summary_lines)
        except Exception as e:
            return f"Error retrieving WhatsApp history: {str(e)}"
