# Drive Endpoints & Authentication

This document outlines the API contract for Google Drive integration endpoints in `pd-google`, including authentication, permissions, and request/response schemas.

## Authentication

All Drive endpoints require authentication. The system prioritizes Supabase JWT tokens but supports legacy headers as a fallback.

### 1. JWT Authentication (Recommended)

Clients should send the Supabase JWT in the `Authorization` header.

```http
Authorization: Bearer <SUPABASE_JWT_TOKEN>
```

The backend extracts the `sub` (User ID) and `role` (User Role) from the token claims.

### 2. Legacy Fallback

If no valid JWT is provided, the system falls back to the following headers (deprecated):

```http
x-user-id: <USER_UUID>
x-user-role: <USER_ROLE>
```

## Permissions

Permissions are derived from the user's role in the application (e.g., `admin`, `analyst`, `client`) and mapped to Drive permissions (`owner`, `writer`, `reader`).

| App Role | Drive Permission | Capabilities |
| :--- | :--- | :--- |
| `admin`, `superadmin` | `owner` | Read, Write, Delete |
| `manager`, `analyst`, `new_business` | `writer` | Read, Write, Soft Delete |
| `client`, `customer` | `reader` | Read Only |
| *Default* | `reader` | Read Only |

## Endpoints

### 1. List Files (Get Entity Drive)

Retrieves files and folders for a specific entity (Company, Lead, Deal).

**Endpoint:** `GET /drive/{entity_type}/{entity_id}`

**Query Parameters:**
- `page`: int (default: 1)
- `page_size`: int (default: 50)
- `include_deleted`: bool (default: false)

**Response Contract:**

```json
{
  "files": [
    {
      "id": "1234567890abcdef",
      "name": "Project Proposal.pdf",
      "mimeType": "application/pdf",
      "parents": ["folder_id_123"],
      "size": 1024576,
      "createdTime": "2023-10-27T10:00:00Z",
      "webViewLink": "https://drive.google.com/file/d/...",
      "type": "file"
    },
    {
      "id": "folder_id_456",
      "name": "Invoices",
      "mimeType": "application/vnd.google-apps.folder",
      "parents": ["folder_id_123"],
      "size": null,
      "createdTime": "2023-10-26T15:30:00Z",
      "webViewLink": "https://drive.google.com/drive/folders/...",
      "type": "folder"
    }
  ],
  "total": 45,
  "page": 1,
  "page_size": 50,
  "total_pages": 1,
  "permission": "writer"
}
```

### 2. Create Folder

Creates a new subfolder within the entity's root folder.

**Endpoint:** `POST /drive/{entity_type}/{entity_id}/folder`

**Body:**
```json
{
  "name": "New Folder Name"
}
```

**Requirements:**
- Permission: `writer` or `owner`

**Response:**
Returns the Google Drive folder object (JSON).

### 3. Upload File

Uploads a file to the entity's root folder.

**Endpoint:** `POST /drive/{entity_type}/{entity_id}/upload`

**Body:** `multipart/form-data` with field `file`.

**Requirements:**
- Permission: `writer` or `owner`

**Response:**
Returns the Google Drive file object (JSON).

### 4. Soft Delete File

Marks a file as deleted in the database without removing it from Google Drive.

**Endpoint:** `DELETE /drive/{entity_type}/{entity_id}/files/{file_id}`

**Query Parameters:**
- `reason`: string (optional)

**Requirements:**
- Permission: `writer` or `owner`

**Response:**
```json
{
  "status": "deleted",
  "file_id": "file_id_123",
  "deleted_at": "2023-10-27T12:00:00Z",
  "deleted_by": "user_uuid_here"
}
```

### 5. Soft Delete Folder

Marks a folder as deleted in the database without removing it from Google Drive.

**Endpoint:** `DELETE /drive/{entity_type}/{entity_id}/folders/{folder_id}`

**Query Parameters:**
- `reason`: string (optional)

**Requirements:**
- Permission: `writer` or `owner`
- Cannot delete the root entity folder.

**Response:**
Similar to File Delete.

### 6. Search

Advanced search for files and folders across entities (if permitted) or within specific entities.

**Endpoint:** `GET /drive/search`

**Query Parameters:**
- `q`: string (text search)
- `entity_type`: string
- `entity_id`: string
- `mime_type`: string
- `created_from`, `created_to`: ISO 8601 dates
- `page`, `page_size`

**Response:**
Returns a paginated list of items with a similar structure to the List Files endpoint, plus a `permission` field for the context.

### 7. Sync Name

Triggers a sync of the root folder name with the current entity name in the database.

**Endpoint:** `POST /drive/sync-name`

**Body:**
```json
{
  "entity_type": "lead",
  "entity_id": "uuid-here"
}
```

**Response:**
```json
{
  "status": "synced",
  "message": "Folder name synchronization triggered"
}
```

## Entity Support

The API fully supports the following entities:

1. **Company**: Root folder `/Companies/[Name]`
2. **Deal**: Folder `/Companies/[Client]/02. Deals/Deal - [Name]`
3. **Lead**: Folder `/Companies/[Client]/01. Leads/Lead - [Name]`

### Lead Specifics

- **Template**:
  - `00. Administração do Lead`
  - `01. Originação & Materiais`
  - `02. Ativo / Terreno (Básico)`
  - `03. Empreendimento & Viabilidade (Preliminar)`
  - `04. Partes & KYC (Básico)`
  - `05. Decisão Interna`
- **Creation**: Automatic upon first access to `GET /drive/lead/{id}` or via adapter.
- **Naming**: `Lead - [Legal Name]` (or `[Name]` if Legal Name is missing).
