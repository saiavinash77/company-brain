"""Telegram bot provider — the owner chats with the Chief of Staff on Telegram.

Setup (5 minutes, free):
1. Message @BotFather on Telegram → /newbot → get the bot token
2. Put the token in .env as TELEGRAM_BOT_TOKEN and your chat id as TELEGRAM_CHAT_ID
3. Set the webhook once:
   curl "https://api.telegram.org/bot<TOKEN>/setWebhook?url=https://<host>/webhook/telegram"
4. Text your bot — the Top Agent replies.

Security: updates from any chat_id other than TELEGRAM_CHAT_ID are ignored.
"""
import logging

import aiohttp
from agno.context.provider import Status

from app.config import TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
from app.providers.base_provider import BaseProvider

logger = logging.getLogger("company-brain.telegram")

API_BASE = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}" if TELEGRAM_BOT_TOKEN else ""


class TelegramProvider(BaseProvider):
    """Send/receive Telegram messages for the Top Agent (owner-only)."""

    def __init__(self):
        super().__init__(provider_id="telegram", name="Telegram Bot")

    def get_tools(self) -> list:
        if not self.is_available():
            return []

        from agno.tools import tool

        @tool(name="send_telegram_message", description="Send a Telegram message to the owner.")
        def send_telegram_message(message: str) -> str:
            """Send `message` to the owner's Telegram chat. Use for replies,
            alerts, approvals, and daily briefings."""
            return send_message_sync(message)

        return [send_telegram_message]

    def get_instructions(self) -> str:
        if not self.is_available():
            return ""
        return (
            "## Telegram\n"
            "- You can message the owner via the send_telegram_message tool.\n"
            "- Keep messages concise; use plain text (no markdown headers).\n"
        )

    # -- ContextProvider lifecycle -------------------------------------

    def status(self) -> Status:
        if TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_ID:
            return Status(ok=True, detail="bot token + owner chat id configured")
        return Status(ok=False, detail="TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID not set")

    async def astatus(self) -> Status:
        return self.status()

    async def asetup(self) -> None:
        """Nothing to open — Telegram API is stateless HTTP."""

    async def aclose(self) -> None:
        """No persistent session held; aiohttp sessions are per-call."""


def send_message_sync(message: str) -> str:
    """Blocking send — called inside Agno tool execution threads."""
    import asyncio

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    if loop and loop.is_running():
        # We're inside an event loop; run in a worker thread to avoid blocking.
        import concurrent.futures

        with concurrent.futures.ThreadPoolExecutor(1) as ex:
            return ex.submit(asyncio.run, _send_async(message)).result(timeout=30)
    return asyncio.run(_send_async(message))


async def _send_async(message: str) -> str:
    url = f"{API_BASE}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHAT_ID, "text": message[:4000]}
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, json=payload, timeout=aiohttp.ClientTimeout(total=20)) as resp:
                data = await resp.json()
                if not data.get("ok"):
                    logger.error("Telegram sendMessage failed: %s", data)
                    return f"error: {data.get('description', 'unknown')}"
                return "sent"
    except Exception as exc:
        logger.error("Telegram sendMessage error: %s", exc)
        return f"error: {exc}"
