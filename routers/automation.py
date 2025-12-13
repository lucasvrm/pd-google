"""
Email Automation Router - Provides endpoints for email automation operations.

Endpoints:
- POST /api/automation/scan-email/{message_id} - Process attachments from a specific email
"""

from fastapi import APIRouter, Depends, HTTPException, Header, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Optional, List
from pydantic import BaseModel, Field

from database import get_db
from services.email_automation_service import EmailAutomationService
from services.permission_service import PermissionService
from utils.structured_logging import StructuredLogger

# Create automation-specific structured logger
automation_logger = StructuredLogger(service="email_automation", logger_name="pipedesk_drive.automation")

router = APIRouter(
    prefix="/api/automation",
    tags=["automation"]
)


# Request/Response Schemas

class ScanEmailRequest(BaseModel):
    """Request body for scanning an email for attachments."""
    lead_id: str = Field(..., description="UUID of the Lead to save attachments to")


class AttachmentSavedInfo(BaseModel):
    """Information about a saved attachment."""
    filename: str
    file_id: str
    web_view_link: Optional[str] = None
    size: int
    mime_type: str


class ScanEmailResponse(BaseModel):
    """Response from scanning an email for attachments."""
    message_id: str
    lead_id: str
    attachments_processed: int
    attachments_saved: List[AttachmentSavedInfo]
    errors: List[str]


class ScanLeadEmailsRequest(BaseModel):
    """Request body for scanning emails from a lead's email address."""
    lead_id: str = Field(..., description="UUID of the Lead")
    email_address: str = Field(..., description="Email address to search for")
    max_messages: int = Field(10, ge=1, le=50, description="Maximum number of messages to process")


class ScanLeadEmailsResponse(BaseModel):
    """Response from scanning lead's emails."""
    lead_id: str
    email_address: str
    messages_scanned: int
    messages_with_attachments: int
    total_attachments_saved: int
    errors: List[str]


# API Endpoints

@router.post(
    "/scan-email/{message_id}",
    response_model=ScanEmailResponse,
    summary="Scan Email for Attachments",
    description="Processes attachments from a specific Gmail message and saves them to a Lead's Drive folder."
)
def scan_email_attachments(
    message_id: str,
    request: ScanEmailRequest,
    db: Session = Depends(get_db),
    x_user_id: Optional[str] = Header(None, alias="x-user-id"),
    x_user_role: Optional[str] = Header(None, alias="x-user-role")
):
    """
    Process attachments from a specific Gmail message and save them to a Lead's Drive folder.

    **Parameters:**
    - **message_id**: Gmail message ID to process (path parameter)
    - **lead_id**: UUID of the Lead to save attachments to (in request body)

    **Process:**
    1. Fetches the email message from Gmail
    2. Identifies all attachments (MIME parts with attachmentId)
    3. Resolves the Lead's Drive folder via HierarchyService
    4. Downloads each attachment from Gmail
    5. Uploads each attachment directly to the Lead's Drive folder
    6. Creates an AuditLog entry for each attachment saved (action="attachment_autosave")

    **Returns:**
    - Summary of processing including attachments saved and any errors

    **Required Permissions:**
    - Must have write access to Drive (sales role or above)
    """
    # Check permissions - require at least sales role to trigger automation
    permissions = PermissionService.get_permissions_for_role(x_user_role)
    if not permissions.gmail_read_metadata:
        automation_logger.warning(
            action="scan_email",
            status="forbidden",
            message=f"Access denied: User does not have permission to trigger email automation",
            role=x_user_role or "none",
            message_id=message_id
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied: You do not have permission to trigger email automation"
        )

    automation_logger.info(
        action="scan_email",
        status="started",
        message=f"Processing attachments for message {message_id} -> lead {request.lead_id}",
        message_id=message_id,
        lead_id=request.lead_id,
        user_id=x_user_id
    )

    try:
        service = EmailAutomationService(db)
        result = service.process_message_attachments(
            message_id=message_id,
            lead_id=request.lead_id,
            actor_id=x_user_id
        )

        # Convert result to response model
        attachments_saved = [
            AttachmentSavedInfo(
                filename=att["filename"],
                file_id=att["file_id"],
                web_view_link=att.get("web_view_link"),
                size=att["size"],
                mime_type=att["mime_type"]
            )
            for att in result.get("attachments_saved", [])
        ]

        response = ScanEmailResponse(
            message_id=result["message_id"],
            lead_id=result["lead_id"],
            attachments_processed=result["attachments_processed"],
            attachments_saved=attachments_saved,
            errors=result.get("errors", [])
        )

        automation_logger.info(
            action="scan_email",
            status="success",
            message=f"Processed {response.attachments_processed} attachments, saved {len(response.attachments_saved)}",
            message_id=message_id,
            lead_id=request.lead_id,
            attachments_processed=response.attachments_processed,
            attachments_saved=len(response.attachments_saved),
            errors=len(response.errors)
        )

        return response

    except Exception as e:
        automation_logger.error(
            action="scan_email",
            message=f"Failed to process email {message_id}",
            error=e,
            message_id=message_id,
            lead_id=request.lead_id
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process email attachments: {str(e)}"
        )


