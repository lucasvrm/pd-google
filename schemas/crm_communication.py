"""
Pydantic schemas for CRM Communication API.
These schemas define aggregated email and event data associated with CRM entities.
"""

from pydantic import BaseModel, Field
from typing import List, Optional, Literal
from datetime import datetime


class EmailSummaryForCRM(BaseModel):
    """
    Email summary tailored for CRM entity display.
    Shows essential information about emails associated with a Company/Lead/Deal.
    """
    id: str = Field(description="Gmail message ID")
    thread_id: str = Field(description="Thread this message belongs to")
    subject: Optional[str] = Field(None, description="Email subject")
    from_email: Optional[str] = Field(None, description="Sender email address")
    to_email: Optional[str] = Field(None, description="Recipient email addresses")
    cc_email: Optional[str] = Field(None, description="CC recipients")
    snippet: Optional[str] = Field(None, description="Short preview of message content")
    internal_date: Optional[datetime] = Field(None, description="Internal message date")
    has_attachments: bool = Field(False, description="Whether message has attachments")
    matched_contacts: List[str] = Field(default_factory=list, description="Entity contact emails that matched in this email")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "18b2f3a8d4c5e1f2",
                "thread_id": "18b2f3a8d4c5e1f2",
                "subject": "Q4 Sales Discussion",
                "from_email": "client@company.com",
                "to_email": "sales@ourcompany.com",
                "cc_email": "manager@ourcompany.com",
                "snippet": "Following up on our previous conversation about Q4 targets...",
                "internal_date": "2024-01-15T14:30:00Z",
                "has_attachments": True,
                "matched_contacts": ["client@company.com"]
            }
        }


class EventSummaryForCRM(BaseModel):
    """
    Calendar event summary tailored for CRM entity display.
    Shows essential information about events associated with a Company/Lead/Deal.
    """
    id: int = Field(description="Internal database event ID")
    google_event_id: str = Field(description="Google Calendar event ID")
    summary: str = Field(description="Event title")
    description: Optional[str] = Field(None, description="Event description")
    start_time: datetime = Field(description="Event start datetime")
    end_time: datetime = Field(description="Event end datetime")
    meet_link: Optional[str] = Field(None, description="Google Meet link if available")
    html_link: Optional[str] = Field(None, description="Link to view in Google Calendar")
    status: Optional[str] = Field(None, description="Event status (confirmed, tentative, cancelled)")
    organizer_email: Optional[str] = Field(None, description="Email of event organizer")
    matched_contacts: List[str] = Field(default_factory=list, description="Entity contact emails that are attendees")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": 42,
                "google_event_id": "evt_abc123xyz",
                "summary": "Client Meeting - Q4 Review",
                "description": "Quarterly review meeting with client",
                "start_time": "2024-01-15T14:00:00+00:00",
                "end_time": "2024-01-15T15:00:00+00:00",
                "meet_link": "https://meet.google.com/abc-defg-hij",
                "html_link": "https://calendar.google.com/event?eid=abc123",
                "status": "confirmed",
                "organizer_email": "sales@ourcompany.com",
                "matched_contacts": ["client@company.com"]
            }
        }


class EmailListForCRMResponse(BaseModel):
    """
    Response for listing emails associated with a CRM entity.
    """
    emails: List[EmailSummaryForCRM]
    total: int = Field(description="Total number of matching emails")
    limit: int
    offset: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "emails": [
                    {
                        "id": "18b2f3a8d4c5e1f2",
                        "thread_id": "18b2f3a8d4c5e1f2",
                        "subject": "Q4 Sales Discussion",
                        "from_email": "client@company.com",
                        "to_email": "sales@ourcompany.com",
                        "snippet": "Following up on our previous conversation...",
                        "internal_date": "2024-01-15T14:30:00Z",
                        "has_attachments": False,
                        "matched_contacts": ["client@company.com"]
                    }
                ],
                "total": 25,
                "limit": 50,
                "offset": 0
            }
        }


class EventListForCRMResponse(BaseModel):
    """
    Response for listing events associated with a CRM entity.
    """
    events: List[EventSummaryForCRM]
    total: int = Field(description="Total number of matching events")
    limit: int
    offset: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "events": [
                    {
                        "id": 42,
                        "google_event_id": "evt_abc123xyz",
                        "summary": "Client Meeting - Q4 Review",
                        "description": "Quarterly review meeting",
                        "start_time": "2024-01-15T14:00:00+00:00",
                        "end_time": "2024-01-15T15:00:00+00:00",
                        "meet_link": "https://meet.google.com/abc-defg-hij",
                        "status": "confirmed",
                        "matched_contacts": ["client@company.com"]
                    }
                ],
                "total": 12,
                "limit": 50,
                "offset": 0
            }
        }


class TimelineItem(BaseModel):
    """
    Unified timeline item representing either an email or calendar event.
    Used to display a chronological view of all communications with a CRM entity.
    """
    id: str = Field(description="Unique identifier (Gmail message ID or Calendar event ID)")
    source: Literal["gmail", "calendar"] = Field(description="Source of this timeline item")
    item_type: Literal["email", "event"] = Field(description="Type of communication", serialization_alias="type")
    subject: str = Field(description="Email subject or event summary")
    snippet: Optional[str] = Field(None, description="Preview text for emails or event description")
    item_datetime: datetime = Field(description="Date/time of the communication (email date or event start)", serialization_alias="datetime")
    participants: List[str] = Field(default_factory=list, description="Email addresses involved")
    matched_contacts: List[str] = Field(default_factory=list, description="Entity contact emails that matched")
    entity_type: str = Field(description="Type of CRM entity (company, lead, deal)")
    entity_id: str = Field(description="ID of the CRM entity")
    
    class Config:
        json_schema_extra = {
            "example": {
                "id": "18b2f3a8d4c5e1f2",
                "source": "gmail",
                "type": "email",
                "subject": "Q4 Sales Discussion",
                "snippet": "Following up on our previous conversation about Q4 targets...",
                "datetime": "2024-01-15T14:30:00Z",
                "participants": ["client@company.com", "sales@ourcompany.com"],
                "matched_contacts": ["client@company.com"],
                "entity_type": "company",
                "entity_id": "comp-123"
            }
        }


class TimelineResponse(BaseModel):
    """
    Response for unified timeline of emails and events for a CRM entity.
    """
    items: List[TimelineItem]
    total: int = Field(description="Total number of timeline items")
    limit: int
    offset: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "id": "evt_abc123",
                        "source": "calendar",
                        "type": "event",
                        "subject": "Client Meeting - Q4 Review",
                        "snippet": "Quarterly review meeting with client",
                        "datetime": "2024-01-16T14:00:00+00:00",
                        "participants": ["client@company.com", "sales@ourcompany.com"],
                        "matched_contacts": ["client@company.com"],
                        "entity_type": "company",
                        "entity_id": "comp-123"
                    },
                    {
                        "id": "18b2f3a8d4c5e1f2",
                        "source": "gmail",
                        "type": "email",
                        "subject": "Q4 Sales Discussion",
                        "snippet": "Following up on our previous conversation...",
                        "datetime": "2024-01-15T14:30:00Z",
                        "participants": ["client@company.com", "sales@ourcompany.com"],
                        "matched_contacts": ["client@company.com"],
                        "entity_type": "company",
                        "entity_id": "comp-123"
                    }
                ],
                "total": 37,
                "limit": 50,
                "offset": 0
            }
        }
