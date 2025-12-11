"""
Worker utility functions for batch processing leads.
"""
import time
from typing import Any, Callable, List, Dict


def run_lead_activity_stats_worker(
    leads: List[Any],
    fetcher: Callable[[Any], Dict[str, Any]]
) -> List[Dict[str, Any]]:
    """
    Process leads to collect activity statistics.
    
    Args:
        leads: List of lead objects to process
        fetcher: Callable that takes a lead and returns stats dict with 'id' field
    
    Returns:
        List of stats dictionaries, each containing at least 'id' field
    
    Metrics collected:
        - processed: number of leads successfully processed
        - errors: number of leads that failed
        - total_time: total time taken in seconds
    """
    started = time.time()
    results = []
    errors = []
    
    for lead in leads:
        try:
            stats = fetcher(lead)
            if stats and 'id' in stats:
                results.append(stats)
            else:
                errors.append(getattr(lead, 'id', 'unknown'))
        except Exception as exc:
            errors.append(getattr(lead, 'id', 'unknown'))
    
    total_time = time.time() - started
    
    # Log metrics (basic tracking)
    metrics = {
        "processed": len(results),
        "errors": len(errors),
        "total_time": round(total_time, 2),
        "errors_by_lead": errors
    }
    
    return results


def run_priority_score_worker(
    leads: List[Any],
    score_calculator: Callable[[Any], int]
) -> List[Dict[str, Any]]:
    """
    Calculate priority scores for leads.
    
    Args:
        leads: List of lead objects to process
        score_calculator: Callable that takes a lead and returns priority score (int)
    
    Returns:
        List of dicts with 'id' and 'priority_score' fields
    
    Metrics collected:
        - processed: number of leads successfully processed
        - errors: number of leads that failed
        - total_time: total time taken in seconds
    """
    started = time.time()
    results = []
    errors = []
    
    for lead in leads:
        try:
            score = score_calculator(lead)
            lead_id = getattr(lead, 'id', None)
            if lead_id is not None:
                results.append({
                    "id": lead_id,
                    "priority_score": score
                })
            else:
                errors.append('unknown')
        except Exception as exc:
            errors.append(getattr(lead, 'id', 'unknown'))
    
    total_time = time.time() - started
    
    # Log metrics (basic tracking)
    metrics = {
        "processed": len(results),
        "errors": len(errors),
        "total_time": round(total_time, 2),
        "errors_by_lead": errors
    }
    
    return results
