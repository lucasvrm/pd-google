import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, List, Literal, Optional

from fastapi import APIRouter, Depends, Query, HTTPException
from fastapi.responses import JSONResponse
from psycopg2 import Error as PsycopgError
from sqlalchemy import and_, case, exists, func, or_, select, text
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
from schemas.lead_tasks import (
    LeadTaskCreate,
    LeadTaskCreateFromTemplate,
    LeadTaskListResponse,
    LeadTaskResponse,
    LeadTaskUpdate,
    UpdateLeadPriorityRequest,
    UpdateLeadPriorityResponse,
)
from services.lead_priority_service import (
    calculate_lead_priority,
    classify_priority_bucket,
)
from services.lead_priority_config_service import get_lead_priority_config
from services.next_action_service import (
    CALL_AGAIN_WINDOW_DAYS,
    COLD_LEAD_DAYS,
    DISQUALIFY_DAYS,
    HIGH_ENGAGEMENT_SCORE,
    MEDIUM_ENGAGEMENT_SCORE,
    POST_MEETING_WINDOW_DAYS,
    SCHEDULE_MEETING_ENGAGEMENT_THRESHOLD,
    STALE_INTERACTION_DAYS,
    VALUE_ASSET_STALE_DAYS,
    suggest_next_action,
)
from services.feature_flags_service import (
    is_auto_next_action_enabled,
    is_auto_priority_enabled,
    is_task_next_action_enabled,
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


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _ensure_str(value: Any) -> Optional[str]:
    """
    Garante que value é string, convertendo UUID se necessário.
    
    Args:
        value: Pode ser UUID, str, ou None
    
    Returns:
        String convertida ou None
    """
    if value is None:
        return None
    return str(value)


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


def _normalize_unique_lower_filter_list(value: Optional[str]) -> List[str]:
    items = _normalize_filter_list(value)
    if not items:
        return []
    seen_actions = set()
    normalized_items: List[str] = []
    for item in items:
        item_lower = item.lower()
        if item_lower and item_lower not in seen_actions:
            seen_actions.add(item_lower)
            normalized_items.append(item_lower)
    return normalized_items


def _priority_description_from_bucket(bucket: str) -> Optional[str]:
    descriptions = {
        "hot": "Alta prioridade",
        "warm": "Prioridade média",
        "cold": "Baixa prioridade",
    }
    return descriptions.get(bucket)


def _get_next_action_from_tasks(db: Session, lead_id: str) -> Optional[dict]:
    """
    Busca a próxima ação de um lead da tabela lead_tasks.
    
    Returns:
        Dict com code, label, reason, task_id ou None
    """
    try:
        result = db.execute(
            text("""
                SELECT 
                    lt.id,
                    lt.title,
                    lt.description,
                    lt.due_date,
                    ltt.code as template_code
                FROM lead_tasks lt
                LEFT JOIN lead_task_templates ltt ON ltt.id = lt.template_id
                WHERE lt.lead_id = :lead_id
                  AND lt.is_next_action = true
                  AND lt.status NOT IN ('completed', 'cancelled')
                ORDER BY lt.sort_order
                LIMIT 1
            """),
            {"lead_id": lead_id}
        )
        row = result.fetchone()
        
        if row is None:
            return None
        
        task_id, title, description, due_date, template_code = row
        
        return {
            "code": template_code or "custom_task",
            "label": title,
            "reason": description or "",
            "dueAt": due_date.isoformat() if due_date else None,
            "taskId": str(task_id),
        }
    except Exception as exc:
        sales_view_logger.warning(
            action="get_next_action_from_tasks",
            message=f"Erro ao buscar next action de lead_tasks para lead {lead_id}",
            error=str(exc),
        )
        return None


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
    next_action: Optional[str] = Query(
        None,
        alias="next_action",
        description="Next action filter (CSV of next_action codes)",
    ),
    include_qualified: Optional[bool] = Query(
        None,
        alias="includeQualified",
        description="Include qualified/soft-deleted leads (default: false)",
    ),
    include_qualified_override: Optional[bool] = Query(
        None,
        alias="include_qualified",
        description="Alias for includeQualified (snake_case)",
    ),
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
    next_action = _extract_value(next_action)
    include_qualified = _extract_value(include_qualified)
    include_qualified_override = _extract_value(include_qualified_override)

    # Normalize search term: use search or fall back to q (legacy alias)
    search_term = search or q

    # Normalize includeQualified - accept camelCase or snake_case, default to False
    # Prefer the first non-None value; if both are None, default to False
    if include_qualified is not None:
        effective_include_qualified = bool(include_qualified)
    elif include_qualified_override is not None:
        effective_include_qualified = bool(include_qualified_override)
    else:
        effective_include_qualified = False

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
    next_action_filter = _normalize_unique_lower_filter_list(next_action)

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
        "next_action_filter": next_action_filter,
    }
    sales_view_logger.info(
        action="sales_view_request",
        message="Sales view request parameters",
        route=sales_view_route_id,
        params=request_params,
    )

    # ========== NOVO: Ler feature flags uma vez ==========
    auto_priority_enabled = is_auto_priority_enabled(db)
    auto_next_action_enabled = is_auto_next_action_enabled(db)
    task_next_action_enabled = is_task_next_action_enabled(db)
    # ========== FIM NOVO ==========

    # ========== NOVO: Carregar config de prioridade ==========
    priority_config = get_lead_priority_config(db)
    thresholds = priority_config.get("thresholds", {"hot": 70, "warm": 40})
    hot_threshold = thresholds.get("hot", 70)
    warm_threshold = thresholds.get("warm", 40)
    # ========== FIM NOVO ==========

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
            # Exclude soft deleted and qualified leads by default
            # When includeQualified=true, show all leads including qualified/deleted ones
            if not effective_include_qualified:
                base_query = base_query.filter(
                    models.Lead.deleted_at.is_(None),
                    models.Lead.qualified_at.is_(None),
                    or_(
                        models.Lead.lead_status_id.is_(None),
                        models.LeadStatus.code != "qualified",
                    ),
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
                hot_threshold = priority_config.get("thresholds", {}).get("hot", 70)
                warm_threshold = priority_config.get("thresholds", {}).get("warm", 40)
                
                bucket_conditions = []
                for bucket in priority_filter:
                    bucket_normalized = bucket.lower()
                    if bucket_normalized == "hot":
                        bucket_conditions.append(
                            models.Lead.priority_score >= hot_threshold
                        )
                    elif bucket_normalized == "warm":
                        bucket_conditions.append(
                            and_(
                                models.Lead.priority_score >= warm_threshold,
                                models.Lead.priority_score < hot_threshold,
                            )
                        )
                    elif bucket_normalized == "cold":
                        bucket_conditions.append(
                            or_(
                                models.Lead.priority_score < warm_threshold,
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

            next_action_rank = None
            next_action_code = None
            if next_action_filter or order_field == "next_action":
                now = datetime.now(timezone.utc)
                stale_threshold = now - timedelta(days=STALE_INTERACTION_DAYS)
                cold_threshold = now - timedelta(days=COLD_LEAD_DAYS)
                disqualify_threshold = now - timedelta(days=DISQUALIFY_DAYS)
                post_meeting_threshold = now - timedelta(days=POST_MEETING_WINDOW_DAYS)
                call_again_threshold = now - timedelta(days=CALL_AGAIN_WINDOW_DAYS)
                value_asset_stale_threshold = now - timedelta(days=VALUE_ASSET_STALE_DAYS)
                next_action_conditions = [
                    (
                        models.LeadActivityStats.last_event_at > now,
                        ("prepare_for_meeting", 1),
                    ),
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
                        ("post_meeting_follow_up", 2),
                    ),
                    (
                        and_(
                            last_interaction_expr.is_(None),
                            or_(
                                models.LeadActivityStats.last_event_at.is_(None),
                                models.LeadActivityStats.last_event_at <= now,
                            ),
                        ),
                        ("call_first_time", 3),
                    ),
                    (
                        and_(
                            models.Lead.qualified_company_id.isnot(None),
                            models.Lead.qualified_master_deal_id.is_(None),
                            models.Lead.disqualified_at.is_(None),
                        ),
                        ("handoff_to_deal", 4),
                    ),
                    (
                        and_(
                            models.LeadActivityStats.engagement_score >= HIGH_ENGAGEMENT_SCORE,
                            models.Lead.qualified_company_id.is_(None),
                            or_(
                                models.LeadActivityStats.last_event_at.is_(None),
                                models.LeadActivityStats.last_event_at <= now,
                            ),
                        ),
                        ("qualify_to_company", 5),
                    ),
                    (
                        and_(
                            models.LeadActivityStats.engagement_score >= SCHEDULE_MEETING_ENGAGEMENT_THRESHOLD,
                            or_(
                                models.LeadActivityStats.last_event_at.is_(None),
                                models.LeadActivityStats.last_event_at <= now,
                            ),
                        ),
                        ("schedule_meeting", 6),
                    ),
                    (
                        and_(
                            models.LeadActivityStats.last_call_at.isnot(None),
                            models.LeadActivityStats.last_call_at >= call_again_threshold,
                        ),
                        ("call_again", 7),
                    ),
                    (
                        and_(
                            models.LeadActivityStats.engagement_score >= MEDIUM_ENGAGEMENT_SCORE,
                            or_(
                                models.LeadActivityStats.last_value_asset_at.is_(None),
                                models.LeadActivityStats.last_value_asset_at <= value_asset_stale_threshold,
                            ),
                        ),
                        ("send_value_asset", 8),
                    ),
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
                        ("send_follow_up", 9),
                    ),
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
                        ("reengage_cold_lead", 10),
                    ),
                    (
                        and_(
                            last_interaction_expr.isnot(None),
                            last_interaction_expr <= disqualify_threshold,
                            models.LeadActivityStats.engagement_score < MEDIUM_ENGAGEMENT_SCORE,
                            models.Lead.qualified_company_id.is_(None),
                            models.Lead.qualified_master_deal_id.is_(None),
                            models.Lead.disqualified_at.is_(None),
                        ),
                        ("disqualify", 11),
                    ),
                ]
                next_action_rank = case(
                    *[(condition, rank) for condition, (_, rank) in next_action_conditions],
                    else_=12,
                )
                if next_action_filter:
                    next_action_code = case(
                        *[(condition, code) for condition, (code, _) in next_action_conditions],
                        else_="send_follow_up",
                    )

            if next_action_filter:
                base_query = base_query.filter(next_action_code.in_(next_action_filter))

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
                # Add tie-breaker by created_at for deterministic ordering
                if not order_desc:
                    base_query = base_query.order_by(
                        models.LeadStatus.sort_order.asc().nullslast(),
                        models.Lead.created_at.desc(),
                    )
                else:
                    base_query = base_query.order_by(
                        models.LeadStatus.sort_order.desc().nullsfirst(),
                        models.Lead.created_at.asc(),
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
                
                # ========== MODIFICADO: Respeitar feature flag de prioridade ==========
                db_score = lead.priority_score if lead.priority_score is not None else None
                
                if auto_priority_enabled:
                    # Sistema antigo: calcular se não existe no banco
                    score = db_score if db_score is not None else calculate_lead_priority(lead, config=priority_config)
                else:
                    # Sistema novo: usar apenas valor do banco (prioridade manual)
                    # Se não existe, default para 0 (cold)
                    score = db_score if db_score is not None else 0
                
                bucket = classify_priority_bucket(score, config=priority_config)
                # ========== FIM MODIFICADO ==========

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

                # ========== MODIFICADO: Respeitar feature flag de next_action ==========
                next_action_data = None
                
                if auto_next_action_enabled:
                    # Sistema antigo: calcular next action automaticamente
                    next_action_data = suggest_next_action(lead, stats)
                elif task_next_action_enabled:
                    # Sistema novo: buscar de lead_tasks
                    next_action_data = _get_next_action_from_tasks(db, lead.id)
                
                # Fallback: se nenhum sistema está habilitado ou não retornou ação, usar padrão
                if next_action_data is None:
                    next_action_data = {
                        "code": "send_follow_up",
                        "label": "Enviar follow-up",
                        "reason": "Manter relacionamento ativo",
                    }
                # ========== FIM MODIFICADO ==========

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
                        next_action=next_action_data,
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


# ===== Lead Qualification Endpoint =====

from schemas.leads import (
    QualifyLeadRequest,
    QualifyLeadResponse,
    MigratedFields,
)
from services.audit_service import set_audit_actor, clear_audit_actor

qualify_lead_logger = StructuredLogger(
    service="lead_qualification", logger_name="pipedesk_drive.lead_qualification"
)


@router.post("/{lead_id}/qualify", response_model=QualifyLeadResponse)
def qualify_lead(
    lead_id: str,
    request: QualifyLeadRequest,
    current_user: Optional[UserContext] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """
    Qualify a lead by linking it to a Deal and soft deleting it.
    
    This endpoint:
    1. Sets qualified_at and deleted_at timestamps on the lead
    2. Links the lead to the specified deal via qualified_master_deal_id
    3. Migrates critical fields (legal_name, trade_name, owner_user_id, description) to the deal
    4. Creates an audit log entry with action="qualify_and_soft_delete"
    
    After qualification, the lead will no longer appear in sales view, kanban, or grid views.
    """
    now = datetime.now(timezone.utc)
    
    try:
        # Set audit actor for tracking
        actor_id = current_user.id if current_user else None
        set_audit_actor(actor_id)
        
        # Fetch the lead
        lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail=f"Lead {lead_id} not found")
        
        # Check if lead is already qualified/deleted
        if lead.deleted_at is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Lead {lead_id} is already qualified or deleted"
            )
        
        # Check if lead is disqualified
        if lead.disqualified_at is not None:
            raise HTTPException(
                status_code=400,
                detail=f"Lead {lead_id} is disqualified and cannot be qualified"
            )
        
        # Fetch the deal
        deal = db.query(models.Deal).filter(models.Deal.id == request.deal_id).first()
        if not deal:
            raise HTTPException(status_code=404, detail=f"Deal {request.deal_id} not found")
        
        # Collect tag IDs before qualification
        tag_ids = [tag.id for tag in lead.tags] if lead.tags else []
        
        # Migrate fields from Lead to Deal
        # Only update deal fields if they are not already set (preserve existing data)
        if not deal.legal_name:
            deal.legal_name = lead.legal_name
        if not deal.trade_name:
            deal.trade_name = lead.trade_name
        if not deal.owner_user_id:
            deal.owner_user_id = lead.owner_user_id
        if not deal.description:
            deal.description = lead.description
        
        # Update lead with qualification data
        lead.qualified_at = now
        lead.deleted_at = now
        lead.qualified_master_deal_id = request.deal_id
        
        # Commit changes
        db.commit()
        
        # Build response
        migrated_fields = MigratedFields(
            legal_name=lead.legal_name,
            trade_name=lead.trade_name,
            owner_user_id=lead.owner_user_id,
            description=lead.description,
            tags=tag_ids,
        )
        
        qualify_lead_logger.info(
            action="lead_qualified",
            message=f"Lead {lead_id} qualified and linked to deal {request.deal_id}",
            lead_id=_ensure_str(lead_id),
            deal_id=_ensure_str(request.deal_id),
            actor_id=_ensure_str(actor_id),
            migrated_fields=migrated_fields.model_dump(),
        )
        
        return QualifyLeadResponse(
            status="qualified",
            lead_id=lead_id,
            deal_id=request.deal_id,
            qualified_at=now,
            deleted_at=now,
            migrated_fields=migrated_fields,
        )
        
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        qualify_lead_logger.error(
            action="lead_qualification_error",
            message=f"Failed to qualify lead {lead_id}",
            lead_id=_ensure_str(lead_id),
            deal_id=_ensure_str(request.deal_id),
            error=str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to qualify lead: {str(exc)}"
        )
    finally:
        clear_audit_actor()


