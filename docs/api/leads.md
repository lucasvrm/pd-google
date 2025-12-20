# Leads API

This document describes the leads-related endpoints available in the pd-google backend.

## Base Path

`/api/leads`

---

## Endpoints

### GET /api/leads/sales-view

Get a paginated list of leads for the sales view with filtering and sorting options.

**Query Parameters:**
- `page` (int, default: 1): Page number
- `pageSize` (int, default: 20, max: 100): Number of results per page
- `search` (string): Text search on lead names
- `owner` / `ownerIds` / `owner_id` (string): Filter by owner user ID (supports CSV)
- `status` (string): Filter by status ID (supports CSV)
- `origin` (string): Filter by origin ID (supports CSV)
- `priority` (string): Filter by priority bucket: "hot", "warm", "cold" (supports CSV)
- `tags` (string): Filter by tag IDs (CSV)
- `next_action` (string): Filter by next action code (CSV)
- `includeQualified` (bool, default: false): Include qualified/soft-deleted leads
- `order_by` (string): Sort field: "priority", "last_interaction", "created_at", "status", "owner", "next_action"

**Response:** `LeadSalesViewResponse`

---

### POST /api/leads/{lead_id}/qualify

Qualify a lead by linking it to a Deal and soft deleting it.

**Path Parameters:**
- `lead_id` (string): UUID of the lead to qualify

**Request Body:**
```json
{
  "deal_id": "uuid-of-the-deal"
}
```

**Response (200 OK):**
```json
{
  "status": "qualified",
  "lead_id": "lead-uuid",
  "deal_id": "deal-uuid",
  "qualified_at": "2024-01-15T10:30:00Z",
  "deleted_at": "2024-01-15T10:30:00Z",
  "migrated_fields": {
    "legal_name": "Company Name",
    "trade_name": "Trade Name",
    "owner_user_id": "user-uuid",
    "description": "Lead description",
    "tags": ["tag-id-1", "tag-id-2"]
  }
}
```

**Error Responses:**
- `404 Not Found`: Lead or Deal not found
- `400 Bad Request`: Lead already qualified/deleted or disqualified

---

### POST /api/leads/{lead_id}/change-owner

Change the owner of a lead with optional member tracking.

**Path Parameters:**
- `lead_id` (string): UUID of the lead to change ownership of

**Request Body:**
```json
{
  "newOwnerId": "uuid-of-new-owner",
  "addPreviousOwnerAsMember": true,
  "currentUserId": "uuid-of-requesting-user"
}
```

**Request Fields:**
- `newOwnerId` (string, required): UUID of the new owner user
- `addPreviousOwnerAsMember` (bool, default: true): Whether to add the previous owner as a collaborator
- `currentUserId` (string, required): UUID of the user making the change (for permission validation)

**Response (200 OK):**
```json
{
  "status": "owner_changed",
  "lead_id": "lead-uuid",
  "previous_owner_id": "previous-owner-uuid",
  "new_owner_id": "new-owner-uuid",
  "previous_owner_added_as_member": true,
  "changed_at": "2024-01-15T10:30:00Z",
  "changed_by": "requesting-user-uuid"
}
```

**Validation Rules:**
1. Lead must exist → `404 Not Found` if not
2. Lead must not be deleted/qualified → `400 Bad Request` if so
3. New owner must exist → `404 Not Found` if not
4. New owner must be active → `400 Bad Request` if inactive
5. New owner must be different from current owner → `400 Bad Request` if same
6. Requesting user must be authorized → `403 Forbidden` if not

**Permission Rules:**
Only the following users can change lead ownership:
- The current owner of the lead
- Users with `manager` role
- Users with `admin` role

**Side Effects:**
1. Updates the lead's `owner_user_id` to the new owner
2. If `addPreviousOwnerAsMember` is true and previous owner is not already a member:
   - Adds the previous owner to `lead_members` with role "collaborator"
3. Creates an audit log entry with action `lead.owner_changed`
4. Sends an email notification to the new owner (fire-and-forget)

**Error Responses:**
- `400 Bad Request`: Invalid request (same owner, inactive owner, deleted lead)
- `403 Forbidden`: User not authorized to change ownership
- `404 Not Found`: Lead or new owner not found
- `500 Internal Server Error`: Unexpected error during processing

---

## Models

### LeadMember

Tracks users who are collaborators on a lead (e.g., previous owners).

| Field | Type | Description |
|-------|------|-------------|
| lead_id | string | UUID of the lead |
| user_id | string | UUID of the member user |
| role | string | Member role: "collaborator", "viewer", etc. |
| added_at | datetime | When the member was added |
| added_by | string | UUID of user who added this member |

---

## Audit Log Actions

| Action | Description |
|--------|-------------|
| `create` | Lead was created |
| `update` | Lead was updated |
| `status_change` | Lead status was changed |
| `soft_delete` | Lead was soft deleted |
| `qualify_and_soft_delete` | Lead was qualified and soft deleted |
| `lead.owner_changed` | Lead ownership was transferred |
