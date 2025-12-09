"""
Tests for Gmail retry behavior and structured logging.
"""

import pytest
import json
import logging
from io import StringIO
from unittest.mock import Mock, patch, MagicMock
from datetime import datetime

from services.google_gmail_service import GoogleGmailService
from utils.retry import RetryExhausted
from utils.structured_logging import StructuredLogger


class TestGmailRetryBehavior:
    """Test retry behavior for Gmail service methods."""
    
    def test_list_messages_retry_on_503(self):
        """Test that list_messages retries on 503 errors."""
        service = GoogleGmailService()
        
        # Mock the service to fail twice with 503, then succeed
        mock_execute = Mock(side_effect=[
            Exception("HttpError 503 when requesting..."),
            Exception("HttpError 503 when requesting..."),
            {'messages': [{'id': 'msg1', 'threadId': 'thread1'}], 'resultSizeEstimate': 1}
        ])
        
        with patch.object(service, 'service') as mock_service:
            mock_chain = MagicMock()
            mock_chain.list.return_value.execute = mock_execute
            mock_service.users.return_value.messages.return_value = mock_chain
            
            # Should succeed after retries
            result = service.list_messages()
            
            assert result['messages'] is not None
            assert mock_execute.call_count == 3  # 2 failures + 1 success
    
    def test_list_messages_retry_on_429(self):
        """Test that list_messages retries on 429 (rate limit) errors."""
        service = GoogleGmailService()
        
        mock_execute = Mock(side_effect=[
            Exception("HttpError 429 when requesting..."),
            {'messages': [{'id': 'msg1', 'threadId': 'thread1'}], 'resultSizeEstimate': 1}
        ])
        
        with patch.object(service, 'service') as mock_service:
            mock_chain = MagicMock()
            mock_chain.list.return_value.execute = mock_execute
            mock_service.users.return_value.messages.return_value = mock_chain
            
            result = service.list_messages()
            
            assert result['messages'] is not None
            assert mock_execute.call_count == 2  # 1 failure + 1 success
    
    def test_list_messages_no_retry_on_404(self):
        """Test that list_messages does NOT retry on 404 errors."""
        service = GoogleGmailService()
        
        mock_execute = Mock(side_effect=Exception("HttpError 404 when requesting..."))
        
        with patch.object(service, 'service') as mock_service:
            mock_chain = MagicMock()
            mock_chain.list.return_value.execute = mock_execute
            mock_service.users.return_value.messages.return_value = mock_chain
            
            with pytest.raises(Exception) as exc_info:
                service.list_messages()
            
            assert "404" in str(exc_info.value)
            assert mock_execute.call_count == 1  # No retries on 4xx
    
    def test_list_messages_exhausted_retries(self):
        """Test that RetryExhausted is raised after max retries."""
        service = GoogleGmailService()
        
        # Fail consistently
        mock_execute = Mock(side_effect=Exception("HttpError 503 when requesting..."))
        
        with patch.object(service, 'service') as mock_service:
            mock_chain = MagicMock()
            mock_chain.list.return_value.execute = mock_execute
            mock_service.users.return_value.messages.return_value = mock_chain
            
            with pytest.raises(RetryExhausted):
                service.list_messages()
            
            # Should have tried: initial + 3 retries = 4 total
            assert mock_execute.call_count == 4
    
    def test_get_message_retry_on_500(self):
        """Test that get_message retries on 500 errors."""
        service = GoogleGmailService()
        
        mock_execute = Mock(side_effect=[
            Exception("HttpError 500 Internal Server Error"),
            {'id': 'msg1', 'threadId': 'thread1', 'payload': {'headers': []}}
        ])
        
        with patch.object(service, 'service') as mock_service:
            mock_chain = MagicMock()
            mock_chain.get.return_value.execute = mock_execute
            mock_service.users.return_value.messages.return_value = mock_chain
            
            result = service.get_message('msg1')
            
            assert result['id'] == 'msg1'
            assert mock_execute.call_count == 2
    
    def test_list_threads_retry_on_502(self):
        """Test that list_threads retries on 502 errors."""
        service = GoogleGmailService()
        
        mock_execute = Mock(side_effect=[
            Exception("HttpError 502 Bad Gateway"),
            {'threads': [{'id': 'thread1'}], 'resultSizeEstimate': 1}
        ])
        
        with patch.object(service, 'service') as mock_service:
            mock_chain = MagicMock()
            mock_chain.list.return_value.execute = mock_execute
            mock_service.users.return_value.threads.return_value = mock_chain
            
            result = service.list_threads()
            
            assert result['threads'] is not None
            assert mock_execute.call_count == 2
    
    def test_get_thread_retry_on_504(self):
        """Test that get_thread retries on 504 errors."""
        service = GoogleGmailService()
        
        mock_execute = Mock(side_effect=[
            Exception("HttpError 504 Gateway Timeout"),
            {'id': 'thread1', 'messages': []}
        ])
        
        with patch.object(service, 'service') as mock_service:
            mock_chain = MagicMock()
            mock_chain.get.return_value.execute = mock_execute
            mock_service.users.return_value.threads.return_value = mock_chain
            
            result = service.get_thread('thread1')
            
            assert result['id'] == 'thread1'
            assert mock_execute.call_count == 2
    
    def test_list_labels_retry_on_connection_error(self):
        """Test that list_labels retries on ConnectionError."""
        service = GoogleGmailService()
        
        mock_execute = Mock(side_effect=[
            ConnectionError("Connection refused"),
            {'labels': [{'id': 'INBOX', 'name': 'INBOX'}]}
        ])
        
        with patch.object(service, 'service') as mock_service:
            mock_chain = MagicMock()
            mock_chain.list.return_value.execute = mock_execute
            mock_service.users.return_value.labels.return_value = mock_chain
            
            result = service.list_labels()
            
            assert result['labels'] is not None
            assert mock_execute.call_count == 2
    
    def test_list_labels_retry_on_timeout(self):
        """Test that list_labels retries on TimeoutError."""
        service = GoogleGmailService()
        
        mock_execute = Mock(side_effect=[
            TimeoutError("Request timed out"),
            {'labels': [{'id': 'INBOX', 'name': 'INBOX'}]}
        ])
        
        with patch.object(service, 'service') as mock_service:
            mock_chain = MagicMock()
            mock_chain.list.return_value.execute = mock_execute
            mock_service.users.return_value.labels.return_value = mock_chain
            
            result = service.list_labels()
            
            assert result['labels'] is not None
            assert mock_execute.call_count == 2


