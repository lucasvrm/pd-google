"""
Gmail API Router
Provides read-only endpoints for accessing Gmail messages, threads, and labels.
"""

from fastapi import APIRouter, Depends, HTTPException, Query, Header
from typing import Optional, List
from datetime import datetime

from services.google_gmail_service import GoogleGmailService
from services.permission_service import PermissionService
from utils.structured_logging import StructuredLogger
from schemas.gmail import (
    MessageSummary,
    MessageDetail,
    ThreadSummary,
    ThreadDetail,
    Label,
    MessageListResponse,
    ThreadListResponse,
    LabelListResponse,
    Attachment
)

# Create Gmail-specific structured logger
gmail_logger = StructuredLogger(service="gmail", logger_name="pipedesk_drive.gmail")

router = APIRouter(
    tags=["gmail"]
)


def get_gmail_service():
    """Dependency to get Gmail service instance."""
    return GoogleGmailService()


# Helper functions to transform Gmail API responses to our schemas

def _parse_message_to_summary(
    message_data: dict,
    service: GoogleGmailService
) -> MessageSummary:
    """Convert Gmail API message to MessageSummary schema."""
    # Get message headers
    headers = service._parse_headers(message_data.get('payload', {}).get('headers', []))
    
    # Check for attachments
    attachments = service._extract_attachments(message_data.get('payload', {}))
    has_attachments = len(attachments) > 0
    
    # Parse internal date (milliseconds timestamp)
    internal_date = None
    if 'internalDate' in message_data:
        try:
            internal_date = datetime.fromtimestamp(int(message_data['internalDate']) / 1000)
        except (ValueError, TypeError):
            pass
    
    return MessageSummary(
        id=message_data.get('id', ''),
        thread_id=message_data.get('threadId', ''),
        subject=headers.get('subject'),
        from_email=headers.get('from'),
        to_email=headers.get('to'),
        snippet=message_data.get('snippet'),
        internal_date=internal_date,
        labels=message_data.get('labelIds', []),
        has_attachments=has_attachments
    )


def _parse_message_to_detail(
    message_data: dict,
    service: GoogleGmailService
) -> MessageDetail:
    """Convert Gmail API message to MessageDetail schema."""
    # Get message headers
    headers = service._parse_headers(message_data.get('payload', {}).get('headers', []))
    
    # Extract body content
    plain_text, html_text = service._get_message_body(message_data.get('payload', {}))
    
    # Extract attachments
    attachment_list = service._extract_attachments(message_data.get('payload', {}))
    attachments = [
        Attachment(
            id=att['id'],
            filename=att['filename'],
            mime_type=att['mimeType'],
            size=att['size']
        )
        for att in attachment_list
    ]
    
    # Parse internal date
    internal_date = None
    if 'internalDate' in message_data:
        try:
            internal_date = datetime.fromtimestamp(int(message_data['internalDate']) / 1000)
        except (ValueError, TypeError):
            pass
    
    # Construct web link
    message_id = message_data.get('id', '')
    web_link = f"https://mail.google.com/mail/u/0/#inbox/{message_id}" if message_id else None
    
    return MessageDetail(
        id=message_id,
        thread_id=message_data.get('threadId', ''),
        subject=headers.get('subject'),
        from_email=headers.get('from'),
        to_email=headers.get('to'),
        cc_email=headers.get('cc'),
        bcc_email=headers.get('bcc'),
        snippet=message_data.get('snippet'),
        internal_date=internal_date,
        labels=message_data.get('labelIds', []),
        plain_text_body=plain_text,
        html_body=html_text,
        attachments=attachments,
        web_link=web_link
    )


def _parse_thread_to_summary(
    thread_data: dict,
    service: GoogleGmailService
) -> ThreadSummary:
    """Convert Gmail API thread to ThreadSummary schema."""
    messages = thread_data.get('messages', [])
    message_count = len(messages)
    
    # Get participants from all messages
    participants = set()
    last_date = None
    has_attachments = False
    
    for msg in messages:
        headers = service._parse_headers(msg.get('payload', {}).get('headers', []))
        if headers.get('from'):
            participants.add(headers['from'])
        if headers.get('to'):
            participants.add(headers['to'])
        
        # Check for attachments
        if service._extract_attachments(msg.get('payload', {})):
            has_attachments = True
        
        # Get last message date
        if 'internalDate' in msg:
            try:
                msg_date = datetime.fromtimestamp(int(msg['internalDate']) / 1000)
                if last_date is None or msg_date > last_date:
                    last_date = msg_date
            except (ValueError, TypeError):
                pass
    
    return ThreadSummary(
        id=thread_data.get('id', ''),
        snippet=thread_data.get('snippet'),
        message_count=message_count,
        participants=list(participants),
        last_message_date=last_date,
        labels=messages[-1].get('labelIds', []) if messages else [],
        has_attachments=has_attachments
    )


