# API Drive Items Adapter

## Overview

The `/api/drive/items` endpoint is an **adapter** that provides frontend-compatible access to Google Drive files and folders associated with entities (companies, leads, deals).

## Purpose

This adapter exists to:
1. **Eliminate CORS/404 errors** - Provides the exact route the frontend expects
2. **Maintain frontend compatibility** - Returns data in the format the frontend currently uses
3. **Bridge the transition** - Allows backend and frontend to evolve independently

The adapter wraps the existing `/drive/{entity_type}/{entity_id}` endpoint functionality while transforming the response to match frontend expectations.

## Endpoint

```
GET /api/drive/items
```

### Query Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| `entityType` | string | Yes | - | Entity type: `company`, `lead`, or `deal` |
| `entityId` | string | Yes | - | UUID of the entity |
| `page` | integer | No | 1 | Page number (1-indexed, min: 1) |
| `limit` | integer | No | 50 | Items per page (min: 1, max: 200) |

### Authentication

This endpoint requires authentication via one of:
- **JWT Bearer Token** (preferred): `Authorization: Bearer <token>`
- **Legacy Headers** (temporary): `x-user-id` and `x-user-role`

### Response Format

```json
{
  "items": [
    {
      "id": "string",
      "name": "string",
      "url": "string | null",
      "createdAt": "string | null",
      "mimeType": "string",
      "type": "file | folder",
      "size": "number | null"
    }
  ],
  "total": "number",
  "root_url": "string | null"
}
```

### Response Fields

- `items`: Array of drive items (paginated)
  - `id`: Google Drive file/folder ID
  - `name`: Name of the file or folder
  - `url`: Web view link (null if not available)
  - `createdAt`: ISO 8601 timestamp of creation (null if not available)
  - `mimeType`: MIME type of the item
  - `type`: Either `"file"` or `"folder"`
  - `size`: Size in bytes (null for folders or if not available)
- `total`: Total number of items before pagination
- `root_url`: Direct URL to the entity's root folder in Google Drive (null if not available). This allows the frontend to open the root folder directly without inferring from the hierarchy.

## Examples

### Basic Request

```bash
curl -X GET "http://localhost:8000/api/drive/items?entityType=deal&entityId=123e4567-e89b-12d3-a456-426614174000" \
  -H "Authorization: Bearer <your-jwt-token>"
```

### Request with Pagination

```bash
curl -X GET "http://localhost:8000/api/drive/items?entityType=company&entityId=123e4567-e89b-12d3-a456-426614174000&page=2&limit=20" \
  -H "Authorization: Bearer <your-jwt-token>"
```

### Legacy Authentication

```bash
curl -X GET "http://localhost:8000/api/drive/items?entityType=lead&entityId=123e4567-e89b-12d3-a456-426614174000" \
  -H "x-user-id: user-123" \
  -H "x-user-role: manager"
```

### Example Response

```json
{
  "items": [
    {
      "id": "1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
      "name": "Project Proposal.pdf",
      "url": "https://drive.google.com/file/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/view",
      "createdAt": "2025-12-01T10:30:00Z",
      "mimeType": "application/pdf",
      "type": "file",
      "size": 245760
    },
    {
      "id": "2CxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
      "name": "Documents",
      "url": "https://drive.google.com/drive/folders/2CxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms",
      "createdAt": "2025-12-01T09:00:00Z",
      "mimeType": "application/vnd.google-apps.folder",
      "type": "folder",
      "size": null
    }
  ],
  "total": 15,
  "root_url": "https://drive.google.com/drive/folders/0BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms"
}
```

## How It Works

### Internal Mapping

The adapter internally calls the same logic used by `/drive/{entity_type}/{entity_id}`:

1. **Validation**: Validates `entityType` is one of: `company`, `lead`, `deal`
2. **Folder Resolution**: Uses `HierarchyService` to ensure folder structure exists
3. **File Listing**: Calls `drive_service.list_files()` to get all files
4. **Soft Delete Filtering**: Excludes items marked as soft-deleted in the database
5. **Pagination**: Performs in-memory pagination based on `page` and `limit`
6. **Transformation**: Converts items to frontend-expected format
7. **Response**: Returns `{ items, total, root_url }` structure

### Differences from `/drive/{entity_type}/{entity_id}`

| Aspect | `/drive/{entity_type}/{entity_id}` | `/api/drive/items` |
|--------|-----------------------------------|-------------------|
| Route style | Path parameters | Query parameters |
| Response root | `files` | `items` |
| Response structure | `DriveResponse` with pagination metadata | Simple `{ items, total, root_url }` |
| Item fields | `createdTime`, `webViewLink` | `createdAt`, `url` |
| Permission in response | Yes | No |
| Root folder URL | Not included | Included as `root_url` |

### Pagination

Pagination is performed **in-memory** after fetching all items:
- All files are retrieved from Google Drive
- Soft-deleted items are filtered out
- Pagination slicing is applied: `items[start:end]`
- `total` always reflects the full count before pagination

**Note**: For large folders (1000+ items), consider implementing pagination at the service layer for better performance.

## Error Responses

### 400 Bad Request - Invalid Entity Type
```json
{
  "detail": "Invalid entityType. Allowed: ['company', 'lead', 'deal']"
}
```

### 401 Unauthorized - Missing Authentication
```json
{
  "detail": "Not authenticated. Missing Authorization header or x-user-id header."
}
```

### 401 Unauthorized - Invalid JWT
```json
{
  "detail": "Invalid token: ..."
}
```

### 404 Not Found - Entity Not Found
```json
{
  "detail": "Lead with ID ... not found in database"
}
```

### 422 Unprocessable Entity - Validation Error
```json
{
  "detail": [
    {
      "loc": ["query", "entityType"],
      "msg": "field required",
      "type": "value_error.missing"
    }
  ]
}
```

### 500 Internal Server Error
```json
{
  "detail": "Failed to resolve/create folder structure"
}
```

## Security Considerations

1. **Authentication Required**: All requests must be authenticated
2. **Permission Enforcement**: Uses the same permission system as the original endpoint
3. **Soft Delete Respect**: Automatically filters out soft-deleted items
4. **No Legacy Header Trust**: While legacy headers are supported for transition, JWT is the preferred and secure method

## Future Considerations

### Migration Path

When the frontend is ready to migrate:

1. **Update frontend** to use `/drive/{entity_type}/{entity_id}` with path parameters
2. **Adapt to new response structure** with full `DriveResponse` schema
3. **Deprecate `/api/drive/items`** endpoint after migration is complete
4. **Remove adapter code** once no longer needed

### Performance Improvements

For production with large datasets:
- Implement pagination at the Google Drive API level
- Add caching for frequently accessed folders
- Consider pagination metadata in response (current page, total pages, etc.)

## Testing

Comprehensive tests are available in `tests/test_drive_items_adapter.py`:
- Response structure validation
- Pagination functionality
- Authentication (JWT and legacy)
- Error handling
- Entity type validation
- Soft delete filtering

Run tests:
```bash
pytest tests/test_drive_items_adapter.py -v
```

## Related Documentation

- [JWT Authentication](./jwt_auth.md) - Details on JWT token usage
- [Drive Endpoints](./drive_endpoints.md) - Original drive endpoint documentation
