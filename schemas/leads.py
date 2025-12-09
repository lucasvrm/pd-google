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


class LeadSalesViewItem(BaseModel):
    id: str
    legal_name: Optional[str]
    trade_name: Optional[str]
    status: Optional[str]
    origin: Optional[str]
    owner: Optional[LeadOwner]
    priority_score: int
    priority_bucket: str
    last_interaction_at: Optional[datetime]
    primary_contact: Optional[LeadContact]
    tags: List[str]


class LeadSalesViewResponse(BaseModel):
    items: List[LeadSalesViewItem]
    page: int
    page_size: int
    total: int