# ============================================================================
# LEAD PRIORITY ENDPOINT
# ============================================================================

PRIORITY_BUCKET_TO_SCORE = {
    "hot": 85,    # >= 70 = hot
    "warm": 55,   # 40-69 = warm
    "cold": 20,   # < 40 = cold
}


@router.patch("/{lead_id}/priority", response_model=UpdateLeadPriorityResponse)
def update_lead_priority(
    lead_id: str,
    data: UpdateLeadPriorityRequest,
    current_user: Optional[UserContext] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Atualiza prioridade do lead manualmente."""
    from services.feature_flags_service import is_manual_priority_enabled
    
    if not is_manual_priority_enabled(db):
        raise HTTPException(
            status_code=403,
            detail="Prioridade manual desabilitada. Habilite feature_lead_manual_priority."
        )
    
    lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} não encontrado")
    
    score = PRIORITY_BUCKET_TO_SCORE.get(data.priority_bucket, 20)
    lead.priority_score = score
    
    db.commit()
    db.refresh(lead)
    
    sales_view_logger.info(
        action="update_lead_priority",
        message=f"Prioridade atualizada: {lead_id} → {data.priority_bucket}",
        lead_id=_ensure_str(lead_id),
        priority_bucket=data.priority_bucket,
        priority_score=score,
        actor_id=_ensure_str(current_user.id if current_user else None),
    )
    
    return UpdateLeadPriorityResponse(
        lead_id=lead_id,
        priority_bucket=data.priority_bucket,
        priority_score=score,
        updated_at=lead.updated_at or datetime.now(timezone.utc),
    )


# ============================================================================
# LEAD TASKS ENDPOINTS
# ============================================================================

def _map_lead_task(task: models.LeadTask) -> LeadTaskResponse:
    """Mapeia model para response."""
    template = None
    template_code = None
    
    if task.template_id:
        # Try to access the template relationship, it should be loaded via joinedload or refresh
        try:
            if hasattr(task, 'template') and task.template:
                template_code = task.template.code
        except Exception:
            # If template relationship is not loaded, template_code will remain None
            pass
    
    return LeadTaskResponse(
        id=str(task.id),
        lead_id=str(task.lead_id),
        template_id=str(task.template_id) if task.template_id else None,
        template_code=template_code,
        title=task.title,
        description=task.description,
        is_next_action=task.is_next_action,
        status=task.status,
        due_date=task.due_date,
        sort_order=task.sort_order,
        completed_at=task.completed_at,
        completed_by=str(task.completed_by) if task.completed_by else None,
        created_at=task.created_at,
        created_by=str(task.created_by) if task.created_by else None,
    )


@router.get("/{lead_id}/tasks", response_model=LeadTaskListResponse)
def list_lead_tasks(
    lead_id: str,
    include_completed: bool = Query(False),
    current_user: Optional[UserContext] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Lista tarefas de um lead."""
    lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} não encontrado")
    
    query = db.query(models.LeadTask).options(
        joinedload(models.LeadTask.template)
    ).filter(models.LeadTask.lead_id == lead_id)
    
    if not include_completed:
        query = query.filter(models.LeadTask.status.notin_(["completed", "cancelled"]))
    
    tasks = query.order_by(
        models.LeadTask.is_next_action.desc(),
        models.LeadTask.sort_order,
    ).all()
    
    next_action = next(
        (t for t in tasks if t.is_next_action and t.status not in ["completed", "cancelled"]),
        None
    )
    
    return LeadTaskListResponse(
        data=[_map_lead_task(t) for t in tasks],
        total=len(tasks),
        next_action=_map_lead_task(next_action) if next_action else None,
    )


