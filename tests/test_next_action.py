import os
import sys
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.next_action_service import (
    COLD_LEAD_DAYS,
    DISQUALIFY_DAYS,
    HIGH_ENGAGEMENT_SCORE,
    MEDIUM_ENGAGEMENT_SCORE,
    POST_MEETING_WINDOW_DAYS,
    SCHEDULE_MEETING_ENGAGEMENT_THRESHOLD,
    STALE_INTERACTION_DAYS,
    suggest_next_action,
)


def _make_lead(**kwargs):
    """Create a mock lead object with defaults."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    defaults = {
        "id": "lead-1",
        "title": "Lead Test",
        "created_at": now - timedelta(days=3),
        "updated_at": now - timedelta(days=1),
        "qualified_company_id": None,
        "qualified_master_deal_id": None,
        "disqualified_at": None,
        "last_interaction_at": None,
    }
    return SimpleNamespace(**{**defaults, **kwargs})


def _make_stats(**kwargs):
    """Create a mock stats object with defaults."""
    defaults = {
        "lead_id": "lead-1",
        "engagement_score": 0,
        "last_interaction_at": None,
        "last_event_at": None,
        "next_scheduled_event_at": None,
        "last_call_at": None,
        "last_value_asset_at": None,
    }
    return SimpleNamespace(**{**defaults, **kwargs})


# ========== EXISTING TESTS (Updated) ==========

def test_suggest_next_action_for_new_lead_without_interaction():
    """Precedence 3: call_first_time when no interaction exists."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead(created_at=now - timedelta(days=1))
    stats = _make_stats(last_interaction_at=None)

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "call_first_time"
    assert "Lead novo" in result["reason"]


def test_suggest_next_action_with_upcoming_meeting():
    """Precedence 1: prepare_for_meeting when future event is scheduled."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead()
    stats = _make_stats(last_event_at=now + timedelta(days=2))

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "prepare_for_meeting"
    assert "Reunião futura" in result["reason"]


def test_suggest_next_action_for_high_engagement_without_deal():
    """Precedence 5: qualify_to_company when engagement is high and no company qualified."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead(qualified_company_id=None)
    stats = _make_stats(
        engagement_score=90, last_interaction_at=now - timedelta(days=1)
    )

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "qualify_to_company"
    assert "Engajamento alto" in result["reason"]


def test_suggest_next_action_for_stale_interaction():
    """Precedence 9: send_follow_up when interaction is stale but not cold."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead()
    # 10 days is stale (>=5) but not cold (<30)
    stats = _make_stats(last_interaction_at=now - timedelta(days=10))

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "send_follow_up"
    assert "10 dias" in result["reason"]


# ========== NEW TESTS FOR SPRINT 2/3 ACTIONS ==========

def test_suggest_next_action_post_meeting_follow_up():
    """Precedence 2: post_meeting_follow_up after recent meeting with no subsequent interaction."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    # Meeting was 2 days ago
    meeting_time = now - timedelta(days=2)
    lead = _make_lead()
    stats = _make_stats(
        last_event_at=meeting_time,
        # Last interaction was before the meeting
        last_interaction_at=meeting_time - timedelta(days=1),
    )

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "post_meeting_follow_up"
    assert result["label"] == "Follow-up pós-reunião"
    assert "2 dia(s)" in result["reason"]


def test_suggest_next_action_handoff_to_deal():
    """Precedence 4: handoff_to_deal when company qualified but no deal linked."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead(
        qualified_company_id="company-123",
        qualified_master_deal_id=None,
    )
    stats = _make_stats(
        last_interaction_at=now - timedelta(days=1),
        engagement_score=50,
    )

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "handoff_to_deal"
    assert result["label"] == "Fazer handoff (para deal)"
    assert "deal" in result["reason"].lower()


def test_suggest_next_action_schedule_meeting():
    """Precedence 6: schedule_meeting when engaged but no upcoming meeting."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead()
    stats = _make_stats(
        engagement_score=SCHEDULE_MEETING_ENGAGEMENT_THRESHOLD,
        last_interaction_at=now - timedelta(days=1),
        last_event_at=None,  # No meeting scheduled
    )

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "schedule_meeting"
    assert result["label"] == "Agendar reunião"
    assert "reunião" in result["reason"].lower()


def test_suggest_next_action_call_again():
    """Precedence 7: call_again when last call was within the call window."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead()
    stats = _make_stats(
        last_interaction_at=now - timedelta(days=3),
        last_call_at=now - timedelta(days=3),
        engagement_score=30,  # Below schedule_meeting threshold
    )

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "call_again"
    assert result["label"] == "Ligar novamente"
    assert "3 dia(s)" in result["reason"]


def test_suggest_next_action_send_value_asset_never_sent():
    """Precedence 8: send_value_asset when no value asset has been sent and lead is engaged."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead()
    stats = _make_stats(
        last_interaction_at=now - timedelta(days=1),
        engagement_score=MEDIUM_ENGAGEMENT_SCORE,  # 40
        last_value_asset_at=None,
        last_call_at=None,  # No recent call to trigger call_again
    )

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "send_value_asset"
    assert result["label"] == "Enviar material / valor"
    assert "material" in result["reason"].lower() or "valor" in result["reason"].lower()


