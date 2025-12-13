"""
Email Automation Service - Automates saving Gmail attachments to Google Drive.

This service provides:
1. Processing of email attachments for known leads
2. Automatic upload of attachments to Lead's Drive folder
3. Audit logging for all attachment operations

Used by:
- Manual trigger endpoint for testing
- Gmail Push webhooks (when ready)
- Background workers for scheduled processing
"""

from typing import Dict, Any, List, Optional
from datetime import datetime, timezone
import logging

from sqlalchemy.orm import Session

from services.google_gmail_service import GoogleGmailService
from services.hierarchy_service import HierarchyService, get_drive_service
from services.audit_service import create_audit_log, get_audit_actor
from utils.retry import exponential_backoff_retry

logger = logging.getLogger("pipedesk_drive.email_automation")


class EmailAutomationService:
    """
    Service for automating email-related operations such as
    saving attachments from emails to a Lead's Drive folder.
    """

    def __init__(self, db: Session):
        """
        Initialize the EmailAutomationService.

        Args:
            db: SQLAlchemy database session
        """
        self.db = db
        self.gmail_service = GoogleGmailService()
        self.drive_service = get_drive_service()
        self.hierarchy_service = HierarchyService(db, self.drive_service)

    def _get_attachment_data(self, message_id: str, attachment_id: str, user_id: str = 'me') -> bytes:
        """
        Download attachment data from Gmail API.

        Args:
            message_id: Gmail message ID
            attachment_id: Attachment ID within the message
            user_id: Gmail user ID (default: 'me')

        Returns:
            Raw bytes of the attachment content
        """
        self.gmail_service._check_auth()
        
        @exponential_backoff_retry(max_retries=3, initial_delay=1.0)
        def _api_call():
            return self.gmail_service.service.users().messages().attachments().get(
                userId=user_id,
                messageId=message_id,
                id=attachment_id
            ).execute()
        
        result = _api_call()
        
        # Gmail returns attachment data as base64url encoded
        import base64
        data = result.get('data', '')
        if data:
            return base64.urlsafe_b64decode(data)
        return b''

    def process_message_attachments(
        self,
        message_id: str,
        lead_id: str,
        actor_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Process all attachments from a Gmail message and save them to the Lead's Drive folder.

        This method:
        1. Fetches the email message from Gmail
        2. Identifies all attachments (MIME parts with attachmentId)
        3. Resolves the Lead's Drive folder via HierarchyService
        4. Downloads each attachment from Gmail
        5. Uploads each attachment directly to the Lead's Drive folder
        6. Creates an AuditLog entry for each attachment saved

        Args:
            message_id: Gmail message ID to process
            lead_id: UUID of the Lead entity
            actor_id: Optional user ID for audit logging (defaults to context actor)

        Returns:
            Dictionary with processing results:
            {
                "message_id": str,
                "lead_id": str,
                "attachments_processed": int,
                "attachments_saved": List[Dict],
                "errors": List[str]
            }
        """
        logger.info(f"Processing attachments for message {message_id} -> lead {lead_id}")

        result = {
            "message_id": message_id,
            "lead_id": lead_id,
            "attachments_processed": 0,
            "attachments_saved": [],
            "errors": []
        }

        try:
            # 1. Get email details via GmailService
            message_data = self.gmail_service.get_message(message_id, format='full')
            payload = message_data.get('payload', {})

            # 2. Identify attachments (MIME parts)
            attachments = self.gmail_service._extract_attachments(payload)

            if not attachments:
                logger.info(f"No attachments found in message {message_id}")
                return result

            result["attachments_processed"] = len(attachments)
            logger.info(f"Found {len(attachments)} attachments in message {message_id}")

            # 3. Resolve Lead's Folder ID via HierarchyService
            try:
                lead_folder = self.hierarchy_service.ensure_lead_structure(lead_id)
                folder_id = lead_folder.folder_id
                logger.info(f"Resolved Lead folder: {folder_id}")
            except Exception as e:
                error_msg = f"Failed to resolve Lead folder for {lead_id}: {str(e)}"
                logger.error(error_msg)
                result["errors"].append(error_msg)
                return result

            # 4 & 5. Stream download -> Stream upload for each attachment
            for attachment in attachments:
                attachment_id = attachment.get('id')
                filename = attachment.get('filename', 'unnamed_attachment')
                mime_type = attachment.get('mimeType', 'application/octet-stream')
                size = attachment.get('size', 0)

                try:
                    logger.info(f"Processing attachment: {filename} ({mime_type}, {size} bytes)")

                    # Download attachment data
                    attachment_data = self._get_attachment_data(message_id, attachment_id)

                    if not attachment_data:
                        error_msg = f"Failed to download attachment {filename}: empty data"
                        logger.warning(error_msg)
                        result["errors"].append(error_msg)
                        continue

                    # Upload to Drive
                    uploaded_file = self.drive_service.upload_file(
                        file_content=attachment_data,
                        name=filename,
                        mime_type=mime_type,
                        parent_id=folder_id
                    )

                    saved_info = {
                        "filename": filename,
                        "file_id": uploaded_file.get('id'),
                        "web_view_link": uploaded_file.get('webViewLink'),
                        "size": len(attachment_data),
                        "mime_type": mime_type
                    }
                    result["attachments_saved"].append(saved_info)

                    logger.info(f"Uploaded attachment {filename} to Drive: {uploaded_file.get('id')}")

                    # 6. Create AuditLog entry
                    create_audit_log(
                        session=self.db,
                        entity_type="lead",
                        entity_id=lead_id,
                        action="attachment_autosave",
                        changes={
                            "message_id": message_id,
                            "filename": filename,
                            "file_id": uploaded_file.get('id'),
                            "mime_type": mime_type,
                            "size": len(attachment_data)
                        },
                        actor_id=actor_id or get_audit_actor()
                    )

                except Exception as e:
                    error_msg = f"Failed to process attachment {filename}: {str(e)}"
                    logger.error(error_msg, exc_info=True)
                    result["errors"].append(error_msg)

            # Commit audit logs
            self.db.commit()

            logger.info(
                f"Completed processing message {message_id}: "
                f"{len(result['attachments_saved'])} saved, "
                f"{len(result['errors'])} errors"
            )

        except Exception as e:
            error_msg = f"Failed to process message {message_id}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result["errors"].append(error_msg)

        return result

    def scan_and_process_lead_emails(
        self,
        lead_id: str,
        email_address: str,
        max_messages: int = 10,
        actor_id: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Scan recent emails from a specific email address and process their attachments.

        This is a convenience method for processing multiple emails from a known
        lead's email address.

        Args:
            lead_id: UUID of the Lead entity
            email_address: Email address to search for
            max_messages: Maximum number of messages to process (default: 10)
            actor_id: Optional user ID for audit logging

        Returns:
            Dictionary with overall processing results
        """
        logger.info(f"Scanning emails from {email_address} for lead {lead_id}")

        result = {
            "lead_id": lead_id,
            "email_address": email_address,
            "messages_scanned": 0,
            "messages_with_attachments": 0,
            "total_attachments_saved": 0,
            "message_results": [],
            "errors": []
        }

        try:
            # Search for messages from the email address
            query = f"from:{email_address} has:attachment"
            messages_response = self.gmail_service.list_messages(
                query=query,
                max_results=max_messages
            )

            messages = messages_response.get('messages', [])
            result["messages_scanned"] = len(messages)

            for msg_ref in messages:
                message_id = msg_ref.get('id')
                msg_result = self.process_message_attachments(
                    message_id=message_id,
                    lead_id=lead_id,
                    actor_id=actor_id
                )

                result["message_results"].append(msg_result)

                if msg_result["attachments_processed"] > 0:
                    result["messages_with_attachments"] += 1
                    result["total_attachments_saved"] += len(msg_result["attachments_saved"])

                if msg_result["errors"]:
                    result["errors"].extend(msg_result["errors"])

            logger.info(
                f"Completed scanning {result['messages_scanned']} messages, "
                f"saved {result['total_attachments_saved']} attachments"
            )

        except Exception as e:
            error_msg = f"Failed to scan emails for {email_address}: {str(e)}"
            logger.error(error_msg, exc_info=True)
            result["errors"].append(error_msg)

        return result