# API Endpoints

@router.get(
    "/messages",
    response_model=MessageListResponse,
    summary="List Gmail Messages",
    description="Retrieves a list of email messages with optional filtering by search query, labels, date range, and sender/recipient."
)
def list_messages(
    q: Optional[str] = Query(None, description="Gmail search query (e.g., 'from:user@example.com subject:important')"),
    label: Optional[str] = Query(None, description="Filter by label ID or name (e.g., 'INBOX', 'SENT')"),
    from_email: Optional[str] = Query(None, description="Filter messages from this email address"),
    to_email: Optional[str] = Query(None, description="Filter messages to this email address"),
    time_min: Optional[str] = Query(None, description="Filter messages after this date (YYYY-MM-DD)"),
    time_max: Optional[str] = Query(None, description="Filter messages before this date (YYYY-MM-DD)"),
    page_token: Optional[str] = Query(None, description="Token for pagination (from previous response)"),
    page_size: int = Query(50, ge=1, le=100, description="Number of messages per page (max 100)"),
    x_user_role: Optional[str] = Header(None, alias="x-user-role")
):
    """
    List email messages from Gmail.
    
    **Query Parameters:**
    - **q**: Gmail search query using Gmail search syntax
    - **label**: Filter by label ID (e.g., 'INBOX', 'SENT', 'IMPORTANT')
    - **from_email**: Filter messages from specific sender
    - **to_email**: Filter messages to specific recipient
    - **time_min**: Filter messages after this date (YYYY-MM-DD format)
    - **time_max**: Filter messages before this date (YYYY-MM-DD format)
    - **page_token**: Pagination token from previous response
    - **page_size**: Number of results per page (1-100, default: 50)
    
    **Returns:**
    - List of message summaries with pagination information
    - Each message includes: id, subject, from, to, snippet, date, labels, attachment indicator
    
    **Examples:**
    - Search for unread messages: `?q=is:unread`
    - Get messages from specific sender: `?from_email=john@example.com`
    - Get messages with label: `?label=IMPORTANT`
    - Combined filters: `?from_email=john@example.com&time_min=2024-01-01`
    """
    # Check permissions
    permissions = PermissionService.get_permissions_for_role(x_user_role)
    if not permissions.gmail_read_metadata:
        gmail_logger.warning(
            action="list_messages",
            status="forbidden",
            message="Access denied: User does not have permission to read Gmail metadata",
            role=x_user_role or "none"
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied: You do not have permission to read Gmail messages"
        )
    
    service = get_gmail_service()
    
    # Build search query
    query_parts = []
    if q:
        query_parts.append(q)
    if from_email:
        query_parts.append(f"from:{from_email}")
    if to_email:
        query_parts.append(f"to:{to_email}")
    if time_min:
        query_parts.append(f"after:{time_min}")
    if time_max:
        query_parts.append(f"before:{time_max}")
    
    search_query = " ".join(query_parts) if query_parts else None
    
    # Handle label filter
    label_ids = [label] if label else None
    
    try:
        # Get messages list
        result = service.list_messages(
            query=search_query,
            label_ids=label_ids,
            max_results=page_size,
            page_token=page_token
        )
        
        messages = []
        # Fetch full details for each message to populate summary
        for msg_ref in result.get('messages', []):
            msg_data = service.get_message(msg_ref['id'], format='full')
            messages.append(_parse_message_to_summary(msg_data, service))
        
        gmail_logger.info(
            action="list_messages",
            status="success",
            message=f"Listed {len(messages)} messages",
            result_count=len(messages),
            page_size=page_size,
            has_next_page=bool(result.get('nextPageToken'))
        )
        
        return MessageListResponse(
            messages=messages,
            next_page_token=result.get('nextPageToken'),
            result_size_estimate=result.get('resultSizeEstimate')
        )
    
    except Exception as e:
        gmail_logger.error(
            action="list_messages",
            message="Failed to list messages",
            error=e
        )
        raise HTTPException(status_code=500, detail=f"Failed to list messages: {str(e)}")


