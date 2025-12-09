"""
Health check endpoints for monitoring Calendar, Gmail and system status.
"""

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from database import SessionLocal
from services.health_service import HealthService

router = APIRouter(tags=["health"])


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@router.get("/health/calendar")
def calendar_health_check(db: Session = Depends(get_db)):
    """Health check endpoint for Calendar service with Google API connectivity."""
    service = HealthService(db)
    return service.calendar_health()


@router.get("/health/gmail")
def gmail_health_check(db: Session = Depends(get_db)):
    """Health check endpoint for Gmail service with Google API connectivity."""
    service = HealthService(db)
    return service.gmail_health()


@router.get("/health")
def general_health_check(db: Session = Depends(get_db)):
    """General health check aggregating all services."""
    service = HealthService(db)
    return service.general_health()
