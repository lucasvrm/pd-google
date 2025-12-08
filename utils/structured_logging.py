"""
Structured JSON logging for Calendar operations.
Provides consistent logging format with required fields:
- service, action, status, google_event_id, entity_type, entity_id
- error_type, error_message (in case of failure)
- Masks sensitive data (partial email addresses)
"""

import logging
import json
from datetime import datetime
from typing import Optional, Dict, Any
import re


def mask_email(email: Optional[str]) -> Optional[str]:
    """
    Partially mask an email address for privacy.
    Example: john.doe@example.com -> j***@example.com
    """
    if not email or '@' not in email:
        return email
    
    local, domain = email.split('@', 1)
    if len(local) <= 1:
        masked_local = local[0] + '***'
    else:
        masked_local = local[0] + '***'
    
    return f"{masked_local}@{domain}"


def mask_emails_in_text(text: str) -> str:
    """
    Find and mask all email addresses in a text string.
    """
    # Regex pattern for email addresses
    email_pattern = r'\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Z|a-z]{2,}\b'
    
    def replacer(match):
        return mask_email(match.group(0))
    
    return re.sub(email_pattern, replacer, text)


class StructuredLogger:
    """
    Structured logger for Calendar operations.
    Outputs JSON-formatted logs with consistent fields.
    """
    
    def __init__(self, service: str = "calendar", logger_name: str = "pipedesk_drive.calendar"):
        self.service = service
        self.logger = logging.getLogger(logger_name)
    
    def _log(
        self,
        level: int,
        action: str,
        status: str,
        message: str,
        google_event_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        error_type: Optional[str] = None,
        error_message: Optional[str] = None,
        mask_sensitive: bool = True,
        **extra_fields
    ):
        """
        Internal method to log structured JSON.
        """
        log_data = {
            "timestamp": datetime.now().astimezone().isoformat(),
            "service": self.service,
            "action": action,
            "status": status,
            "message": mask_emails_in_text(message) if mask_sensitive else message,
        }
        
        # Add optional fields
        if google_event_id:
            log_data["google_event_id"] = google_event_id
        if entity_type:
            log_data["entity_type"] = entity_type
        if entity_id:
            log_data["entity_id"] = entity_id
        if error_type:
            log_data["error_type"] = error_type
        if error_message:
            # Mask emails in error messages
            log_data["error_message"] = mask_emails_in_text(error_message) if mask_sensitive else error_message
        
        # Add any extra fields
        for key, value in extra_fields.items():
            if isinstance(value, str) and mask_sensitive:
                log_data[key] = mask_emails_in_text(value)
            else:
                log_data[key] = value
        
        # Output as JSON
        json_log = json.dumps(log_data)
        self.logger.log(level, json_log)
    
    def info(
        self,
        action: str,
        status: str = "success",
        message: str = "",
        google_event_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        **extra_fields
    ):
        """
        Log informational message.
        
        Args:
            action: The operation being performed (e.g., "create_event", "sync", "watch")
            status: Status of the operation (default: "success")
            message: Human-readable message
            google_event_id: Google Calendar event ID
            entity_type: Type of entity (e.g., "company", "lead", "deal")
            entity_id: ID of the entity
            **extra_fields: Additional fields to include in the log
        """
        self._log(
            logging.INFO,
            action=action,
            status=status,
            message=message,
            google_event_id=google_event_id,
            entity_type=entity_type,
            entity_id=entity_id,
            **extra_fields
        )
    
    def warning(
        self,
        action: str,
        status: str = "warning",
        message: str = "",
        google_event_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        **extra_fields
    ):
        """Log warning message."""
        self._log(
            logging.WARNING,
            action=action,
            status=status,
            message=message,
            google_event_id=google_event_id,
            entity_type=entity_type,
            entity_id=entity_id,
            **extra_fields
        )
    
    def error(
        self,
        action: str,
        message: str,
        error: Optional[Exception] = None,
        google_event_id: Optional[str] = None,
        entity_type: Optional[str] = None,
        entity_id: Optional[str] = None,
        **extra_fields
    ):
        """
        Log error message.
        
        Args:
            action: The operation that failed
            message: Human-readable error message
            error: Exception object (if available)
            google_event_id: Google Calendar event ID
            entity_type: Type of entity
            entity_id: ID of the entity
            **extra_fields: Additional fields
        """
        error_type = None
        error_message = None
        
        if error:
            error_type = type(error).__name__
            error_message = str(error)
        
        self._log(
            logging.ERROR,
            action=action,
            status="error",
            message=message,
            google_event_id=google_event_id,
            entity_type=entity_type,
            entity_id=entity_id,
            error_type=error_type,
            error_message=error_message,
            **extra_fields
        )


# Singleton instance for Calendar logging
calendar_logger = StructuredLogger(service="calendar")
