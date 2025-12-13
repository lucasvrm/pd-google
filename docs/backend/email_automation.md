# Email Automation API

## Overview

The Email Automation service provides endpoints for automatically processing Gmail attachments and saving them to a Lead's Google Drive folder. This feature enables sales teams to organize email attachments without manual effort.

## Architecture

```
┌─────────────────┐     ┌──────────────────────┐     ┌────────────────┐
│   API Request   │────▶│ EmailAutomationService│────▶│  Google Drive  │
│ (manual/webhook)│     │                      │     │                │
└─────────────────┘     └──────────────────────┘     └────────────────┘
                                │
                                ▼
                        ┌──────────────────┐
                        │    Gmail API     │
                        │ (read message &  │
                        │   attachments)   │
                        └──────────────────┘
```

## Components

### EmailAutomationService

Located in `services/email_automation_service.py`, this service handles:

1. **Message Processing**: Fetches email details from Gmail API
2. **Attachment Extraction**: Identifies MIME parts with attachmentId
3. **Folder Resolution**: Uses HierarchyService to get/create Lead's Drive folder
4. **Stream Upload**: Downloads attachment from Gmail and uploads directly to Drive (no disk I/O)
5. **Audit Logging**: Creates audit log entries for traceability

### Automation Router

Located in `routers/automation.py`, provides two endpoints:

- `POST /api/automation/scan-email/{message_id}` - Process single email
- `POST /api/automation/scan-lead-emails` - Batch process emails from an address

## API Endpoints

### 1. Scan Email for Attachments

Process attachments from a specific Gmail message and save them to a Lead's Drive folder.

**Endpoint:** `POST /api/automation/scan-email/{message_id}`

**Path Parameters:**
- `message_id` (string, required): Gmail message ID

**Request Body:**
```json
{
  "lead_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response:**
```json
{
  "message_id": "18c5a3b2f1e4d6c9",
  "lead_id": "550e8400-e29b-41d4-a716-446655440000",
  "attachments_processed": 2,
  "attachments_saved": [
    {
      "filename": "proposal.pdf",
      "file_id": "1abc123def456",
      "web_view_link": "https://drive.google.com/file/d/1abc123def456/view",
      "size": 245678,
      "mime_type": "application/pdf"
    },
    {
      "filename": "contract.docx",
      "file_id": "2xyz789ghi012",
      "web_view_link": "https://drive.google.com/file/d/2xyz789ghi012/view",
      "size": 123456,
      "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    }
  ],
  "errors": []
}
```

**Headers Required:**
- `x-user-role`: User role for permission check (minimum: sales)
- `x-user-id`: User ID for audit logging

### 2. Scan Lead's Emails

Batch process multiple emails from a specific email address.

**Endpoint:** `POST /api/automation/scan-lead-emails`

**Request Body:**
```json
{
  "lead_id": "550e8400-e29b-41d4-a716-446655440000",
  "email_address": "client@company.com",
  "max_messages": 10
}
```

**Response:**
```json
{
  "lead_id": "550e8400-e29b-41d4-a716-446655440000",
  "email_address": "client@company.com",
  "messages_scanned": 8,
  "messages_with_attachments": 3,
  "total_attachments_saved": 5,
  "errors": []
}
```

## Audit Logging

Every attachment saved creates an audit log entry with:

- `entity_type`: "lead"
- `entity_id`: Lead's UUID
- `action`: "attachment_autosave"
- `changes`: JSON containing:
  - `message_id`: Gmail message ID
  - `filename`: Attachment filename
  - `file_id`: Drive file ID
  - `mime_type`: File MIME type
  - `size`: File size in bytes

## Error Handling

The service handles errors gracefully:

1. **Lead Not Found**: Returns error in response, does not fail entire request
2. **Attachment Download Failed**: Logs error, continues with other attachments
3. **Drive Upload Failed**: Logs error, continues with other attachments
4. **Gmail API Errors**: Retried with exponential backoff (3 retries)

## Integration Points

### Gmail Push Webhooks (Future)

When Gmail Push notifications are configured, the webhook handler in `routers/webhooks.py` can trigger `EmailAutomationService.process_message_attachments()` in a background task.

### Background Workers (Future)

For scheduled processing, add a worker that:
1. Queries leads with known email addresses
2. Calls `scan_and_process_lead_emails()` periodically

## Security Considerations

1. **Permissions**: Requires `gmail_read_metadata` permission (sales role or above)
2. **No Disk I/O**: Attachments are streamed from Gmail to Drive without saving to disk
3. **Audit Trail**: All operations are logged for compliance

## Configuration

No additional configuration required. Uses existing:
- `GOOGLE_SERVICE_ACCOUNT_JSON` for Google API authentication
- Database connection for Lead folder mappings

## Testing

Run tests with:
```bash
pytest tests/test_email_automation.py -v
```

## Usage Examples

### Python Client
```python
import requests

# Process single email
response = requests.post(
    "https://api.example.com/api/automation/scan-email/18c5a3b2f1e4d6c9",
    json={"lead_id": "550e8400-e29b-41d4-a716-446655440000"},
    headers={
        "x-user-role": "sales",
        "x-user-id": "user-uuid-here"
    }
)
print(response.json())
```

### cURL
```bash
curl -X POST \
  'https://api.example.com/api/automation/scan-email/18c5a3b2f1e4d6c9' \
  -H 'Content-Type: application/json' \
  -H 'x-user-role: sales' \
  -H 'x-user-id: user-uuid-here' \
  -d '{"lead_id": "550e8400-e29b-41d4-a716-446655440000"}'
```

## Troubleshooting

### Common Issues

1. **"Failed to resolve Lead folder"**
   - Ensure the lead_id exists in the database
   - Check that the lead has a qualified_company_id set

2. **"Empty attachment data"**
   - Gmail API may return empty data for very large attachments
   - Check attachment size limits (25MB for Gmail)

3. **"Access denied"**
   - Verify the x-user-role header is set
   - Ensure user has at least sales role

### Logging

The service uses structured logging with:
- Logger name: `pipedesk_drive.email_automation`
- Key actions logged: `scan_email`, `scan_lead_emails`

## Future Enhancements

- [ ] Smart file organization (subfolder by date/type)
- [ ] Attachment preview in timeline
- [ ] Gmail Push webhook integration for real-time processing
- [ ] Duplicate detection (avoid re-uploading same file)
- [ ] File type filtering (only save specific MIME types)
