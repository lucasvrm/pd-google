import time
from datetime import datetime, timedelta, timezone
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse
from psycopg2 import Error as PsycopgError
from sqlalchemy import func
from sqlalchemy.exc import ProgrammingError
from sqlalchemy.orm import Session, joinedload

import models
from auth.dependencies import get_current_user_optional
from auth.jwt import UserContext
from database import SessionLocal
from schemas.leads import (
    LeadOwner,
    LeadSalesViewItem,
    LeadSalesViewResponse,
    Pagination,
    PrimaryContact,
    TagItem,
)
from services.lead_priority_service import (
    calculate_lead_priority,
    classify_priority_bucket,
)
from services.next_action_service import suggest_next_action
from utils.prometheus import Counter, Histogram
from utils.structured_logging import StructuredLogger

router = APIRouter(prefix="/api/leads", tags=["leads"])
sales_view_route_id = "sales_view"
sales_view_logger = StructuredLogger(
    service="lead_sales_view", logger_name="pipedesk_drive.lead_sales_view"
)
sales_view_metrics = {"calls": 0, "errors": 0, "total_latency": 0.0}

sales_view_request_counter = Counter(
    "sales_view_requests_total",
    "Total number of /api/leads/sales-view requests grouped by HTTP status",
    ["status_code"],
)
sales_view_latency_histogram = Histogram(
    "sales_view_latency_seconds",
    "Latency in seconds for /api/leads/sales-view requests",
    buckets=(0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 30, 60),
)
sales_view_items_histogram = Histogram(
    "sales_view_items_returned",
    "Number of items returned by /api/leads/sales-view",
    buckets=(0, 1, 5, 10, 20, 50, 100, 200, 500),
)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _normalize_datetime(value: Any) -> Optional[datetime]:
    if value is None:
        return None

    if isinstance(value, str):
        try:
            # Try parsing ISO format
            value = datetime.fromisoformat(value)
        except ValueError:
            return None

    if not isinstance(value, datetime):
        return None

    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _normalize_filter_list(value: Optional[str]) -> List[str]:
    """Normalize filter values from CSV string or single value to list."""
    # Handle FastAPI Query objects (when called directly in tests)
    if hasattr(value, "__class__") and value.__class__.__name__ == "Query":
        return []
    if not value or not isinstance(value, str):
        return []
    # Split by comma and strip whitespace
    items = [item.strip() for item in value.split(",")]
    # Filter out empty strings
    return [item for item in items if item]


def _priority_description_from_bucket(bucket: str) -> Optional[str]:
    descriptions = {
        "hot": "Alta prioridade",
        "warm": "Prioridade média",
        "cold": "Baixa prioridade",
    }
    return descriptions.get(bucket)


