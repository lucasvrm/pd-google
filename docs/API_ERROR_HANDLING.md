# API Error Handling Contract

All endpoints under `/api` return standardized JSON error envelopes. HTML pages or non-API routes keep their existing behavior.

## Envelope shape

```json
{
  "error": "Human-friendly summary of what went wrong",
  "code": "machine_readable_code",
  "message": "Same human-friendly summary",
  "details": {} | [] | null
}
```

- **error**: mirrors the human-readable message for quick debugging.
- **message**: identical to `error` for compatibility with clients that expect a `message` field.
- **code**: stable identifier derived from the HTTP status or domain-specific errors.
- **details** (optional): structured context (e.g., Pydantic validation errors).

## Common codes

| HTTP status | `code`                | Notes                                         |
|-------------|-----------------------|-----------------------------------------------|
| 400         | `bad_request`         | Invalid parameters or malformed requests.     |
| 401         | `unauthorized`        | Missing/invalid credentials for `/api`.       |
| 403         | `forbidden`           | Authenticated but not allowed.                |
| 404         | `not_found`           | Resource not found.                           |
| 409         | `conflict`            | Conflict/duplication semantics.               |
| 422         | `validation_error`    | Pydantic/request validation failures.         |
| 429         | `too_many_requests`   | Rate limiting.                                |
| 5xx         | `internal_server_error` | Unexpected/unhandled exceptions.              |
| Domain      | `sales_view_error`    | Sales View specific internal failures.        |

## Examples

### Validation error (422)

```json
{
  "error": "Validation error",
  "code": "validation_error",
  "message": "Validation error",
  "details": [
    {
      "loc": ["query", "page"],
      "msg": "page must be >= 1",
      "type": "value_error"
    }
  ]
}
```

### HTTP error converted from `HTTPException`

```json
{
  "error": "Invalid entity_type. Allowed: ['company', 'lead', 'deal']",
  "code": "bad_request",
  "message": "Invalid entity_type. Allowed: ['company', 'lead', 'deal']"
}
```

### Forbidden

```json
{
  "error": "Access denied: insufficient permissions",
  "code": "forbidden",
  "message": "Access denied: insufficient permissions"
}
```

### Internal server error (fallback)

```json
{
  "error": "An unexpected error occurred",
  "code": "internal_server_error",
  "message": "An unexpected error occurred"
}
```

## Scope and compatibility

- The normalization is applied exclusively to `/api` routes. HTML pages and other callbacks are untouched.
- The original HTTP status code is preserved.
- Existing Sales View responses continue to emit `sales_view_error` for domain failures.
