import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import models
from services.lead_priority_service import calculate_lead_priority, classify_priority_bucket
from services.lead_priority_config_service import DEFAULT_CONFIG


def test_calculate_lead_priority_with_status_and_origin_weights():
    """Test priority calculation using status and origin priority weights."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    
    # Create status and origin with priority weights
    status = models.LeadStatus(
        id="status-1",
        code="qualified",
        label="Qualified",
        priority_weight=26
    )
    origin = models.LeadOrigin(
        id="origin-1",
        code="inbound",
        label="Inbound",
        priority_weight=20
    )
    
    lead = models.Lead(
        id="lead-priority-1",
        title="Lead Priority",
        lead_status_id=status.id,
        lead_origin_id=origin.id,
        created_at=now - timedelta(days=5),
        updated_at=now - timedelta(days=2),
    )
    lead.lead_status = status
    lead.lead_origin = origin
    
    stats = models.LeadActivityStats(
        lead_id=lead.id,
        engagement_score=80,
        last_interaction_at=now - timedelta(days=1),
    )
    lead.activity_stats = stats
    
    config = DEFAULT_CONFIG.copy()
    score = calculate_lead_priority(lead, now=now, config=config)
    
    # Score should include: status(26) + origin(20) + recency(~39) = ~85
    assert 70 <= score <= 100
    assert classify_priority_bucket(score, config) == "hot"


def test_calculate_lead_priority_penalizes_stale_leads():
    """Test that stale leads get lower priority scores."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    
    # Create status and origin with low weights
    status = models.LeadStatus(
        id="status-2",
        code="lost",
        label="Lost",
        priority_weight=5
    )
    origin = models.LeadOrigin(
        id="origin-2",
        code="outbound",
        label="Outbound",
        priority_weight=12
    )
    
    lead = models.Lead(
        id="lead-priority-2",
        title="Lead Priority Cold",
        lead_status_id=status.id,
        lead_origin_id=origin.id,
        created_at=now - timedelta(days=120),
        updated_at=now - timedelta(days=90),
    )
    lead.lead_status = status
    lead.lead_origin = origin
    
    stats = models.LeadActivityStats(
        lead_id=lead.id,
        engagement_score=5,
        last_interaction_at=now - timedelta(days=80),
    )
    lead.activity_stats = stats
    
    config = DEFAULT_CONFIG.copy()
    score = calculate_lead_priority(lead, now=now, config=config)
    
    # Score should be low: status(5) + origin(12) + recency(0) = 17
    assert score < 40
    assert classify_priority_bucket(score, config) == "cold"


def test_calculate_lead_priority_with_upcoming_meeting():
    """Test that leads with upcoming meetings get bonus points."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    
    status = models.LeadStatus(
        id="status-3",
        code="contacted",
        label="Contacted",
        priority_weight=22
    )
    origin = models.LeadOrigin(
        id="origin-3",
        code="referral",
        label="Referral",
        priority_weight=18
    )
    
    lead = models.Lead(
        id="lead-priority-3",
        title="Lead with Meeting",
        lead_status_id=status.id,
        lead_origin_id=origin.id,
        created_at=now - timedelta(days=5),
        updated_at=now - timedelta(days=1),
    )
    lead.lead_status = status
    lead.lead_origin = origin
    
    stats = models.LeadActivityStats(
        lead_id=lead.id,
        engagement_score=50,
        last_interaction_at=now - timedelta(days=1),
        next_scheduled_event_at=now + timedelta(days=2),  # Future meeting
    )
    lead.activity_stats = stats
    
    config = DEFAULT_CONFIG.copy()
    score = calculate_lead_priority(lead, now=now, config=config)
    
    # Score includes meeting bonus (25 points)
    # status(22) + origin(18) + recency(~39) + meeting(25) = ~104 -> clamped to 100
    assert score >= 90


def test_calculate_lead_priority_without_relationships():
    """Test that priority calculation handles missing relationships gracefully."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    
    lead = models.Lead(
        id="lead-priority-4",
        title="Lead No Relations",
        created_at=now - timedelta(days=5),
        updated_at=now - timedelta(days=1),
    )
    # No status or origin set
    lead.lead_status = None
    lead.lead_origin = None
    lead.activity_stats = None
    
    config = DEFAULT_CONFIG.copy()
    score = calculate_lead_priority(lead, now=now, config=config)
    
    # Score should be very low with no weights
    assert score >= 0
    assert score < 40
    assert classify_priority_bucket(score, config) == "cold"


def test_classify_priority_bucket_with_custom_thresholds():
    """Test bucket classification with custom thresholds."""
    config = {
        "thresholds": {
            "hot": 80,
            "warm": 50,
        }
    }
    
    assert classify_priority_bucket(85, config) == "hot"
    assert classify_priority_bucket(75, config) == "warm"
    assert classify_priority_bucket(60, config) == "warm"
    assert classify_priority_bucket(45, config) == "cold"


def test_calculate_lead_priority_recency_decay():
    """Test that recency score decays properly over time."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    
    status = models.LeadStatus(
        id="status-5",
        code="new",
        label="New",
        priority_weight=18
    )
    origin = models.LeadOrigin(
        id="origin-5",
        code="inbound",
        label="Inbound",
        priority_weight=20
    )
    
    # Lead with interaction 15 days ago
    lead = models.Lead(
        id="lead-priority-5",
        title="Lead Decay Test",
        lead_status_id=status.id,
        lead_origin_id=origin.id,
        created_at=now - timedelta(days=30),
        updated_at=now - timedelta(days=15),
    )
    lead.lead_status = status
    lead.lead_origin = origin
    
    stats = models.LeadActivityStats(
        lead_id=lead.id,
        engagement_score=0,
        last_interaction_at=now - timedelta(days=15),
    )
    lead.activity_stats = stats
    
    config = DEFAULT_CONFIG.copy()
    score = calculate_lead_priority(lead, now=now, config=config)
    
    # With default staleDays=30, at 15 days we should have 50% recency
    # status(18) + origin(20) + recency(~20) = ~58
    assert 50 <= score <= 70
    assert classify_priority_bucket(score, config) == "warm"


def test_calculate_lead_priority_clamps_to_range():
    """Test that scores are clamped to min/max range."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    
    # Very high weights to test clamping
    status = models.LeadStatus(
        id="status-6",
        code="won",
        label="Won",
        priority_weight=100
    )
    origin = models.LeadOrigin(
        id="origin-6",
        code="inbound",
        label="Inbound",
        priority_weight=100
    )
    
    lead = models.Lead(
        id="lead-priority-6",
        title="Lead Clamp Test",
        lead_status_id=status.id,
        lead_origin_id=origin.id,
        created_at=now,
        updated_at=now,
    )
    lead.lead_status = status
    lead.lead_origin = origin
    
    stats = models.LeadActivityStats(
        lead_id=lead.id,
        last_interaction_at=now,
        next_scheduled_event_at=now + timedelta(days=1),
    )
    lead.activity_stats = stats
    
    config = DEFAULT_CONFIG.copy()
    score = calculate_lead_priority(lead, now=now, config=config)
    
    # Should be clamped to maxScore (100)
    assert score == 100