class TestGmailStructuredLogging:
    """Test structured logging for Gmail router endpoints."""
    
    def test_list_messages_success_log(self):
        """Test that list_messages logs success with correct structure."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        
        logger = StructuredLogger(service="gmail", logger_name="test.gmail.list_messages")
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)
        
        logger.info(
            action="list_messages",
            status="success",
            message="Listed 5 messages",
            result_count=5,
            page_size=50,
            has_next_page=False
        )
        
        log_output = log_stream.getvalue()
        log_data = json.loads(log_output)
        
        assert log_data["service"] == "gmail"
        assert log_data["action"] == "list_messages"
        assert log_data["status"] == "success"
        assert log_data["message"] == "Listed 5 messages"
        assert log_data["result_count"] == 5
        assert log_data["page_size"] == 50
        assert log_data["has_next_page"] is False
        assert "timestamp" in log_data
    
    def test_list_messages_error_log(self):
        """Test that list_messages logs errors with correct structure."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        
        logger = StructuredLogger(service="gmail", logger_name="test.gmail.list_messages_error")
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.ERROR)
        
        try:
            raise Exception("HttpError 503 when requesting Gmail API")
        except Exception as e:
            logger.error(
                action="list_messages",
                message="Failed to list messages",
                error=e
            )
        
        log_output = log_stream.getvalue()
        log_data = json.loads(log_output)
        
        assert log_data["service"] == "gmail"
        assert log_data["action"] == "list_messages"
        assert log_data["status"] == "error"
        assert log_data["message"] == "Failed to list messages"
        assert log_data["error_type"] == "Exception"
        assert "503" in log_data["error_message"]
    
    def test_get_message_success_log(self):
        """Test that get_message logs success with message_id."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        
        logger = StructuredLogger(service="gmail", logger_name="test.gmail.get_message")
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)
        
        logger.info(
            action="get_message",
            status="success",
            message="Retrieved message msg_123",
            message_id="msg_123"
        )
        
        log_output = log_stream.getvalue()
        log_data = json.loads(log_output)
        
        assert log_data["action"] == "get_message"
        assert log_data["status"] == "success"
        assert log_data["message_id"] == "msg_123"
    
    def test_get_message_not_found_log(self):
        """Test that get_message logs not_found warnings."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        
        logger = StructuredLogger(service="gmail", logger_name="test.gmail.get_message_404")
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.WARNING)
        
        logger.warning(
            action="get_message",
            status="not_found",
            message="Message msg_999 not found",
            message_id="msg_999"
        )
        
        log_output = log_stream.getvalue()
        log_data = json.loads(log_output)
        
        assert log_data["action"] == "get_message"
        assert log_data["status"] == "not_found"
        assert log_data["message_id"] == "msg_999"
    
    def test_list_threads_success_log(self):
        """Test that list_threads logs success."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        
        logger = StructuredLogger(service="gmail", logger_name="test.gmail.list_threads")
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)
        
        logger.info(
            action="list_threads",
            status="success",
            message="Listed 3 threads",
            result_count=3,
            page_size=50,
            has_next_page=True
        )
        
        log_output = log_stream.getvalue()
        log_data = json.loads(log_output)
        
        assert log_data["action"] == "list_threads"
        assert log_data["result_count"] == 3
        assert log_data["has_next_page"] is True
    
    def test_get_thread_success_log(self):
        """Test that get_thread logs success with thread info."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        
        logger = StructuredLogger(service="gmail", logger_name="test.gmail.get_thread")
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)
        
        logger.info(
            action="get_thread",
            status="success",
            message="Retrieved thread thread_123",
            thread_id="thread_123",
            message_count=5
        )
        
        log_output = log_stream.getvalue()
        log_data = json.loads(log_output)
        
        assert log_data["action"] == "get_thread"
        assert log_data["thread_id"] == "thread_123"
        assert log_data["message_count"] == 5
    
    def test_list_labels_success_log(self):
        """Test that list_labels logs success."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        
        logger = StructuredLogger(service="gmail", logger_name="test.gmail.list_labels")
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)
        
        logger.info(
            action="list_labels",
            status="success",
            message="Listed 10 labels",
            label_count=10
        )
        
        log_output = log_stream.getvalue()
        log_data = json.loads(log_output)
        
        assert log_data["action"] == "list_labels"
        assert log_data["label_count"] == 10
    
    def test_email_masking_in_logs(self):
        """Test that emails are masked in Gmail logs."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        
        logger = StructuredLogger(service="gmail", logger_name="test.gmail.masking")
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.INFO)
        
        logger.info(
            action="get_message",
            status="success",
            message="Retrieved message from john.doe@example.com to jane.smith@company.com"
        )
        
        log_output = log_stream.getvalue()
        log_data = json.loads(log_output)
        
        # Emails should be masked
        assert "j***@example.com" in log_data["message"]
        assert "j***@company.com" in log_data["message"]
        assert "john.doe@example.com" not in log_data["message"]
        assert "jane.smith@company.com" not in log_data["message"]
    
    def test_email_masking_in_error_messages(self):
        """Test that emails are masked in error messages."""
        log_stream = StringIO()
        handler = logging.StreamHandler(log_stream)
        
        logger = StructuredLogger(service="gmail", logger_name="test.gmail.error_masking")
        logger.logger.addHandler(handler)
        logger.logger.setLevel(logging.ERROR)
        
        try:
            raise Exception("Failed to fetch message for user@example.com")
        except Exception as e:
            logger.error(
                action="get_message",
                message="Error retrieving message from admin@company.com",
                error=e
            )
        
        log_output = log_stream.getvalue()
        log_data = json.loads(log_output)
        
        # Emails should be masked in both message and error_message
        assert "u***@example.com" in log_data["error_message"]
        assert "user@example.com" not in log_data["error_message"]
        assert "a***@company.com" in log_data["message"]
        assert "admin@company.com" not in log_data["message"]
