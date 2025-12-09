from __future__ import annotations

"""
Gmail write-enabled service helpers.

Provides helper methods for sending messages, managing drafts, and updating
labels using the Gmail API. This is separate from the read-only
GoogleGmailService to avoid expanding scopes for read-only consumers.
"""

import base64
from email.mime.base import MIMEBase
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email import encoders
from typing import Dict, Any, List, Optional

from services.google_auth import GoogleAuthService
from utils.retry import exponential_backoff_retry

SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
]


class GmailService:
    """Service for write operations against Gmail."""

    def __init__(self):
        self.auth_service = GoogleAuthService(scopes=SCOPES)
        self.service = self.auth_service.get_service("gmail", "v1")

    def _check_auth(self):
        if not self.service:
            raise Exception(
                "Gmail Service configuration error: GOOGLE_SERVICE_ACCOUNT_JSON is missing or invalid."
            )

    def _build_message(
        self,
        to: List[str],
        subject: Optional[str] = None,
        body_text: Optional[str] = None,
        body_html: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, str]]] = None,
    ) -> str:
        """Build a MIME message and return it as base64url encoded string."""

        message = MIMEMultipart("mixed")
        message["To"] = ", ".join(to)
        if cc:
            message["Cc"] = ", ".join(cc)
        if bcc:
            message["Bcc"] = ", ".join(bcc)
        if subject:
            message["Subject"] = subject

        alternative = MIMEMultipart("alternative")
        if body_text:
            alternative.attach(MIMEText(body_text, "plain"))
        if body_html:
            alternative.attach(MIMEText(body_html, "html"))

        message.attach(alternative)

        for attachment in attachments or []:
            part = MIMEBase("application", "octet-stream")
            content = attachment.get("content")
            if content:
                part.set_payload(base64.b64decode(content))
            encoders.encode_base64(part)
            part.add_header(
                "Content-Disposition",
                f"attachment; filename={attachment.get('filename', 'attachment')}",
            )
            if attachment.get("mime_type"):
                part.add_header("Content-Type", attachment["mime_type"])
            message.attach(part)

        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        return raw_message

    @exponential_backoff_retry(max_retries=3, initial_delay=1.0)
    def send_email(
        self,
        *,
        to: List[str],
        subject: Optional[str] = None,
        body_text: Optional[str] = None,
        body_html: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, str]]] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Send an email message."""

        self._check_auth()
        raw_message = self._build_message(
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
        )

        body: Dict[str, Any] = {"raw": raw_message}
        if thread_id:
            body["threadId"] = thread_id

        return (
            self.service.users()
            .messages()
            .send(userId="me", body=body)
            .execute()
        )

    @exponential_backoff_retry(max_retries=3, initial_delay=1.0)
    def create_draft(
        self,
        *,
        to: List[str],
        subject: Optional[str] = None,
        body_text: Optional[str] = None,
        body_html: Optional[str] = None,
        cc: Optional[List[str]] = None,
        bcc: Optional[List[str]] = None,
        attachments: Optional[List[Dict[str, str]]] = None,
        thread_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Create a draft message."""

        self._check_auth()
        raw_message = self._build_message(
            to=to,
            subject=subject,
            body_text=body_text,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
            attachments=attachments,
        )
        message_body: Dict[str, Any] = {"raw": raw_message}
        if thread_id:
            message_body["threadId"] = thread_id

        return (
            self.service.users()
            .drafts()
            .create(userId="me", body={"message": message_body})
            .execute()
        )

    @exponential_backoff_retry(max_retries=3, initial_delay=1.0)
    def update_draft(self, draft_id: str, *, message: Dict[str, Any]) -> Dict[str, Any]:
        """Update an existing draft."""

        self._check_auth()
        return (
            self.service.users()
            .drafts()
            .update(userId="me", id=draft_id, body={"message": message})
            .execute()
        )

    @exponential_backoff_retry(max_retries=3, initial_delay=1.0)
    def get_draft(self, draft_id: str) -> Dict[str, Any]:
        """Retrieve a draft by ID."""

        self._check_auth()
        return self.service.users().drafts().get(userId="me", id=draft_id).execute()

    @exponential_backoff_retry(max_retries=3, initial_delay=1.0)
    def delete_draft(self, draft_id: str) -> None:
        """Delete a draft."""

        self._check_auth()
        self.service.users().drafts().delete(userId="me", id=draft_id).execute()

    @exponential_backoff_retry(max_retries=3, initial_delay=1.0)
    def update_labels(
        self, message_id: str, add_labels: Optional[List[str]] = None, remove_labels: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """Add or remove labels from a message."""

        self._check_auth()
        body = {
            "addLabelIds": add_labels or [],
            "removeLabelIds": remove_labels or [],
        }
        return (
            self.service.users()
            .messages()
            .modify(userId="me", id=message_id, body=body)
            .execute()
        )
