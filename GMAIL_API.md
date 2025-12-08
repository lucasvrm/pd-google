# Gmail API Documentation

## Overview

The Gmail API integration provides read-only access to email data through a RESTful API. This API allows frontend applications to retrieve messages, threads, and labels from Gmail accounts.

**Key Features:**
- Read-only access (no email sending or modification)
- Message listing with advanced filtering
- Thread (conversation) management
- Label management
- Full message details including attachments metadata
- Pagination support for large result sets

**Authentication:**
- Uses Google Service Account authentication
- Requires Gmail read-only scope: `https://www.googleapis.com/auth/gmail.readonly`

## Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/api/gmail/messages` | List email messages with filtering |
| GET | `/api/gmail/messages/{id}` | Get detailed information about a specific message |
| GET | `/api/gmail/threads` | List email threads (conversations) |
| GET | `/api/gmail/threads/{id}` | Get detailed information about a specific thread |
| GET | `/api/gmail/labels` | List all Gmail labels |

---

## Endpoint Details

### GET /api/gmail/messages

Retrieves a list of email messages with optional filtering.

**Query Parameters:**

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `q` | string | No | Gmail search query | `is:unread` |
| `label` | string | No | Filter by label ID | `INBOX` |
| `from_email` | string | No | Filter by sender email | `john@example.com` |
| `to_email` | string | No | Filter by recipient email | `team@company.com` |
| `time_min` | string | No | Filter messages after date (YYYY-MM-DD) | `2024-01-01` |
| `time_max` | string | No | Filter messages before date (YYYY-MM-DD) | `2024-12-31` |
| `page_token` | string | No | Pagination token from previous response | `ABC123...` |
| `page_size` | integer | No | Number of results per page (1-100, default: 50) | `25` |

**Response Schema:**

```json
{
  "messages": [
    {
      "id": "18b2f3a8d4c5e1f2",
      "thread_id": "18b2f3a8d4c5e1f2",
      "subject": "Q4 Sales Report",
      "from_email": "john@company.com",
      "to_email": "team@company.com",
      "snippet": "Please find attached the Q4 sales report for your review...",
      "internal_date": "2024-01-15T14:30:00Z",
      "labels": ["INBOX", "IMPORTANT"],
      "has_attachments": true
    }
  ],
  "next_page_token": "ABC123...",
  "result_size_estimate": 150
}
```

**Example Request:**

```bash
# Get unread messages from inbox
curl -X GET "http://localhost:8000/api/gmail/messages?q=is:unread&label=INBOX&page_size=20"

# Get messages from a specific sender
curl -X GET "http://localhost:8000/api/gmail/messages?from_email=john@example.com"

# Get messages within a date range
curl -X GET "http://localhost:8000/api/gmail/messages?time_min=2024-01-01&time_max=2024-01-31"

# Pagination example
curl -X GET "http://localhost:8000/api/gmail/messages?page_size=50&page_token=ABC123..."
```

---

### GET /api/gmail/messages/{id}

Retrieves complete details of a specific email message.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | Gmail message ID |

**Response Schema:**

```json
{
  "id": "18b2f3a8d4c5e1f2",
  "thread_id": "18b2f3a8d4c5e1f2",
  "subject": "Q4 Sales Report",
  "from_email": "john@company.com",
  "to_email": "team@company.com",
  "cc_email": "manager@company.com",
  "bcc_email": null,
  "snippet": "Please find attached the Q4 sales report...",
  "internal_date": "2024-01-15T14:30:00Z",
  "labels": ["INBOX", "IMPORTANT"],
  "plain_text_body": "Please find attached the Q4 sales report for your review.\n\nBest regards,\nJohn",
  "html_body": "<p>Please find attached the Q4 sales report for your review.</p><p>Best regards,<br>John</p>",
  "attachments": [
    {
      "id": "ANGjdJ9qvx...",
      "filename": "Q4_Sales_Report.pdf",
      "mime_type": "application/pdf",
      "size": 245678
    }
  ],
  "web_link": "https://mail.google.com/mail/u/0/#inbox/18b2f3a8d4c5e1f2"
}
```

