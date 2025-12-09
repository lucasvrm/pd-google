import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import models
from services.next_action_service import suggest_next_action


def _make_lead(**kwargs):
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    defaults = {
        "id": "lead-1",
        "title": "Lead Test",
        "created_at": now - timedelta(days=3),
        "updated_at": now - timedelta(days=1),
        "status": "new",
    }
    return models.Lead(**defaults | kwargs)


def _make_stats(**kwargs):
    defaults = {"lead_id": "lead-1", "engagement_score": 0}
    return models.LeadActivityStats(**defaults | kwargs)


def test_suggest_next_action_for_new_lead_without_interaction():
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead(created_at=now - timedelta(days=1))
    stats = _make_stats(last_interaction_at=None)

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "call_first_time"
    assert "Lead novo" in result["reason"]


def test_suggest_next_action_with_upcoming_meeting():
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead()
    stats = _make_stats(last_event_at=now + timedelta(days=2))

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "prepare_for_meeting"
    assert "Reunião futura" in result["reason"]


def test_suggest_next_action_for_high_engagement_without_deal():
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead(qualified_company_id=None)
    stats = _make_stats(
        engagement_score=90, last_interaction_at=now - timedelta(days=1)
    )

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "qualify_to_company"
    assert "Engajamento alto" in result["reason"]


def test_suggest_next_action_for_stale_interaction():
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead()
    stats = _make_stats(last_interaction_at=now - timedelta(days=10))

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "send_follow_up"
    assert "10 dias" in result["reason"]