@router.post(
    "/scan-lead-emails",
    response_model=ScanLeadEmailsResponse,
    summary="Scan Lead's Emails for Attachments",
    description="Scans recent emails from a Lead's email address and saves attachments to their Drive folder."
)
def scan_lead_emails(
    request: ScanLeadEmailsRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    x_user_id: Optional[str] = Header(None, alias="x-user-id"),
    x_user_role: Optional[str] = Header(None, alias="x-user-role")
):
    """
    Scan recent emails from a specific email address and save attachments to a Lead's Drive folder.

    **Parameters:**
    - **lead_id**: UUID of the Lead
    - **email_address**: Email address to search for
    - **max_messages**: Maximum number of messages to process (1-50, default: 10)

    **Process:**
    1. Searches Gmail for messages from the specified email address that have attachments
    2. For each message found, processes all attachments
    3. Saves attachments to the Lead's Drive folder
    4. Creates audit log entries for each attachment saved

    **Returns:**
    - Summary of processing including total attachments saved and any errors

    **Required Permissions:**
    - Must have write access to Drive (sales role or above)
    """
    # Check permissions
    permissions = PermissionService.get_permissions_for_role(x_user_role)
    if not permissions.gmail_read_metadata:
        automation_logger.warning(
            action="scan_lead_emails",
            status="forbidden",
            message=f"Access denied: User does not have permission to trigger email automation",
            role=x_user_role or "none",
            lead_id=request.lead_id
        )
        raise HTTPException(
            status_code=403,
            detail="Access denied: You do not have permission to trigger email automation"
        )

    automation_logger.info(
        action="scan_lead_emails",
        status="started",
        message=f"Scanning emails from {request.email_address} for lead {request.lead_id}",
        lead_id=request.lead_id,
        email_address=request.email_address,
        max_messages=request.max_messages,
        user_id=x_user_id
    )

    try:
        service = EmailAutomationService(db)
        result = service.scan_and_process_lead_emails(
            lead_id=request.lead_id,
            email_address=request.email_address,
            max_messages=request.max_messages,
            actor_id=x_user_id
        )

        response = ScanLeadEmailsResponse(
            lead_id=result["lead_id"],
            email_address=result["email_address"],
            messages_scanned=result["messages_scanned"],
            messages_with_attachments=result["messages_with_attachments"],
            total_attachments_saved=result["total_attachments_saved"],
            errors=result.get("errors", [])
        )

        automation_logger.info(
            action="scan_lead_emails",
            status="success",
            message=f"Scanned {response.messages_scanned} messages, saved {response.total_attachments_saved} attachments",
            lead_id=request.lead_id,
            messages_scanned=response.messages_scanned,
            total_attachments_saved=response.total_attachments_saved,
            errors=len(response.errors)
        )

        return response

    except Exception as e:
        automation_logger.error(
            action="scan_lead_emails",
            message=f"Failed to scan emails for lead {request.lead_id}",
            error=e,
            lead_id=request.lead_id,
            email_address=request.email_address
        )
        raise HTTPException(
            status_code=500,
            detail=f"Failed to scan lead emails: {str(e)}"
        )
