# Lead Priority Configuration

## Overview

The lead priority calculation system uses dynamic configuration stored in the database (`system_settings` table) to calculate priority scores and classify leads into hot/warm/cold buckets.

## Configuration Structure

The `lead_priority_config` key in `system_settings` contains a JSON object with:

```json
{
  "weights": {
    "status": {
      "new": 18,
      "contacted": 22,
      "qualified": 26,
      "proposal": 28,
      "won": 30,
      "lost": 5
    },
    "origin": {
      "inbound": 20,
      "referral": 18,
      "partner": 16,
      "event": 15,
      "outbound": 12
    },
    "recency_max": 30.0,
    "recency_decay_rate": 0.5,
    "engagement_multiplier": 0.2
  },
  "thresholds": {
    "hot": 70,
    "warm": 40
  }
}
```

## Components

### Weights

- **status**: Points awarded based on lead's current status (higher = closer to conversion)
- **origin**: Points awarded based on how the lead was acquired
- **recency_max**: Maximum points for recency (30 points for leads with recent interaction)
- **recency_decay_rate**: How fast recency points decay over time (0.5 = lose 0.5 points per day)
- **engagement_multiplier**: Multiplier for engagement score (0.2 = engagement score is worth 20% of its value)

### Thresholds

- **hot**: Minimum score (default 70) to be classified as "hot" priority
- **warm**: Minimum score (default 40) to be classified as "warm" priority
- Scores below warm threshold are classified as "cold"

## Priority Calculation

The priority score (0-100) is calculated as:

```
score = status_points + origin_points + recency_points + engagement_points
```

Where:
- `status_points` = weight for lead's status (from config)
- `origin_points` = weight for lead's origin (from config)
- `recency_points` = max(0, recency_max - (days_since_interaction * recency_decay_rate))
- `engagement_points` = lead.engagement_score * engagement_multiplier

## API Usage

### Sales View Endpoint

`GET /api/leads/sales-view` uses dynamic thresholds for filtering:

```bash
# Filter by priority bucket using dynamic thresholds
GET /api/leads/sales-view?priority=hot,warm

# Filter by minimum score
GET /api/leads/sales-view?min_priority_score=50
```

The endpoint:
1. Loads config once per request from `system_settings`
2. Uses `thresholds.hot` and `thresholds.warm` for bucket filtering
3. Calculates priority score using weights from config for leads without stored scores

### Priority Worker

The `LeadPriorityWorker` (background job):
1. Loads config once at start
2. Eager-loads `lead_status` and `lead_origin` relationships (prevents N+1 queries)
3. Calculates priority score for each lead using config weights
4. Updates `priority_score` column in database

## Configuration Updates

To update the configuration:

```sql
-- Update thresholds
UPDATE system_settings
SET value = jsonb_set(value, '{thresholds,hot}', '80')
WHERE key = 'lead_priority_config';

-- Update status weight
UPDATE system_settings
SET value = jsonb_set(value, '{weights,status,contacted}', '25')
WHERE key = 'lead_priority_config';
```

Changes take effect immediately on next request/worker run (config is loaded fresh each time).

## Default Fallback

If `system_settings.lead_priority_config` is not found, the system falls back to hardcoded defaults defined in `services/lead_priority_config_service.py`.

## Migration

Run `migrations/ensure_leads_schema_v4.sql` to:
1. Create `system_settings` table if it doesn't exist
2. Seed default `lead_priority_config`
3. Add `priority_weight` columns to `lead_statuses` and `lead_origins` (for future use)
4. Seed default statuses and origins with priority weights

## See Also

- `services/lead_priority_config_service.py` - Config loading with defaults
- `services/lead_priority_service.py` - Score calculation logic
- `services/lead_priority_worker.py` - Background score updater
- `routers/leads.py` - Sales view endpoint implementation