@router.get("/sales-view", response_model=LeadSalesViewResponse)
def sales_view(
    page: int = Query(1, ge=1, description="Página atual"),
    page_size: int = Query(
        20,
        ge=1,
        le=100,
        alias="pageSize",
        description="Quantidade por página (aceita pageSize ou page_size)",
    ),
    page_size_override: Optional[int] = Query(
        None, ge=1, le=100, alias="page_size", description="Alias para page_size"
    ),
    owner: Optional[str] = Query(None, description="Owner ID filter"),
    owner_ids: Optional[str] = Query(
        None, alias="ownerIds", description="Owner IDs filter (CSV)"
    ),
    owners: Optional[str] = Query(None, description="Owners filter (CSV)"),
    owner_id: Optional[str] = Query(
        None, alias="owner_id", description="Owner ID filter (legacy name)"
    ),
    owner_user_id: Optional[str] = Query(
        None, alias="owner_user_id", description="Owner user ID filter"
    ),
    status: Optional[str] = Query(None, description="Status filter (CSV)"),
    origin: Optional[str] = Query(None, description="Origin filter (CSV)"),
    priority: Optional[str] = Query(None, description="Priority bucket filter (CSV)"),
    min_priority_score: Optional[int] = Query(
        None, description="Minimum priority score"
    ),
    has_recent_interaction: Optional[bool] = Query(
        None, description="Filter by recent interaction"
    ),
    order_by: str = Query("priority", description="Campo de ordenação"),
    filters: Optional[str] = Query(None, description="Additional filters (JSON)"),
    current_user: Optional[UserContext] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    started = time.perf_counter()
    sales_view_metrics["calls"] += 1
    http_status = 200
    item_count = 0
    success = False

    # Extract actual values from Query objects (for direct test calls)
    def _extract_value(val):
        if hasattr(val, "__class__") and val.__class__.__name__ == "Query":
            return val.default
        return val

    owner = _extract_value(owner)
    owner_ids = _extract_value(owner_ids)
    owners = _extract_value(owners)
    owner_id = _extract_value(owner_id)
    owner_user_id = _extract_value(owner_user_id)
    status = _extract_value(status)
    origin = _extract_value(origin)
    priority = _extract_value(priority)
    min_priority_score = _extract_value(min_priority_score)
    has_recent_interaction = _extract_value(has_recent_interaction)
    order_by = _extract_value(order_by)
    page_size_override = _extract_value(page_size_override)

    # Determine effective page size supporting pageSize and page_size
    effective_page_size = page_size_override or page_size

    # Normalize owner filters - accept from multiple sources
    owner_filter: List[str] = []
    if owner:
        owner_filter.extend(_normalize_filter_list(owner))
    if owner_ids:
        owner_filter.extend(_normalize_filter_list(owner_ids))
    if owners:
        owner_filter.extend(_normalize_filter_list(owners))
    if owner_id:
        owner_filter.extend(_normalize_filter_list(owner_id))
    if owner_user_id:
        owner_filter.extend(_normalize_filter_list(owner_user_id))

    if owner_filter:
        normalized_owner_filter = []
        for value in owner_filter:
            if isinstance(value, str) and value.lower() == "me":
                if not current_user or not current_user.id:
                    raise HTTPException(
                        status_code=401,
                        detail="Authentication required for owner=me filter",
                    )
                normalized_owner_filter.append(str(current_user.id))
            else:
                normalized_owner_filter.append(value)
        owner_filter = normalized_owner_filter

    # Normalize other filters
    status_filter = _normalize_filter_list(status)
    origin_filter = _normalize_filter_list(origin)
    priority_filter = _normalize_filter_list(priority)

    # Parse order_by to handle descending order with "-" prefix
    order_desc = False
    order_field = order_by
    if order_by and order_by.startswith("-"):
        order_desc = True
        order_field = order_by[1:]

    valid_order_by = ["priority", "last_interaction", "created_at"]
    if order_field not in valid_order_by:
        sales_view_logger.warning(
            action="sales_view_invalid_param",
            message=f"Invalid order_by parameter: {order_by}, defaulting to priority",
            route=sales_view_route_id,
        )
        order_field = "priority"
        order_desc = False

    # Log initial params
    request_params = {
        "page": page,
        "page_size": effective_page_size,
        "owner": owner,
        "owner_filter": owner_filter,
        "status_filter": status_filter,
        "origin_filter": origin_filter,
        "priority_filter": priority_filter,
        "order_by": order_by,
        "has_recent_interaction": has_recent_interaction,
    }
    sales_view_logger.info(
        action="sales_view_request",
        message="Sales view request parameters",
        route=sales_view_route_id,
        params=request_params,
    )

    try:
        try:
            base_query = (
                db.query(models.Lead)
                .outerjoin(models.LeadActivityStats)
                .outerjoin(models.User, models.User.id == models.Lead.owner_user_id)
                .options(
                    joinedload(models.Lead.activity_stats),
                    joinedload(models.Lead.owner),
                    joinedload(models.Lead.lead_status),
                    joinedload(models.Lead.lead_origin),
                    joinedload(models.Lead.qualified_master_deal),
                    joinedload(models.Lead.tags),
                )
            )
            # Apply owner filter - support list
            if owner_filter:
                base_query = base_query.filter(
                    models.Lead.owner_user_id.in_(owner_filter)
                )

            # Apply status filter - support list
            if status_filter:
                base_query = base_query.filter(
                    models.Lead.lead_status_id.in_(status_filter)
                )

            # Apply origin filter - support list
            if origin_filter:
                base_query = base_query.filter(
                    models.Lead.lead_origin_id.in_(origin_filter)
                )

            # Apply priority filter - support list (for priority_bucket)
            if priority_filter:
                # Note: priority is the bucket (hot/warm/cold), not the score
                # This would need to be implemented based on calculated buckets
                # For now, we'll skip this as it requires post-filtering
                pass

            if min_priority_score is not None:
                base_query = base_query.filter(
                    models.Lead.priority_score >= min_priority_score
                )

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
                    (last_interaction_expr < threshold)
                    | (last_interaction_expr.is_(None))
                )

            # Apply ordering with direction support
            if order_field == "priority":
                order_expr = (
                    models.Lead.priority_score.desc()
                    if not order_desc
                    else models.Lead.priority_score.asc()
                )
                base_query = base_query.order_by(order_expr)
            elif order_field == "last_interaction":
                if not order_desc:
                    base_query = base_query.order_by(
                        last_interaction_expr.desc().nullslast()
                    )
                else:
                    base_query = base_query.order_by(
                        last_interaction_expr.asc().nullsfirst()
                    )
            else:  # created_at
                order_expr = (
                    models.Lead.created_at.desc()
                    if not order_desc
                    else models.Lead.created_at.asc()
                )
                base_query = base_query.order_by(order_expr)

            total = base_query.count()
            leads: List[models.Lead] = (
                base_query.offset((page - 1) * effective_page_size)
                .limit(effective_page_size)
                .all()
            )

        except (ProgrammingError, PsycopgError, Exception) as query_exc:
            sales_view_metrics["errors"] += 1
            sales_view_logger.error(
                action="sales_view_query_error",
                message="Failed to execute sales view query",
                route=sales_view_route_id,
                error=query_exc,
            )
            http_status = 500
            return JSONResponse(
                status_code=500,
                content={
                    "error": "sales_view_error",
                    "code": "sales_view_error",
                    "message": "Failed to build sales view",
                },
            )

        items: List[LeadSalesViewItem] = []
        for lead in leads:
            try:
                stats = lead.activity_stats
                # Handle potential null priority_score in DB gracefully
                db_score = (
                    lead.priority_score if lead.priority_score is not None else None
                )
                score = (
                    db_score
                    if db_score is not None
                    else calculate_lead_priority(lead, stats)
                )
                bucket = classify_priority_bucket(score)

                last_interaction = (
                    stats.last_interaction_at
                    if stats and stats.last_interaction_at
                    else lead.updated_at or lead.created_at
                )
                last_interaction = _normalize_datetime(last_interaction)

                # Robust tag extraction: filter out None values and ensure string conversion
                tags_list: List[TagItem] = []
                if lead.tags:
                    tags_list = [
                        TagItem(
                            id=str(tag.id),
                            name=str(tag.name),
                            color=tag.color,
                        )
                        for tag in lead.tags
                        if tag and tag.name is not None and tag.id is not None
                    ]

                # Robust next action
                next_action = suggest_next_action(lead, stats)

                # Create LeadOwner only if ID is present or handle as Optional
                lead_owner: Optional[LeadOwner] = None
                if getattr(lead, "owner", None):
                    lead_owner = LeadOwner(
                        id=str(lead.owner.id) if lead.owner.id is not None else None,
                        name=lead.owner.name,
                    )

                items.append(
                    LeadSalesViewItem(
                        id=str(lead.id),  # Ensure ID is string
                        legal_name=getattr(lead, "legal_name", None) or lead.title,
                        trade_name=lead.trade_name,
                        lead_status_id=(
                            str(lead.lead_status_id)
                            if lead.lead_status_id is not None
                            else None
                        ),
                        lead_origin_id=(
                            str(lead.lead_origin_id)
                            if lead.lead_origin_id is not None
                            else None
                        ),
                        owner_user_id=(
                            str(lead.owner_user_id)
                            if lead.owner_user_id is not None
                            else None
                        ),
                        owner=lead_owner,
                        priority_score=score,
                        priority_bucket=bucket,
                        priority_description=_priority_description_from_bucket(bucket),
                        last_interaction_at=last_interaction,
                        qualified_master_deal_id=(
                            str(lead.qualified_master_deal_id)
                            if lead.qualified_master_deal_id is not None
                            else None
                        ),
                        address_city=lead.address_city,
                        address_state=lead.address_state,
                        tags=tags_list,
                        primary_contact=None,
                        next_action=next_action,
                    )
                )
            except Exception as item_exc:
                # Log error for specific lead but SKIPPING instead of RAISING
                sales_view_logger.error(
                    action="sales_view_item_error",
                    message=f"Failed to process lead {lead.id}. Skipping.",
                    route=sales_view_route_id,
                    error=item_exc,
                    exc_info=True,
                )
                # Skip this bad item to ensure 200 OK for the list
                continue

        # Items are already ordered by the database query, no need to re-sort
        item_count = len(items)
        success = True
        return LeadSalesViewResponse(
            data=items,
            pagination=Pagination(
                total=total,
                per_page=effective_page_size,
                page=page,
            ),
        )
    except HTTPException as http_exc:
        http_status = http_exc.status_code
        raise
    except Exception as exc:  # pragma: no cover - defensive logging path
        sales_view_metrics["errors"] += 1
        sales_view_logger.error(
            action="sales_view",
            message="Failed to build sales view",
            route=sales_view_route_id,
            error=exc,
        )
        http_status = 500
        return JSONResponse(
            status_code=500,
            content={
                "error": "sales_view_error",
                "code": "sales_view_error",
                "message": "Failed to build sales view",
            },
        )
    finally:
        duration = time.perf_counter() - started
        sales_view_metrics["total_latency"] += duration
        avg_latency = (
            sales_view_metrics["total_latency"]
            / max(sales_view_metrics["calls"], 1)
        )

        try:
            sales_view_request_counter.labels(status_code=str(http_status)).inc()
            sales_view_latency_histogram.observe(duration)
            sales_view_items_histogram.observe(item_count)
        except Exception as metrics_exc:  # pragma: no cover - defensive
            sales_view_logger.warning(
                action="sales_view_metrics_error",
                message="Failed to emit Prometheus metrics",
                route=sales_view_route_id,
                error_type=type(metrics_exc).__name__,
                error=str(metrics_exc),
            )

        sales_view_logger.info(
            action="sales_view_metrics",
            status="success" if success else "error",
            message="Sales view request telemetry",
            route=sales_view_route_id,
            status_code=http_status,
            item_count=item_count,
            calls=sales_view_metrics["calls"],
            errors=sales_view_metrics["errors"],
            avg_latency_ms=round(avg_latency * 1000, 2),
            last_request_ms=round(duration * 1000, 2),
        )
