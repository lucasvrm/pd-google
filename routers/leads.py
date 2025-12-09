from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session, joinedload

import models
from database import SessionLocal
from schemas.leads import (
    LeadContact,
    LeadOwner,
    LeadSalesViewItem,
    LeadSalesViewResponse,
)
from services.lead_priority_service import (
    calculate_lead_priority,
    classify_priority_bucket,
)

router = APIRouter(prefix="/api/leads", tags=["leads"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


@router.get("/sales-view", response_model=LeadSalesViewResponse)
def sales_view(
    page: int = Query(1, ge=1, description="Página atual"),
    page_size: int = Query(20, ge=1, le=100, description="Quantidade por página"),
    db: Session = Depends(get_db),
):
    base_query = (
        db.query(models.Lead)
        .options(
            joinedload(models.Lead.activity_stats),
            joinedload(models.Lead.owner),
            joinedload(models.Lead.primary_contact),
            joinedload(models.Lead.tags),
        )
    )

    total = base_query.count()
    leads: List[models.Lead] = base_query.all()

    items: List[LeadSalesViewItem] = []
    for lead in leads:
        stats = lead.activity_stats
        score = calculate_lead_priority(lead, stats)
        bucket = classify_priority_bucket(score)

        last_interaction = (
            stats.last_interaction_at
            if stats and stats.last_interaction_at
            else lead.updated_at or lead.created_at
        )
        last_interaction = _normalize_datetime(last_interaction)

        items.append(
            LeadSalesViewItem(
                id=lead.id,
                legal_name=getattr(lead, "legal_name", None) or lead.title,
                trade_name=lead.trade_name,
                status=lead.status,
                origin=lead.origin,
                owner=LeadOwner(id=lead.owner.id, name=lead.owner.name)
                if lead.owner
                else None,
                priority_score=score,
                priority_bucket=bucket,
                last_interaction_at=last_interaction,
                primary_contact=
                LeadContact(
                    id=lead.primary_contact.id,
                    name=lead.primary_contact.name,
                    email=lead.primary_contact.email,
                    phone=lead.primary_contact.phone,
                )
                if lead.primary_contact
                else None,
                tags=[tag.name for tag in lead.tags] if lead.tags else [],
            )
        )

    items = sorted(
        items,
        key=lambda item: (
            -item.priority_score,
            item.last_interaction_at is None,
            -(item.last_interaction_at.timestamp()) if item.last_interaction_at else 0,
        ),
    )

    start = (page - 1) * page_size
    end = start + page_size
    paginated_items = items[start:end]

    return LeadSalesViewResponse(
        items=paginated_items,
        page=page,
        page_size=page_size,
        total=total,
    )
