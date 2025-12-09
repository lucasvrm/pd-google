"""
Health check endpoints for monitoring Calendar, Gmail and system status.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import SessionLocal
from datetime import datetime, timezone
import models
from services.google_gmail_service import GoogleGmailService, SCOPES as GMAIL_SCOPES
from utils.structured_logging import StructuredLogger
from config import config

router = APIRouter(tags=["health"])

# Create health-specific structured logger
health_logger = StructuredLogger(service="health", logger_name="pipedesk_drive.health")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/health/calendar")
def calendar_health_check(db: Session = Depends(get_db)):
    """
    Health check endpoint for Calendar service.
    
    Returns:
        - active_channels: Number of active, non-expired webhook channels
        - last_sync: Timestamp of last successful sync (if available)
        - event_count: Total number of active (non-cancelled) events in database
        - oldest_event: Date of oldest active event (if any)
        - newest_event: Date of newest active event (if any)
        - status: Overall health status (healthy/degraded/unhealthy)
    
    Status codes:
        - 200: Service is healthy
        - 200 with status='degraded': Service is operational but with issues
    """
    now = datetime.now(timezone.utc)
    
    # Count active, non-expired channels
    active_channels = db.query(models.CalendarSyncState).filter(
        models.CalendarSyncState.active == True,
        models.CalendarSyncState.expiration > now
    ).count()
    
    # Get last sync timestamp (most recent updated_at from sync states)
    last_sync_obj = db.query(models.CalendarSyncState).filter(
        models.CalendarSyncState.active == True
    ).order_by(
        models.CalendarSyncState.updated_at.desc()
    ).first()
    
    last_sync = None
    if last_sync_obj and last_sync_obj.updated_at:
        last_sync = last_sync_obj.updated_at.isoformat()
    
    # Count active events (non-cancelled)
    event_count = db.query(models.CalendarEvent).filter(
        models.CalendarEvent.status != 'cancelled'
    ).count()
    
    # Get oldest and newest active events
    oldest_event_obj = db.query(models.CalendarEvent).filter(
        models.CalendarEvent.status != 'cancelled'
    ).order_by(
        models.CalendarEvent.start_time.asc()
    ).first()
    
    newest_event_obj = db.query(models.CalendarEvent).filter(
        models.CalendarEvent.status != 'cancelled'
    ).order_by(
        models.CalendarEvent.start_time.desc()
    ).first()
    
    oldest_event = None
    newest_event = None
    
    if oldest_event_obj and oldest_event_obj.start_time:
        oldest_event = oldest_event_obj.start_time.isoformat()
    
    if newest_event_obj and newest_event_obj.start_time:
        newest_event = newest_event_obj.start_time.isoformat()
    
    # Determine health status
    status = "healthy"
    issues = []
    
    if active_channels == 0:
        status = "degraded"
        issues.append("No active webhook channels")
    
    if last_sync is None:
        status = "degraded"
        issues.append("No sync activity recorded")
    
    # Build response
    response = {
        "service": "calendar",
        "status": status,
        "timestamp": now.isoformat(),
        "active_channels": active_channels,
        "last_sync": last_sync,
        "event_count": event_count,
        "oldest_event": oldest_event,
        "newest_event": newest_event
    }
    
    if issues:
        response["issues"] = issues
    
    return response


@router.get("/health/gmail")
def gmail_health_check():
    """
    Health check endpoint for Gmail service.
    
    Returns:
        - auth_ok: Whether Gmail credentials and scopes are configured correctly
        - api_reachable: Whether Gmail API is accessible
        - last_check_timestamp: Timestamp of this health check
        - status: Overall health status (healthy/degraded/unhealthy)
    
    Status codes:
        - 200: Service is healthy or degraded
    """
    now = datetime.now(timezone.utc)
    status = "healthy"
    issues = []
    auth_ok = False
    api_reachable = False
    
    # Check credentials and scopes configuration
    try:
        # Check if credentials are configured
        if not config.GOOGLE_SERVICE_ACCOUNT_JSON:
            status = "unhealthy"
            issues.append("Gmail credentials not configured (GOOGLE_SERVICE_ACCOUNT_JSON missing)")
            health_logger.warning(
                action="gmail_health_check",
                status="unhealthy",
                message="Gmail credentials not configured"
            )
        else:
            # Try to initialize Gmail service
            gmail_service = GoogleGmailService()
            
            # Check if service initialized successfully
            if not gmail_service.service:
                status = "unhealthy"
                issues.append("Failed to initialize Gmail service")
                auth_ok = False
                health_logger.error(
                    action="gmail_health_check",
                    message="Failed to initialize Gmail service"
                )
            else:
                auth_ok = True
                
                # Perform lightweight API call to check reachability
                try:
                    # List labels is a lightweight call that verifies API access
                    result = gmail_service.list_labels()
                    
                    if result and 'labels' in result:
                        api_reachable = True
                        health_logger.info(
                            action="gmail_health_check",
                            status="success",
                            message=f"Gmail API is reachable, found {len(result.get('labels', []))} labels"
                        )
                    else:
                        status = "degraded"
                        issues.append("Gmail API returned unexpected response")
                        health_logger.warning(
                            action="gmail_health_check",
                            status="degraded",
                            message="Gmail API returned unexpected response"
                        )
                except Exception as api_error:
                    status = "degraded"
                    api_reachable = False
                    issues.append(f"Gmail API not reachable: {str(api_error)}")
                    health_logger.error(
                        action="gmail_health_check",
                        message="Gmail API call failed",
                        error=api_error
                    )
                    
    except Exception as e:
        status = "unhealthy"
        issues.append(f"Gmail health check failed: {str(e)}")
        health_logger.error(
            action="gmail_health_check",
            message="Gmail health check failed",
            error=e
        )
    
    # Build response
    response = {
        "service": "gmail",
        "status": status,
        "timestamp": now.isoformat(),
        "auth_ok": auth_ok,
        "api_reachable": api_reachable,
        "configured_scopes": GMAIL_SCOPES
    }
    
    if issues:
        response["issues"] = issues
    
    return response


@router.get("/health")
def general_health_check(db: Session = Depends(get_db)):
    """
    General health check endpoint aggregating all services.
    
    Returns:
        - overall_status: Overall system health (healthy/degraded/unhealthy)
        - services: Status of individual services (calendar, gmail)
        - timestamp: Timestamp of this health check
    
    Status determination:
        - healthy: All services are healthy
        - degraded: At least one service is degraded, none unhealthy
        - unhealthy: At least one service is unhealthy
    """
    now = datetime.now(timezone.utc)
    
    # Get Calendar health
    calendar_health = calendar_health_check(db)
    
    # Get Gmail health
    gmail_health = gmail_health_check()
    
    # Determine overall status
    statuses = [calendar_health["status"], gmail_health["status"]]
    
    if "unhealthy" in statuses:
        overall_status = "unhealthy"
    elif "degraded" in statuses:
        overall_status = "degraded"
    else:
        overall_status = "healthy"
    
    health_logger.info(
        action="general_health_check",
        status=overall_status,
        message=f"Overall health: {overall_status}",
        calendar_status=calendar_health["status"],
        gmail_status=gmail_health["status"]
    )
    
    response = {
        "overall_status": overall_status,
        "timestamp": now.isoformat(),
        "services": {
            "calendar": {
                "status": calendar_health["status"],
                "active_channels": calendar_health.get("active_channels"),
                "last_sync": calendar_health.get("last_sync")
            },
            "gmail": {
                "status": gmail_health["status"],
                "auth_ok": gmail_health.get("auth_ok"),
                "api_reachable": gmail_health.get("api_reachable")
            }
        }
    }
    
    return response