@router.post("/{lead_id}/tasks", response_model=LeadTaskResponse, status_code=201)
def create_lead_task(
    lead_id: str,
    data: LeadTaskCreate,
    current_user: Optional[UserContext] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Cria tarefa customizada para um lead."""
    try:
        # Validate lead exists
        lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail=f"Lead {lead_id} não encontrado")
        
        # If template_id is provided, validate it exists
        if data.template_id:
            template = db.query(models.LeadTaskTemplate).filter(
                models.LeadTaskTemplate.id == data.template_id
            ).first()
            if not template:
                raise HTTPException(
                    status_code=404,
                    detail=f"Template {data.template_id} não encontrado"
                )
        
        # Get max sort order
        max_order = db.query(func.max(models.LeadTask.sort_order)).filter(
            models.LeadTask.lead_id == lead_id
        ).scalar() or 0
        
        # Create task
        task = models.LeadTask(
            id=str(uuid.uuid4()),
            lead_id=lead_id,
            template_id=data.template_id,
            title=data.title,
            description=data.description,
            is_next_action=data.is_next_action,
            status=data.status,
            due_date=data.due_date,
            sort_order=max_order + 1,
            created_by=current_user.id if current_user else None,
        )
        
        db.add(task)
        db.commit()
        db.refresh(task)
        
        sales_view_logger.info(
            action="create_lead_task",
            message=f"Tarefa customizada criada para lead {lead_id}",
            lead_id=_ensure_str(lead_id),
            task_id=_ensure_str(task.id),
            is_next_action=data.is_next_action,
            actor_id=_ensure_str(current_user.id if current_user else None),
        )
        
        return _map_lead_task(task)
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ProgrammingError as pg_exc:
        # Handle database programming errors (e.g., constraint violations)
        db.rollback()
        sales_view_logger.error(
            action="create_lead_task_db_error",
            message=f"Erro de banco ao criar tarefa para lead {lead_id}",
            lead_id=_ensure_str(lead_id),
            error=str(pg_exc),
        )
        raise HTTPException(
            status_code=400,
            detail="Erro ao criar tarefa. Verifique se os dados estão corretos."
        )
    except Exception as exc:
        # Handle unexpected errors
        db.rollback()
        sales_view_logger.error(
            action="create_lead_task_error",
            message=f"Erro inesperado ao criar tarefa para lead {lead_id}",
            lead_id=_ensure_str(lead_id),
            error=str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao criar tarefa: {str(exc)}"
        )


@router.post("/{lead_id}/tasks/from-template", response_model=LeadTaskResponse, status_code=201)
def create_task_from_template(
    lead_id: str,
    data: LeadTaskCreateFromTemplate,
    current_user: Optional[UserContext] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Cria tarefa a partir de um template (drag-and-drop)."""
    try:
        # Validate lead exists
        lead = db.query(models.Lead).filter(models.Lead.id == lead_id).first()
        if not lead:
            raise HTTPException(status_code=404, detail=f"Lead {lead_id} não encontrado")
        
        # Validate template exists
        template = db.query(models.LeadTaskTemplate).filter(
            models.LeadTaskTemplate.id == data.template_id
        ).first()
        if not template:
            raise HTTPException(status_code=404, detail=f"Template {data.template_id} não encontrado")
        
        # Check if template is active
        if not template.is_active:
            raise HTTPException(
                status_code=400,
                detail=f"Template {data.template_id} está inativo e não pode ser usado"
            )
        
        # Get max sort order
        max_order = db.query(func.max(models.LeadTask.sort_order)).filter(
            models.LeadTask.lead_id == lead_id
        ).scalar() or 0
        
        # Create task
        # Note: created_by is set automatically by Supabase trigger (set_created_by_on_lead_tasks)
        task = models.LeadTask(
            id=str(uuid.uuid4()),
            lead_id=lead_id,
            template_id=template.id,
            title=template.label,
            description=template.description,
            is_next_action=data.is_next_action,
            status="pending",
            due_date=data.due_date,
            sort_order=max_order + 1,
        )
        
        db.add(task)
        db.commit()
        db.refresh(task)
        
        # Reload template relationship for response
        db.refresh(task)
        if task.template_id:
            task.template = template
        
        sales_view_logger.info(
            action="create_task_from_template",
            message=f"Tarefa criada a partir de template: {template.code}",
            lead_id=_ensure_str(lead_id),
            task_id=_ensure_str(task.id),
            template_id=_ensure_str(template.id),
            is_next_action=data.is_next_action,
            actor_id=_ensure_str(current_user.id if current_user else None),
        )
        
        return _map_lead_task(task)
        
    except HTTPException:
        # Re-raise HTTP exceptions as-is
        raise
    except ProgrammingError as pg_exc:
        # Handle database programming errors (e.g., constraint violations)
        db.rollback()
        sales_view_logger.error(
            action="create_task_from_template_db_error",
            message=f"Erro de banco ao criar tarefa para lead {lead_id}",
            lead_id=_ensure_str(lead_id),
            template_id=_ensure_str(data.template_id),
            error=str(pg_exc),
        )
        raise HTTPException(
            status_code=400,
            detail="Erro ao criar tarefa. Verifique se os dados estão corretos."
        )
    except Exception as exc:
        # Handle unexpected errors
        db.rollback()
        sales_view_logger.error(
            action="create_task_from_template_error",
            message=f"Erro inesperado ao criar tarefa para lead {lead_id}",
            lead_id=_ensure_str(lead_id),
            template_id=_ensure_str(data.template_id),
            error=str(exc),
            exc_info=True,
        )
        raise HTTPException(
            status_code=500,
            detail=f"Erro ao criar tarefa: {str(exc)}"
        )


@router.patch("/{lead_id}/tasks/{task_id}", response_model=LeadTaskResponse)
def update_lead_task(
    lead_id: str,
    task_id: str,
    data: LeadTaskUpdate,
    current_user: Optional[UserContext] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Atualiza uma tarefa."""
    task = db.query(models.LeadTask).options(
        joinedload(models.LeadTask.template)
    ).filter(
        models.LeadTask.id == task_id,
        models.LeadTask.lead_id == lead_id,
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Tarefa {task_id} não encontrada")
    
    update_data = data.model_dump(exclude_unset=True)
    
    # Auto-preencher completed_at/completed_by
    if update_data.get("status") == "completed" and task.status != "completed":
        update_data["completed_at"] = datetime.now(timezone.utc)
        update_data["completed_by"] = current_user.id if current_user else None
    
    for key, value in update_data.items():
        setattr(task, key, value)
    
    db.commit()
    db.refresh(task)
    
    return _map_lead_task(task)


@router.delete("/{lead_id}/tasks/{task_id}", status_code=204)
def delete_lead_task(
    lead_id: str,
    task_id: str,
    current_user: Optional[UserContext] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Remove uma tarefa."""
    task = db.query(models.LeadTask).filter(
        models.LeadTask.id == task_id,
        models.LeadTask.lead_id == lead_id,
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Tarefa {task_id} não encontrada")
    
    db.delete(task)
    db.commit()


@router.post("/{lead_id}/tasks/{task_id}/complete", response_model=LeadTaskResponse)
def complete_lead_task(
    lead_id: str,
    task_id: str,
    current_user: Optional[UserContext] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Marca tarefa como completa."""
    task = db.query(models.LeadTask).options(
        joinedload(models.LeadTask.template)
    ).filter(
        models.LeadTask.id == task_id,
        models.LeadTask.lead_id == lead_id,
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Tarefa {task_id} não encontrada")
    
    task.status = "completed"
    task.completed_at = datetime.now(timezone.utc)
    task.completed_by = current_user.id if current_user else None
    
    db.commit()
    db.refresh(task)
    
    return _map_lead_task(task)


@router.patch("/{lead_id}/tasks/{task_id}/set-next-action", response_model=LeadTaskResponse)
def set_task_as_next_action(
    lead_id: str,
    task_id: str,
    current_user: Optional[UserContext] = Depends(get_current_user_optional),
    db: Session = Depends(get_db),
):
    """Define tarefa como próxima ação do lead."""
    task = db.query(models.LeadTask).options(
        joinedload(models.LeadTask.template)
    ).filter(
        models.LeadTask.id == task_id,
        models.LeadTask.lead_id == lead_id,
    ).first()
    
    if not task:
        raise HTTPException(status_code=404, detail=f"Tarefa {task_id} não encontrada")
    
    if task.status in ["completed", "cancelled"]:
        raise HTTPException(status_code=400, detail="Não é possível definir tarefa finalizada como próxima ação")
    
    # O trigger do banco vai desmarcar outras next_actions
    task.is_next_action = True
    db.commit()
    db.refresh(task)
    
    return _map_lead_task(task)

