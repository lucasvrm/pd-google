# Leads API

Endpoints for managing leads in the CRM.

## Endpoints

### GET /api/leads/sales-view

Returns a paginated list of leads for the sales view with priority scoring and next action recommendations.

**Query Parameters:**
- `page` (int, default: 1): Page number
- `pageSize` (int, default: 20, max: 100): Items per page
- `search` (string, optional): Text search on lead names
- `tags` (string, optional): Comma-separated tag IDs to filter by
- `owner` (string, optional): Owner user ID filter (use "me" for current user)
- `status` (string, optional): Status filter (CSV)
- `priority` (string, optional): Priority bucket filter (hot, warm, cold)
- `order_by` (string, default: "priority"): Sort field (priority, last_interaction, created_at, status, owner, next_action)

**Response:** `LeadSalesViewResponse`

---

### POST /api/leads/{lead_id}/qualify

Qualifies a lead by linking it to a deal and soft deleting it from the sales pipeline.

**Path Parameters:**
- `lead_id` (string): UUID of the lead to qualify

**Request Body:** `QualifyLeadRequest`
```json
{
  "deal_id": "string (required) - UUID of the deal to link"
}
```

**Response:** `QualifyLeadResponse`
```json
{
  "status": "qualified",
  "lead_id": "string",
  "deal_id": "string",
  "qualified_at": "datetime",
  "deleted_at": "datetime",
  "migrated_fields": {
    "legal_name": "string | null",
    "trade_name": "string | null",
    "owner_user_id": "string | null",
    "description": "string | null",
    "tags": ["tag_id1", "tag_id2"]
  }
}
```

**Errors:**
- 404: Lead or Deal not found
- 400: Lead already qualified/deleted or disqualified

---

### POST /api/leads/{lead_id}/change-owner

Changes the owner of a lead.

**Path Parameters:**
- `lead_id` (string): UUID of the lead

**Request Body:** `ChangeOwnerRequest`
```json
{
  "new_owner_id": "string (required) - UUID of the new owner",
  "current_user_id": "string (required) - UUID of the user making the change",
  "add_previous_owner_as_member": "boolean (default: true) - Reserved for future use"
}
```

**Response:** `ChangeOwnerResponse`
```json
{
  "status": "success",
  "lead_id": "string",
  "previous_owner_id": "string | null",
  "new_owner_id": "string",
  "changed_by": "string",
  "changed_at": "datetime"
}
```

**Permission Requirements:**
- The current lead owner can transfer their own leads
- Users with manager or admin roles can transfer any lead

**Errors:**
- 404: Lead not found
- 404: New owner user not found
- 400: New owner is the same as current owner
- 403: User does not have permission to change ownership

**Audit Logging:**
Creates an audit log entry with action `lead.owner_changed` containing:
- Previous owner ID
- New owner ID
- Who made the change
- Timestamp

---

## Schemas

### LeadSalesViewItem
```json
{
  "id": "string",
  "legal_name": "string | null",
  "trade_name": "string | null",
  "lead_status_id": "string | null",
  "lead_origin_id": "string | null",
  "owner_user_id": "string | null",
  "owner": {
    "id": "string | null",
    "name": "string | null"
  },
  "priority_score": "int",
  "priority_bucket": "string (hot | warm | cold)",
  "priority_description": "string | null",
  "last_interaction_at": "datetime | null",
  "qualified_master_deal_id": "string | null",
  "address_city": "string | null",
  "address_state": "string | null",
  "tags": [{"id": "string", "name": "string", "color": "string | null"}],
  "primary_contact": {"id": "string | null", "name": "string | null", "role": "string | null"},
  "next_action": {"code": "string", "label": "string", "reason": "string"}
}
```
