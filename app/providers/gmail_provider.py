import base64
import json
import logging
import os
from datetime import datetime, timedelta
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

import httpx
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from app.config import GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN
from app.providers.base_provider import BaseProvider

logger = logging.getLogger("company-brain.gmail")


class GmailProvider(BaseProvider):
    """Gmail integration for reading, sending, and watching client emails.

    Uses the Gmail API with OAuth2 (service account or user credentials).
    The provider creates a tool that agents can use to:
    - Read unread emails from specific senders
    - Send emails
    - Search emails by query

    Requires: GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN
    """

    SCOPES = [
        "https://www.googleapis.com/auth/gmail.readonly",
        "https://www.googleapis.com/auth/gmail.send",
        "https://www.googleapis.com/auth/gmail.modify",
    ]

    def __init__(self):
        self._service = None
        self._creds = None

    def is_available(self) -> bool:
        return bool(GMAIL_CLIENT_ID and GMAIL_CLIENT_SECRET and GMAIL_REFRESH_TOKEN)

    def _get_credentials(self) -> Credentials:
        """Get or refresh OAuth2 credentials."""
        if self._creds and not self._creds.expired:
            return self._creds

        self._creds = Credentials(
            client_id=GMAIL_CLIENT_ID,
            client_secret=GMAIL_CLIENT_SECRET,
            refresh_token=GMAIL_REFRESH_TOKEN,
            token_uri="https://oauth2.googleapis.com/token",
            scopes=self.SCOPES,
        )

        # Refresh if expired
        if self._creds.expired:
            self._creds.refresh(httpx.Client())
            logger.info("Gmail credentials refreshed")

        return self._creds

    def _get_service(self):
        """Get the Gmail API service instance."""
        if not self._service:
            creds = self._get_credentials()
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    def get_tools(self) -> list:
        if not self.is_available():
            logger.warning("Gmail provider not configured — skipping tools")
            return []
        return [
            self.read_unread_emails,
            self.send_email,
            self.search_emails,
        ]

    def get_instructions(self) -> str:
        if not self.is_available():
            return ""
        return (
            "You have access to Gmail for client communications.\n"
            "- Use read_unread_emails to check for new client emails.\n"
            "- Use send_email to respond to clients (only after owner approval).\n"
            "- Use search_emails to find past emails from or about a client.\n"
            "- NEVER send emails without owner approval.\n"
            "- Always store important email content in the client vault."
        )

    async def read_unread_emails(
        self,
        max_results: int = 10,
        sender: str = "",
    ) -> str:
        """Read unread emails from the inbox, optionally filtered by sender.

        Args:
            max_results: Maximum number of emails to return (default 10).
            sender: Optional email address to filter by sender.

        Returns:
            Summary of unread emails with sender, subject, and snippet.
        """
        try:
            service = self._get_service()
            query = "is:unread"
            if sender:
                query += f" from:{sender}"

            results = service.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()

            messages = results.get("messages", [])
            if not messages:
                return "No unread emails found."

            lines = [f"Found {len(messages)} unread email(s):\n"]
            for msg in messages:
                msg_data = (
                    service.users()
                    .messages()
                    .get(userId="me", id=msg["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"])
                    .execute()
                )
                headers = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
                lines.append(
                    f"- From: {headers.get('From', 'unknown')} | "
                    f"Subject: {headers.get('Subject', 'no subject')} | "
                    f"Date: {headers.get('Date', 'unknown')}"
                )

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Error reading Gmail: {e}")
            return f"Error reading emails: {e}"

    async def send_email(
        self,
        to: str,
        subject: str,
        body: str,
        cc: str = "",
    ) -> str:
        """Send an email. REQUIRES OWNER APPROVAL before calling.

        Args:
            to: Recipient email address.
            subject: Email subject line.
            body: Email body text.
            cc: Optional CC recipients (comma-separated).

        Returns:
            Confirmation or error message.
        """
        try:
            service = self._get_service()

            msg = MIMEMultipart("alternative")
            msg["To"] = to
            msg["Subject"] = subject
            if cc:
                msg["Cc"] = cc

            msg.attach(MIMEText(body, "plain"))

            raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
            send_result = (
                service.users()
                .messages()
                .send(userId="me", body={"raw": raw})
                .execute()
            )

            return f"Email sent successfully to {to}. Message ID: {send_result.get('id', 'unknown')}"

        except Exception as e:
            logger.error(f"Error sending Gmail: {e}")
            return f"Error sending email: {e}"

    async def search_emails(
        self,
        query: str,
        max_results: int = 10,
    ) -> str:
        """Search Gmail using Gmail search operators.

        Args:
            query: Gmail search query (e.g., 'from:client@company.com subject:invoice').
            max_results: Maximum results to return.

        Returns:
            Summary of matching emails.
        """
        try:
            service = self._get_service()

            results = service.users().messages().list(
                userId="me", q=query, maxResults=max_results
            ).execute()

            messages = results.get("messages", [])
            if not messages:
                return f"No emails found matching: {query}"

            lines = [f"Found {len(messages)} email(s) matching '{query}':\n"]
            for msg in messages:
                msg_data = (
                    service.users()
                    .messages()
                    .get(userId="me", id=msg["id"], format="metadata", metadataHeaders=["From", "Subject", "Date"])
                    .execute()
                )
                headers = {h["name"]: h["value"] for h in msg_data.get("payload", {}).get("headers", [])}
                lines.append(
                    f"- From: {headers.get('From', 'unknown')} | "
                    f"Subject: {headers.get('Subject', 'no subject')} | "
                    f"Date: {headers.get('Date', 'unknown')}"
                )

            return "\n".join(lines)

        except Exception as e:
            logger.error(f"Error searching Gmail: {e}")
            return f"Error searching emails: {e}"
