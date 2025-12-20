from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class LeadOwner(BaseModel):
    id: Optional[str]
    name: Optional[str]


class TagItem(BaseModel):
    id: str
    name: str
    color: Optional[str] = None


class PrimaryContact(BaseModel):
    id: Optional[str] = None
    name: Optional[str] = None
    role: Optional[str] = None


class NextAction(BaseModel):
    code: str
    label: str
    reason: str


class LeadSalesViewItem(BaseModel):
    id: str
    legal_name: Optional[str]
    trade_name: Optional[str]
    lead_status_id: Optional[str]
    lead_origin_id: Optional[str]
    owner_user_id: Optional[str]
    owner: Optional[LeadOwner]
    priority_score: int
    priority_bucket: str
    last_interaction_at: Optional[datetime]
    qualified_master_deal_id: Optional[str]
    address_city: Optional[str]
    address_state: Optional[str]
    tags: List[TagItem]
    primary_contact: Optional[PrimaryContact] = None
    priority_description: Optional[str] = None
    next_action: NextAction


class Pagination(BaseModel):
    total: int
    per_page: int
    page: int


class LeadSalesViewResponse(BaseModel):
    data: List[LeadSalesViewItem]
    pagination: Pagination


# ===== Lead Qualification Schemas =====

class QualifyLeadRequest(BaseModel):
    """Request body for qualifying a lead."""
    deal_id: str  # ID of the Deal to link the qualified lead to


class MigratedFields(BaseModel):
    """Fields migrated from Lead to Deal during qualification."""
    legal_name: Optional[str] = None
    trade_name: Optional[str] = None
    owner_user_id: Optional[str] = None
    description: Optional[str] = None
    tags: List[str] = []  # List of tag IDs


class QualifyLeadResponse(BaseModel):
    """Response body for lead qualification."""
    status: str  # "qualified"
    lead_id: str
    deal_id: str
    qualified_at: datetime
    deleted_at: datetime
    migrated_fields: MigratedFields


# ===== Lead Change Owner Schemas =====

class ChangeOwnerRequest(BaseModel):
    """Request body for changing lead owner."""
    new_owner_id: str  # UUID of the new owner (required)
    current_user_id: str  # UUID of the user making the change (required)
    add_previous_owner_as_member: bool = True  # Whether to add previous owner as collaborator (default: True)


class ChangeOwnerResponse(BaseModel):
    """Response body for change owner operation."""
    status: str  # "success"
    lead_id: str
    previous_owner_id: Optional[str]
    new_owner_id: str
    changed_by: str
    changed_at: datetime