**Example Request:**

```bash
curl -X GET "http://localhost:8000/api/gmail/messages/18b2f3a8d4c5e1f2"
```

**Notes:**
- The `html_body` field contains raw HTML. Frontend should sanitize before rendering.
- Attachments include metadata only. To download attachment content, you would need to implement a separate endpoint (not included in read-only scope).
- The `web_link` provides a direct link to view the message in Gmail's web interface.

---

### GET /api/gmail/threads

Retrieves a list of email threads (conversations).

**Query Parameters:**

| Parameter | Type | Required | Description | Example |
|-----------|------|----------|-------------|---------|
| `q` | string | No | Gmail search query | `important project` |
| `label` | string | No | Filter by label ID | `INBOX` |
| `page_token` | string | No | Pagination token | `ABC123...` |
| `page_size` | integer | No | Results per page (1-100, default: 50) | `25` |

**Response Schema:**

```json
{
  "threads": [
    {
      "id": "18b2f3a8d4c5e1f2",
      "snippet": "Great! Let's schedule a follow-up meeting...",
      "message_count": 5,
      "participants": ["john@company.com", "jane@company.com", "bob@company.com"],
      "last_message_date": "2024-01-15T16:45:00Z",
      "labels": ["INBOX"],
      "has_attachments": true
    }
  ],
  "next_page_token": "XYZ789...",
  "result_size_estimate": 42
}
```

**Example Request:**

```bash
# Get inbox threads
curl -X GET "http://localhost:8000/api/gmail/threads?label=INBOX&page_size=20"

# Search in threads
curl -X GET "http://localhost:8000/api/gmail/threads?q=important+meeting"
```

---

### GET /api/gmail/threads/{id}

Retrieves complete details of a specific email thread including all messages.

**Path Parameters:**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | Gmail thread ID |

**Response Schema:**

```json
{
  "id": "18b2f3a8d4c5e1f2",
  "snippet": "Great! Let's schedule a follow-up meeting...",
  "messages": [
    {
      "id": "18b2f3a8d4c5e1f2",
      "thread_id": "18b2f3a8d4c5e1f2",
      "subject": "Q4 Sales Report",
      "from_email": "john@company.com",
      "to_email": "team@company.com",
      "snippet": "Please find attached...",
      "internal_date": "2024-01-15T14:30:00Z",
      "labels": ["INBOX"],
      "has_attachments": true
    },
    {
      "id": "18b2f3a8d4c5e1f3",
      "thread_id": "18b2f3a8d4c5e1f2",
      "subject": "Re: Q4 Sales Report",
      "from_email": "jane@company.com",
      "to_email": "john@company.com",
      "snippet": "Thanks for the report...",
      "internal_date": "2024-01-15T15:30:00Z",
      "labels": ["INBOX"],
      "has_attachments": false
    }
  ]
}
```

**Example Request:**

```bash
curl -X GET "http://localhost:8000/api/gmail/threads/18b2f3a8d4c5e1f2"
```

**Notes:**
- Messages are returned in chronological order
- Each message in the thread is returned as a MessageSummary (without body content)
- To get full message details including body, use GET /api/gmail/messages/{id}

---

### GET /api/gmail/labels

Retrieves all labels from the user's Gmail account.

**Response Schema:**

```json
{
  "labels": [
    {
      "id": "INBOX",
      "name": "INBOX",
      "type": "system",
      "message_list_visibility": "show",
      "label_list_visibility": "labelShow"
    },
    {
      "id": "Label_1",
      "name": "Work Projects",
      "type": "user",
      "message_list_visibility": "show",
      "label_list_visibility": "labelShow"
    }
  ]
}
```

**Example Request:**

