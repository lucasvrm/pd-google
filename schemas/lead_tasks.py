"""
Schemas para Lead Tasks e Task Templates.
"""

from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field


# ============================================================================
# LEAD TASK TEMPLATES
# ============================================================================

class LeadTaskTemplateBase(BaseModel):
    code: str = Field(..., min_length=1, max_length=100)
    label: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None
    is_active: bool = True
    sort_order: int = 0


class LeadTaskTemplateCreate(LeadTaskTemplateBase):
    pass


class LeadTaskTemplateUpdate(BaseModel):
    code: Optional[str] = Field(None, min_length=1, max_length=100)
    label: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None
    is_active: Optional[bool] = None
    sort_order: Optional[int] = None


class LeadTaskTemplateResponse(LeadTaskTemplateBase):
    id: str
    created_at: datetime

    class Config:
        from_attributes = True


class LeadTaskTemplateListResponse(BaseModel):
    data: List[LeadTaskTemplateResponse]
    total: int


# ============================================================================
# LEAD TASKS
# ============================================================================

class LeadTaskBase(BaseModel):
    title: str = Field(..., min_length=1, max_length=500)
    description: Optional[str] = None
    is_next_action: bool = False
    status: str = Field(default="pending", pattern="^(pending|in_progress|completed|cancelled)$")
    due_date: Optional[datetime] = None


class LeadTaskCreate(LeadTaskBase):
    template_id: Optional[str] = None


class LeadTaskCreateFromTemplate(BaseModel):
    template_id: str
    is_next_action: bool = False
    due_date: Optional[datetime] = None


class LeadTaskUpdate(BaseModel):
    title: Optional[str] = Field(None, min_length=1, max_length=500)
    description: Optional[str] = None
    is_next_action: Optional[bool] = None
    status: Optional[str] = Field(None, pattern="^(pending|in_progress|completed|cancelled)$")
    due_date: Optional[datetime] = None
    sort_order: Optional[int] = None


class LeadTaskResponse(BaseModel):
    id: str
    lead_id: str
    template_id: Optional[str] = None
    template_code: Optional[str] = None
    title: str
    description: Optional[str] = None
    is_next_action: bool
    status: str
    due_date: Optional[datetime] = None
    sort_order: int
    completed_at: Optional[datetime] = None
    completed_by: Optional[str] = None
    created_at: datetime
    created_by: Optional[str] = None

    class Config:
        from_attributes = True


class LeadTaskListResponse(BaseModel):
    data: List[LeadTaskResponse]
    total: int
    next_action: Optional[LeadTaskResponse] = None


# ============================================================================
# LEAD PRIORITY
# ============================================================================

class UpdateLeadPriorityRequest(BaseModel):
    priority_bucket: str = Field(..., pattern="^(hot|warm|cold)$")


class UpdateLeadPriorityResponse(BaseModel):
    lead_id: str
    priority_bucket: str
    priority_score: int
    updated_at: datetime
