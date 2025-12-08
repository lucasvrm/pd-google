"""
Health check endpoints for monitoring Calendar and system status.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from sqlalchemy import func
from database import SessionLocal
from datetime import datetime, timezone
import models

router = APIRouter(tags=["health"])


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