@router.get(
    "/messages/{message_id}",
    response_model=MessageDetail,
    summary="Get Message Details",
    description="Retrieves complete details of a specific email message including body content and attachments."
)
def get_message(
    message_id: str,
    x_user_role: Optional[str] = Header(None, alias="x-user-role")
):
    """
    Get detailed information about a specific email message.
    
    **Parameters:**
    - **message_id**: Gmail message ID
    
    **Returns:**
    - Complete message details including:
      - All header fields (from, to, cc, bcc, subject)
      - Message body in both plain text and HTML formats
      - List of attachments with metadata
      - Labels applied to the message
      - Web link to view in Gmail UI
      - Internal date and snippet
    
    **Note:**
    - The HTML body is returned as-is from Gmail. Frontend should sanitize before rendering.
    - Attachment content is not included; use the attachment ID to download separately if needed.
    """
    # Check permissions
    permissions = PermissionService.get_permissions_for_role(x_user_role)
    if not permissions.gmail_read_metadata:
        gmail_logger.warning(
            action="get_message",
            status="forbidden",
            message=f"Access denied: User does not have permission to read Gmail metadata for message {message_id}",
            role=x_user_role or "none",
            message_id=message_id
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied: You do not have permission to read Gmail messages"
        )
    
    service = get_gmail_service()
    
    try:
        message_data = service.get_message(message_id, format='full')
        message_detail = _parse_message_to_detail(message_data, service)
        
        # Redact body if user doesn't have permission to read it
        if not permissions.gmail_read_body:
            message_detail.plain_text_body = None
            message_detail.html_body = None
            
            gmail_logger.info(
                action="get_message",
                status="success_redacted",
                message=f"Retrieved message {message_id} (body redacted)",
                message_id=message_id,
                role=x_user_role or "none"
            )
        else:
            gmail_logger.info(
                action="get_message",
                status="success",
                message=f"Retrieved message {message_id}",
                message_id=message_id,
                role=x_user_role or "none"
            )
        
        return message_detail
    
    except Exception as e:
        if "404" in str(e) or "not found" in str(e).lower():
            gmail_logger.warning(
                action="get_message",
                status="not_found",
                message=f"Message {message_id} not found",
                message_id=message_id
            )
            raise HTTPException(status_code=404, detail=f"Message {message_id} not found")
        
        gmail_logger.error(
            action="get_message",
            message=f"Failed to get message {message_id}",
            error=e,
            message_id=message_id
        )
        raise HTTPException(status_code=500, detail=f"Failed to get message: {str(e)}")


@router.get(
    "/threads",
    response_model=ThreadListResponse,
    summary="List Email Threads",
    description="Retrieves a list of email threads (conversations) with optional filtering."
)
def list_threads(
    q: Optional[str] = Query(None, description="Gmail search query"),
    label: Optional[str] = Query(None, description="Filter by label ID"),
    page_token: Optional[str] = Query(None, description="Token for pagination"),
    page_size: int = Query(50, ge=1, le=100, description="Number of threads per page (max 100)"),
    x_user_role: Optional[str] = Header(None, alias="x-user-role")
):
    """
    List email threads (conversations) from Gmail.
    
    **Query Parameters:**
    - **q**: Gmail search query using Gmail search syntax
    - **label**: Filter by label ID (e.g., 'INBOX', 'SENT')
    - **page_token**: Pagination token from previous response
    - **page_size**: Number of results per page (1-100, default: 50)
    
    **Returns:**
    - List of thread summaries with:
      - Thread ID
      - Snippet from the latest message
      - Message count in the thread
      - List of participants
      - Date of last activity
      - Labels and attachment indicator
    
    **Examples:**
    - Get inbox threads: `?label=INBOX`
    - Search in threads: `?q=important project`
    """
    # Check permissions
    permissions = PermissionService.get_permissions_for_role(x_user_role)
    if not permissions.gmail_read_metadata:
        gmail_logger.warning(
            action="list_threads",
            status="forbidden",
            message="Access denied: User does not have permission to read Gmail metadata",
            role=x_user_role or "none"
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied: You do not have permission to read Gmail threads"
        )
    
    service = get_gmail_service()
    
    label_ids = [label] if label else None
    
    try:
        # Get threads list
        result = service.list_threads(
            query=q,
            label_ids=label_ids,
            max_results=page_size,
            page_token=page_token
        )
        
        threads = []
        # Fetch full details for each thread
        for thread_ref in result.get('threads', []):
            thread_data = service.get_thread(thread_ref['id'], format='metadata')
            threads.append(_parse_thread_to_summary(thread_data, service))
        
        gmail_logger.info(
            action="list_threads",
            status="success",
            message=f"Listed {len(threads)} threads",
            result_count=len(threads),
            page_size=page_size,
            has_next_page=bool(result.get('nextPageToken'))
        )
        
        return ThreadListResponse(
            threads=threads,
            next_page_token=result.get('nextPageToken'),
            result_size_estimate=result.get('resultSizeEstimate')
        )
    
    except Exception as e:
        gmail_logger.error(
            action="list_threads",
            message="Failed to list threads",
            error=e
        )
        raise HTTPException(status_code=500, detail=f"Failed to list threads: {str(e)}")


