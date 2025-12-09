import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import models
from services.lead_priority_service import calculate_lead_priority, classify_priority_bucket


def test_calculate_lead_priority_rewards_recent_engagement():
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = models.Lead(
        id="lead-priority-1",
        title="Lead Priority",
        status="qualified",
        origin="inbound",
        created_at=now - timedelta(days=5),
        updated_at=now - timedelta(days=2),
    )
    stats = models.LeadActivityStats(
        lead_id=lead.id,
        engagement_score=80,
        last_interaction_at=now - timedelta(days=1),
    )

    score = calculate_lead_priority(lead, stats, now=now)

    assert 70 <= score <= 100
    assert classify_priority_bucket(score) == "hot"


def test_calculate_lead_priority_penalizes_stale_leads():
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = models.Lead(
        id="lead-priority-2",
        title="Lead Priority Cold",
        status="lost",
        origin="outbound",
        created_at=now - timedelta(days=120),
        updated_at=now - timedelta(days=90),
    )
    stats = models.LeadActivityStats(
        lead_id=lead.id,
        engagement_score=5,
        last_interaction_at=now - timedelta(days=80),
    )

    score = calculate_lead_priority(lead, stats, now=now)

    assert score < 40
    assert classify_priority_bucket(score) == "cold"