```bash
curl -X GET "http://localhost:8000/api/gmail/labels"
```

**Common System Labels:**
- `INBOX` - Inbox messages
- `SENT` - Sent messages
- `DRAFT` - Draft messages
- `SPAM` - Spam messages
- `TRASH` - Deleted messages
- `IMPORTANT` - Important messages
- `STARRED` - Starred messages
- `UNREAD` - Unread messages

---

## Gmail Search Query Syntax

The `q` parameter supports Gmail's powerful search syntax:

| Query | Description |
|-------|-------------|
| `from:user@example.com` | Messages from specific sender |
| `to:user@example.com` | Messages to specific recipient |
| `subject:meeting` | Messages with "meeting" in subject |
| `is:unread` | Unread messages |
| `is:starred` | Starred messages |
| `has:attachment` | Messages with attachments |
| `after:2024/01/01` | Messages after date |
| `before:2024/12/31` | Messages before date |
| `filename:pdf` | Messages with PDF attachments |
| `label:important` | Messages with specific label |

**Combining Queries:**
```
from:john@example.com has:attachment after:2024/01/01
```

---

## Pagination

All list endpoints support pagination to handle large result sets efficiently.

**How to use:**
1. Make initial request without `page_token`
2. Check response for `next_page_token`
3. If present, use it in the next request as `page_token` parameter
4. Repeat until `next_page_token` is null

**Example:**
```bash
# First request
curl -X GET "http://localhost:8000/api/gmail/messages?page_size=50"

# Response includes: "next_page_token": "ABC123..."

# Next page request
curl -X GET "http://localhost:8000/api/gmail/messages?page_size=50&page_token=ABC123..."
```

---

## Error Responses

All endpoints may return the following error responses:

| Status Code | Description |
|-------------|-------------|
| 400 | Bad Request - Invalid parameters |
| 404 | Not Found - Message/Thread not found |
| 500 | Internal Server Error - Gmail API error or authentication failure |

**Error Response Schema:**
```json
{
  "detail": "Error message describing what went wrong"
}
```

---

## Usage Examples

### Frontend Integration Example (JavaScript)

```javascript
// Fetch inbox messages
async function getInboxMessages(pageSize = 20) {
  const response = await fetch(
    `http://localhost:8000/api/gmail/messages?label=INBOX&page_size=${pageSize}`
  );
  const data = await response.json();
  return data;
}

// Get unread messages from specific sender
async function getUnreadFromSender(email) {
  const query = encodeURIComponent(`from:${email} is:unread`);
  const response = await fetch(
    `http://localhost:8000/api/gmail/messages?q=${query}`
  );
  const data = await response.json();
  return data;
}

// Get message details
async function getMessageDetails(messageId) {
  const response = await fetch(
    `http://localhost:8000/api/gmail/messages/${messageId}`
  );
  const data = await response.json();
  return data;
}

// Get thread with all messages
async function getThreadMessages(threadId) {
  const response = await fetch(
    `http://localhost:8000/api/gmail/threads/${threadId}`
  );
  const data = await response.json();
  return data;
}

// Get all labels
async function getLabels() {
  const response = await fetch(
    `http://localhost:8000/api/gmail/labels`
  );
  const data = await response.json();
  return data.labels;
}
```

---

## Security Considerations

1. **Read-Only Access**: This API only provides read access. No modifications to Gmail data are possible.

2. **HTML Content**: The `html_body` field in message details contains raw HTML. Always sanitize HTML content before rendering in the frontend to prevent XSS attacks.

3. **Authentication**: Requires valid Google Service Account credentials with Gmail API access.

4. **Rate Limiting**: Gmail API has quota limits. Implement appropriate caching and rate limiting in your frontend application.

---

## Future Enhancements

The following features are not currently implemented but could be added:

- Attachment download endpoint
- Message modification (mark as read/unread, add/remove labels)
- Email sending capabilities
- Draft management
- Search suggestions
- Email filtering and rules management
