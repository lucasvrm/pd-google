import time
from datetime import datetime, timedelta, timezone
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse
from psycopg2 import Error as PsycopgError
from sqlalchemy import and_, case, exists, func, or_, select
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
from services.next_action_service import (
    COLD_LEAD_DAYS,
    DISQUALIFY_DAYS,
    HIGH_ENGAGEMENT_SCORE,
    MEDIUM_ENGAGEMENT_SCORE,
    POST_MEETING_WINDOW_DAYS,
    SCHEDULE_MEETING_ENGAGEMENT_THRESHOLD,
    STALE_INTERACTION_DAYS,
    suggest_next_action,
)
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

PRIORITY_HOT_THRESHOLD = 70
PRIORITY_WARM_THRESHOLD = 40


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
    search: Optional[str] = Query(None, description="Text search on lead names"),
    q: Optional[str] = Query(None, description="Text search on lead names (legacy alias)"),
    tags: Optional[str] = Query(None, description="Tag IDs filter (CSV)"),
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
    days_without_interaction: Optional[int] = Query(
        None,
        ge=1,
        description="Filter leads without interaction for at least N days",
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
    days_without_interaction = _extract_value(days_without_interaction)
    search = _extract_value(search)
    q = _extract_value(q)
    tags = _extract_value(tags)

    # Normalize search term: use search or fall back to q (legacy alias)
    search_term = search or q

    # Normalize tags filter (CSV of tag IDs)
    tags_filter = _normalize_filter_list(tags)

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

    valid_order_by = ["priority", "last_interaction", "created_at", "status", "owner", "next_action"]
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
        "days_without_interaction": days_without_interaction,
        "search_term": search_term,
        "tags_filter": tags_filter,
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
                .outerjoin(models.LeadStatus, models.LeadStatus.id == models.Lead.lead_status_id)
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

            # Apply text search filter (ILIKE on legal_name, trade_name)
            if search_term:
                search_pattern = f"%{search_term}%"
                base_query = base_query.filter(
                    or_(
                        models.Lead.title.ilike(search_pattern),  # title maps to legal_name column
                        models.Lead.trade_name.ilike(search_pattern),
                    )
                )

            # Apply tags filter via EXISTS subquery on entity_tags
            if tags_filter:
                # Use EXISTS subquery to filter leads that have any of the specified tags
                entity_tag_subquery = select(models.EntityTag.entity_id).where(
                    and_(
                        models.EntityTag.entity_type == "lead",
                        models.EntityTag.entity_id == models.Lead.id,
                        models.EntityTag.tag_id.in_(tags_filter),
                    )
                ).correlate(models.Lead)
                base_query = base_query.filter(exists(entity_tag_subquery))

            # Apply priority filter - support list (for priority_bucket)
            if priority_filter:
                bucket_conditions = []
                for bucket in priority_filter:
                    bucket_normalized = bucket.lower()
                    if bucket_normalized == "hot":
                        bucket_conditions.append(
                            models.Lead.priority_score >= PRIORITY_HOT_THRESHOLD
                        )
                    elif bucket_normalized == "warm":
                        bucket_conditions.append(
                            and_(
                                models.Lead.priority_score >= PRIORITY_WARM_THRESHOLD,
                                models.Lead.priority_score < PRIORITY_HOT_THRESHOLD,
                            )
                        )
                    elif bucket_normalized == "cold":
                        bucket_conditions.append(
                            or_(
                                models.Lead.priority_score < PRIORITY_WARM_THRESHOLD,
                                models.Lead.priority_score.is_(None),
                            )
                        )
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Invalid priority bucket: {bucket}",
                        )

                if bucket_conditions:
                    base_query = base_query.filter(or_(*bucket_conditions))

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

            if days_without_interaction is not None:
                threshold = datetime.now(timezone.utc) - timedelta(
                    days=days_without_interaction
                )
                base_query = base_query.filter(
                    (last_interaction_expr <= threshold)
                    | (last_interaction_expr.is_(None))
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
            elif order_field == "status":
                # Order by LeadStatus.sort_order (lower is more urgent)
                if not order_desc:
                    base_query = base_query.order_by(
                        models.LeadStatus.sort_order.asc().nullslast()
                    )
                else:
                    base_query = base_query.order_by(
                        models.LeadStatus.sort_order.desc().nullsfirst()
                    )
            elif order_field == "owner":
                # Order by User.name alphabetically
                if not order_desc:
                    base_query = base_query.order_by(
                        models.User.name.asc().nullslast()
                    )
                else:
                    base_query = base_query.order_by(
                        models.User.name.desc().nullsfirst()
                    )
            elif order_field == "next_action":
                # SQL CASE-based ranking to mimic suggest_next_action logic
                # Precedence (lower = more urgent):
                #  1: prepare_for_meeting     - Future event scheduled (last_event_at > now)
                #  2: post_meeting_follow_up  - Recent past meeting without subsequent interaction
                #  3: call_first_time         - No interaction at all
                #  4: handoff_to_deal         - Qualified company but no master deal
                #  5: qualify_to_company      - High engagement (>=70) without company
                #  6: schedule_meeting        - Medium+ engagement without upcoming meeting
                #  7: call_again              - (requires last_call_at field - not available in SQL)
                #  8: send_value_asset        - (requires last_value_asset_at field - not available in SQL)
                #  9: send_follow_up          - Stale interaction (>=5 days)
                # 10: reengage_cold_lead      - Very cold (>=30 days without interaction)
                # 11: disqualify              - Very long (>=60 days), low engagement, no company/deal
                # 12: send_follow_up          - Default (keep active)
                now = datetime.now(timezone.utc)
                stale_threshold = now - timedelta(days=STALE_INTERACTION_DAYS)
                cold_threshold = now - timedelta(days=COLD_LEAD_DAYS)
                disqualify_threshold = now - timedelta(days=DISQUALIFY_DAYS)
                post_meeting_threshold = now - timedelta(days=POST_MEETING_WINDOW_DAYS)
                next_action_rank = case(
                    # Priority 1: prepare_for_meeting (future event scheduled)
                    (
                        models.LeadActivityStats.last_event_at > now,
                        1,
                    ),
                    # Priority 2: post_meeting_follow_up (recent past meeting, no interaction after)
                    (
                        and_(
                            models.LeadActivityStats.last_event_at.isnot(None),
                            models.LeadActivityStats.last_event_at <= now,
                            models.LeadActivityStats.last_event_at >= post_meeting_threshold,
                            or_(
                                last_interaction_expr.is_(None),
                                last_interaction_expr <= models.LeadActivityStats.last_event_at,
                            ),
                        ),
                        2,
                    ),
                    # Priority 3: call_first_time (no interaction at all)
                    (
                        and_(
                            last_interaction_expr.is_(None),
                            or_(
                                models.LeadActivityStats.last_event_at.is_(None),
                                models.LeadActivityStats.last_event_at <= now,
                            ),
                        ),
                        3,
                    ),
                    # Priority 4: handoff_to_deal (qualified_company_id present, no master deal)
                    (
                        and_(
                            models.Lead.qualified_company_id.isnot(None),
                            models.Lead.qualified_master_deal_id.is_(None),
                            models.Lead.disqualified_at.is_(None),
                        ),
                        4,
                    ),
                    # Priority 5: qualify_to_company (high engagement >=70, no company)
                    (
                        and_(
                            models.LeadActivityStats.engagement_score >= HIGH_ENGAGEMENT_SCORE,
                            models.Lead.qualified_company_id.is_(None),
                            or_(
                                models.LeadActivityStats.last_event_at.is_(None),
                                models.LeadActivityStats.last_event_at <= now,
                            ),
                        ),
                        5,
                    ),
                    # Priority 6: schedule_meeting (medium+ engagement, no upcoming meeting)
                    (
                        and_(
                            models.LeadActivityStats.engagement_score >= SCHEDULE_MEETING_ENGAGEMENT_THRESHOLD,
                            or_(
                                models.LeadActivityStats.last_event_at.is_(None),
                                models.LeadActivityStats.last_event_at <= now,
                            ),
                        ),
                        6,
                    ),
                    # NOTE: Ranks 7-8 are skipped in SQL because they require optional fields
                    # (last_call_at for call_again, last_value_asset_at for send_value_asset)
                    # that may not exist in the database schema. The Python service handles
                    # these cases when the fields are available. Using consistent rank numbers
                    # (9, 10, 11) ensures the Python and SQL ordering align for leads that
                    # fall through to these categories.
                    #
                    # Priority 9: send_follow_up (stale interaction >=5 days but < 30 days)
                    (
                        and_(
                            last_interaction_expr.isnot(None),
                            last_interaction_expr <= stale_threshold,
                            last_interaction_expr > cold_threshold,
                            or_(
                                models.LeadActivityStats.last_event_at.is_(None),
                                models.LeadActivityStats.last_event_at <= now,
                            ),
                        ),
                        9,
                    ),
                    # Priority 10: reengage_cold_lead (>=30 days, <60 days)
                    (
                        and_(
                            last_interaction_expr.isnot(None),
                            last_interaction_expr <= cold_threshold,
                            last_interaction_expr > disqualify_threshold,
                            or_(
                                models.LeadActivityStats.last_event_at.is_(None),
                                models.LeadActivityStats.last_event_at <= now,
                            ),
                        ),
                        10,
                    ),
                    # Priority 11: disqualify (>=60 days, low engagement, no company/deal)
                    (
                        and_(
                            last_interaction_expr.isnot(None),
                            last_interaction_expr <= disqualify_threshold,
                            models.LeadActivityStats.engagement_score < MEDIUM_ENGAGEMENT_SCORE,
                            models.Lead.qualified_company_id.is_(None),
                            models.Lead.qualified_master_deal_id.is_(None),
                            models.Lead.disqualified_at.is_(None),
                        ),
                        11,
                    ),
                    # Default: send_follow_up (keep active)
                    else_=12,
                )
                if not order_desc:
                    # Ascending: most urgent first (rank 1, 2, 3...)
                    base_query = base_query.order_by(
                        next_action_rank.asc(),
                        last_interaction_expr.asc().nullsfirst(),
                    )
                else:
                    # Descending: least urgent first (rank 5, 4, 3...)
                    base_query = base_query.order_by(
                        next_action_rank.desc(),
                        last_interaction_expr.desc().nullslast(),
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

            # Pre-fetch tags from entity_tags for all leads (source of truth)
            lead_ids = [lead.id for lead in leads]
            entity_tags_lookup: dict = {}
            if lead_ids:
                entity_tags_rows = (
                    db.query(models.EntityTag, models.Tag)
                    .join(models.Tag, models.Tag.id == models.EntityTag.tag_id)
                    .filter(
                        models.EntityTag.entity_type == "lead",
                        models.EntityTag.entity_id.in_(lead_ids),
                    )
                    .all()
                )
                for entity_tag, tag in entity_tags_rows:
                    if entity_tag.entity_id not in entity_tags_lookup:
                        entity_tags_lookup[entity_tag.entity_id] = []
                    entity_tags_lookup[entity_tag.entity_id].append(tag)

            # Pre-fetch primary contacts from lead_contacts + contacts for all leads
            primary_contacts_lookup: dict = {}
            if lead_ids:
                try:
                    lead_contacts_rows = (
                        db.query(models.LeadContact, models.Contact)
                        .join(models.Contact, models.Contact.id == models.LeadContact.contact_id)
                        .filter(models.LeadContact.lead_id.in_(lead_ids))
                        .order_by(
                            models.LeadContact.is_primary.desc(),
                            models.LeadContact.added_at.asc(),
                        )
                        .all()
                    )
                    for lead_contact, contact in lead_contacts_rows:
                        # Only store the first contact per lead (is_primary=true takes precedence due to ordering)
                        if lead_contact.lead_id not in primary_contacts_lookup:
                            primary_contacts_lookup[lead_contact.lead_id] = contact
                except Exception as contact_exc:
                    # Log error but continue (primary_contact is optional)
                    sales_view_logger.warning(
                        action="sales_view_contacts_warning",
                        message="Failed to fetch lead contacts. Continuing without primary contacts.",
                        route=sales_view_route_id,
                        error_type=type(contact_exc).__name__,
                        error=str(contact_exc),
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
                    else getattr(lead, "last_interaction_at", None)
                    or lead.updated_at
                    or lead.created_at
                )
                last_interaction = _normalize_datetime(last_interaction)

                # Robust tag extraction: use entity_tags as source of truth
                # Fall back to lead.tags if entity_tags lookup returns empty
                tags_list: List[TagItem] = []
                entity_tags = entity_tags_lookup.get(lead.id, [])
                if entity_tags:
                    tags_list = [
                        TagItem(
                            id=str(tag.id),
                            name=str(tag.name),
                            color=tag.color,
                        )
                        for tag in entity_tags
                        if tag and tag.name is not None and tag.id is not None
                    ]
                elif lead.tags:
                    # Fallback to lead.tags if entity_tags is empty
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

                # Get primary contact from pre-fetched lookup
                primary_contact: Optional[PrimaryContact] = None
                contact = primary_contacts_lookup.get(lead.id)
                if contact:
                    primary_contact = PrimaryContact(
                        id=str(contact.id) if contact.id is not None else None,
                        name=contact.name,
                        role=contact.role,
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
                        primary_contact=primary_contact,
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
