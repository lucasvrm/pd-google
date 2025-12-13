"""
Timeline Schemas

Pydantic models for the Unified Timeline API response.
Provides a standardized structure for all timeline event types.
"""

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel


class TimelineUser(BaseModel):
    """User information for timeline entries."""
    id: Optional[str] = None
    name: Optional[str] = None
    email: Optional[str] = None


class TimelineEntry(BaseModel):
    """
    Standardized timeline entry.
    
    Represents a single event in the unified timeline, which can be:
    - meeting: Calendar event
    - audit: Audit log entry (create, update, status_change)
    - email: Email communication (placeholder)
    """
    type: Literal["meeting", "audit", "email"]
    timestamp: datetime
    summary: str
    details: Optional[Dict[str, Any]] = None
    user: Optional[TimelineUser] = None


class TimelinePagination(BaseModel):
    """Pagination metadata for timeline responses."""
    total: int
    limit: int
    offset: int


class TimelineResponse(BaseModel):
    """
    Response model for the unified timeline endpoint.
    
    Contains a list of timeline items from all sources (calendar, audit, email)
    sorted by timestamp in descending order.
    """
    items: List[TimelineEntry]
    pagination: TimelinePagination

    class Config:
        json_schema_extra = {
            "example": {
                "items": [
                    {
                        "type": "meeting",
                        "timestamp": "2024-01-15T14:00:00Z",
                        "summary": "Sales Meeting - Client Review",
                        "details": {
                            "google_event_id": "evt_abc123",
                            "meet_link": "https://meet.google.com/abc-defg-hij",
                            "status": "confirmed",
                            "attendees": ["client@example.com"]
                        },
                        "user": {
                            "id": "user-123",
                            "name": "John Doe",
                            "email": "john@company.com"
                        }
                    },
                    {
                        "type": "audit",
                        "timestamp": "2024-01-14T10:30:00Z",
                        "summary": "Status changed: New → Qualified",
                        "details": {
                            "action": "status_change",
                            "field": "lead_status_id",
                            "old_value": "status-new-id",
                            "new_value": "status-qualified-id"
                        },
                        "user": {
                            "id": "user-456",
                            "name": "Jane Smith",
                            "email": "jane@company.com"
                        }
                    },
                    {
                        "type": "email",
                        "timestamp": "2024-01-13T16:45:00Z",
                        "summary": "Re: Product inquiry",
                        "details": {
                            "subject": "Re: Product inquiry",
                            "from": "client@example.com",
                            "to": ["sales@company.com"]
                        },
                        "user": None
                    }
                ],
                "pagination": {
                    "total": 25,
                    "limit": 20,
                    "offset": 0
                }
            }
        }
