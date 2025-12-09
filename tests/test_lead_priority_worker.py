import os
import sys
from datetime import datetime, timedelta, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import models
from database import Base
from services import lead_priority_worker

SQLALCHEMY_DATABASE_URL = "sqlite:///./test_lead_priority_worker.db"
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
    if os.path.exists("./test_lead_priority_worker.db"):
        os.remove("./test_lead_priority_worker.db")

    Base.metadata.create_all(bind=engine)
    db = TestingSessionLocal()
    now = datetime.now(timezone.utc)

    lead = models.Lead(
        id="priority-worker-1",
        title="Priority Lead",
        created_at=now - timedelta(days=10),
        updated_at=now - timedelta(days=5),
    )
    stats = models.LeadActivityStats(
        lead_id=lead.id,
        engagement_score=20,
        last_interaction_at=now - timedelta(days=2),
    )

    db.add_all([lead, stats])
    db.commit()
    db.close()


def teardown_module(module):
    if os.path.exists("./test_lead_priority_worker.db"):
        os.remove("./test_lead_priority_worker.db")


def test_priority_worker_refreshes_scores_and_logs(monkeypatch):
    logger = DummyLogger()
    monkeypatch.setattr(lead_priority_worker, "priority_logger", logger)

    monkeypatch.setattr(lead_priority_worker, "calculate_lead_priority", lambda *_, **__: 77)

    worker = lead_priority_worker.LeadPriorityWorker(session_factory=override_session_factory)
    worker.run()

    db = TestingSessionLocal()
    lead = db.query(models.Lead).filter_by(id="priority-worker-1").first()
    db.close()

    assert lead.priority_score == 77

    assert logger.info_calls, "Telemetry should be emitted"
    telemetry = logger.info_calls[-1]
    assert telemetry["processed"] == 1
    assert telemetry["errors"] == 0
    assert telemetry["errors_by_lead"] == []

