from __future__ import annotations

from typing import List, Optional
from pydantic import BaseModel, Field


class EmailAttachment(BaseModel):
    """Attachment payload for outgoing messages."""

    filename: str = Field(description="Attachment file name")
    mime_type: Optional[str] = Field(None, description="MIME type of the attachment")
    content: str = Field(description="Base64-encoded content of the attachment")


class SendEmailRequest(BaseModel):
    """Request body for sending an email."""

    to: List[str] = Field(..., description="List of recipient email addresses")
    cc: Optional[List[str]] = Field(None, description="List of CC recipients")
    bcc: Optional[List[str]] = Field(None, description="List of BCC recipients")
    subject: Optional[str] = Field(None, description="Email subject")
    body_text: Optional[str] = Field(None, description="Plain text body content")
    body_html: Optional[str] = Field(None, description="HTML body content")
    attachments: Optional[List[EmailAttachment]] = Field(None, description="Attachments to include")
    thread_id: Optional[str] = Field(None, description="Thread ID to reply within")

    class Config:
        json_schema_extra = {
            "example": {
                "to": ["recipient@example.com"],
                "cc": ["manager@example.com"],
                "subject": "Status Update",
                "body_text": "Weekly update attached.",
                "attachments": [
                    {
                        "filename": "report.pdf",
                        "mime_type": "application/pdf",
                        "content": "<base64-encoded>"
                    }
                ]
            }
        }


class DraftRequest(SendEmailRequest):
    """Request body for creating or updating a draft."""


class SentMessage(BaseModel):
    """Minimal information about a sent or draft message."""

    id: str = Field(description="Gmail message ID")
    thread_id: Optional[str] = Field(None, description="Thread ID associated with the message")
    label_ids: Optional[List[str]] = Field(None, description="Labels applied to the message")


class DraftResponse(BaseModel):
    """Response for draft operations."""

    id: str = Field(description="Draft ID")
    message: Optional[SentMessage] = Field(None, description="Underlying message metadata")


class LabelUpdateRequest(BaseModel):
    """Payload for updating Gmail labels on a message."""

    add_labels: List[str] = Field(default_factory=list, description="Label IDs to add")
    remove_labels: List[str] = Field(default_factory=list, description="Label IDs to remove")


class LabelUpdateResponse(BaseModel):
    """Result of a label modification request."""

    id: str = Field(description="Message ID")
    label_ids: List[str] = Field(default_factory=list, description="Resulting label IDs after update")
