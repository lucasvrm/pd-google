import os
import sys
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import models
from database import Base
from services.health_service import HealthService

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_health_service.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="module", autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    if os.path.exists("./test_health_service.db"):
        os.remove("./test_health_service.db")


@pytest.fixture
def db_session():
    db = TestingSessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_calendar_health_includes_queue_metrics(monkeypatch, db_session):
    now = datetime(2024, 1, 1, tzinfo=timezone.utc)

    channel = models.CalendarSyncState(
        channel_id="health-channel",
        resource_id="resource",
        calendar_id="primary",
        expiration=now + timedelta(hours=1),
        active=True,
        updated_at=now,
    )
    db_session.add(channel)

    event = models.CalendarEvent(
        google_event_id="event-1",
        summary="Test",
        start_time=now,
        end_time=now + timedelta(hours=1),
        status="confirmed",
    )
    db_session.add(event)

    db_session.add(models.DriveChangeLog(channel_id="c1", resource_id="r1", resource_state="add"))
    db_session.commit()

    monkeypatch.setattr(
        HealthService,
        "_check_calendar_connectivity",
        lambda self: {"reachable": True, "detail": "mock"},
    )

    service = HealthService(db_session, now_provider=lambda: now)
    result = service.calendar_health()

    assert result["webhook_queue"]["queue_depth"] == 1
    assert result["calendar_api_reachable"] is True
    assert result["status"] == "healthy"


def test_webhook_queue_backlog_triggers_degraded(monkeypatch, db_session):
    now = datetime(2024, 1, 2, tzinfo=timezone.utc)

    channel = models.CalendarSyncState(
        channel_id="health-channel-2",
        resource_id="resource-2",
        calendar_id="primary",
        expiration=now + timedelta(hours=1),
        active=True,
        updated_at=now,
    )
    db_session.add(channel)

    for idx in range(0, 1001):
        db_session.add(
            models.DriveChangeLog(
                channel_id=f"c{idx}",
                resource_id=f"r{idx}",
                resource_state="add",
                received_at=now - timedelta(minutes=idx % 5),
            )
        )
    db_session.commit()

    monkeypatch.setattr(
        HealthService,
        "_check_calendar_connectivity",
        lambda self: {"reachable": True, "detail": "mock"},
    )

    service = HealthService(db_session, now_provider=lambda: now)
    result = service.calendar_health()

    assert result["webhook_queue"]["queue_depth"] >= 1001
    assert result["status"] == "degraded"
    assert any("queue" in issue.lower() for issue in result.get("issues", []))


def test_gmail_health_uses_connectivity(monkeypatch, db_session):
    now = datetime(2024, 1, 3, tzinfo=timezone.utc)

    monkeypatch.setattr(
        HealthService,
        "_check_gmail_connectivity",
        lambda self: {"reachable": False, "auth_ok": False, "detail": "failure"},
    )

    service = HealthService(db_session, now_provider=lambda: now)
    result = service.gmail_health()

    assert result["api_reachable"] is False
    assert result["auth_ok"] is False
    assert result["status"] == "degraded"
    assert "issues" in result
