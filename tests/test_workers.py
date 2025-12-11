import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from services.workers import run_lead_activity_stats_worker, run_priority_score_worker


class MockLead:
    def __init__(self, lead_id, should_fail=False):
        self.id = lead_id
        self.should_fail = should_fail


def test_run_lead_activity_stats_worker_success():
    """Test that worker processes leads and returns stats."""
    leads = [MockLead("lead-1"), MockLead("lead-2"), MockLead("lead-3")]
    
    def mock_fetcher(lead):
        return {
            "id": lead.id,
            "engagement_score": 50,
            "total_emails": 5
        }
    
    results = run_lead_activity_stats_worker(leads, mock_fetcher)
    
    assert len(results) == 3
    assert results[0]["id"] == "lead-1"
    assert results[0]["engagement_score"] == 50
    assert results[1]["id"] == "lead-2"
    assert results[2]["id"] == "lead-3"


def test_run_lead_activity_stats_worker_handles_errors():
    """Test that worker handles errors gracefully."""
    leads = [MockLead("lead-1"), MockLead("lead-2"), MockLead("lead-3")]
    
    def mock_fetcher(lead):
        if lead.id == "lead-2":
            raise Exception("Simulated error")
        return {
            "id": lead.id,
            "engagement_score": 50
        }
    
    results = run_lead_activity_stats_worker(leads, mock_fetcher)
    
    # Should have 2 successful results (lead-1 and lead-3)
    assert len(results) == 2
    assert results[0]["id"] == "lead-1"
    assert results[1]["id"] == "lead-3"


def test_run_lead_activity_stats_worker_skips_invalid_results():
    """Test that worker skips results without 'id' field."""
    leads = [MockLead("lead-1"), MockLead("lead-2"), MockLead("lead-3")]
    
    def mock_fetcher(lead):
        if lead.id == "lead-2":
            return {"no_id_field": True}  # Missing 'id' field
        return {
            "id": lead.id,
            "engagement_score": 50
        }
    
    results = run_lead_activity_stats_worker(leads, mock_fetcher)
    
    # Should have 2 valid results
    assert len(results) == 2
    assert results[0]["id"] == "lead-1"
    assert results[1]["id"] == "lead-3"


def test_run_priority_score_worker_success():
    """Test that worker calculates priority scores."""
    leads = [MockLead("lead-1"), MockLead("lead-2"), MockLead("lead-3")]
    
    def mock_calculator(lead):
        # Simple mock: return different scores based on lead id
        scores = {"lead-1": 80, "lead-2": 50, "lead-3": 20}
        return scores.get(lead.id, 0)
    
    results = run_priority_score_worker(leads, mock_calculator)
    
    assert len(results) == 3
    assert results[0]["id"] == "lead-1"
    assert results[0]["priority_score"] == 80
    assert results[1]["id"] == "lead-2"
    assert results[1]["priority_score"] == 50
    assert results[2]["id"] == "lead-3"
    assert results[2]["priority_score"] == 20


def test_run_priority_score_worker_handles_errors():
    """Test that worker handles calculation errors."""
    leads = [MockLead("lead-1"), MockLead("lead-2"), MockLead("lead-3")]
    
    def mock_calculator(lead):
        if lead.id == "lead-2":
            raise Exception("Calculation failed")
        return 75
    
    results = run_priority_score_worker(leads, mock_calculator)
    
    # Should have 2 successful results
    assert len(results) == 2
    assert results[0]["id"] == "lead-1"
    assert results[0]["priority_score"] == 75
    assert results[1]["id"] == "lead-3"
    assert results[1]["priority_score"] == 75


def test_run_priority_score_worker_accumulates_results():
    """Test that worker accumulates all results correctly."""
    # Test with larger dataset
    leads = [MockLead(f"lead-{i}") for i in range(10)]
    
    def mock_calculator(lead):
        return 60
    
    results = run_priority_score_worker(leads, mock_calculator)
    
    assert len(results) == 10
    for i, result in enumerate(results):
        assert result["id"] == f"lead-{i}"
        assert result["priority_score"] == 60
