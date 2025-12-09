import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import models
from database import Base
from services import lead_activity_worker

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_lead_activity_worker.db"
engine = create_engine(SQLALCHEMY_DATABASE_URL, connect_args={"check_same_thread": False})
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class DummyLogger:
    def __init__(self):
        self.info_calls: list[dict] = []
        self.error_calls: list[dict] = []

    def info(self, *args, **kwargs):
        payload = kwargs.copy()
        if args:
            payload["args"] = args
        self.info_calls.append(payload)

    def error(self, *args, **kwargs):
        payload = kwargs.copy()
        if args:
            payload["args"] = args
        self.error_calls.append(payload)


def override_session_factory():
    return TestingSessionLocal()


def setup_module(module):
    if os.path.exists("./test_lead_activity_worker.db"):
        os.remove("./test_lead_activity_worker.db")

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    now = datetime.now(timezone.utc)

    lead = models.Lead(
        id="worker-lead-1",
        title="Worker Lead",
        created_at=now - timedelta(days=3),
        updated_at=now - timedelta(days=1),
    )
    db.add(lead)
    db.commit()
    db.close()


def teardown_module(module):
    if os.path.exists("./test_lead_activity_worker.db"):
        os.remove("./test_lead_activity_worker.db")


def test_lead_activity_worker_updates_stats_and_logs(monkeypatch):
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)

    def fake_compute_lead_engagement(*_, **__):
        class Stats:
            engagement_score = 55
            last_interaction_at = now - timedelta(days=1)
            last_email_at = now - timedelta(days=2)
            last_event_at = now + timedelta(days=3)
            total_emails = 4
            total_events = 1
            total_interactions = 5

        return Stats()

    monkeypatch.setattr(
        lead_activity_worker, "compute_lead_engagement", fake_compute_lead_engagement
    )
    monkeypatch.setattr(lead_activity_worker, "GoogleGmailService", lambda: object())
    monkeypatch.setattr(lead_activity_worker, "CRMContactService", lambda db: object())

    logger = DummyLogger()
    monkeypatch.setattr(lead_activity_worker, "activity_logger", logger)

    worker = lead_activity_worker.LeadActivityWorker(session_factory=override_session_factory)
    worker.run()

    db = TestingSessionLocal()
    stats = db.query(models.LeadActivityStats).filter_by(lead_id="worker-lead-1").first()
    db.close()

    assert stats is not None
    assert stats.engagement_score == 55
    assert stats.last_interaction_at.date() == (now - timedelta(days=1)).date()

    assert logger.info_calls, "Telemetry info should be logged"
    telemetry = logger.info_calls[-1]
    assert telemetry["processed"] == 1
    assert telemetry["errors"] == 0
    assert telemetry["errors_by_lead"] == []