@router.get(
    "/threads/{thread_id}",
    response_model=ThreadDetail,
    summary="Get Thread Details",
    description="Retrieves complete details of a specific email thread including all messages."
)
def get_thread(
    thread_id: str,
    x_user_role: Optional[str] = Header(None, alias="x-user-role")
):
    """
    Get detailed information about a specific email thread.
    
    **Parameters:**
    - **thread_id**: Gmail thread ID
    
    **Returns:**
    - Complete thread details including:
      - List of all messages in the thread (as MessageSummary objects)
      - Thread snippet
      - Thread ID
    
    **Note:**
    - Messages are returned in chronological order
    - Each message includes basic information (subject, from, to, snippet, etc.)
    - For full message details including body, use the GET /messages/{id} endpoint
    """
    # Check permissions
    permissions = PermissionService.get_permissions_for_role(x_user_role)
    if not permissions.gmail_read_metadata:
        gmail_logger.warning(
            action="get_thread",
            status="forbidden",
            message=f"Access denied: User does not have permission to read Gmail metadata for thread {thread_id}",
            role=x_user_role or "none",
            thread_id=thread_id
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied: You do not have permission to read Gmail threads"
        )
    
    service = get_gmail_service()
    
    try:
        thread_data = service.get_thread(thread_id, format='full')
        
        # Parse messages in the thread
        messages = []
        for msg in thread_data.get('messages', []):
            messages.append(_parse_message_to_summary(msg, service))
        
        gmail_logger.info(
            action="get_thread",
            status="success",
            message=f"Retrieved thread {thread_id}",
            thread_id=thread_id,
            message_count=len(messages)
        )
        
        return ThreadDetail(
            id=thread_data.get('id', ''),
            messages=messages,
            snippet=thread_data.get('snippet')
        )
    
    except Exception as e:
        if "404" in str(e) or "not found" in str(e).lower():
            gmail_logger.warning(
                action="get_thread",
                status="not_found",
                message=f"Thread {thread_id} not found",
                thread_id=thread_id
            )
            raise HTTPException(status_code=404, detail=f"Thread {thread_id} not found")
        
        gmail_logger.error(
            action="get_thread",
            message=f"Failed to get thread {thread_id}",
            error=e,
            thread_id=thread_id
        )
        raise HTTPException(status_code=500, detail=f"Failed to get thread: {str(e)}")


@router.get(
    "/labels",
    response_model=LabelListResponse,
    summary="List Gmail Labels",
    description="Retrieves all labels from the user's Gmail account including system and custom labels."
)
def list_labels():
    """
    List all Gmail labels.
    
    **Returns:**
    - List of all labels including:
      - Label ID (used for filtering messages/threads)
      - Label name (display name)
      - Label type (system or user)
      - Visibility settings
    
    **System Labels:**
    - INBOX, SENT, DRAFT, SPAM, TRASH, IMPORTANT, STARRED, UNREAD, etc.
    
    **User Labels:**
    - Custom labels created by the user
    
    **Note:**
    - Use the label ID (not name) when filtering messages or threads
    - System label IDs are uppercase (e.g., 'INBOX')
    - User label IDs are alphanumeric strings
    """
    service = get_gmail_service()
    
    try:
        result = service.list_labels()
        
        labels = []
        for label_data in result.get('labels', []):
            labels.append(Label(
                id=label_data.get('id', ''),
                name=label_data.get('name', ''),
                type=label_data.get('type'),
                message_list_visibility=label_data.get('messageListVisibility'),
                label_list_visibility=label_data.get('labelListVisibility')
            ))
        
        gmail_logger.info(
            action="list_labels",
            status="success",
            message=f"Listed {len(labels)} labels",
            label_count=len(labels)
        )
        
        return LabelListResponse(labels=labels)
    
    except Exception as e:
        gmail_logger.error(
            action="list_labels",
            message="Failed to list labels",
            error=e
        )
        raise HTTPException(status_code=500, detail=f"Failed to list labels: {str(e)}")
