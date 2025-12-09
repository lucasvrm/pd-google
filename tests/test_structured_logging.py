"""
Tests for structured JSON logging.
"""

import pytest
import json
import logging
from io import StringIO
from utils.structured_logging import StructuredLogger, mask_email, mask_emails_in_text


def test_mask_email():
    """Test email masking function."""
    assert mask_email("john.doe@example.com") == "j***@example.com"
    assert mask_email("a@example.com") == "a***@example.com"
    assert mask_email("test@domain.co.uk") == "t***@domain.co.uk"
    assert mask_email("") == ""
    assert mask_email(None) is None
    assert mask_email("not-an-email") == "not-an-email"


def test_mask_emails_in_text():
    """Test masking multiple emails in text."""
    text = "Contact john.doe@example.com or jane.smith@company.com"
    masked = mask_emails_in_text(text)
    assert "j***@example.com" in masked
    assert "j***@company.com" in masked
    assert "john.doe@example.com" not in masked
    assert "jane.smith@company.com" not in masked


def test_structured_logger_info():
    """Test structured logging for info level."""
    # Capture log output
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    
    logger = StructuredLogger(service="calendar", logger_name="test.calendar")
    logger.logger.addHandler(handler)
    logger.logger.setLevel(logging.INFO)
    
    logger.info(
        action="create_event",
        status="success",
        message="Event created successfully",
        google_event_id="event123",
        entity_type="deal",
        entity_id="deal-456"
    )
    
    log_output = log_stream.getvalue()
    log_data = json.loads(log_output)
    
    assert log_data["service"] == "calendar"
    assert log_data["action"] == "create_event"
    assert log_data["status"] == "success"
    assert log_data["message"] == "Event created successfully"
    assert log_data["google_event_id"] == "event123"
    assert log_data["entity_type"] == "deal"
    assert log_data["entity_id"] == "deal-456"
    assert "timestamp" in log_data


def test_structured_logger_error():
    """Test structured logging for error level."""
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    
    logger = StructuredLogger(service="calendar", logger_name="test.calendar.error")
    logger.logger.addHandler(handler)
    logger.logger.setLevel(logging.ERROR)
    
    try:
        raise ValueError("Invalid event data")
    except Exception as e:
        logger.error(
            action="create_event",
            message="Failed to create event",
            error=e,
            google_event_id="event789"
        )
    
    log_output = log_stream.getvalue()
    log_data = json.loads(log_output)
    
    assert log_data["service"] == "calendar"
    assert log_data["action"] == "create_event"
    assert log_data["status"] == "error"
    assert log_data["message"] == "Failed to create event"
    assert log_data["error_type"] == "ValueError"
    assert log_data["error_message"] == "Invalid event data"
    assert log_data["google_event_id"] == "event789"


def test_structured_logger_warning():
    """Test structured logging for warning level."""
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    
    logger = StructuredLogger(service="calendar", logger_name="test.calendar.warning")
    logger.logger.addHandler(handler)
    logger.logger.setLevel(logging.WARNING)
    
    logger.warning(
        action="sync",
        status="warning",
        message="Sync token expired, performing full sync",
        entity_type="calendar"
    )
    
    log_output = log_stream.getvalue()
    log_data = json.loads(log_output)
    
    assert log_data["service"] == "calendar"
    assert log_data["action"] == "sync"
    assert log_data["status"] == "warning"
    assert log_data["message"] == "Sync token expired, performing full sync"
    assert log_data["entity_type"] == "calendar"


def test_structured_logger_masks_emails():
    """Test that structured logger masks emails in messages and error messages."""
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    
    logger = StructuredLogger(service="calendar", logger_name="test.calendar.mask")
    logger.logger.addHandler(handler)
    logger.logger.setLevel(logging.ERROR)
    
    try:
        raise Exception("Failed to send to john.doe@example.com and jane@company.com")
    except Exception as e:
        logger.error(
            action="send_invite",
            message="Error sending invites to john.doe@example.com",
            error=e
        )
    
    log_output = log_stream.getvalue()
    log_data = json.loads(log_output)
    
    # Check that emails are masked in error_message
    assert "j***@example.com" in log_data["error_message"]
    assert "j***@company.com" in log_data["error_message"]
    assert "john.doe@example.com" not in log_data["error_message"]
    assert "jane@company.com" not in log_data["error_message"]
    
    # Check that message itself doesn't contain unmasked email
    assert "j***@example.com" in log_data["message"]
    assert "john.doe@example.com" not in log_data["message"]


def test_structured_logger_extra_fields():
    """Test that extra fields are included in log output."""
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    
    logger = StructuredLogger(service="calendar", logger_name="test.calendar.extra")
    logger.logger.addHandler(handler)
    logger.logger.setLevel(logging.INFO)
    
    logger.info(
        action="update_event",
        status="success",
        message="Event updated",
        google_event_id="event999",
        attendee_count=5,
        duration_minutes=60,
        has_meet_link=True
    )
    
    log_output = log_stream.getvalue()
    log_data = json.loads(log_output)
    
    assert log_data["attendee_count"] == 5
    assert log_data["duration_minutes"] == 60
    assert log_data["has_meet_link"] is True


def test_structured_logger_optional_fields():
    """Test that optional fields are omitted when not provided."""
    log_stream = StringIO()
    handler = logging.StreamHandler(log_stream)
    
    logger = StructuredLogger(service="calendar", logger_name="test.calendar.optional")
    logger.logger.addHandler(handler)
    logger.logger.setLevel(logging.INFO)
    
    logger.info(
        action="list_events",
        status="success",
        message="Listed 10 events"
    )
    
    log_output = log_stream.getvalue()
    log_data = json.loads(log_output)
    
    # Optional fields should not be present
    assert "google_event_id" not in log_data
    assert "entity_type" not in log_data
    assert "entity_id" not in log_data
    assert "error_type" not in log_data
    assert "error_message" not in log_data
    
    # Required fields should be present
    assert log_data["service"] == "calendar"
    assert log_data["action"] == "list_events"
    assert log_data["status"] == "success"
    assert log_data["message"] == "Listed 10 events"
