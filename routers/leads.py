import time
from datetime import datetime, timedelta, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
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
from services.next_action_service import suggest_next_action
from utils.structured_logging import StructuredLogger

router = APIRouter(prefix="/api/leads", tags=["leads"])
sales_view_logger = StructuredLogger(
    service="lead_sales_view", logger_name="pipedesk_drive.lead_sales_view"
)
sales_view_metrics = {"calls": 0, "errors": 0, "total_latency": 0.0}


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
    owner_id: Optional[str] = None,
    status: Optional[str] = None,
    origin: Optional[str] = None,
    min_priority_score: Optional[int] = None,
    has_recent_interaction: Optional[bool] = None,
    order_by: Literal["priority", "last_interaction", "created_at"] = "priority",
    db: Session = Depends(get_db),
):
    started = time.time()
    sales_view_metrics["calls"] += 1
    success = False

    try:
        base_query = (
            db.query(models.Lead)
            .outerjoin(models.LeadActivityStats)
            .options(
                joinedload(models.Lead.activity_stats),
                joinedload(models.Lead.owner),
                joinedload(models.Lead.primary_contact),
                joinedload(models.Lead.tags),
            )
        )
        if owner_id:
            base_query = base_query.filter(models.Lead.owner_id == owner_id)
        if status:
            base_query = base_query.filter(models.Lead.status == status)
        if origin:
            base_query = base_query.filter(models.Lead.origin == origin)
        if min_priority_score is not None:
            base_query = base_query.filter(models.Lead.priority_score >= min_priority_score)

        last_interaction_expr = func.coalesce(
            models.Lead.last_interaction_at,
            models.LeadActivityStats.last_interaction_at,
            models.Lead.updated_at,
            models.Lead.created_at,
        )

        if has_recent_interaction is True:
            threshold = datetime.now(timezone.utc) - timedelta(days=7)
            base_query = base_query.filter(last_interaction_expr >= threshold)
        elif has_recent_interaction is False:
            threshold = datetime.now(timezone.utc) - timedelta(days=7)
            base_query = base_query.filter(
                (last_interaction_expr < threshold) | (last_interaction_expr.is_(None))
            )

        if order_by == "priority":
            base_query = base_query.order_by(models.Lead.priority_score.desc())
        elif order_by == "last_interaction":
            base_query = base_query.order_by(last_interaction_expr.desc().nullslast())
        else:
            base_query = base_query.order_by(models.Lead.created_at.desc())

        total = base_query.count()
        leads: List[models.Lead] = base_query.offset((page - 1) * page_size).limit(
            page_size
        ).all()

        items: List[LeadSalesViewItem] = []
        for lead in leads:
            stats = lead.activity_stats
            score = (
                lead.priority_score
                if lead.priority_score is not None
                else calculate_lead_priority(lead, stats)
            )
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
                    next_action=suggest_next_action(lead, stats),
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

        success = True
        return LeadSalesViewResponse(
            items=paginated_items,
            page=page,
            page_size=page_size,
            total=total,
        )
    except Exception as exc:  # pragma: no cover - defensive logging path
        sales_view_metrics["errors"] += 1
        sales_view_logger.error(
            action="sales_view",
            message="Failed to build sales view",
            error=exc,
        )
        raise
    finally:
        duration = time.time() - started
        sales_view_metrics["total_latency"] += duration
        avg_latency = sales_view_metrics["total_latency"] / max(sales_view_metrics["calls"], 1)
        sales_view_logger.info(
            action="sales_view_metrics",
            status="success" if success else "error",
            message="Sales view request telemetry",
            calls=sales_view_metrics["calls"],
            errors=sales_view_metrics["errors"],
            avg_latency_ms=round(avg_latency * 1000, 2),
            last_request_ms=round(duration * 1000, 2),
        )
