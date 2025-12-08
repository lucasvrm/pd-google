"""
Pydantic schemas for Gmail API data models.
These schemas define the structure of data exposed to the frontend.
"""

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


class Label(BaseModel):
    """
    Represents a Gmail label.
    """
    id: str
    name: str
    type: Optional[str] = None  # 'system' or 'user'
    message_list_visibility: Optional[str] = None
    label_list_visibility: Optional[str] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "INBOX",
                "name": "INBOX",
                "type": "system",
                "message_list_visibility": "show",
                "label_list_visibility": "labelShow"
            }
        }


class Attachment(BaseModel):
    """
    Represents an email attachment.
    """
    id: str = Field(description="Attachment ID for downloading")
    filename: str = Field(description="Name of the attachment file")
    mime_type: str = Field(description="MIME type of the attachment")
    size: int = Field(description="Size in bytes")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "ANGjdJ9qvx...",
                "filename": "document.pdf",
                "mime_type": "application/pdf",
                "size": 245678
            }
        }


class MessageSummary(BaseModel):
    """
    Summary view of an email message for list display.
    Contains the essential information needed for inbox/list views.
    """
    id: str = Field(description="Gmail message ID")
    thread_id: str = Field(description="Thread this message belongs to")
    subject: Optional[str] = Field(None, description="Email subject")
    from_email: Optional[str] = Field(None, description="Sender email address")
    to_email: Optional[str] = Field(None, description="Recipient email addresses")
    snippet: Optional[str] = Field(None, description="Short preview of message content")
    internal_date: Optional[datetime] = Field(None, description="Internal message date")
    labels: List[str] = Field(default_factory=list, description="List of label IDs")
    has_attachments: bool = Field(False, description="Whether message has attachments")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "18b2f3a8d4c5e1f2",
                "thread_id": "18b2f3a8d4c5e1f2",
                "subject": "Q4 Sales Report",
                "from_email": "john@company.com",
                "to_email": "team@company.com",
                "snippet": "Please find attached the Q4 sales report for your review...",
                "internal_date": "2024-01-15T14:30:00Z",
                "labels": ["INBOX", "IMPORTANT"],
                "has_attachments": True
            }
        }


class MessageDetail(BaseModel):
    """
    Detailed view of an email message.
    Contains complete message information including body and attachments.
    """
    id: str = Field(description="Gmail message ID")
    thread_id: str = Field(description="Thread this message belongs to")
    subject: Optional[str] = Field(None, description="Email subject")
    from_email: Optional[str] = Field(None, description="Sender email address")
    to_email: Optional[str] = Field(None, description="Recipient email addresses")
    cc_email: Optional[str] = Field(None, description="CC recipients")
    bcc_email: Optional[str] = Field(None, description="BCC recipients")
    snippet: Optional[str] = Field(None, description="Short preview of message content")
    internal_date: Optional[datetime] = Field(None, description="Internal message date")
    labels: List[str] = Field(default_factory=list, description="List of label IDs")
    plain_text_body: Optional[str] = Field(None, description="Plain text body of the email")
    html_body: Optional[str] = Field(None, description="HTML body of the email")
    attachments: List[Attachment] = Field(default_factory=list, description="List of attachments")
    web_link: Optional[str] = Field(None, description="Link to view in Gmail web UI")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "18b2f3a8d4c5e1f2",
                "thread_id": "18b2f3a8d4c5e1f2",
                "subject": "Q4 Sales Report",
                "from_email": "john@company.com",
                "to_email": "team@company.com",
                "cc_email": "manager@company.com",
                "bcc_email": None,
                "snippet": "Please find attached the Q4 sales report...",
                "internal_date": "2024-01-15T14:30:00Z",
                "labels": ["INBOX", "IMPORTANT"],
                "plain_text_body": "Please find attached the Q4 sales report for your review.\n\nBest regards,\nJohn",
                "html_body": "<p>Please find attached the Q4 sales report for your review.</p><p>Best regards,<br>John</p>",
                "attachments": [
                    {
                        "id": "ANGjdJ9qvx...",
                        "filename": "Q4_Sales_Report.pdf",
                        "mime_type": "application/pdf",
                        "size": 245678
                    }
                ],
                "web_link": "https://mail.google.com/mail/u/0/#inbox/18b2f3a8d4c5e1f2"
            }
        }


class ThreadSummary(BaseModel):
    """
    Summary view of an email thread for list display.
    """
    id: str = Field(description="Gmail thread ID")
    snippet: Optional[str] = Field(None, description="Preview of the latest message")
    message_count: int = Field(0, description="Number of messages in the thread")
    participants: List[str] = Field(default_factory=list, description="List of participant emails")
    last_message_date: Optional[datetime] = Field(None, description="Date of the most recent message")
    labels: List[str] = Field(default_factory=list, description="Labels applied to the thread")
    has_attachments: bool = Field(False, description="Whether any message has attachments")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "18b2f3a8d4c5e1f2",
                "snippet": "Great! Let's schedule a follow-up meeting...",
                "message_count": 5,
                "participants": ["john@company.com", "jane@company.com", "bob@company.com"],
                "last_message_date": "2024-01-15T16:45:00Z",
                "labels": ["INBOX"],
                "has_attachments": True
            }
        }


class ThreadDetail(BaseModel):
    """
    Detailed view of an email thread with all messages.
    """
    id: str = Field(description="Gmail thread ID")
    messages: List[MessageSummary] = Field(description="List of messages in the thread")
    snippet: Optional[str] = Field(None, description="Preview of the latest message")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "18b2f3a8d4c5e1f2",
                "snippet": "Great! Let's schedule a follow-up meeting...",
                "messages": [
                    {
                        "id": "18b2f3a8d4c5e1f2",
                        "thread_id": "18b2f3a8d4c5e1f2",
                        "subject": "Q4 Sales Report",
                        "from_email": "john@company.com",
                        "to_email": "team@company.com",
                        "snippet": "Please find attached...",
                        "internal_date": "2024-01-15T14:30:00Z",
                        "labels": ["INBOX"],
                        "has_attachments": True
                    }
                ]
            }
        }


class MessageListResponse(BaseModel):
    """
    Response for listing messages with pagination.
    """
    messages: List[MessageSummary]
    next_page_token: Optional[str] = None
    result_size_estimate: Optional[int] = None


class ThreadListResponse(BaseModel):
    """
    Response for listing threads with pagination.
    """
    threads: List[ThreadSummary]
    next_page_token: Optional[str] = None
    result_size_estimate: Optional[int] = None


class LabelListResponse(BaseModel):
    """
    Response for listing labels.
    """
    labels: List[Label]