def test_suggest_next_action_send_value_asset_stale():
    """Precedence 8: send_value_asset when last value asset is old."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead()
    stats = _make_stats(
        last_interaction_at=now - timedelta(days=1),
        engagement_score=MEDIUM_ENGAGEMENT_SCORE,
        last_value_asset_at=now - timedelta(days=20),  # Old (>=14 days)
        last_call_at=None,
    )

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "send_value_asset"
    assert result["label"] == "Enviar material / valor"
    assert "20 dias" in result["reason"]


def test_suggest_next_action_reengage_cold_lead():
    """Precedence 10: reengage_cold_lead when interaction is cold (>=30 days)."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead()
    stats = _make_stats(
        last_interaction_at=now - timedelta(days=45),  # Cold (>=30, <60)
        engagement_score=30,  # Below medium threshold
    )

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "reengage_cold_lead"
    assert result["label"] == "Reengajar lead frio"
    assert "45 dias" in result["reason"]


def test_suggest_next_action_disqualify():
    """Precedence 11: disqualify when very old, low engagement, and no company/deal."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead(
        qualified_company_id=None,
        qualified_master_deal_id=None,
        disqualified_at=None,
    )
    stats = _make_stats(
        last_interaction_at=now - timedelta(days=DISQUALIFY_DAYS + 10),  # 70 days
        engagement_score=20,  # Low (< 40)
    )

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "disqualify"
    assert result["label"] == "Desqualificar / encerrar"
    assert "engajamento baixo" in result["reason"].lower()


def test_suggest_next_action_disqualify_not_applied_if_company_exists():
    """Disqualify should NOT be suggested if company is already qualified."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead(
        qualified_company_id="company-123",  # Has company
        qualified_master_deal_id=None,
    )
    stats = _make_stats(
        last_interaction_at=now - timedelta(days=DISQUALIFY_DAYS + 10),  # 70 days
        engagement_score=20,  # Low
    )

    result = suggest_next_action(lead, stats, now=now)

    # Should suggest handoff_to_deal instead (because company exists but no deal)
    assert result["code"] == "handoff_to_deal"
    assert result["code"] != "disqualify"


def test_suggest_next_action_disqualify_not_applied_if_already_disqualified():
    """Disqualify should NOT be suggested if lead is already disqualified."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead(
        qualified_company_id=None,
        qualified_master_deal_id=None,
        disqualified_at=now - timedelta(days=5),  # Already disqualified
    )
    stats = _make_stats(
        last_interaction_at=now - timedelta(days=DISQUALIFY_DAYS + 10),
        engagement_score=20,
    )

    result = suggest_next_action(lead, stats, now=now)

    # Should fall through to reengage_cold_lead or send_follow_up
    assert result["code"] != "disqualify"
    assert result["code"] in ["reengage_cold_lead", "send_follow_up"]


def test_suggest_next_action_uses_next_scheduled_event_at():
    """prepare_for_meeting should use next_scheduled_event_at if available."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead()
    stats = _make_stats(
        next_scheduled_event_at=now + timedelta(days=3),
        last_event_at=now - timedelta(days=5),  # Past event, should be ignored
    )

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "prepare_for_meeting"
    assert "Reunião futura" in result["reason"]


# ========== PRECEDENCE ORDER TESTS ==========

def test_precedence_prepare_for_meeting_over_all():
    """Future meeting takes precedence over everything."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead(
        qualified_company_id="company-123",  # Would trigger handoff
    )
    stats = _make_stats(
        last_event_at=now + timedelta(days=1),  # Future meeting
        engagement_score=90,  # High engagement
        last_interaction_at=None,  # Would trigger call_first_time
    )

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "prepare_for_meeting"


def test_precedence_post_meeting_over_call_first_time():
    """Post-meeting follow-up takes precedence over call_first_time."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead()
    stats = _make_stats(
        last_event_at=now - timedelta(days=1),  # Past meeting
        last_interaction_at=None,  # Would normally trigger call_first_time
    )

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "post_meeting_follow_up"


def test_precedence_handoff_over_qualify():
    """Handoff to deal takes precedence over qualify_to_company."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead(
        qualified_company_id="company-123",  # Already has company
    )
    stats = _make_stats(
        engagement_score=HIGH_ENGAGEMENT_SCORE + 10,  # Would trigger qualify
        last_interaction_at=now - timedelta(days=1),
    )

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "handoff_to_deal"


def test_precedence_qualify_over_schedule_meeting():
    """Qualify to company takes precedence over schedule_meeting."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead(qualified_company_id=None)
    stats = _make_stats(
        engagement_score=HIGH_ENGAGEMENT_SCORE,  # High engagement
        last_interaction_at=now - timedelta(days=1),
    )

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "qualify_to_company"


def test_default_send_follow_up():
    """Default action is send_follow_up when nothing else applies."""
    now = datetime(2024, 1, 10, tzinfo=timezone.utc)
    lead = _make_lead()
    stats = _make_stats(
        last_interaction_at=now - timedelta(days=2),  # Recent (< 5 days)
        engagement_score=30,  # Low-medium
    )

    result = suggest_next_action(lead, stats, now=now)

    assert result["code"] == "send_follow_up"
    assert result["label"] == "Enviar follow-up"
    assert "Manter relacionamento" in result["reason"]
