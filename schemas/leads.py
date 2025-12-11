from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class LeadOwner(BaseModel):
    id: Optional[str]
    name: Optional[str]


class LeadContact(BaseModel):
    id: Optional[str]
    name: Optional[str]
    email: Optional[str]
    phone: Optional[str]


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
    primary_contact: Optional[LeadContact]
    priority_score: int
    priority_bucket: str
    last_interaction_at: Optional[datetime]
    qualified_master_deal_id: Optional[str]
    address_city: Optional[str]
    address_state: Optional[str]
    tags: List[str]
    next_action: NextAction


class Pagination(BaseModel):
    total: int
    per_page: int
    page: int


class LeadSalesViewResponse(BaseModel):
    data: List[LeadSalesViewItem]
    pagination: Pagination
