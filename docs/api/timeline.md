# Timeline API

Prefix: `/api/timeline`

## Endpoint
- `GET /{entity_type}/{entity_id}` – Returns a paginated feed combining Calendar events, Gmail messages, and audit logs related to a lead, deal, or contact. Query parameters include `limit`, `offset`, and entity metadata to refine matching.

The router normalizes timestamps, attaches user info, and orders items by recency. Gmail fetching relies on company/lead contact emails and falls back gracefully if Gmail access fails.
